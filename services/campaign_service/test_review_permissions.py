import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app import main


def request():
    return SimpleNamespace(headers={})


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
