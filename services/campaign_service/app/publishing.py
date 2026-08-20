import os
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel


class PublishPlatform(str, Enum):
    FACEBOOK = "facebook"
    GOOGLE_ADS = "google_ads"
    TIKTOK = "tiktok"


class PublishTarget(BaseModel):
    platform: PublishPlatform
    asset_id: str
    enabled: bool = True


class PublishRequest(BaseModel):
    targets: list[PublishTarget]
    operator: str | None = None


class PublishResult(BaseModel):
    platform: str
    status: str
    detail: str | None = None
    published_url: str | None = None


class PublishResponse(BaseModel):
    campaign_id: str
    results: list[PublishResult]


PlatformAdapter = Callable[[str, str, dict[str, Any] | None], PublishResult]
PLATFORM_ADAPTERS: dict[str, PlatformAdapter] = {}


def register_platform_adapter(platform: str, adapter: PlatformAdapter) -> None:
    PLATFORM_ADAPTERS[platform] = adapter


def _placeholder_or_empty(value: str) -> bool:
    token = (value or "").strip().lower()
    return token in {"", "replace-me", "change-me", "change_me", "your_api_key"}


def _stub_result(platform: str, asset_id: str, reason: str) -> PublishResult:
    return PublishResult(
        platform=platform,
        status="published",
        detail=f"Stub mode ({reason})",
        published_url=f"https://{platform}.com/ads/stub/{asset_id}",
    )


def _real_mode_enabled() -> bool:
    return os.getenv("PUBLISHING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def facebook_adapter(campaign_id: str, asset_id: str, context: dict[str, Any] | None = None) -> PublishResult:
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    account_id = os.getenv("META_AD_ACCOUNT_ID", "").strip()
    if not _real_mode_enabled() or _placeholder_or_empty(token) or _placeholder_or_empty(account_id):
        return _stub_result("facebook", asset_id, "missing credentials or disabled")

    # Real integration placeholder path; keeps interface stable until credentials are provided.
    return PublishResult(
        platform="facebook",
        status="queued",
        detail="Credentials detected. Real adapter skeleton ready; execution enabled in key-integration phase.",
        published_url=f"meta://{account_id}/{campaign_id}/{asset_id}",
    )


def google_ads_adapter(campaign_id: str, asset_id: str, context: dict[str, Any] | None = None) -> PublishResult:
    developer_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
    customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "").strip()
    if not _real_mode_enabled() or _placeholder_or_empty(developer_token) or _placeholder_or_empty(customer_id):
        return _stub_result("google_ads", asset_id, "missing credentials or disabled")

    return PublishResult(
        platform="google_ads",
        status="queued",
        detail="Credentials detected. Real adapter skeleton ready; execution enabled in key-integration phase.",
        published_url=f"googleads://{customer_id}/{campaign_id}/{asset_id}",
    )


def tiktok_adapter(campaign_id: str, asset_id: str, context: dict[str, Any] | None = None) -> PublishResult:
    app_id = os.getenv("TIKTOK_ADS_APP_ID", "").strip()
    secret = os.getenv("TIKTOK_ADS_APP_SECRET", "").strip()
    if not _real_mode_enabled() or _placeholder_or_empty(app_id) or _placeholder_or_empty(secret):
        return _stub_result("tiktok", asset_id, "missing credentials or disabled")

    return PublishResult(
        platform="tiktok",
        status="queued",
        detail="Credentials detected. Real adapter skeleton ready; execution enabled in key-integration phase.",
        published_url=f"tiktok://{app_id}/{campaign_id}/{asset_id}",
    )


register_platform_adapter(PublishPlatform.FACEBOOK.value, facebook_adapter)
register_platform_adapter(PublishPlatform.GOOGLE_ADS.value, google_ads_adapter)
register_platform_adapter(PublishPlatform.TIKTOK.value, tiktok_adapter)


def dispatch_publish(campaign_id: str, targets: list[PublishTarget]) -> list[PublishResult]:
    results: list[PublishResult] = []
    for target in targets:
        platform = target.platform.value
        if not target.enabled:
            results.append(PublishResult(platform=platform, status="skipped", detail="Disabled"))
            continue

        adapter = PLATFORM_ADAPTERS.get(platform)
        if adapter is None:
            results.append(PublishResult(platform=platform, status="skipped", detail="No adapter registered"))
            continue

        try:
            result = adapter(campaign_id, target.asset_id, None)
            results.append(result)
        except Exception as exc:
            results.append(PublishResult(platform=platform, status="failed", detail=str(exc)))
    return results
