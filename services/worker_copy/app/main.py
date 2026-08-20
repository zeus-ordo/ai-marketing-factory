import logging
import os
import time
from fastapi import FastAPI, HTTPException
import httpx
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .schemas import CopyRunRequest, CopyRunResponse, CopyVariant, RevisionRequest

CAMPAIGN_SERVICE_URL = os.getenv("CAMPAIGN_SERVICE_URL", "http://campaign-service:8080").strip()
INTERNAL_API_KEY = (os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip() or os.getenv("INTERNAL_API_KEY", "").strip())


REQUEST_COUNT = Counter(
    "worker_copy_requests_total",
    "Total copy generation requests",
    ["status"],
)
REQUEST_LATENCY = Histogram(
    "worker_copy_request_latency_seconds",
    "Copy generation latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
STUB_MODE_COUNT = Counter(
    "worker_copy_stub_mode_total",
    "Requests served in stub mode",
)
REGENERATE_COUNT = Counter(
    "worker_copy_regenerate_total",
    "Copy regeneration requests",
    ["status"],
)

app = FastAPI(
    title="Marketing AI Factory - Copy Worker",
    version="0.1.0",
    description="Real DeepSeek-v3 copy generation worker.",
)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_V3_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip().rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
STRICT_REAL_MODE = os.getenv("WORKER_STRICT_REAL_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

logger = logging.getLogger("worker_copy")


def _has_real_key(value: str) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    return token.lower() not in {"replace-me", "changeme", "change_me", "your_api_key"}


def build_copy_prompt(prompt: str, brand_context: dict[str, object], variant_no: int) -> str:
    context_parts = []
    if brand_context:
        for key, val in brand_context.items():
            context_parts.append(f"{key}: {val}")
    context_str = "\n".join(context_parts)
    return (
        f"{prompt}\n"
        + (f"Brand context:\n{context_str}\n" if context_str else "")
        + (
            f"Generate copy variant {variant_no}. "
            "Output ONLY valid JSON with these exact keys and length limits: "
            '{"title": "max 30 chars", "body": "80-200 chars", "cta": "max 15 chars"}. '
            "Do NOT use null or empty strings for any field."
        )
    )


def _report_usage(company_id: str, model: str, provider: str, usage: dict[str, int]) -> None:
    """Fire-and-forget report of LLM token usage to campaign service."""
    if not INTERNAL_API_KEY or not CAMPAIGN_SERVICE_URL:
        logger.warning(
            "worker_copy: _report_usage skipped — INTERNAL_API_KEY or CAMPAIGN_SERVICE_URL not configured"
        )
        return
    import json as _json
    try:
        import urllib.request as _req
        payload = {
            "company_id": company_id,
            "model": model,
            "provider": provider,
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "request_count": 1,
        }
        req = _req.Request(
            f"{CAMPAIGN_SERVICE_URL}/internal/usage/ingest",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Internal-Api-Key": INTERNAL_API_KEY,
            },
            data=_json.dumps(payload).encode("utf-8"),
        )
        with _req.urlopen(req, timeout=5):
            pass
    except Exception as exc:
        logger.warning(f"worker_copy: _report_usage failed: {exc}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/internal/workers/copy/run", response_model=CopyRunResponse)
def run_copy_worker(payload: CopyRunRequest) -> CopyRunResponse:
    t0 = time.perf_counter()
    variants: list[CopyVariant] = []

    if not _has_real_key(DEEPSEEK_API_KEY):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail="DEEPSEEK_V3_API_KEY is required when WORKER_STRICT_REAL_MODE=true")
        for index in range(payload.variants):
            no = index + 1
            variants.append(
                CopyVariant(
                    title=f"[stub] {payload.prompt} - Variant {no}",
                    body=f"Premium campaign copy variant {no} for {payload.campaign_id}.",
                    cta="Learn More",
                )
            )
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="stub").inc()
        STUB_MODE_COUNT.inc()
        return CopyRunResponse(
            task_id=payload.task_id,
            provider="DeepSeek",
            model_name=f"{DEEPSEEK_MODEL}-stub",
            variants=variants,
        )

    for index in range(payload.variants):
        variant_no = index + 1
        user_prompt = build_copy_prompt(payload.prompt, payload.brand_context, variant_no)

        raw = None
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(
                        f"{DEEPSEEK_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": DEEPSEEK_MODEL,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": (
                                        f"{user_prompt}\n\n"
                                        "Respond ONLY with valid JSON. "
                                        'Field rules: "title" max 30 chars, "body" 80-200 chars, "cta" max 15 chars. '
                                        'Do NOT use null, None, or empty strings for any field.'
                                    ),
                                }
                            ],
                            "response_format": {"type": "json_object"},
                            "thinking": {"type": "disabled"},
                            "temperature": 0.8,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    usage = data.get("usage", {})
                    if usage and payload.company_id:
                        _report_usage(payload.company_id, DEEPSEEK_MODEL, "deepseek", usage)
                    break
            except Exception as exc:
                last_exc = exc
                continue

        if raw is None:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"DeepSeek copy generation failed: {last_exc}",
            ) from last_exc

        import json as _json

        try:
            parsed = _json.loads(raw)
        except Exception:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"DeepSeek returned non-JSON: {raw[:200]}",
            )

        variants.append(
            CopyVariant(
                title=str(parsed["title"]) if parsed.get("title") else f"Variant {variant_no}",
                body=str(parsed["body"]) if parsed.get("body") else f"Copy variant {variant_no} for {payload.campaign_id}.",
                cta=str(parsed["cta"]) if parsed.get("cta") else "Learn More",
            )
        )

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REQUEST_COUNT.labels(status="success").inc()
    return CopyRunResponse(
        task_id=payload.task_id,
        provider="DeepSeek",
        model_name=DEEPSEEK_MODEL,
        variants=variants,
    )


