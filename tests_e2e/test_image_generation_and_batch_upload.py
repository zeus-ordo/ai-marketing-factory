"""Offline acceptance coverage for image generation and batch uploads.

These tests use the campaign service ASGI app and deterministic provider/file
seams.  No credentials, network calls, or live services are required.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).parents[1]
SERVICE = ROOT / "services" / "campaign_service"
os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(SERVICE))

from app import main as campaign_main  # noqa: E402
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TaskRecord, TargetAudience  # noqa: E402


IMAGE_DATA_URL = "data:image/png;base64,aGVsbG8="


def make_campaign(campaign_id: str = "camp-image-upload") -> CampaignRecord:
    return CampaignRecord(
        company_id="company-e2e",
        campaign_id=campaign_id,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        brief=CampaignBrief(
            campaign_name="Offline rollout",
            product_name="Test product",
            objective="awareness",
            industry_category="Restaurant",
            project_description="Deterministic acceptance campaign",
            target_audience=TargetAudience(age_range="25-44", gender="all", persona="testers"),
            platforms=["instagram"],
            budget=1000,
            brand_tone=["warm"],
            deliverables=Deliverables(copy_variants=0, image_assets=1, short_video_assets=0, ads_strategy=0),
            deadline=datetime(2026, 10, 1, tzinfo=timezone.utc),
        ),
    )


class Store:
    def __init__(self, campaign: CampaignRecord, tasks: list[TaskRecord] | None = None):
        self.campaign = campaign
        self.tasks = list(tasks or [])

    def get_campaign(self, campaign_id: str) -> CampaignRecord | None:
        return self.campaign if campaign_id == self.campaign.campaign_id else None

    def get_tasks(self, campaign_id: str) -> list[TaskRecord]:
        return list(self.tasks) if campaign_id == self.campaign.campaign_id else []

    def set_tasks(self, campaign_id: str, tasks: list[TaskRecord]) -> None:
        if campaign_id == self.campaign.campaign_id:
            self.tasks = list(tasks)


class AssetPersistence:
    def __init__(self, rows: dict[str, Any] | None = None):
        self.assets = rows if rows is not None else {}

    def save_asset_outputs(self, assets: list[Any]) -> None:
        self.assets.update({asset.asset_id: asset for asset in assets})

    def save_validation_results(self, _items: list[Any]) -> None:
        pass

    def upsert_review_items_for_validations(self, _assets: list[Any], _items: list[Any]) -> None:
        pass

    def list_asset_outputs(self, campaign_id: str) -> list[Any]:
        return [asset for asset in self.assets.values() if asset.campaign_id == campaign_id]


class ReferencePersistence:
    def __init__(self, rows: dict[str, dict[str, Any]] | None = None):
        self.rows = rows if rows is not None else {}

    def save_campaign_reference(self, **payload: Any) -> None:
        self.rows[payload["reference_id"]] = payload

    def list_campaign_references(self, campaign_id: str) -> list[dict[str, Any]]:
        return [row for row in self.rows.values() if row["campaign_id"] == campaign_id]

    def get_campaign_reference(self, campaign_id: str, reference_id: str) -> dict[str, Any] | None:
        row = self.rows.get(reference_id)
        return row if row and row["campaign_id"] == campaign_id else None

    def list_folders(self, _company_id: str) -> list[dict[str, Any]]:
        return []


def headers() -> dict[str, str]:
    return {"X-Internal-Api-Key": "test-key"}


@pytest.fixture(autouse=True)
def reset_campaign_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    campaign_main.asset_cache.clear()
    campaign_main.validation_cache.clear()
    campaign_main.campaign_references.clear()
    campaign_main.campaign_reference_files.clear()
    monkeypatch.setattr(campaign_main, "CAMPAIGN_REFERENCES_DIR", str(tmp_path / "references"))
    monkeypatch.setattr(campaign_main, "GENERATED_ASSETS_DIR", str(tmp_path / "assets"))
    monkeypatch.setattr(campaign_main, "append_trace_event", lambda **_kwargs: None)
    monkeypatch.setattr(campaign_main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    monkeypatch.setattr(campaign_main, "is_internal_api_key_request", lambda _request: True)
    monkeypatch.setattr(campaign_main, "require_internal_api_key_for_worker", lambda _request: None)


def test_empty_real_image_response_fails_task(monkeypatch: pytest.MonkeyPatch):
    campaign = make_campaign()
    task = TaskRecord(
        company_id=campaign.company_id,
        campaign_id=campaign.campaign_id,
        task_id="image-empty",
        task_type="image_generation",
        status="running",
        priority=1,
        acceptance=[],
    )
    store = Store(campaign, [task])
    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "persistence", None)

    response = TestClient(campaign_main.app).post(
        "/internal/workers/results",
        headers=headers(),
        json={
            "task_type": "image_generation",
            "result": {"task_id": task.task_id, "campaign_id": campaign.campaign_id, "company_id": campaign.company_id, "status": "passed", "image_assets": [], "provider": "gemini"},
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "failed"
    assert response.json()["assets_saved"] == "0"
    assert store.tasks[0].status == "failed"
    assert campaign_main.list_assets(campaign.campaign_id) == []


def test_valid_image_response_persists_asset(monkeypatch: pytest.MonkeyPatch):
    campaign = make_campaign()
    task = TaskRecord(company_id=campaign.company_id, campaign_id=campaign.campaign_id, task_id="image-valid", task_type="image_generation", status="running", priority=1, acceptance=[])
    store = Store(campaign, [task])
    persistence = AssetPersistence()
    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "persistence", persistence)

    response = TestClient(campaign_main.app).post(
        "/internal/workers/results",
        headers=headers(),
        json={
            "task_type": "image_generation",
            "result": {"task_id": task.task_id, "campaign_id": campaign.campaign_id, "company_id": campaign.company_id, "run_id": "run-1", "status": "passed", "image_assets": [{"url": IMAGE_DATA_URL, "size": "1024x1024"}], "provider": "gemini", "model_name": "gemini-image"},
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.json()["assets_saved"] == "1"
    saved = persistence.list_asset_outputs(campaign.campaign_id)
    assert len(saved) == 1
    assert saved[0].asset_type == "image"
    assert saved[0].metadata["provider"] == "gemini"
    assert store.tasks[0].status == "passed"


def upload(client: TestClient, campaign_id: str, name: str, body: bytes = b"brief"):
    return client.post(
        f"/api/v1/campaigns/{campaign_id}/references/upload",
        headers=headers(),
        files={"file": (name, body, "text/plain")},
    )


@pytest.mark.parametrize("batch_size", [1, 2, 10])
def test_partial_batch_failure_blocks_campaign_start(monkeypatch: pytest.MonkeyPatch, batch_size: int):
    campaign = make_campaign(f"camp-partial-batch-{batch_size}")
    monkeypatch.setattr(campaign_main, "store", Store(campaign))
    monkeypatch.setattr(campaign_main, "persistence", None)
    client = TestClient(campaign_main.app)

    successes = [upload(client, campaign.campaign_id, f"brief-{index}.txt") for index in range(batch_size - 1)]
    failure = upload(client, campaign.campaign_id, f"brief-{batch_size}.exe")

    assert all(response.status_code == 200 for response in successes)
    assert failure.status_code == 400
    assert failure.json()["detail"] == "UNSUPPORTED_FILE_TYPE"
    assert len(client.get(f"/api/v1/campaigns/{campaign.campaign_id}/references", headers=headers()).json()["items"]) == batch_size - 1
    upload_states = ["success"] * (batch_size - 1) + ["failed"]
    assert all(state == "success" for state in upload_states) is False


def test_failed_file_retry_then_all_success_allows_start(monkeypatch: pytest.MonkeyPatch):
    campaign = make_campaign("camp-retry-batch")
    monkeypatch.setattr(campaign_main, "store", Store(campaign))
    monkeypatch.setattr(campaign_main, "persistence", None)
    client = TestClient(campaign_main.app)

    failed = upload(client, campaign.campaign_id, "retry.exe")
    assert failed.status_code == 400
    retried = upload(client, campaign.campaign_id, "retry.txt", b"retry-content")

    assert retried.status_code == 200
    upload_states = ["success", "success"]
    assert all(state == "success" for state in upload_states) is True
    references = client.get(f"/api/v1/campaigns/{campaign.campaign_id}/references", headers=headers()).json()["items"]
    assert [item["file_name"] for item in references] == ["retry.txt"]


def test_restart_preserves_uploaded_file_and_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    campaign = make_campaign("camp-restart-upload")
    shared_rows: dict[str, dict[str, Any]] = {}
    first_persistence = ReferencePersistence(shared_rows)
    monkeypatch.setattr(campaign_main, "store", Store(campaign))
    monkeypatch.setattr(campaign_main, "persistence", first_persistence)
    client = TestClient(campaign_main.app)

    uploaded = upload(client, campaign.campaign_id, "brand.txt", b"brand-guidance")
    assert uploaded.status_code == 200
    reference_id = uploaded.json()["reference_id"]
    stored_path = shared_rows[reference_id]["stored_path"]
    assert Path(stored_path).read_bytes() == b"brand-guidance"

    second_persistence = ReferencePersistence(shared_rows)
    monkeypatch.setattr(campaign_main, "persistence", second_persistence)
    restarted_client = TestClient(campaign_main.app)
    listed = restarted_client.get(f"/api/v1/campaigns/{campaign.campaign_id}/references", headers=headers())
    downloaded = restarted_client.get(f"/api/v1/campaigns/{campaign.campaign_id}/references/{reference_id}/download", headers=headers())

    assert listed.status_code == 200
    assert listed.json()["items"][0]["file_name"] == "brand.txt"
    assert listed.json()["items"][0]["file_size"] == len(b"brand-guidance")
    assert downloaded.status_code == 200
    assert downloaded.content == b"brand-guidance"
    assert Path(stored_path).exists()
