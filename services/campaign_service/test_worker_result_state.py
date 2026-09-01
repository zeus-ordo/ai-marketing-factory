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

from app.main import apply_worker_result_state, classify_worker_error, sanitize_worker_error_detail
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
