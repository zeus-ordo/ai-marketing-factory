import logging
import os
import re
import shutil
import tempfile
import time
from urllib import request
from fastapi import FastAPI, HTTPException
import httpx
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .schemas import VideoRunRequest, VideoRunResponse, RevisionRequest

CAMPAIGN_SERVICE_URL = os.getenv("CAMPAIGN_SERVICE_URL", "http://campaign-service:8080").strip()
INTERNAL_API_KEY = (os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip() or os.getenv("INTERNAL_API_KEY", "").strip())


REQUEST_COUNT = Counter(
    "worker_video_requests_total",
    "Total video generation requests",
    ["status"],
)
REQUEST_LATENCY = Histogram(
    "worker_video_request_latency_seconds",
    "Video generation latency",
    buckets=[5.0, 10.0, 30.0, 60.0, 120.0, 180.0, 300.0],
)
STUB_MODE_COUNT = Counter(
    "worker_video_stub_mode_total",
    "Requests served in stub mode",
)
REGENERATE_COUNT = Counter(
    "worker_video_regenerate_total",
    "Video regeneration requests",
    ["status"],
)

app = FastAPI(
    title="Marketing AI Factory - Video Worker",
    version="0.1.0",
    description="Real video generation worker (MiniMax / Google AI Studio Veo compatible).",
)

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "").strip()
MINIMAX_API_BASE = os.getenv("MINIMAX_API_BASE", "https://api.minimax.io").strip().rstrip("/")
MINIMAX_VIDEO_MODEL = os.getenv("MINIMAX_VIDEO_MODEL", "MiniMax-Hailuo-2.3").strip()
MINIMAX_VIDEO_RESOLUTION = os.getenv("MINIMAX_VIDEO_RESOLUTION", "768P").strip()
STRICT_REAL_MODE = os.getenv("WORKER_STRICT_REAL_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
MINIMAX_VIDEO_POLL_INTERVAL_SECONDS = max(3, int(os.getenv("MINIMAX_VIDEO_POLL_INTERVAL_SECONDS", "10")))
MINIMAX_VIDEO_MAX_WAIT_SECONDS = max(30, int(os.getenv("MINIMAX_VIDEO_MAX_WAIT_SECONDS", "600")))

# Google AI Studio Veo
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
VEEO_API_BASE = os.getenv("VEEO_API_BASE", "https://generativelanguage.googleapis.com").strip().rstrip("/")
VEEO_VIDEO_MODEL = os.getenv("VEEO_VIDEO_MODEL", "veo-3.1-generate-preview").strip()
VIDEO_WORKER_PROVIDER = os.getenv("VIDEO_WORKER_PROVIDER", "minimax").strip().lower()
VEEO_POLL_INTERVAL_SECONDS = max(5, int(os.getenv("VEEO_POLL_INTERVAL_SECONDS", "10")))
VEEO_MAX_WAIT_SECONDS = max(30, int(os.getenv("VEEO_MAX_WAIT_SECONDS", "600")))
GENERATED_ASSETS_DIR = os.getenv("GENERATED_ASSETS_DIR", "/app/generated_assets")

logger = logging.getLogger("worker_video")


def _has_real_key(value: str) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    return token.lower() not in {"replace-me", "changeme", "change_me", "your_api_key"}


def _active_video_provider() -> str:
    if VIDEO_WORKER_PROVIDER == "veo":
        return "veo"
    return "minimax"


def _active_video_api_key() -> str:
    if _active_video_provider() == "veo":
        return GEMINI_API_KEY
    return MINIMAX_API_KEY


def _active_video_model() -> str:
    if _active_video_provider() == "veo":
        return VEEO_VIDEO_MODEL
    return MINIMAX_VIDEO_MODEL


def _active_video_provider_name() -> str:
    if _active_video_provider() == "veo":
        return "Google AI Studio"
    return "MiniMax"


def _report_usage(company_id: str, model: str, provider: str, usage: dict[str, int]) -> None:
    """Fire-and-forget report of LLM token usage to campaign service."""
    if not INTERNAL_API_KEY or not CAMPAIGN_SERVICE_URL:
        logger.warning(
            "worker_video: _report_usage skipped — INTERNAL_API_KEY or CAMPAIGN_SERVICE_URL not configured"
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
        logger.warning(f"worker_video: _report_usage failed: {exc}")


def _is_quota_or_plan_limit(message: str) -> bool:
    normalized = message.lower()
    return any(
        token in normalized
        for token in (
            "usage limit",
            "quota",
            "token plan",
            "purchase credits",
            "not in plan",
            "weekly usage limit",
        )
    )


def _quota_fallback_response(payload: VideoRunRequest | RevisionRequest, model_name: str, detail: str) -> VideoRunResponse:
    safe_detail = detail[:500]
    STUB_MODE_COUNT.inc()
    return VideoRunResponse(
        task_id=payload.task_id,
        provider="MiniMax",
        model_name=f"{model_name}-quota-fallback",
        video_url=f"minimax-quota://assets/{payload.campaign_id}/{payload.task_id}.mp4",
        thumbnail_url=f"minimax-quota://assets/{payload.campaign_id}/{payload.task_id}_thumb.png",
        fallback_reason="minimax_quota_or_plan_limit",
        fallback_detail=safe_detail,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/internal/workers/video/run", response_model=VideoRunResponse)
def run_video_worker(payload: VideoRunRequest) -> VideoRunResponse:
    t0 = time.perf_counter()
    provider = _active_video_provider()

    if provider == "veo":
        if not _has_real_key(GEMINI_API_KEY):
            if STRICT_REAL_MODE:
                raise HTTPException(status_code=503, detail="GEMINI_API_KEY is required when VIDEO_WORKER_PROVIDER=veo and WORKER_STRICT_REAL_MODE=true")
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="stub").inc()
            STUB_MODE_COUNT.inc()
            return VideoRunResponse(
                task_id=payload.task_id,
                provider="Google AI Studio",
                model_name=f"{VEEO_VIDEO_MODEL}-stub",
                video_url=f"stub://veo/{payload.campaign_id}/{payload.task_id}.mp4",
                thumbnail_url=f"stub://veo/{payload.campaign_id}/{payload.task_id}_thumb.png",
            )
        try:
            video_url, thumbnail_url = _generate_veo_video(
                task_id=payload.task_id,
                campaign_id=payload.campaign_id,
                company_id=payload.company_id,
                prompt=payload.prompt,
                duration=payload.duration,
                aspect_ratio=payload.aspect_ratio,
                api_key=GEMINI_API_KEY,
            )
        except HTTPException:
            raise
        except Exception as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise HTTPException(status_code=502, detail=f"Veo video generation failed: {exc}") from exc
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="success").inc()
        return VideoRunResponse(
            task_id=payload.task_id,
            provider="Google AI Studio",
            model_name=VEEO_VIDEO_MODEL,
            video_url=video_url,
            thumbnail_url=thumbnail_url,
        )

    # MiniMax path (unchanged)
    if not _has_real_key(MINIMAX_API_KEY):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail="MINIMAX_API_KEY is required when WORKER_STRICT_REAL_MODE=true")
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="stub").inc()
        STUB_MODE_COUNT.inc()
        return VideoRunResponse(
            task_id=payload.task_id,
            provider="MiniMax",
            model_name=f"{MINIMAX_VIDEO_MODEL}-stub",
            video_url=f"stub://assets/{payload.campaign_id}/{payload.task_id}.mp4",
            thumbnail_url=f"stub://assets/{payload.campaign_id}/{payload.task_id}_thumb.png",
        )

    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                _minimax_video_generation_url(),
                headers={
                    "Authorization": f"Bearer {MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MINIMAX_VIDEO_MODEL,
                    "prompt": payload.prompt,
                    "duration": _normalize_duration(payload.duration),
                    "resolution": MINIMAX_VIDEO_RESOLUTION,
                    "prompt_optimizer": True,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") not in {None, 0, "0"}:
            status_msg = str(base_resp.get("status_msg", "unknown error"))
            if _is_quota_or_plan_limit(status_msg):
                REQUEST_LATENCY.observe(time.perf_counter() - t0)
                REQUEST_COUNT.labels(status="quota_fallback").inc()
                return _quota_fallback_response(payload, MINIMAX_VIDEO_MODEL, status_msg)
            raise HTTPException(
                status_code=502,
                detail=f"MiniMax video generation failed: {status_msg}",
            )
        video_id = str(data.get("task_id") or data.get("video_id") or payload.task_id)
        video_url = str(data.get("video_url") or "").strip()
        thumbnail_url = str(data.get("thumbnail_url") or "").strip()
        if not _is_downloadable_url(video_url):
            video_url = _retrieve_minimax_video_download_url(video_id)
        if not thumbnail_url:
            thumbnail_url = video_url
        usage = data.get("usage", {})
        if usage and payload.company_id:
            _report_usage(payload.company_id, MINIMAX_VIDEO_MODEL, "minimax", usage)
    except Exception as exc:
        message = str(exc)
        if _is_quota_or_plan_limit(message):
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="quota_fallback").inc()
            return _quota_fallback_response(payload, MINIMAX_VIDEO_MODEL, message)
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="error").inc()
        raise HTTPException(
            status_code=502,
            detail=f"Video generation failed: {exc}",
        ) from exc

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REQUEST_COUNT.labels(status="success").inc()
    return VideoRunResponse(
        task_id=payload.task_id,
        provider="MiniMax",
        model_name=MINIMAX_VIDEO_MODEL,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
    )


