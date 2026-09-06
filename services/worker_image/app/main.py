import os
import time
import json as _json
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, TypeVar
from urllib.parse import quote, urlparse
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
MAX_PROVIDER_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 8.0
SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

T = TypeVar("T")


class ProviderError(Exception):
    def __init__(
        self,
        provider: str,
        status_code: int | None,
        retryable: bool,
        attempts: int,
        message: str,
        retry_after: float | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        self.attempts = attempts
        self.message = message
        self.retry_after = retry_after
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        status = f", status={self.status_code}" if self.status_code is not None else ""
        return (
            f"{self.message} (provider={self.provider}{status}, "
            f"retryable={self.retryable}, attempts={self.attempts})"
        )


def _retry_after(headers: object) -> float | None:
    try:
        value = headers.get("Retry-After")  # type: ignore[union-attr]
        if value is None:
            return None
        try:
            delay = float(value)
        except (TypeError, ValueError):
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            delay = retry_at.timestamp() - time.time()
        return min(MAX_RETRY_DELAY_SECONDS, max(0.0, delay))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _validate_image_asset(asset: object, *, provider: str, status_code: int) -> str:
    if not isinstance(asset, str) or not asset.strip():
        raise ProviderError(provider, status_code, True, 1, "Provider returned no usable image asset")
    value = asset.strip()
    if value.startswith("data:"):
        header, separator, payload = value.partition(",")
        mime_type = header[5:].split(";", 1)[0].lower()
        if not separator or not header.lower().endswith(";base64") or mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ProviderError(provider, status_code, True, 1, "Provider returned an invalid image data URL")
        try:
            if not payload or not base64.b64decode(payload, validate=True):
                raise ValueError
        except (ValueError, TypeError, base64.binascii.Error):
            raise ProviderError(provider, status_code, True, 1, "Provider returned an invalid image data URL")
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(character.isspace() for character in value):
        raise ProviderError(provider, status_code, True, 1, "Provider returned an invalid image URL")
    return value


def _request_with_retry(request_fn: Callable[[], T], *, provider: str, max_attempts: int = MAX_PROVIDER_ATTEMPTS) -> T:
    max_attempts = min(MAX_PROVIDER_ATTEMPTS, max(1, max_attempts))
    for attempt in range(1, max_attempts + 1):
        try:
            return request_fn()
        except ProviderError as exc:
            exc.attempts = attempt
            exc.args = (exc._format_message(),)
            if not exc.retryable or attempt >= max_attempts:
                raise
            delay = exc.retry_after if exc.retry_after is not None else min(
                MAX_RETRY_DELAY_SECONDS, 0.5 * (2 ** (attempt - 1))
            )
            time.sleep(delay)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            if attempt >= max_attempts:
                raise ProviderError(provider, None, True, attempt, "Provider request failed") from exc
            time.sleep(min(MAX_RETRY_DELAY_SECONDS, 0.5 * (2 ** (attempt - 1))))
    raise AssertionError("unreachable")


def _provider_response_error(provider: str, response: httpx.Response) -> ProviderError:
    status_code = response.status_code
    return ProviderError(
        provider,
        status_code,
        status_code == 429 or status_code in {500, 502, 503, 504},
        1,
        "Provider request returned an unsuccessful response",
        _retry_after(response.headers),
    )


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
            provider=payload.provider or _active_provider_name(),
            model_name=payload.model or _active_model_name("-stub"),
            image_assets=assets,
        )

    for size in payload.sizes:
        try:
            generated_url = _validate_image_asset(
                _generate_image_asset_url(payload.prompt, size, api_key),
                provider=_active_provider(),
                status_code=200,
            )
        except ProviderError as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except HTTPException:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise
        except Exception as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REQUEST_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"Image generation failed for size {size}",
            ) from exc

        assets.append(
            ImageAsset(
                url=generated_url,
                size=size,
            )
        )

    if not assets:
        raise HTTPException(status_code=502, detail="Provider returned no usable image assets")
    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REQUEST_COUNT.labels(status="success").inc()
    return ImageRunResponse(
        task_id=payload.task_id,
        provider=payload.provider or _active_provider_name(),
        model_name=payload.model or _active_model_name(),
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
            provider=payload.provider or _active_provider_name(),
            model_name=payload.model or _active_model_name("-rev-stub"),
            image_assets=assets,
        )

    for size in payload.sizes:
        try:
            generated_url = _validate_image_asset(
                _generate_image_asset_url(revised_prompt, size, api_key),
                provider=_active_provider(),
                status_code=200,
            )
        except ProviderError as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except HTTPException:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise
        except Exception as exc:
            REQUEST_LATENCY.observe(time.perf_counter() - t0)
            REGENERATE_COUNT.labels(status="error").inc()
            raise HTTPException(
                status_code=502,
                detail=f"Image regeneration failed for size {size}",
            ) from exc

        assets.append(
            ImageAsset(
                url=generated_url,
                size=size,
            )
        )

    if not assets:
        raise HTTPException(status_code=502, detail="Provider returned no usable image assets")
    REQUEST_LATENCY.observe(time.perf_counter() - t0)
    REGENERATE_COUNT.labels(status="success").inc()
    return ImageRunResponse(
        task_id=payload.task_id,
        provider=payload.provider or _active_provider_name(),
        model_name=payload.model or _active_model_name("-rev"),
        image_assets=assets,
    )


