import logging
import os
import time
from fastapi import FastAPI, HTTPException
import httpx
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .schemas import AdsRunRequest, AdsRunResponse, RevisionRequest

CAMPAIGN_SERVICE_URL = os.getenv("CAMPAIGN_SERVICE_URL", "http://campaign-service:8080").strip()
INTERNAL_API_KEY = (os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip() or os.getenv("INTERNAL_API_KEY", "").strip())


REQUEST_COUNT = Counter(
    "worker_ads_requests_total",
    "Total ads strategy generation requests",
    ["status"],
)
REQUEST_LATENCY = Histogram(
    "worker_ads_request_latency_seconds",
    "Ads generation latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
STUB_MODE_COUNT = Counter(
    "worker_ads_stub_mode_total",
    "Requests served in stub mode",
)
REGENERATE_COUNT = Counter(
    "worker_ads_regenerate_total",
    "Ads regeneration requests",
    ["status"],
)

app = FastAPI(
    title="Marketing AI Factory - Ads Strategy Worker",
    version="0.1.0",
    description="Real ads strategy generation worker (DeepSeek).",
)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_V3_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip().rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
STRICT_REAL_MODE = os.getenv("WORKER_STRICT_REAL_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

logger = logging.getLogger("worker_ads")


def _has_real_key(value: str) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    return token.lower() not in {"replace-me", "changeme", "change_me", "your_api_key"}


def _report_usage(company_id: str, model: str, provider: str, usage: dict[str, int]) -> None:
    """Fire-and-forget report of LLM token usage to campaign service."""
    if not INTERNAL_API_KEY or not CAMPAIGN_SERVICE_URL:
        logger.warning(
            "worker_ads: _report_usage skipped — INTERNAL_API_KEY or CAMPAIGN_SERVICE_URL not configured"
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
        logger.warning(f"worker_ads: _report_usage failed: {exc}")


def build_ads_prompt(objective: str, budget: float, platforms: list[str]) -> str:
    return (
        f"You are an expert digital marketing strategist.\n"
        f"Campaign objective: {objective}\n"
        f"Total budget: ${budget:.2f}\n"
        f"Target platforms: {', '.join(platforms)}\n\n"
        "Respond ONLY with valid JSON: "
        '{"<platform>": {"budget": <number>, "strategy": "<brief>"}, ...}.'
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/internal/workers/ads/run", response_model=AdsRunResponse)
def run_ads_worker(payload: AdsRunRequest) -> AdsRunResponse:
    t0 = time.perf_counter()
    platforms = payload.platforms or ["facebook"]

    if not _has_real_key(DEEPSEEK_API_KEY):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail="DEEPSEEK_V3_API_KEY is required when WORKER_STRICT_REAL_MODE=true")
        normalized: dict[str, dict[str, float]] = {
            p: {"budget": round(payload.budget / len(platforms), 2)} for p in platforms
        }
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="stub").inc()
        STUB_MODE_COUNT.inc()
        return AdsRunResponse(
            task_id=payload.task_id,
            provider="DeepSeek",
            model_name=f"{DEEPSEEK_MODEL}-stub",
            ads_plan=normalized,
        )

    user_prompt = build_ads_prompt(payload.objective, payload.budget, platforms)

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
                    "messages": [{"role": "user", "content": user_prompt}],
                    "response_format": {"type": "json_object"},
                    "thinking": {"type": "disabled"},
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        if usage and payload.company_id:
            _report_usage(payload.company_id, DEEPSEEK_MODEL, "deepseek", usage)
    except Exception as exc:
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="error").inc()
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek ads generation failed: {exc}",
        ) from exc

    import json as _json

    try:
        plan = _json.loads(raw)
    except Exception:
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="error").inc()
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek returned non-JSON: {raw[:200]}",
        )

    normalized: dict[str, dict[str, float]] = {}
    for platform in platforms:
        if platform in plan and isinstance(plan[platform], dict) and "budget" in plan[platform]:
            normalized[platform] = {"budget": float(plan[platform]["budget"])}
        else:
            normalized[platform] = {"budget": round(payload.budget / len(platforms), 2)}

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REQUEST_COUNT.labels(status="success").inc()
    return AdsRunResponse(
        task_id=payload.task_id,
        provider="DeepSeek",
        model_name=DEEPSEEK_MODEL,
        ads_plan=normalized,
    )


@app.post("/internal/workers/ads/regenerate", response_model=AdsRunResponse)
def regenerate_ads(payload: RevisionRequest) -> AdsRunResponse:
    t0 = time.perf_counter()
    platforms = payload.platforms or ["facebook"]

    revised_prompt = (
        f"You are an expert digital marketing strategist.\n"
        f"Campaign objective: {payload.objective}\n"
        f"Total budget: ${payload.budget:.2f}\n"
        f"Target platforms: {', '.join(platforms)}\n\n"
        f"Note: The previous version was rejected. Reason: {payload.reject_reason}\n"
        "Please provide an improved strategy. Respond ONLY with valid JSON: "
        '{"<platform>": {"budget": <number>, "strategy": "<brief>"}, ...}.'
    )

    if not _has_real_key(DEEPSEEK_API_KEY):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail="DEEPSEEK_V3_API_KEY is required when WORKER_STRICT_REAL_MODE=true")
        normalized: dict[str, dict[str, float]] = {
            p: {"budget": round(payload.budget / len(platforms), 2)} for p in platforms
        }
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="stub").inc()
        return AdsRunResponse(
            task_id=payload.task_id,
            provider="DeepSeek",
            model_name=f"{DEEPSEEK_MODEL}-rev-stub",
            ads_plan=normalized,
        )

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
                    "messages": [{"role": "user", "content": revised_prompt}],
                    "response_format": {"type": "json_object"},
                    "thinking": {"type": "disabled"},
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            if usage and payload.company_id:
                _report_usage(payload.company_id, f"{DEEPSEEK_MODEL}-rev", "deepseek", usage)
    except Exception as exc:
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="error").inc()
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek ads regeneration failed: {exc}",
        ) from exc

    import json as _json

    try:
        plan = _json.loads(raw)
    except Exception:
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="error").inc()
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek returned non-JSON: {raw[:200]}",
        )

    normalized: dict[str, dict[str, float]] = {}
    for platform in platforms:
        if platform in plan and isinstance(plan[platform], dict) and "budget" in plan[platform]:
            normalized[platform] = {"budget": float(plan[platform]["budget"])}
        else:
            normalized[platform] = {"budget": round(payload.budget / len(platforms), 2)}

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REGENERATE_COUNT.labels(status="success").inc()
    return AdsRunResponse(
        task_id=payload.task_id,
        provider="DeepSeek",
        model_name=f"{DEEPSEEK_MODEL}-rev",
        ads_plan=normalized,
    )
