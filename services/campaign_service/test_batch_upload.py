import io
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.schemas import CampaignBrief, CampaignRecord


def make_campaign(company_id="company-a", campaign_id="campaign-1"):
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
    def __init__(self, campaign):
        self.campaign = campaign

    def get_campaign(self, campaign_id):
        return self.campaign if campaign_id == self.campaign.campaign_id else None


class Persistence:
    def __init__(self, failure=None):
        self.saved = []
        self.rows = {}
        self.deleted = []
        self.failure = failure

    def save_campaign_reference(self, **payload):
        self.saved.append(payload)
        self.rows[payload["reference_id"]] = payload
        if self.failure:
            raise self.failure

    def delete_campaign_reference(self, campaign_id, reference_id):
        self.deleted.append((campaign_id, reference_id))
        self.rows.pop(reference_id, None)


def request():
    return SimpleNamespace(headers=Headers(), base_url="http://test")


def upload(name="guide.txt", content=b"guide", content_type="text/plain"):
    return UploadFile(
        filename=name,
        file=io.BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.fixture
def configured(monkeypatch, tmp_path):
    campaign = make_campaign()
    persistence = Persistence()
    monkeypatch.setattr(main, "store", Store(campaign))
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "CAMPAIGN_REFERENCES_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: SimpleNamespace(company_id="company-a", permissions=[]))
    monkeypatch.setattr(main, "append_trace_event", lambda **_kwargs: None)
    main.campaign_references.clear()
    main.campaign_reference_files.clear()
    return campaign, persistence, tmp_path


def test_upload_policy_route_precedes_dynamic_campaign_route(configured, monkeypatch):
    campaign, _, _ = configured
    monkeypatch.setattr(main, "derive_campaign_status", lambda item: item.status)
    monkeypatch.setattr(main, "enrich_campaign_diagnostics", lambda item: item)
    client = TestClient(main.app)

    policy_response = client.get("/api/v1/campaigns/upload-policy")
    assert policy_response.status_code == 200
    policy = policy_response.json()
    assert policy["maxBytes"] == main.REFERENCE_MAX_SIZE_BYTES
    assert ".pdf" in policy["allowedExtensions"]
    assert "application/pdf" in policy["mimeTypes"][".pdf"]

    campaign_response = client.get(f"/api/v1/campaigns/{campaign.campaign_id}")
    assert campaign_response.status_code == 200
    assert campaign_response.json()["campaign_id"] == campaign.campaign_id


def test_same_company_reference_upload_succeeds(configured):
    campaign, persistence, _ = configured

    result = main.upload_campaign_reference(campaign.campaign_id, request(), upload(), operator="operator-1", folder_id=None)

    assert result.reference_id.startswith("ref_")
    assert result.folder_id is None
    assert persistence.saved[0]["reference_id"] == result.reference_id
    assert result.download_url == f"/api/v1/campaigns/{campaign.campaign_id}/references/{result.reference_id}/download"


def test_cross_company_reference_upload_is_forbidden_before_write(configured, monkeypatch):
    campaign, persistence, tmp_path = configured
    monkeypatch.setattr(main, "require_jwt", lambda _req: SimpleNamespace(company_id="company-b", permissions=[]))

    class NoRead:
        def read(self, *_args):
            raise AssertionError("upload bytes were read before authorization")

    file = UploadFile(filename="guide.txt", file=NoRead(), headers=Headers({"content-type": "text/plain"}))
    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), file, operator=None, folder_id=None)

    assert exc.value.status_code == 403
    assert exc.value.detail == "CAMPAIGN_ACCESS_DENIED"
    assert persistence.saved == []
    assert list(tmp_path.rglob("*")) == []


def test_oversized_upload_returns_file_too_large(configured, monkeypatch):
    campaign, persistence, tmp_path = configured
    monkeypatch.setattr(main, "REFERENCE_MAX_SIZE_BYTES", 3)

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), upload(content=b"1234"), operator=None, folder_id=None)

    assert exc.value.status_code == 400
    assert exc.value.detail == "FILE_TOO_LARGE"
    assert persistence.saved == []
    assert list(tmp_path.rglob("*")) == []


def test_unsupported_extension_returns_unsupported_file_type(configured):
    campaign, persistence, tmp_path = configured

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), upload(name="guide.exe", content_type="application/octet-stream"), operator=None, folder_id=None)

    assert exc.value.status_code == 400
    assert exc.value.detail == "UNSUPPORTED_FILE_TYPE"
    assert persistence.saved == []
    assert list(tmp_path.rglob("*")) == []


def test_persistence_failure_returns_persistence_error_without_orphan_file(configured, monkeypatch):
    campaign, _, tmp_path = configured
    persistence = Persistence(RuntimeError("database secret /var/lib/postgres"))
    monkeypatch.setattr(main, "persistence", persistence)

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), upload(), operator=None, folder_id=None)

    assert exc.value.status_code == 500
    assert exc.value.detail == "PERSISTENCE_ERROR"
    assert main.campaign_references.get(campaign.campaign_id, []) == []
    assert main.campaign_reference_files.get(campaign.campaign_id, {}) == {}
    assert persistence.rows == {}
    assert list(tmp_path.rglob("*")) == []
    assert "database secret" not in str(exc.value.detail)


