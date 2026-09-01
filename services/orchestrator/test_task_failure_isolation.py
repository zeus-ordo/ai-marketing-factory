import os
import threading
import time
import pytest
from urllib.error import HTTPError

os.environ.setdefault("POSTGRES_DSN", "")

from app.main import MAX_RETRY, classify_worker_error, next_retry_delay, process_task, dispatch, reclaim_pending_messages
from app.schemas import DispatchRequest, OrchestratorTask, TaskCompleteRequest
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


def test_queue_message_is_not_acknowledged_when_task_persistence_fails(monkeypatch):
    acknowledged = []
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: False)
    monkeypatch.setattr(orchestrator, "redis_client", type("Redis", (), {"xack": lambda *_args: acknowledged.append(_args)})())
    assert orchestrator.process_queue_message("task.image", "1-0", {"campaign_id": "camp", "task_id": "image"}) is False
    assert acknowledged == []


def test_ack_exception_retains_message_and_task_claims(monkeypatch):
    released = []

    class Redis:
        def set(self, *_args, **_kwargs):
            return True

        def eval(self, script, _keys, key, *_args):
            if "del" in script:
                released.append(key)
            return 1

        def xack(self, *_args):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: True)

    with pytest.raises(RuntimeError, match="redis unavailable"):
        orchestrator.process_queue_message("task.image", "ack-error", {"campaign_id": "camp", "task_id": "image"})

    assert released == []


def test_renewal_failure_immediately_before_ack_leaves_message_pending(monkeypatch):
    acknowledged = []
    renewals = []

    class Redis:
        def set(self, *_args, **_kwargs):
            return True

        def eval(self, script, _keys, key, *_args):
            if "pexpire" in script:
                renewals.append(key)
                return 0
            return 1

        def xack(self, *args):
            acknowledged.append(args)

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: True)
    monkeypatch.setattr(orchestrator, "LEASE_HEARTBEAT_INTERVAL_SECONDS", 60)

    assert orchestrator.process_queue_message(
        "task.image", "final-renewal-loss", {"campaign_id": "camp", "task_id": "image"}
    ) is False
    assert renewals
    assert acknowledged == []


def test_message_lease_is_renewed_while_task_runs(monkeypatch):
    acknowledged = []
    renewals = []
    started = threading.Event()
    release = threading.Event()

    class Redis:
        def set(self, key, token, nx=False, ex=None):
            return True

        def eval(self, script, _keys, key, token, *_args):
            if "pexpire" in script:
                renewals.append((key, token))
                return 1
            return 1

        def xack(self, *args):
            acknowledged.append(args)

    def process(*_args):
        started.set()
        assert release.wait(timeout=3)
        return True

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", process)
    monkeypatch.setattr(orchestrator, "MESSAGE_CLAIM_TTL_SECONDS", 3)
    monkeypatch.setattr(orchestrator, "LEASE_HEARTBEAT_INTERVAL_SECONDS", 0.01)

    worker = threading.Thread(
        target=orchestrator.process_queue_message,
        args=("task.image", "1-0", {"campaign_id": "camp", "task_id": "image"}),
    )
    worker.start()
    assert started.wait(timeout=2)
    time.sleep(0.05)
    release.set()
    worker.join(timeout=2)

    assert renewals
    assert acknowledged == [("task.image", orchestrator.GROUP_NAME, "1-0")]


def test_message_lease_renewal_failure_does_not_ack(monkeypatch):
    acknowledged = []

    class Redis:
        def set(self, *_args, **_kwargs):
            return True

        def eval(self, script, *_args):
            return 0 if "pexpire" in script else 1

        def xack(self, *args):
            acknowledged.append(args)

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: (time.sleep(0.05), True)[1])
    monkeypatch.setattr(orchestrator, "LEASE_HEARTBEAT_INTERVAL_SECONDS", 0.01)

    assert orchestrator.process_queue_message(
        "task.image", "renewal-loss", {"campaign_id": "camp", "task_id": "image"}
    ) is False
    assert acknowledged == []


