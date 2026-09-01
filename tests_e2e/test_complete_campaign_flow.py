"""Deterministic acceptance coverage for the complete campaign generation flow.

These tests run the real service functions and FastAPI app in-process. Provider,
storage, and worker boundaries are replaced with fixtures, so this module never
calls Google, Gemini, PostgreSQL, Redis, or a live worker.
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).parents[1]
CAMPAIGN_SERVICE = ROOT / "services" / "campaign_service"
ORCHESTRATOR_SERVICE = ROOT / "services" / "orchestrator"
os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(CAMPAIGN_SERVICE))

from app import main as campaign_main  # noqa: E402
from app.context_assembler import ContextSourceItem, assemble_generation_context  # noqa: E402
from app.external_search import ExternalSearchError, GoogleCustomSearchProvider, build_search_provider  # noqa: E402
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TaskRecord, TargetAudience  # noqa: E402


def load_orchestrator():
    """Load the second service's app package without replacing campaign_main."""
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    sys.path.insert(0, str(ORCHESTRATOR_SERVICE))
    return importlib.import_module("app.main")


def campaign(campaign_id: str = "camp-e2e") -> CampaignRecord:
    return CampaignRecord(
        company_id="company-e2e",
        campaign_id=campaign_id,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        brief=CampaignBrief(
            campaign_name="Deterministic launch",
            product_name="New drink",
            objective="awareness",
            industry_category="Restaurant",
            project_description="Seasonal campaign brief",
            target_audience=TargetAudience(age_range="25-44", gender="all", persona="foodies"),
            platforms=["instagram"],
            budget=1000,
            brand_tone=["warm"],
            deliverables=Deliverables(copy_variants=1, image_assets=1, short_video_assets=0, ads_strategy=0),
            deadline=datetime(2026, 10, 1, tzinfo=timezone.utc),
        ),
    )


def brief_payload() -> dict[str, Any]:
    return campaign().brief.model_dump(mode="json")


def source(source_type: str, source_id: str, text: str, **metadata: Any) -> ContextSourceItem:
    return ContextSourceItem(source_type, source_id, source_id, text, metadata)


def test_api_rejects_each_required_field_without_persisting(monkeypatch: pytest.MonkeyPatch):
    calls: list[Any] = []

    class Store:
        def create_campaign(self, *_args):
            calls.append(True)
            raise AssertionError("invalid campaign must not be persisted")

    monkeypatch.setattr(campaign_main, "store", Store())
    monkeypatch.setattr(campaign_main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    client = TestClient(campaign_main.app)
    for field in ("campaign_name", "product_name", "objective", "industry_category", "project_description"):
        payload = brief_payload()
        payload.pop(field)
        response = client.post("/api/v1/campaigns", json=payload, headers={"X-Internal-Api-Key": "test-key"})
        assert response.status_code == 422, (field, response.text)
        assert field in response.text
    assert calls == []


def test_api_requires_positive_budget_for_ads_and_allows_zero_without_ads(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(campaign_main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    client = TestClient(campaign_main.app)
    ads = brief_payload() | {"budget": 0, "deliverables": {"ads_strategy": 1}}
    response = client.post("/api/v1/campaigns", json=ads, headers={"X-Internal-Api-Key": "test-key"})
    assert response.status_code == 422
    assert "budget" in response.text

    no_ads = brief_payload() | {"budget": 0, "deliverables": {"ads_strategy": 0}}
    monkeypatch.setattr(campaign_main, "store", type("Store", (), {
        "create_campaign": lambda *_: campaign(),
        "get_campaign": lambda self, _campaign_id: campaign(),
    })())
    assert client.post("/api/v1/campaigns", json=no_ads, headers={"X-Internal-Api-Key": "test-key"}).status_code == 200


def test_reference_priority_and_measurable_75_25_context():
    priority_snapshot = assemble_generation_context(
        campaign(),
        [source("immediate_upload", "upload-1", "upload")],
        [source("industry_matched", "industry-1", "industry")],
        [source("external_web", "https://source.test", "external", url="https://source.test", provider="mock")],
        100,
    )
    assert [item.source_type for item in priority_snapshot.items] == ["immediate_upload", "industry_matched", "external_web"]

    snapshot = assemble_generation_context(
        campaign(),
        [source("immediate_upload", "upload-1", "U" * 3000)],
        [source("industry_matched", "industry-1", "I" * 1000)],
        [source("external_web", "https://source.test", "E" * 1000, url="https://source.test", provider="mock")],
        1000,
    )
    assert snapshot.internal_token_count <= 750
    assert snapshot.external_token_count <= 250
    assert snapshot.internal_ratio == pytest.approx(0.75, abs=0.02)
    assert snapshot.external_ratio == pytest.approx(0.25, abs=0.02)


def test_google_disabled_failure_and_redaction_are_deterministic():
    assert build_search_provider({"EXTERNAL_SEARCH_PROVIDER": "disabled"}) is None

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    provider = GoogleCustomSearchProvider(
        "google-secret", "engine", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ExternalSearchError) as failure:
        provider.search("New drink Restaurant awareness", 3)
    assert failure.value.category == "timeout"
    assert "google-secret" not in str(failure.value)

    class FailingProvider:
        def search(self, *_args):
            raise RuntimeError("authorization=google-secret")

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(campaign_main, "external_search_provider", FailingProvider())
        snapshot = campaign_main.create_generation_context(campaign(), "run-search-failure")
    finally:
        monkeypatch.undo()
    assert snapshot.external_search_status == "provider_error"
    assert snapshot.external_source_urls == ()
    assert "google-secret" not in (snapshot.external_search_error or "")


def test_context_persists_and_rehydrates_after_cache_restart(monkeypatch: pytest.MonkeyPatch):
    stored = assemble_generation_context(campaign(), [source("campaign_reference", "ref-1", "persisted")], [], [], 100)

    class Persistence:
        def load_generation_context(self, campaign_id: str, run_id: str):
            assert (campaign_id, run_id) == ("camp-e2e", "run-restart")
            return stored

        def list_campaign_runs(self, _campaign_id: str):
            return [{"run_id": "run-restart"}]

    monkeypatch.setattr(campaign_main, "persistence", Persistence())
    campaign_main.generation_context_cache.clear()
    campaign_main.generation_context_run_cache.clear()
    restored = campaign_main.snapshot_for_campaign(campaign(), "run-restart")
    assert restored is stored
    assert campaign_main.snapshot_for_campaign(campaign()) is stored


def test_worker_failure_isolates_descendants_and_unrelated_tasks_continue():
    tasks = [
        TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="image", task_type="image_generation", status="running", priority=1, acceptance=[]),
        TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="video", task_type="video_generation", status="pending", priority=1, depends_on=["image"], acceptance=[]),
        TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="copy", task_type="copywriting", status="passed", priority=1, acceptance=[]),
    ]
    state = {task.task_id: task for task in campaign_main.apply_worker_result_state(tasks, "image", {"status": "failed", "error": "quota depleted"})}
    assert state["image"].status == "failed"
    assert state["video"].status == "blocked"
    assert state["video"].blocked_by_task_id == "image"
    assert state["copy"].status == "passed"


