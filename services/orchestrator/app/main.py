import importlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

logger = logging.getLogger("orchestrator")

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from .schemas import (
    DispatchRequest,
    DispatchResponse,
    OrchestratorTask,
    TaskCompleteRequest,
    TaskCompleteResponse,
    TaskStateResponse,
)


class EventRunResponse(BaseModel):
    campaign_id: str
    processed_task_id: str | None
    worker_topic: str | None
    tasks: list[OrchestratorTask]


class QueueTopicHealth(BaseModel):
    topic: str
    length: int
    pending: int
    lag: int


class DlqItem(BaseModel):
    message_id: str
    campaign_id: str
    task_id: str
    task_type: str
    reason: str


class QueueHealthResponse(BaseModel):
    topics: list[QueueTopicHealth]
    dlq_size: int
    dlq_recent: list[DlqItem]


class HealthCheckResponse(BaseModel):
    redis_ok: bool
    workers: dict[str, bool]


class HealthCheckRequest(BaseModel):
    operator: str | None = None


class PurgeTopicRequest(BaseModel):
    topic: str
    operator: str | None = None


class PurgeTopicResponse(BaseModel):
    topic: str
    purged: bool


class TrimTopicRequest(BaseModel):
    topic: str
    maxlen: int = 500
    operator: str | None = None


class TrimTopicResponse(BaseModel):
    topic: str
    maxlen: int
    trimmed: int


class RetryDlqRequest(BaseModel):
    message_id: str
    operator: str | None = None


class RetryDlqResponse(BaseModel):
    message_id: str
    retried: bool
    detail: str


class OperationAuditEntry(BaseModel):
    timestamp: str
    operator: str
    operation: str
    target: str
    result: str
    detail: str


class OperationAuditResponse(BaseModel):
    items: list[OperationAuditEntry]
    total: int
    page: int
    page_size: int


@dataclass
class AuditQueryResult:
    items: list[dict[str, str]]
    total: int


class OperationAuditStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._psycopg = importlib.import_module("psycopg")

    def _connect(self):
        return self._psycopg.connect(self._dsn)

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS operation_audit_logs (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        operator TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        target TEXT NOT NULL,
                        result TEXT NOT NULL,
                        detail TEXT NOT NULL
                    );
                    """
                )
            conn.commit()

    def append(self, timestamp: str, operator: str, operation: str, target: str, result: str, detail: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO operation_audit_logs
                        (timestamp, operator, operation, target, result, detail)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (timestamp, operator, operation, target, result, detail),
                )
            conn.commit()

    def query(
        self,
        page: int,
        page_size: int,
        operator: str | None,
        operation: str | None,
        result: str | None,
        from_ts: str | None,
        to_ts: str | None,
    ) -> AuditQueryResult:
        conditions: list[str] = []
        params: list[object] = []

        if operator:
            conditions.append("operator = %s")
            params.append(operator)
        if operation:
            conditions.append("operation = %s")
            params.append(operation)
        if result:
            conditions.append("result = %s")
            params.append(result)
        if from_ts:
            conditions.append("timestamp >= %s")
            params.append(from_ts)
        if to_ts:
            conditions.append("timestamp <= %s")
            params.append(to_ts)

        where_sql = ""
        if conditions:
            where_sql = " WHERE " + " AND ".join(conditions)

        offset = (page - 1) * page_size
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM operation_audit_logs{where_sql};", params)
                total = int(cur.fetchone()[0])

                cur.execute(
                    f"""
                    SELECT timestamp, operator, operation, target, result, detail
                    FROM operation_audit_logs
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT %s OFFSET %s;
                    """,
                    [*params, page_size, offset],
                )
                rows = cur.fetchall()

        items = [
            {
                "timestamp": row[0].isoformat(),
                "operator": row[1],
                "operation": row[2],
                "target": row[3],
                "result": row[4],
                "detail": row[5],
            }
            for row in rows
        ]
        return AuditQueryResult(items=items, total=total)


class TaskStateStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._psycopg = importlib.import_module("psycopg")

    def _connect(self):
        return self._psycopg.connect(self._dsn)

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orchestrator_task_state (
                        task_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        task_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        priority INTEGER NOT NULL,
                        company_id TEXT NOT NULL DEFAULT '',
                        run_id TEXT NOT NULL DEFAULT '',
                        depends_on_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        acceptance_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        worker_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute("ALTER TABLE orchestrator_task_state ADD COLUMN IF NOT EXISTS company_id TEXT NOT NULL DEFAULT '';")
                cur.execute("ALTER TABLE orchestrator_task_state ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT '';")
                cur.execute("ALTER TABLE orchestrator_task_state ADD COLUMN IF NOT EXISTS worker_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_orchestrator_task_state_campaign_priority
                    ON orchestrator_task_state (campaign_id, priority ASC, updated_at ASC);
                    """
                )
            conn.commit()

    def save_campaign_tasks(self, campaign_id: str, tasks: list[OrchestratorTask]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM orchestrator_task_state WHERE campaign_id = %s", (campaign_id,))
                for task in tasks:
                    cur.execute(
                        """
                        INSERT INTO orchestrator_task_state
                            (task_id, campaign_id, task_type, status, priority, company_id, run_id, depends_on_json, acceptance_json, worker_payload_json, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, NOW())
                        ON CONFLICT (task_id) DO UPDATE SET
                            campaign_id = EXCLUDED.campaign_id,
                            task_type = EXCLUDED.task_type,
                            status = EXCLUDED.status,
                            priority = EXCLUDED.priority,
                            company_id = EXCLUDED.company_id,
                            run_id = EXCLUDED.run_id,
                            depends_on_json = EXCLUDED.depends_on_json,
                            acceptance_json = EXCLUDED.acceptance_json,
                            worker_payload_json = EXCLUDED.worker_payload_json,
                            updated_at = NOW();
                        """,
                        (
                            task.task_id,
                            campaign_id,
                            task.task_type,
                            task.status,
                            task.priority,
                            task.company_id,
                            task.run_id,
                            json.dumps(task.depends_on),
                            json.dumps(task.acceptance),
                            json.dumps(task.worker_payload),
                        ),
                    )
            conn.commit()

    def load_campaign_tasks(self, campaign_id: str) -> list[OrchestratorTask]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, task_type, status, priority, company_id, run_id, depends_on_json, acceptance_json, worker_payload_json
                    FROM orchestrator_task_state
                    WHERE campaign_id = %s
                    ORDER BY priority ASC, updated_at ASC;
                    """,
                    (campaign_id,),
                )
                rows = cur.fetchall()
        return [
            OrchestratorTask(
                task_id=row[0],
                task_type=row[1],
                status=row[2],
                priority=row[3],
                company_id=row[4] or "",
                run_id=row[5] or "",
                depends_on=list(row[6] or []),
                acceptance=list(row[7] or []),
                worker_payload=dict(row[8] or {}),
            )
            for row in rows
        ]


app = FastAPI(
    title="Marketing AI Factory - Orchestrator",
    version="0.3.0",
    description="Event-driven orchestrator with Redis streams, retry, and DLQ.",
)

task_state: dict[str, dict[str, OrchestratorTask]] = {}
task_state_lock = threading.Lock()
retry_state: dict[str, int] = {}
retry_state_lock = threading.Lock()
operation_audit_logs: list[OperationAuditEntry] = []
operation_rate_limit_state: dict[str, list[float]] = {}

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")
WORKER_COPY_URL = os.getenv("WORKER_COPY_URL", "http://worker-copy:8091")
WORKER_IMAGE_URL = os.getenv("WORKER_IMAGE_URL", "http://worker-image:8092")
WORKER_VIDEO_URL = os.getenv("WORKER_VIDEO_URL", "http://worker-video:8093")
WORKER_ADS_URL = os.getenv("WORKER_ADS_URL", "http://worker-ads:8094")
WORKER_REQUEST_TIMEOUT_SECONDS = max(15.0, float(os.getenv("WORKER_REQUEST_TIMEOUT_SECONDS", "180")))
CAMPAIGN_SERVICE_URL = os.getenv("CAMPAIGN_SERVICE_URL", "http://campaign-service:8080").strip()
INTERNAL_API_KEY = os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip() or os.getenv("INTERNAL_API_KEY", "").strip()

GROUP_NAME = "orchestrator"
CONSUMER_NAME = "orchestrator-1"
MAX_RETRY = 2
OPS_RATE_LIMIT = 20
OPS_WINDOW_SECONDS = 60

redis_module = importlib.import_module("redis")
redis_client = redis_module.Redis.from_url(REDIS_URL, decode_responses=True)

audit_store: OperationAuditStore | None = None
task_state_store: TaskStateStore | None = None
if POSTGRES_DSN:
    try:
        candidate_audit_store = OperationAuditStore(POSTGRES_DSN)
        candidate_audit_store.initialize()
        audit_store = candidate_audit_store
    except Exception:
        audit_store = None
    try:
        candidate_task_state_store = TaskStateStore(POSTGRES_DSN)
        candidate_task_state_store.initialize()
        task_state_store = candidate_task_state_store
    except Exception:
        task_state_store = None

TASK_TOPIC_MAP: dict[str, str] = {
    "copywriting": "task.copy",
    "image_generation": "task.image",
    "video_generation": "task.video",
    "ads_strategy": "task.ads",
}

TOPICS = list(TASK_TOPIC_MAP.values())
DLQ_TOPIC = "task.dlq"


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with request.urlopen(req, timeout=WORKER_REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = f" HTTP response body: {body[:1000]}" if body else ""
        raise RuntimeError(f"Worker request failed for {url}: HTTP Error {exc.code}: {exc.reason}.{detail}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Worker request failed for {url}: {exc}") from exc


def get_json(url: str) -> dict[str, Any]:
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=WORKER_REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = f" HTTP response body: {body[:1000]}" if body else ""
        raise RuntimeError(f"Worker request failed for {url}: HTTP Error {exc.code}: {exc.reason}.{detail}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Worker request failed for {url}: {exc}") from exc


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_operation_audit(operator: str, operation: str, target: str, result: str, detail: str) -> None:
    timestamp = utc_now_iso()
    operation_audit_logs.append(
        OperationAuditEntry(
            timestamp=timestamp,
            operator=operator,
            operation=operation,
            target=target,
            result=result,
            detail=detail,
        )
    )
    if len(operation_audit_logs) > 300:
        del operation_audit_logs[0 : len(operation_audit_logs) - 300]

    if audit_store is not None:
        try:
            audit_store.append(timestamp, operator, operation, target, result, detail)
        except Exception as exc:
            logger.warning(f"Failed to append audit log: {exc}")


def persist_campaign_task_state(campaign_id: str, campaign_tasks: dict[str, OrchestratorTask]) -> None:
    if task_state_store is None:
        return
    try:
        task_state_store.save_campaign_tasks(campaign_id, list(campaign_tasks.values()))
    except Exception:
        pass


def get_or_hydrate_campaign_tasks(campaign_id: str) -> dict[str, OrchestratorTask] | None:
    with task_state_lock:
        campaign_tasks = task_state.get(campaign_id)
        if campaign_tasks is not None:
            return campaign_tasks
        if task_state_store is None:
            return None
        try:
            loaded = task_state_store.load_campaign_tasks(campaign_id)
        except Exception:
            return None
        if not loaded:
            return None
        hydrated = {task.task_id: task for task in loaded}
        task_state[campaign_id] = hydrated
        return hydrated


def check_and_mark_operation_rate_limit(operator: str, operation: str) -> bool:
    key = f"{operator}:{operation}"
    now = time.time()
    window_start = now - OPS_WINDOW_SECONDS
    history = operation_rate_limit_state.get(key, [])
    filtered = [value for value in history if value >= window_start]
    if len(filtered) >= OPS_RATE_LIMIT:
        operation_rate_limit_state[key] = filtered
        return False

    filtered.append(now)
    operation_rate_limit_state[key] = filtered
    return True


def mark_ready_tasks_as_planned(campaign_tasks: dict[str, OrchestratorTask]) -> list[OrchestratorTask]:
    next_tasks: list[OrchestratorTask] = []
    for task in campaign_tasks.values():
        if task.status != "pending":
            continue
        ready = all(
            campaign_tasks.get(dep_id) is not None and campaign_tasks[dep_id].status == "passed"
            for dep_id in task.depends_on
        )
        if ready:
            task.status = "planned"
            next_tasks.append(task)
    return next_tasks


def publish_task(topic: str, campaign_id: str, task: OrchestratorTask) -> None:
    redis_client.xadd(
        topic,
        {
            "campaign_id": campaign_id,
            "task_id": task.task_id,
            "task_type": task.task_type,
        },
    )


def publish_dlq(campaign_id: str, task: OrchestratorTask, reason: str) -> None:
    redis_client.xadd(
        "task.dlq",
        {
            "campaign_id": campaign_id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "reason": reason,
        },
    )


def run_worker(task: OrchestratorTask, campaign_id: str) -> dict[str, Any]:
    """
    Run a worker task and report the result back to campaign_service.
    Returns the worker response for further processing.
    """
    company_id = task.company_id or ""
    run_id = task.run_id or ""
    worker_payload = dict(task.worker_payload or {})

    if task.task_type == "copywriting":
        payload = {
            "task_id": task.task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "prompt": "Generate conversion-focused copy",
            "brand_context": {"tone": ["premium", "minimal"]},
            "variants": 3,
        }
        payload.update(worker_payload)
        result = post_json(
            f"{WORKER_COPY_URL}/internal/workers/copy/run",
            payload,
        )
        _report_worker_result_to_campaign_service(task.task_type, result, campaign_id, company_id, run_id)
        return result
    elif task.task_type == "image_generation":
        payload = {
            "task_id": task.task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "prompt": "Generate premium campaign visuals",
            "sizes": ["1080x1080", "1080x1350"],
            "style_profile": {"mood": "minimal luxury"},
        }
        payload.update(worker_payload)
        result = post_json(
            f"{WORKER_IMAGE_URL}/internal/workers/image/run",
            payload,
        )
        _report_worker_result_to_campaign_service(task.task_type, result, campaign_id, company_id, run_id)
        return result
    elif task.task_type == "video_generation":
        payload = {
            "task_id": task.task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "prompt": "Generate short social video",
            "duration": 6,
            "aspect_ratio": "9:16",
        }
        payload.update(worker_payload)
        result = post_json(
            f"{WORKER_VIDEO_URL}/internal/workers/video/run",
            payload,
        )
        _report_worker_result_to_campaign_service(task.task_type, result, campaign_id, company_id, run_id)
        return result
    elif task.task_type == "ads_strategy":
        payload = {
            "task_id": task.task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "objective": "conversion",
            "budget": 100000,
            "platforms": ["facebook", "instagram", "google_display"],
        }
        payload.update(worker_payload)
        result = post_json(
            f"{WORKER_ADS_URL}/internal/workers/ads/run",
            payload,
        )
        _report_worker_result_to_campaign_service(task.task_type, result, campaign_id, company_id, run_id)
        return result
    return {}


def _report_worker_result_to_campaign_service(task_type: str, result: dict[str, Any], campaign_id: str, company_id: str, run_id: str) -> None:
    """Report worker result to campaign_service. Failure is logged but non-blocking to allow failover mechanism to handle."""
    if not CAMPAIGN_SERVICE_URL or not INTERNAL_API_KEY:
        logger.warning("Orchestrator: CAMPAIGN_SERVICE_URL or INTERNAL_API_KEY not configured, skipping result report")
        return

    import urllib.request as _req
    import json as _json

    payload = {
        "task_type": task_type,
        "result": {
            **result,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "run_id": run_id,
        },
    }

    try:
        req = _req.Request(
            f"{CAMPAIGN_SERVICE_URL}/internal/workers/results",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Internal-Api-Key": INTERNAL_API_KEY,
            },
            data=_json.dumps(payload).encode("utf-8"),
        )
        with _req.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
            logger.info(f"Worker result reported to campaign_service: {body}")
    except Exception as exc:
        # Log as error (not warning) since this means assets may not be persisted
        # The campaign_service failover mechanism (generate_outputs_via_workers) should handle this
        logger.error(f"Orchestrator: failed to report worker result to campaign_service: {exc}")


def process_task(campaign_id: str, task_id: str) -> None:
    campaign_tasks = get_or_hydrate_campaign_tasks(campaign_id)
    if campaign_tasks is None:
        return

    task = campaign_tasks.get(task_id)
    if task is None:
        return

    task.status = "running"
    campaign_tasks[task_id] = task

    retry_key = f"{campaign_id}:{task_id}"

    try:
        run_worker(task, campaign_id)
        task.status = "passed"
        campaign_tasks[task_id] = task

        next_tasks = mark_ready_tasks_as_planned(campaign_tasks)
        for next_task in next_tasks:
            publish_task(TASK_TOPIC_MAP[next_task.task_type], campaign_id, next_task)
        with retry_state_lock:
            retry_state.pop(retry_key, None)
    except RuntimeError as exc:
        with retry_state_lock:
            current_retry = retry_state.get(retry_key, 0) + 1
            retry_state[retry_key] = current_retry

        if current_retry <= MAX_RETRY:
            task.status = "retrying"
            campaign_tasks[task_id] = task
            task.status = "planned"
            campaign_tasks[task_id] = task
            publish_task(TASK_TOPIC_MAP[task.task_type], campaign_id, task)
        else:
            task.status = "failed"
            campaign_tasks[task_id] = task
            publish_dlq(campaign_id, task, str(exc))

    # Persist to Postgres FIRST, then update in-memory state.
    # This ensures that if we crash between persist and memory update,
    # on restart we reload from Postgres (which has the correct state).
    persist_campaign_task_state(campaign_id, campaign_tasks)
    with task_state_lock:
        task_state[campaign_id] = campaign_tasks


def ensure_groups() -> None:
    for topic in TOPICS:
        try:
            redis_client.xgroup_create(topic, GROUP_NAME, id="0", mkstream=True)
        except Exception:
            pass

    try:
        redis_client.xgroup_create(DLQ_TOPIC, GROUP_NAME, id="0", mkstream=True)
    except Exception:
        pass


def consumer_loop() -> None:
    ensure_groups()
    streams_dict = {topic: ">" for topic in TOPICS}

    while True:
        try:
            messages = redis_client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams=streams_dict,
                count=10,
                block=1000,
            )
        except Exception as exc:
            logger.warning(f"Consumer loop: xreadgroup failed: {exc}")
            time.sleep(1)
            continue

        if not messages:
            continue

        for stream_name, stream_messages in messages:
            for message_id, fields in stream_messages:
                campaign_id = fields.get("campaign_id")
                task_id = fields.get("task_id")
                if campaign_id and task_id:
                    process_task(campaign_id, task_id)
                redis_client.xack(stream_name, GROUP_NAME, message_id)


@app.on_event("startup")
def start_consumer() -> None:
    thread = threading.Thread(target=consumer_loop, daemon=True)
    thread.start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/orchestrator/dispatch", response_model=DispatchResponse)
def dispatch(payload: DispatchRequest) -> DispatchResponse:
    campaign_tasks: dict[str, OrchestratorTask] = {}
    for task in payload.tasks:
        task.status = "planned" if len(task.depends_on) == 0 else "pending"
        campaign_tasks[task.task_id] = task

    with task_state_lock:
        task_state[payload.campaign_id] = campaign_tasks
    persist_campaign_task_state(payload.campaign_id, campaign_tasks)

    for task in campaign_tasks.values():
        if task.status == "planned":
            topic = TASK_TOPIC_MAP[task.task_type]
            publish_task(topic, payload.campaign_id, task)

    return DispatchResponse(campaign_id=payload.campaign_id, status="planned", tasks=list(campaign_tasks.values()))


@app.get("/internal/orchestrator/campaign/{campaign_id}/tasks", response_model=TaskStateResponse)
def get_campaign_tasks(campaign_id: str) -> TaskStateResponse:
    campaign_tasks = get_or_hydrate_campaign_tasks(campaign_id)
    if campaign_tasks is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return TaskStateResponse(campaign_id=campaign_id, tasks=list(campaign_tasks.values()))


@app.post("/internal/orchestrator/task-complete", response_model=TaskCompleteResponse)
def task_complete(payload: TaskCompleteRequest) -> TaskCompleteResponse:
    campaign_tasks = get_or_hydrate_campaign_tasks(payload.campaign_id)
    if campaign_tasks is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    current = campaign_tasks.get(payload.task_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Task not found")

    current.status = payload.result
    campaign_tasks[payload.task_id] = current

    next_tasks = mark_ready_tasks_as_planned(campaign_tasks)
    for task in next_tasks:
        topic = TASK_TOPIC_MAP[task.task_type]
        publish_task(topic, payload.campaign_id, task)

    with task_state_lock:
        task_state[payload.campaign_id] = campaign_tasks
    persist_campaign_task_state(payload.campaign_id, campaign_tasks)
    return TaskCompleteResponse(
        campaign_id=payload.campaign_id,
        task_id=payload.task_id,
        result=payload.result,
        next_tasks=next_tasks,
        tasks=list(campaign_tasks.values()),
    )


@app.post("/internal/orchestrator/events/run-once/{campaign_id}", response_model=EventRunResponse)
def run_once(campaign_id: str) -> EventRunResponse:
    campaign_tasks = get_or_hydrate_campaign_tasks(campaign_id)
    if campaign_tasks is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    planned_tasks = [task for task in campaign_tasks.values() if task.status == "planned"]
    if not planned_tasks:
        return EventRunResponse(campaign_id=campaign_id, processed_task_id=None, worker_topic=None, tasks=list(campaign_tasks.values()))

    task = planned_tasks[0]
    topic = TASK_TOPIC_MAP[task.task_type]
    process_task(campaign_id, task.task_id)

    refreshed = task_state.get(campaign_id, campaign_tasks)
    return EventRunResponse(
        campaign_id=campaign_id,
        processed_task_id=task.task_id,
        worker_topic=topic,
        tasks=list(refreshed.values()),
    )


@app.get("/internal/orchestrator/monitor/overview", response_model=QueueHealthResponse)
def monitor_overview() -> QueueHealthResponse:
    topic_items: list[QueueTopicHealth] = []

    for topic in TOPICS:
        length = 0
        pending = 0
        lag = 0

        try:
            length = int(redis_client.xlen(topic))
        except Exception:
            length = 0

        try:
            pending_info = redis_client.xpending(topic, GROUP_NAME)
            pending = int(pending_info.get("pending", 0)) if isinstance(pending_info, dict) else 0
        except Exception:
            pending = 0

        try:
            group_info = redis_client.xinfo_groups(topic)
            current_group = next((group for group in group_info if group.get("name") == GROUP_NAME), None)
            if current_group is not None:
                lag = int(current_group.get("lag", 0) or 0)
        except Exception:
            lag = 0

        topic_items.append(QueueTopicHealth(topic=topic, length=length, pending=pending, lag=lag))

    dlq_size = 0
    dlq_recent: list[DlqItem] = []

    try:
        dlq_size = int(redis_client.xlen(DLQ_TOPIC))
    except Exception:
        dlq_size = 0

    try:
        recent = redis_client.xrevrange(DLQ_TOPIC, count=20)
        for message_id, payload in recent:
            dlq_recent.append(
                DlqItem(
                    message_id=message_id,
                    campaign_id=str(payload.get("campaign_id", "")),
                    task_id=str(payload.get("task_id", "")),
                    task_type=str(payload.get("task_type", "")),
                    reason=str(payload.get("reason", "")),
                )
            )
    except Exception:
        dlq_recent = []

    return QueueHealthResponse(topics=topic_items, dlq_size=dlq_size, dlq_recent=dlq_recent)


@app.get("/internal/orchestrator/ops/audit-logs", response_model=OperationAuditResponse)
def operations_audit_logs(
    page: int = 1,
    page_size: int = 20,
    operator: str | None = None,
    operation: str | None = None,
    result: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> OperationAuditResponse:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))

    if audit_store is not None:
        try:
            query = audit_store.query(
                page=normalized_page,
                page_size=normalized_page_size,
                operator=operator,
                operation=operation,
                result=result,
                from_ts=from_ts,
                to_ts=to_ts,
            )
            items = [OperationAuditEntry(**item) for item in query.items]
            return OperationAuditResponse(
                items=items,
                total=query.total,
                page=normalized_page,
                page_size=normalized_page_size,
            )
        except Exception:
            pass

    filtered = operation_audit_logs
    if operator:
        filtered = [item for item in filtered if item.operator == operator]
    if operation:
        filtered = [item for item in filtered if item.operation == operation]
    if result:
        filtered = [item for item in filtered if item.result == result]
    if from_ts:
        filtered = [item for item in filtered if item.timestamp >= from_ts]
    if to_ts:
        filtered = [item for item in filtered if item.timestamp <= to_ts]

    filtered = list(reversed(filtered))
    total = len(filtered)
    start = (normalized_page - 1) * normalized_page_size
    end = start + normalized_page_size
    return OperationAuditResponse(
        items=filtered[start:end],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


@app.get("/internal/orchestrator/ops/audit-logs.csv")
def operations_audit_logs_csv(
    operator: str | None = None,
    operation: str | None = None,
    result: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> Response:
    data = operations_audit_logs(
        page=1,
        page_size=10000,
        operator=operator,
        operation=operation,
        result=result,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    lines = ["timestamp,operator,operation,target,result,detail"]
    for item in data.items:
        detail = item.detail.replace('"', '""')
        target = item.target.replace('"', '""')
        line = f'{item.timestamp},{item.operator},{item.operation},"{target}",{item.result},"{detail}"'
        lines.append(line)

    csv_body = "\n".join(lines) + "\n"
    headers = {"Content-Disposition": 'attachment; filename="operation-audit-logs.csv"'}
    return Response(content=csv_body, media_type="text/csv", headers=headers)


@app.post("/internal/orchestrator/ops/health-check", response_model=HealthCheckResponse)
def operations_health_check(payload: HealthCheckRequest) -> HealthCheckResponse:
    operator = (payload.operator or "system").strip() or "system"
    if not check_and_mark_operation_rate_limit(operator, "health-check"):
        append_operation_audit(operator, "health-check", "workers", "rate_limited", "Too many operations")
        raise HTTPException(status_code=429, detail="Too many operations, please retry later")

    redis_ok = True
    try:
        redis_client.ping()
    except Exception:
        redis_ok = False

    workers: dict[str, bool] = {
        "worker-copy": False,
        "worker-image": False,
        "worker-video": False,
        "worker-ads": False,
    }

    worker_health_urls = {
        "worker-copy": f"{WORKER_COPY_URL}/health",
        "worker-image": f"{WORKER_IMAGE_URL}/health",
        "worker-video": f"{WORKER_VIDEO_URL}/health",
        "worker-ads": f"{WORKER_ADS_URL}/health",
    }

    for name, url in worker_health_urls.items():
        try:
            get_json(url)
            workers[name] = True
        except RuntimeError:
            workers[name] = False

    append_operation_audit(operator, "health-check", "workers", "ok", "Health check executed")
    return HealthCheckResponse(redis_ok=redis_ok, workers=workers)


@app.post("/internal/orchestrator/ops/purge-topic", response_model=PurgeTopicResponse)
def operations_purge_topic(payload: PurgeTopicRequest) -> PurgeTopicResponse:
    operator = (payload.operator or "system").strip() or "system"
    if not check_and_mark_operation_rate_limit(operator, "purge-topic"):
        append_operation_audit(operator, "purge-topic", payload.topic, "rate_limited", "Too many operations")
        raise HTTPException(status_code=429, detail="Too many operations, please retry later")

    topic = payload.topic
    if topic not in TOPICS and topic != DLQ_TOPIC:
        append_operation_audit(operator, "purge-topic", topic, "failed", "Unsupported topic")
        raise HTTPException(status_code=400, detail="Unsupported topic")

    redis_client.delete(topic)

    if topic in TOPICS:
        try:
            redis_client.xgroup_create(topic, GROUP_NAME, id="0", mkstream=True)
        except Exception:
            pass

    append_operation_audit(operator, "purge-topic", topic, "ok", "Topic purged")
    return PurgeTopicResponse(topic=topic, purged=True)


@app.post("/internal/orchestrator/ops/retry-dlq", response_model=RetryDlqResponse)
def operations_retry_dlq(payload: RetryDlqRequest) -> RetryDlqResponse:
    operator = (payload.operator or "system").strip() or "system"
    if not check_and_mark_operation_rate_limit(operator, "retry-dlq"):
        append_operation_audit(operator, "retry-dlq", payload.message_id, "rate_limited", "Too many operations")
        raise HTTPException(status_code=429, detail="Too many operations, please retry later")

    entries = redis_client.xrange(DLQ_TOPIC, min=payload.message_id, max=payload.message_id, count=1)
    if not entries:
        append_operation_audit(operator, "retry-dlq", payload.message_id, "failed", "DLQ message not found")
        return RetryDlqResponse(message_id=payload.message_id, retried=False, detail="DLQ message not found")

    message_id, fields = entries[0]
    campaign_id = str(fields.get("campaign_id", ""))
    task_id = str(fields.get("task_id", ""))
    task_type = str(fields.get("task_type", ""))

    if not campaign_id or not task_id or task_type not in TASK_TOPIC_MAP:
        append_operation_audit(operator, "retry-dlq", message_id, "failed", "Invalid DLQ payload")
        return RetryDlqResponse(message_id=message_id, retried=False, detail="Invalid DLQ payload")

    campaign_tasks = task_state.get(campaign_id)
    if campaign_tasks is not None and task_id in campaign_tasks:
        task = campaign_tasks[task_id]
        task.status = "planned"
        campaign_tasks[task_id] = task
        task_state[campaign_id] = campaign_tasks

    redis_client.xdel(DLQ_TOPIC, message_id)

    topic = TASK_TOPIC_MAP[task_type]
    redis_client.xadd(
        topic,
        {
            "campaign_id": campaign_id,
            "task_id": task_id,
            "task_type": task_type,
            "replay_from": "dlq",
        },
    )

    append_operation_audit(operator, "retry-dlq", message_id, "ok", "DLQ task requeued")
    return RetryDlqResponse(message_id=message_id, retried=True, detail="DLQ task requeued")


@app.post("/internal/orchestrator/ops/trim-topic", response_model=TrimTopicResponse)
def operations_trim_topic(payload: TrimTopicRequest) -> TrimTopicResponse:
    operator = (payload.operator or "system").strip() or "system"
    if not check_and_mark_operation_rate_limit(operator, "trim-topic"):
        append_operation_audit(operator, "trim-topic", payload.topic, "rate_limited", "Too many operations")
        raise HTTPException(status_code=429, detail="Too many operations, please retry later")

    topic = payload.topic
    if topic not in TOPICS and topic != DLQ_TOPIC:
        append_operation_audit(operator, "trim-topic", topic, "failed", "Unsupported topic")
        raise HTTPException(status_code=400, detail="Unsupported topic")

    maxlen = max(1, min(payload.maxlen, 100000))
    before = int(redis_client.xlen(topic))
    redis_client.xtrim(topic, maxlen=maxlen, approximate=False)
    after = int(redis_client.xlen(topic))
    trimmed = max(0, before - after)
    append_operation_audit(operator, "trim-topic", topic, "ok", f"Trimmed {trimmed} messages to maxlen={maxlen}")
    return TrimTopicResponse(topic=topic, maxlen=maxlen, trimmed=trimmed)
