import os
import sys
import pytest
from uuid import uuid4
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app.persistence import PostgresPersistence


class Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.executed.append((statement, params))

    def fetchall(self):
        return self.rows


class Connection:
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


def test_knowledge_and_reference_rows_round_trip_folder_id(monkeypatch):
    knowledge_cursor = Cursor(rows=[("item-1", "company-a", "Guide", "manual", "text", None, {}, datetime.utcnow(), "folder-1")])
    reference_cursor = Cursor(rows=[("ref-1", "campaign-1", "guide.txt", "text/plain", 4, datetime.utcnow(), "/tmp/guide.txt", "General", "folder-1")])
    persistence = PostgresPersistence.__new__(PostgresPersistence)

    cursors = iter([knowledge_cursor, reference_cursor])
    monkeypatch.setattr(persistence, "_connect", lambda: Connection(next(cursors)))

    knowledge = persistence.list_knowledge_items("company-a")
    references = persistence.list_campaign_references("campaign-1")

    assert knowledge[0]["folder_id"] == "folder-1"
    assert references[0]["folder_id"] == "folder-1"
    assert "folder_id" in knowledge_cursor.executed[0][0]
    assert "folder_id" in reference_cursor.executed[0][0]


def test_delete_folder_checks_reference_and_knowledge_associations():
    persistence = PostgresPersistence.__new__(PostgresPersistence)

    class Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params=None):
            self.statement = statement
            self.params = params

        def fetchone(self):
            return (1,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

        def commit(self):
            pass

    persistence._connect = lambda: Connection()
    assert persistence.count_folder_associations("folder-1") == 1


@pytest.mark.skipif(not os.getenv("CAMPAIGN_TEST_DATABASE_URL"), reason="requires disposable PostgreSQL fixture")
def test_reference_folder_association_survives_real_persistence_reload():
    persistence = PostgresPersistence(os.environ["CAMPAIGN_TEST_DATABASE_URL"])
    persistence.initialize()
    folder_id = f"test-folder-{uuid4().hex}"
    reference_id = f"test-reference-{uuid4().hex}"
    persistence.create_folder({
        "folder_id": folder_id, "scope": "company", "company_id": "reload-company", "name": "Reload",
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    })
    persistence.save_campaign_reference(
        reference_id, "reload-campaign", "guide.txt", "text/plain", 1, datetime.utcnow(), __file__, "test",
        "Reload", folder_id,
    )

    reloaded = PostgresPersistence(os.environ["CAMPAIGN_TEST_DATABASE_URL"])
    assert reloaded.list_campaign_references("reload-campaign")[0]["folder_id"] == folder_id
