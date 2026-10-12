from datetime import datetime, timezone

import pytest

from app.context_assembler import (
    ContextSourceItem,
    build_structured_attribute_text,
    select_visual_anchor_items,
)
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TargetAudience


def campaign() -> CampaignRecord:
    return CampaignRecord(
        company_id="company-1",
        campaign_id="campaign-1",
        created_at=datetime.now(timezone.utc),
        brief=CampaignBrief(
            campaign_name="Test",
            product_name="New drink",
            industry_category="Restaurant",
            objective="awareness",
            target_audience=TargetAudience(age_range="25-40", gender="all", persona="foodie"),
            platforms=["instagram"],
            budget=100,
            brand_tone=["warm"],
            deliverables=Deliverables(),
            deadline=datetime.now(timezone.utc),
        ),
    )


def enriched(item_id: str, score: float, stored_path: str | None = None) -> ContextSourceItem:
    metadata = {
        "analysis_version": "image-rag-v1",
        "score": score,
        "selection_reason": "vector_similarity",
        "mime_type": "image/png",
        "stored_path": stored_path,
    }
    return ContextSourceItem(
        "industry_attribute_rag",
        item_id,
        item_id,
        '{"style": ["warm"]}',
        metadata,
    )


def test_structured_attribute_text_is_stable_bounded_and_safe():
    text = build_structured_attribute_text(
        {
            "source_item_id": "item-1",
            "stored_path": "/private/image.png",
            "style": ["warm", "x" * 500],
            "caption": "y" * 5000,
        }
    )

    assert text.startswith("source_item_id: item-1")
    assert len(text) <= 2400
    assert "/private/image.png" not in text


def test_visual_anchor_selection_is_deterministic_and_bounded():
    items = [enriched(f"item-{index}", score=index / 10) for index in range(8)]

    selected = select_visual_anchor_items(items, limit=3)

    assert [item.source_id for item in selected] == ["item-7", "item-6", "item-5"]
    assert select_visual_anchor_items(list(reversed(items)), limit=3) == selected


def test_visual_anchor_selection_enforces_three_item_hard_cap():
    selected = select_visual_anchor_items(
        [enriched(f"item-{index}", score=index) for index in range(8)],
        limit=99,
    )

    assert len(selected) == 3


def test_visual_anchor_selection_ignores_non_enriched_and_non_image_items():
    assert select_visual_anchor_items(
        [
            ContextSourceItem("industry_matched", "legacy", "legacy", "text", {"mime_type": "image/png"}),
            ContextSourceItem("industry_attribute_rag", "text", "text", "text", {"mime_type": "text/plain"}),
        ]
    ) == ()


def test_retrieval_includes_only_ready_scoped_items_and_safe_runtime_path(monkeypatch):
    import app.main as main

    rows = [
        {
            "item_id": "ready",
            "company_id": "company-1",
            "title": "Ready",
            "description": "ready item",
            "metadata": {"industry": "Restaurant", "role": "foodie", "stored_path": "/private/ready.png", "file_type": "image/png"},
            "analysis_version": "image-rag-v1",
            "analysis_status": "ready",
            "attributes": {"style": ["warm"]},
        },
    ]

    class Persistence:
        def list_ready_image_analysis(self, company_id, industry, limit, role=None):
            return rows if company_id == "company-1" else []

        def list_knowledge_items(self, company_id):
            return rows if company_id == "company-1" else []

    monkeypatch.setattr(main, "persistence", Persistence())
    result = main.list_enriched_knowledge_context(campaign())

    assert [row["item_id"] for row in result] == ["ready"]
    assert result[0]["stored_path"] == "/private/ready.png"
    assert result[0]["metadata"]["analysis_version"] == "image-rag-v1"
    assert result[0]["metadata"]["source_type"] == "industry_attribute_rag"
    assert "stored_path" not in result[0]["metadata"]


