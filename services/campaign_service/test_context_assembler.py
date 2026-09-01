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
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")

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
    with pytest.raises(TypeError):
        snapshot.items[0].metadata["nested"] = {"x": []}


def test_direct_worker_generation_uses_persisted_snapshot_prompt(monkeypatch):
    import importlib
    main = importlib.import_module("app.main")
    snapshot = assemble_generation_context(campaign(), [item("user_selected", "ref", "UNIQUE SNAPSHOT")], [], [], 100)
    main.generation_context_cache[snapshot.generation_context_id] = snapshot
    captured = {}
    monkeypatch.setattr(main, "_worker_post_json", lambda url, payload, *args: captured.update(payload) or {"variants": [{"body": "ok"}]})
    from app.schemas import TaskRecord
    main.generate_outputs_via_workers("co-1", "camp-1", campaign(), [TaskRecord(company_id="co-1", task_id="t", campaign_id="camp-1", task_type="copywriting", status="planned", priority=1)], generation_context_id=snapshot.generation_context_id)
    assert "UNIQUE SNAPSHOT" in captured["prompt"]
    assert captured["generation_context_id"] == snapshot.generation_context_id


def test_existing_table_migrations_are_additive():
    from app.persistence import PostgresPersistence
    class Cursor:
        def __init__(self): self.queries = []
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, query, params=None): self.queries.append(query)
    class Connection:
        def __init__(self, cursor): self.cursor_value = cursor
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def cursor(self): return self.cursor_value
        def commit(self): pass
    cursor = Cursor()
    persistence = object.__new__(PostgresPersistence)
    persistence._connect = lambda: Connection(cursor)
    persistence.initialize()
    migrations = [query for query in cursor.queries if "ALTER TABLE generation_context" in query]
    assert migrations
    assert all("IF NOT EXISTS" in query for query in migrations)
    assert not any("DROP " in query.upper() for query in migrations)


def test_retry_rehydrates_snapshot_from_persistence(monkeypatch):
    import importlib
    main = importlib.import_module("app.main")
    snapshot = assemble_generation_context(campaign(), [item("campaign_reference", "ref", "persisted")], [], [], 100)
    class Persistence:
        def load_generation_context(self, campaign_id, run_id): return snapshot
    main.generation_context_cache.clear()
    monkeypatch.setattr(main, "persistence", Persistence())
    assert main.snapshot_for_campaign(campaign(), "run-1") is snapshot


def test_review_regeneration_uses_snapshot_for_image_and_ads(monkeypatch):
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    import importlib
    from starlette.requests import Request
    from app.schemas import AssetOutput
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    snapshot = assemble_generation_context(campaign(), [item("user_selected", "ref", "REVIEW SNAPSHOT")], [], [], 100)
    main.generation_context_cache.clear()
    main.generation_context_cache[snapshot.generation_context_id] = snapshot
    asset = AssetOutput(company_id="co-1", asset_id="asset", campaign_id="camp-1", task_id="task", asset_type="image", url="https://old", created_at=datetime.now(timezone.utc), run_id="run-1")
    class Persistence:
        def get_asset_output(self, asset_id): return asset
        def get_review_item_by_asset(self, asset_id): return None
        def list_asset_outputs(self, campaign_id): return [asset]
        def save_asset_outputs(self, assets): pass
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main.store, "get_campaign", lambda campaign_id: campaign())
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: None)
    monkeypatch.setattr(main, "finalize_campaign_workflow", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda *args, **kwargs: None)
    captured = {}
    def post_json(url, payload):
        captured["payload"] = payload
        result = {"image_assets": [{"url": "https://new", "size": "1024x1024"}]} if asset.asset_type == "image" else {"ads_plan": {}}
        result.update({"task_id": "task", "campaign_id": "camp-1", "company_id": "co-1"})
        return result
    monkeypatch.setattr(main, "post_json", post_json)
    request = Request({"type": "http", "headers": [(b"x-internal-api-key", b"test-key")]})
    for asset_type in ("image", "ads"):
        asset.asset_type = asset_type
        main._perform_asset_regeneration(request, "asset")
        assert captured["payload"]["generation_context_id"] == snapshot.generation_context_id
        assert "REVIEW SNAPSHOT" in captured["payload"].get("prompt", captured["payload"].get("context", ""))
