import os
import sys
import importlib.util
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.context_assembler import ContextSourceItem, assemble_generation_context, build_generation_reference_payload
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TaskRecord


_WORKER_SCHEMAS_PATH = Path(__file__).parents[1] / "worker_image" / "app" / "schemas.py"
_WORKER_SCHEMAS_SPEC = importlib.util.spec_from_file_location("worker_image_schemas", _WORKER_SCHEMAS_PATH)
assert _WORKER_SCHEMAS_SPEC and _WORKER_SCHEMAS_SPEC.loader
_WORKER_SCHEMAS = importlib.util.module_from_spec(_WORKER_SCHEMAS_SPEC)
_WORKER_SCHEMAS_SPEC.loader.exec_module(_WORKER_SCHEMAS)


def pack_snapshot(tmp_path, selection_mode):
    campaign = CampaignRecord(
        company_id="company", campaign_id="campaign", created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Campaign", product_name="Product", objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables=Deliverables(image_assets=1), deadline=datetime.utcnow()),
    )
    item = ContextSourceItem(
        "platform_default", "pack-item", "pack.png", "",
        {"stored_path": str(tmp_path / "missing.png"), "file_type": "image/png", "pack_id": "pack-1", "pack_name": "Brand Pack",
         "pack_role": "brand_identity", "selection_mode": selection_mode, "max_images": 1, "priority": 10},
    )
    return campaign, assemble_generation_context(campaign, [item], [], [], 100)


def test_optional_pack_missing_file_is_audited_without_blocking_generation(tmp_path):
    campaign, snapshot = pack_snapshot(tmp_path, "optional")

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    assert payload["reference_images"] == []
    assert payload["reference_audit"]["failures"] == []


def test_copy_payload_has_attributes_without_image_parts(tmp_path):
    campaign, snapshot = pack_snapshot(tmp_path, "optional")
    snapshot = assemble_generation_context(campaign, [ContextSourceItem(
        "industry_attribute_rag", "attr-1", "anchor.png", "warm visual",
        {"mime_type": "image/png", "attributes": {"style": ["warm"]},
         "analysis_version": "image-rag-v1", "selection_reason": "vector_similarity"},
    )], [], [], 100)

    payload = build_generation_reference_payload(snapshot, "copywriting")

    assert payload["attributes"][0]["source_item_id"] == "attr-1"
    assert payload["visual_anchors"] == []
    assert payload["legacy_references"] == []


def test_image_payload_caps_enriched_anchors_and_keeps_pack_precedence(tmp_path):
    campaign, _ = pack_snapshot(tmp_path, "optional")
    pack_path = tmp_path / "pack.png"
    pack_path.write_bytes(b"pack")
    items = [ContextSourceItem(
        "platform_default", "pack-item", "pack.png", "", {
            "stored_path": str(pack_path), "file_type": "image/png", "pack_id": "pack-1",
            "pack_role": "brand_identity", "selection_mode": "mandatory", "max_images": 1,
        },
    )]
    for index in range(5):
        anchor_path = tmp_path / f"anchor-{index}.png"
        anchor_path.write_bytes(f"anchor-{index}".encode())
        items.append(ContextSourceItem(
            "industry_attribute_rag", f"anchor-{index}", f"anchor-{index}.png", "",
            {"stored_path": str(anchor_path), "file_type": "image/png", "attributes": {"style": ["warm"]},
             "analysis_version": "image-rag-v1", "score": index, "selection_reason": "vector_similarity", "role": "foodie"},
        ))
    snapshot = assemble_generation_context(campaign, items, [], [], 100)

    payload = build_generation_reference_payload(snapshot, "image_generation")

    assert len(payload["visual_anchors"]) == 3
    assert all("stored_path" not in anchor for anchor in payload["visual_anchors"])
    assert all(anchor["role"] == "foodie" for anchor in payload["visual_anchors"])
    assert payload["legacy_references"][0]["source_id"] == "pack-item"

    worker_payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )
    _WORKER_SCHEMAS.ImageRunRequest.model_validate(worker_payload)
    assert all(set(reference) <= {"reference_id", "file_name", "mime_type", "data", "folder", "sha256"}
               for reference in worker_payload["reference_images"])
    enriched_audit = [
        reference for reference in worker_payload["reference_audit"]["references"]
        if reference.get("source_type") == "industry_attribute_rag"
    ]
    assert enriched_audit
    assert all(reference["role"] == "foodie" for reference in enriched_audit)
    assert all(reference["analysis_version"] == "image-rag-v1" for reference in enriched_audit)
    assert all(reference["selection_reason"] == "vector_similarity" for reference in enriched_audit)
    assert all(reference["similarity"] in {2, 3, 4} for reference in enriched_audit)


