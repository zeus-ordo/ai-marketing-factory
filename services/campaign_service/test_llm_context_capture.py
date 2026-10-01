import os
import sys
from pathlib import Path

import pytest

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
    assert "DROP CONSTRAINT" in sql
    assert "ADD PRIMARY KEY (payload_id)" in sql
    assert "UPDATE llm_generation_payloads SET payload_id = uuid_generate_v4()" in sql
    assert "n.nspname = current_schema()" in sql
    assert "array_agg(a.attname ORDER BY k.ordinality)" in sql


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


def test_internal_capture_ingest_requires_key_and_persists_exact_payload(monkeypatch):
    from fastapi import Request
    from app import main

    captured = []
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    monkeypatch.setattr(main, "persistence", type("Persistence", (), {
        "save_llm_generation_payload": lambda _self, payload: captured.append(payload),
    })())
    worker_payload = {
        "campaign_id": "campaign-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "generation_context_id": "context-1",
        "task_type": "copywriting",
        "provider": "openai",
        "model": "gpt-test",
        "prompt": "exact prompt",
        "context": {"nested": {"keep": True}},
    }
    payload = {"task_type": "copywriting", "campaign_id": "campaign-1", "task_id": "task-1", "payload": worker_payload}
    scope = {"type": "http", "method": "POST", "headers": [(b"x-internal-api-key", b"test-key")]}

    response = main.ingest_llm_generation_payload(payload, Request(scope))

    assert response == {"status": "accepted"}
    assert captured[0]["context"] == worker_payload


def test_missing_identifiers_are_not_used_as_conflict_key(monkeypatch):
    cursor = RecordingCursor()
    monkeypatch.setattr(PostgresPersistence, "_connect", lambda self: RecordingConnection(cursor))
    persistence = PostgresPersistence.__new__(PostgresPersistence)
    payload = {
        "campaign_id": "campaign-1",
        "run_id": "",
        "task_id": "task-1",
        "generation_context_id": "",
        "task_type": "copywriting",
        "prompt": "PROMPT-MARKER",
        "context": {},
    }

    persistence.save_llm_generation_payload(payload)
    persistence.save_llm_generation_payload(payload)

    inserts = [statement for statement, _params in cursor.statements if "INSERT INTO llm_generation_payloads" in statement]
    assert len(inserts) == 2
    assert all("ON CONFLICT (campaign_id, run_id, task_id, generation_context_id)" not in statement for statement in inserts)


@pytest.mark.skipif(not os.getenv("CAMPAIGN_TEST_DATABASE_URL"), reason="CAMPAIGN_TEST_DATABASE_URL is not configured")
def test_postgres_migration_preserves_legacy_rows_and_repeated_missing_ids():
    import psycopg

    dsn = os.environ["CAMPAIGN_TEST_DATABASE_URL"]
    table = "llm_generation_payloads"
    legacy = ("legacy-campaign", "legacy-run", "legacy-task", "legacy-context", "copywriting", "legacy-provider", "legacy-model", "LEGACY-PROMPT", "{}")
    payload = {
        "campaign_id": "new-campaign",
        "run_id": "",
        "task_id": "new-task",
        "generation_context_id": "",
        "task_type": "copywriting",
        "provider": "test-provider",
        "model": "test-model",
        "prompt": "NEW-PROMPT",
        "context": {"marker": "new"},
    }

    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(
                f"""
                CREATE TABLE {table} (
                    campaign_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    generation_context_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    context_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (campaign_id, run_id, task_id, generation_context_id)
                )
                """
            )
            cur.execute(
                f"INSERT INTO {table} (campaign_id, run_id, task_id, generation_context_id, task_type, provider, model, prompt, context_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                legacy,
            )

        persistence = PostgresPersistence(dsn)
        persistence.initialize()
        persistence.save_llm_generation_payload(payload)
        persistence.save_llm_generation_payload(payload)

        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT prompt FROM {table} ORDER BY prompt")
            prompts = [row[0] for row in cur.fetchall()]
            cur.execute(
                "SELECT array_agg(a.attname ORDER BY k.ordinality) FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ordinality) ON TRUE JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum WHERE n.nspname = current_schema() AND t.relname = %s AND c.contype = 'p' GROUP BY c.oid",
                (table,),
            )
            primary_keys = cur.fetchall()
        assert "LEGACY-PROMPT" in prompts
        assert prompts.count("NEW-PROMPT") == 2
        assert primary_keys == [(["payload_id"],)]
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
