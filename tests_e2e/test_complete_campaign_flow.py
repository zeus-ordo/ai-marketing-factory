"""Offline route-level acceptance coverage for the complete campaign flow.

The app is exercised through FastAPI's ASGI TestClient. External search,
decision/orchestrator dispatch, workers, and persistence are deterministic
fixtures; no collection-time or test-time localhost probes are used.
"""

from __future__ import annotations

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
os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(CAMPAIGN_SERVICE))

from app import main as campaign_main  # noqa: E402
from app.context_assembler import ContextSourceItem, assemble_generation_context  # noqa: E402
from app.external_search import ExternalSearchError, ExternalSearchResult, GoogleCustomSearchProvider, build_search_provider  # noqa: E402
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TaskRecord, TargetAudience  # noqa: E402


def campaign(campaign_id: str = "camp-offline") -> CampaignRecord:
    return CampaignRecord(
        company_id="company-offline",
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


def brief_payload(**updates: Any) -> dict[str, Any]:
    payload = campaign().brief.model_dump(mode="json")
    payload.update(updates)
    return payload


def source(source_type: str, source_id: str, text: str, **metadata: Any) -> ContextSourceItem:
    return ContextSourceItem(source_type, source_id, source_id, text, metadata)


class FlowStore:
    def __init__(self, item: CampaignRecord | None = None, tasks: list[TaskRecord] | None = None):
        self.campaigns = {item.campaign_id: item} if item else {}
        self.tasks = {item.campaign_id: list(tasks or [])} if item else {}
        self.created = []

    def create_campaign(self, company_id: str, brief: CampaignBrief) -> CampaignRecord:
        item = CampaignRecord(company_id=company_id, campaign_id="camp-created", created_at=datetime.now(timezone.utc), brief=brief)
        self.campaigns[item.campaign_id] = item
        self.tasks[item.campaign_id] = []
        self.created.append(item)
        return item

    def get_campaign(self, campaign_id: str) -> CampaignRecord | None:
        return self.campaigns.get(campaign_id)

    def get_tasks(self, campaign_id: str) -> list[TaskRecord]:
        return list(self.tasks.get(campaign_id, []))

    def set_tasks(self, campaign_id: str, tasks: list[TaskRecord]) -> None:
        self.tasks[campaign_id] = list(tasks)

    def update_campaign_brief(self, campaign_id: str, brief: CampaignBrief) -> CampaignRecord:
        item = self.campaigns[campaign_id].model_copy(update={"brief": brief})
        self.campaigns[campaign_id] = item
        return item

    def create_task_plan(self, company_id: str, campaign_id: str) -> list[TaskRecord]:
        return []


class FlowPersistence:
    def __init__(self):
        self.snapshots = {}
        self.attempts = []

    def save_generation_context(self, snapshot, run_id):
        self.snapshots[(snapshot.campaign_id, run_id)] = snapshot

    def load_generation_context(self, campaign_id, run_id):
        return self.snapshots.get((campaign_id, run_id))

    def list_campaign_runs(self, campaign_id):
        return [{"run_id": run_id} for (saved_campaign, run_id) in self.snapshots if saved_campaign == campaign_id]


def internal_headers() -> dict[str, str]:
    return {"X-Internal-Api-Key": "test-key"}


def test_create_route_rejects_required_and_conditional_invalid_briefs_without_persistence(monkeypatch: pytest.MonkeyPatch):
    store = FlowStore()
    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    client = TestClient(campaign_main.app)

    for field in ("campaign_name", "product_name", "objective", "industry_category", "project_description"):
        payload = brief_payload()
        payload.pop(field)
        response = client.post("/api/v1/campaigns", json=payload, headers=internal_headers())
        assert response.status_code == 422, (field, response.text)
        assert field in response.text

    response = client.post(
        "/api/v1/campaigns",
        json=brief_payload(budget=0, deliverables={"ads_strategy": 1}),
        headers=internal_headers(),
    )
    assert response.status_code == 422
    assert "budget" in response.text
    assert store.created == []


def test_create_route_persists_zero_budget_campaign_when_ads_are_not_selected(monkeypatch: pytest.MonkeyPatch):
    store = FlowStore()
    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    monkeypatch.setattr(campaign_main, "append_trace_event", lambda **_kwargs: None)
    response = TestClient(campaign_main.app).post(
        "/api/v1/campaigns", json=brief_payload(budget=0, deliverables={"ads_strategy": 0}), headers=internal_headers()
    )
    assert response.status_code == 200
    assert store.created[0].brief.budget == 0


def test_run_route_stores_mock_google_context_and_propagates_snapshot_to_dispatch(monkeypatch: pytest.MonkeyPatch):
    item = campaign()
    store = FlowStore(item)
    persistence = FlowPersistence()
    captured: dict[str, Any] = {}
    google_result = ExternalSearchResult(
        source_type="external_web", title="Mock market facts", url="https://mock.test/facts",
        summary="Useful facts", retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        query="New drink Restaurant awareness", provider="google",
    )

    def google_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "test-google-key"
        assert request.url.params["cx"] == "test-engine"
        assert request.url.params["q"] == "New drink Restaurant awareness"
        return httpx.Response(200, json={"items": [{
            "title": google_result.title, "link": google_result.url, "snippet": google_result.summary,
        }]})

    def dispatch(url: str, payload: dict[str, Any]):
        captured[url] = payload
        if "decision" in url:
            return {"tasks": [{"task_id": "copy-1", "task_type": "copywriting", "status": "planned", "priority": 1, "acceptance": []}]}
        return {"tasks": payload["tasks"]}

    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "persistence", persistence)
    monkeypatch.setattr(campaign_main, "is_internal_api_key_request", lambda _req: True)
    monkeypatch.setattr(campaign_main, "external_search_provider", GoogleCustomSearchProvider(
        "test-google-key", "test-engine", client=httpx.Client(transport=httpx.MockTransport(google_handler))
    ))
    monkeypatch.setattr(campaign_main, "post_json", dispatch)
    monkeypatch.setattr(campaign_main, "list_campaign_reference_context", lambda *_args: [{
        "reference_id": "upload-1", "source_type": "immediate_upload", "file_name": "brand.txt", "stored_path": "", "file_type": "text/plain", "folder": "Brand"
    }])
    monkeypatch.setattr(campaign_main, "list_industry_knowledge_context", lambda *_args: [{
        "item_id": "industry-1", "source_type": "industry_matched", "title": "Restaurant guide", "description": "Industry facts", "metadata": {}, "folder": "Restaurant"
    }])
    monkeypatch.setattr(campaign_main, "safe_reference_excerpt", lambda *_args: "Upload guidance")
    monkeypatch.setattr(campaign_main, "finalize_campaign_workflow", lambda *_args, **_kwargs: item)
    monkeypatch.setattr(campaign_main, "append_trace_event", lambda **_kwargs: None)

    response = TestClient(campaign_main.app).post(f"/api/v1/campaigns/{item.campaign_id}/run", headers=internal_headers())
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    snapshot = persistence.snapshots[(item.campaign_id, run_id)]
    assert snapshot.external_search_status == "succeeded"
    assert snapshot.external_source_urls == ("https://mock.test/facts",)
    assert snapshot.internal_token_count <= 3000
    assert snapshot.external_token_count <= 1000
    assert snapshot.internal_ratio == pytest.approx(0.75, abs=0.03)
    assert snapshot.external_ratio == pytest.approx(0.25, abs=0.03)
    task = captured[next(url for url in captured if "orchestrator" in url)]["tasks"][0]
    assert task["generation_context_id"] == snapshot.generation_context_id
    assert task["worker_payload"]["generation_context_id"] == snapshot.generation_context_id
    assert any(source_item["source_type"] == "external_web" for source_item in task["worker_payload"]["context_sources"])


