"""
End-to-end test for company isolation across membership and campaign services.

Requires both services to be running:
  - Membership service: http://localhost:8095
  - Campaign service:   http://localhost:8080

Run with: pytest tests_e2e/ -v -s
If services are not running, tests are SKIPPED automatically with clear instructions.

Prerequisites:
  1. Start membership: cd services/membership_service && python -m uvicorn app.main:app --port 8095
  2. Start campaign:   cd services/campaign_service   && python -m uvicorn app.main:app --port 8080
  3. PostgreSQL running for membership service
  4. Env vars: JWT_SECRET=dev-secret-key-for-testing-only
              PLATFORM_ADMIN_KEY=dev-platform-admin-key-change-me
"""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

PLATFORM_KEY = os.getenv("PLATFORM_ADMIN_KEY", "dev-platform-admin-key-change-me")
JWT_SECRET  = os.getenv("JWT_SECRET",          "dev-secret-key-for-testing-only")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_jwt(member_id: str, company_id: str, email: str = "test@example.com") -> str:
    """Create a valid JWT for the campaign service (HS256, matching JWT_SECRET)."""
    import jwt as _jwt
    now = datetime.now(timezone.utc)
    payload = {
        "sub": member_id,
        "company_id": company_id,
        "email": email,
        "permissions": ["campaign:read", "campaign:create", "campaign:run"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return _jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ─── Fixtures (provided by conftest.py) ────────────────────────────────────────
# http_client     → httpx.Client for membership service (base: MEMBERSHIP_BASE)
# campaign_client → httpx.Client for campaign service (base: CAMPAIGN_BASE)

@pytest.fixture
def platform_headers() -> dict:
    return {"X-Platform-Key": PLATFORM_KEY}


# ─── Test Cases ───────────────────────────────────────────────────────────────

class TestCompanyIsolationE2E:
    """
    Full flow: create company → create admin → login → get JWT
               → create campaign A → verify only A's campaigns visible
               → create campaign B (different company) → verify cross-company isolation
    """

    def test_full_company_isolation_flow(self, http_client, campaign_client, platform_headers) -> None:
        # ── Step 1: Create two companies via platform admin ──────────────────
        ts = int(time.time())
        company_a_name = f"TestCo-A-{ts}"
        company_b_name = f"TestCo-B-{ts}"

        resp_a = http_client.post(
            "/api/v1/platform/companies",
            json={"name": company_a_name, "slug": f"testco-a-{ts}"},
            headers=platform_headers,
        )
        assert resp_a.status_code == 201, f"Failed to create company A: {resp_a.text}"
        company_a_id = resp_a.json()["company_id"]

        resp_b = http_client.post(
            "/api/v1/platform/companies",
            json={"name": company_b_name, "slug": f"testco-b-{ts}"},
            headers=platform_headers,
        )
        assert resp_b.status_code == 201, f"Failed to create company B: {resp_b.text}"
        company_b_id = resp_b.json()["company_id"]

        print(f"\n[*] Created companies: A={company_a_id}, B={company_b_id}")

        # ── Step 2: Create admin accounts for each company ─────────────────
        admin_a_email = f"admin-a-{ts}@test.example.com"
        admin_b_email = f"admin-b-{ts}@test.example.com"

        resp_a_admin = http_client.post(
            f"/api/v1/platform/companies/{company_a_id}/admin",
            json={"email": admin_a_email, "password": "TestPass1234"},
            headers=platform_headers,
        )
        assert resp_a_admin.status_code == 201, f"Failed to create admin A: {resp_a_admin.text}"

        resp_b_admin = http_client.post(
            f"/api/v1/platform/companies/{company_b_id}/admin",
            json={"email": admin_b_email, "password": "TestPass1234"},
            headers=platform_headers,
        )
        assert resp_b_admin.status_code == 201, f"Failed to create admin B: {resp_b_admin.text}"

        print(f"[*] Created admins: A={admin_a_email}, B={admin_b_email}")

        # ── Step 3: Login as admin A to get JWT ─────────────────────────────
        resp_login_a = http_client.post(
            "/api/v1/auth/login",
            json={"email": admin_a_email, "password": "TestPass1234"},
        )
        assert resp_login_a.status_code == 200, f"Login A failed: {resp_login_a.text}"
        jwt_a = resp_login_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {jwt_a}"}

        resp_login_b = http_client.post(
            "/api/v1/auth/login",
            json={"email": admin_b_email, "password": "TestPass1234"},
        )
        assert resp_login_b.status_code == 200, f"Login B failed: {resp_login_b.text}"
        jwt_b = resp_login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {jwt_b}"}

        print(f"[*] Logged in both admins, got JWTs")

        # ── Step 4: Each admin creates a campaign ───────────────────────────
        campaign_brief = {
            "campaign_name": "Test Campaign",
            "product_name": "Test Product",
            "objective": "Brand awareness",
            "target_audience": {
                "age_range": "25-40",
                "gender": "all",
                "persona": "young professionals",
            },
            "platforms": ["instagram", "facebook"],
            "budget": 10000.0,
            "brand_tone": ["friendly"],
            "deliverables": {"copy_variants": 3, "image_assets": 2, "short_video_assets": 1},
            "deadline": "2026-12-31T00:00:00",
        }

        resp_camp_a = campaign_client.post(
            "/api/v1/campaigns",
            json={**campaign_brief, "campaign_name": "Campaign from Company A"},
            headers=headers_a,
        )
        assert resp_camp_a.status_code == 200, f"Create campaign A failed: {resp_camp_a.text}"
        campaign_a_id = resp_camp_a.json()["campaign_id"]

        resp_camp_b = campaign_client.post(
            "/api/v1/campaigns",
            json={**campaign_brief, "campaign_name": "Campaign from Company B"},
            headers=headers_b,
        )
        assert resp_camp_b.status_code == 200, f"Create campaign B failed: {resp_camp_b.text}"
        campaign_b_id = resp_camp_b.json()["campaign_id"]

        print(f"[*] Created campaigns: A={campaign_a_id}, B={campaign_b_id}")

        # ── Step 5: Verify company A sees only its own campaign ─────────────
        resp_list_a = campaign_client.get("/api/v1/campaigns", headers=headers_a)
        assert resp_list_a.status_code == 200, f"List campaigns A failed: {resp_list_a.text}"
        list_a = resp_list_a.json()["items"]
        assert len(list_a) == 1, f"Company A should see 1 campaign, saw {len(list_a)}"
        assert list_a[0]["campaign_id"] == campaign_a_id
        assert list_a[0]["company_id"] == company_a_id
        print(f"[*] Company A sees only its own campaign ({campaign_a_id})")

        # ── Step 6: Verify company B sees only its own campaign ─────────────
        resp_list_b = campaign_client.get("/api/v1/campaigns", headers=headers_b)
        assert resp_list_b.status_code == 200, f"List campaigns B failed: {resp_list_b.text}"
        list_b = resp_list_b.json()["items"]
        assert len(list_b) == 1, f"Company B should see 1 campaign, saw {len(list_b)}"
        assert list_b[0]["campaign_id"] == campaign_b_id
        assert list_b[0]["company_id"] == company_b_id
        print(f"[*] Company B sees only its own campaign ({campaign_b_id})")

        # ── Step 7: Company A cannot GET company B's campaign ───────────────
        resp_cross_get = campaign_client.get(
            f"/api/v1/campaigns/{campaign_b_id}",
            headers=headers_a,
        )
        assert resp_cross_get.status_code == 403, (
            f"Cross-company GET should return 403, got {resp_cross_get.status_code}"
        )
        print(f"[*] Company A correctly denied GET on Company B's campaign (403)")

        # ── Step 8: Company A cannot RUN company B's campaign ───────────────
        resp_cross_run = campaign_client.post(
            f"/api/v1/campaigns/{campaign_b_id}/run",
            headers=headers_a,
        )
        assert resp_cross_run.status_code == 403, (
            f"Cross-company RUN should return 403, got {resp_cross_run.status_code}"
        )
        print(f"[*] Company A correctly denied RUN on Company B's campaign (403)")

        # ── Step 9: Platform admin bypasses isolation ───────────────────────
        resp_admin_list = campaign_client.get(
            "/api/v1/campaigns",
            headers=platform_headers,
        )
        assert resp_admin_list.status_code == 200
        admin_items = resp_admin_list.json()["items"]
        assert len(admin_items) >= 2, f"Platform admin should see ≥2 campaigns, saw {len(admin_items)}"
        company_ids = {c["company_id"] for c in admin_items}
        assert company_a_id in company_ids and company_b_id in company_ids
        print(f"[*] Platform admin sees all campaigns across companies ({len(admin_items)} total)")

        print("\n[*] Full company isolation E2E flow passed!")


class TestPlatformAdminAuditLogE2E:
    """Verify audit logs capture admin actions correctly."""

    def test_audit_log_shows_company_creation(self, http_client, platform_headers) -> None:
        ts = int(time.time())
        company_name = f"AuditTestCo-{ts}"
        slug = f"audit-test-{ts}"

        resp = http_client.post(
            "/api/v1/platform/companies",
            json={"name": company_name, "slug": slug},
            headers=platform_headers,
        )
        assert resp.status_code == 201, f"Create company failed: {resp.text}"
        company_id = resp.json()["company_id"]

        # Give the service a moment to write the audit log
        time.sleep(0.5)

        # Verify the creation appears in audit logs
        resp_logs = http_client.get(
            "/api/v1/platform/audit-logs",
            params={"company_id": company_id},
            headers=platform_headers,
        )
        assert resp_logs.status_code == 200, f"Get audit logs failed: {resp_logs.text}"
        logs = resp_logs.json()["items"]

        # The "create_company" action should appear for this company
        create_logs = [
            l for l in logs
            if "create" in l["action"].lower() and str(company_id) in str(l.values())
        ]
        assert len(create_logs) >= 1, f"Expected audit log for company creation, got: {logs}"

        print(f"[*] Audit log captured company creation: {create_logs[0]['action']}")


class TestCampaignServiceJWTTypes:
    """Verify JWT claims are correctly used for company isolation (no membership service needed)."""

    def test_jwt_company_id_is_respected(self, campaign_client) -> None:
        """Even with a valid JWT, wrong company_id cannot access other campaigns."""
        # Company-x creates a campaign
        jwt_x = make_jwt("member-x", "company-x", "x@test.com")
        resp = campaign_client.post(
            "/api/v1/campaigns",
            json={
                "campaign_name": "Isolation Test Campaign",
                "product_name": "Product",
                "objective": "Awareness",
                "target_audience": {"age_range": "20-30", "gender": "all", "persona": "test"},
                "platforms": ["instagram"],
                "budget": 5000.0,
                "brand_tone": ["casual"],
                "deliverables": {"copy_variants": 1, "image_assets": 1, "short_video_assets": 0},
                "deadline": "2026-12-31T00:00:00",
            },
            headers={"Authorization": f"Bearer {jwt_x}"},
        )
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        campaign_x_id = resp.json()["campaign_id"]

        # Company-y cannot access company-x's campaign
        jwt_y = make_jwt("member-y", "company-y", "y@test.com")
        resp_403 = campaign_client.get(
            f"/api/v1/campaigns/{campaign_x_id}",
            headers={"Authorization": f"Bearer {jwt_y}"},
        )
        assert resp_403.status_code == 403, f"Expected 403, got {resp_403.status_code}"

        print(f"[*] JWT company_id correctly enforced in access control")