def test_retry_is_bounded_and_single_task_retry_reopens_only_branch():
    orchestrator = load_orchestrator()
    assert orchestrator.next_retry_delay(1) == 5.0
    assert orchestrator.next_retry_delay(20) == 300.0
    assert orchestrator.MAX_RETRY == 2
    tasks = [
        TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="image", task_type="image_generation", status="failed", priority=1, acceptance=[]),
        TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="video", task_type="video_generation", status="blocked", priority=1, depends_on=["image"], acceptance=[]),
        TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="copy", task_type="copywriting", status="passed", priority=1, acceptance=[]),
    ]
    retried = campaign_main.apply_worker_result_state(tasks, "image", {"status": "retrying"})
    by_id = {task.task_id: task for task in retried}
    assert by_id["image"].status == "retrying"
    assert by_id["video"].status == "pending"
    assert by_id["copy"].status == "passed"


def test_review_diagnostics_are_filtered_by_run_and_expose_contract():
    item = campaign()
    snapshot = assemble_generation_context(item, [source("campaign_reference", "ref-1", "private")], [], [], 100)
    campaign_main.generation_context_cache.clear()
    campaign_main.cache_generation_context(snapshot, "run-review")
    review = campaign_main.ReviewItem(
        review_id="review-1", campaign_id=item.campaign_id, asset_id="asset-1", score=0.9,
        status="review_pending", submitted_at="2026-09-01T00:00:00Z", run_id="run-review",
    )
    other = review.model_copy(update={"review_id": "review-2", "run_id": "run-other"})
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(campaign_main, "store", type("Store", (), {"get_campaign": lambda *_: item})())
        monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _req: True)
        monkeypatch.setattr(campaign_main, "build_review_items", lambda: [review, other])
        monkeypatch.setattr(campaign_main, "list_review_items_filtered", lambda **kwargs: [review] if kwargs.get("run_id") == "run-review" else [review, other])
        response = TestClient(campaign_main.app).get("/api/v1/review/items?run_id=run-review", headers={"X-Platform-Key": "test"})
    finally:
        monkeypatch.undo()
    assert response.status_code == 200
    assert [entry["run_id"] for entry in response.json()["items"]] == ["run-review"]


def test_empty_worker_result_cannot_pass_and_metadata_is_preserved():
    task = TaskRecord(company_id="company-e2e", campaign_id="camp-e2e", task_id="image", task_type="image_generation", status="running", priority=1, acceptance=[])
    failed = campaign_main.apply_worker_result_state([task], "image", {"status": "passed", "image_assets": [], "provider": "vertex", "model_name": "imagen-3"})[0]
    assert failed.status == "failed"
    assert failed.retryable is not False
    assert "no displayable assets" in (failed.error_detail or "")
    passed = campaign_main.apply_worker_result_state([task], "image", {"status": "passed", "image_assets": [{"url": "https://asset"}], "provider": "vertex", "model_name": "imagen-3"})[0]
    assert passed.status == "passed"
    assert passed.provider == "vertex"
    assert passed.model == "imagen-3"


def test_api_and_ui_contracts_expose_diagnostics_retry_and_safe_metadata():
    spec = campaign_main.app.openapi()
    assert "/api/v1/review/items" in spec["paths"]
    assert "/api/v1/campaigns/{campaign_id}/run" in spec["paths"]
    campaign_page = (ROOT / "app" / "campaigns" / "page.tsx").read_text(encoding="utf-8")
    review_page = (ROOT / "app" / "review" / "page.tsx").read_text(encoding="utf-8")
    assert "generation_context_id" in campaign_page
    assert "internal_ratio" in review_page
    assert "retry" in campaign_page.lower()
    assert "provider" in review_page and "model" in review_page
