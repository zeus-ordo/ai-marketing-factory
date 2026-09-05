import os
import sys
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app.persistence import PostgresPersistence


class RecordingCursor:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))


class RecordingConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        pass


def test_initialize_adds_scoped_folder_and_association_columns_to_existing_schema(monkeypatch):
    cursor = RecordingCursor()
    monkeypatch.setattr(PostgresPersistence, "_connect", lambda self: RecordingConnection(cursor))
    persistence = PostgresPersistence.__new__(PostgresPersistence)

    persistence.initialize()

    sql = "\n".join(statement for statement, _params in cursor.statements)
    assert "CREATE TABLE IF NOT EXISTS folders" in sql
    assert "ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS folder_id" in sql
    assert "ALTER TABLE campaign_references ADD COLUMN IF NOT EXISTS folder_id" in sql


def test_legacy_text_without_safe_folder_inference_is_explicitly_unfiled():
    from app.persistence import legacy_folder_id

    assert legacy_folder_id("Old category", []) is None
    assert legacy_folder_id("Brand", [{"folder_id": "folder-brand", "name": "Brand"}]) == "folder-brand"
    assert legacy_folder_id("brand", [
        {"folder_id": "platform-brand", "name": "Brand"},
        {"folder_id": "company-brand", "name": "Brand"},
    ]) is None


def test_legacy_category_is_inferred_through_knowledge_list_production_path(monkeypatch):
    from app import main

    class Persistence:
        def list_knowledge_items(self, _company_id):
            return [{
                "item_id": "item-1", "company_id": "company-a", "title": "Guide", "source": "manual",
                "description": "", "content_url": None, "metadata": {"category": "brand"},
                "created_at": "2026-09-06T00:00:00Z", "folder_id": None,
            }]

        def list_folders(self, _company_id):
            return [{"folder_id": "folder-brand", "scope": "company", "company_id": "company-a", "name": "Brand"}]

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: type("Actor", (), {"company_id": "company-a"})())

    result = main.list_knowledge_items(object())
    assert result.items[0].folder_id == "folder-brand"