def test_run_route_records_provider_failure_and_continues_internal_only(monkeypatch: pytest.MonkeyPatch):
    item = campaign("camp-search-failure")
    store = FlowStore(item)
    persistence = FlowPersistence()

    class Provider:
        def search(self, *_args):
            raise ExternalSearchError("quota", "External search quota exceeded")

    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "persistence", persistence)
    monkeypatch.setattr(campaign_main, "is_internal_api_key_request", lambda _req: True)
    monkeypatch.setattr(campaign_main, "external_search_provider", Provider())
    monkeypatch.setattr(campaign_main, "post_json", lambda url, payload: {"tasks": payload.get("tasks", [])} if "orchestrator" in url else {"tasks": []})
    monkeypatch.setattr(campaign_main, "finalize_campaign_workflow", lambda *_args, **_kwargs: item)
    monkeypatch.setattr(campaign_main, "append_trace_event", lambda **_kwargs: None)
    response = TestClient(campaign_main.app).post(f"/api/v1/campaigns/{item.campaign_id}/run", headers=internal_headers())
    assert response.status_code == 200
    snapshot = next(iter(persistence.snapshots.values()))
    assert snapshot.external_search_status == "quota"
    assert snapshot.external_source_urls == ()


def test_campaign_get_route_hydrates_persisted_context_after_cache_restart(monkeypatch: pytest.MonkeyPatch):
    item = campaign("camp-restart-route")
    snapshot = assemble_generation_context(item, [source("campaign_reference", "ref-1", "persisted")], [], [], 100)
    persistence = FlowPersistence()
    persistence.save_generation_context(snapshot, "run-restart")
    campaign_main.generation_context_cache.clear()
    campaign_main.generation_context_run_cache.clear()
    monkeypatch.setattr(campaign_main, "store", FlowStore(item))
    monkeypatch.setattr(campaign_main, "persistence", persistence)
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _req: True)
    response = TestClient(campaign_main.app).get(f"/api/v1/campaigns/{item.campaign_id}", headers={"X-Platform-Key": "offline"})
    assert response.status_code == 200
    body = response.json()
    assert body["generation_context_id"] == snapshot.generation_context_id
    assert body["source_summary"]["internal_source_count"] == 1
    assert body["source_summary"]["provenance"][0]["source_id"] == "ref-1"


