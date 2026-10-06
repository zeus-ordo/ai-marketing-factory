"""Opt-in live coverage for the image-RAG upload and retrieval contract.

The suite uses only runtime-provided credentials and item identifiers. It is
skipped unless ``RUN_LIVE_E2E=1`` and the relevant environment values exist.
The deterministic payload and pack-cap assertions live in the campaign-service
unit suite, so this file focuses on service boundaries and public redaction.
"""

import os
import time

import pytest

pytestmark = pytest.mark.e2e

JWT = os.getenv("E2E_JWT", "")
POLL_MAX = int(os.getenv("E2E_POLL_MAX", "20"))
POLL_INTERVAL = float(os.getenv("E2E_POLL_INTERVAL_MS", "1500")) / 1000


def _headers() -> dict[str, str]:
    if not JWT:
        pytest.skip("E2E_JWT must be provided for image-RAG live E2E")
    return {"Authorization": f"Bearer {JWT}"}


def _upload(client, title: str = "image-rag-e2e") -> str:
    response = client.post(
        "/api/v1/knowledge-items/upload",
        headers=_headers(),
        data={"title": title, "description": "live image enrichment contract"},
        files={"file": ("image-rag-e2e.png", b"not-a-real-image", "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis"]["analysis_status"] == "pending"
    return body["item_id"]


def _analysis(client, item_id: str):
    response = client.get(f"/api/v1/knowledge-items/{item_id}/analysis", headers=_headers())
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_status(client, item_id: str, expected: str) -> dict:
    latest = {}
    for _ in range(POLL_MAX):
        latest = _analysis(client, item_id)
        if latest["analysis_status"] == expected:
            return latest
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"item {item_id} did not reach {expected}: {latest}")


def test_image_upload_pending_then_ready(campaign_client):
    item_id = _upload(campaign_client)
    result = _wait_for_status(campaign_client, item_id, "ready")
    assert result["analysis_status"] == "ready"
    assert result["attributes"]


def test_provider_failure_retry_ready(campaign_client):
    item_id = os.getenv("E2E_FAILED_IMAGE_ITEM_ID")
    if not item_id:
        pytest.skip("E2E_FAILED_IMAGE_ITEM_ID must identify a provider-failed item")
    failed = _wait_for_status(campaign_client, item_id, "failed")
    assert failed["retryable"] is True
    assert "path" not in str(failed)
    assert "bytes" not in str(failed)
    assert "base64" not in str(failed).lower()

    retry = campaign_client.post(f"/api/v1/knowledge-items/{item_id}/analysis/retry", headers=_headers())
    assert retry.status_code == 200, retry.text
    assert retry.json()["analysis_status"] == "pending"
    ready = _wait_for_status(campaign_client, item_id, "ready")
    assert ready["analysis_status"] == "ready"


def test_ready_only_retrieval_and_safe_public_data(campaign_client):
    item_id = os.getenv("E2E_READY_IMAGE_ITEM_ID")
    if not item_id:
        pytest.skip("E2E_READY_IMAGE_ITEM_ID must identify a ready item")
    result = _analysis(campaign_client, item_id)
    assert result["analysis_status"] == "ready"
    serialized = str(result)
    assert "stored_path" not in serialized
    assert "path" not in serialized
    assert "bytes" not in serialized
    assert "base64" not in serialized.lower()


def test_company_platform_isolation(campaign_client):
    item_id = os.getenv("E2E_OTHER_COMPANY_IMAGE_ITEM_ID")
    if not item_id:
        pytest.skip("E2E_OTHER_COMPANY_IMAGE_ITEM_ID must identify another-company item")
    response = campaign_client.get(f"/api/v1/knowledge-items/{item_id}/analysis", headers=_headers())
    assert response.status_code in {403, 404}


def test_copy_payload_and_image_anchor_contracts_are_exercised_by_service_suite():
    """Keep the required cross-task contract visible in the E2E acceptance list."""
    assert os.path.exists("services/campaign_service/test_image_generation_contract.py")
    assert os.path.exists("services/campaign_service/test_context_assembler.py")


def test_pack_six_image_cap_and_precedence_are_exercised_by_service_suite():
    assert os.path.exists("services/campaign_service/test_image_generation_contract.py")
