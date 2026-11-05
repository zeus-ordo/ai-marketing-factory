from pathlib import Path

from app import main


class FakePersistence:
    def __init__(self, path: str):
        self.item = {"item_id": "item-1", "stored_path": path}
        self.record = {"item_id": "item-1", "embedding_status": "pending"}
        self.chunks = []
        self.failed = None

    def get_text_embedding(self, item_id, version): return self.record
    def get_text_item(self, item_id): return self.item
    def claim_text_embedding(self, item_id, version):
        if self.record["embedding_status"] != "pending": return False
        self.record["embedding_status"] = "processing"
        return True
    def complete_text_embedding_chunk(self, item_id, version, index, count, embedding, model): self.chunks.append((index, count, embedding, model))
    def complete_text_embedding(self, item_id, version, count): self.record.update(embedding_status="ready", chunk_count=count, ready_chunk_count=count)
    def fail_text_embedding(self, item_id, version, code, detail): self.failed = (code, detail); self.record["embedding_status"] = "failed"


def test_text_embedding_job_reads_utf8_chunks_and_marks_ready(monkeypatch, tmp_path: Path):
    source = tmp_path / "news.txt"
    source.write_text("alpha\n\nbeta\n\ngamma", encoding="utf-8")
    persistence = FakePersistence(str(source))
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main.providers, "embedding_provider", type("Provider", (), {"model": "test-model", "embed": lambda self, text: [float(len(text))]})())
    result = main.process_text_embedding_job({"item_id": "item-1", "embedding_version": "text-rag-v1"})
    assert result == {"item_id": "item-1", "status": "ready"}
    assert len(persistence.chunks) == 3


def test_text_embedding_job_provider_failure_is_retryable(monkeypatch, tmp_path: Path):
    source = tmp_path / "news.txt"
    source.write_text("alpha", encoding="utf-8")
    persistence = FakePersistence(str(source))
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main.providers, "embedding_provider", type("Provider", (), {"embed": lambda self, text: (_ for _ in ()).throw(RuntimeError("secret/private/path"))})())
    result = main.process_text_embedding_job({"item_id": "item-1", "embedding_version": "text-rag-v1"})
    assert result["status"] == "failed"
    assert persistence.failed == ("PROVIDER_ERROR", "provider request failed")
