from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.main as main
from app.schemas import CampaignBrief, Deliverables, TargetAudience
from app.validation import validate_campaign_brief


def valid_brief(**updates: object) -> CampaignBrief:
    payload: dict[str, object] = {
        "campaign_name": "Spring campaign",
        "product_name": "Coffee beans",
        "objective": "Increase awareness",
        "industry_category": "Food and beverage",
        "project_description": "Launch a seasonal coffee campaign",
        "target_audience": {"age_range": "25-44", "gender": "all", "persona": "Coffee drinkers"},
        "platforms": ["instagram"],
        "budget": 1000,
        "brand_tone": ["warm"],
        "deliverables": {"copy_variants": 1, "image_assets": 1, "short_video_assets": 0, "ads_strategy": 0},
        "deadline": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }
    payload.update(updates)
    return CampaignBrief(**payload)


@pytest.mark.parametrize("field", ["campaign_name", "product_name", "objective", "industry_category", "project_description"])
def test_rejects_blank_required_fields(field: str):
    with pytest.raises(HTTPException) as exc:
        validate_campaign_brief(valid_brief(**{field: "   "}))

    assert exc.value.status_code == 422
    assert field in str(exc.value.detail)


def test_rejects_non_finite_budget():
    with pytest.raises(HTTPException) as exc:
        validate_campaign_brief(valid_brief(budget=float("nan")))

    assert exc.value.status_code == 422
    assert "budget" in str(exc.value.detail)


def test_requires_positive_budget_when_ads_are_selected():
    with pytest.raises(HTTPException) as exc:
        validate_campaign_brief(valid_brief(budget=0, deliverables=Deliverables(ads_strategy=1)))

    assert exc.value.status_code == 422
    assert "budget" in str(exc.value.detail)


def test_allows_zero_budget_without_ads_strategy():
    validate_campaign_brief(valid_brief(budget=0, deliverables=Deliverables(ads_strategy=0)))


def test_preserves_existing_brief_aliases():
    payload = valid_brief().model_dump()
    payload.pop("industry_category")
    payload.pop("project_description")
    payload["industryCategory"] = "Retail"
    payload["projectDescription"] = "Seasonal launch"
    brief = CampaignBrief(**payload)

    validate_campaign_brief(brief)
    assert brief.industry_category == "Retail"
    assert brief.project_description == "Seasonal launch"


def test_invalid_campaign_is_not_persisted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    before = dict(main.store.campaigns)
    request = Request({"type": "http", "headers": [(b"x-internal-api-key", b"test-key")]})

    with pytest.raises(HTTPException) as exc:
        main.create_campaign(request, valid_brief(project_description=""))

    assert exc.value.status_code == 422
    assert main.store.campaigns == before
