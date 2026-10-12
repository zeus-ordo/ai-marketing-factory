import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.schemas import CampaignBrief, CampaignRecord


def campaign(company_id="company-a", campaign_id="campaign-1"):
    return CampaignRecord(
        company_id=company_id,
        campaign_id=campaign_id,
        created_at=datetime.utcnow(),
        brief=CampaignBrief(
            campaign_name="Campaign",
            product_name="Product",
            objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"},
            platforms=["social"],
            budget=1,
            brand_tone=[],
            deliverables={},
            deadline="2026-09-06T00:00:00Z",
        ),
    )


class Store:
    def __init__(self, item):
        self.item = item

    def get_campaign(self, campaign_id):
        return self.item if campaign_id == self.item.campaign_id else None


class Persistence:
    def list_campaign_references(self, campaign_id):
        return [{
            "reference_id": "ref-1", "campaign_id": campaign_id, "file_name": "guide.txt",
            "file_type": "text/plain", "file_size": 1, "uploaded_at": "2026-09-06T00:00:00Z",
            "stored_path": __file__, "folder": "General", "folder_id": None,
        }]

    def get_campaign_reference(self, campaign_id, reference_id):
        return self.list_campaign_references(campaign_id)[0] if reference_id == "ref-1" else None


def test_reference_list_requires_same_company_jwt(monkeypatch):
    item = campaign()
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: SimpleNamespace(company_id="company-b", permissions=[]))

    with pytest.raises(HTTPException) as exc:
        main.list_campaign_references(item.campaign_id, object())
    assert exc.value.status_code == 403


def test_reference_download_requires_authentication(monkeypatch):
    item = campaign()
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: (_ for _ in ()).throw(HTTPException(status_code=401, detail="Unauthorized")))

    with pytest.raises(HTTPException) as exc:
        main.download_campaign_reference(item.campaign_id, "ref-1", object())
    assert exc.value.status_code == 401


def test_reference_list_allows_same_company_and_explicit_internal_bypass(monkeypatch):
    item = campaign()
    monkeypatch.setattr(main, "store", Store(item))
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: SimpleNamespace(company_id="company-a", permissions=[]))

    request = SimpleNamespace(base_url="http://test")
    assert main.list_campaign_references(item.campaign_id, request).total == 1

    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: True)
    assert main.list_campaign_references(item.campaign_id, request).total == 1