def test_generation_payload_rejects_nested_unsafe_attributes():
    campaign, snapshot = pack_snapshot(Path("."), "optional")
    snapshot = assemble_generation_context(campaign, [ContextSourceItem(
        "industry_attribute_rag", "unsafe", "unsafe.png", "safe text",
        {"mime_type": "image/png", "attributes": {"style": {"nested": {"stored_path": "/private/a.png"}}}},
    )], [], [], 100)

    payload = build_generation_reference_payload(snapshot, "copywriting")

    assert payload["attributes"] == []
    assert "/private/a.png" not in str(payload)


def test_image_audit_has_fixed_counts_and_anchor_role_when_empty():
    campaign, snapshot = pack_snapshot(Path("."), "optional")

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    audit = payload["reference_audit"]
    assert audit["candidate_count"] == 1
    assert audit["selected_attribute_count"] == 0
    assert audit["selected_anchor_count"] == 0
    assert audit["attached_anchor_count"] == 0


def test_image_audit_rejects_unsafe_reference_metadata_but_keeps_worker_bytes(tmp_path):
    campaign = _campaign() if "_campaign" in globals() else CampaignRecord(
        company_id="company", campaign_id="campaign", created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Campaign", product_name="Product", objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables=Deliverables(image_assets=1), deadline=datetime.utcnow()),
    )
    path = tmp_path / "reference.png"
    path.write_bytes(b"reference-bytes")
    snapshot = assemble_generation_context(campaign, [ContextSourceItem(
        "campaign_reference", "unsafe-ref", "C:/private/brand.png", "",
        {
            "stored_path": str(path), "file_type": "image/png", "folder": "data:image/png;base64,ZmFrZQ==",
            "provenance": "C:\\private\\provenance.json", "pack_name": "L3ByaXZhdGUvcGFjay5qcGc=",
        },
    )], [], [], 100)

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    assert payload["reference_images"][0]["data"]
    serialized_audit = str(payload["reference_audit"]).lower()
    assert "data:image" not in serialized_audit
    assert "c:/private" not in serialized_audit
    assert "provenance.json" not in serialized_audit
    assert "l3by" not in serialized_audit
    assert all(key not in serialized_audit for key in ("stored_path", "image_data", "base64", "binary_data"))


def test_mandatory_pack_missing_file_returns_structured_422(tmp_path):
    from fastapi import HTTPException

    campaign, snapshot = pack_snapshot(tmp_path, "mandatory")

    try:
        main.build_worker_payload_for_task(
            campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
        )
    except HTTPException as error:
        assert error.status_code == 422
        failure = error.detail["failures"][0]
        assert failure["reference_id"] == "pack-item"
        assert failure["category"] == "missing_file"
        assert failure["mandatory"] is True
        assert failure["reference_pack_id"] == "pack-1"
    else:
        raise AssertionError("mandatory Pack attachment failure must return 422")