def test_active_message_ids_are_scoped_by_stream(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    processed = []

    class Redis:
        def set(self, *_args, **_kwargs):
            return True

        def eval(self, *_args):
            return 1

        def xack(self, *_args):
            pass

    def process(*args):
        processed.append(args)
        entered.set()
        assert release.wait(timeout=2)
        return True

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", process)
    first = threading.Thread(target=orchestrator.process_queue_message, args=("task.image", "1-0", {"campaign_id": "a", "task_id": "t"}))
    second = threading.Thread(target=orchestrator.process_queue_message, args=("task.video", "1-0", {"campaign_id": "b", "task_id": "t"}))
    first.start()
    assert entered.wait(timeout=2)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert len(processed) == 2


def test_duplicate_task_entry_leaves_message_pending(monkeypatch):
    acknowledged = []
    sets = {}

    class Redis:
        def set(self, key, token, nx=False, ex=None):
            if nx and key in sets:
                return False
            sets[key] = token
            return True

        def eval(self, *_args):
            return 1

        def xack(self, *args):
            acknowledged.append(args)

    calls = []
    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", lambda *args: calls.append(args) or True)
    assert orchestrator.process_queue_message("task.image", "1-0", {"campaign_id": "camp", "task_id": "image"}) is True
    assert orchestrator.process_queue_message("task.image", "2-0", {"campaign_id": "camp", "task_id": "image"}) is False
    assert calls == [("camp", "image")]
    assert acknowledged == [("task.image", orchestrator.GROUP_NAME, "1-0")]


def test_task_claim_failure_leaves_message_pending_without_ack(monkeypatch):
    acknowledged = []

    class Redis:
        def set(self, key, *_args, **_kwargs):
            return not key.startswith("orchestrator:task-claim:")

        def xack(self, *args):
            acknowledged.append(args)

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: (_ for _ in ()).throw(AssertionError("must not dispatch")))
    assert orchestrator.process_queue_message("task.image", "1-0", {"campaign_id": "camp", "task_id": "image"}) is False
    assert acknowledged == []


def test_queue_message_is_not_acknowledged_when_task_load_fails(monkeypatch):
    acknowledged = []
    load_attempts = []
    delays = []

    class BrokenStore:
        def load_campaign_tasks(self, *_args):
            load_attempts.append(1)
            raise RuntimeError("database unavailable")

    orchestrator.task_state.pop("camp-load-failure", None)
    monkeypatch.setattr(orchestrator, "task_state_store", BrokenStore())
    monkeypatch.setattr(orchestrator.time, "sleep", lambda delay: delays.append(delay))
    monkeypatch.setattr(orchestrator, "redis_client", type("Redis", (), {"xack": lambda *_args: acknowledged.append(_args)})())

    assert orchestrator.process_queue_message(
        "task.image", "1-0", {"campaign_id": "camp-load-failure", "task_id": "image"}
    ) is False
    assert len(load_attempts) == MAX_RETRY + 1
    assert delays == [next_retry_delay(1), next_retry_delay(2)]
    assert acknowledged == []


def test_pending_queue_message_is_reclaimed_and_retried_after_storage_recovers(monkeypatch):
    acknowledged = []
    attempts = []

    class Redis:
        def xautoclaim(self, **kwargs):
            assert kwargs["min_idle_time"] == orchestrator.PENDING_MESSAGE_IDLE_MS
            if kwargs["name"] != "task.copy":
                return ("0-0", [], [])
            return ("0-0", [("1-0", {"campaign_id": "camp", "task_id": "image"})], [])

        def xack(self, *args):
            acknowledged.append(args)

    def process(_campaign_id, _task_id):
        attempts.append(1)
        return len(attempts) > 1

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "process_task", process)

    assert reclaim_pending_messages() == 1
    assert acknowledged == []
    assert reclaim_pending_messages() == 1
    assert acknowledged == [("task.copy", orchestrator.GROUP_NAME, "1-0")]
    assert len(attempts) == 2


def test_pending_queue_message_is_not_reclaimed_while_active(monkeypatch):
    processed = []

    class Redis:
        def xautoclaim(self, **kwargs):
            return ("0-0", [("active-1", {"campaign_id": "camp", "task_id": "copy"})], [])

        def xack(self, *args):
            raise AssertionError("active message must not be acknowledged by recovery")

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "TOPICS", ["task.copy"])
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: processed.append(1))
    with orchestrator.active_message_ids_lock:
        orchestrator.active_message_ids.add("task.copy:active-1")
    try:
        assert orchestrator.reclaim_pending_messages() == 0
    finally:
        with orchestrator.active_message_ids_lock:
            orchestrator.active_message_ids.discard("task.copy:active-1")
    assert processed == []


