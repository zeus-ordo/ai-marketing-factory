import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.context_assembler import ContextSourceItem, GenerationContextSnapshot
from app.main import ReviewItem, RetryWorkerTaskRequest
from app.schemas import CampaignBrief, CampaignRecord, TaskRecord


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
