"""Pytest configuration for explicit live E2E tests.

Offline acceptance tests do not use these fixtures. Live tests are opt-in via
RUN_LIVE_E2E=1 and never trigger network probes during collection.
"""

import os

import pytest


MEMBERSHIP_BASE = os.getenv("MEMBERSHIP_E2E_URL", "http://localhost:8095")
CAMPAIGN_BASE = os.getenv("CAMPAIGN_E2E_URL", "http://localhost:8080")
LIVE_E2E_ENABLED = os.getenv("RUN_LIVE_E2E", "0") == "1"

not_running_msg = (
    "E2E tests skipped: required services not running.\n"
    "  Live services were not enabled (set RUN_LIVE_E2E=1 after starting them).\n"
    "\n"
    "To run E2E tests, start both services:\n"
    "  membership: cd services/membership_service && python -m uvicorn app.main:app --port 8095\n"
    "  campaign:   cd services/campaign_service   && python -m uvicorn app.main:app --port 8080\n"
    "\n"
    "Also ensure PostgreSQL is running for membership service and set:\n"
    "  JWT_SECRET=dev-secret-key-for-testing-only\n"
    "  PLATFORM_ADMIN_KEY=dev-platform-admin-key-change-me\n"
    "in both services' environments."
)


def pytest_configure(config: pytest.Config) -> None:
    """Register custom marker so skip reason is always visible in output."""
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring live services")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if not LIVE_E2E_ENABLED:
        skip_marker = pytest.mark.skip(not_running_msg)
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_marker)


@pytest.fixture(scope="module")
def http_client():
    if not LIVE_E2E_ENABLED:
        pytest.skip(not_running_msg, allow_module_level=True)
    import httpx  # type: ignore
    return httpx.Client(base_url=MEMBERSHIP_BASE, timeout=15.0)


@pytest.fixture(scope="module")
def campaign_client():
    if not LIVE_E2E_ENABLED:
        pytest.skip(not_running_msg, allow_module_level=True)
    import httpx  # type: ignore
    return httpx.Client(base_url=CAMPAIGN_BASE, timeout=15.0)
