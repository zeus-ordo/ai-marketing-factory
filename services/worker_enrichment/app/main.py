import json
import logging
import os
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import providers
from .safe_attributes import validate_safe_attributes

try:
    from services.campaign_service.app.image_enrichment import canonical_attribute_text, redact_provider_error
except ImportError:
    def canonical_attribute_text(attributes: dict[str, Any]) -> str:
        safe_attributes = validate_safe_attributes(attributes)
        return json.dumps(safe_attributes, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))

    def redact_provider_error(error: BaseException) -> str:
        return "provider timeout" if isinstance(error, TimeoutError) else "provider request failed"


logger = logging.getLogger("worker_enrichment")
ANALYSIS_VERSION = os.getenv("IMAGE_ANALYSIS_VERSION", "image-rag-v1")
TEXT_EMBEDDING_VERSION = "text-rag-v1"


class PersistenceBoundary(Protocol):
    def get_image_analysis(self, item_id: str, analysis_version: str) -> dict[str, Any] | None: ...
    def get_image_item(self, item_id: str) -> dict[str, Any] | None: ...
    def claim_image_analysis(self, item_id: str, analysis_version: str) -> bool: ...
    def complete_image_analysis(self, item_id: str, analysis_version: str, attributes: dict[str, Any], embedding: list[float], embedding_model: str) -> dict[str, Any]: ...
    def fail_image_analysis(self, item_id: str, analysis_version: str, error_code: str, error_detail: str) -> dict[str, Any]: ...
    def get_text_embedding(self, item_id: str, embedding_version: str) -> dict[str, Any] | None: ...
    def get_text_item(self, item_id: str) -> dict[str, Any] | None: ...
    def claim_text_embedding(self, item_id: str, embedding_version: str) -> bool: ...
    def complete_text_embedding_chunk(self, item_id: str, embedding_version: str, chunk_index: int, chunk_count: int, embedding: list[float], embedding_model: str) -> None: ...
    def complete_text_embedding(self, item_id: str, embedding_version: str, chunk_count: int) -> dict[str, Any]: ...
    def fail_text_embedding(self, item_id: str, embedding_version: str, error_code: str, error_detail: str) -> dict[str, Any]: ...


