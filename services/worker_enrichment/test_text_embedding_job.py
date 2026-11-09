from pathlib import Path
import pytest

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
        incomplete_ready = (
            self.record.get("embedding_status") == "ready"
            and self.record.get("ready_chunk_count", 0) < self.record.get("chunk_count", 0)
        )
        if self.record["embedding_status"] != "pending" and not incomplete_ready: return False
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
    with pytest.raises(RuntimeError):
        main.process_text_embedding_job({"item_id": "item-1", "embedding_version": "text-rag-v1"})
    assert persistence.failed == ("PROVIDER_ERROR", "provider request failed")


def test_partial_chunk_failure_marks_failed_and_raises(monkeypatch, tmp_path: Path):
    source = tmp_path / "news.txt"
    source.write_text("alpha\n\nbeta", encoding="utf-8")
    persistence = FakePersistence(str(source))
    monkeypatch.setattr(main, "persistence", persistence)
    calls = {"count": 0}
    def embed(self, text):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("provider down")
        return [1.0]
    monkeypatch.setattr(main.providers, "embedding_provider", type("Provider", (), {"embed": embed})())
    with pytest.raises(RuntimeError):
        main.process_text_embedding_job({"item_id": "item-1", "embedding_version": "text-rag-v1"})
    assert len(persistence.chunks) == 1
    assert persistence.record["embedding_status"] == "failed"


def test_ready_text_embedding_job_is_idempotent(monkeypatch, tmp_path: Path):
    source = tmp_path / "news.txt"
    source.write_text("alpha", encoding="utf-8")
    persistence = FakePersistence(str(source))
    persistence.record["embedding_status"] = "ready"
    monkeypatch.setattr(main, "persistence", persistence)
    result = main.process_text_embedding_job({"item_id": "item-1", "embedding_version": "text-rag-v1"})
    assert result == {"item_id": "item-1", "status": "already_complete"}
    assert persistence.chunks == []


def test_partial_ready_text_embedding_reclaims_and_rebuilds_all_chunks(monkeypatch, tmp_path: Path):
    source = tmp_path / "news.txt"
    source.write_text("alpha\n\nbeta\n\ngamma", encoding="utf-8")
    persistence = FakePersistence(str(source))
    persistence.record.update(embedding_status="ready", chunk_count=3, ready_chunk_count=1)
    persistence.chunks.append((0, 3, [999.0], "old-model"))
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main.providers, "embedding_provider", type("Provider", (), {"model": "test-model", "embed": lambda self, text: [float(len(text))]})())

    result = main.process_text_embedding_job({"item_id": "item-1", "embedding_version": "text-rag-v1"})

    assert result == {"item_id": "item-1", "status": "ready"}
    assert [chunk[0] for chunk in persistence.chunks[1:]] == [0, 1, 2]
