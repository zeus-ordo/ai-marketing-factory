import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main


def actor(company_id="company-a", permissions=None):
    return SimpleNamespace(company_id=company_id, permissions=permissions or ["folder:read", "folder:use"])


def test_company_can_read_and_use_platform_folder_but_cannot_mutate():
    folder = {"folder_id": "platform-brand", "scope": "platform", "company_id": None, "name": "Brand"}

    main.authorize_folder_access(folder, actor(), "read")
    main.authorize_folder_access(folder, actor(), "use")
    with pytest.raises(HTTPException) as exc:
        main.authorize_folder_access(folder, actor(), "edit")
    assert exc.value.status_code == 403


def test_company_folder_requires_matching_company_and_permission():
    folder = {"folder_id": "company-brand", "scope": "company", "company_id": "company-a", "name": "Brand"}
    main.authorize_folder_access(folder, actor(permissions=["folder:edit"]), "edit")

    with pytest.raises(HTTPException) as exc:
        main.authorize_folder_access(folder, actor("company-b", ["folder:read"]), "read")
    assert exc.value.status_code == 403


def test_legacy_unfiled_content_remains_general_when_no_folder_id_exists():
    assert main.authorize_folder_access({"folder_id": None, "scope": None, "company_id": None, "name": "General"}, actor(), "use") is None


def test_folder_delete_rejects_referenced_folder(monkeypatch):
    folder = {"folder_id": "company-brand", "scope": "company", "company_id": "company-a", "name": "Brand"}

    class Persistence:
        def get_folder(self, folder_id):
            return folder if folder_id == folder["folder_id"] else None

        def count_folder_associations(self, folder_id):
            return 1

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor(permissions=["folder:delete"]))

    with pytest.raises(HTTPException) as exc:
        main.delete_folder(object(), "company-brand")
    assert exc.value.status_code == 409
