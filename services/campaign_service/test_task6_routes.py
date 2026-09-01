import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import threading
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.context_assembler import ContextSourceItem, GenerationContextSnapshot
from app.main import ReviewItem, RetryWorkerTaskRequest
from app.schemas import AssetOutput, CampaignBrief, CampaignRecord, TaskRecord, ValidationResult
from services.worker_image.app.schemas import ImageRunRequest


def campaign(campaign_id="camp-route"):
    return CampaignRecord(
        company_id="co-1", campaign_id=campaign_id, created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Route campaign", product_name="Product", objective="awareness",
            industry_category="food", project_description="brief",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables={}, deadline=datetime.utcnow()),
    )


class Store:
    def __init__(self, item):
        self.item = item

    def get_campaign(self, campaign_id):
        return self.item if campaign_id == self.item.campaign_id else None

    def list_campaigns(self, company_id=None):
        return [self.item]

    def set_campaign_status(self, campaign_id, status):
        return self.item.model_copy(update={"status": status})

    def get_tasks(self, campaign_id):
        return [TaskRecord(company_id="co-1", campaign_id=campaign_id, task_id="task-1", task_type="image_generation", status="failed", priority=1, retry_count=1, acceptance=[])]

    def set_tasks(self, campaign_id, tasks):
        pass


def snapshot(campaign_id, run_id):
    return GenerationContextSnapshot("gctx-route", campaign_id, 3, 2, .6, .4,
        (ContextSourceItem("campaign_reference", "ref-1", "Guide", "content", {"folder": "Brand"}),), ())


def test_campaign_get_and_list_include_hydrated_diagnostics(monkeypatch):
    item = campaign()
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda req: True)
    main.generation_context_cache.clear()
    main.generation_context_cache["gctx-route"] = snapshot(item.campaign_id, "run-1")

    one = main.get_campaign(object(), item.campaign_id)
    many = main.list_campaigns(object())
    assert one.generation_context_id == "gctx-route"
    assert one.source_summary["internal_source_count"] == 1
    assert many.items[0].tasks[0].error_class is None


def test_review_route_serializes_diagnostics_for_item_run(monkeypatch):
    item = campaign()
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda req: True)
    review = ReviewItem(review_id="review-1", campaign_id=item.campaign_id, asset_id="asset-1", score=1, status="review_pending", submitted_at=datetime.utcnow().isoformat(), run_id="run-1")
    monkeypatch.setattr(main, "build_review_items", lambda: [review])
    monkeypatch.setattr(main, "snapshot_for_campaign", lambda campaign, run_id=None: snapshot(campaign.campaign_id, run_id) if run_id == "run-1" else None)

    result = main.list_review_queue(object())
    assert result.items[0].generation_context_id == "gctx-route"
    assert result.items[0].source_provenance[0]["source_type"] == "campaign_reference"


def test_retry_route_concurrent_requests_claim_one_attempt(monkeypatch):
    item = campaign("camp-retry")
    retry_task = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-retry", task_type="image_generation", status="failed", priority=1, acceptance=[])
    tasks = [retry_task]
    store = Store(item)
    store.get_tasks = lambda campaign_id: list(tasks)
    store.set_tasks = lambda campaign_id, updated: tasks.__setitem__(slice(None), updated)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "_dispatch_worker_for_task", lambda campaign, task: ([object()], []))
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: None)
    monkeypatch.setattr(main, "dispatch_ready_retry_descendants", lambda campaign, tasks, task_id, run_id=None: [])
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "_notify_webhook", lambda **kwargs: None)

    def call():
        try:
            return main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id=retry_task.task_id), object())
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: call(), range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(getattr(result, "status_code", None) == 409 for result in results) == 1


def test_retry_descendant_dispatch_is_limited_to_review_run(monkeypatch):
    item = campaign("camp-mixed")
    selected = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="image-old", task_type="image_generation", status="passed", priority=1, run_id="run-old", acceptance=[])
    same_run = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="video-old", task_type="video_generation", status="pending", priority=2, run_id="run-old", depends_on=["image-old"], acceptance=[])
    other_run = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="video-new", task_type="video_generation", status="pending", priority=2, run_id="run-new", depends_on=["image-old"], acceptance=[])
    captured = {}
    monkeypatch.setattr(main, "snapshot_for_campaign", lambda campaign, run_id=None: snapshot(campaign.campaign_id, run_id) if run_id == "run-old" else None)
    monkeypatch.setattr(main, "post_json", lambda url, payload: captured.update(payload) or {"tasks": payload["tasks"]})

    dispatched = main.dispatch_ready_retry_descendants(item, [selected, same_run, other_run], "image-old", "run-old")
    assert [task["task_id"] for task in captured["tasks"]] == ["video-old"]
    assert [task.task_id for task in dispatched] == ["video-old"]