def test_pack_audit_counts_pack_candidates_and_preserves_mixed_manual_provenance(tmp_path):
    campaign = CampaignRecord(
        company_id="company", campaign_id="campaign", created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Campaign", product_name="Product", objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables=Deliverables(image_assets=1), deadline=datetime.utcnow()),
    )
    pack_items = []
    for index in range(7):
        path = tmp_path / f"pack-{index}.png"
        path.write_bytes(f"pack-{index}".encode())
        pack_items.append(ContextSourceItem(
            "platform_default", f"pack-{index}", f"pack-{index}.png", "",
            {"stored_path": str(path), "file_type": "image/png", "pack_id": "pack-1", "pack_name": "Style",
             "pack_role": "style", "selection_mode": "optional", "max_images": 10, "priority": 1},
        ))
    manual_path = tmp_path / "manual.png"
    manual_path.write_bytes(b"manual")
    manual = ContextSourceItem(
        "campaign_reference", "manual-1", "manual.png", "",
        {"stored_path": str(manual_path), "file_type": "image/png", "folder": "General"},
    )
    snapshot = assemble_generation_context(campaign, [manual, *pack_items], [], [], 100)

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    audit = payload["reference_audit"]
    assert audit["candidate_count"] == 8
    assert audit["pack_candidate_count"] == 7
    assert audit["enriched_candidate_count"] == 0
    assert audit["selected_count"] == 1
    assert audit["attached_count"] == 1
    assert audit["references"][0]["reference_id"] == "manual-1"
    assert all(reference.get("reference_pack_id") != "pack-1" for reference in audit["references"])


def test_optional_pack_failure_audit_includes_selection_reason(tmp_path):
    campaign, snapshot = pack_snapshot(tmp_path, "optional")

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    assert payload["reference_audit"]["failures"] == []


def test_pack_audit_filters_default_sources_without_pack_id(tmp_path):
    campaign = CampaignRecord(
        company_id="company", campaign_id="campaign", created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Campaign", product_name="Product", objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables=Deliverables(image_assets=1), deadline=datetime.utcnow()),
    )
    invalid_path = tmp_path / "invalid.png"
    invalid_path.write_bytes(b"invalid-pack-source")
    valid_path = tmp_path / "valid.png"
    valid_path.write_bytes(b"valid-pack-source")
    snapshot = assemble_generation_context(campaign, [
        ContextSourceItem("platform_default", "invalid", "invalid.png", "", {"stored_path": str(invalid_path), "file_type": "image/png"}),
        ContextSourceItem("platform_default", "valid", "valid.png", "", {"stored_path": str(valid_path), "file_type": "image/png", "pack_id": "pack-1", "pack_role": "style", "selection_mode": "optional", "max_images": 1}),
    ], [], [], 100)

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    assert payload["reference_audit"]["candidate_count"] == 2
    assert payload["reference_audit"]["pack_candidate_count"] == 1
    assert all(reference["reference_id"] != "invalid" for reference in payload["reference_audit"]["references"])


def test_image_payload_uses_fixed_mandatory_user_and_rag_partitions(tmp_path):
    campaign, _ = pack_snapshot(tmp_path, "optional")
    items = []
    for index in range(8):
        path = tmp_path / f"mandatory-{index}.png"
        path.write_bytes(f"mandatory-{index}".encode())
        items.append(ContextSourceItem(
            "platform_default", f"mandatory-{index}", path.name, "",
            {"stored_path": str(path), "file_type": "image/png", "pack_id": "mandatory-pack",
             "pack_role": "style", "selection_mode": "mandatory", "max_images": 8, "priority": 10},
        ))
    for index in range(5):
        path = tmp_path / f"user-{index}.png"
        path.write_bytes(f"user-{index}".encode())
        items.append(ContextSourceItem(
            "user_selected", f"user-{index}", path.name, "",
            {"stored_path": str(path), "file_type": "image/png"},
        ))
    for index in range(5):
        path = tmp_path / f"rag-{index}.png"
        path.write_bytes(f"rag-{index}".encode())
        items.append(ContextSourceItem(
            "industry_attribute_rag", f"rag-{index}", path.name, "",
            {"stored_path": str(path), "file_type": "image/png", "score": index,
             "attributes": {"style": ["warm"]}, "selection_reason": "vector_similarity"},
        ))
    optional_path = tmp_path / "optional.png"
    optional_path.write_bytes(b"optional")
    items.append(ContextSourceItem(
        "platform_default", "optional", optional_path.name, "",
        {"stored_path": str(optional_path), "file_type": "image/png", "pack_id": "optional-pack",
         "pack_role": "style", "selection_mode": "optional", "max_images": 20},
    ))
    industry_path = tmp_path / "industry.png"
    industry_path.write_bytes(b"industry")
    items.append(ContextSourceItem(
        "industry_matched", "industry", industry_path.name, "",
        {"stored_path": str(industry_path), "file_type": "image/png"},
    ))
    snapshot = assemble_generation_context(campaign, items, [], [], 1000)

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    audit = payload["reference_audit"]
    assert len(payload["reference_images"]) == 12
    assert len({reference["reference_id"] for reference in payload["reference_images"][:6]}) == 6
    assert all(reference["reference_id"].startswith("mandatory-") for reference in payload["reference_images"][:6])
    assert [reference["reference_id"] for reference in payload["reference_images"][6:9]] == [f"user-{index}" for index in range(3)]
    assert {reference["reference_id"] for reference in payload["reference_images"][9:]} == {"rag-2", "rag-3", "rag-4"}
    assert "optional" not in {reference["reference_id"] for reference in payload["reference_images"]}
    assert "industry" not in {reference["reference_id"] for reference in payload["reference_images"]}
    assert audit["total_limit"] == 12
    assert audit["mandatory_selected_count"] == 6
    assert audit["mandatory_attached_count"] == 6
    assert audit["user_selected_count"] == 3
    assert audit["user_attached_count"] == 3
    assert audit["rag_selected_count"] == 3
    assert audit["rag_attached_count"] == 3


