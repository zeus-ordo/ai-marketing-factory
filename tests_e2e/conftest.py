"""
Pytest configuration for E2E tests.
Checks service availability at collection time and skips all tests if services aren't running.
"""

import os

import pytest


MEMBERSHIP_BASE = os.getenv("MEMBERSHIP_E2E_URL", "http://localhost:8095")
CAMPAIGN_BASE   = os.getenv("CAMPAIGN_E2E_URL",   "http://localhost:8080")


def check_service(url: str) -> bool:
    try:
        import httpx  # type: ignore
        r = httpx.Client(timeout=5.0).get(f"{url}/health")
        return r.status_code == 200
    except Exception:
        return False


membership_ok = check_service(MEMBERSHIP_BASE)
campaign_ok   = check_service(CAMPAIGN_BASE)

not_running_msg = (
    "E2E tests skipped: required services not running.\n"
    f"  Membership ({MEMBERSHIP_BASE}): {'OK' if membership_ok else 'NOT RUNNING'}\n"
    f"  Campaign   ({CAMPAIGN_BASE}):   {'OK' if campaign_ok else 'NOT RUNNING'}\n"
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
    if not (membership_ok and campaign_ok):
        skip_marker = pytest.mark.skip(not_running_msg)
        for item in items:
            item.add_marker(skip_marker)


@pytest.fixture(scope="module")
def http_client():
    if not membership_ok:
        pytest.skip(not_running_msg, allow_module_level=True)
    import httpx  # type: ignore
    return httpx.Client(base_url=MEMBERSHIP_BASE, timeout=15.0)


@pytest.fixture(scope="module")
def campaign_client():
    if not campaign_ok:
        pytest.skip(not_running_msg, allow_module_level=True)
    import httpx  # type: ignore
    return httpx.Client(base_url=CAMPAIGN_BASE, timeout=15.0)
