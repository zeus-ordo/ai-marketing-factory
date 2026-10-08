"""Executable image-RAG lifecycle and payload acceptance tests.

The deterministic tests use the real campaign and enrichment application
functions with an in-memory persistence boundary and controllable providers.
The final live smoke test is opt-in and uses the existing live-service fixture.
"""

from __future__ import annotations

import base64
import importlib
import io
import sys
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, QueryParams, UploadFile


ROOT = Path(__file__).parents[1]
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _load_package(alias: str, directory: Path):
    spec = spec_from_file_location(alias, directory / "__init__.py", submodule_search_locations=[str(directory)])
    assert spec and spec.loader
    package = module_from_spec(spec)
    sys.modules[alias] = package
    spec.loader.exec_module(package)
    return importlib.import_module(f"{alias}.main")


campaign_main = _load_package("task7_campaign_app", ROOT / "services" / "campaign_service" / "app")
worker_main = _load_package("task7_worker_app", ROOT / "services" / "worker_enrichment" / "app")
from task7_campaign_app.context_assembler import (  # noqa: E402
    ContextSourceItem,
    assemble_generation_context,
    build_generation_reference_payload,
)
from task7_campaign_app.schemas import CampaignBrief, CampaignRecord, Deliverables, TargetAudience  # noqa: E402


def _request() -> SimpleNamespace:
    return SimpleNamespace(headers=Headers())


def _upload() -> UploadFile:
    return UploadFile(
        filename="valid.png",
        file=io.BytesIO(PNG_BYTES),
        headers=Headers({"content-type": "image/png"}),
    )


class LifecycleStore:
    def __init__(self, company_id: str = "company-a"):
        self.items: dict[str, dict] = {}
        self.analysis: dict[str, dict] = {}
        self.company_id = company_id
        self.fail_next = False

    def create_knowledge_item(self, item):
        value = item.model_dump(mode="python") if hasattr(item, "model_dump") else dict(item)
        self.items[value["item_id"]] = value
        return value

    def list_knowledge_items(self, company_id):
        return [item for item in self.items.values() if item["company_id"] == company_id]

    def create_image_analysis(self, item_id, version):
        value = {
            "item_id": item_id,
            "analysis_version": version,
            "analysis_status": "pending",
            "attributes": {},
            "retryable": True,
            "analyzed_at": None,
        }
        self.analysis[item_id] = value
        return value

    def get_image_analysis(self, item_id, analysis_version=None):
        value = self.analysis.get(item_id)
        if value and (analysis_version is None or value["analysis_version"] == analysis_version):
            return value
        return None

    def get_image_item(self, item_id):
        item = self.items.get(item_id)
        if not item:
            return None
        metadata = item.get("metadata", {})
        return {
            "item_id": item_id,
            "title": item["title"],
            "description": item["description"],
            "stored_path": metadata.get("stored_path"),
            "mime_type": metadata.get("file_type", "image/png"),
        }

    def list_ready_image_analysis(self, company_id, industry, limit, role=None):
        return [
            {
                **analysis,
                "company_id": item["company_id"],
                "title": item["title"],
                "description": item["description"],
                "metadata": {**item.get("metadata", {}), "industry": industry},
            }
            for item_id, item in self.items.items()
            for analysis in [self.analysis.get(item_id)]
            if analysis and item["company_id"] == company_id
        ]

    def claim_image_analysis(self, item_id, version):
        value = self.analysis[item_id]
        if value["analysis_status"] not in {"pending", "failed"} or (value["analysis_status"] == "failed" and not value["retryable"]):
            return False
        value.update(analysis_status="processing", retryable=True)
        return True

    def complete_image_analysis(self, item_id, version, attributes, embedding, embedding_model):
        self.analysis[item_id].update(
            analysis_status="ready", retryable=False, attributes=attributes, analyzed_at=datetime.now(timezone.utc)
        )
        return {"item_id": item_id, "analysis_status": "ready"}

    def fail_image_analysis(self, item_id, version, error_code, error_detail):
        self.analysis[item_id].update(
            analysis_status="failed", retryable=True, error_code=error_code, error_detail=error_detail
        )
        return {"item_id": item_id, "analysis_status": "failed"}

    def reset_image_analysis_for_retry(self, item_id, version):
        value = self.analysis[item_id]
        value.update(analysis_status="pending", retryable=True)
        return value