def test_directory_creation_failure_returns_sanitized_persistence_error(configured, monkeypatch):
    campaign, persistence, tmp_path = configured
    original_makedirs = main.os.makedirs

    def fail_campaign_directory(path, *args, **kwargs):
        if str(path).startswith(str(tmp_path)):
            raise OSError("secret local path")
        return original_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(main.os, "makedirs", fail_campaign_directory)

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), upload(), operator=None, folder_id=None)

    assert exc.value.status_code == 500
    assert exc.value.detail == "PERSISTENCE_ERROR"
    assert "secret local path" not in str(exc.value.detail)
    assert persistence.rows == {}


def test_generic_stream_failure_returns_sanitized_persistence_error(configured):
    campaign, persistence, tmp_path = configured

    class BrokenStream:
        def read(self, *_args):
            raise RuntimeError("provider secret body")

    file = UploadFile(filename="guide.txt", file=BrokenStream(), headers=Headers({"content-type": "text/plain"}))
    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), file, operator=None, folder_id=None)

    assert exc.value.status_code == 500
    assert exc.value.detail == "PERSISTENCE_ERROR"
    assert "provider secret body" not in str(exc.value.detail)
    assert persistence.rows == {}
    assert list(tmp_path.rglob("*")) == []


def test_upload_timeout_returns_upload_timeout_and_cleans_file(configured, monkeypatch):
    campaign, persistence, tmp_path = configured
    clock = iter((100.0, 100.0, 101.0))
    monkeypatch.setattr(main, "REFERENCE_UPLOAD_TIMEOUT_SECONDS", 0.5, raising=False)
    monkeypatch.setattr(main.time, "monotonic", lambda: next(clock))

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), upload(), operator=None, folder_id=None)

    assert exc.value.status_code == 504
    assert exc.value.detail == "UPLOAD_TIMEOUT"
    assert persistence.rows == {}
    assert list(tmp_path.rglob("*")) == []


def test_upload_result_contains_reference_id_and_folder_id(configured, monkeypatch):
    campaign, persistence, _ = configured
    monkeypatch.setattr(main, "resolve_folder_for_actor", lambda _req, _folder_id: {"name": "Brand"})

    result = main.upload_campaign_reference(campaign.campaign_id, request(), upload(), folder_id="folder-1")

    assert result.reference_id == persistence.saved[0]["reference_id"]
    assert result.folder_id == "folder-1"
    assert result.download_url.startswith("/api/")
    assert "stored_path" not in result.model_dump()


def test_mismatched_mime_returns_unsupported_file_type(configured):
    campaign, persistence, tmp_path = configured

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(
            campaign.campaign_id,
            request(),
            upload(name="guide.txt", content_type="application/pdf"),
            operator=None,
            folder_id=None,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "UNSUPPORTED_FILE_TYPE"
    assert persistence.saved == []
    assert list(tmp_path.rglob("*")) == []


def test_octet_stream_must_match_explicit_safe_extension_allowlist(configured):
    campaign, persistence, tmp_path = configured

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(
            campaign.campaign_id,
            request(),
            upload(name="guide.txt", content_type="application/octet-stream"),
            operator=None,
            folder_id=None,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "UNSUPPORTED_FILE_TYPE"
    assert persistence.rows == {}
    assert list(tmp_path.rglob("*")) == []


def test_partial_database_persistence_is_deleted_after_failure(configured, monkeypatch):
    campaign, _, tmp_path = configured
    persistence = Persistence(RuntimeError("database failure"))
    monkeypatch.setattr(main, "persistence", persistence)

    with pytest.raises(HTTPException) as exc:
        main.upload_campaign_reference(campaign.campaign_id, request(), upload(), operator=None, folder_id=None)

    assert exc.value.detail == "PERSISTENCE_ERROR"
    assert persistence.rows == {}
    assert len(persistence.deleted) == 1
    assert list(tmp_path.rglob("*")) == []


def test_company_user_can_download_visible_platform_knowledge_item(configured, monkeypatch, tmp_path):
    stored_path = tmp_path / "platform-guide.txt"
    stored_path.write_text("platform guide", encoding="utf-8")

    class KnowledgePersistence:
        def list_knowledge_items(self, company_id):
            return [{
                "item_id": "kh_platform",
                "metadata": {"stored_path": str(stored_path)},
            }] if company_id == "platform" else []

    monkeypatch.setattr(main, "persistence", KnowledgePersistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: SimpleNamespace(company_id="company-a", permissions=[]))

    response = main.download_knowledge_item(request(), "kh_platform", "guide.txt")

    assert response.path == str(stored_path)