@app.post("/internal/workers/copy/regenerate", response_model=CopyRunResponse)
def regenerate_copy(payload: RevisionRequest) -> CopyRunResponse:
    t0 = time.perf_counter()
    variants: list[CopyVariant] = []

    revised_prompt = (
        f"{payload.prompt}\n\n"
        f"Note: The previous version was rejected. Reason: {payload.reject_reason}\n"
        "Please provide an improved version."
    )

    if not _has_real_key(DEEPSEEK_API_KEY):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail="DEEPSEEK_V3_API_KEY is required when WORKER_STRICT_REAL_MODE=true")
        for index in range(payload.variants):
            no = index + 1
            variants.append(
                CopyVariant(
                    title=f"[stub-rev] {payload.prompt} - Revision {no}",
                    body=f"Revised copy ({payload.reject_reason[:50]}) for {payload.campaign_id}.",
                    cta="Learn More",
                )
            )
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="stub").inc()
        return CopyRunResponse(
            task_id=payload.task_id,
            provider="DeepSeek",
            model_name=f"{DEEPSEEK_MODEL}-rev-stub",
            variants=variants,
        )

    for index in range(payload.variants):
        variant_no = index + 1
        user_prompt = build_copy_prompt(revised_prompt, payload.brand_context, variant_no)

        raw = None
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(
                        f"{DEEPSEEK_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": DEEPSEEK_MODEL,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": (
                                        f"{user_prompt}\n\n"
                                        "Respond ONLY with valid JSON. "
                                        'Field rules: "title" max 30 chars, "body" 80-200 chars, "cta" max 15 chars. '
                                        'Do NOT use null, None, or empty strings for any field.'
                                    ),
                                }
                            ],
                            "response_format": {"type": "json_object"},
                            "thinking": {"type": "disabled"},
                            "temperature": 0.8,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    usage = data.get("usage", {})
                    if usage and payload.company_id:
                        _report_usage(payload.company_id, f"{DEEPSEEK_MODEL}-rev", "deepseek", usage)
                    break
            except Exception as exc:
                last_exc = exc
                continue

        if raw is None:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"DeepSeek copy regeneration failed: {last_exc}",
            ) from last_exc

        import json as _json

        try:
            parsed = _json.loads(raw)
        except Exception:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"DeepSeek returned non-JSON: {raw[:200]}",
            )

        variants.append(
            CopyVariant(
                title=str(parsed["title"]) if parsed.get("title") else f"Revision {variant_no}",
                body=str(parsed["body"]) if parsed.get("body") else f"Revised copy for {payload.campaign_id}.",
                cta=str(parsed["cta"]) if parsed.get("cta") else "Learn More",
            )
        )

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REGENERATE_COUNT.labels(status="success").inc()
    return CopyRunResponse(
        task_id=payload.task_id,
        provider="DeepSeek",
        model_name=f"{DEEPSEEK_MODEL}-rev",
        variants=variants,
    )