class GoodAnalysisProvider:
    def analyze(self, image_path, mime_type, title, description):
        assert Path(image_path).read_bytes() == PNG_BYTES
        return {"objects": ["pixel"], "style": "minimal"}


class GoodEmbeddingProvider:
    def embed(self, text):
        assert "private" not in text.lower()
        return [0.1, 0.2]


class FailingAnalysisProvider:
    def analyze(self, *_args):
        raise RuntimeError("provider secret /private/image.png")


@pytest.fixture
def campaign_config(monkeypatch, tmp_path):
    store = LifecycleStore()
    monkeypatch.setattr(campaign_main, "persistence", store)
    monkeypatch.setattr(campaign_main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _request: False)
    monkeypatch.setattr(campaign_main, "require_jwt", lambda _request: SimpleNamespace(company_id="company-a", sub="user-a", permissions=[]))
    monkeypatch.setattr(campaign_main, "resolve_folder_for_actor", lambda *_args: None)
    monkeypatch.setattr(campaign_main, "enqueue_image_enrichment", lambda *_args: None)
    monkeypatch.setattr(worker_main, "persistence", store)
    return store


def _run_worker(monkeypatch, store, provider):
    monkeypatch.setattr(worker_main.providers, "analysis_provider", provider)
    monkeypatch.setattr(worker_main.providers, "embedding_provider", GoodEmbeddingProvider())
    return worker_main.process_image_enrichment_job({"item_id": next(iter(store.items)), "analysis_version": "image-rag-v1"})


def test_upload_pending_then_worker_ready(campaign_config, monkeypatch):
    result = campaign_main.upload_knowledge_item(_request(), "One pixel", "", "", None, "", _upload())
    item_id = result.item_id
    uploaded_path = campaign_config.items[item_id]["metadata"]["stored_path"]
    assert Path(uploaded_path).read_bytes() == PNG_BYTES
    assert campaign_config.get_image_item(item_id)["stored_path"] == uploaded_path
    assert result.analysis.analysis_status == "pending"
    assert campaign_config.get_image_analysis(item_id)["analysis_status"] == "pending"
    response_data = result.model_dump_json()
    for forbidden in ("stored_path", "private", "base64", "bytes"):
        assert forbidden not in response_data.lower()

    completed = _run_worker(monkeypatch, campaign_config, GoodAnalysisProvider())
    assert completed == {"item_id": item_id, "status": "ready"}
    assert campaign_config.get_image_analysis(item_id)["analysis_status"] == "ready"


def test_provider_failure_then_retry_ready_is_induced_by_test_provider(campaign_config, monkeypatch):
    result = campaign_main.upload_knowledge_item(_request(), "Retry me", "", "", None, "", _upload())
    item_id = result.item_id

    failed = _run_worker(monkeypatch, campaign_config, FailingAnalysisProvider())
    assert failed["status"] == "failed"
    failed_record = campaign_config.get_image_analysis(item_id)
    assert failed_record["retryable"] is True
    assert "/private/image.png" not in str(failed_record)
    assert "secret" not in str(failed_record)

    retry = campaign_main.retry_knowledge_item_analysis(_request(), item_id)
    assert retry.analysis_status == "pending"
    completed = _run_worker(monkeypatch, campaign_config, GoodAnalysisProvider())
    assert completed["status"] == "ready"


