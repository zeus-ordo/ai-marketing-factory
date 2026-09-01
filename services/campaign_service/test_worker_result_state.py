import os
import sys
from pathlib import Path

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")

# Both services use an ``app`` package; make combined pytest invocation load this service.
loaded_app_main = sys.modules.get("app.main")
if loaded_app_main is None or "campaign_service" not in str(getattr(loaded_app_main, "__file__", "")):
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app.main import apply_worker_result_state, classify_worker_error, normalize_task_payload, sanitize_worker_error_detail
from app.schemas import TaskRecord


def task(task_id, task_type, depends_on=(), status="pending"):
    return TaskRecord(
        company_id="co-1", task_id=task_id, campaign_id="camp-1", task_type=task_type,
        status=status, priority=1, depends_on=list(depends_on), acceptance=[]
    )


def test_worker_failure_sets_blocked_reason_without_blocking_unrelated_tasks():
    tasks = [task("image", "image_generation", status="running"), task("video", "video_generation", ["image"]), task("copy", "copywriting")]
    updated = apply_worker_result_state(tasks, "image", {"status": "failed", "error": "quota exceeded"})
    by_id = {item.task_id: item for item in updated}
    assert by_id["image"].status == "failed"
    assert by_id["video"].status == "blocked"
    assert by_id["video"].blocked_reason == "blocked by failed task image"
    assert by_id["copy"].status == "pending"


def test_single_task_retry_resets_failed_task_and_blocked_descendants():
    tasks = [task("image", "image_generation", status="failed"), task("video", "video_generation", ["image"], "blocked"), task("copy", "copywriting", status="passed")]
    updated = apply_worker_result_state(tasks, "image", {"status": "retrying"})
    by_id = {item.task_id: item for item in updated}
    assert by_id["image"].status == "retrying"
    assert by_id["video"].status == "pending"
    assert by_id["copy"].status == "passed"


def test_error_detail_redacts_secrets():
    detail = sanitize_worker_error_detail("https://worker/run?api_key=secret-token password=hunter2")
    assert "secret-token" not in detail
    assert "hunter2" not in detail
    assert classify_worker_error(RuntimeError("HTTP 429 quota exceeded")) == "quota"


def test_normalize_preserves_blocked_task_diagnostics():
    normalized = normalize_task_payload({
        "task_id": "video", "task_type": "video_generation", "status": "blocked",
        "blocked_by_task_id": "image", "blocked_reason": "blocked by failed task image",
    }, "camp-1")
    assert normalized.status == "blocked"
    assert normalized.blocked_by_task_id == "image"
    assert normalized.blocked_reason == "blocked by failed task image"


def test_retry_success_returns_passed_persisted_state():
    tasks = [task("image", "image_generation", status="retrying")]
    updated = apply_worker_result_state(tasks, "image", {"status": "passed"})
    assert updated[0].status == "passed"


def test_retry_dispatch_failure_is_terminal_but_retryable():
    failed = apply_worker_result_state(
        [task("image", "image_generation", status="retrying"), task("video", "video_generation", ["image"], "pending")],
        "image", {"status": "failed", "error": "provider secret=do-not-leak"}
    )
    assert failed[0].status == "failed"
    assert failed[1].status == "blocked"
    retried = apply_worker_result_state(failed, "image", {"status": "retrying"})
    assert retried[0].status == "retrying"
    assert retried[1].status == "pending"


def test_structured_secret_fields_are_redacted():
    detail = sanitize_worker_error_detail('{"api_key":"provider-key", "credentials":{"token":"abc", "password":"pw"}}')
    assert "provider-key" not in detail
    assert "abc" not in detail
    assert "pw" not in detail
