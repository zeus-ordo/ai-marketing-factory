import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app import main


def request():
    return SimpleNamespace(headers={})


def authorized_request(company_id="co-1", permissions=None):
    return SimpleNamespace(headers={}, company_id=company_id, permissions=permissions or ["review:manage"])


def review_fixture(monkeypatch, company_id="co-1"):
    campaign = main.CampaignRecord(
        company_id=company_id,
        campaign_id="campaign-review",
        created_at=main.datetime.utcnow(),
        brief=main.CampaignBrief(
            campaign_name="Review campaign",
            product_name="Product",
            objective="awareness",
            industry_category="food",
            project_description="brief",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"},
            platforms=["social"],
            budget=1,
            brand_tone=[],
            deliverables={},
            deadline=main.datetime.utcnow(),
        ),
    )
    item = main.ReviewItem(
        review_id="review-1",
        campaign_id=campaign.campaign_id,
        asset_id="asset-1",
        score=1,
        status="review_pending",
        submitted_at=main.datetime.utcnow().isoformat(),
    )

    class Store:
        def get_campaign(self, campaign_id):
            return campaign if campaign_id == campaign.campaign_id else None

        def get_tasks(self, _campaign_id):
            return []

    monkeypatch.setattr(main, "store", Store())
    monkeypatch.setattr(main, "find_review_item", lambda _review_id: item)
    monkeypatch.setattr(main, "build_review_items", lambda: [item])
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "sync_approved_asset_to_knowledge_item", lambda *args: None)
    monkeypatch.setattr(main, "finalize_campaign_workflow", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_review_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_notify_webhook", lambda *args, **kwargs: None)
    return campaign, item


@pytest.mark.parametrize(
    "permissions",
    [["review:manage"], ["review:approve"], ["review:reject"], ["review:revision"], ["*"], ["admin"], ["platform:admin"]],
)
def test_review_access_accepts_review_permissions_and_bypasses(monkeypatch, permissions):
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(permissions=permissions))

    main.require_review_action_access(request())


def test_review_access_rejects_users_without_review_permission(monkeypatch):
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(permissions=["role:manage"]))

    with pytest.raises(main.HTTPException) as error:
        main.require_review_action_access(request())

    assert error.value.status_code == 403


def test_review_queue_and_diagnostics_require_review_permission_and_scope_company(monkeypatch):
    campaign, item = review_fixture(monkeypatch)
    monkeypatch.setattr(main, "generation_diagnostics", lambda *_args: {
        "generation_context_id": "context-1",
        "provenance": [{"source_type": "campaign_reference"}],
    })
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id="co-1", permissions=["review:manage"]))

    result = main.list_review_queue(authorized_request())
    assert result.items[0].review_id == item.review_id
    assert result.items[0].source_summary["generation_context_id"] == "context-1"
    assert result.items[0].source_provenance[0]["source_type"] == "campaign_reference"

    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id="other-company", permissions=["review:manage"]))
    isolated = main.list_review_queue(authorized_request(company_id="other-company"))
    assert isolated.items == []
    assert isolated.total == 0


@pytest.mark.parametrize("permission", ["review:manage", "review:approve", "review:reject", "review:revision", "*"])
def test_review_actions_accept_manage_legacy_and_wildcard_permissions(monkeypatch, permission):
    campaign, item = review_fixture(monkeypatch)
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=[permission]))
    req = authorized_request(permissions=[permission])

    main.approve_review_item(item.review_id, main.ReviewActionRequest(), req)


def test_review_actions_reject_unauthorized_and_cross_company_users(monkeypatch):
    campaign, item = review_fixture(monkeypatch)
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=["role:manage"]))
    with pytest.raises(HTTPException) as unauthorized:
        main.approve_review_item(item.review_id, main.ReviewActionRequest(), authorized_request(permissions=["role:manage"]))
    assert unauthorized.value.status_code == 403

    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id="other-company", permissions=["review:manage"]))
    with pytest.raises(HTTPException) as isolated:
        main.approve_review_item(item.review_id, main.ReviewActionRequest(), authorized_request(company_id="other-company"))
    assert isolated.value.status_code == 403


def test_reject_and_revision_actions_accept_review_manage(monkeypatch):
    campaign, item = review_fixture(monkeypatch)
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=["review:manage"]))
    req = authorized_request()
    main.reject_review_item(item.review_id, main.ReviewActionRequest(reason="needs changes"), req)

    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=["review:reject"]))
    main.reject_review_item(item.review_id, main.ReviewActionRequest(reason="needs changes"), authorized_request(permissions=["review:reject"]))

    monkeypatch.setattr(main, "WORKER_TYPE_TO_URL", {"copy": "http://worker"})
    monkeypatch.setattr(main, "post_json", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=["review:manage"]))
    main.submit_revision_request(
        main.RevisionRequestPayload(
            review_id=item.review_id,
            campaign_id=campaign.campaign_id,
            task_id="task-1",
            asset_id=item.asset_id,
            asset_type="copy",
            reject_reason="needs changes",
        ),
        req,
    )

    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=["review:revision"]))
    main.submit_revision_request(
        main.RevisionRequestPayload(
            review_id=item.review_id,
            campaign_id=campaign.campaign_id,
            task_id="task-1",
            asset_id=item.asset_id,
            asset_type="copy",
            reject_reason="needs changes",
        ),
        authorized_request(permissions=["review:revision"]),
    )


def test_all_review_actions_reject_an_unauthorized_user(monkeypatch):
    campaign, item = review_fixture(monkeypatch)
    monkeypatch.setattr(main, "require_jwt", lambda _request: SimpleNamespace(company_id=campaign.company_id, permissions=["role:manage"]))
    req = authorized_request(permissions=["role:manage"])

    with pytest.raises(HTTPException) as approve_error:
        main.approve_review_item(item.review_id, main.ReviewActionRequest(), req)
    assert approve_error.value.status_code == 403

    with pytest.raises(HTTPException) as reject_error:
        main.reject_review_item(item.review_id, main.ReviewActionRequest(reason="reason"), req)
    assert reject_error.value.status_code == 403

    with pytest.raises(HTTPException) as revision_error:
        main.submit_revision_request(
            main.RevisionRequestPayload(
                review_id=item.review_id,
                campaign_id=campaign.campaign_id,
                task_id="task-1",
                asset_id=item.asset_id,
                asset_type="copy",
                reject_reason="reason",
            ),
            req,
        )
    assert revision_error.value.status_code == 403