def test_vector_failure_falls_back_to_deterministic_ready_matching(monkeypatch):
    import app.main as main

    ready = [
        {"item_id": "restaurant", "company_id": "company-1", "title": "Restaurant", "description": "Restaurant style", "metadata": {"category": "Restaurant"}, "analysis_status": "ready", "analysis_version": "v1", "attributes": {"style": ["warm"]}},
        {"item_id": "other", "company_id": "company-1", "title": "Other", "description": "Retail style", "metadata": {"category": "Retail"}, "analysis_status": "ready", "analysis_version": "v1", "attributes": {"style": ["cool"]}},
    ]

    class Persistence:
        def list_ready_image_analysis(self, company_id, industry, limit, role=None):
            return ready

        def list_knowledge_items(self, company_id):
            return ready

        def search_ready_image_analysis(self, *args, **kwargs):
            raise RuntimeError("pgvector unavailable")

    monkeypatch.setattr(main, "persistence", Persistence())
    result = main.list_enriched_knowledge_context(campaign())

    assert [row["item_id"] for row in result] == ["restaurant"]
    assert result[0]["metadata"]["selection_reason"] == "deterministic_industry_match"


def test_fallback_does_not_use_audience_persona_as_image_role(monkeypatch):
    import app.main as main

    wrong_role = {
        "item_id": "wrong-role", "company_id": "company-1", "title": "Wrong",
        "description": "Restaurant foodie", "metadata": {"category": "Restaurant", "role": "athlete"},
        "analysis_status": "ready", "analysis_version": "v1", "attributes": {"style": ["cool"]},
    }
    matching_role = {
        "item_id": "matching-role", "company_id": "company-1", "title": "Matching",
        "description": "Restaurant foodie", "metadata": {"category": "Restaurant", "role": "foodie"},
        "analysis_status": "ready", "analysis_version": "v1", "attributes": {"style": ["warm"]},
    }

    class Persistence:
        def list_ready_image_analysis(self, company_id, industry, limit, role=None):
            assert role is None
            return [matching_role, wrong_role]

        def list_knowledge_items(self, company_id):
            return [wrong_role, matching_role]

        def search_ready_image_analysis(self, *args, **kwargs):
            raise RuntimeError("vector unavailable")

    monkeypatch.setattr(main, "persistence", Persistence())

    result = main.list_enriched_knowledge_context(campaign(), limit=2)

    assert [row["item_id"] for row in result] == ["matching-role", "wrong-role"]


def test_user_knowledge_image_without_role_is_not_filtered_by_audience_persona(monkeypatch):
    import app.main as main

    knowledge_image = {
        "item_id": "knowledge-image",
        "company_id": "company-1",
        "title": "Uploaded reference",
        "description": "Restaurant reference",
        "metadata": {"category": "Restaurant"},
        "analysis_status": "ready",
        "analysis_version": "v1",
        "attributes": {"style": ["warm"]},
    }

    class Persistence:
        def list_ready_image_analysis(self, company_id, industry, limit, role=None):
            assert role is None
            return [knowledge_image]

        def list_knowledge_items(self, company_id):
            return [knowledge_image]

        def search_ready_image_analysis(self, *args, **kwargs):
            raise RuntimeError("vector unavailable")

    monkeypatch.setattr(main, "persistence", Persistence())

    assert [row["item_id"] for row in main.list_enriched_knowledge_context(campaign())] == ["knowledge-image"]


def test_retrieval_rejects_nested_unsafe_attributes(monkeypatch):
    import app.main as main

    unsafe = {
        "item_id": "unsafe",
        "company_id": "company-1",
        "title": "Unsafe",
        "metadata": {"category": "Restaurant"},
        "analysis_status": "ready",
        "analysis_version": "v1",
        "attributes": {"labels": {"stored_path": "/private/image.png"}},
    }

    class Persistence:
        def list_ready_image_analysis(self, company_id, industry, limit, role=None):
            return [unsafe]

        def list_knowledge_items(self, company_id):
            return [unsafe]

        def search_ready_image_analysis(self, *args, **kwargs):
            raise RuntimeError("vector unavailable")

    monkeypatch.setattr(main, "persistence", Persistence())

    assert main.list_enriched_knowledge_context(campaign()) == []