def test_optional_pack_does_not_fill_reserved_user_or_rag_partition(tmp_path):
    campaign, _ = pack_snapshot(tmp_path, "optional")
    items = []
    for index in range(10):
        path = tmp_path / f"optional-{index}.png"
        path.write_bytes(f"optional-{index}".encode())
        items.append(ContextSourceItem(
            "platform_default", f"optional-{index}", path.name, "",
            {"stored_path": str(path), "file_type": "image/png", "pack_id": "optional-pack",
             "pack_role": "style", "selection_mode": "optional", "max_images": 20},
        ))
    rag_path = tmp_path / "rag.png"
    rag_path.write_bytes(b"rag")
    items.append(ContextSourceItem(
        "industry_attribute_rag", "rag", rag_path.name, "",
        {"stored_path": str(rag_path), "file_type": "image/png", "score": 1,
         "attributes": {"style": ["warm"]}},
    ))
    snapshot = assemble_generation_context(campaign, items, [], [], 1000)

    payload = main.build_worker_payload_for_task(
        campaign, {"task_id": "image-task", "task_type": "image_generation", "run_id": "run-1"}, snapshot,
    )

    assert [reference["reference_id"] for reference in payload["reference_images"]] == ["rag"]
    assert payload["reference_audit"]["mandatory_selected_count"] == 0
    assert payload["reference_audit"]["user_selected_count"] == 0
    assert payload["reference_audit"]["rag_selected_count"] == 1


def image_result(image_assets):
    return {
        "task_id": "image-task",
        "campaign_id": "campaign",
        "company_id": "company",
        "image_assets": image_assets,
    }


def test_empty_image_assets_fail_generation_and_do_not_persist(monkeypatch):
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))

    response = main._save_image_worker_result(image_result([]), datetime.utcnow())

    assert response["status"] == "failed"
    assert response["assets_saved"] == "0"
    assert persisted == []


def test_invalid_image_asset_url_fails_generation(monkeypatch):
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))

    response = main._save_image_worker_result(image_result([{"url": "data:image/png;base64,not-base64"}]), datetime.utcnow())

    assert response["status"] == "failed"
    assert response["assets_saved"] == "0"
    assert persisted == []


def test_cache_failure_fails_generation_without_persisting_provider_url(monkeypatch, tmp_path):
    persisted = []
    generated_dir = tmp_path / "generated"
    monkeypatch.setattr(main, "GENERATED_ASSETS_DIR", str(generated_dir))
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    monkeypatch.setattr(main, "cache_generated_asset_url", lambda **kwargs: (_ for _ in ()).throw(OSError("download failed")))

    response = main._save_image_worker_result(image_result([{"url": "https://provider/image.png"}]), datetime.utcnow())

    assert response["status"] == "failed"
    assert response["assets_saved"] == "0"
    assert persisted == []
    assert not generated_dir.exists()


