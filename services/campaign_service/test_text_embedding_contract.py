from app import main


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
