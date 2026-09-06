import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main


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
    assert all("secret prompt" not in str(event["payload"]) for event in traces)
    assert all("provider-token" not in str(event["payload"]) for event in traces)


def test_successful_image_asset_persists_and_reports_positive_count(monkeypatch):
    persisted = []
    monkeypatch.setattr(main, "save_assets_and_validations", lambda assets, validations: persisted.extend(assets))
    monkeypatch.setattr(main, "cache_generated_asset_url", lambda **kwargs: ("/api/v1/campaigns/campaign/assets/generated-files/asset.png", {"source": "generated_cache", "stored_path": __file__}))

    response = main._save_image_worker_result(image_result([{"url": "https://provider/image.png", "size": "1024x1024"}]), datetime.utcnow())

    assert response["status"] == "accepted"
    assert int(response["assets_saved"]) > 0
    assert len(persisted) == 1
