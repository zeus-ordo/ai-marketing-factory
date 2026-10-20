import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.schemas import AssetOutput, CampaignBrief, CampaignRecord, TaskRecord


def campaign(project_description: str) -> CampaignRecord:
    return CampaignRecord(
        company_id="company-1",
        campaign_id="campaign-1",
        created_at=datetime.utcnow(),
        brief=CampaignBrief(
            campaign_name="Campaign",
            product_name="Product",
            objective="awareness",
            industry_category="food",
            project_description=project_description,
            target_audience={"age_range": "all", "gender": "all", "persona": "all"},
            platforms=["social"],
            budget=100,
            brand_tone=[],
            deliverables={"copy_variants": 1, "image_assets": 0, "short_video_assets": 0},
            deadline=datetime.utcnow(),
        ),
    )


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("公關稿 for product launch", {"body_min_length": 300, "body_max_length": 500}),
        ("Write a 新聞稿", {"body_min_length": 300, "body_max_length": 500}),
        ("Create a press release", {"body_min_length": 300, "body_max_length": 500}),
        ("public relations announcement", {"body_min_length": 300, "body_max_length": 500}),
        ("社群貼文 for launch", {"body_min_length": 100, "body_max_length": 200}),
        ("promotional copy", {"body_min_length": 0, "body_max_length": 100}),
        ("general campaign copy", {"body_min_length": 80, "body_max_length": 200}),
    ],
)
def test_copy_body_length_contract_matches_explicit_format(description, expected):
    assert main.get_copy_body_length_contract(campaign(description)) == expected


def test_initial_copy_worker_payload_contains_body_length_contract():
    payload = main.build_worker_payload_for_task(
        campaign("press release"),
        TaskRecord(
            company_id="company-1",
            campaign_id="campaign-1",
            task_id="copy-task",
            task_type="copywriting",
            status="pending",
            priority=1,
            acceptance=[],
        ),
    )

    assert payload["body_min_length"] == 300
    assert payload["body_max_length"] == 500
    assert payload["task_id"] == "copy-task"
    assert payload["campaign_id"] == "campaign-1"
    assert payload["company_id"] == "company-1"
    assert payload["variants"] == 1
    assert payload["brand_context"]["product_name"] == "Product"
    assert "Copy type policy:" in payload["prompt"]
    assert "公關稿（300-500 字）" in payload["prompt"]


def test_initial_copy_dispatch_contains_body_length_contract(monkeypatch):
    captured = {}
    monkeypatch.setattr(main, "_worker_post_json", lambda _url, payload, *_args: captured.update(payload) or {"variants": [{"body": "copy"}]})

    main.generate_outputs_via_workers(
        "company-1",
        "campaign-1",
        campaign("social post"),
        [TaskRecord(
            company_id="company-1",
            campaign_id="campaign-1",
            task_id="copy-task",
            task_type="copywriting",
            status="pending",
            priority=1,
            acceptance=[],
        )],
    )

    assert captured["body_min_length"] == 100
    assert captured["body_max_length"] == 200


def test_copy_asset_regeneration_payload_contains_body_length_contract(monkeypatch):
    item = campaign("promotional copy")
    asset = AssetOutput(
        company_id="company-1",
        asset_id="asset-1",
        campaign_id="campaign-1",
        task_id="copy-task",
        asset_type="copy",
        url="generated://copy",
        metadata={},
        validation_status="pending",
        created_at=datetime.utcnow(),
    )
    captured = {}
    monkeypatch.setattr(main, "store", type("Store", (), {
        "get_campaign": lambda self, _id: item,
        "get_tasks": lambda self, _id: [],
    })())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "require_campaign_access", lambda _req, _campaign: None)
    monkeypatch.setattr(main, "post_json", lambda _url, payload: captured.update(payload) or {"variants": []})
    monkeypatch.setattr(main, "_capture_worker_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_save_copy_worker_result", lambda *_args: {"status": "accepted", "assets_saved": "0", "asset_ids": ""})
    monkeypatch.setattr(main, "finalize_campaign_workflow", lambda *args, **kwargs: None)

    monkeypatch.setattr(main, "latest_campaign_run_id", lambda _campaign_id: "run-1")
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)

    monkeypatch.setattr(main, "persistence", type("Persistence", (), {
        "get_asset_output": lambda self, _id: asset,
        "get_review_item_by_asset": lambda self, _id: None,
        "list_asset_outputs": lambda self, _id: [asset],
        "save_asset_outputs": lambda self, assets: None,
    })())
    main._perform_asset_regeneration(object(), "asset-1")

    assert captured["body_min_length"] == 0
    assert captured["body_max_length"] == 100


def test_review_revision_copy_dispatch_contains_body_length_contract(monkeypatch):
    item = campaign("public relations announcement")
    captured = {}
    monkeypatch.setattr(main, "store", type("Store", (), {"get_campaign": lambda self, _id: item})())
    monkeypatch.setattr(main, "require_review_action_access", lambda _req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda _req, _campaign: None)
    monkeypatch.setattr(main, "post_json", lambda _url, payload: captured.update(payload) or {})
    monkeypatch.setattr(main, "_capture_worker_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)

    result = main.submit_revision_request(
        main.RevisionRequestPayload(
            review_id="review-1",
            campaign_id="campaign-1",
            task_id="copy-task",
            asset_id="asset-1",
            asset_type="copy",
            reject_reason="Needs revision",
        ),
        object(),
    )

    assert result == {"status": "ok"}
    assert captured["body_min_length"] == 300
    assert captured["body_max_length"] == 500
    assert captured["task_id"] == "copy-task"
    assert captured["campaign_id"] == "campaign-1"
    assert captured["company_id"] == "company-1"
    assert captured["reject_reason"] == "Needs revision"
    assert captured["variants"] == 3
    assert captured["brand_context"] == {}


def test_review_revision_dispatch_retries_transient_worker_failure(monkeypatch):
    item = campaign("public relations announcement")
    attempts = []

    def post_json(_url, _payload):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("Request failed: HTTP Error 503: unavailable")
        return {}

    monkeypatch.setattr(main, "store", type("Store", (), {"get_campaign": lambda self, _id: item})())
    monkeypatch.setattr(main, "require_review_action_access", lambda _req: None)
    monkeypatch.setattr(main, "require_campaign_access", lambda _req, _campaign: None)
    monkeypatch.setattr(main, "post_json", post_json)
    monkeypatch.setattr(main, "_capture_worker_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "WORKER_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(main, "WORKER_RETRY_BACKOFF_SECONDS", 0)

    result = main.submit_revision_request(
        main.RevisionRequestPayload(
            review_id="review-1",
            campaign_id="campaign-1",
            task_id="copy-task",
            asset_id="asset-1",
            asset_type="copy",
            reject_reason="Needs revision",
        ),
        object(),
    )

    assert result == {"status": "ok"}
    assert len(attempts) == 2