def test_in_memory_review_fallback_retains_asset_task_run_id(monkeypatch):
    item = campaign("camp-fallback-runs")
    asset = AssetOutput(company_id="co-1", asset_id="asset-old", campaign_id=item.campaign_id, task_id="task-old", asset_type="image", url="https://asset", created_at=datetime.utcnow(), run_id="run-old")
    validation = ValidationResult(company_id="co-1", validation_id="validation-old", campaign_id=item.campaign_id, asset_id=asset.asset_id, validator="visual", score=0.9, result="passed", created_at=datetime.utcnow(), run_id="run-old")
    store = Store(item)
    store.get_tasks = lambda _campaign_id: [TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-old", task_type="image_generation", status="passed", priority=1, run_id="run-old", acceptance=[])]
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "list_assets", lambda _campaign_id: [asset])
    monkeypatch.setattr(main, "list_validation", lambda _campaign_id: [validation])
    result = main.build_review_items()
    assert result[0].run_id == "run-old"


def test_fastapi_http_campaign_review_and_validation_routes(monkeypatch):
    item = campaign("camp-http")
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda req: True)
    main.generation_context_cache["gctx-route"] = snapshot(item.campaign_id, "run-http")
    review = ReviewItem(review_id="review-http", campaign_id=item.campaign_id, asset_id="asset-http", score=1, status="review_pending", submitted_at=datetime.utcnow().isoformat(), run_id="run-http")
    monkeypatch.setattr(main, "build_review_items", lambda: [review])
    client = TestClient(main.app)

    assert client.get(f"/api/v1/campaigns/{item.campaign_id}").json()["generation_context_id"] == "gctx-route"
    assert client.get("/api/v1/campaigns").json()["items"][0]["source_summary"]["internal_source_count"] == 1
    assert client.get("/api/v1/review/items?run_id=run-http").json()["items"][0]["run_id"] == "run-http"
    validation = client.post("/api/v1/campaigns", json={})
    assert validation.status_code == 422
    assert isinstance(validation.json()["detail"], list)


def test_campaign_hydration_loads_persisted_snapshot_after_cold_cache(monkeypatch):
    item = campaign("camp-cold")
    class Persistence:
        def list_campaign_runs(self, _campaign_id): return [{"run_id": "run-cold"}]
        def load_generation_context(self, _campaign_id, run_id): return snapshot(item.campaign_id, run_id)
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    main.generation_context_cache.clear()
    monkeypatch.setattr(main, "is_platform_admin_request", lambda req: True)
    result = main.get_campaign(object(), item.campaign_id)
    assert result.generation_context_id == "gctx-route"


@pytest.mark.parametrize("task_type,result", [
    ("copywriting", {"task_id": "task-1", "campaign_id": "camp-empty", "company_id": "co-1", "variants": []}),
    ("image_generation", {"task_id": "task-1", "campaign_id": "camp-empty", "company_id": "co-1", "image_assets": []}),
    ("video_generation", {"task_id": "task-1", "campaign_id": "camp-empty", "company_id": "co-1", "video_url": ""}),
    ("ads_strategy", {"task_id": "task-1", "campaign_id": "camp-empty", "company_id": "co-1", "ads_plan": {}}),
])
def test_http_worker_empty_result_is_failed_not_passed(monkeypatch, task_type, result):
    item = campaign("camp-empty")
    task_item = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-1", task_type=task_type, status="running", priority=1, acceptance=[])
    store = Store(item)
    store.get_tasks = lambda _campaign_id: [task_item]
    updated = []
    store.set_tasks = lambda _campaign_id, tasks: updated.extend(tasks)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    client = TestClient(main.app)
    response = client.post("/internal/workers/results", json={"task_type": task_type, "result": result}, headers={"X-Internal-Api-Key": "test-key"})
    assert response.status_code == 202
    assert response.json()["status"] == "failed"
    assert updated[0].status == "failed"
    assert updated[0].blocked_reason is None


def test_primary_worker_assets_preserve_provider_model_metadata(monkeypatch):
    captured = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: captured.extend(assets))
    now = datetime.utcnow()
    main._save_copy_worker_result({"task_id": "copy", "campaign_id": "camp", "company_id": "co", "variants": [{"body": "copy"}], "provider": "p", "model_name": "m"}, now)
    main._save_image_worker_result({"task_id": "image", "campaign_id": "camp", "company_id": "co", "image_assets": [{"url": "data:image/svg+xml,test", "size": "1:1"}], "provider": "p", "model_name": "m"}, now)
    main._save_ads_worker_result({"task_id": "ads", "campaign_id": "camp", "company_id": "co", "ads_plan": {"social": {}}, "provider": "p", "model_name": "m"}, now)
    assert len(captured) == 3
    assert all(asset.metadata["provider"] == "p" and asset.metadata["model_name"] == "m" for asset in captured)