@app.post("/internal/workers/video/regenerate", response_model=VideoRunResponse)
def regenerate_video(payload: RevisionRequest) -> VideoRunResponse:
    t0 = time.perf_counter()
    provider = _active_video_provider()

    revised_prompt = (
        f"{payload.prompt}\n\n"
        f"Note: The previous version was rejected. Reason: {payload.reject_reason}\n"
        "Please generate an improved video."
    )

    if provider == "veo":
        if not _has_real_key(GEMINI_API_KEY):
            if STRICT_REAL_MODE:
                raise HTTPException(status_code=503, detail="GEMINI_API_KEY is required when VIDEO_WORKER_PROVIDER=veo and WORKER_STRICT_REAL_MODE=true")
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="stub").inc()
            return VideoRunResponse(
                task_id=payload.task_id,
                provider="Google AI Studio",
                model_name=f"{VEEO_VIDEO_MODEL}-rev-stub",
                video_url=f"stub-rev://veo/{payload.campaign_id}/{payload.task_id}_rev.mp4",
                thumbnail_url=f"stub-rev://veo/{payload.campaign_id}/{payload.task_id}_rev_thumb.png",
            )
        try:
            video_url, thumbnail_url = _generate_veo_video(
                task_id=payload.task_id,
                campaign_id=payload.campaign_id,
                company_id=payload.company_id,
                prompt=revised_prompt,
                duration=payload.duration,
                aspect_ratio=payload.aspect_ratio,
                api_key=GEMINI_API_KEY,
            )
        except HTTPException:
            raise
        except Exception as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise HTTPException(status_code=502, detail=f"Veo video regeneration failed: {exc}") from exc
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="success").inc()
        return VideoRunResponse(
            task_id=payload.task_id,
            provider="Google AI Studio",
            model_name=f"{VEEO_VIDEO_MODEL}-rev",
            video_url=video_url,
            thumbnail_url=thumbnail_url,
        )

    # MiniMax path (unchanged)
    if not _has_real_key(MINIMAX_API_KEY):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail="MINIMAX_API_KEY is required when WORKER_STRICT_REAL_MODE=true")
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="stub").inc()
        return VideoRunResponse(
            task_id=payload.task_id,
            provider="MiniMax",
            model_name=f"{MINIMAX_VIDEO_MODEL}-rev-stub",
            video_url=f"stub-rev://assets/{payload.campaign_id}/{payload.task_id}_rev.mp4",
            thumbnail_url=f"stub-rev://assets/{payload.campaign_id}/{payload.task_id}_rev_thumb.png",
        )

    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                _minimax_video_generation_url(),
                headers={
                    "Authorization": f"Bearer {MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MINIMAX_VIDEO_MODEL,
                    "prompt": revised_prompt,
                    "duration": _normalize_duration(payload.duration),
                    "resolution": MINIMAX_VIDEO_RESOLUTION,
                    "prompt_optimizer": True,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") not in {None, 0, "0"}:
            status_msg = str(base_resp.get("status_msg", "unknown error"))
            if _is_quota_or_plan_limit(status_msg):
                REQUEST_LATENCY.observe(time.perf_counter() - t0)
                REGENERATE_COUNT.labels(status="quota_fallback").inc()
                return _quota_fallback_response(payload, f"{MINIMAX_VIDEO_MODEL}-rev", status_msg)
            raise HTTPException(
                status_code=502,
                detail=f"MiniMax video regeneration failed: {status_msg}",
            )
        video_id = str(data.get("task_id") or data.get("video_id") or f"{payload.task_id}_rev")
        video_url = str(data.get("video_url") or "").strip()
        thumbnail_url = str(data.get("thumbnail_url") or "").strip()
        if not _is_downloadable_url(video_url):
            video_url = _retrieve_minimax_video_download_url(video_id)
        if not thumbnail_url:
            thumbnail_url = video_url
        usage = data.get("usage", {})
        if usage and payload.company_id:
            _report_usage(payload.company_id, f"{MINIMAX_VIDEO_MODEL}-rev", "minimax", usage)
    except Exception as exc:
        message = str(exc)
        if _is_quota_or_plan_limit(message):
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="quota_fallback").inc()
            return _quota_fallback_response(payload, f"{MINIMAX_VIDEO_MODEL}-rev", message)
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="error").inc()
        raise HTTPException(
            status_code=502,
            detail=f"Video regeneration failed: {exc}",
        ) from exc

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REGENERATE_COUNT.labels(status="success").inc()
    return VideoRunResponse(
        task_id=payload.task_id,
        provider="MiniMax",
        model_name=f"{MINIMAX_VIDEO_MODEL}-rev",
        video_url=video_url,
        thumbnail_url=thumbnail_url,
    )


