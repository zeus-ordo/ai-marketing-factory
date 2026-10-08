from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path

import pytest

import app.context_assembler as context_assembler
from app.context_assembler import (
    ContextSourceItem,
    assemble_generation_context,
    select_image_reference_items,
    select_reference_pack_items,
)
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TargetAudience


def campaign() -> CampaignRecord:
    return CampaignRecord(
        company_id="co-1",
        campaign_id="camp-1",
        created_at=datetime.now(timezone.utc),
        brief=CampaignBrief(
            campaign_name="Test",
            product_name="New drink",
            project_description="Launch the seasonal drink campaign",
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


def test_image_reference_selection_caps_manual_and_industry_sources_in_stable_order():
    sources = [
        item("campaign_reference", f"manual-{index}", file_type="image/png") for index in range(5)
    ] + [
        item("industry_matched", f"industry-{index}", file_type="image/jpeg") for index in range(4)
    ]

    selected = select_image_reference_items(sources)

    assert [source.source_id for source in selected] == [
        "manual-0", "manual-1", "manual-2", "manual-3", "industry-0", "industry-1"
    ]


def test_image_reference_selection_ignores_non_image_sources():
    selected = select_image_reference_items([
        item("campaign_reference", "text-1", file_type="text/plain"),
        item("campaign_reference", "image-1", file_type="image/png"),
    ])

    assert [source.source_id for source in selected] == ["image-1"]


def pack_item(pack_id: str, role: str, item_id: str, **metadata: str) -> ContextSourceItem:
    return item(
        "platform_default" if metadata.get("industry") is None else "industry_default",
        item_id,
        pack_id=pack_id,
        pack_role=role,
        selection_mode=metadata.pop("selection_mode", "optional"),
        priority=metadata.pop("priority", "0"),
        max_images=metadata.pop("max_images", "2"),
        mime_type="image/png",
        **metadata,
    )


def test_reference_pack_selection_prioritizes_mandatory_brand_product_and_caps_total():
    sources = [
        pack_item("style", "style", "style-1", selection_mode="optional", priority="100"),
        pack_item("brand", "brand_identity", "brand-1", selection_mode="mandatory", priority="1"),
        pack_item("product", "product", "product-1", selection_mode="mandatory", priority="1"),
    ] + [item("campaign_reference", f"manual-{index}", file_type="image/png") for index in range(6)]

    selected = select_reference_pack_items(sources, "camp-1", "run-1")

    assert [source.source_id for source in selected[:2]] == ["brand-1", "product-1"]
    assert len(selected) == 6
    assert all(source.source_id != "style-1" for source in selected)


def test_reference_pack_selection_rotates_stably_and_deduplicates_sha256():
    sources = [
        pack_item("style", "style", f"style-{index}", priority="1", sha256=f"sha-{index % 2}")
        for index in range(4)
    ]

    first = select_reference_pack_items(sources, "camp-1", "run-1")
    same = select_reference_pack_items(sources, "camp-1", "run-1")
    rotated = select_reference_pack_items(sources, "camp-1", "run-2")

    assert [item.source_id for item in first] == [item.source_id for item in same]
    assert len({item.metadata["sha256"] for item in first}) == len(first)
    assert [item.source_id for item in first] != [item.source_id for item in rotated]


def test_reference_pack_selection_deduplicates_before_filling_cap():
    sources = [
        pack_item("style", "style", "duplicate-a", max_images="10", sha256="same"),
        pack_item("style", "style", "duplicate-b", max_images="10", sha256="same"),
        *[pack_item("style", "style", f"unique-{index}", max_images="10", sha256=f"unique-{index}") for index in range(6)],
    ]

    selected = select_reference_pack_items(sources, "camp-1", "run-1")

    assert len(selected) == 6
    assert len({item.metadata["sha256"] for item in selected}) == 6


def test_reference_pack_selection_deduplicates_across_pack_groups_before_limits(tmp_path):
    duplicate = b"same-file-bytes"
    duplicate_path = tmp_path / "duplicate.png"
    duplicate_path.write_bytes(duplicate)
    duplicate_sha = hashlib.sha256(duplicate).hexdigest()
    unique_path = tmp_path / "unique.png"
    unique_path.write_bytes(b"unique-file-bytes")
    unique_sha = hashlib.sha256(unique_path.read_bytes()).hexdigest()
    duplicate_id, unique_id = "product-duplicate", "product-unique"
    duplicate_rotation = hashlib.sha256(f"camp-1:run-1:product:{duplicate_id}".encode()).hexdigest()
    unique_rotation = hashlib.sha256(f"camp-1:run-1:product:{unique_id}".encode()).hexdigest()
    if duplicate_rotation > unique_rotation:
        duplicate_id, unique_id = unique_id, duplicate_id
    sources = [
        pack_item("brand", "brand_identity", "brand-duplicate", selection_mode="mandatory", max_images="1", sha256=duplicate_sha, stored_path=str(duplicate_path)),
        pack_item("product", "product", duplicate_id, selection_mode="mandatory", max_images="1", sha256=duplicate_sha, stored_path=str(duplicate_path)),
        pack_item("product", "product", unique_id, selection_mode="mandatory", max_images="1", sha256=unique_sha, stored_path=str(unique_path)),
    ]

    selected = select_reference_pack_items(sources, "camp-1", "run-1")

    assert [item.source_id for item in selected] == ["brand-duplicate", unique_id]


def test_reference_pack_selection_ignores_whitespace_only_pack_id():
    selected = select_reference_pack_items(
        [pack_item("   ", "style", "whitespace-pack", selection_mode="optional")],
        "camp-1",
        "run-1",
    )

    assert selected == ()


def test_regeneration_reference_metadata_preserves_partitions_and_stable_ids(tmp_path):
    paths = {}
    for name in ("brand", "product", "style", "rag"):
        path = tmp_path / f"{name}.png"
        path.write_bytes(name.encode())
        paths[name] = str(path)
    sources = [
        pack_item("brand", "brand_identity", "brand-1", selection_mode="mandatory", stored_path=paths["brand"]),
        pack_item("product", "product", "product-1", selection_mode="mandatory", stored_path=paths["product"]),
        pack_item("style", "style", "style-1", stored_path=paths["style"]),
        item(
            "industry_attribute_rag",
            "rag-1",
            "",
            mime_type="image/png",
            stored_path=paths["rag"],
            score="0.9",
            selection_reason="visual_anchor",
            role="style",
        ),
    ]
    snapshot = assemble_generation_context(campaign(), sources, [], [], 100)

    builder = getattr(context_assembler, "build_regeneration_reference_metadata", None)
    assert callable(builder), "regeneration reference metadata helper is required"
    metadata = builder(snapshot)

    assert metadata["immutable_reference_ids"] == ["brand-1", "product-1"]
    assert metadata["adjustable_reference_ids"] == ["style-1", "rag-1"]
    assert metadata["selected_reference_ids"] == ["brand-1", "product-1", "rag-1"]
    assert all("stored_path" not in json.dumps(value) for value in metadata.values())
    assert all("data" not in json.dumps(value) for value in metadata.values())


def test_persisted_snapshot_regeneration_reuses_complete_image_partitions(tmp_path):
    import importlib

    main = importlib.import_module("app.main")
    sources = []
    for index, role in enumerate(("brand_identity", "product", "brand_identity", "product")):
        path = tmp_path / f"mandatory-{index}.png"
        path.write_bytes(f"mandatory-{index}".encode())
        sources.append(pack_item(f"pack-{index}", role, f"mandatory-{index}", selection_mode="mandatory", stored_path=str(path)))
    for index in range(4):
        path = tmp_path / f"manual-{index}.png"
        path.write_bytes(f"manual-{index}".encode())
        sources.append(item("campaign_reference", f"manual-{index}", f"manual-{index}.png", mime_type="image/png", stored_path=str(path)))
    for index in range(4):
        path = tmp_path / f"rag-{index}.png"
        path.write_bytes(f"rag-{index}".encode())
        sources.append(item("industry_attribute_rag", f"rag-{index}", f"rag-{index}.png", mime_type="image/png", stored_path=str(path), score=str(index), role="style"))

    snapshot = assemble_generation_context(campaign(), sources, [], [], 100, run_id="reviewed-run")
    persisted_snapshot = snapshot.__class__(
        **{**snapshot.__dict__, "image_reference_ids": (), "image_reference_partitions": {}}
    )

    references, audit = main.build_image_reference_payload(persisted_snapshot, "different-run")

    assert snapshot.image_reference_ids
    assert set(snapshot.image_reference_ids) == set(audit["selected_reference_ids"])
    assert [reference["reference_id"] for reference in references] == list(snapshot.image_reference_ids)
    assert len(references) <= 12
    assert len(snapshot.image_reference_partitions["mandatory"]) == 4
    assert len(snapshot.image_reference_partitions["user"]) == 3
    assert len(snapshot.image_reference_partitions["rag"]) == 3


def test_active_pack_loading_preserves_persisted_item_metadata(monkeypatch):
    import importlib

    main = importlib.import_module("app.main")
    pack = {
        "pack_id": "pack-style", "name": "Style", "role": "style", "scope": "platform",
        "industry": None, "selection_mode": "optional", "max_images": 2, "priority": 1,
        "is_active": True,
    }
    row = {
        "item_id": "item-1", "title": "Style image", "description": "",
        "metadata": {"stored_path": "/private/style.png", "file_name": "style.png", "file_type": "image/png", "sha256": "persisted-sha"},
    }

    class Persistence:
        def list_reference_packs(self, **kwargs):
            return [pack]

        def list_reference_pack_items(self, pack_id):
            return [row]

    monkeypatch.setattr(main, "persistence", Persistence())
    loaded = main.list_reference_pack_context(campaign())

    assert loaded[0]["sha256"] == "persisted-sha"
    assert loaded[0]["stored_path"] == "/private/style.png"


def test_generation_context_sanitizes_pack_path_but_keeps_runtime_attachment_path(tmp_path):
    image_path = tmp_path / "pack.png"
    image_path.write_bytes(b"pack-image")

    snapshot = assemble_generation_context(
        campaign(),
        [item("platform_default", "pack-item", "", pack_id="pack-1", stored_path=str(image_path), file_type="image/png")],
        [],
        [],
        100,
    )

    source = snapshot.items[0]
    assert "stored_path" not in source.metadata
    assert source.transient_stored_path == str(image_path)


def test_cache_loss_rehydrates_runtime_pack_path_without_persisting_it(monkeypatch, tmp_path):
    import importlib

    main = importlib.import_module("app.main")
    image_path = tmp_path / "pack.png"
    image_path.write_bytes(b"reloaded-pack-image")
    source = item(
        "platform_default",
        "pack-item",
        "pack.png",
        pack_id="pack-1",
        pack_name="Brand Pack",
        pack_role="brand_identity",
        selection_mode="mandatory",
        max_images="1",
        priority="1",
        file_type="image/png",
        stored_path=str(image_path),
    )
    original = assemble_generation_context(campaign(), [source], [], [], 100)
    persisted_metadata = [dict(item.metadata) for item in original.items]
    persisted = original.__class__(
        **{**original.__dict__, "items": tuple(ContextSourceItem(item.source_type, item.source_id, item.label, item.text, metadata) for item, metadata in zip(original.items, persisted_metadata))},
    )

    class Persistence:
        def save_generation_context(self, snapshot, run_id):
            assert all("stored_path" not in metadata for metadata in persisted_metadata)

        def load_generation_context(self, campaign_id, run_id):
            return persisted

        def list_campaign_references(self, campaign_id):
            return []

        def list_reference_packs(self, **kwargs):
            return [{"pack_id": "pack-1", "name": "Brand Pack", "role": "brand_identity", "industry": None, "selection_mode": "mandatory", "max_images": 1, "priority": 1, "is_active": True}]

        def list_reference_pack_items(self, pack_id):
            return [{"item_id": "pack-item", "title": "pack.png", "description": "", "metadata": {"stored_path": str(image_path), "file_type": "image/png"}, "reference_pack_id": pack_id}]

        def list_knowledge_items(self, company_id):
            return []

    persistence = Persistence()
    persistence.save_generation_context(original, "run-after-restart")
    monkeypatch.setattr(main, "persistence", persistence)
    main.generation_context_cache.clear()
    main.generation_context_run_cache.clear()

    loaded = main.snapshot_for_campaign(campaign(), "run-after-restart")
    assert loaded is not None
    assert loaded.items[0].transient_stored_path == str(image_path)
    assert "stored_path" not in loaded.items[0].metadata

    payload = main.build_worker_payload_for_task(campaign(), {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-after-restart"}, loaded)
    assert payload["reference_images"][0]["data"]


def test_cache_loss_rehydrates_nested_industry_knowledge_image_path(monkeypatch, tmp_path):
    import importlib

    main = importlib.import_module("app.main")
    image_path = tmp_path / "industry.png"
    image_path.write_bytes(b"industry-image")
    source = item(
        "industry_matched",
        "knowledge-image",
        "industry.png",
        category="Restaurant",
        file_type="image/png",
        stored_path=str(image_path),
    )
    original = assemble_generation_context(campaign(), [], [source], [], 100)
    persisted = original.__class__(
        **{
            **original.__dict__,
            "items": tuple(
                ContextSourceItem(
                    item.source_type,
                    item.source_id,
                    item.label,
                    item.text,
                    dict(item.metadata),
                )
                for item in original.items
            ),
        }
    )

    class Persistence:
        def load_generation_context(self, campaign_id, run_id):
            return persisted

        def list_campaign_references(self, campaign_id):
            return []

        def list_reference_packs(self, **kwargs):
            return []

        def list_knowledge_items(self, company_id):
            return [{
                "item_id": "knowledge-image",
                "title": "industry.png",
                "description": "",
                "metadata": {
                    "category": "Restaurant",
                    "file_type": "image/png",
                    "stored_path": str(image_path),
                },
            }]

    monkeypatch.setattr(main, "persistence", Persistence())
    main.generation_context_cache.clear()
    main.generation_context_run_cache.clear()

    loaded = main.snapshot_for_campaign(campaign(), "run-industry-restart")
    assert loaded is not None
    assert loaded.items[0].transient_stored_path == str(image_path)
    assert "stored_path" not in loaded.items[0].metadata

    payload = main.build_worker_payload_for_task(
        campaign(),
        {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-industry-restart"},
        loaded,
    )
    assert payload["reference_images"] == []


def test_active_pack_loading_surfaces_persistence_errors(monkeypatch):
    import importlib

    main = importlib.import_module("app.main")

    class Persistence:
        def list_reference_packs(self, **kwargs):
            raise OSError("database unavailable")

    monkeypatch.setattr(main, "persistence", Persistence())

    with pytest.raises(RuntimeError, match="Unable to load active reference packs"):
        main.list_reference_pack_context(campaign())


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


def test_image_payload_contains_reference_audit_and_sanitized_persisted_context(monkeypatch, tmp_path):
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    monkeypatch.setenv("CAMPAIGN_REQUIRE_POSTGRES", "false")
    import importlib
    main = importlib.import_module("app.main")
    image_path = Path(tmp_path) / "reference.png"
    image_path.write_bytes(b"reference-image")
    snapshot = assemble_generation_context(
        campaign(),
        [item("campaign_reference", "ref-1", "", mime_type="image/png", stored_path=str(image_path), folder="General")],
        [],
        [],
        100,
    )

    payload = main.build_worker_payload_for_task(campaign(), {"task_id": "task-image", "task_type": "image_generation"}, snapshot)

    assert payload["reference_images"][0]["reference_id"] == "ref-1"
    assert payload["reference_images"][0]["data"]
    assert payload["brand_context"]["project_description"] == "Launch the seasonal drink campaign"
    assert payload["reference_audit"]["generation_context_id"] == snapshot.generation_context_id
    assert payload["reference_audit"]["brand_context"] == payload["brand_context"]
    assert payload["reference_audit"]["project_description"] == "Launch the seasonal drink campaign"
    assert payload["reference_audit"] == {
        "total_limit": 12,
        "selected_count": 1,
        "attached_count": 1,
        "failures": [],
        "multimodal": True,
        "candidate_count": 1,
        "pack_candidate_count": 0,
        "enriched_candidate_count": 0,
        "candidate_attribute_count": 0,
        "selected_attribute_count": 0,
        "selected_anchor_count": 0,
        "attached_anchor_count": 0,
        "mandatory_selected_count": 0,
        "mandatory_attached_count": 0,
        "user_selected_count": 1,
        "user_attached_count": 1,
        "rag_selected_count": 0,
        "rag_attached_count": 0,
        "references": [{
            "reference_id": "ref-1",
            "file_name": "ref-1",
            "mime_type": "image/png",
            "folder": "General",
            "sha256": "4110dd12af975f556bdac0299d0bfa04d42fa22d94f56b8550f1762e48fff7fb",
            "source_type": "campaign_reference",
            "selection_reason": "user_reference",
            "provenance": "adjustable",
        }],
        "immutable_reference_ids": [],
        "adjustable_reference_ids": ["ref-1"],
        "generation_context_id": snapshot.generation_context_id,
        "brand_context": payload["brand_context"],
        "project_description": "Launch the seasonal drink campaign",
        "selected_reference_ids": ["ref-1"],
        "partitions": {
            "immutable": [],
            "adjustable": [{
                "reference_id": "ref-1",
                "source_type": "campaign_reference",
                "file_name": "ref-1",
                "mime_type": "image/png",
                "folder": "General",
                "selected": True,
                "provenance": "adjustable",
            }],
        },
    }

    captured = {}

    class Persistence:
        def save_llm_generation_payload(self, value):
            captured.update(value)

    monkeypatch.setattr(main, "persistence", Persistence())
    main._capture_worker_payload(payload, "image_generation", "camp-1", "task-image")

    persisted_context = captured["context"]
    assert persisted_context["reference_audit"] == payload["reference_audit"]
    assert "reference_images" not in persisted_context
    assert "data" not in persisted_context["reference_audit"]["references"][0]


def test_persisted_context_removes_nested_reference_image_data(monkeypatch):
    import importlib
    main = importlib.import_module("app.main")
    captured = {}

    class Persistence:
        def save_llm_generation_payload(self, value):
            captured.update(value)

    monkeypatch.setattr(main, "persistence", Persistence())
    audit = {
        "selected_count": 1,
        "attached_count": 1,
        "failures": [],
        "multimodal": True,
        "references": [{"reference_id": "ref-1", "sha256": "abc"}],
    }
    payload = {
        "reference_audit": audit,
        "nested": {"reference_images": [{"reference_id": "ref-1", "data": "nested-secret"}]},
        "unrelated": {
            "data": "keep-this-data",
            "image_data": "keep-this-image-data",
            "base64": "keep-this-base64",
        },
    }

    main._capture_worker_payload(payload, "image_generation", "camp-1", "task-image")

    serialized_context = json.dumps(captured["context"])
    assert "nested-secret" not in serialized_context
    assert "reference_images" not in serialized_context
    assert captured["context"]["reference_audit"] == audit
    assert captured["context"]["unrelated"] == {
        "data": "keep-this-data",
        "image_data": "keep-this-image-data",
        "base64": "keep-this-base64",
    }


def test_persisted_reference_audit_removes_nested_private_values(monkeypatch):
    import importlib

    main = importlib.import_module("app.main")
    captured = {}

    class Persistence:
        def save_llm_generation_payload(self, value):
            captured.update(value)

    monkeypatch.setattr(main, "persistence", Persistence())
    main._capture_worker_payload({
        "reference_audit": {
            "references": [{
                "file_name": "/private/brand.png",
                "folder": "C:\\private\\folder",
                "failure": {"stored_path": "/private/failure.png", "bytes": b"secret", "base64": "c2VjcmV0"},
            }],
            "failures": [{"file_name": "file:///private/failure.png", "folder": "data:image/png;base64,c2VjcmV0"}],
        },
        "reference_images": [{"reference_id": "brand", "data": "c2VjcmV0"}],
    }, "image_generation", "camp-1", "task-image")

    serialized = json.dumps(captured["context"], default=str)
    assert "/private/" not in serialized
    assert "c2VjcmV0" not in serialized
    assert "secret" not in serialized


def test_reference_attachment_failure_is_persisted_before_generation_raises(monkeypatch, tmp_path):
    import importlib
    from fastapi import HTTPException

    main = importlib.import_module("app.main")
    missing_path = Path(tmp_path) / "missing.png"
    snapshot = assemble_generation_context(
        campaign(),
        [item("campaign_reference", "ref-1", "", mime_type="image/png", stored_path=str(missing_path), folder="Brand")],
        [],
        [],
        100,
    )
    captured = []

    class Persistence:
        def save_llm_generation_payload(self, value):
            captured.append(value)

    monkeypatch.setattr(main, "persistence", Persistence())

    with pytest.raises(HTTPException) as error:
        main.build_worker_payload_for_task(campaign(), {"task_id": "task-image", "task_type": "image_generation"}, snapshot)

    assert error.value.status_code == 422
    assert len(captured) == 1
    persisted = captured[0]["context"]
    assert persisted["reference_audit"]["failures"] == [{"reference_id": "ref-1", "category": "missing_file"}]
    assert "reference_images" not in persisted
    assert "data" not in json.dumps(persisted)


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


def test_snapshot_for_campaign_uses_reviewed_run_and_latest_for_missing_run(monkeypatch):
    import importlib
    main = importlib.import_module("app.main")
    old_snapshot = assemble_generation_context(campaign(), [item("user_selected", "old", "OLD RUN")], [], [], 100)
    new_snapshot = assemble_generation_context(campaign(), [item("user_selected", "new", "NEW RUN")], [], [], 100)
    main.generation_context_cache.clear()
    main.generation_context_cache[old_snapshot.generation_context_id] = old_snapshot
    main.generation_context_cache[new_snapshot.generation_context_id] = new_snapshot

    class Persistence:
        def load_generation_context(self, campaign_id, run_id):
            return {"run-old": old_snapshot, "run-new": new_snapshot}.get(run_id)

    monkeypatch.setattr(main, "persistence", Persistence())
    assert main.snapshot_for_campaign(campaign(), "run-old") is old_snapshot
    assert main.snapshot_for_campaign(campaign(), None) is new_snapshot


def test_review_regeneration_uses_snapshot_for_image_and_ads(monkeypatch):
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    import importlib
    from starlette.requests import Request
    from app.schemas import AssetOutput
    from services.worker_image.app.schemas import ImageRunRequest, RevisionRequest
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    old_snapshot = assemble_generation_context(campaign(), [item("user_selected", "old", "OLD REVIEW SNAPSHOT")], [], [], 100)
    new_snapshot = assemble_generation_context(campaign(), [item("user_selected", "new", "NEW REVIEW SNAPSHOT")], [], [], 100)
    main.generation_context_cache.clear()
    main.generation_context_run_cache.clear()
    main.cache_generation_context(old_snapshot, "run-1")
    main.cache_generation_context(new_snapshot, "run-2")
    asset = AssetOutput(company_id="co-1", asset_id="asset", campaign_id="camp-1", task_id="task", asset_type="image", url="https://old", created_at=datetime.now(timezone.utc), run_id="run-1")
    class Persistence:
        def get_asset_output(self, asset_id): return asset
        def get_review_item_by_asset(self, asset_id): return None
        def get_latest_campaign_run(self, campaign_id): return {"run_id": "run-2"}
        def list_asset_outputs(self, campaign_id): return [asset]
        def save_asset_outputs(self, assets): pass
    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main.store, "get_campaign", lambda campaign_id: campaign())
    monkeypatch.setattr(main, "cache_generated_asset_url", lambda **kwargs: (kwargs["source_url"], {"stored_path": "generated/test.png"}))
    saved_assets = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: saved_assets.extend(assets))
    monkeypatch.setattr(main, "finalize_campaign_workflow", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda *args, **kwargs: None)
    captured = {}
    def post_json(url, payload):
        captured["payload"] = payload
        result = {"image_assets": [{"url": "https://new", "size": "1024x1024"}]} if asset.asset_type == "image" else {"ads_plan": {}}
        result.update({"task_id": "task", "campaign_id": "camp-1", "company_id": "co-1", "provider": "provider", "model_name": "model"})
        return result
    monkeypatch.setattr(main, "post_json", post_json)
    request = Request({"type": "http", "headers": [(b"x-internal-api-key", b"test-key")]})
    for asset_type in ("image", "ads"):
        asset.asset_type = asset_type
        main._perform_asset_regeneration(request, "asset")
        assert captured["payload"]["generation_context_id"] == old_snapshot.generation_context_id
        assert "OLD REVIEW SNAPSHOT" in captured["payload"].get("prompt", captured["payload"].get("context", ""))
        if asset_type == "image":
            validated = ImageRunRequest.model_validate(captured["payload"])
            RevisionRequest.model_validate({**captured["payload"], "reject_reason": "quality"})
            assert validated.company_id == "co-1"
            assert saved_assets[-1].metadata["task_type"] == "image_generation"
            assert saved_assets[-1].metadata["provider"] == "provider"
            assert saved_assets[-1].metadata["model_name"] == "model"
    asset.run_id = None
    asset.asset_type = "image"
    main._perform_asset_regeneration(request, "asset")
    assert captured["payload"]["generation_context_id"] == new_snapshot.generation_context_id
    assert "NEW REVIEW SNAPSHOT" in captured["payload"]["prompt"]


def test_review_image_regeneration_reuses_snapshot_reference_images_and_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    import importlib
    from starlette.requests import Request
    from app.schemas import AssetOutput

    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    reference_path = tmp_path / "brand.png"
    reference_path.write_bytes(b"brand-image")
    snapshot = assemble_generation_context(
        campaign(),
        [item(
            "platform_default",
            "brand-1",
            "brand.png",
            pack_id="brand",
            pack_role="brand_identity",
            selection_mode="mandatory",
            mime_type="image/png",
            stored_path=str(reference_path),
        )],
        [],
        [],
        100,
    )
    main.generation_context_cache.clear()
    main.generation_context_run_cache.clear()
    main.cache_generation_context(snapshot, "run-1")
    asset = AssetOutput(
        company_id="co-1", asset_id="asset", campaign_id="camp-1", task_id="task",
        asset_type="image", url="https://old", created_at=datetime.now(timezone.utc), run_id="run-1",
    )

    class Persistence:
        def get_asset_output(self, asset_id): return asset
        def get_review_item_by_asset(self, asset_id): return None
        def list_asset_outputs(self, campaign_id): return [asset]
        def save_asset_outputs(self, assets): pass

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main.store, "get_campaign", lambda campaign_id: campaign())
    monkeypatch.setattr(main, "post_json", lambda url, payload: {"image_assets": [{"url": "https://new", "size": "1024x1024"}], "task_id": "task", "campaign_id": "camp-1", "provider": "p", "model_name": "m"})
    monkeypatch.setattr(main, "cache_generated_asset_url", lambda **kwargs: (kwargs["source_url"], {"stored_path": "generated/test.png"}))
    monkeypatch.setattr(main, "save_assets_and_validations", lambda *args: None)
    monkeypatch.setattr(main, "finalize_campaign_workflow", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda *args, **kwargs: None)
    captured = {}
    monkeypatch.setattr(main, "_capture_worker_payload", lambda payload, *args, **kwargs: captured.update(payload))

    main._perform_asset_regeneration(
        Request({"type": "http", "headers": [(b"x-internal-api-key", b"test-key")]}),
        "asset",
    )

    assert captured["reference_images"][0]["reference_id"] == "brand-1"
    assert captured["reference_audit"]["references"][0]["provenance"] == "immutable"


def test_regeneration_uses_persisted_selected_reference_ids_instead_of_reselection(tmp_path):
    import importlib

    main = importlib.import_module("app.main")
    old_path = tmp_path / "old.png"
    new_path = tmp_path / "new.png"
    old_path.write_bytes(b"old")
    new_path.write_bytes(b"new")
    snapshot = assemble_generation_context(
        campaign(),
        [
            item("platform_default", "old-brand", "old.png", pack_id="brand", pack_role="brand_identity", selection_mode="mandatory", mime_type="image/png", stored_path=str(old_path)),
            item("platform_default", "new-brand", "new.png", pack_id="brand", pack_role="brand_identity", selection_mode="mandatory", mime_type="image/png", stored_path=str(new_path)),
        ],
        [],
        [],
        100,
    )

    references, audit = main.build_image_reference_payload(
        snapshot,
        "different-run",
        persisted_selection={
            "partitions": {
                "immutable": [{"reference_id": "old-brand", "selected": True, "provenance": "immutable"}],
                "adjustable": [],
            },
        },
    )

    assert [reference["reference_id"] for reference in references] == ["old-brand"]
    assert audit["selected_reference_ids"] == ["old-brand"]


def test_regeneration_prompt_reasserts_immutable_policy_after_user_instruction(monkeypatch, tmp_path):
    monkeypatch.setenv("CHATBOT_INTERNAL_API_KEY", "test-key")
    import importlib
    from starlette.requests import Request
    from app.schemas import AssetOutput

    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "CHATBOT_INTERNAL_API_KEY", "test-key")
    image_path = tmp_path / "brand.png"
    image_path.write_bytes(b"brand")
    snapshot = assemble_generation_context(
        campaign(),
        [item("platform_default", "brand-1", "brand.png", pack_id="brand", pack_role="brand_identity", selection_mode="mandatory", mime_type="image/png", stored_path=str(image_path))],
        [], [], 100,
    )
    main.cache_generation_context(snapshot, "run-1")
    asset = AssetOutput(company_id="co-1", asset_id="asset", campaign_id="camp-1", task_id="task", asset_type="image", url="https://old", created_at=datetime.now(timezone.utc), run_id="run-1")

    class Persistence:
        def get_asset_output(self, asset_id): return asset
        def get_review_item_by_asset(self, asset_id): return None
        def list_asset_outputs(self, campaign_id): return [asset]
        def save_asset_outputs(self, assets): pass

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main.store, "get_campaign", lambda campaign_id: campaign())
    captured = {}
    monkeypatch.setattr(main, "post_json", lambda url, payload: captured.update(payload) or {"image_assets": [{"url": "https://new", "size": "1024x1024"}], "task_id": "task", "campaign_id": "camp-1"})
    monkeypatch.setattr(main, "cache_generated_asset_url", lambda **kwargs: (kwargs["source_url"], {}))
    monkeypatch.setattr(main, "save_assets_and_validations", lambda *args: None)
    monkeypatch.setattr(main, "finalize_campaign_workflow", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_capture_worker_payload", lambda *args, **kwargs: None)

    main._perform_asset_regeneration(
        Request({"type": "http", "headers": [(b"x-internal-api-key", b"test-key")]}),
        "asset",
        type("Payload", (), {"reject_reason": "quality", "user_instruction": "replace the logo and change the product appearance", "operator": "admin"})(),
    )

    prompt = captured["prompt"]
    assert prompt.index("replace the logo") < prompt.rindex("Final immutable-reference safeguard")