def test_worker_result_route_persists_success_state_and_rejects_empty_result(monkeypatch: pytest.MonkeyPatch):
    item = campaign("camp-worker")
    task = TaskRecord(company_id=item.company_id, campaign_id=item.campaign_id, task_id="image-1", task_type="image_generation", status="running", priority=1, acceptance=[])
    dependent = TaskRecord(company_id=item.company_id, campaign_id=item.campaign_id, task_id="video-1", task_type="video_generation", status="pending", priority=1, depends_on=["image-1"], acceptance=[])
    unrelated = TaskRecord(company_id=item.company_id, campaign_id=item.campaign_id, task_id="copy-1", task_type="copywriting", status="pending", priority=1, acceptance=[])
    store = FlowStore(item, [task, dependent, unrelated])
    saved_assets = []
    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    monkeypatch.setattr(campaign_main, "require_internal_api_key_for_worker", lambda _req: None)
    monkeypatch.setattr(campaign_main, "save_assets_and_validations", lambda assets, _validations: saved_assets.extend(assets))
    client = TestClient(campaign_main.app)

    response = client.post("/internal/workers/results", headers=internal_headers(), json={
        "task_type": "image_generation", "result": {"task_id": "image-1", "campaign_id": item.campaign_id, "company_id": item.company_id, "run_id": "run-1", "status": "passed", "image_assets": [{"url": "https://asset.test/image.png"}], "provider": "vertex", "model_name": "imagen-3"}
    })
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert saved_assets[0].metadata["provider"] == "vertex"
    assert saved_assets[0].metadata["model_name"] == "imagen-3"
    assert store.get_tasks(item.campaign_id)[0].status == "passed"

    empty = client.post("/internal/workers/results", headers=internal_headers(), json={
        "task_type": "image_generation", "result": {"task_id": "image-1", "campaign_id": item.campaign_id, "company_id": item.company_id, "run_id": "run-1", "status": "passed", "image_assets": []}
    })
    assert empty.status_code == 202
    assert empty.json()["status"] == "failed"
    result_tasks = {task.task_id: task for task in store.get_tasks(item.campaign_id)}
    assert result_tasks["video-1"].status == "blocked"
    assert result_tasks["video-1"].blocked_by_task_id == "image-1"
    assert result_tasks["copy-1"].status == "pending"