def _generate_image_asset_url(prompt: str, size: str, api_key: str) -> str:
    if _active_provider() == "minimax":
        return _generate_minimax_image(prompt, size, api_key)
    if _active_provider() == "gemini":
        return _generate_gemini_image(prompt, size, api_key)
    return _generate_stability_image(prompt, size, api_key)


def _generate_stability_image(prompt: str, size: str, api_key: str) -> str:
    with httpx.Client(timeout=120.0) as client:
        def request() -> str:
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
            if resp.status_code != 200:
                raise _provider_response_error("stability", resp)
            try:
                data = resp.json()
                artifacts = data.get("artifacts", [])
                base64_image = artifacts[0].get("base64") if artifacts else None
            except (AttributeError, IndexError, KeyError, TypeError, ValueError):
                base64_image = None
            if not base64_image:
                raise ProviderError("stability", resp.status_code, True, 1, "Provider returned no usable image asset")
            return _validate_image_asset(f"data:image/png;base64,{base64_image}", provider="stability", status_code=resp.status_code)

        return _request_with_retry(request, provider="stability")


def _generate_minimax_image(prompt: str, size: str, api_key: str) -> str:
    with httpx.Client(timeout=120.0) as client:
        def request() -> str:
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
            if resp.status_code != 200:
                raise _provider_response_error("minimax", resp)
            try:
                data = resp.json()
                base_resp = data.get("base_resp") or {}
                response_data = data.get("data") or {}
                image_urls = response_data.get("image_urls") or []
                if not isinstance(base_resp, dict) or not isinstance(response_data, dict) or not isinstance(image_urls, list):
                    raise TypeError
            except (AttributeError, KeyError, TypeError, ValueError):
                base_resp, image_urls = {}, []
            if base_resp.get("status_code") not in {None, 0, "0"} or not image_urls:
                raise ProviderError("minimax", resp.status_code, True, 1, "Provider returned no usable image asset")
            return _validate_image_asset(image_urls[0], provider="minimax", status_code=resp.status_code)

        return _request_with_retry(request, provider="minimax")


def _generate_gemini_image(prompt: str, size: str, api_key: str) -> str:
    aspect_ratio = _size_to_aspect_ratio(size)
    with httpx.Client(timeout=120.0) as client:
        def request() -> str:
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
            if resp.status_code != 200:
                raise _provider_response_error("gemini", resp)
            image_data = ""
            mime_type = "image/png"
            try:
                data = resp.json()
                for step in data.get("steps", []):
                    for item in step.get("content", []):
                        if isinstance(item, dict) and item.get("type") == "image" and isinstance(item.get("data"), str) and item["data"].strip():
                            image_data = item["data"]
                            mime_type = item.get("mime_type")
                            break
                    if image_data:
                        break
            except (AttributeError, KeyError, TypeError, ValueError):
                image_data = ""
            if not image_data or not isinstance(mime_type, str):
                raise ProviderError("gemini", resp.status_code, True, 1, "Provider returned no usable image asset")
            return _validate_image_asset(f"data:{mime_type};base64,{image_data}", provider="gemini", status_code=resp.status_code)

        return _request_with_retry(request, provider="gemini")


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