def test_pending_queue_recovery_paginates_past_first_batch(monkeypatch):
    starts = []
    processed = []
    first_batch = [(f"{index}-0", {"campaign_id": "camp", "task_id": "copy"}) for index in range(10)]
    later_batch = [("11-0", {"campaign_id": "camp", "task_id": "copy"})]

    class Redis:
        def xautoclaim(self, **kwargs):
            starts.append(kwargs["start_id"])
            if kwargs["start_id"] == "0-0":
                return ("10-0", first_batch, [])
            return ("0-0", later_batch, [])

        def xack(self, *_args):
            pass

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "TOPICS", ["task.copy"])
    monkeypatch.setattr(orchestrator, "process_task", lambda *_: processed.append(1) or True)
    assert orchestrator.reclaim_pending_messages() == 11
    assert starts == ["0-0", "10-0"]
    assert len(processed) == 11


def test_pending_queue_recovery_accepts_byte_cursor(monkeypatch):
    starts = []

    class Redis:
        def xautoclaim(self, **kwargs):
            starts.append(kwargs["start_id"])
            if kwargs["start_id"] == "0-0":
                return (b"10-0", [], [])
            return (b"0-0", [("1-0", {"campaign_id": "camp", "task_id": "copy"})], [])

    monkeypatch.setattr(orchestrator, "redis_client", Redis())
    monkeypatch.setattr(orchestrator, "TOPICS", ["task.copy"])
    monkeypatch.setattr(orchestrator, "process_queue_message", lambda *_: True)
    assert orchestrator.reclaim_pending_messages() == 1
    assert starts == ["0-0", b"10-0"]


def test_hydration_does_not_hold_global_lock_during_database_io(monkeypatch):
    campaign_id = "camp-lock-scope"
    entered = threading.Event()
    release = threading.Event()
    hydrated = {"image": task("image", "image_generation")}

    class SlowStore:
        def load_campaign_tasks(self, _campaign_id):
            entered.set()
            assert release.wait(timeout=2)
            return list(hydrated.values())

    orchestrator.task_state.pop(campaign_id, None)
    monkeypatch.setattr(orchestrator, "task_state_store", SlowStore())
    result = []
    worker = threading.Thread(target=lambda: result.append(orchestrator.get_or_hydrate_campaign_tasks(campaign_id)))
    worker.start()
    assert entered.wait(timeout=2)
    with orchestrator.task_state_lock:
        orchestrator.task_state[campaign_id] = {"copy": task("copy", "copywriting")}
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert result[0] == orchestrator.task_state[campaign_id]
    assert "copy" in result[0]


def test_concurrent_hydration_loads_campaign_once(monkeypatch):
    campaign_id = "camp-single-flight"
    entered = threading.Event()
    release = threading.Event()
    load_count = []

    class SlowStore:
        def load_campaign_tasks(self, _campaign_id):
            load_count.append(1)
            entered.set()
            assert release.wait(timeout=2)
            return [task("image", "image_generation")]

    orchestrator.task_state.pop(campaign_id, None)
    monkeypatch.setattr(orchestrator, "task_state_store", SlowStore())
    results = []
    workers = [
        threading.Thread(target=lambda: results.append(orchestrator.get_or_hydrate_campaign_tasks(campaign_id)))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    assert entered.wait(timeout=2)
    release.set()
    for worker in workers:
        worker.join(timeout=2)

    assert all(not worker.is_alive() for worker in workers)
    assert len(load_count) == 1
    assert results[0] is results[1]


def test_task_complete_rolls_back_when_persistence_fails(monkeypatch):
    campaign_id = "camp-rollback"
    original = {"copy": task("copy", "copywriting", status="passed"), "video": task("video", "video_generation", ["copy"])}
    orchestrator.task_state[campaign_id] = original
    monkeypatch.setattr(orchestrator, "persist_campaign_task_state", lambda *_: False)
    with pytest.raises(orchestrator.HTTPException) as exc:
        orchestrator.task_complete(TaskCompleteRequest(campaign_id=campaign_id, task_id="copy", result="passed"))
    assert exc.value.status_code == 503
    assert orchestrator.task_state[campaign_id]["copy"].status == "passed"
    assert orchestrator.task_state[campaign_id]["video"].status == "pending"
