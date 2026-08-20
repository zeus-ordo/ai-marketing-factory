import os
import time
import json as _json
from urllib.parse import quote
from fastapi import FastAPI, HTTPException
import httpx
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .schemas import ImageRunRequest, ImageRunResponse, ImageAsset, RevisionRequest
from .prompt_utils import fit_minimax_prompt


REQUEST_COUNT = Counter(
    "worker_image_requests_total",
    "Total image generation requests",
    ["status"],
)
REQUEST_LATENCY = Histogram(
    "worker_image_request_latency_seconds",
    "Image generation latency",
    buckets=[1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)
STUB_MODE_COUNT = Counter(
    "worker_image_stub_mode_total",
    "Requests served in stub mode",
)
REGENERATE_COUNT = Counter(
    "worker_image_regenerate_total",
    "Image regeneration requests",
    ["status"],
)

app = FastAPI(
    title="Marketing AI Factory - Image Worker",
    version="0.1.0",
    description="Real image generation worker (Stability AI / MiniMax / Google AI Studio Gemini compatible).",
)

IMAGE_PROVIDER = os.getenv("IMAGE_WORKER_PROVIDER", "stability").strip().lower()
IMAGE_API_KEY = os.getenv("IMAGE_WORKER_API_KEY", "").strip()
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
IMAGE_API_BASE = os.getenv(
    "IMAGE_WORKER_API_BASE",
    "https://api.stability.ai/v1",
).strip()
IMAGE_ENGINE = os.getenv("IMAGE_WORKER_ENGINE", "stable-diffusion-xl-1024-v1-0")
MINIMAX_IMAGE_API_BASE = os.getenv("MINIMAX_IMAGE_API_BASE", "https://api.minimax.io").strip().rstrip("/")
MINIMAX_IMAGE_MODEL = os.getenv("MINIMAX_IMAGE_MODEL", "image-01").strip()
GEMINI_IMAGE_API_BASE = os.getenv("GEMINI_IMAGE_API_BASE", "https://generativelanguage.googleapis.com").strip().rstrip("/")
STRICT_REAL_MODE = os.getenv("WORKER_STRICT_REAL_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


def _has_real_key(value: str) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    return token.lower() not in {"replace-me", "changeme", "change_me", "your_api_key"}


def _active_provider() -> str:
    if IMAGE_PROVIDER in {"minimax", "stability", "gemini"}:
        return IMAGE_PROVIDER
    return "stability"


def _active_api_key() -> str:
    if _active_provider() == "minimax":
        return MINIMAX_API_KEY or IMAGE_API_KEY
    if _active_provider() == "gemini":
        return GEMINI_API_KEY
    return IMAGE_API_KEY


def _active_model_name(suffix: str = "") -> str:
    if _active_provider() == "minimax":
        return f"{MINIMAX_IMAGE_MODEL}{suffix}"
    if _active_provider() == "gemini":
        return f"gemini-3.1-flash-image{suffix}"
    return f"{IMAGE_ENGINE}{suffix}"


def _active_provider_name() -> str:
    if _active_provider() == "minimax":
        return "MiniMax"
    if _active_provider() == "gemini":
        return "Google AI Studio"
    return "StabilityAI"


def _missing_key_detail() -> str:
    if _active_provider() == "minimax":
        return "MINIMAX_API_KEY or IMAGE_WORKER_API_KEY is required when IMAGE_WORKER_PROVIDER=minimax and WORKER_STRICT_REAL_MODE=true"
    if _active_provider() == "gemini":
        return "GEMINI_API_KEY is required when IMAGE_WORKER_PROVIDER=gemini and WORKER_STRICT_REAL_MODE=true"
    return "IMAGE_WORKER_API_KEY is required when WORKER_STRICT_REAL_MODE=true"


def _fallback_svg_data_url(campaign_id: str, task_id: str, size: str, label: str = "Generated image") -> str:
    width, height = 1024, 1024
    if "x" in size:
        try:
            width_text, height_text = size.lower().split("x", 1)
            width = max(1, int(width_text))
            height = max(1, int(height_text))
        except Exception:
            width, height = 1024, 1024
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>
<defs><linearGradient id='g' x1='0' x2='1' y1='0' y2='1'><stop stop-color='#2563eb'/><stop offset='1' stop-color='#7c3aed'/></linearGradient></defs>
<rect width='100%' height='100%' rx='48' fill='url(#g)'/>
<circle cx='{width * 0.78:.0f}' cy='{height * 0.22:.0f}' r='{min(width, height) * 0.16:.0f}' fill='rgba(255,255,255,0.22)'/>
<text x='50%' y='45%' text-anchor='middle' font-family='Arial, sans-serif' font-size='{max(28, width // 18)}' font-weight='700' fill='white'>{label}</text>
<text x='50%' y='54%' text-anchor='middle' font-family='Arial, sans-serif' font-size='{max(16, width // 34)}' fill='rgba(255,255,255,0.86)'>{campaign_id}</text>
<text x='50%' y='61%' text-anchor='middle' font-family='Arial, sans-serif' font-size='{max(14, width // 42)}' fill='rgba(255,255,255,0.72)'>{task_id} · {size}</text>
</svg>"""
    return "data:image/svg+xml," + quote(svg, safe="/:#%?=&;,+")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/internal/workers/image/run", response_model=ImageRunResponse)
def run_image_worker(payload: ImageRunRequest) -> ImageRunResponse:
    t0 = time.perf_counter()
    assets: list[ImageAsset] = []

    api_key = _active_api_key()

    if not _has_real_key(api_key):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail=_missing_key_detail())
        for size in payload.sizes:
            assets.append(
                ImageAsset(
                    url=_fallback_svg_data_url(payload.campaign_id, payload.task_id, size, "Image preview"),
                    size=size,
                )
            )
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REQUEST_COUNT.labels(status="stub").inc()
        STUB_MODE_COUNT.inc()
        return ImageRunResponse(
            task_id=payload.task_id,
            provider=_active_provider_name(),
            model_name=_active_model_name("-stub"),
            image_assets=assets,
        )

    for size in payload.sizes:
        try:
            generated_url = _generate_image_asset_url(payload.prompt, size, api_key)
        except HTTPException:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise
        except Exception as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"Image generation failed ({size}): {exc}",
            ) from exc

        sanitized_size = size.replace("x", "_")
        assets.append(
            ImageAsset(
                url=generated_url or _fallback_svg_data_url(payload.campaign_id, payload.task_id, size, "Image preview"),
                size=size,
            )
        )

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REQUEST_COUNT.labels(status="success").inc()
    return ImageRunResponse(
        task_id=payload.task_id,
        provider=_active_provider_name(),
        model_name=_active_model_name(),
        image_assets=assets,
    )


@app.post("/internal/workers/image/regenerate", response_model=ImageRunResponse)
def regenerate_image(payload: RevisionRequest) -> ImageRunResponse:
    t0 = time.perf_counter()
    assets: list[ImageAsset] = []

    revised_prompt = (
        f"{payload.prompt}\n\n"
        f"Note: The previous version was rejected. Reason: {payload.reject_reason}\n"
        "Please generate an improved image."
    )

    api_key = _active_api_key()

    if not _has_real_key(api_key):
        if STRICT_REAL_MODE:
            raise HTTPException(status_code=503, detail=_missing_key_detail())
        for size in payload.sizes:
            assets.append(
                ImageAsset(
                    url=_fallback_svg_data_url(payload.campaign_id, payload.task_id, size, "Revised image"),
                    size=size,
                )
            )
        REQUEST_LATENCY.observe(time.perf_counter() - t0)
        REGENERATE_COUNT.labels(status="stub").inc()
        return ImageRunResponse(
            task_id=payload.task_id,
            provider=_active_provider_name(),
            model_name=_active_model_name("-rev-stub"),
            image_assets=assets,
        )

    for size in payload.sizes:
        try:
            generated_url = _generate_image_asset_url(revised_prompt, size, api_key)
        except HTTPException:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise
        except Exception as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"Image regeneration failed ({size}): {exc}",
            ) from exc

        sanitized_size = size.replace("x", "_")
        assets.append(
            ImageAsset(
                url=generated_url or _fallback_svg_data_url(payload.campaign_id, payload.task_id, size, "Revised image"),
                size=size,
            )
        )

    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REGENERATE_COUNT.labels(status="success").inc()
    return ImageRunResponse(
        task_id=payload.task_id,
        provider=_active_provider_name(),
        model_name=_active_model_name("-rev"),
        image_assets=assets,
    )


def _generate_image_asset_url(prompt: str, size: str, api_key: str) -> str | None:
    if _active_provider() == "minimax":
        return _generate_minimax_image(prompt, size, api_key)
    if _active_provider() == "gemini":
        return _generate_gemini_image(prompt, size, api_key)
    return _generate_stability_image(prompt, size, api_key)


def _generate_stability_image(prompt: str, size: str, api_key: str) -> str:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{IMAGE_API_BASE.rstrip('/')}/generation/{IMAGE_ENGINE}/text-to-image",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "text_prompts": [{"text": prompt}],
                "width": _parse_width(size),
                "height": _parse_height(size),
                "samples": 1,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    artifacts = data.get("artifacts", [])
    if not artifacts or not artifacts[0].get("base64"):
        raise HTTPException(
            status_code=502,
            detail=f"Image generation returned no usable Stability artifact for size {size}.",
        )
    base64_image = artifacts[0]["base64"]
    return f"data:image/png;base64,{base64_image}"


def _generate_minimax_image(prompt: str, size: str, api_key: str) -> str:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{MINIMAX_IMAGE_API_BASE}/v1/image_generation",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": MINIMAX_IMAGE_MODEL,
                "prompt": fit_minimax_prompt(prompt),
                "aspect_ratio": _size_to_aspect_ratio(size),
                "response_format": "url",
                "n": 1,
                "prompt_optimizer": True,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    base_resp = data.get("base_resp") or {}
    if base_resp.get("status_code") not in {None, 0, "0"}:
        raise HTTPException(
            status_code=502,
            detail=f"MiniMax image generation failed: {base_resp.get('status_msg', 'unknown error')}",
        )
    image_urls = (data.get("data") or {}).get("image_urls") or []
    if not image_urls:
        raise HTTPException(
            status_code=502,
            detail=f"Image generation returned no usable MiniMax URL for size {size}.",
        )
    return str(image_urls[0])


def _generate_gemini_image(prompt: str, size: str, api_key: str) -> str:
    aspect_ratio = _size_to_aspect_ratio(size)
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{GEMINI_IMAGE_API_BASE}/v1beta/interactions",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": "gemini-3.1-flash-image",
                "input": [{"type": "text", "text": prompt}],
                "response_format": {
                    "type": "image",
                    "aspect_ratio": aspect_ratio,
                    "image_size": "1K",
                },
            },
        )
    resp.raise_for_status()
    data = resp.json()
    image_data = ""
    mime_type = "image/png"
    for step in data.get("steps", []):
        for item in step.get("content", []):
            if isinstance(item, dict) and item.get("type") == "image" and item.get("data"):
                image_data = item["data"]
                mime_type = item.get("mime_type", "image/jpeg")
                break
        if image_data:
            break
    if not image_data:
        raise HTTPException(status_code=502, detail="Gemini image generation returned no image data")
    return f"data:{mime_type};base64,{image_data}"


def _parse_width(size: str) -> int:
    parts = size.lower().split("x")
    return int(parts[0]) if len(parts) == 2 else 1024


def _parse_height(size: str) -> int:
    parts = size.lower().split("x")
    return int(parts[1]) if len(parts) == 2 else 1024


def _size_to_aspect_ratio(size: str) -> str:
    width = _parse_width(size)
    height = _parse_height(size)
    if width <= 0 or height <= 0:
        return "1:1"
    ratio = width / height
    candidates = {
        "1:1": 1.0,
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "3:2": 3 / 2,
        "2:3": 2 / 3,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
        "21:9": 21 / 9,
    }
    return min(candidates, key=lambda key: abs(candidates[key] - ratio))
