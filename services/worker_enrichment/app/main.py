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


class PersistenceBoundary(Protocol):
    def get_image_analysis(self, item_id: str, analysis_version: str) -> dict[str, Any] | None: ...
    def get_image_item(self, item_id: str) -> dict[str, Any] | None: ...
    def claim_image_analysis(self, item_id: str, analysis_version: str) -> bool: ...
    def complete_image_analysis(self, item_id: str, analysis_version: str, attributes: dict[str, Any], embedding: list[float], embedding_model: str) -> dict[str, Any]: ...
    def fail_image_analysis(self, item_id: str, analysis_version: str, error_code: str, error_detail: str) -> dict[str, Any]: ...


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
            os.getenv("EMBEDDING_MODEL", "embedding-model"),
        )
        return _result(item_id, "ready")
    except Exception as exc:
        persistence.fail_image_analysis(item_id, analysis_version, _safe_error_code(exc), redact_provider_error(exc))
        return _result(item_id, "failed")


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