class PostgresPersistenceBoundary:
    """Small worker-side adapter for the campaign service persistence contract."""

    def __init__(self) -> None:
        self.dsn = os.getenv("CAMPAIGN_DATABASE_URL", os.getenv("DATABASE_URL", ""))

    def _connect(self):
        import psycopg

        if not self.dsn:
            raise RuntimeError("CAMPAIGN_DATABASE_URL is not configured")
        return psycopg.connect(self.dsn)

    @staticmethod
    def _record(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "item_id": row[0],
            "analysis_version": row[1],
            "analysis_status": row[2],
        }

    def get_image_analysis(self, item_id: str, analysis_version: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT item_id, analysis_version, analysis_status FROM knowledge_item_image_analysis "
                "WHERE item_id = %s AND analysis_version = %s LIMIT 1",
                (item_id, analysis_version),
            )
            return self._record(cur.fetchone())

    def get_image_item(self, item_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT item_id, title, description, metadata_json FROM knowledge_items "
                "WHERE item_id = %s AND deleted_at IS NULL",
                (item_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        metadata = row[3] if isinstance(row[3], dict) else {}
        return {
            "item_id": row[0],
            "title": row[1],
            "description": row[2],
            "stored_path": metadata.get("stored_path"),
            "mime_type": metadata.get("mime_type") or metadata.get("file_type") or metadata.get("content_type"),
        }

    def claim_image_analysis(self, item_id: str, analysis_version: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE knowledge_item_image_analysis
                   SET analysis_status = 'processing', embedding_status = 'processing',
                       attempt_count = attempt_count + 1, error_code = NULL,
                       error_detail = NULL, updated_at = NOW()
                   WHERE item_id = %s AND analysis_version = %s
                     AND (analysis_status = 'pending' OR (analysis_status = 'failed' AND retryable = TRUE))
                   RETURNING item_id""",
                (item_id, analysis_version),
            )
            claimed = cur.fetchone() is not None
            conn.commit()
        return claimed

    def complete_image_analysis(self, item_id: str, analysis_version: str, attributes: dict[str, Any], embedding: list[float], embedding_model: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE knowledge_item_image_analysis
                   SET analysis_status = 'ready', embedding_status = 'ready',
                       attributes_json = %s::jsonb, embedding_json = %s::jsonb,
                       embedding_model = %s, embedding_dimension = %s,
                       error_code = NULL, error_detail = NULL, retryable = FALSE,
                       analyzed_at = NOW(), updated_at = NOW()
                   WHERE item_id = %s AND analysis_version = %s
                     AND analysis_status = 'processing'
                   RETURNING item_id""",
                (json.dumps(attributes), json.dumps(embedding), embedding_model, len(embedding), item_id, analysis_version),
            )
            row = cur.fetchone()
            if row is not None:
                # JSONB is the durable fallback; pgvector is an optional retrieval accelerator.
                cur.execute("SAVEPOINT image_analysis_embedding_vector;")
                try:
                    cur.execute(
                        """
                        UPDATE knowledge_item_image_analysis
                        SET embedding = %s::vector
                        WHERE item_id = %s AND analysis_version = %s;
                        """,
                        ("[" + ",".join(str(float(value)) for value in embedding) + "]", item_id, analysis_version),
                    )
                    cur.execute("RELEASE SAVEPOINT image_analysis_embedding_vector;")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT image_analysis_embedding_vector;")
                    cur.execute("RELEASE SAVEPOINT image_analysis_embedding_vector;")
            conn.commit()
        if row is None:
            raise ValueError("image analysis must be claimed before completion")
        return {"item_id": item_id, "analysis_status": "ready"}

    def fail_image_analysis(self, item_id: str, analysis_version: str, error_code: str, error_detail: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE knowledge_item_image_analysis
                   SET analysis_status = 'failed', embedding_status = 'failed',
                       error_code = %s, error_detail = %s, retryable = TRUE, updated_at = NOW()
                   WHERE item_id = %s AND analysis_version = %s
                     AND analysis_status IN ('pending', 'processing')
                   RETURNING item_id""",
                (error_code, error_detail, item_id, analysis_version),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            raise ValueError("image analysis is not pending or processing")
        return {"item_id": item_id, "analysis_status": "failed"}

    def get_text_embedding(self, item_id: str, embedding_version: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT item_id, embedding_version, embedding_status, chunk_count FROM knowledge_item_text_embeddings WHERE item_id = %s AND embedding_version = %s ORDER BY chunk_index", (item_id, embedding_version))
            rows = cur.fetchall()
        if not rows:
            return None
        statuses = [row[2] for row in rows]
        chunk_count = max(int(row[3] or 0) for row in rows)
        status = "failed" if "failed" in statuses else "ready" if chunk_count and len(statuses) >= chunk_count and all(value == "ready" for value in statuses) else "processing" if "processing" in statuses else "pending"
        return {"item_id": rows[0][0], "embedding_version": rows[0][1], "embedding_status": status}

    def get_text_item(self, item_id: str) -> dict[str, Any] | None:
        return self.get_image_item(item_id)

    def claim_text_embedding(self, item_id: str, embedding_version: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_item_text_embeddings SET embedding_status = 'processing', attempt_count = attempt_count + 1, updated_at = NOW() WHERE item_id = %s AND embedding_version = %s AND chunk_index = 0 AND (embedding_status = 'pending' OR (embedding_status = 'failed' AND retryable = TRUE)) RETURNING item_id", (item_id, embedding_version))
            claimed = cur.fetchone() is not None
            conn.commit()
        return claimed

    def complete_text_embedding_chunk(self, item_id: str, embedding_version: str, chunk_index: int, chunk_count: int, embedding: list[float], embedding_model: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_item_text_embeddings SET chunk_count = %s, embedding_status = 'ready', embedding_json = %s::jsonb, embedding_model = %s, embedding_dimension = %s, updated_at = NOW() WHERE item_id = %s AND embedding_version = %s AND chunk_index = %s", (chunk_count, json.dumps(embedding), embedding_model, len(embedding), item_id, embedding_version, chunk_index))
            cur.execute("SAVEPOINT text_embedding_vector_write;")
            try:
                cur.execute("UPDATE knowledge_item_text_embeddings SET embedding = %s::vector WHERE item_id = %s AND embedding_version = %s AND chunk_index = %s", ("[" + ",".join(str(float(value)) for value in embedding) + "]", item_id, embedding_version, chunk_index))
                cur.execute("RELEASE SAVEPOINT text_embedding_vector_write;")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT text_embedding_vector_write;")
                cur.execute("RELEASE SAVEPOINT text_embedding_vector_write;")
            conn.commit()

    def complete_text_embedding(self, item_id: str, embedding_version: str, chunk_count: int) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_item_text_embeddings SET chunk_count = %s, embedding_status = 'ready', retryable = FALSE, updated_at = NOW() WHERE item_id = %s AND embedding_version = %s", (chunk_count, item_id, embedding_version))
            conn.commit()
        return {"item_id": item_id, "embedding_version": embedding_version, "embedding_status": "ready"}

    def fail_text_embedding(self, item_id: str, embedding_version: str, error_code: str, error_detail: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_item_text_embeddings SET embedding_status = 'failed', error_code = %s, error_detail = %s, retryable = TRUE, updated_at = NOW() WHERE item_id = %s AND embedding_version = %s", (error_code, error_detail, item_id, embedding_version))
            conn.commit()
        return {"item_id": item_id, "embedding_version": embedding_version, "embedding_status": "failed"}


persistence: PersistenceBoundary | None = PostgresPersistenceBoundary()
INTERNAL_API_KEY = os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip() or os.getenv("INTERNAL_API_KEY", "").strip()
SAFE_ERROR_CODES = {"ANALYSIS_PROVIDER_ERROR", "EMBEDDING_PROVIDER_ERROR", "INVALID_ATTRIBUTES", "INVALID_EMBEDDING", "PROVIDER_ERROR", "PROVIDER_TIMEOUT"}


class EnrichmentRequest(BaseModel):
    item_id: str = Field(min_length=1)
    analysis_version: str = Field(min_length=1)


app = FastAPI(title="Marketing AI Factory - Image Enrichment Worker", version="0.1.0")


def _result(item_id: str, status: str) -> dict[str, str]:
    return {"item_id": item_id, "status": status}


def _safe_error_code(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return "PROVIDER_TIMEOUT"
    if isinstance(error, providers.ProviderError) and error.code in SAFE_ERROR_CODES:
        return error.code
    return "PROVIDER_ERROR"


def process_image_enrichment_job(payload: dict[str, Any]) -> dict[str, str]:
    item_id = payload.get("item_id")
    analysis_version = payload.get("analysis_version")
    if not isinstance(item_id, str) or not item_id.strip() or not isinstance(analysis_version, str) or not analysis_version.strip():
        raise ValueError("item_id and analysis_version are required")
    if persistence is None:
        raise RuntimeError("persistence boundary is not configured")

    record = persistence.get_image_analysis(item_id, analysis_version)
    if record is None:
        raise ValueError("image analysis record not found")
    if record.get("analysis_status") == "ready":
        return _result(item_id, "already_complete")
    if not persistence.claim_image_analysis(item_id, analysis_version):
        latest = persistence.get_image_analysis(item_id, analysis_version)
        if latest and latest.get("analysis_status") == "ready":
            return _result(item_id, "already_complete")
        return _result(item_id, "already_processing")

    try:
        item = persistence.get_image_item(item_id)
        if not item or not item.get("stored_path"):
            raise ValueError("image source unavailable")
        try:
            attributes = providers.validate_attributes(
                providers.analysis_provider.analyze(
                    str(item["stored_path"]),
                    str(item.get("mime_type") or "image/png"),
                    str(item.get("title") or ""),
                    str(item.get("description") or ""),
                )
            )
        except (TypeError, ValueError) as exc:
            raise providers.ProviderError("INVALID_ATTRIBUTES") from exc
        attribute_text = canonical_attribute_text(attributes)
        try:
            embedding = providers.validate_embedding(providers.embedding_provider.embed(attribute_text))
        except (TypeError, ValueError) as exc:
            raise providers.ProviderError("INVALID_EMBEDDING") from exc
        persistence.complete_image_analysis(
            item_id,
            analysis_version,
            attributes,
            embedding,
            getattr(providers.embedding_provider, "model", os.getenv("EMBEDDING_MODEL", "embedding-model")),
        )
        return _result(item_id, "ready")
    except Exception as exc:
        persistence.fail_image_analysis(item_id, analysis_version, _safe_error_code(exc), redact_provider_error(exc))
        return _result(item_id, "failed")


def _text_chunks(text: str, limit: int = 1200) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks = [paragraph[i:i + limit] for paragraph in paragraphs for i in range(0, len(paragraph), limit)]
    return chunks or [""]


def process_text_embedding_job(payload: dict[str, Any]) -> dict[str, str]:
    item_id = payload.get("item_id")
    version = payload.get("embedding_version", TEXT_EMBEDDING_VERSION)
    if not isinstance(item_id, str) or not item_id.strip() or not isinstance(version, str) or not version.strip():
        raise ValueError("item_id and embedding_version are required")
    if persistence is None:
        raise RuntimeError("persistence boundary is not configured")
    record = persistence.get_text_embedding(item_id, version)
    if record is None:
        raise ValueError("text embedding record not found")
    if record.get("embedding_status") == "ready":
        return _result(item_id, "already_complete")
    if not persistence.claim_text_embedding(item_id, version):
        return _result(item_id, "already_processing")
    try:
        item = persistence.get_text_item(item_id)
        if not item or not item.get("stored_path"):
            raise ValueError("text source unavailable")
        with open(str(item["stored_path"]), encoding="utf-8") as source:
            chunks = _text_chunks(source.read())
        model = getattr(providers.embedding_provider, "model", os.getenv("EMBEDDING_MODEL", "embedding-model"))
        for index, chunk in enumerate(chunks):
            embedding = providers.validate_embedding(providers.embedding_provider.embed(chunk))
            persistence.complete_text_embedding_chunk(item_id, version, index, len(chunks), embedding, model)
        persistence.complete_text_embedding(item_id, version, len(chunks))
        return _result(item_id, "ready")
    except Exception as exc:
        persistence.fail_text_embedding(item_id, version, _safe_error_code(exc), redact_provider_error(exc))
        raise


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/v1/image-enrichment")
def enrich_image(payload: EnrichmentRequest, x_internal_api_key: str | None = Header(default=None)) -> dict[str, str]:
    if not INTERNAL_API_KEY or x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="invalid internal API key")
    try:
        return process_image_enrichment_job(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/internal/v1/text-embedding")
def embed_text(payload: dict[str, Any], x_internal_api_key: str | None = Header(default=None)) -> dict[str, str]:
    if not INTERNAL_API_KEY or x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="invalid internal API key")
    try:
        return process_text_embedding_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