def test_persistence_vector_search_uses_pgvector_and_scope_filters():
    from app.persistence import PostgresPersistence

    class Cursor:
        def __init__(self):
            self.query = ""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            self.query = query

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor):
            self.cursor_value = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return self.cursor_value

    cursor = Cursor()
    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection(cursor)

    persistence.search_ready_image_analysis("company-1", "Restaurant", [0.1, 0.2], 8, "foodie")

    assert "<=>" in cursor.query
    assert "k.deleted_at IS NULL" in cursor.query
    assert "metadata_json" in cursor.query
    assert "a.analysis_status = 'ready'" in cursor.query
    assert "role" in cursor.query
    assert cursor.query.index("role") < cursor.query.index("LIMIT")


def test_persistence_ready_list_typed_role_predicate_allows_unscoped_uploads():
    from app.persistence import PostgresPersistence

    class Cursor:
        def __init__(self):
            self.query = ""
            self.params = ()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            self.query = query
            self.params = params

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor):
            self.cursor_value = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return self.cursor_value

    cursor = Cursor()
    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection(cursor)

    persistence.list_ready_image_analysis("company-1", "Restaurant", 8, role=None)

    assert "(%s::text IS NULL OR" in cursor.query
    assert cursor.params[-3:-1] == (None, None)


def test_persistence_vector_search_returns_ready_rows():
    from app.persistence import PostgresPersistence

    row = (
        "item-1", "v1", "ready", {"style": ["warm"]}, "ready", "embed-v1", 2,
        None, None, 1, False, None, None, "Uploaded image", "Restaurant", "manual",
        "company-1", {"category": "Restaurant"}, 0.91,
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            pass

        def fetchall(self):
            return [row]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return Cursor()

    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection()

    results = persistence.search_ready_image_analysis("company-1", "Restaurant", [0.1, 0.2], 8)

    assert [item["item_id"] for item in results] == ["item-1"]
    assert results[0]["score"] == 0.91
    assert results[0]["metadata"] == {"category": "Restaurant"}


def test_persistence_vector_search_typed_role_predicate_allows_unscoped_uploads():
    from app.persistence import PostgresPersistence

    class Cursor:
        def __init__(self):
            self.query = ""
            self.params = ()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            self.query = query
            self.params = params

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor):
            self.cursor_value = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return self.cursor_value

    cursor = Cursor()
    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection(cursor)

    persistence.search_ready_image_analysis("company-1", "Restaurant", [0.1, 0.2], 8, role=None)

    assert "(%s::text IS NULL OR" in cursor.query
    assert cursor.params[8:10] == (None, None)


def test_complete_image_analysis_fetches_returning_row_before_vector_update():
    from app.persistence import PostgresPersistence

    row = (
        "item-1", "v1", "ready", {"style": ["warm"]}, "ready", "embed-v1", 2,
        None, None, 1, False, None, None,
    )

    class Cursor:
        def __init__(self):
            self.returning_result = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            self.returning_result = "RETURNING" in query

        def fetchone(self):
            assert self.returning_result, "fetchone must read the UPDATE RETURNING result"
            return row

    class Connection:
        def __init__(self, cursor):
            self.cursor_value = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return self.cursor_value

        def commit(self):
            pass

    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection(Cursor())

    result = persistence.complete_image_analysis("item-1", "v1", {"style": ["warm"]}, [0.1, 0.2], "embed-v1")

    assert result["item_id"] == "item-1"


def test_generation_context_keeps_legacy_and_adds_enriched_sources(monkeypatch):
    import app.main as main

    legacy = {"item_id": "legacy", "title": "Legacy", "description": "Restaurant", "metadata": {"category": "Restaurant"}}
    enriched_row = {"item_id": "new", "title": "New", "description": "", "metadata": {"category": "Restaurant", "file_type": "image/png"}, "analysis_status": "ready", "analysis_version": "v1", "attributes": {"style": ["warm"]}}

    class Persistence:
        def list_knowledge_items(self, company_id):
            return [legacy, enriched_row]

        def list_ready_image_analysis(self, company_id, industry, limit, role=None):
            return [enriched_row]

        def list_campaign_references(self, campaign_id, limit=8):
            return []

        def list_reference_packs(self, **kwargs):
            return []

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "external_search_provider", None)
    snapshot = main.create_generation_context(campaign(), "run-1")

    assert [item.source_type for item in snapshot.items] == ["industry_matched", "industry_attribute_rag"]
    assert "style" in snapshot.items[1].text