def test_image_retry_payload_validates_company_and_authoritative_provider_model():
    payload = main.build_worker_payload_for_task(campaign("camp-image"), TaskRecord(
        company_id="co-1", campaign_id="camp-image", task_id="image-1", task_type="image_generation",
        status="retrying", priority=1, acceptance=[], run_id="run-1", provider="p", model="m",
    ))
    validated = ImageRunRequest.model_validate(payload)
    assert validated.company_id == "co-1"
    assert validated.provider == "p"
    assert validated.model == "m"


def test_retry_uses_authoritative_claimed_retry_count_and_run(monkeypatch):
    item = campaign("camp-authoritative")
    stale = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-retry", task_type="image_generation", status="failed", priority=1, retry_count=1, run_id="run-old", acceptance=[])
    authoritative = stale.model_copy(update={"retry_count": 2, "run_id": "run-new", "status": "retrying"})
    dispatched = []

    class Persistence:
        def claim_manual_task_retry(self, *_args):
            return authoritative

        def record_task_attempt(self, *_args):
            pass

    store = Store(item)
    store.get_tasks = lambda _campaign_id: [stale]
    store.set_tasks = lambda _campaign_id, tasks: None
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "_dispatch_worker_for_task", lambda _campaign, task: dispatched.append(task) or ([], []))
    monkeypatch.setattr(main, "dispatch_ready_retry_descendants", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "_notify_webhook", lambda **kwargs: None)

    main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id=stale.task_id), object())
    assert dispatched[0].retry_count == 2
    assert dispatched[0].run_id == "run-new"


def test_replica_style_retry_claim_cannot_lose_increment_or_exceed_cap():
    item = campaign("camp-atomic")
    lock = threading.Lock()
    state = {"retry_count": 1, "status": "failed"}

    class AtomicPersistence:
        def claim_manual_task_retry(self, _campaign_id, _task_id, max_attempts):
            with lock:
                if state["status"] != "failed" or state["retry_count"] >= max_attempts:
                    return None
                state["retry_count"] += 1
                state["status"] = "retrying"
                return TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-retry", task_type="image_generation", status="retrying", priority=1, retry_count=state["retry_count"], acceptance=[])

    persistence = AtomicPersistence()
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: persistence.claim_manual_task_retry(item.campaign_id, "task-retry", 3), range(2)))
    assert sum(result is not None for result in results) == 1
    assert state["retry_count"] == 2


def test_retry_rejects_invalid_review_and_asset_ids(monkeypatch):
    item = campaign("camp-validation")
    store = Store(item)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "find_review_item", lambda _review_id: None)

    with pytest.raises(main.HTTPException) as missing_review:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id="task-1", review_id="missing"), object())
    assert missing_review.value.status_code == 404

    with pytest.raises(main.HTTPException) as missing_asset:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id="task-1", asset_id="missing"), object())
    assert missing_asset.value.status_code == 404


def test_retry_rejects_review_asset_campaign_and_run_mismatch(monkeypatch):
    item = campaign("camp-validation")
    review = main.ReviewItem(review_id="review-1", campaign_id=item.campaign_id, asset_id="asset-1", score=1, status="review_pending", submitted_at=datetime.utcnow().isoformat(), run_id="run-old")
    asset = AssetOutput(company_id="co-1", asset_id="asset-1", campaign_id="other-campaign", task_id="task-1", asset_type="image", url="https://asset", created_at=datetime.utcnow(), run_id="run-old")
    store = Store(item)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "find_review_item", lambda _review_id: review)
    monkeypatch.setattr(main, "get_asset_output_by_id", lambda _asset_id: asset)

    with pytest.raises(main.HTTPException) as mismatch:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id="task-1", review_id=review.review_id), object())
    assert mismatch.value.status_code == 400

    asset = asset.model_copy(update={"campaign_id": item.campaign_id})
    monkeypatch.setattr(main, "get_asset_output_by_id", lambda _asset_id: asset)
    with pytest.raises(main.HTTPException) as run_mismatch:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id="task-1", review_id=review.review_id, run_id="run-new"), object())
    assert run_mismatch.value.status_code == 400