def test_retry_route_dispatches_one_failed_task_and_preserves_run_context(monkeypatch: pytest.MonkeyPatch):
    item = campaign("camp-retry-route")
    task = TaskRecord(company_id=item.company_id, campaign_id=item.campaign_id, task_id="image-1", task_type="image_generation", status="failed", priority=1, retry_count=0, retryable=True, run_id="run-1", generation_context_id="gctx-1", acceptance=[])
    store = FlowStore(item, [task])
    dispatched = []
    asset = campaign_main.AssetOutput(company_id=item.company_id, asset_id="asset-1", campaign_id=item.campaign_id, task_id=task.task_id, asset_type="image", url="https://asset.test/retry.png", created_at=datetime.now(timezone.utc), run_id="run-1", metadata={"provider": "vertex", "model_name": "imagen-3"})
    monkeypatch.setattr(campaign_main, "store", store)
    monkeypatch.setattr(campaign_main, "persistence", None)
    monkeypatch.setattr(campaign_main, "require_review_action_access", lambda _req: None)
    monkeypatch.setattr(campaign_main, "require_campaign_access", lambda _req, _campaign: None)
    monkeypatch.setattr(campaign_main, "_dispatch_worker_for_task", lambda _campaign, retried: dispatched.append(retried) or ([asset], []))
    monkeypatch.setattr(campaign_main, "save_assets_and_validations", lambda *_args: None)
    monkeypatch.setattr(campaign_main, "dispatch_ready_retry_descendants", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(campaign_main, "append_trace_event", lambda **_kwargs: None)
    monkeypatch.setattr(campaign_main, "_notify_webhook", lambda **_kwargs: None)

    response = TestClient(campaign_main.app).post(f"/api/v1/internal/campaigns/{item.campaign_id}/tasks/retry", headers=internal_headers(), json={"task_id": task.task_id})
    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    assert len(dispatched) == 1
    assert dispatched[0].run_id == "run-1"
    assert store.get_tasks(item.campaign_id)[0].status == "passed"


def test_review_route_serializes_only_requested_run_diagnostics(monkeypatch: pytest.MonkeyPatch):
    item = campaign("camp-review-route")
    snapshot = assemble_generation_context(item, [source("campaign_reference", "ref-1", "private")], [], [], 100)
    campaign_main.generation_context_cache.clear()
    campaign_main.cache_generation_context(snapshot, "run-review")
    review = campaign_main.ReviewItem(review_id="review-1", campaign_id=item.campaign_id, asset_id="asset-1", score=0.9, status="review_pending", submitted_at="2026-09-01T00:00:00Z", run_id="run-review")
    other = review.model_copy(update={"review_id": "review-2", "run_id": "run-other"})
    monkeypatch.setattr(campaign_main, "store", FlowStore(item))
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(campaign_main, "build_review_items", lambda: [review, other])
    response = TestClient(campaign_main.app).get("/api/v1/review/items?run_id=run-review", headers={"X-Platform-Key": "test"})
    assert response.status_code == 200
    assert [entry["run_id"] for entry in response.json()["items"]] == ["run-review"]


def test_google_adapter_mock_success_and_failure_redact_secrets():
    def success(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "key"
        return httpx.Response(200, json={"items": [{"title": "Facts", "link": "https://mock.test", "snippet": "Summary"}]})

    provider = GoogleCustomSearchProvider("key", "engine", client=httpx.Client(transport=httpx.MockTransport(success)))
    result = provider.search("query", 1)[0]
    assert result.source_type == "external_web"
    assert result.provider == "google"

    def failure(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    with pytest.raises(ExternalSearchError) as exc:
        GoogleCustomSearchProvider("secret-key", "engine", client=httpx.Client(transport=httpx.MockTransport(failure))).search("query", 1)
    assert exc.value.category == "quota"
    assert "secret-key" not in str(exc.value)
    assert build_search_provider({"EXTERNAL_SEARCH_PROVIDER": "disabled"}) is None
    with pytest.raises(ExternalSearchError, match="not configured"):
        build_search_provider({"EXTERNAL_SEARCH_PROVIDER": "google", "EXTERNAL_SEARCH_API_KEY": "key"})


def test_retry_limit_is_explicitly_bounded_for_campaign_worker_dispatch():
    assert campaign_main.WORKER_RETRY_MAX_ATTEMPTS == 2


def test_ui_and_openapi_contracts_are_additive_and_route_backed():
    spec = campaign_main.app.openapi()
    assert "/api/v1/campaigns/{campaign_id}/run" in spec["paths"]
    assert "/api/v1/internal/campaigns/{campaign_id}/tasks/retry" in spec["paths"]
    assert "/internal/workers/results" in spec["paths"]
