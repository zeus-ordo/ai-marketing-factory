import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
sys.path.insert(0, str(Path(__file__).parent))

from app.persistence import PostgresPersistence
from app.schemas import ImageAnalysisRecord


pytestmark = pytest.mark.skipif(
    not os.getenv("CAMPAIGN_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL fixture",
)


@pytest.fixture
def persistence():
    value = PostgresPersistence(os.environ["CAMPAIGN_TEST_DATABASE_URL"])
    value.initialize()
    item_id = f"image-analysis-test-{uuid4().hex}"
    value.create_knowledge_item(
        {
            "item_id": item_id,
            "company_id": "company-1",
            "title": "Food image",
            "source": "manual",
            "description": "A food reference",
            "metadata": {"industry": "food"},
            "created_at": __import__("datetime").datetime.utcnow(),
        }
    )
    yield value, item_id
    with value._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM knowledge_items WHERE item_id = %s", (item_id,))
        conn.commit()


def test_new_analysis_starts_pending(persistence):
    store, item_id = persistence

    row = store.create_image_analysis(item_id, "image-rag-v1")

    assert row["analysis_status"] == "pending"
    assert row["analysis_version"] == "image-rag-v1"
    assert row["attempt_count"] == 0


def test_claim_complete_and_get_analysis(persistence):
    store, item_id = persistence
    store.create_image_analysis(item_id, "image-rag-v1")

    assert store.claim_image_analysis(item_id, "image-rag-v1") is True
    row = store.complete_image_analysis(
        item_id,
        "image-rag-v1",
        {"style": ["warm"], "objects": ["bowl"]},
        [0.1, 0.2],
        "embedding-v1",
    )

    assert row["analysis_status"] == "ready"
    assert row["embedding_status"] == "ready"
    assert row["embedding_dimension"] == 2
    assert store.get_image_analysis(item_id)["attributes"]["style"] == ["warm"]


def test_ready_listing_excludes_pending_and_failed(persistence):
    store, item_id = persistence
    pending_id = f"pending-{uuid4().hex}"
    failed_id = f"failed-{uuid4().hex}"
    for current_id in (pending_id, failed_id):
        store.create_knowledge_item(
            {
                "item_id": current_id,
                "company_id": "company-1",
                "title": current_id,
                "source": "manual",
                "metadata": {"industry": "food"},
                "created_at": __import__("datetime").datetime.utcnow(),
            }
        )
        store.create_image_analysis(current_id, "image-rag-v1")
    store.claim_image_analysis(failed_id, "image-rag-v1")
    store.fail_image_analysis(failed_id, "image-rag-v1", "PROVIDER_ERROR", "retry")

    assert store.list_ready_image_analysis("company-1", "food", 20) == []


def test_image_analysis_record_has_internal_fields():
    record = ImageAnalysisRecord(
        item_id="item-1",
        analysis_status="pending",
        analysis_version="image-rag-v1",
        attributes={},
        embedding_status="pending",
        attempt_count=0,
        analyzed_at=None,
        updated_at=__import__("datetime").datetime.utcnow(),
    )

    assert record.item_id == "item-1"