def test_retry_dispatch_failure_reconciles_terminal_state_when_store_save_fails(monkeypatch):
    item = campaign("camp-reconcile")
    task_item = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-retry", task_type="image_generation", status="failed", priority=1, retry_count=1, acceptance=[])
    reconciled = []

    class Persistence:
        def claim_manual_task_retry(self, *_args):
            return task_item.model_copy(update={"status": "retrying", "retry_count": 2})

        def record_task_attempt(self, *_args):
            pass

        def fail_manual_task_retry(self, *args, **kwargs):
            reconciled.append((args, kwargs))
            return True

        def release_manual_task_retry(self, *_args):
            pass

    class FailingStore(Store):
        def __init__(self, campaign):
            super().__init__(campaign)
            self.tasks = [task_item]

        def get_tasks(self, _campaign_id):
            return list(self.tasks)

        def set_tasks(self, _campaign_id, tasks):
            if any(task.status == "failed" for task in tasks):
                raise RuntimeError("database unavailable")
            self.tasks = list(tasks)

    monkeypatch.setattr(main, "store", FailingStore(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "_dispatch_worker_for_task", lambda *_args: (_ for _ in ()).throw(RuntimeError("worker unavailable")))
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "_notify_webhook", lambda **kwargs: None)

    with pytest.raises(main.HTTPException) as failure:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id=task_item.task_id), object())
    assert failure.value.status_code == 502
    assert reconciled


def test_retry_dispatch_failure_reconciles_from_authoritative_claim_when_store_read_fails(monkeypatch):
    item = campaign("camp-read-reconcile")
    task_item = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-retry", task_type="image_generation", status="failed", priority=1, retry_count=1, acceptance=[])
    reconciled = []

    class Persistence:
        def claim_manual_task_retry(self, *_args):
            return task_item.model_copy(update={"status": "retrying", "retry_count": 2})

        def record_task_attempt(self, *_args):
            pass

        def fail_manual_task_retry(self, *args, **kwargs):
            reconciled.append((args, kwargs))
            return True

    class StoreWithReadFailure(Store):
        def __init__(self, campaign):
            super().__init__(campaign)
            self.reads = 0
            self.writes = 0

        def get_tasks(self, campaign_id):
            self.reads += 1
            if self.reads > 1:
                raise RuntimeError("database unavailable")
            return [task_item]

        def set_tasks(self, _campaign_id, tasks):
            self.writes += 1
            if self.writes > 1:
                raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "store", StoreWithReadFailure(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "_dispatch_worker_for_task", lambda *_args: (_ for _ in ()).throw(RuntimeError("worker unavailable")))
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "_notify_webhook", lambda **kwargs: None)

    with pytest.raises(main.HTTPException) as failure:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id=task_item.task_id), object())
    assert failure.value.status_code == 502
    assert reconciled


def test_retry_rejects_run_scoped_asset_without_run_id(monkeypatch):
    item = campaign("camp-no-asset-run")
    review = main.ReviewItem(review_id="review-1", campaign_id=item.campaign_id, asset_id="asset-1", score=1, status="review_pending", submitted_at=datetime.utcnow().isoformat(), run_id="run-old")
    asset = AssetOutput(company_id="co-1", asset_id="asset-1", campaign_id=item.campaign_id, task_id="task-1", asset_type="image", url="https://asset", created_at=datetime.utcnow(), run_id=None)
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "find_review_item", lambda _review_id: review)
    monkeypatch.setattr(main, "get_asset_output_by_id", lambda _asset_id: asset)

    with pytest.raises(main.HTTPException) as failure:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id="task-1", review_id=review.review_id), object())
    assert failure.value.status_code == 400


def test_retry_reconciliation_zero_rows_returns_recovery_pending(monkeypatch):
    item = campaign("camp-zero-reconcile")
    task_item = TaskRecord(company_id="co-1", campaign_id=item.campaign_id, task_id="task-retry", task_type="image_generation", status="failed", priority=1, retry_count=1, acceptance=[])

    class Persistence:
        def claim_manual_task_retry(self, *_args):
            return task_item.model_copy(update={"status": "retrying", "retry_count": 2})

        def record_task_attempt(self, *_args):
            pass

        def fail_manual_task_retry(self, *_args, **_kwargs):
            return False

        def release_manual_task_retry(self, *_args):
            pass

    class FailingStore(Store):
        def get_tasks(self, _campaign_id):
            return [task_item]

        def set_tasks(self, _campaign_id, tasks):
            if any(task.status == "failed" for task in tasks):
                raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "store", FailingStore(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "require_review_action_access", lambda req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda req, campaign: None)
    monkeypatch.setattr(main, "_dispatch_worker_for_task", lambda *_args: (_ for _ in ()).throw(RuntimeError("worker unavailable")))

    with pytest.raises(main.HTTPException) as failure:
        main.retry_worker_task(item.campaign_id, RetryWorkerTaskRequest(task_id=task_item.task_id), object())
    assert failure.value.status_code == 503