def test_analysis_api_is_ready_only_and_safe(campaign_config, monkeypatch):
    result = campaign_main.upload_knowledge_item(_request(), "Safe API", "", "", None, "", _upload())
    _run_worker(monkeypatch, campaign_config, GoodAnalysisProvider())
    response = campaign_main.get_knowledge_item_analysis(_request(), result.item_id)
    serialized = response.model_dump_json()
    assert response.analysis_status == "ready"
    for forbidden in ("stored_path", "private", "base64", "bytes"):
        assert forbidden not in serialized.lower()


def test_ready_only_retrieval_excludes_pending_and_failed(campaign_config):
    campaign = _campaign()
    for item_id, status in (("pending-item", "pending"), ("failed-item", "failed"), ("ready-item", "ready")):
        campaign_config.items[item_id] = {
            "item_id": item_id,
            "company_id": "company-a",
            "title": item_id,
            "description": "Restaurant foodie",
            "metadata": {"industry": "Restaurant", "role": "foodie", "file_type": "image/png"},
        }
        campaign_config.analysis[item_id] = {
            "item_id": item_id,
            "company_id": "company-a",
            "analysis_version": "image-rag-v1",
            "analysis_status": status,
            "attributes": {"style": ["warm"]},
            "retryable": status != "ready",
            "analyzed_at": None,
        }

    result = campaign_main.list_enriched_knowledge_context(campaign)
    assert [row["item_id"] for row in result] == ["ready-item"]
    assert result[0]["analysis_status"] == "ready"


def _campaign() -> CampaignRecord:
    return CampaignRecord(
        company_id="company-a",
        campaign_id="campaign-a",
        created_at=datetime.now(timezone.utc),
        brief=CampaignBrief(
            campaign_name="E2E",
            product_name="Product",
            industry_category="Restaurant",
            objective="awareness",
            target_audience=TargetAudience(age_range="all", gender="all", persona="foodie"),
            platforms=["instagram"],
            budget=100,
            brand_tone=["warm"],
            deliverables=Deliverables(image_assets=1),
            deadline=datetime.now(timezone.utc),
        ),
    )


def test_copy_payload_has_attributes_without_images_and_image_anchors_are_bounded(tmp_path, monkeypatch):
    campaign = _campaign()
    anchor_paths = []
    items = [
        ContextSourceItem(
            "industry_attribute_rag", f"anchor-{index}", f"anchor-{index}.png", "safe visual",
            {
                "mime_type": "image/png", "attributes": {"style": ["warm"]}, "score": index, "role": "foodie",
                "stored_path": str(tmp_path / f"anchor-{index}.png"),
            },
        )
        for index in range(6)
    ]
    for index in range(6):
        path = tmp_path / f"anchor-{index}.png"
        path.write_bytes(PNG_BYTES)
        anchor_paths.append(path)
    snapshot = assemble_generation_context(campaign, items, [], [], 100)
    copy_payload = build_generation_reference_payload(snapshot, "copywriting")
    image_payload = build_generation_reference_payload(snapshot, "image_generation")
    assert len(copy_payload["attributes"]) == 6
    assert copy_payload["visual_anchors"] == []
    assert len(image_payload["visual_anchors"]) == 3
    assert all("stored_path" not in str(value) for value in image_payload["visual_anchors"])

    worker_payload = campaign_main.build_worker_payload_for_task(
        campaign,
        {"task_id": "task", "task_type": "image_generation", "run_id": "run"},
        snapshot,
    )
    safe_audit = worker_payload["reference_audit"]
    safe_context = campaign_main._sanitize_persisted_context(worker_payload)
    for safe_data in (safe_audit, safe_context):
        serialized = str(safe_data).lower()
        assert "stored_path" not in serialized
        assert "private" not in serialized
        assert "base64" not in serialized
        assert "bytes" not in serialized

    captured = []
    capture_store = SimpleNamespace(save_llm_generation_payload=lambda value: captured.append(value))
    monkeypatch.setattr(campaign_main, "persistence", capture_store)
    campaign_main._capture_worker_payload(worker_payload, "image_generation", campaign.campaign_id, "task", raise_on_failure=True)
    persisted_context = captured[0]["context"]
    assert "reference_images" not in persisted_context
    for forbidden in ("stored_path", "private", "base64", "bytes"):
        assert forbidden not in str(persisted_context).lower()


