import os
from urllib.error import HTTPError

os.environ.setdefault("POSTGRES_DSN", "")

from app.main import MAX_RETRY, classify_worker_error, next_retry_delay, process_task, dispatch
from app.schemas import DispatchRequest, OrchestratorTask
import app.main as orchestrator


def task(task_id, task_type, depends_on=(), status="pending"):
    return OrchestratorTask(
        task_id=task_id,
        task_type=task_type,
        depends_on=list(depends_on),
        priority=1,
        acceptance=[],
        status=status,
    )


def test_classifies_quota_timeout_and_provider_failures():
    quota = HTTPError("https://worker", 429, "Too Many Requests", {}, None)
    assert classify_worker_error(quota) == "quota"
    assert classify_worker_error(TimeoutError("worker timed out")) == "timeout"
    assert classify_worker_error(RuntimeError("provider returned 503")) == "provider_error"


def test_image_failure_blocks_video_but_not_unrelated_copy(monkeypatch):
    campaign_id = "campaign-isolation"
    orchestrator.task_state[campaign_id] = {
        "copy": task("copy", "copywriting", status="passed"),
        "image": task("image", "image_generation", status="planned"),
        "video": task("video", "video_generation", depends_on=["image"]),
    }
    monkeypatch.setattr(orchestrator, "run_worker", lambda *_: (_ for _ in ()).throw(RuntimeError("quota depleted")))
    monkeypatch.setattr(orchestrator, "publish_task", lambda *_: None)
    monkeypatch.setattr(orchestrator, "publish_dlq", lambda *_: None)
    monkeypatch.setattr(orchestrator, "persist_campaign_task_state", lambda *_: True)
    monkeypatch.setattr(orchestrator.time, "sleep", lambda *_: None)

    for _ in range(MAX_RETRY + 1):
        process_task(campaign_id, "image")
    state = orchestrator.task_state[campaign_id]
    assert state["image"].status == "failed"
    assert state["video"].status == "blocked"
    assert state["video"].blocked_by_task_id == "image"
    assert state["copy"].status == "passed"


def test_retry_delay_is_bounded():
    assert next_retry_delay(1) == 5.0
    assert next_retry_delay(20) == 300.0


def test_quota_failure_does_not_retry_forever(monkeypatch):
    campaign_id = "campaign-finite"
    orchestrator.task_state[campaign_id] = {"image": task("image", "image_generation", status="planned")}
    attempts = []
    monkeypatch.setattr(orchestrator, "run_worker", lambda *_: (attempts.append(1), (_ for _ in ()).throw(RuntimeError("quota")))[1])
    monkeypatch.setattr(orchestrator, "publish_task", lambda *_: None)
    monkeypatch.setattr(orchestrator, "publish_dlq", lambda *_: None)
    monkeypatch.setattr(orchestrator, "persist_campaign_task_state", lambda *_: True)
    monkeypatch.setattr(orchestrator.time, "sleep", lambda *_: None)

    for _ in range(MAX_RETRY + 1):
        process_task(campaign_id, "image")
    assert orchestrator.task_state[campaign_id]["image"].status == "failed"
    assert len(attempts) == MAX_RETRY + 1


def test_persistence_failure_is_reported(monkeypatch, caplog):
    monkeypatch.setattr(orchestrator, "task_state_store", type("BrokenStore", (), {"save_campaign_tasks": lambda *_: (_ for _ in ()).throw(RuntimeError("database unavailable"))})())
    assert orchestrator.persist_campaign_task_state("camp", {}) is False
    assert "persistence_error" in caplog.text


def test_structured_orchestrator_secret_fields_are_redacted():
    detail = orchestrator.sanitize_error_detail("{'authorization': 'Bearer supersecret', 'nested': {'credentials': {'token': 'abc'}}}")
    assert "supersecret" not in detail
    assert "Bearer supersecret" not in detail
    assert "provider-key" not in detail
    assert "abc" not in detail


def test_dispatch_does_not_publish_when_persistence_fails(monkeypatch):
    published = []
    monkeypatch.setattr(orchestrator, "persist_campaign_task_state", lambda *_: False)
    monkeypatch.setattr(orchestrator, "publish_task", lambda *args: published.append(args))
    response = dispatch(DispatchRequest(campaign_id="camp-durable", tasks=[task("copy", "copywriting")]))
    assert response.status == "persistence_failed"
    assert published == []


def test_process_task_logs_final_persistence_failure(monkeypatch, caplog):
    campaign_id = "camp-final-durable"
    orchestrator.task_state[campaign_id] = {"copy": task("copy", "copywriting", status="planned")}
    monkeypatch.setattr(orchestrator, "run_worker", lambda *_: {})
    monkeypatch.setattr(orchestrator, "publish_task", lambda *_: None)
    monkeypatch.setattr(orchestrator, "persist_campaign_task_state", lambda *_: False)
    process_task(campaign_id, "copy")
    assert orchestrator.task_state[campaign_id]["copy"].status == "retrying"
    assert "persistence_error" in caplog.text
