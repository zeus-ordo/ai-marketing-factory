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


def test_save_llm_generation_payload_inserts_prompt_and_all_identifiers(monkeypatch):
    cursor = RecordingCursor()
    monkeypatch.setattr(PostgresPersistence, "_connect", lambda self: RecordingConnection(cursor))
    persistence = PostgresPersistence.__new__(PostgresPersistence)
    payload = {
        "campaign_id": "campaign-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "generation_context_id": "context-1",
        "task_type": "copywriting",
        "provider": "openai",
        "model": "gpt-test",
        "prompt": "PROMPT-MARKER",
        "context": {"source": "context-value"},
    }

    persistence.save_llm_generation_payload(payload)

    statement, params = cursor.statements[0]
    assert "llm_generation_payloads" in statement
    assert "ON CONFLICT DO NOTHING" in statement
    assert params[:8] == (
        "campaign-1", "run-1", "task-1", "context-1",
        "copywriting", "openai", "gpt-test", "PROMPT-MARKER",
    )
    assert params[8] == '{"source": "context-value"}'


def test_initialize_creates_llm_generation_payload_table_and_indexes(monkeypatch):
    cursor = RecordingCursor()
    monkeypatch.setattr(PostgresPersistence, "_connect", lambda self: RecordingConnection(cursor))
    persistence = PostgresPersistence.__new__(PostgresPersistence)

    persistence.initialize()

    sql = "\n".join(statement for statement, _params in cursor.statements)
    assert "CREATE TABLE IF NOT EXISTS llm_generation_payloads" in sql
    assert "idx_llm_generation_payloads_campaign" in sql
    assert "idx_llm_generation_payloads_run" in sql
    assert "idx_llm_generation_payloads_context" in sql
    assert "payload_id UUID PRIMARY KEY" in sql


def test_worker_dispatch_captures_exact_payload_before_call(monkeypatch):
    from app import main

    captured = []
    monkeypatch.setattr(main, "persistence", type("Persistence", (), {
        "save_llm_generation_payload": lambda _self, payload: captured.append(payload),
    })())
    worker_payload = {
        "campaign_id": "campaign-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "generation_context_id": "context-1",
        "provider": "openai",
        "model": "gpt-test",
        "prompt": "PROMPT-MARKER",
        "nested": {"value": "exact"},
    }
    monkeypatch.setattr(main, "post_json", lambda _url, payload: {"ok": True, "payload": payload})

    result = main._worker_post_json("http://worker", worker_payload, "copywriting", "campaign-1", "task-1", "company-1")

    assert result["payload"] == worker_payload
    assert captured[0]["context"] == worker_payload


def test_worker_dispatch_continues_when_capture_fails(monkeypatch):
    from app import main

    class FailingPersistence:
        def save_llm_generation_payload(self, _payload):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "persistence", FailingPersistence())
    monkeypatch.setattr(main, "post_json", lambda _url, _payload: {"ok": True})

    result = main._worker_post_json(
        "http://worker",
        {"task_id": "task-1", "campaign_id": "campaign-1", "prompt": "PROMPT-MARKER"},
        "copywriting",
        "campaign-1",
        "task-1",
        "company-1",
    )

    assert result == {"ok": True}
