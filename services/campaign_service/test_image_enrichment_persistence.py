import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
sys.path.insert(0, str(Path(__file__).parent))

from app.persistence import PostgresPersistence
from app.image_enrichment import validate_image_attributes
from app.schemas import ImageAnalysisRecord, KnowledgeItemAnalysisSummary


@pytest.fixture
def persistence():
    if not os.getenv("CAMPAIGN_TEST_DATABASE_URL"):
        pytest.skip("requires disposable PostgreSQL fixture")
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
            "created_at": datetime.utcnow(),
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
    ready_id = f"ready-{uuid4().hex}"
    for current_id in (pending_id, failed_id, ready_id):
        store.create_knowledge_item(
            {
                "item_id": current_id,
                "company_id": "company-1",
                "title": current_id,
                "source": "manual",
                "metadata": {"industry": "food"},
                "created_at": datetime.utcnow(),
            }
        )
        store.create_image_analysis(current_id, "image-rag-v1")
    store.claim_image_analysis(failed_id, "image-rag-v1")
    store.fail_image_analysis(failed_id, "image-rag-v1", "PROVIDER_ERROR", "retry")
    store.claim_image_analysis(ready_id, "image-rag-v1")
    store.complete_image_analysis(ready_id, "image-rag-v1", {"style": ["warm"]}, [0.1], "embedding-v1")

    rows = store.list_ready_image_analysis("company-1", "food", 20)
    assert [row["item_id"] for row in rows] == [ready_id]
    assert rows[0]["attributes"] == {"style": ["warm"]}


def test_image_analysis_record_has_internal_fields():
    record = ImageAnalysisRecord(
        item_id="item-1",
        analysis_status="pending",
        analysis_version="image-rag-v1",
        attributes={},
        embedding_status="pending",
        attempt_count=0,
        analyzed_at=None,
        updated_at=datetime.utcnow(),
    )

    assert record.item_id == "item-1"


@pytest.mark.parametrize(
    "attributes",
    [
        {"stored_path": "/private/image.png"},
        {"storage_key": "bucket/private/image.png"},
        {"binary_data": "AA=="},
        {"labels": {"path": "C:\\private\\image.png"}},
        {"labels": {"values": {1, 2}}},
        {"labels": {"created_at": datetime.utcnow()}},
        {"labels": object()},
    ],
)
def test_image_attributes_reject_private_storage_and_non_json_values(attributes):
    with pytest.raises((TypeError, ValueError, ValidationError)):
        validate_image_attributes(attributes)


def test_public_analysis_schemas_validate_attributes_with_the_same_rules():
    with pytest.raises((TypeError, ValueError, ValidationError)):
        ImageAnalysisRecord(
            item_id="item-1",
            analysis_status="ready",
            analysis_version="image-rag-v1",
            attributes={"private_path": "/secret/image.png"},
            embedding_status="pending",
            updated_at=datetime.utcnow(),
        )
    with pytest.raises((TypeError, ValueError, ValidationError)):
        KnowledgeItemAnalysisSummary(
            analysis_status="ready",
            analysis_version="image-rag-v1",
            attributes={"value": datetime.utcnow()},
            retryable=False,
        )
