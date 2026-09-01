from datetime import datetime, timezone

import pytest

from app.context_assembler import ContextSourceItem, assemble_generation_context
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TargetAudience


def campaign() -> CampaignRecord:
    return CampaignRecord(
        company_id="co-1",
        campaign_id="camp-1",
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


def item(source_type: str, source_id: str, text: str = "source text", **metadata: str) -> ContextSourceItem:
    return ContextSourceItem(source_type, source_id, source_id, text, metadata)


def test_allocates_floor_75_25_budgets_and_records_ratios():
    snapshot = assemble_generation_context(
        campaign(),
        [item("user_selected", "u1", "i" * 3000)],
        [item("industry_matched", "i1", "industry")],
        [item("external_web", "e1", "e" * 1000)],
        1000,
    )
    assert snapshot.internal_token_count <= 750
    assert snapshot.external_token_count <= 250
    assert snapshot.internal_ratio == pytest.approx(0.75, abs=0.02)
    assert snapshot.external_ratio == pytest.approx(0.25, abs=0.02)


def test_ranks_selected_before_industry_before_external():
    snapshot = assemble_generation_context(
        campaign(),
        [item("user_selected", "u1")],
        [item("industry_matched", "i1")],
        [item("external_web", "e1", url="https://example.com")],
        100,
    )
    assert [source.source_type for source in snapshot.items] == ["user_selected", "industry_matched", "external_web"]
    assert snapshot.items[-1].metadata["url"] == "https://example.com"


def test_internal_shortage_does_not_relabel_external_content():
    snapshot = assemble_generation_context(campaign(), [], [], [item("external_web", "e1")], 100)
    assert all(source.source_type == "external_web" for source in snapshot.items)


def test_persistence_snapshot_shape_contains_source_provenance():
    from app.persistence import PostgresPersistence

    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, query, params):
            self.calls.append((query, params))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

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

    cursor = Cursor()
    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection(cursor)
    snapshot = assemble_generation_context(campaign(), [item("campaign_reference", "ref-1", "body", folder="Brand")], [], [], 100)
    persistence.save_generation_context(snapshot, "run-1")
    assert "generation_contexts" in cursor.calls[0][0]
    assert "generation_context_items" in cursor.calls[1][0]
    assert cursor.calls[1][1][4:9] == ("ref-1", "ref-1", "body", "Brand", None)


def test_automatic_search_is_added_and_failure_is_classified(monkeypatch):
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    monkeypatch.setenv("CAMPAIGN_REQUIRE_POSTGRES", "false")
    import importlib
    main = importlib.import_module("app.main")

    class Provider:
        def search(self, query, limit):
            return [type("Result", (), {"source_type": "external_web", "url": "https://web.test", "title": "Web", "summary": "facts", "provider": "mock", "query": query, "retrieved_at": datetime.now(timezone.utc)})()]

    monkeypatch.setattr(main, "external_search_provider", Provider())
    snapshot = main.create_generation_context(campaign(), "run-1")
    assert snapshot.external_search_status == "succeeded"
    assert snapshot.external_source_urls == ("https://web.test",)
    payload = main.build_worker_payload_for_task(campaign(), {"task_id": "task-1", "task_type": "copywriting"}, snapshot)
    assert payload["generation_context_id"] == snapshot.generation_context_id
    assert "facts" in payload["prompt"] or "Web" in payload["prompt"]
    class FailingProvider:
        def search(self, query, limit):
            raise RuntimeError("unavailable")

    monkeypatch.setattr(main, "external_search_provider", FailingProvider())
    failed = main.create_generation_context(campaign(), "run-2")
    assert failed.external_search_status == "provider_error"
    assert failed.external_source_urls == ()


def test_snapshot_has_required_provenance_fields_and_is_immutable():
    snapshot = assemble_generation_context(
        campaign(),
        [item("immediate_upload", "ref-1", "body", folder="Upload")],
        [item("industry_matched", "knowledge-1", "facts", folder_name="Food")],
        [],
        100,
    )
    assert snapshot.task_id is None
    assert snapshot.selected_reference_ids == ("ref-1",)
    assert snapshot.matched_folder_names == ("Food",)
    with pytest.raises(TypeError):
        snapshot.items[0].metadata["folder"] = "changed"