def test_cached_image_metadata_never_persists_provider_query_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "GENERATED_ASSETS_DIR", str(tmp_path / "generated"))

    class Response:
        headers = {"content-type": "image/png"}

        def read(self):
            return b"\x89PNG\r\n\x1a\nminimal-image"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(main.request, "urlopen", lambda *args, **kwargs: Response())

    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    response = main._save_image_worker_result(
        image_result([{"url": "https://provider.example/image.png?token=super-secret&signature=private"}]),
        datetime.utcnow(),
    )

    assert response["status"] == "accepted"
    assert persisted
    metadata_text = str(persisted[0].metadata)
    assert "token=super-secret" not in metadata_text
    assert "signature=private" not in metadata_text
    assert "original_url" not in persisted[0].metadata


def test_mixed_valid_and_invalid_image_assets_fail_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "GENERATED_ASSETS_DIR", str(tmp_path / "generated"))
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    valid = "data:image/png;base64,aW1hZ2U="

    response = main._save_image_worker_result(
        image_result([{"url": valid}, {"url": "data:image/png;base64:not-valid"}]),
        datetime.utcnow(),
    )

    assert response["status"] == "failed"
    assert response["assets_saved"] == "0"
    assert persisted == []


def test_non_base64_image_data_url_fails_generation(monkeypatch):
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))

    response = main._save_image_worker_result(image_result([{"url": "data:image/png,arbitrary payload"}]), datetime.utcnow())

    assert response["status"] == "failed"
    assert persisted == []


