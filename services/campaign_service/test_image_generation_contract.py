import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.schemas import CampaignBrief, CampaignRecord, Deliverables, TaskRecord


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
