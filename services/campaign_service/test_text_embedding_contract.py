from app import main
from app.persistence import PostgresPersistence, aggregate_text_embedding_status


def test_text_upload_creates_pending_state_and_text_enqueue(monkeypatch):
    item = {"item_id": "item-1", "metadata": {"file_name": "news.txt", "file_type": "text/plain", "sha256": "abc"}}
    created, enqueued = [], []
    monkeypatch.setattr(main, "persistence", type("Persistence", (), {"create_text_embedding": lambda self, item_id, version, sha: created.append((item_id, version, sha)) or {"embedding_status": "pending", "embedding_version": version, "chunk_count": 0, "ready_chunk_count": 0}})())
    monkeypatch.setattr(main, "enqueue_text_embedding", lambda *args: enqueued.append(args))
    state = main._create_pending_text_embedding(item)
    assert state["embedding_status"] == "pending"
    assert created == [("item-1", "text-rag-v1", "abc")]
    assert enqueued == [("item-1", "text-rag-v1")]


def test_ready_text_retrieval_excludes_pending_rows():
    rows = [{"item_id": "ready", "embedding_status": "ready", "embedding": [1.0]}, {"item_id": "pending", "embedding_status": "pending", "embedding": [1.0]}]
    assert [row["item_id"] for row in main.ready_text_embedding_rows(rows)] == ["ready"]


def test_text_context_uses_ready_semantic_results_and_fallback(monkeypatch):
    class Persistence:
        def search_ready_text_embeddings(self, query_embedding, limit=8):
            return [{"item_id": "ready", "title": "Ready", "description": "semantic", "metadata": {"file_type": "text/plain"}, "score": 0.9}]
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setenv("TEXT_RAG_QUERY_EMBEDDING", "[1.0]")
    result = main.retrieve_text_reference_context("query", fallback_rows=[{"item_id": "pending", "title": "Pending", "description": "excerpt", "metadata": {"file_type": "text/plain"}}])
    assert [row["item_id"] for row in result] == ["ready"]


def test_text_context_falls_back_deterministically_when_semantic_unavailable(monkeypatch):
    class Persistence:
        def search_ready_text_embeddings(self, query_embedding, limit=8): raise RuntimeError("pgvector unavailable")
    monkeypatch.setattr(main, "persistence", Persistence())
    rows = [{"item_id": "b", "title": "B", "description": "b", "metadata": {"file_type": "text/plain"}}, {"item_id": "a", "title": "A", "description": "a", "metadata": {"file_type": "text/plain"}}]
    result = main.retrieve_text_reference_context("query", fallback_rows=rows)
    assert [row["item_id"] for row in result] == ["a", "b"]


def test_mixed_chunk_status_is_deterministic():
    assert aggregate_text_embedding_status(["processing", "ready"], 2) == "processing"
    assert aggregate_text_embedding_status(["failed", "ready"], 2) == "failed"
    assert aggregate_text_embedding_status(["ready", "ready"], 2) == "ready"


def test_text_chunk_completion_writes_optional_vector_column():
    class Cursor:
        def __init__(self): self.queries = []
        def execute(self, query, params=()): self.queries.append((query, params))
        def fetchone(self): return ("item-1", "text-rag-v1", "sha")
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Conn:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    persistence = PostgresPersistence.__new__(PostgresPersistence)
    conn = Conn()
    persistence._connect = lambda: conn
    persistence.complete_text_embedding_chunk("item-1", "text-rag-v1", 1, 2, [0.1, 0.2], "model")
    assert any("embedding = %s::vector" in query for query, _ in conn.cursor_value.queries)


def test_text_embedding_persistence_exposes_reset_and_list_methods():
    assert callable(getattr(PostgresPersistence, "reset_text_embedding_for_retry"))
    assert callable(getattr(PostgresPersistence, "list_text_embeddings"))