def _minimax_video_generation_url() -> str:
    if MINIMAX_API_BASE.endswith("/v1"):
        return f"{MINIMAX_API_BASE}/video_generation"
    return f"{MINIMAX_API_BASE}/v1/video_generation"


def _minimax_video_query_url() -> str:
    if MINIMAX_API_BASE.endswith("/v1"):
        return f"{MINIMAX_API_BASE}/query/video_generation"
    return f"{MINIMAX_API_BASE}/v1/query/video_generation"


def _minimax_file_retrieve_url() -> str:
    if MINIMAX_API_BASE.endswith("/v1"):
        return f"{MINIMAX_API_BASE}/files/retrieve"
    return f"{MINIMAX_API_BASE}/v1/files/retrieve"


def _is_downloadable_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _retrieve_minimax_video_download_url(task_id: str) -> str:
    deadline = time.monotonic() + MINIMAX_VIDEO_MAX_WAIT_SECONDS
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}"}
    last_status = "unknown"
    last_payload: dict | None = None

    with httpx.Client(timeout=60.0) as client:
        while time.monotonic() < deadline:
            time.sleep(MINIMAX_VIDEO_POLL_INTERVAL_SECONDS)
            resp = client.get(_minimax_video_query_url(), headers=headers, params={"task_id": task_id})
            resp.raise_for_status()
            payload = resp.json()
            last_payload = payload
            status = str(payload.get("status") or payload.get("Status") or "").strip()
            last_status = status or "unknown"
            normalized = last_status.lower()

            if normalized in {"success", "succeeded", "completed", "complete"}:
                file_id = str(payload.get("file_id") or payload.get("fileId") or "").strip()
                if not file_id:
                    raise HTTPException(status_code=502, detail=f"MiniMax video task succeeded without file_id: {payload}")
                file_resp = client.get(_minimax_file_retrieve_url(), headers=headers, params={"file_id": file_id})
                file_resp.raise_for_status()
                file_payload = file_resp.json()
                file_obj = file_payload.get("file") if isinstance(file_payload, dict) else None
                download_url = ""
                if isinstance(file_obj, dict):
                    download_url = str(file_obj.get("download_url") or file_obj.get("downloadUrl") or "").strip()
                if not download_url and isinstance(file_payload, dict):
                    download_url = str(file_payload.get("download_url") or file_payload.get("downloadUrl") or "").strip()
                if not _is_downloadable_url(download_url):
                    raise HTTPException(status_code=502, detail=f"MiniMax file retrieve returned no downloadable URL: {file_payload}")
                return download_url

            if normalized in {"fail", "failed", "error"}:
                detail = payload.get("error_message") or payload.get("error_msg") or payload.get("message") or payload
                raise HTTPException(status_code=502, detail=f"MiniMax video task failed: {detail}")

    raise HTTPException(
        status_code=504,
        detail=f"MiniMax video task did not complete within {MINIMAX_VIDEO_MAX_WAIT_SECONDS}s: task_id={task_id}, status={last_status}, payload={last_payload}",
    )