def test_worker_502_records_retryable_failure_trace(monkeypatch):
    traces = []
    monkeypatch.setattr(main, "post_json", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 502 secret=provider-token")))
    monkeypatch.setattr(main, "append_trace_event", lambda **kwargs: traces.append(kwargs))
    monkeypatch.setattr(main, "WORKER_RETRY_BACKOFF_SECONDS", 0)

    try:
        main._worker_post_json("https://worker/internal", {"prompt": "secret prompt"}, "image_generation", "campaign", "task", "company")
    except RuntimeError:
        pass

    assert traces
    assert all(event["payload"]["retryable"] is True for event in traces)
    assert all(event["payload"]["attempts"] == event["payload"]["attempt"] for event in traces)
    assert all(set(event["payload"]) <= {"task_id", "task_type", "attempt", "attempts", "retryable", "error_code", "status_code", "provider", "message", "error", "error_detail", "worker_url"} for event in traces)
    assert all("secret prompt" not in str(event["payload"]) for event in traces)
    assert all("provider-token" not in str(event["payload"]) for event in traces)
    assert all("worker/internal" not in str(event["payload"]) for event in traces)
    assert all(event["payload"]["error"] == "Worker request failed" for event in traces)
    assert all(event["payload"]["error_detail"] == "Worker request failed" for event in traces)
    assert all(event["payload"]["worker_url"] is None for event in traces)


def test_worker_failure_trace_preserves_legacy_retry_fields_safely():
    payload = main.worker_failure_trace_payload(
        "HTTP 502 provider=https://evil.example credential=secret",
        task_id="task",
        task_type="image_generation",
        attempt=1,
        retryable=True,
        provider="https://evil.example/token",
    )

    assert payload["error"] == "Worker request failed"
    assert payload["error_detail"] == "Worker request failed"
    assert payload["worker_url"] is None
    assert payload["provider"] == "unknown"
    assert "evil.example" not in str(payload)


def test_uppercase_base64_image_data_url_with_valid_bytes_is_accepted(tmp_path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\n" + b"minimal-image"
    monkeypatch.setattr(main, "GENERATED_ASSETS_DIR", str(tmp_path / "generated"))
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    encoded = __import__("base64").b64encode(png).decode("ascii")

    response = main._save_image_worker_result(image_result([{"url": f"data:image/png;BASE64,{encoded}"}]), datetime.utcnow())

    assert response["status"] == "accepted"
    assert len(persisted) == 1
    assert Path(persisted[0].metadata["stored_path"]).read_bytes() == png


def test_worker_failure_trace_payload_is_bounded_and_safe():
    payload = main.worker_failure_trace_payload(
        "https://worker/internal?token=secret HTTP 502 provider response=private",
        task_id="task",
        task_type="image_generation",
        attempt=2,
        retryable=True,
        provider="gemini",
    )

    assert payload == {
        "task_id": "task",
        "task_type": "image_generation",
        "attempt": 2,
        "attempts": 2,
        "retryable": True,
        "error_code": "provider_error",
        "error": "Worker request failed",
        "error_detail": "Worker request failed",
        "worker_url": None,
        "status_code": 502,
        "provider": "gemini",
        "message": "Worker request failed",
    }


def test_non_strict_empty_image_result_fails_without_success_path(monkeypatch):
    campaign = CampaignRecord(
        company_id="company", campaign_id="campaign", created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Campaign", product_name="Product", objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables=Deliverables(image_assets=1), deadline=datetime.utcnow()),
    )
    task = TaskRecord(company_id="company", campaign_id="campaign", task_id="image-task", task_type="image_generation", status="planned", priority=1, acceptance=[])
    monkeypatch.setattr(main, "_worker_post_json", lambda *args, **kwargs: {"image_assets": []})

    try:
        main.generate_outputs_via_workers("company", "campaign", campaign, [task], strict=False)
    except RuntimeError as exc:
        assert "no displayable assets" in str(exc)
    else:
        raise AssertionError("empty non-strict generation must fail")


def test_worker_generation_rejects_mixed_image_assets_without_partial_persistence(monkeypatch):
    campaign = CampaignRecord(
        company_id="company", campaign_id="campaign", created_at=datetime.utcnow(),
        brief=CampaignBrief(campaign_name="Campaign", product_name="Product", objective="awareness",
            target_audience={"age_range": "all", "gender": "all", "persona": "all"}, platforms=["social"],
            budget=1, brand_tone=[], deliverables=Deliverables(image_assets=2), deadline=datetime.utcnow()),
    )
    task = TaskRecord(company_id="company", campaign_id="campaign", task_id="image-task", task_type="image_generation", status="planned", priority=1, acceptance=[])
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    monkeypatch.setattr(main, "_worker_post_json", lambda *args, **kwargs: {"image_assets": [
        {"url": "data:image/png;base64,aW1hZ2U="},
        {"url": "data:image/png;base64:not-valid"},
    ]})

    try:
        main.generate_outputs_via_workers("company", "campaign", campaign, [task], strict=False)
    except RuntimeError as exc:
        assert "no displayable assets" in str(exc)
    else:
        raise AssertionError("mixed image generation must fail")
    assert persisted == []


def test_successful_image_asset_persists_and_reports_positive_count(monkeypatch):
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    monkeypatch.setattr(main, "cache_generated_asset_url", lambda **kwargs: ("/api/v1/campaigns/campaign/assets/generated-files/asset.png", {"source": "generated_cache", "stored_path": __file__}))

    response = main._save_image_worker_result(image_result([{"url": "https://provider/image.png", "size": "1024x1024"}]), datetime.utcnow())

    assert response["status"] == "accepted"
    assert int(response["assets_saved"]) > 0
    assert len(persisted) == 1


def test_local_image_file_is_downloaded_to_generated_cache(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nminimal-image")
    monkeypatch.setattr(main, "GENERATED_ASSETS_DIR", str(tmp_path / "generated"))
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))

    response = main._save_image_worker_result(image_result([{"url": source.as_uri()}]), datetime.utcnow())

    assert response["status"] == "accepted"
    assert len(persisted) == 1
    stored_path = persisted[0].metadata["stored_path"]
    assert persisted[0].url.startswith("/api/v1/campaigns/campaign/assets/generated-files/")
    assert Path(stored_path).is_file()
    assert Path(stored_path).read_bytes() == b"\x89PNG\r\n\x1a\nminimal-image"
