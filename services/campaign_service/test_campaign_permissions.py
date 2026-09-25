from datetime import datetime, timezone

from starlette.requests import Request

from app.auth import JWTPayload
import app.main as main
from app.schemas import CampaignCreatedResponse, CampaignRecord
from test_campaign_validation import valid_brief


def test_campaign_create_accepts_canonical_colon_permission(monkeypatch):
    campaign = CampaignRecord(
        company_id="company-1",
        campaign_id="campaign-1",
        status="draft",
        created_at=datetime.now(timezone.utc),
        brief=valid_brief(),
    )
    monkeypatch.setattr(main.store, "create_campaign", lambda company_id, brief: campaign)
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: None)
    payload = JWTPayload(
        sub="member-1",
        company_id="company-1",
        email="manager@example.com",
        permissions=["campaign:create"],
        exp=2_000_000_000,
        iat=1_900_000_000,
    )
    request = Request({"type": "http", "headers": []})
    monkeypatch.setattr(main, "require_jwt", lambda req: payload)

    result = main.create_campaign(request, valid_brief())

    assert isinstance(result, CampaignCreatedResponse)
    assert result.campaign_id == "campaign-1"