def _normalize_duration(duration: int) -> int:
    return 6


# ─── Veo (Google AI Studio) helpers ──────────────────────────────────────────


def _veo_generation_url() -> str:
    return f"{VEEO_API_BASE}/v1beta/models/{VEEO_VIDEO_MODEL}:predictLongRunning"


def _veo_operation_url(operation_name: str) -> str:
    return f"{VEEO_API_BASE}/v1beta/{operation_name}"


def _wait_for_veo_operation(operation_name: str, api_key: str) -> dict:
    deadline = time.monotonic() + VEEO_MAX_WAIT_SECONDS
    headers = {"x-goog-api-key": api_key}
    with httpx.Client(timeout=60.0) as client:
        while time.monotonic() < deadline:
            time.sleep(VEEO_POLL_INTERVAL_SECONDS)
            resp = client.get(_veo_operation_url(operation_name), headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("done"):
                return data
    raise HTTPException(status_code=504, detail=f"Veo operation did not complete within {VEEO_MAX_WAIT_SECONDS}s: {operation_name}")


def _download_veo_video(video_uri: str, api_key: str, target_path: str) -> None:
    headers = {"x-goog-api-key": api_key}
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        resp = client.get(video_uri, headers=headers)
        resp.raise_for_status()
        with open(target_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)


def _generate_veo_video(
    *,
    task_id: str,
    campaign_id: str,
    company_id: str,
    prompt: str,
    duration: int,
    aspect_ratio: str,
    api_key: str,
) -> tuple[str, str]:
    """Generate video via Veo, save to generated_assets, return (video_url, thumbnail_url)."""
    resolution_map = {"720p": "720p", "1080p": "1080p", "4k": "4k", "768P": "720p"}
    resolution = resolution_map.get(MINIMAX_VIDEO_RESOLUTION.upper().replace("P", "p"), "720p")

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            _veo_generation_url(),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "aspectRatio": aspect_ratio,
                    "resolution": resolution,
                },
            },
        )
    resp.raise_for_status()
    data = resp.json()
    operation_name = data.get("name", "").strip()
    if not operation_name:
        raise HTTPException(status_code=502, detail=f"Veo did not return operation name: {data}")

    operation_data = _wait_for_veo_operation(operation_name, api_key)
    if not operation_data.get("done"):
        raise HTTPException(status_code=504, detail=f"Veo operation returned done=false: {operation_name}")

    resp_data = operation_data.get("response", {})
    generated = resp_data.get("generateVideoResponse", {}).get("generatedSamples", [{}])
    video_info = generated[0] if generated else {}
    video_uri = video_info.get("video", {}).get("uri", "").strip()
    if not video_uri:
        raise HTTPException(status_code=502, detail=f"Veo operation completed but returned no video URI: {operation_data}")

    safe_company = re.sub(r"[^A-Za-z0-9._-]+", "_", company_id or "unknown_company").strip("._") or "unknown_company"
    safe_campaign = re.sub(r"[^A-Za-z0-9._-]+", "_", campaign_id).strip("._") or campaign_id
    target_dir = os.path.join(GENERATED_ASSETS_DIR, safe_company, safe_campaign)
    os.makedirs(target_dir, exist_ok=True)
    safe_task = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._") or task_id
    target_path = os.path.abspath(os.path.join(target_dir, f"{safe_task}.mp4"))
    if not target_path.startswith(os.path.abspath(target_dir)):
        raise HTTPException(status_code=500, detail="Invalid video target path")
    _download_veo_video(video_uri, api_key, target_path)

    video_url = f"file://{target_path}"
    thumbnail_url = f"file://{target_path}"
    return video_url, thumbnail_url