def test_optional_pack_is_excluded_and_mandatory_failure_is_asserted(tmp_path):
    campaign = _campaign()
    manual = ContextSourceItem("campaign_reference", "manual", "manual.png", "", {"mime_type": "image/png", "stored_path": str(tmp_path / "manual.png")})
    pack_items = [
        ContextSourceItem(
            "platform_default", f"pack-{index}", f"pack-{index}.png", "",
            {"mime_type": "image/png", "stored_path": str(tmp_path / f"pack-{index}.png"), "pack_id": "pack", "pack_role": "style", "selection_mode": "optional", "priority": 1},
        )
        for index in range(7)
    ]
    for path in [tmp_path / "manual.png", *[tmp_path / f"pack-{index}.png" for index in range(7)]]:
        path.write_bytes(PNG_BYTES)
    optional = assemble_generation_context(campaign, [manual, *pack_items], [], [], 100)
    payload = campaign_main.build_worker_payload_for_task(campaign, {"task_id": "task", "task_type": "image_generation", "run_id": "run"}, optional)
    assert payload["reference_audit"]["selected_count"] == 1
    assert payload["reference_audit"]["references"][0]["reference_id"] == "manual"
    assert all(reference.get("reference_pack_id") != "pack" for reference in payload["reference_audit"]["references"])

    mandatory = pack_items[0].__class__(pack_items[0].source_type, pack_items[0].source_id, pack_items[0].label, "", {**dict(pack_items[0].metadata), "selection_mode": "mandatory", "stored_path": str(tmp_path / "missing.png")})
    with pytest.raises(HTTPException) as error:
        campaign_main.build_worker_payload_for_task(campaign, {"task_id": "task", "task_type": "image_generation", "run_id": "run"}, assemble_generation_context(campaign, [mandatory], [], [], 100))
    assert error.value.status_code == 422
    assert error.value.detail["failures"][0]["mandatory"] is True


def test_company_isolation_and_platform_visibility(campaign_config, monkeypatch):
    campaign_config.items["company-b-item"] = {"item_id": "company-b-item", "company_id": "company-b", "title": "Other", "description": "", "metadata": {}}
    campaign_config.analysis["company-b-item"] = {"item_id": "company-b-item", "analysis_version": "image-rag-v1", "analysis_status": "ready", "attributes": {}, "retryable": False, "analyzed_at": None}
    with pytest.raises(HTTPException) as error:
        campaign_main.get_knowledge_item_analysis(_request(), "company-b-item")
    assert error.value.status_code == 404

    platform_item = {
        "item_id": "platform-item", "company_id": "platform", "title": "Platform", "description": "", "metadata": {}
    }
    campaign_config.items["platform-item"] = platform_item
    campaign_config.analysis["platform-item"] = {
        "item_id": "platform-item", "analysis_version": "image-rag-v1", "analysis_status": "ready",
        "attributes": {}, "retryable": False, "analyzed_at": None,
    }
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _request: True)
    platform_request = SimpleNamespace(headers=Headers(), query_params=QueryParams())
    assert campaign_main.get_knowledge_item_analysis(platform_request, "platform-item").analysis_status == "ready"


@pytest.mark.e2e
def test_live_deployed_boundary_upload_pending_requires_explicit_runtime_infrastructure(campaign_client):
    response = campaign_client.post(
        "/api/v1/knowledge-items/upload",
        data={"title": "live image"},
        files={"file": ("live.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["analysis"]["analysis_status"] == "pending"
