import base64
import json
import logging
import mimetypes
import os
import re
import shutil
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast
from urllib import error, parse, request
from uuid import uuid4

logger = logging.getLogger("campaign_service")

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .auth import (
    JWTPayload,
    optional_jwt,
    require_jwt,
    require_platform_admin,
    is_platform_admin_request,
    check_permission,
    PLATFORM_ADMIN_KEY,
)
from .persistence import PostgresPersistence, now_utc
from .schemas import (
    AssetOutput,
    AssetVersion,
    AssetVersionListResponse,
    CampaignBrief,
    CampaignCreatedResponse,
    CampaignListResponse,
    CampaignRecord,
    CampaignRunResponse,
    CampaignRunSummary,
    CampaignRunListResponse,
    ErrorResponse,
    FinalAssetBundle,
    TaskListResponse,
    TaskRecord,
    ValidationResult,
    ValidationResultListResponse,
    WebhookSubscription,
    WebhookSubscriptionCreateRequest,
    WebhookSubscriptionResponse,
    WebhookDeliveryLog,
    WebhookDeliveryLogResponse,
    WorkerResultRequest,
)
from .store import InMemoryStore


class QueueHealthResponse(BaseModel):
    topics: list[dict[str, int | str]]
    dlq_size: int
    dlq_recent: list[dict[str, str]]


class OperationHealthCheckResponse(BaseModel):
    redis_ok: bool
    workers: dict[str, bool]


class CampaignDeleteResponse(BaseModel):
    campaign_id: str
    deleted: bool


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


class SlaScanRequest(BaseModel):
    operator: str | None = None
    limit: int = 500


class SlaScanResponse(BaseModel):
    scanned: int
    escalated: int
    overdue_pending: int


class SlaBacklogEntry(BaseModel):
    work_order_id: str
    campaign_id: str
    title: str
    status: str
    priority: int
    due_at: str | None = None
    overdue: bool
    escalated_at: str | None = None
    escalation_reason: str | None = None
    assignee: str | None = None
    created_by: str


class SlaBacklogResponse(BaseModel):
    items: list[SlaBacklogEntry]
    total: int
    overdue_pending: int


class RedisStats(BaseModel):
    redis_version: str | None = None
    connected_clients: int | None = None
    used_memory_human: str | None = None
    uptime_days: int | None = None
    total_connections_received: int | None = None
    instantaneous_ops_modules: str | None = None
    role: str | None = None


class CampaignGroup(BaseModel):
    company_id: str = ""
    group_id: str
    name: str
    campaign_ids: list[str]
    created_at: str


class CampaignGroupCreateRequest(BaseModel):
    name: str
    campaign_ids: list[str]


class CampaignGroupListResponse(BaseModel):
    items: list[CampaignGroup]
    total: int


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


class ReviewItem(BaseModel):
    review_id: str
    campaign_id: str
    asset_id: str
    asset_name: str | None = None
    asset_type: str = "unknown"
    reason: str | None = None
    score: float
    status: str
    submitted_at: str
    assignee: str | None = None
    run_id: str | None = None


class ReviewQueueResponse(BaseModel):
    items: list[ReviewItem]
    total: int


class ReviewActionRequest(BaseModel):
    operator: str | None = None
    reason: str | None = None


class ReviewActionResponse(BaseModel):
    review_id: str
    status: str
    detail: str


class ReviewAuditEntry(BaseModel):
    timestamp: str
    operator: str
    action: str
    target: str
    result: str
    reason: str | None = None


class ReviewAuditResponse(BaseModel):
    items: list[ReviewAuditEntry]
    total: int
    page: int
    page_size: int


class ManualAssetCreateRequest(BaseModel):
    asset_type: Literal["copy", "image", "video"]
    text: str | None = None
    url: str | None = None
    prompt: str | None = None


class AssetRegenerateRequest(BaseModel):
    reject_reason: str | None = None
    user_instruction: str | None = None
    operator: str | None = None


class ManualAssetCreateResponse(BaseModel):
    campaign_id: str
    asset_id: str
    asset_type: Literal["copy", "image", "video"]
    validation_status: str


class SingleAssetGenerateRequest(BaseModel):
    asset_type: Literal["copy", "image", "video"]
    prompt: str = ""


class SingleAssetGenerateResponse(BaseModel):
    campaign_id: str
    asset_type: Literal["copy", "image", "video"]
    status: Literal["queued"]


class KnowledgeItemRecord(BaseModel):
    item_id: str
    company_id: str
    title: str
    source: Literal["ai", "manual"]
    description: str = ""
    content_url: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime


class KnowledgeItemListResponse(BaseModel):
    items: list[KnowledgeItemRecord]
    total: int


class KnowledgeItemCreateRequest(BaseModel):
    title: str
    source: Literal["ai", "manual"] = "manual"
    description: str = ""
    content_url: str | None = None
    metadata: dict[str, Any] = {}


class KnowledgeItemUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    content_url: str | None = None
    category: str | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeItemDeleteResponse(BaseModel):
    item_id: str
    deleted: bool


class RevisionRequestPayload(BaseModel):
    review_id: str
    campaign_id: str
    task_id: str
    asset_id: str
    asset_type: str
    reject_reason: str
    operator: str | None = None


class WorkflowTemplateTask(BaseModel):
    task_type: str
    depends_on: list[str] = []
    priority: int
    acceptance: list[str] = []


class WorkflowTemplateVersion(BaseModel):
    version: int
    tasks: list[WorkflowTemplateTask]
    created_at: str


class WorkflowTemplate(BaseModel):
    template_id: str
    name: str
    description: str
    active_version: int
    created_at: str
    status: Literal["active", "inactive"] = "active"


class WorkflowTemplateListResponse(BaseModel):
    items: list[WorkflowTemplate]
    total: int


class WorkflowTemplateDetailResponse(BaseModel):
    template: WorkflowTemplate
    versions: list[WorkflowTemplateVersion]


class WorkflowTemplateCreateRequest(BaseModel):
    name: str
    description: str = ""
    source_campaign_id: str | None = None
    tasks: list[WorkflowTemplateTask] | None = None


class WorkflowTemplateVersionCreateRequest(BaseModel):
    tasks: list[WorkflowTemplateTask]


class WorkflowTemplateApplyRequest(BaseModel):
    campaign_id: str


class WorkflowTemplateApplyResponse(BaseModel):
    template_id: str
    campaign_id: str
    status: str
    dispatched_tasks: int


class WorkflowTemplateStatusResponse(BaseModel):
    template_id: str
    status: Literal["active", "inactive"]


class CampaignReferenceRecord(BaseModel):
    reference_id: str
    campaign_id: str
    file_name: str
    file_type: str
    file_size: int
    uploaded_at: str
    download_url: str
    folder: str = "General"


class CampaignReferenceUpdateRequest(BaseModel):
    folder: str | None = None
    metadata: dict[str, Any] | None = None


class CampaignReferenceListResponse(BaseModel):
    items: list[CampaignReferenceRecord]
    total: int


class CampaignReferenceDeleteResponse(BaseModel):
    reference_id: str
    deleted: bool


class CampaignReferenceAttachRequest(BaseModel):
    file_name: str
    content: str
    file_type: str = "text/plain"
    operator: str | None = None


class ChatbotAuditWriteRequest(BaseModel):
    audit_id: str
    timestamp: str
    actor_id: str
    actor_role: str
    locale: str
    message: str
    intent: str
    ok: bool
    detail: str | None = None
    request_pending_action_type: str | None = None
    request_pending_campaign_id: str | None = None
    request_pending_reference_id: str | None = None
    request_pending_review_id: str | None = None
    result_pending_action_type: str | None = None
    result_pending_campaign_id: str | None = None
    result_pending_reference_id: str | None = None
    result_pending_review_id: str | None = None


class ChatbotAuditRecord(BaseModel):
    audit_id: str
    timestamp: str
    actor_id: str
    actor_role: str
    locale: str
    message: str
    intent: str
    ok: bool
    detail: str | None = None
    request_pending_action_type: str | None = None
    request_pending_campaign_id: str | None = None
    request_pending_reference_id: str | None = None
    request_pending_review_id: str | None = None
    result_pending_action_type: str | None = None
    result_pending_campaign_id: str | None = None
    result_pending_reference_id: str | None = None
    result_pending_review_id: str | None = None


class ChatbotAuditListResponse(BaseModel):
    items: list[ChatbotAuditRecord]
    total: int


class CampaignTraceRecord(BaseModel):
    trace_id: str
    campaign_id: str
    company_id: str = ""
    created_by: str
    source: str
    created_at: str
    updated_at: str


class CampaignTraceSummaryResponse(BaseModel):
    trace: CampaignTraceRecord | None = None
    event_total: int
    chat_total: int


class CampaignTraceEventRecord(BaseModel):
    event_id: str
    trace_id: str
    campaign_id: str
    company_id: str = ""
    event_type: str
    actor_id: str
    actor_role: str
    summary: str
    payload: dict[str, Any]
    created_at: str


class CampaignTraceEventListResponse(BaseModel):
    items: list[CampaignTraceEventRecord]
    total: int
    next_cursor: str | None = None


class CampaignTraceChatRecord(BaseModel):
    message_id: str
    trace_id: str
    campaign_id: str
    company_id: str = ""
    role: str
    content_masked: str
    raw_ref: str | None = None
    created_at: str


class CampaignTraceChatListResponse(BaseModel):
    items: list[CampaignTraceChatRecord]
    total: int
    next_cursor: str | None = None


class CampaignTraceEventCreateRequest(BaseModel):
    event_type: str
    actor_id: str = "system"
    actor_role: str = "system"
    summary: str
    payload: dict[str, Any] = {}
    source: str | None = None


class WorkOrderRecord(BaseModel):
    company_id: str
    work_order_id: str
    campaign_id: str
    task_id: str | None = None
    title: str
    description: str
    assignee: str | None = None
    status: Literal["open", "in_progress", "blocked", "review_pending", "approved", "rejected", "done", "cancelled"]
    priority: int
    created_by: str
    due_at: str | None = None
    escalated_at: str | None = None
    escalation_reason: str | None = None
    overdue: bool = False
    created_at: str
    updated_at: str


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderRecord]
    total: int
    next_cursor: str | None = None


class WorkOrderCreateRequest(BaseModel):
    task_id: str | None = None
    title: str
    description: str = ""
    assignee: str | None = None
    priority: int = 3
    created_by: str = "system"
    due_at: str | None = None


class WorkOrderUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee: str | None = None
    status: Literal["open", "in_progress", "blocked", "review_pending", "approved", "rejected", "done", "cancelled"] | None = None
    priority: int | None = None
    due_at: str | None = None


class WorkOrderMessageRecord(BaseModel):
    company_id: str
    message_id: str
    work_order_id: str
    campaign_id: str
    role: str
    content_masked: str
    actor_id: str
    created_at: str


class WorkOrderMessageListResponse(BaseModel):
    items: list[WorkOrderMessageRecord]
    total: int
    next_cursor: str | None = None


class WorkOrderMessageCreateRequest(BaseModel):
    role: str = "user"
    content: str
    actor_id: str = "system"


class TraceEventTypeCount(BaseModel):
    event_type: str
    total: int


class SystemTraceHealthResponse(BaseModel):
    retention_days: int
    cleanup_interval_hours: int
    last_cleanup_at: str | None = None
    trace_total: int
    event_total: int
    chat_total: int
    work_order_total: int
    work_order_message_total: int
    work_order_overdue_total: int
    work_order_escalated_total: int
    latest_event_at: str | None = None
    latest_chat_at: str | None = None
    top_event_types: list[TraceEventTypeCount]


# ─── LLM Usage Models ──────────────────────────────────────────────────────────

class LlmUsageIngestRequest(BaseModel):
    company_id: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_count: int = 1


class LlmUsageRecord(BaseModel):
    usage_id: str
    company_id: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost_usd: float
    created_at: str


class LlmUsageListResponse(BaseModel):
    items: list[LlmUsageRecord]
    total: int
    page: int
    page_size: int


class LlmUsageSummaryByModel(BaseModel):
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost_usd: float


class LlmUsageSummaryResponse(BaseModel):
    total_prompt_tokens: int
    total_completion_tokens: int
    total_request_count: int
    total_cost_usd: float
    by_model: list[LlmUsageSummaryByModel]


class LlmModelPricingRecord(BaseModel):
    pricing_id: str
    model: str
    provider: str
    prompt_price_per_m: float
    completion_price_per_m: float
    is_active: bool
    created_at: str
    updated_at: str


class LlmPricingListResponse(BaseModel):
    items: list[LlmModelPricingRecord]
    total: int


class LlmPricingUpsertRequest(BaseModel):
    model: str
    provider: str
    prompt_price_per_m: float
    completion_price_per_m: float


@dataclass
class MetricsRegistry:
    counters: Counter[str]

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def render(self, running_campaigns: int) -> str:
        lines = [
            "# HELP campaign_created_total Number of created campaigns",
            "# TYPE campaign_created_total counter",
            f"campaign_created_total {self.counters['campaign_created_total']}",
            "# HELP campaign_run_total Number of campaign runs",
            "# TYPE campaign_run_total counter",
            f"campaign_run_total {self.counters['campaign_run_total']}",
            "# HELP bundle_requested_total Number of bundle requests",
            "# TYPE bundle_requested_total counter",
            f"bundle_requested_total {self.counters['bundle_requested_total']}",
            "# HELP db_write_total Successful DB write operations",
            "# TYPE db_write_total counter",
            f"db_write_total {self.counters['db_write_total']}",
            "# HELP db_write_fail_total Failed DB write operations",
            "# TYPE db_write_fail_total counter",
            f"db_write_fail_total {self.counters['db_write_fail_total']}",
            "# HELP decision_failover_total Number of run failovers to local plan",
            "# TYPE decision_failover_total counter",
            f"decision_failover_total {self.counters['decision_failover_total']}",
            "# HELP worker_task_complete_total Number of worker completed tasks",
            "# TYPE worker_task_complete_total counter",
            f"worker_task_complete_total {self.counters['worker_task_complete_total']}",
            "# HELP worker_dispatch_failed_total Number of worker dispatch failures",
            "# TYPE worker_dispatch_failed_total counter",
            f"worker_dispatch_failed_total {self.counters['worker_dispatch_failed_total']}",
            "# HELP worker_retry_attempt_total Number of worker retry attempts",
            "# TYPE worker_retry_attempt_total counter",
            f"worker_retry_attempt_total {self.counters['worker_retry_attempt_total']}",
            "# HELP trace_event_write_total Trace events written",
            "# TYPE trace_event_write_total counter",
            f"trace_event_write_total {self.counters['trace_event_write_total']}",
            "# HELP trace_event_write_fail_total Trace event write failures",
            "# TYPE trace_event_write_fail_total counter",
            f"trace_event_write_fail_total {self.counters['trace_event_write_fail_total']}",
            "# HELP trace_read_total Trace read requests",
            "# TYPE trace_read_total counter",
            f"trace_read_total {self.counters['trace_read_total']}",
            "# HELP trace_read_fail_total Trace read failures",
            "# TYPE trace_read_fail_total counter",
            f"trace_read_fail_total {self.counters['trace_read_fail_total']}",
            "# HELP trace_cleanup_total Trace cleanup executions",
            "# TYPE trace_cleanup_total counter",
            f"trace_cleanup_total {self.counters['trace_cleanup_total']}",
            "# HELP trace_cleanup_fail_total Trace cleanup failures",
            "# TYPE trace_cleanup_fail_total counter",
            f"trace_cleanup_fail_total {self.counters['trace_cleanup_fail_total']}",
            "# HELP work_order_created_total Work orders created",
            "# TYPE work_order_created_total counter",
            f"work_order_created_total {self.counters['work_order_created_total']}",
            "# HELP work_order_updated_total Work orders updated",
            "# TYPE work_order_updated_total counter",
            f"work_order_updated_total {self.counters['work_order_updated_total']}",
            "# HELP work_order_message_total Work order messages appended",
            "# TYPE work_order_message_total counter",
            f"work_order_message_total {self.counters['work_order_message_total']}",
            "# HELP work_order_update_denied_total Denied work order status updates",
            "# TYPE work_order_update_denied_total counter",
            f"work_order_update_denied_total {self.counters['work_order_update_denied_total']}",
            "# HELP work_order_sla_breach_total Work orders that breached SLA",
            "# TYPE work_order_sla_breach_total counter",
            f"work_order_sla_breach_total {self.counters['work_order_sla_breach_total']}",
            "# HELP work_order_escalated_total Work orders escalated due to SLA",
            "# TYPE work_order_escalated_total counter",
            f"work_order_escalated_total {self.counters['work_order_escalated_total']}",
            "# HELP work_order_sla_scan_total Manual SLA scans executed",
            "# TYPE work_order_sla_scan_total counter",
            f"work_order_sla_scan_total {self.counters['work_order_sla_scan_total']}",
            "# HELP campaign_running Gauge of running campaigns",
            "# TYPE campaign_running gauge",
            f"campaign_running {running_campaigns}",
        ]
        return "\n".join(lines) + "\n"


app = FastAPI(
    title="Marketing AI Factory - Campaign Service",
    version="0.2.0",
    description="Campaign service with MVP persistence, bundle output, and metrics.",
)

_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
_cors_allowed = [o.strip() for o in _cors_origins.split(",") if o.strip()] if _cors_origins else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed if _cors_allowed else ["http://localhost:3000"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

store = InMemoryStore()
metrics = MetricsRegistry(counters=Counter())


@app.on_event("startup")
async def start_sla_scheduler() -> None:
    if SLA_SCAN_ENABLED:
        import asyncio

        async def sla_loop() -> None:
            while True:
                await asyncio.sleep(SLA_SCAN_INTERVAL_SECONDS)
                try:
                    run_scheduled_sla_scan()
                except Exception as exc:
                    logger.error(f"SLA scan loop failed: {exc}", exc_info=True)

        asyncio.create_task(sla_loop())

    if CAMPAIGN_STATUS_RECONCILE_ENABLED:
        import asyncio

        async def campaign_status_reconcile_loop() -> None:
            while True:
                await asyncio.sleep(CAMPAIGN_STATUS_RECONCILE_INTERVAL_SECONDS)
                try:
                    reconcile_campaign_statuses(operator="scheduler")
                except Exception as exc:
                    logger.error(f"Campaign status reconcile loop failed: {exc}", exc_info=True)

        asyncio.create_task(campaign_status_reconcile_loop())

    # Start LLM usage flusher
    import asyncio
    async def llm_flush_loop() -> None:
        while True:
            await asyncio.sleep(LLM_USAGE_FLUSH_INTERVAL)
            _flush_llm_usage_buffer()

    asyncio.create_task(llm_flush_loop())


DECISION_SERVICE_URL = os.getenv("DECISION_SERVICE_URL", "http://decision-service:8082")
OPENCLAW_CONTROLLER_URL = os.getenv("OPENCLAW_CONTROLLER_URL", "http://orchestrator:8081")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")
REQUIRE_POSTGRES = os.getenv("CAMPAIGN_REQUIRE_POSTGRES", "true").strip().lower() != "false"
CHATBOT_INTERNAL_API_KEY = os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip()
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
CHAT_AUDIT_REQUIRE_PERSISTENCE = os.getenv("CHAT_AUDIT_REQUIRE_PERSISTENCE", "true").strip().lower() != "false"
TRACE_RETENTION_DAYS = int(os.getenv("TRACE_RETENTION_DAYS", "90"))
TRACE_CLEANUP_INTERVAL_HOURS = int(os.getenv("TRACE_CLEANUP_INTERVAL_HOURS", "24"))
SLA_SCAN_ENABLED = os.getenv("SLA_SCAN_ENABLED", "false").strip().lower() == "true"
SLA_SCAN_INTERVAL_SECONDS = max(60, int(os.getenv("SLA_SCAN_INTERVAL_SECONDS", "300")))
CAMPAIGN_STATUS_RECONCILE_ENABLED = os.getenv("CAMPAIGN_STATUS_RECONCILE_ENABLED", "true").strip().lower() != "false"
CAMPAIGN_STATUS_RECONCILE_INTERVAL_SECONDS = max(60, int(os.getenv("CAMPAIGN_STATUS_RECONCILE_INTERVAL_SECONDS", "300")))
CAMPAIGN_RUNNING_TIMEOUT_SECONDS = max(300, int(os.getenv("CAMPAIGN_RUNNING_TIMEOUT_SECONDS", "1800")))
WEBHOOK_NOTIFY_URL = os.getenv("WEBHOOK_NOTIFY_URL", "").strip()
WORKER_RETRY_MAX_ATTEMPTS = max(1, int(os.getenv("WORKER_RETRY_MAX_ATTEMPTS", "2")))
WORKER_RETRY_BACKOFF_SECONDS = max(0.0, float(os.getenv("WORKER_RETRY_BACKOFF_SECONDS", "0.5")))
WORKER_REQUEST_TIMEOUT_SECONDS = max(15.0, float(os.getenv("WORKER_REQUEST_TIMEOUT_SECONDS", "180")))
WORKER_COPY_URL = os.getenv("WORKER_COPY_URL", "http://worker-copy:8091").strip()
WORKER_IMAGE_URL = os.getenv("WORKER_IMAGE_URL", "http://worker-image:8092").strip()
WORKER_VIDEO_URL = os.getenv("WORKER_VIDEO_URL", "http://worker-video:8093").strip()
WORKER_ADS_URL = os.getenv("WORKER_ADS_URL", "http://worker-ads:8094").strip()
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0").strip()
_last_sla_scan_at: datetime | None = None

if not CHATBOT_INTERNAL_API_KEY:
    raise RuntimeError("CHATBOT_INTERNAL_API_KEY is required")

persistence: PostgresPersistence | None = None
if REQUIRE_POSTGRES and not POSTGRES_DSN:
    raise RuntimeError("POSTGRES_DSN is required when CAMPAIGN_REQUIRE_POSTGRES=true")

if REQUIRE_POSTGRES:
    try:
        persistence = PostgresPersistence(POSTGRES_DSN)
        persistence.initialize()
        store.set_persistence(persistence)
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize Postgres persistence: {exc}") from exc

asset_cache: dict[str, list[AssetOutput]] = {}
validation_cache: dict[str, list[ValidationResult]] = {}
campaign_run_cache: dict[str, list[dict[str, Any]]] = {}
review_status_overrides: dict[str, str] = {}
review_audit_logs: list[ReviewAuditEntry] = []
workflow_templates: dict[str, WorkflowTemplate] = {}
workflow_template_versions: dict[str, list[WorkflowTemplateVersion]] = {}
campaign_references: dict[str, list[CampaignReferenceRecord]] = {}
campaign_reference_files: dict[str, dict[str, str]] = {}
knowledge_items: dict[str, list[KnowledgeItemRecord]] = {}
chatbot_audit_logs: list[ChatbotAuditRecord] = []
campaign_traces: dict[str, CampaignTraceRecord] = {}
campaign_trace_events: dict[str, list[CampaignTraceEventRecord]] = {}
campaign_trace_chats: dict[str, list[CampaignTraceChatRecord]] = {}
campaign_work_orders: dict[str, list[WorkOrderRecord]] = {}
work_order_by_id: dict[str, WorkOrderRecord] = {}
work_order_messages: dict[str, list[WorkOrderMessageRecord]] = {}
campaign_groups: dict[str, CampaignGroup] = {}
last_trace_cleanup_at: datetime | None = None
CAMPAIGN_REFERENCES_DIR = os.getenv("CAMPAIGN_REFERENCES_DIR", os.path.join(os.getcwd(), "campaign_references"))
MANUAL_ASSETS_DIR = os.getenv("MANUAL_ASSETS_DIR", os.path.join(os.getcwd(), "manual_assets"))
GENERATED_ASSETS_DIR = os.getenv("GENERATED_ASSETS_DIR", os.path.join(os.getcwd(), "generated_assets"))
KNOWLEDGE_UPLOADS_DIR = os.getenv("KNOWLEDGE_UPLOADS_DIR", os.path.join(os.getcwd(), "knowledge_uploads"))
REFERENCE_MAX_SIZE_BYTES = int(os.getenv("REFERENCE_MAX_SIZE_BYTES", str(50 * 1024 * 1024)))
LLM_USAGE_BUFFER_KEY = "llm_usage_buffer"
LLM_USAGE_FLUSH_INTERVAL = 60  # seconds

REFERENCE_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}
REFERENCE_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
}
os.makedirs(CAMPAIGN_REFERENCES_DIR, exist_ok=True)
os.makedirs(GENERATED_ASSETS_DIR, exist_ok=True)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with request.urlopen(req, timeout=WORKER_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def get_json(url: str) -> dict[str, Any]:
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=WORKER_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def _classify_worker_error(message: str) -> str:
    text = (message or "").lower()
    if "timeout" in text:
        return "WORKER_TIMEOUT"
    if "503" in text:
        return "WORKER_UNAVAILABLE"
    if "401" in text or "403" in text:
        return "WORKER_AUTH"
    if "422" in text:
        return "WORKER_PAYLOAD_INVALID"
    if "502" in text:
        return "WORKER_UPSTREAM_ERROR"
    return "WORKER_UNKNOWN_ERROR"


def _extract_worker_error_detail(message: str) -> str:
    text = (message or "").strip()
    # common format: "... HTTP Error 422: Unprocessable Entity"
    # keep original when no structured detail can be extracted
    return text


def _worker_post_json(url: str, payload: dict[str, Any], task_type: str, campaign_id: str, task_id: str, company_id: str) -> dict[str, Any]:
    last_exc: RuntimeError | None = None
    for attempt in range(1, WORKER_RETRY_MAX_ATTEMPTS + 1):
        try:
            if attempt > 1:
                metrics.inc("worker_retry_attempt_total")
            return post_json(url, payload)
        except RuntimeError as exc:
            last_exc = exc
            metrics.inc("worker_dispatch_failed_total")
            error_text = str(exc)
            error_code = _classify_worker_error(error_text)
            error_detail = _extract_worker_error_detail(error_text)
            append_trace_event(
                campaign_id=campaign_id,
                event_type="worker_dispatch_retrying" if attempt < WORKER_RETRY_MAX_ATTEMPTS else "worker_dispatch_failed",
                actor_id="system",
                actor_role="system",
                summary=f"Worker request failed (attempt {attempt}/{WORKER_RETRY_MAX_ATTEMPTS}) for {task_id}",
                payload={
                    "task_id": task_id,
                    "task_type": task_type,
                    "attempt": attempt,
                    "error_code": error_code,
                    "error": error_text,
                    "error_detail": error_detail,
                    "worker_url": url,
                    "worker_payload": payload,
                },
                source="workers",
                company_id=company_id,
            )
            if attempt < WORKER_RETRY_MAX_ATTEMPTS and WORKER_RETRY_BACKOFF_SECONDS > 0:
                time.sleep(WORKER_RETRY_BACKOFF_SECONDS)
    raise RuntimeError(str(last_exc) if last_exc else "unknown worker failure")


TaskType = Literal["copywriting", "image_generation", "video_generation", "ads_strategy"]
TaskStatus = Literal["pending", "planned", "running", "validating", "passed", "failed", "retrying"]


def normalize_task_payload(payload: dict[str, Any], campaign_id: str) -> TaskRecord:
    raw_task_id = payload.get("task_id")
    task_id = str(raw_task_id) if raw_task_id else f"tsk_{uuid4().hex[:8]}"

    raw_task_type = str(payload.get("task_type", "copywriting"))
    if raw_task_type not in {"copywriting", "image_generation", "video_generation", "ads_strategy"}:
        raw_task_type = "copywriting"
    task_type = cast(TaskType, raw_task_type)

    raw_status = str(payload.get("status", "pending"))
    if raw_status not in {"pending", "planned", "running", "validating", "passed", "failed", "retrying"}:
        raw_status = "pending"
    status = cast(TaskStatus, raw_status)

    try:
        priority = int(payload.get("priority", 1))
    except (TypeError, ValueError):
        priority = 1

    depends_on_raw = payload.get("depends_on", [])
    depends_on = [str(item) for item in depends_on_raw] if isinstance(depends_on_raw, list) else []

    acceptance_raw = payload.get("acceptance", [])
    acceptance = [str(item) for item in acceptance_raw] if isinstance(acceptance_raw, list) else []

    # Resolve company_id: prefer payload value, else look up from campaign
    company_id = str(payload.get("company_id") or "")
    if not company_id and store:
        campaign = store.get_campaign(campaign_id)
        if campaign is not None:
            company_id = campaign.company_id or ""

    return TaskRecord(
        task_id=task_id,
        campaign_id=campaign_id,
        company_id=company_id,
        task_type=task_type,
        status=status,
        priority=priority,
        depends_on=depends_on,
        acceptance=acceptance,
    )


def sync_tasks_from_orchestrator(campaign_id: str) -> list[TaskRecord]:
    state = get_json(f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/campaign/{campaign_id}/tasks")
    task_items = state.get("tasks", [])
    tasks = [normalize_task_payload(item, campaign_id) for item in task_items if isinstance(item, dict)]
    store.set_tasks(campaign_id, tasks)
    return tasks


def save_assets_and_validations(assets: list[AssetOutput], validations: list[ValidationResult]) -> None:
    assets = [asset for asset in assets if is_displayable_asset(asset)]
    if assets:
        assets = assign_campaign_run_version_metadata(assets[0].campaign_id, assets)
    asset_ids = {asset.asset_id for asset in assets}
    validations = [item for item in validations if item.asset_id in asset_ids]
    if not assets and not validations:
        return
    campaign_id = assets[0].campaign_id if assets else validations[0].campaign_id
    if assets:
        existing_assets = {item.asset_id: item for item in asset_cache.get(campaign_id, [])}
        for item in assets:
            existing_assets[item.asset_id] = item
        asset_cache[campaign_id] = list(existing_assets.values())
    if validations:
        existing_validations = {item.validation_id: item for item in validation_cache.get(campaign_id, [])}
        for item in validations:
            existing_validations[item.validation_id] = item
        validation_cache[campaign_id] = list(existing_validations.values())

    if persistence is None:
        return
    try:
        persistence.save_asset_outputs(assets)
        persistence.save_validation_results(validations)
        persistence.upsert_review_items_for_validations(assets, validations)
        # Save asset versions for each generated asset
        for asset in assets:
            if asset.run_id:
                run_id = asset.run_id
                version_rows = persistence.list_asset_versions(asset.asset_id)
                version_number = max((r["version_number"] for r in version_rows), default=0) + 1
                version_id = f"ver_{asset.asset_id}_{run_id}"
                persistence.save_asset_version(version_id, asset.asset_id, run_id, version_number, asset.url, asset.metadata)
        metrics.inc("db_write_total")
    except Exception:
        metrics.inc("db_write_fail_total")


def mark_tasks_from_generated_assets(campaign_id: str, tasks: list[TaskRecord], assets: list[AssetOutput], validations: list[ValidationResult]) -> list[TaskRecord]:
    """Sync task status after synchronous fallback generation creates displayable assets."""
    if not tasks or not assets:
        return tasks
    validation_by_asset = {item.asset_id: item for item in validations}
    generated_task_results: dict[str, str] = {}
    for asset in assets:
        validation = validation_by_asset.get(asset.asset_id)
        if validation is None:
            continue
        generated_task_results[asset.task_id] = "passed" if validation.result == "passed" else "failed"
    if not generated_task_results:
        return tasks
    updated_tasks = [
        task.model_copy(update={"status": generated_task_results[task.task_id]})
        if task.task_id in generated_task_results
        else task
        for task in tasks
    ]
    store.set_tasks(campaign_id, updated_tasks)
    return updated_tasks


def mark_tasks_from_existing_assets(campaign_id: str, tasks: list[TaskRecord], run_id: str | None) -> list[TaskRecord]:
    """Reconcile task status from already persisted assets/validations for the latest run."""
    if not tasks:
        return tasks
    validations_by_asset = {item.asset_id: item for item in list_validation(campaign_id)}
    task_results: dict[str, str] = {}
    for asset in list_assets(campaign_id):
        if run_id and asset.run_id != run_id:
            continue
        validation = validations_by_asset.get(asset.asset_id)
        if validation is None:
            continue
        task_results[asset.task_id] = "passed" if validation.result == "passed" else "failed"
    if not task_results:
        return tasks
    updated_tasks = [
        task.model_copy(update={"status": task_results[task.task_id]})
        if task.task_id in task_results and task.status not in {"passed", "failed"}
        else task
        for task in tasks
    ]
    if updated_tasks != tasks:
        store.set_tasks(campaign_id, updated_tasks)
    return updated_tasks


def list_assets(campaign_id: str) -> list[AssetOutput]:
    if persistence is not None:
        try:
            return persistence.list_asset_outputs(campaign_id)
        except Exception:
            pass
    return asset_cache.get(campaign_id, [])


def get_asset_output_by_id(asset_id: str) -> AssetOutput | None:
    if persistence is not None:
        try:
            return persistence.get_asset_output(asset_id)
        except Exception:
            pass
    for assets in asset_cache.values():
        for asset in assets:
            if asset.asset_id == asset_id:
                return asset
    return None


def approved_asset_knowledge_title(campaign: CampaignRecord, asset: AssetOutput) -> str:
    metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
    name = asset_metadata_name(metadata)
    if name:
        return name
    type_label = {
        "copy": "文案",
        "image": "圖片",
        "video": "影片",
        "ads": "廣告策略",
    }.get(asset.asset_type, asset.asset_type)
    return f"{campaign.brief.campaign_name} · {type_label}"


def approved_asset_knowledge_description(asset: AssetOutput) -> str:
    if asset.asset_type == "copy":
        return extract_copy_text_from_asset(asset)[:1200]
    metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
    if asset.asset_type == "ads":
        ads_plan = metadata.get("ads_plan")
        if ads_plan:
            try:
                return json.dumps(ads_plan, ensure_ascii=False)[:1200]
            except Exception:
                return str(ads_plan)[:1200]
    return "審核通過素材"


def sync_approved_asset_to_knowledge_item(campaign: CampaignRecord, review_item: ReviewItem, operator: str) -> None:
    """Publish approved review asset into Content Studio / knowledge_items."""
    asset = get_asset_output_by_id(review_item.asset_id)
    if asset is None or not is_displayable_asset(asset):
        return
    company_id = campaign.company_id
    metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
    item_id = f"ki_asset_{asset.asset_id}"
    item = KnowledgeItemRecord(
        item_id=item_id,
        company_id=company_id,
        title=approved_asset_knowledge_title(campaign, asset),
        source="ai",
        description=approved_asset_knowledge_description(asset),
        content_url=public_asset_url(asset.url) if asset.asset_type in {"image", "video"} else None,
        metadata={
            "category": "審核通過素材",
            "source_label": "review_approved",
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.brief.campaign_name,
            "review_id": review_item.review_id,
            "approved_asset_id": asset.asset_id,
            "asset_id": asset.asset_id,
            "asset_type": asset.asset_type,
            "asset_name": asset_metadata_name(metadata),
            "run_id": asset.run_id,
            "approved_by": operator,
            "approved_at": now_utc().isoformat(),
        },
        created_at=now_utc(),
    )
    if persistence is not None:
        try:
            persistence.create_knowledge_item(item.model_dump(mode="python"))
            return
        except Exception:
            metrics.inc("db_write_fail_total")
    existing = [row for row in knowledge_items.get(company_id, []) if row.item_id != item_id]
    knowledge_items[company_id] = [item, *existing]


def list_validation(campaign_id: str) -> list[ValidationResult]:
    if persistence is not None:
        try:
            return persistence.list_validation_results(campaign_id)
        except Exception:
            pass
    return validation_cache.get(campaign_id, [])


def create_campaign_run_record(campaign: CampaignRecord, triggered_by: str) -> tuple[str, int | None]:
    run_id = f"run_{uuid4().hex[:12]}"
    if persistence is not None:
        try:
            run_number = persistence.create_campaign_run(
                run_id=run_id,
                campaign_id=campaign.campaign_id,
                company_id=campaign.company_id,
                status="running",
                triggered_by=triggered_by,
            )
            return run_id, run_number
        except Exception:
            metrics.inc("db_write_fail_total")
    runs = campaign_run_cache.setdefault(campaign.campaign_id, [])
    run_number = len(runs) + 1
    runs.insert(0, {"run_id": run_id, "run_number": run_number, "status": "running", "started_at": now_utc()})
    return run_id, run_number


def complete_campaign_run_record(run_id: str | None, campaign_id: str, status: str, metadata: dict[str, Any] | None = None) -> None:
    if not run_id:
        return
    if persistence is not None:
        try:
            persistence.complete_campaign_run(run_id, status, metadata)
            return
        except Exception:
            metrics.inc("db_write_fail_total")
    for item in campaign_run_cache.get(campaign_id, []):
        if item.get("run_id") == run_id:
            item["status"] = status
            item["completed_at"] = now_utc()
            if metadata:
                item.setdefault("metadata", {}).update(metadata)
            return


def latest_campaign_run_id(campaign_id: str) -> str | None:
    if persistence is not None:
        try:
            latest = persistence.get_latest_campaign_run(campaign_id)
            if latest:
                return str(latest.get("run_id") or "") or None
        except Exception:
            pass
    runs = campaign_run_cache.get(campaign_id, [])
    return str(runs[0].get("run_id")) if runs else None


def list_campaign_runs_raw(campaign_id: str) -> list[dict[str, Any]]:
    if persistence is not None:
        try:
            return persistence.list_campaign_runs(campaign_id)
        except Exception:
            pass
    return campaign_run_cache.get(campaign_id, [])


def effective_review_statuses_by_asset_group(campaign_id: str) -> dict[str, str]:
    """Return latest review status per regenerated asset group.

    Older versions must keep their own rejected/approved display status, but they
    should not decide the campaign lifecycle once a newer version exists.
    """
    if persistence is not None:
        try:
            items = persistence.list_review_items(campaign_id=campaign_id)
        except Exception:
            metrics.inc("db_write_fail_total")
            items = []
    else:
        items = []
    latest: dict[str, tuple[int, datetime, str]] = {}
    for item in items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        asset_id = str(item.get("asset_id") or "")
        group_key = str(metadata.get("root_asset_id") or metadata.get("asset_base_name") or asset_id)
        if not group_key:
            continue
        try:
            version = int(metadata.get("asset_version") or 1)
        except (TypeError, ValueError):
            version = 1
        submitted_at = item.get("submitted_at")
        if not isinstance(submitted_at, datetime):
            submitted_at = datetime.min
        status = str(item.get("status") or "review_pending")
        current = latest.get(group_key)
        if current is None or (version, submitted_at) >= (current[0], current[1]):
            latest[group_key] = (version, submitted_at, status)
    return {key: value[2] for key, value in latest.items()}


def campaign_has_rejected_reviews(campaign_id: str) -> bool:
    """Only the latest version in each regenerated asset group can fail a campaign."""
    statuses = effective_review_statuses_by_asset_group(campaign_id)
    if statuses:
        return any(status == "rejected" for status in statuses.values())
    return False


def campaign_has_pending_reviews(campaign_id: str) -> bool:
    """Pending human review means generation is done but campaign is not final-complete yet."""
    statuses = effective_review_statuses_by_asset_group(campaign_id)
    if statuses:
        return any(status == "review_pending" for status in statuses.values())
    return False


def derive_campaign_status(campaign: CampaignRecord) -> Literal["draft", "running", "completed", "failed"]:
    if campaign_has_rejected_reviews(campaign.campaign_id):
        return "failed"
    if campaign_has_pending_reviews(campaign.campaign_id):
        return "running"

    tasks = store.get_tasks(campaign.campaign_id)
    if tasks:
        if any(task.status == "failed" for task in tasks):
            return "failed"
        if all(task.status == "passed" for task in tasks):
            return "completed"
        if any(task.status in {"planned", "pending", "running", "validating", "retrying"} for task in tasks):
            return "running"

    runs = list_campaign_runs_raw(campaign.campaign_id)
    if runs:
        latest = runs[0]
        status = str(latest.get("status") or "")
        if status == "completed":
            return "completed"
        if status == "failed":
            return "failed"
        if status == "running":
            return "running"

    return "running"


def derive_workflow_status_from_tasks(tasks: list[TaskRecord]) -> Literal["running", "completed", "failed"] | None:
    """Return the workflow status implied by tasks, or None when tasks do not exist yet."""
    if not tasks:
        return None
    if any(task.status == "failed" for task in tasks):
        return "failed"
    if all(task.status == "passed" for task in tasks):
        return "completed"
    return "running"


def finalize_campaign_workflow(
    campaign_id: str,
    *,
    run_id: str | None = None,
    run_number: int | None = None,
    tasks: list[TaskRecord] | None = None,
    operator: str = "system",
    reason: str = "workflow_finalizer",
    notify_completed: bool = False,
) -> CampaignRecord | None:
    """Single status lifecycle finalizer for campaign workflow/run state.

    Campaign status is treated as a display cache derived from tasks/latest run.
    Direct callers should update tasks/runs first, then call this helper instead of
    scattering set_campaign_status()/complete_campaign_run_record() writes.
    """
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        return None

    task_items = tasks if tasks is not None else store.get_tasks(campaign_id)
    task_status = derive_workflow_status_from_tasks(task_items)
    runs = list_campaign_runs_raw(campaign_id)
    latest_run = runs[0] if runs else None
    effective_run_id = run_id or (str(latest_run.get("run_id") or "") if latest_run else None)

    if task_status is not None:
        target: Literal["draft", "running", "completed", "failed"] = task_status
    elif latest_run is not None:
        latest_status = str(latest_run.get("status") or "")
        target = latest_status if latest_status in {"running", "completed", "failed"} else "running"  # type: ignore[assignment]
    else:
        target = "running"

    metadata = {
        "task_count": len(task_items),
        "finalized_by": operator,
        "reason": reason,
    }
    if target == "completed" and campaign_has_pending_reviews(campaign_id):
        target = "running"

    if target in {"completed", "failed"} and effective_run_id:
        complete_campaign_run_record(effective_run_id, campaign_id, target, metadata)

    before = campaign.status
    updated = store.set_campaign_status(campaign_id, target) or campaign.model_copy(update={"status": target})

    if before != target or target in {"completed", "failed"}:
        append_trace_event(
            campaign_id=campaign_id,
            event_type="campaign_workflow_finalized",
            actor_id=operator,
            actor_role="system",
            summary=f"Campaign workflow finalized: {before} -> {target}",
            payload={
                "before": before,
                "after": target,
                "run_id": effective_run_id,
                "run_number": run_number,
                "task_count": len(task_items),
                "reason": reason,
            },
            source="system",
            company_id=campaign.company_id,
        )

    if notify_completed and target == "completed":
        _notify_webhook(
            event_type="campaign_completed",
            campaign_id=campaign_id,
            payload={"run_id": effective_run_id, "run_number": run_number, "task_count": len(task_items)},
            company_id=campaign.company_id,
        )

    return updated


def normalize_campaign_status(campaign: CampaignRecord) -> CampaignRecord:
    derived = derive_campaign_status(campaign)
    if campaign.status != derived:
        updated = store.set_campaign_status(campaign.campaign_id, derived)
        if updated is not None:
            return updated
        campaign.status = derived
    return campaign


def coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def latest_run_age_seconds(campaign_id: str) -> float | None:
    runs = list_campaign_runs_raw(campaign_id)
    if not runs:
        return None
    started_at = coerce_datetime(runs[0].get("started_at"))
    if started_at is None:
        return None
    return max(0.0, (now_utc().replace(tzinfo=None) - started_at.replace(tzinfo=None)).total_seconds())


def reconcile_campaign_status(campaign: CampaignRecord, operator: str = "scheduler") -> tuple[CampaignRecord, bool, str]:
    before = campaign.status
    tasks = store.get_tasks(campaign.campaign_id)
    runs = list_campaign_runs_raw(campaign.campaign_id)
    latest_run = runs[0] if runs else None
    latest_run_status = str(latest_run.get("status") or "") if latest_run else ""
    age = latest_run_age_seconds(campaign.campaign_id)
    timeout = age is not None and age >= CAMPAIGN_RUNNING_TIMEOUT_SECONDS

    target = derive_campaign_status(campaign)
    reason = "derived"

    if latest_run_status == "running" and timeout:
        if not tasks:
            target = "running"
            reason = "stale_running_no_tasks"
        elif any(task.status == "failed" for task in tasks):
            target = "failed"
            reason = "stale_running_failed_tasks"
        elif all(task.status == "passed" for task in tasks):
            target = "completed"
            reason = "stale_running_passed_tasks"
        else:
            target = "failed"
            reason = "stale_running_timeout"

        if latest_run:
            complete_campaign_run_record(
                str(latest_run.get("run_id") or ""),
                campaign.campaign_id,
                "failed" if target in {"draft", "failed"} else target,
                {"reconciled_by": operator, "reason": reason},
            )

    changed = before != target
    if changed:
        updated = store.set_campaign_status(campaign.campaign_id, target) or campaign
        append_trace_event(
            campaign_id=campaign.campaign_id,
            event_type="campaign_status_reconciled",
            actor_id=operator,
            actor_role="system",
            summary=f"Campaign status reconciled: {before} -> {target}",
            payload={"before": before, "after": target, "reason": reason, "latest_run_status": latest_run_status, "latest_run_age_seconds": age},
            source="system",
            company_id=campaign.company_id,
        )
        return updated, True, reason

    return campaign, False, reason


def reconcile_campaign_statuses(operator: str = "scheduler", company_id: str | None = None) -> dict[str, Any]:
    items = store.list_campaigns(company_id=company_id)
    scanned = 0
    changed = 0
    changes: list[dict[str, Any]] = []
    for campaign in items:
        if campaign.status != "running":
            runs = list_campaign_runs_raw(campaign.campaign_id)
            if not runs or str(runs[0].get("status") or "") != "running":
                continue
        scanned += 1
        updated, did_change, reason = reconcile_campaign_status(campaign, operator=operator)
        if did_change:
            changed += 1
            changes.append({"campaign_id": campaign.campaign_id, "before": campaign.status, "after": updated.status, "reason": reason})
    return {"scanned": scanned, "changed": changed, "changes": changes}


def public_asset_url(url: str) -> str:
    """Return a browser-safe public URL for generated assets.

    Some upstream image providers return signed HTTP URLs even though the same
    object is available over HTTPS. Opening those links from the HTTPS app can
    produce blank tabs or browser blocking. Prefer HTTPS for external assets;
    keep relative/internal schemes untouched.
    """
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def _asset_extension(asset_type: str, content_type: str, source_url: str) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "image/jpeg":
        return "jpg"
    if content_type == "image/png":
        return "png"
    if content_type == "image/webp":
        return "webp"
    if content_type == "image/gif":
        return "gif"
    if content_type == "image/svg+xml":
        return "svg"
    if content_type == "video/mp4":
        return "mp4"
    if content_type == "video/webm":
        return "webm"
    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        return guessed.lstrip(".").replace("jpeg", "jpg")
    path = parse.urlparse(source_url).path
    suffix = os.path.splitext(path)[1].lstrip(".")
    if suffix:
        return suffix[:12]
    return "mp4" if asset_type == "video" else "jpg"


def cache_generated_asset_url(
    *,
    company_id: str,
    campaign_id: str,
    asset_id: str,
    asset_type: Literal["image", "video"],
    source_url: str,
) -> tuple[str, dict[str, Any]]:
    """Persist short-lived provider URLs/data URLs and return a durable local API URL."""
    value = (source_url or "").strip()
    if not value:
        raise ValueError("source_url is required")

    content_type = ""
    payload: bytes
    if value.startswith("data:"):
        header, _, data = value.partition(",")
        content_type = header.removeprefix("data:").split(";", 1)[0] or ("video/mp4" if asset_type == "video" else "image/png")
        if ";base64" in header:
            payload = base64.b64decode(data)
        else:
            payload = parse.unquote_to_bytes(data)
    elif value.startswith("file://"):
        file_path = value[7:]  # strip "file://"
        file_path = parse.unquote(file_path)
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            raise ValueError(f"file:// URL points to non-existent path: {file_path}")
        with open(file_path, "rb") as f:
            payload = f.read()
        content_type = "video/mp4" if asset_type == "video" else "image/png"
    else:
        req = request.Request(value, method="GET", headers={"User-Agent": "AI-Marketing-Factory/1.0"})
        with request.urlopen(req, timeout=180) as resp:
            content_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            payload = resp.read()

    if not payload:
        raise ValueError("generated asset download returned empty payload")
    if asset_type == "image" and not content_type.startswith("image/"):
        raise ValueError(f"generated image returned non-image content-type: {content_type}")
    if asset_type == "video" and not (content_type.startswith("video/") or content_type == "application/octet-stream"):
        raise ValueError(f"generated video returned non-video content-type: {content_type}")

    ext = _asset_extension(asset_type, content_type, value)
    safe_company = re.sub(r"[^A-Za-z0-9._-]+", "_", company_id or "unknown_company").strip("._") or "unknown_company"
    safe_file = f"{asset_id}.{ext}"
    target_dir = os.path.join(GENERATED_ASSETS_DIR, safe_company, campaign_id)
    os.makedirs(target_dir, exist_ok=True)
    stored_path = os.path.abspath(os.path.join(target_dir, safe_file))
    root_path = os.path.abspath(target_dir)
    if not stored_path.startswith(root_path):
        raise ValueError("invalid generated asset path")
    with open(stored_path, "wb") as out:
        out.write(payload)

    public_url = f"/api/v1/campaigns/{campaign_id}/assets/generated-files/{asset_id}/{parse.quote(safe_file)}"
    return public_url, {
        "source": "generated_cache",
        "stored_path": stored_path,
        "file_name": safe_file,
        "content_type": content_type,
        "original_url": value,
        "file_size": len(payload),
    }


def is_openable_asset_url(url: str) -> bool:
    value = (url or "").strip()
    if not value:
        return False
    if value.startswith(("stub://", "minimax-quota://", "minimax://")):
        return False
    if value.startswith(("http://", "https://", "data:image/", "file://")):
        return True
    if value.startswith("/api/"):
        return True
    return False


def extract_copy_text_from_asset(asset: AssetOutput) -> str:
    metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
    variant = metadata.get("variant")
    if isinstance(variant, dict):
        body = variant.get("body")
        if isinstance(body, str) and body.strip():
            return body.strip()
    manual_text = metadata.get("manual_text")
    if isinstance(manual_text, str) and manual_text.strip():
        return manual_text.strip()
    return ""


def is_displayable_asset(asset: AssetOutput) -> bool:
    metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
    if asset.asset_type == "copy":
        return bool(extract_copy_text_from_asset(asset))
    if asset.asset_type in {"image", "video"}:
        if not is_openable_asset_url(asset.url):
            return False
        if metadata.get("source") in {"manual_upload", "generated_cache"}:
            stored_path = metadata.get("stored_path")
            if not isinstance(stored_path, str) or not os.path.exists(stored_path):
                return False
        return True
    if asset.asset_type == "ads":
        ads_plan = metadata.get("ads_plan")
        return isinstance(ads_plan, dict) and bool(ads_plan)
    return False


def append_validation_for_asset(
    validations: list[ValidationResult],
    company_id: str,
    campaign_id: str,
    asset_id: str,
    now: datetime,
    score: float = 0.9,
    result: str = "passed",
    reasons: list[str] | None = None,
    run_id: str | None = None,
) -> None:
    validations.append(
        ValidationResult(
            company_id=company_id,
            validation_id=f"val_{uuid4().hex[:10]}",
            campaign_id=campaign_id,
            asset_id=asset_id,
            validator="policy-check",
            score=score,
            result=result,
            reasons=reasons or ["worker output accepted"],
            created_at=now,
            run_id=run_id,
        )
    )


def asset_type_display_label(asset_type: str) -> str:
    if asset_type == "copy":
        return "Copy"
    if asset_type == "image":
        return "Image"
    if asset_type == "video":
        return "Video"
    if asset_type == "ads":
        return "Ads"
    return "Asset"


def strip_asset_version_suffix(name: str) -> str:
    cleaned = name.strip()
    upper = cleaned.upper()
    marker = "_V"
    idx = upper.rfind(marker)
    if idx > 0 and upper[idx + 2 :].isdigit():
        return cleaned[:idx].strip()
    return cleaned


def default_asset_base_name(campaign: CampaignRecord, asset_type: str) -> str:
    campaign_name = (campaign.brief.campaign_name or campaign.campaign_id).strip()
    return f"{campaign_name}_{asset_type_display_label(asset_type)}"


def is_single_asset_generation(task_id: str) -> bool:
    return task_id.startswith("manual_")


def next_single_asset_index(existing_base_names: list[str], prefix: str) -> int:
    indexes = []
    for base_name in existing_base_names:
        if not base_name.startswith(prefix):
            continue
        suffix = base_name[len(prefix):]
        if suffix.isdigit():
            indexes.append(int(suffix))
    return max(indexes, default=0) + 1


def single_asset_base_name(campaign_name: str, asset_type: str, index: int) -> str:
    return f"{campaign_name.strip()}_manual_{asset_type}_{index}"


def asset_display_name(base_name: str, version_number: int) -> str:
    return f"{strip_asset_version_suffix(base_name)}_V{max(1, version_number)}"


def asset_metadata_name(metadata: dict[str, Any] | None, fallback: str | None = None) -> str | None:
    if isinstance(metadata, dict):
        for key in ("asset_name", "display_name", "asset_display_name"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback.strip() if isinstance(fallback, str) and fallback.strip() else None


def prepare_regeneration_naming(campaign: CampaignRecord, source_asset: AssetOutput) -> dict[str, Any]:
    source_metadata = source_asset.metadata if isinstance(source_asset.metadata, dict) else {}
    source_name = asset_metadata_name(source_metadata)
    base_name = str(source_metadata.get("asset_base_name") or strip_asset_version_suffix(source_name or default_asset_base_name(campaign, source_asset.asset_type))).strip()
    if not base_name:
        base_name = default_asset_base_name(campaign, source_asset.asset_type)
    root_asset_id = str(source_metadata.get("root_asset_id") or source_metadata.get("parent_asset_id") or source_asset.asset_id)
    max_version = 0
    if persistence is not None:
        try:
            for item in persistence.list_asset_outputs(source_asset.campaign_id):
                item_metadata = item.metadata if isinstance(item.metadata, dict) else {}
                same_root = str(item_metadata.get("root_asset_id") or item_metadata.get("parent_asset_id") or item.asset_id) == root_asset_id
                same_base = str(item_metadata.get("asset_base_name") or "") == base_name
                if item.asset_id == source_asset.asset_id or same_root or same_base:
                    if "asset_version" not in item_metadata:
                        continue
                    try:
                        max_version = max(max_version, int(item_metadata.get("asset_version") or 0))
                    except (TypeError, ValueError):
                        max_version = max(max_version, 0)
        except Exception:
            metrics.inc("db_write_fail_total")
    next_version = max_version + 1
    return {
        "parent_asset_id": source_asset.asset_id,
        "root_asset_id": root_asset_id,
        "asset_base_name": base_name,
        "asset_version": next_version,
        "asset_name": asset_display_name(base_name, next_version),
        "is_regenerated": True,
    }


def apply_regeneration_metadata(metadata: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    context = result.get("regeneration_context")
    if isinstance(context, dict):
        for key in ("parent_asset_id", "root_asset_id", "asset_base_name", "asset_version", "asset_name", "is_regenerated"):
            if key in context and context[key] not in (None, ""):
                metadata[key] = context[key]
        if "asset_name" in metadata:
            metadata["display_name"] = metadata["asset_name"]
    return metadata


def assign_campaign_run_version_metadata(campaign_id: str, assets: list[AssetOutput]) -> list[AssetOutput]:
    if not assets:
        return assets
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        return assets
    generated_assets = [asset for asset in assets if isinstance(asset.metadata, dict) and not asset.metadata.get("asset_base_name") and asset.metadata.get("source") not in {"manual", "manual_upload"}]
    if not generated_assets:
        return assets

    existing_assets: list[AssetOutput] = []
    if persistence is not None:
        try:
            existing_assets = persistence.list_asset_outputs(campaign_id)
        except Exception:
            metrics.inc("db_write_fail_total")
    else:
        existing_assets = asset_cache.get(campaign_id, [])

    backfill_updates: list[AssetOutput] = []
    existing_by_type: dict[str, list[AssetOutput]] = {}
    for item in existing_assets:
        if item.asset_id in {asset.asset_id for asset in generated_assets}:
            continue
        item_metadata = item.metadata if isinstance(item.metadata, dict) else {}
        if item_metadata.get("source") in {"manual", "manual_upload"}:
            continue
        existing_by_type.setdefault(item.asset_type, []).append(item)

    for asset_type, items in existing_by_type.items():
        items.sort(key=lambda item: item.created_at)
        for index, item in enumerate(items, start=1):
            item_metadata = dict(item.metadata if isinstance(item.metadata, dict) else {})
            if item_metadata.get("asset_base_name"):
                continue
            base_name = f"{default_asset_base_name(campaign, asset_type)}_{index}"
            item_metadata.update({
                "root_asset_id": item.asset_id,
                "asset_base_name": base_name,
                "asset_version": 1,
                "asset_name": asset_display_name(base_name, 1),
                "display_name": asset_display_name(base_name, 1),
            })
            backfill_updates.append(AssetOutput(
                company_id=item.company_id,
                asset_id=item.asset_id,
                campaign_id=item.campaign_id,
                task_id=item.task_id,
                asset_type=item.asset_type,
                url=item.url,
                metadata=item_metadata,
                validation_status=item.validation_status,
                created_at=item.created_at,
                run_id=item.run_id,
            ))

    max_version_by_base: dict[str, int] = {}
    root_by_base: dict[str, str] = {}
    for item in [*existing_assets, *backfill_updates]:
        item_metadata = item.metadata if isinstance(item.metadata, dict) else {}
        base_name = str(item_metadata.get("asset_base_name") or "").strip()
        if not base_name:
            continue
        try:
            version = int(item_metadata.get("asset_version") or 1)
        except (TypeError, ValueError):
            version = 1
        max_version_by_base[base_name] = max(max_version_by_base.get(base_name, 0), version)
        root_by_base.setdefault(base_name, str(item_metadata.get("root_asset_id") or item.asset_id))

    counters: dict[str, int] = {}
    single_counters: dict[str, int] = {}
    existing_base_names = [
        str(item.metadata.get("asset_base_name") or "")
        for item in existing_assets
        if isinstance(item.metadata, dict)
    ]
    updated_assets: list[AssetOutput] = []
    for asset in assets:
        if asset not in generated_assets:
            updated_assets.append(asset)
            continue
        counters[asset.asset_type] = counters.get(asset.asset_type, 0) + 1
        is_single_asset = is_single_asset_generation(asset.task_id)
        if is_single_asset:
            single_prefix = f"{campaign.brief.campaign_name.strip()}_manual_{asset.asset_type}_"
            if asset.asset_type not in single_counters:
                single_counters[asset.asset_type] = next_single_asset_index(existing_base_names, single_prefix) - 1
            single_counters[asset.asset_type] += 1
            base_name = single_asset_base_name(campaign.brief.campaign_name, asset.asset_type, single_counters[asset.asset_type])
            version = 1
            root_asset_id = asset.asset_id
        else:
            base_name = f"{default_asset_base_name(campaign, asset.asset_type)}_{counters[asset.asset_type]}"
            version = max_version_by_base.get(base_name, 0) + 1
            root_asset_id = root_by_base.get(base_name, asset.asset_id)
        metadata = dict(asset.metadata if isinstance(asset.metadata, dict) else {})
        metadata.update({
            "root_asset_id": root_asset_id,
            "parent_asset_id": root_asset_id if root_asset_id != asset.asset_id else None,
            "asset_base_name": base_name,
            "asset_version": version,
            "asset_name": asset_display_name(base_name, version),
            "display_name": asset_display_name(base_name, version),
        })
        updated_assets.append(AssetOutput(
            company_id=asset.company_id,
            asset_id=asset.asset_id,
            campaign_id=asset.campaign_id,
            task_id=asset.task_id,
            asset_type=asset.asset_type,
            url=asset.url,
            metadata={key: value for key, value in metadata.items() if value is not None},
            validation_status=asset.validation_status,
            created_at=asset.created_at,
            run_id=asset.run_id,
        ))

    if backfill_updates and persistence is not None:
        try:
            persistence.save_asset_outputs(backfill_updates)
        except Exception:
            metrics.inc("db_write_fail_total")
    return updated_assets


def safe_reference_excerpt(stored_path: str | None, file_type: str | None, max_chars: int = 1200) -> str:
    if not stored_path or not os.path.exists(stored_path):
        return ""
    lower_path = stored_path.lower()
    lower_type = (file_type or "").lower()
    text_like = (
        lower_type.startswith("text/")
        or lower_type in {"application/json", "application/xml", "application/csv"}
        or lower_path.endswith((".txt", ".md", ".csv", ".json", ".xml", ".html"))
    )
    if not text_like:
        return ""
    try:
        with open(stored_path, "r", encoding="utf-8", errors="ignore") as source:
            return source.read(max_chars).strip()
    except OSError:
        return ""


def list_campaign_reference_prompt_lines(campaign: CampaignRecord, limit: int = 8) -> list[str]:
    rows: list[dict[str, Any]] = []
    if persistence is not None:
        try:
            rows = persistence.list_campaign_references(campaign.campaign_id)
        except Exception:
            rows = []
    if not rows:
        for item in campaign_references.get(campaign.campaign_id, []):
            rows.append({
                "reference_id": item.reference_id,
                "file_name": item.file_name,
                "file_type": item.file_type,
                "stored_path": campaign_reference_files.get(campaign.campaign_id, {}).get(item.reference_id),
            })

    lines: list[str] = []
    for row in rows[:limit]:
        file_name = str(row.get("file_name") or "reference")
        file_type = str(row.get("file_type") or "")
        stored_path = str(row.get("stored_path") or "")
        excerpt = safe_reference_excerpt(stored_path, file_type)
        if excerpt:
            lines.append(f"- Manual/campaign reference: {file_name}\n  Excerpt: {excerpt}")
        else:
            lines.append(f"- Manual/campaign reference: {file_name} ({file_type or 'unknown type'})")
    return lines


def list_industry_knowledge_prompt_lines(campaign: CampaignRecord, limit: int = 8) -> list[str]:
    industry = (getattr(campaign.brief, "industry_category", "") or "").strip().lower()
    if not industry:
        return []
    rows: list[dict[str, Any]] = []
    if persistence is not None:
        try:
            rows = persistence.list_knowledge_items(campaign.company_id)
        except Exception:
            rows = []
    if not rows:
        rows = [item.model_dump(mode="python") for item in knowledge_items.get(campaign.company_id, [])]

    matched: list[dict[str, Any]] = []
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        category = str(metadata.get("category") or metadata.get("folder") or metadata.get("folder_name") or "")
        searchable = " ".join([
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            category,
            str(metadata.get("file_name") or ""),
        ]).lower()
        if industry in searchable or any(part and part in searchable for part in re.split(r"[\s,/，、|]+", industry)):
            matched.append(row)

    lines: list[str] = []
    for row in matched[:limit]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        category = str(metadata.get("category") or metadata.get("folder") or metadata.get("folder_name") or "uncategorized")
        file_name = str(metadata.get("file_name") or "")
        title = str(row.get("title") or file_name or "knowledge item")
        description = str(row.get("description") or "").strip()
        detail = f"- Industry-matched knowledge folder/item: [{category}] {title}"
        if file_name and file_name != title:
            detail += f" / file: {file_name}"
        if description:
            detail += f"\n  Summary: {description[:600]}"
        lines.append(detail)
    return lines


def build_campaign_prompt_context(campaign: CampaignRecord) -> str:
    brief = campaign.brief
    target = brief.target_audience
    project_description = getattr(brief, "project_description", "") or getattr(brief, "description", "") or ""
    parts = [
        f"Campaign: {brief.campaign_name}",
        f"Product/Brand: {brief.product_name}",
        f"Industry: {getattr(brief, 'industry_category', '') or 'N/A'}",
        f"Objective: {brief.objective}",
        f"Platforms: {', '.join(brief.platforms) if brief.platforms else 'N/A'}",
        f"Target audience: age={target.age_range}, gender={target.gender}, persona={target.persona}",
        f"Project brief: {project_description or 'N/A'}",
        f"Brand tone: {', '.join(brief.brand_tone) if brief.brand_tone else 'N/A'}",
        f"Budget: USD {brief.budget} (美金)",
        f"Deadline: {brief.deadline.isoformat() if hasattr(brief.deadline, 'isoformat') else brief.deadline}",
        (
            "Deliverables: "
            f"copy={brief.deliverables.copy_variants}, "
            f"image={brief.deliverables.image_assets}, "
            f"video={brief.deliverables.short_video_assets}, "
            f"ads_strategy={brief.deliverables.ads_strategy}"
        ),
    ]
    reference_lines = list_campaign_reference_prompt_lines(campaign)
    industry_knowledge_lines = list_industry_knowledge_prompt_lines(campaign)
    parts.extend([
        "Reference priority rules:",
        "- When generating, prioritize existing internal folder/knowledge-base content and manually uploaded campaign references over general web/model knowledge.",
        "- Use a 75:25 guidance ratio: 75% internal folder/manual reference facts and style cues, 25% general web/model knowledge for supplemental context only.",
        "- Based on the industry/category above, first consult and align with matching knowledge folders/items before using unrelated references.",
        "- If internal/manual references conflict with general knowledge, follow the internal/manual references unless they are unsafe or impossible.",
    ])
    if industry_knowledge_lines:
        parts.append("Industry/category matched knowledge references:")
        parts.extend(industry_knowledge_lines)
    if reference_lines:
        parts.append("Manual uploaded / attached campaign references:")
        parts.extend(reference_lines)
    if brief.mandatory_elements:
        parts.append("Must include: " + ", ".join(brief.mandatory_elements))
    if brief.forbidden_elements:
        parts.append("Avoid: " + ", ".join(brief.forbidden_elements))
    return "\n".join(parts)


def build_image_generation_prompt(campaign: CampaignRecord) -> str:
    brief = campaign.brief
    parts = [
        build_campaign_prompt_context(campaign),
        "",
        "Image generation task: Create campaign visual assets using all campaign context above.",
    ]

    intent_text = " ".join(parts).lower()
    comparison_terms = ["比較", "對比", "comparison", "compare", "vs", "versus", "排行", "排名"]
    if any(term in intent_text for term in comparison_terms):
        parts.append(
            "Create a comparison infographic, not a product-only hero image. "
            "Use a clear table/card layout comparing multiple options with headings, columns, labels, icons, and concise data points. "
            "The visual should communicate differences at a glance and look like a shareable market comparison chart."
        )
    else:
        parts.append("Create a campaign key visual aligned with the campaign name and user brief.")

    return "\n".join(parts)


def build_copy_generation_prompt(campaign: CampaignRecord) -> str:
    return "\n\n".join(
        [
            build_campaign_prompt_context(campaign),
            "Copywriting task: Generate campaign copy using all campaign context above. Preserve the project brief intent and industry context.",
        ]
    )


def build_video_generation_prompt(campaign: CampaignRecord) -> str:
    return "\n\n".join(
        [
            build_campaign_prompt_context(campaign),
            "Video generation task: Create a polished short vertical social media ad video using all campaign context above.",
            "Output requirements: duration 6 seconds, aspect ratio 9:16 vertical, MP4, 1080p high-definition quality if supported, commercial-grade sharp visuals, smooth motion, readable Traditional Chinese text overlays when text is needed, clear CTA ending, no blurry frames, no distorted logos/text, no misleading claims.",
        ]
    )


def build_worker_payload_for_task(campaign: CampaignRecord, task: dict[str, Any] | TaskRecord) -> dict[str, Any]:
    """Build the exact worker payload from the campaign brief so orchestrator does not use generic English defaults."""
    task_id = task.get("task_id") if isinstance(task, dict) else task.task_id
    task_type = task.get("task_type") if isinstance(task, dict) else task.task_type
    company_id = campaign.company_id or ""
    campaign_id = campaign.campaign_id
    if task_type == "copywriting":
        return {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "prompt": build_copy_generation_prompt(campaign),
            "brand_context": {
                "campaign_name": campaign.brief.campaign_name,
                "product_name": campaign.brief.product_name,
                "industry_category": getattr(campaign.brief, "industry_category", ""),
                "project_description": getattr(campaign.brief, "project_description", "") or getattr(campaign.brief, "description", ""),
                "objective": campaign.brief.objective,
                "platforms": campaign.brief.platforms,
                "brand_tone": campaign.brief.brand_tone,
                "target_audience": campaign.brief.target_audience.model_dump(mode="json"),
                "budget": campaign.brief.budget,
                "deadline": campaign.brief.deadline.isoformat() if hasattr(campaign.brief.deadline, "isoformat") else str(campaign.brief.deadline),
            },
            "variants": min(10, max(0, int(campaign.brief.deliverables.copy_variants or 0))),
        }
    if task_type == "image_generation":
        image_prompt = build_image_generation_prompt(campaign)
        return {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "prompt": image_prompt,
            "sizes": image_sizes_for_count(campaign.brief.deliverables.image_assets),
            "style_profile": {"preset": "infographic" if "comparison infographic" in image_prompt else "photographic"},
        }
    if task_type == "video_generation":
        return {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "prompt": build_video_generation_prompt(campaign),
            "duration": 6,
            "aspect_ratio": "9:16",
        }
    if task_type == "ads_strategy":
        return {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "objective": campaign.brief.objective,
            "budget": float(campaign.brief.budget),
            "platforms": campaign.brief.platforms,
        }
    return {}


def task_enabled_by_deliverables(task_type: str, brief: CampaignBrief) -> bool:
    if task_type == "copywriting":
        return int(brief.deliverables.copy_variants or 0) > 0
    if task_type == "image_generation":
        return int(brief.deliverables.image_assets or 0) > 0
    if task_type == "video_generation":
        return int(brief.deliverables.short_video_assets or 0) > 0
    if task_type == "ads_strategy":
        return int(brief.deliverables.ads_strategy or 0) > 0
    return True


def apply_deliverable_task_gates(tasks: list[TaskRecord], brief: CampaignBrief) -> list[TaskRecord]:
    return [
        task if task_enabled_by_deliverables(task.task_type, brief) else task.model_copy(update={"status": "passed"})
        for task in tasks
    ]


def image_sizes_for_count(count: int) -> list[str]:
    desired = max(0, min(5, int(count or 0)))
    base = ["1024x1024", "1080x1350", "1080x1920", "1350x1080", "1024x1024"]
    return base[:desired]


def is_visual_comparison_request(brief: CampaignBrief) -> bool:
    text = " ".join(
        [
            brief.campaign_name,
            brief.product_name,
            getattr(brief, "description", "") or "",
            " ".join(brief.mandatory_elements),
        ]
    ).lower()
    comparison = any(term in text for term in ["比較", "對比", "comparison", "compare", "vs", "versus", "排行", "排名"])
    visual = any(term in text for term in ["圖", "圖片", "照片", "image", "visual", "infographic", "資訊圖"])
    return comparison and visual


def explicitly_requests_copy(brief: CampaignBrief) -> bool:
    text = " ".join(
        [
            getattr(brief, "description", "") or "",
            " ".join(brief.mandatory_elements),
        ]
    ).lower()
    return any(term in text for term in ["文案", "貼文", "copy", "caption", "post", "社群貼文"])


def normalize_visual_only_deliverables(brief: CampaignBrief) -> CampaignBrief:
    """Prevent visual-only comparison requests from inheriting copy/video defaults."""
    if not is_visual_comparison_request(brief) or explicitly_requests_copy(brief):
        return brief
    deliverables = brief.deliverables.model_copy(
        update={
            "copy_variants": 0,
            "image_assets": int(brief.deliverables.image_assets or 0),
            "short_video_assets": 0,
            "ads_strategy": 0,
        }
    )
    return brief.model_copy(update={"deliverables": deliverables})


def generate_outputs_via_workers(company_id: str, campaign_id: str, campaign: CampaignRecord, tasks: list[TaskRecord], run_id: str | None = None) -> tuple[list[AssetOutput], list[ValidationResult]]:
    company_id = company_id or ""
    now = now_utc()
    assets: list[AssetOutput] = []
    validations: list[ValidationResult] = []

    for task in tasks:
        if task.task_type not in {"copywriting", "image_generation", "video_generation", "ads_strategy"}:
            continue

        try:
            if not task_enabled_by_deliverables(task.task_type, campaign.brief):
                continue

            if task.task_type == "copywriting":
                copy_prompt = build_copy_generation_prompt(campaign)
                copy_resp = _worker_post_json(
                    f"{WORKER_COPY_URL}/internal/workers/copy/run",
                    {
                        "task_id": task.task_id,
                        "campaign_id": campaign_id,
                        "company_id": company_id,
                        "prompt": copy_prompt,
                        "brand_context": {
                            "campaign_name": campaign.brief.campaign_name,
                            "product_name": campaign.brief.product_name,
                            "industry_category": getattr(campaign.brief, "industry_category", ""),
                            "project_description": getattr(campaign.brief, "project_description", "") or getattr(campaign.brief, "description", ""),
                            "objective": campaign.brief.objective,
                            "platforms": campaign.brief.platforms,
                            "brand_tone": campaign.brief.brand_tone,
                            "target_audience": campaign.brief.target_audience.model_dump(mode="json"),
                            "budget": campaign.brief.budget,
                            "deadline": campaign.brief.deadline.isoformat() if hasattr(campaign.brief.deadline, "isoformat") else str(campaign.brief.deadline),
                        },
                        "variants": min(10, max(0, int(campaign.brief.deliverables.copy_variants or 0))),
                    },
                    "copywriting",
                    campaign_id,
                    task.task_id,
                    company_id,
                )
                variants = copy_resp.get("variants", [])
                for idx, variant in enumerate(variants):
                    if not isinstance(variant, dict):
                        continue
                    body = variant.get("body")
                    if not isinstance(body, str) or not body.strip():
                        continue
                    asset_id = f"ast_{uuid4().hex[:10]}"
                    asset = AssetOutput(
                        company_id=company_id,
                        asset_id=asset_id,
                        campaign_id=campaign_id,
                        task_id=task.task_id,
                        asset_type="copy",
                        url=f"generated://copy/{campaign_id}/{task.task_id}/{idx+1}",
                        metadata={"variant": variant, "task_type": task.task_type, "priority": task.priority},
                        validation_status="passed",
                        created_at=now,
                        run_id=run_id,
                    )
                    if not is_displayable_asset(asset):
                        continue
                    assets.append(asset)
                    append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

            elif task.task_type == "image_generation":
                image_prompt = build_image_generation_prompt(campaign)
                image_resp = _worker_post_json(
                    f"{WORKER_IMAGE_URL}/internal/workers/image/run",
                    {
                        "task_id": task.task_id,
                        "campaign_id": campaign_id,
                        "prompt": image_prompt,
                        "sizes": image_sizes_for_count(campaign.brief.deliverables.image_assets),
                        "style_profile": {"preset": "infographic" if "comparison infographic" in image_prompt else "photographic"},
                    },
                    "image_generation",
                    campaign_id,
                    task.task_id,
                    company_id,
                )
                for image_item in image_resp.get("image_assets", []):
                    if not isinstance(image_item, dict):
                        continue
                    image_url = str(image_item.get("url", "")).strip()
                    if not is_openable_asset_url(image_url):
                        continue
                    asset_id = f"ast_{uuid4().hex[:10]}"
                    metadata = {"size": image_item.get("size"), "task_type": task.task_type, "priority": task.priority}
                    try:
                        image_url, cached_metadata = cache_generated_asset_url(
                            company_id=company_id,
                            campaign_id=campaign_id,
                            asset_id=asset_id,
                            asset_type="image",
                            source_url=image_url,
                        )
                        metadata.update(cached_metadata)
                    except Exception as exc:
                        logger.warning(f"Failed to cache generated image asset {asset_id}: {exc}")
                    asset = AssetOutput(
                        company_id=company_id,
                        asset_id=asset_id,
                        campaign_id=campaign_id,
                        task_id=task.task_id,
                        asset_type="image",
                        url=image_url,
                        metadata=metadata,
                        validation_status="passed",
                        created_at=now,
                        run_id=run_id,
                    )
                    if not is_displayable_asset(asset):
                        continue
                    assets.append(asset)
                    append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

            elif task.task_type == "video_generation":
                video_prompt = build_video_generation_prompt(campaign)
                video_resp = _worker_post_json(
                    f"{WORKER_VIDEO_URL}/internal/workers/video/run",
                    {
                        "task_id": task.task_id,
                        "campaign_id": campaign_id,
                        "company_id": company_id,
                        "prompt": video_prompt,
                        "duration": 6,
                        "aspect_ratio": "9:16",
                    },
                    "video_generation",
                    campaign_id,
                    task.task_id,
                    company_id,
                )
                asset_id = f"ast_{uuid4().hex[:10]}"
                video_url = str(video_resp.get("video_url", "")).strip()
                metadata = {
                    "thumbnail_url": video_resp.get("thumbnail_url"),
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "provider": video_resp.get("provider"),
                    "model_name": video_resp.get("model_name"),
                    "fallback_reason": video_resp.get("fallback_reason"),
                    "fallback_detail": video_resp.get("fallback_detail"),
                }
                if is_openable_asset_url(video_url):
                    try:
                        video_url, cached_metadata = cache_generated_asset_url(
                            company_id=company_id,
                            campaign_id=campaign_id,
                            asset_id=asset_id,
                            asset_type="video",
                            source_url=video_url,
                        )
                        metadata.update(cached_metadata)
                    except Exception as exc:
                        logger.warning(f"Failed to cache generated video asset {asset_id}: {exc}")
                asset = AssetOutput(
                    company_id=company_id,
                    asset_id=asset_id,
                    campaign_id=campaign_id,
                    task_id=task.task_id,
                    asset_type="video",
                    url=video_url,
                    metadata=metadata,
                    validation_status="passed",
                    created_at=now,
                    run_id=run_id,
                )
                if is_displayable_asset(asset):
                    assets.append(asset)
                    append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

            elif task.task_type == "ads_strategy":
                ads_resp = _worker_post_json(
                    f"{WORKER_ADS_URL}/internal/workers/ads/run",
                    {
                        "task_id": task.task_id,
                        "campaign_id": campaign_id,
                        "company_id": company_id,
                        "objective": campaign.brief.objective,
                        "budget": float(campaign.brief.budget),
                        "platforms": campaign.brief.platforms,
                    },
                    "ads_strategy",
                    campaign_id,
                    task.task_id,
                    company_id,
                )
                asset_id = f"ast_{uuid4().hex[:10]}"
                asset = AssetOutput(
                    company_id=company_id,
                    asset_id=asset_id,
                    campaign_id=campaign_id,
                    task_id=task.task_id,
                    asset_type="ads",
                    url=f"generated://ads/{campaign_id}/{task.task_id}",
                    metadata={"ads_plan": ads_resp.get("ads_plan", {}), "task_type": task.task_type, "priority": task.priority},
                    validation_status="passed",
                    created_at=now,
                    run_id=run_id,
                )
                if is_displayable_asset(asset):
                    assets.append(asset)
                    append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)
            metrics.inc("worker_task_complete_total")
        except RuntimeError as exc:
            _notify_webhook(
                event_type="worker_dispatch_failed",
                campaign_id=campaign_id,
                payload={
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "error_code": _classify_worker_error(str(exc)),
                    "error": str(exc),
                },
                company_id=company_id,
            )

    return assets, validations


def tasks_missing_displayable_assets_for_run(campaign_id: str, tasks: list[TaskRecord], run_id: str | None) -> list[TaskRecord]:
    """Return tasks that do not have displayable assets for the requested run.

    Re-runs can leave older assets on the same campaign. Those older assets must
    not satisfy latest-run deliverables, otherwise a missing video in the latest
    run can be hidden by a previous run's video asset.
    """
    task_asset_type = {
        "copywriting": "copy",
        "image_generation": "image",
        "video_generation": "video",
        "ads_strategy": "ads",
    }
    current_assets = [
        asset
        for asset in list_assets(campaign_id)
        if is_displayable_asset(asset) and (run_id is None or asset.run_id == run_id)
    ]
    available_pairs = {(asset.task_id, asset.asset_type) for asset in current_assets}
    missing: list[TaskRecord] = []
    for task in tasks:
        expected_type = task_asset_type.get(task.task_type)
        if expected_type is None:
            continue
        if (task.task_id, expected_type) not in available_pairs:
            missing.append(task)
    return missing


def _notify_webhook(event_type: str, campaign_id: str, payload: dict[str, Any], company_id: str = "") -> None:
    if persistence is None:
        return
    try:
        subs = persistence.list_webhook_subscriptions(company_id=company_id or None, active=True)
    except Exception:
        return
    for sub in subs:
        events = sub.get("events", [])
        if event_type not in events:
            continue
        url = sub["url"]
        secret = sub.get("secret", "")
        log_id = f"wlog_{campaign_id}_{sub['sub_id']}_{int(datetime.utcnow().timestamp())}"
        body = {
            "event_type": event_type,
            "campaign_id": campaign_id,
            "payload": payload,
            "timestamp": now_utc().isoformat(),
        }
        body_bytes = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if secret:
            import hmac, hashlib
            signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
            headers["X-AMF-Signature"] = f"sha256={signature}"
        req = request.Request(url, method="POST", headers=headers, data=body_bytes)
        status = "delivered"
        response_code = None
        response_body = None
        try:
            with request.urlopen(req, timeout=10) as resp:
                response_code = resp.status
                response_body = resp.read(512).decode("utf-8", errors="replace")
        except request.HTTPError as e:
            response_code = e.code
            response_body = str(e.reason)
            status = "failed"
        except Exception as e:
            response_body = str(e)
            status = "failed"
        try:
            persistence.log_webhook_delivery(
                log_id=log_id,
                sub_id=sub["sub_id"],
                event_type=event_type,
                payload_json=body,
                response_code=response_code,
                response_body=response_body,
                attempt=1,
                status=status,
            )
        except Exception:
            pass


def build_review_items() -> list[ReviewItem]:
    if persistence is not None:
        try:
            if not getattr(build_review_items, "_backfilled", False):
                persistence.backfill_review_items()
                setattr(build_review_items, "_backfilled", True)
            rows = persistence.list_review_items()
            return [
                ReviewItem(
                    review_id=str(row["review_id"]),
                    campaign_id=str(row["campaign_id"]),
                    asset_id=str(row["asset_id"]),
                    asset_name=asset_metadata_name(row.get("metadata")),
                    asset_type=str(row.get("asset_type") or "unknown"),
                    reason=row.get("reason"),
                    score=float(row["score"]),
                    status=str(row["status"]),
                    submitted_at=row["submitted_at"].isoformat() if hasattr(row["submitted_at"], "isoformat") else str(row["submitted_at"]),
                    assignee=row.get("assignee"),
                    run_id=row.get("run_id"),
                )
                for row in rows
            ]
        except Exception:
            metrics.inc("db_write_fail_total")

    items: list[ReviewItem] = []

    for campaign in store.list_campaigns():
        asset_map = {asset.asset_id: asset for asset in list_assets(campaign.campaign_id) if is_displayable_asset(asset)}
        validations = list_validation(campaign.campaign_id)
        for validation in validations:
            if validation.asset_id not in asset_map:
                continue
            review_id = f"rev_{validation.validation_id}"
            status = review_status_overrides.get(review_id, "review_pending")
            items.append(
                ReviewItem(
                    review_id=review_id,
                    campaign_id=validation.campaign_id,
                    asset_id=validation.asset_id,
                    asset_name=asset_metadata_name(asset_map[validation.asset_id].metadata),
                    asset_type=asset_map[validation.asset_id].asset_type,
                    reason=None,
                    score=validation.score,
                    status=status,
                    submitted_at=validation.created_at.isoformat(),
                    assignee=None,
                    run_id=None,
                )
            )

    return sorted(items, key=lambda item: item.submitted_at, reverse=True)


def list_review_items_filtered(status: str | None = None, campaign_id: str | None = None, run_id: str | None = None) -> list[ReviewItem]:
    items = build_review_items()
    if status:
        items = [item for item in items if item.status == status]
    if campaign_id:
        items = [item for item in items if item.campaign_id == campaign_id]
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    return items


def find_review_item(review_id: str) -> ReviewItem | None:
    for item in build_review_items():
        if item.review_id == review_id:
            return item
    return None


def append_review_audit(
    action: str,
    target: str,
    result: str,
    operator: str,
    reason: str | None = None,
) -> None:
    review_audit_logs.append(
        ReviewAuditEntry(
            timestamp=now_utc().isoformat(),
            operator=operator,
            action=action,
            target=target,
            result=result,
            reason=reason,
        )
    )


def to_template_tasks(task_records: list[TaskRecord]) -> list[WorkflowTemplateTask]:
    ordered = sorted(task_records, key=lambda task: task.priority)
    return [
        WorkflowTemplateTask(
            task_type=task.task_type,
            depends_on=task.depends_on,
            priority=task.priority,
            acceptance=task.acceptance,
        )
        for task in ordered
    ]


def resolve_template_tasks(source_campaign_id: str | None, tasks: list[WorkflowTemplateTask] | None) -> list[WorkflowTemplateTask]:
    if tasks is not None and len(tasks) > 0:
        return tasks

    if source_campaign_id:
        existing = store.get_tasks(source_campaign_id)
        if existing:
            return to_template_tasks(existing)

        try:
            synced = sync_tasks_from_orchestrator(source_campaign_id)
            if synced:
                return to_template_tasks(synced)
        except RuntimeError:
            pass

    return [
        WorkflowTemplateTask(
            task_type="copywriting",
            depends_on=[],
            priority=1,
            acceptance=["At least 3 variants", "Contains CTA"],
        ),
        WorkflowTemplateTask(
            task_type="image_generation",
            depends_on=["copywriting"],
            priority=2,
            acceptance=["1:1 and 4:5 dimensions"],
        ),
        WorkflowTemplateTask(
            task_type="video_generation",
            depends_on=["image_generation"],
            priority=3,
            acceptance=["Under 15 seconds"],
        ),
        WorkflowTemplateTask(
            task_type="ads_strategy",
            depends_on=["copywriting", "image_generation"],
            priority=2,
            acceptance=["Channel budget split"],
        ),
    ]


def get_template_or_404(template_id: str) -> WorkflowTemplate:
    load_persisted_workflow_templates()
    template = workflow_templates.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return template


def load_persisted_workflow_templates() -> None:
    if persistence is None:
        return
    try:
        rows = persistence.list_workflow_templates()
    except Exception:
        return
    for row in rows:
        template = WorkflowTemplate(**row["template"])
        versions = [WorkflowTemplateVersion(**version) for version in row["versions"]]
        workflow_templates[template.template_id] = template
        workflow_template_versions[template.template_id] = versions


def persist_workflow_template(template_id: str) -> None:
    if persistence is None:
        return
    template = workflow_templates.get(template_id)
    if template is None:
        return
    persistence.upsert_workflow_template(
        template.model_dump(mode="json"),
        [version.model_dump(mode="json") for version in workflow_template_versions.get(template_id, [])],
    )


def build_reference_download_url(base_url: str, campaign_id: str, reference_id: str) -> str:
    # Use a same-origin URL for browsers. The service may see an internal
    # base_url such as http://127.0.0.1:8080 behind Caddy/ngrok; returning that
    # breaks HTTPS pages and opens blank/error tabs for uploaded references.
    return f"/api/v1/campaigns/{campaign_id}/references/{reference_id}/download"


def reference_file_exists(payload: dict[str, Any]) -> bool:
    stored_path = str(payload.get("stored_path") or "")
    return bool(stored_path) and os.path.exists(stored_path)


def to_reference_record(base_url: str, payload: dict[str, Any]) -> CampaignReferenceRecord:
    uploaded_at_value = payload.get("uploaded_at")
    if isinstance(uploaded_at_value, datetime):
        uploaded_at = uploaded_at_value.isoformat()
    else:
        uploaded_at = str(uploaded_at_value)

    reference_id = str(payload.get("reference_id"))
    campaign_id = str(payload.get("campaign_id"))
    return CampaignReferenceRecord(
        reference_id=reference_id,
        campaign_id=campaign_id,
        file_name=str(payload.get("file_name")),
        file_type=str(payload.get("file_type") or "application/octet-stream"),
        file_size=int(payload.get("file_size") or 0),
        uploaded_at=uploaded_at,
        download_url=build_reference_download_url(base_url, campaign_id, reference_id),
        folder=str(payload.get("folder") or "General"),
    )


def validate_reference_upload(file_name: str, file_type: str, file_size: int) -> None:
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in REFERENCE_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension")

    if file_size > REFERENCE_MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds upload limit")


def get_reference_payload_or_404(campaign_id: str, reference_id: str) -> dict[str, Any]:
    if persistence is not None:
        payload = persistence.get_campaign_reference(campaign_id, reference_id)
        if payload is not None:
            return payload
        raise HTTPException(status_code=404, detail="Campaign reference not found")

    refs = campaign_references.get(campaign_id, [])
    for item in refs:
        if item.reference_id == reference_id:
            path_map = campaign_reference_files.get(campaign_id, {})
            stored_path = path_map.get(reference_id)
            if stored_path is None:
                raise HTTPException(status_code=404, detail="Campaign reference file not found")
            return {
                "reference_id": item.reference_id,
                "campaign_id": item.campaign_id,
                "file_name": item.file_name,
                "file_type": item.file_type,
                "file_size": item.file_size,
                "uploaded_at": item.uploaded_at,
                "stored_path": stored_path,
            }

    raise HTTPException(status_code=404, detail="Campaign reference not found")


def normalize_chatbot_audit_record(payload: dict[str, Any]) -> ChatbotAuditRecord:
    timestamp_value = payload.get("timestamp")
    if isinstance(timestamp_value, datetime):
        timestamp = timestamp_value.isoformat()
    else:
        timestamp = str(timestamp_value)

    return ChatbotAuditRecord(
        audit_id=str(payload.get("audit_id")),
        timestamp=timestamp,
        actor_id=str(payload.get("actor_id")),
        actor_role=str(payload.get("actor_role")),
        locale=str(payload.get("locale")),
        message=str(payload.get("message")),
        intent=str(payload.get("intent")),
        ok=bool(payload.get("ok")),
        detail=str(payload.get("detail")) if payload.get("detail") is not None else None,
        request_pending_action_type=str(payload.get("request_pending_action_type"))
        if payload.get("request_pending_action_type") is not None
        else None,
        request_pending_campaign_id=str(payload.get("request_pending_campaign_id"))
        if payload.get("request_pending_campaign_id") is not None
        else None,
        request_pending_reference_id=str(payload.get("request_pending_reference_id"))
        if payload.get("request_pending_reference_id") is not None
        else None,
        request_pending_review_id=str(payload.get("request_pending_review_id"))
        if payload.get("request_pending_review_id") is not None
        else None,
        result_pending_action_type=str(payload.get("result_pending_action_type"))
        if payload.get("result_pending_action_type") is not None
        else None,
        result_pending_campaign_id=str(payload.get("result_pending_campaign_id"))
        if payload.get("result_pending_campaign_id") is not None
        else None,
        result_pending_reference_id=str(payload.get("result_pending_reference_id"))
        if payload.get("result_pending_reference_id") is not None
        else None,
        result_pending_review_id=str(payload.get("result_pending_review_id"))
        if payload.get("result_pending_review_id") is not None
        else None,
    )


def validate_actor_role_or_400(actor_role: str) -> None:
    if actor_role not in {"admin", "operator", "system"}:
        raise HTTPException(status_code=400, detail="actor_role must be admin, operator, or system")


def require_internal_api_key(req: Request) -> None:
    if not CHATBOT_INTERNAL_API_KEY:
        raise HTTPException(status_code=503, detail="CHATBOT_INTERNAL_API_KEY is not configured")
    provided = req.headers.get("x-internal-api-key")
    if provided != CHATBOT_INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_review_action_access(req: Request) -> None:
    """Allow review actions from internal automation, platform admin, or privileged company members."""
    if is_internal_api_key_request(req):
        return
    if is_platform_admin_request(req):
        return
    payload = require_jwt(req)
    require_any_permission(
        payload,
        {
            "review:manage",
            "review:approve",
            "review:reject",
            "review:revision",
            "campaign:review",
            "campaign:approve",
            "role:manage",
        },
    )


def is_internal_api_key_request(req: Request) -> bool:
    provided = req.headers.get("x-internal-api-key")
    return bool(CHATBOT_INTERNAL_API_KEY and provided == CHATBOT_INTERNAL_API_KEY)


def require_campaign_trace_access(req: Request, campaign: CampaignRecord) -> None:
    """Allow trace read via internal key, platform key, or member JWT (company scoped)."""
    provided_internal_key = req.headers.get("x-internal-api-key")
    if CHATBOT_INTERNAL_API_KEY and provided_internal_key == CHATBOT_INTERNAL_API_KEY:
        return

    if is_platform_admin_request(req):
        return

    payload = require_jwt(req)
    actor_company_id = payload.company_id or ""
    if campaign.company_id != actor_company_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this campaign")


def require_system_operations_access(req: Request) -> None:
    """Allow system ops via internal key, platform key, or privileged member JWT."""
    provided_internal_key = req.headers.get("x-internal-api-key")
    if CHATBOT_INTERNAL_API_KEY and provided_internal_key == CHATBOT_INTERNAL_API_KEY:
        return

    if is_platform_admin_request(req):
        return

    payload = require_jwt(req)
    require_any_permission(payload, {"system:manage", "operations:manage", "role:manage"})


def require_authenticated_read_access(req: Request) -> None:
    if is_internal_api_key_request(req) or is_platform_admin_request(req):
        return
    require_jwt(req)


def has_any_permission(payload: JWTPayload, allowed: set[str]) -> bool:
    permissions = set(payload.permissions or [])
    return bool(permissions.intersection(allowed | {"*", "admin", "platform:admin"}))


def require_any_permission(payload: JWTPayload, allowed: set[str]) -> None:
    if not has_any_permission(payload, allowed):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def require_campaign_access(req: Request, campaign: CampaignRecord) -> JWTPayload | None:
    if is_platform_admin_request(req) or is_internal_api_key_request(req):
        return None
    payload = require_jwt(req)
    actor_company_id = payload.company_id or ""
    if campaign.company_id != actor_company_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this campaign")
    return payload


def resolve_workflow_actor(req: Request) -> tuple[str, JWTPayload | None]:
    if is_platform_admin_request(req):
        return "platform-admin", None
    if is_internal_api_key_request(req):
        return (req.headers.get("x-actor-id") or "workflow-template").strip() or "workflow-template", None
    payload = require_jwt(req)
    return payload.sub, payload


def resolve_internal_actor(req: Request) -> tuple[str, str]:
    actor_id = (req.headers.get("x-actor-id") or "system").strip() or "system"
    actor_role = (req.headers.get("x-actor-role") or "operator").strip() or "operator"
    if actor_role not in {"admin", "operator", "system"}:
        actor_role = "operator"
    return actor_id, actor_role


def require_persistent_chat_audit() -> None:
    if CHAT_AUDIT_REQUIRE_PERSISTENCE and persistence is None:
        raise HTTPException(status_code=503, detail="Chatbot audit persistence unavailable")


def run_trace_cleanup(force: bool = False) -> dict[str, int]:
    global last_trace_cleanup_at

    now = now_utc()
    if not force and last_trace_cleanup_at is not None:
        elapsed_hours = (now - last_trace_cleanup_at).total_seconds() / 3600
        if elapsed_hours < TRACE_CLEANUP_INTERVAL_HOURS:
            return {"deleted_events": 0, "deleted_chat": 0, "deleted_traces": 0}

    cutoff = now.replace(microsecond=0)
    cutoff = cutoff - timedelta(days=max(1, TRACE_RETENTION_DAYS))

    if persistence is not None:
        metrics.inc("trace_cleanup_total")
        result = persistence.cleanup_campaign_trace_before(cutoff)
        last_trace_cleanup_at = now
        return result

    deleted_events = 0
    deleted_chat = 0
    deleted_traces = 0
    cutoff_iso = cutoff.isoformat()

    for campaign_id, items in list(campaign_trace_events.items()):
        kept = [item for item in items if item.created_at >= cutoff_iso]
        deleted_events += max(0, len(items) - len(kept))
        campaign_trace_events[campaign_id] = kept

    for campaign_id, items in list(campaign_trace_chats.items()):
        kept = [item for item in items if item.created_at >= cutoff_iso]
        deleted_chat += max(0, len(items) - len(kept))
        campaign_trace_chats[campaign_id] = kept

    for campaign_id, trace in list(campaign_traces.items()):
        has_events = any(item.trace_id == trace.trace_id for item in campaign_trace_events.get(campaign_id, []))
        has_chat = any(item.trace_id == trace.trace_id for item in campaign_trace_chats.get(campaign_id, []))
        if not has_events and not has_chat and trace.updated_at < cutoff_iso:
            deleted_traces += 1
            campaign_traces.pop(campaign_id, None)

    metrics.inc("trace_cleanup_total")
    last_trace_cleanup_at = now
    return {
        "deleted_events": deleted_events,
        "deleted_chat": deleted_chat,
        "deleted_traces": deleted_traces,
    }


def run_scheduled_sla_scan() -> SlaScanResponse:
    global _last_sla_scan_at
    if not SLA_SCAN_ENABLED:
        return SlaScanResponse(scanned=0, escalated=0, overdue_pending=0)
    now = now_utc()
    if _last_sla_scan_at is not None:
        elapsed = (now - _last_sla_scan_at).total_seconds()
        if elapsed < SLA_SCAN_INTERVAL_SECONDS:
            return SlaScanResponse(scanned=0, escalated=0, overdue_pending=0)
    _last_sla_scan_at = now
    return scan_and_enforce_work_order_sla(limit=500, operator="scheduler")


def parse_iso_datetime_or_400(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be ISO-8601") from exc


def parse_optional_iso_datetime_or_400(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return parse_iso_datetime_or_400(trimmed, field_name)


def is_work_order_overdue(status: str, due_at_iso: str | None) -> bool:
    if not due_at_iso:
        return False
    if status in {"done", "cancelled"}:
        return False
    due_dt = parse_iso_datetime_or_400(due_at_iso, "due_at")
    return due_dt < now_utc()


def parse_trace_cursor_or_400(value: str, field_name: str, kind: Literal["event", "chat"]) -> tuple[datetime, str]:
    parts = value.split("|", 1)
    created_at = parse_iso_datetime_or_400(parts[0], field_name)
    if len(parts) == 2:
        item_id = parts[1].strip()
        if not item_id:
            raise HTTPException(status_code=400, detail=f"{field_name} must include a cursor id")
        return (created_at, item_id)

    if kind == "event":
        return (created_at, "evt_~")
    return (created_at, "msg_~")


def to_trace_cursor(created_at: str, item_id: str) -> str:
    return f"{created_at}|{item_id}"


def to_trace_record(payload: dict[str, Any]) -> CampaignTraceRecord:
    created_at = payload.get("created_at")
    updated_at = payload.get("updated_at")
    return CampaignTraceRecord(
        trace_id=str(payload.get("trace_id")),
        campaign_id=str(payload.get("campaign_id")),
        created_by=str(payload.get("created_by")),
        source=str(payload.get("source")),
        created_at=created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
        updated_at=updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at),
    )


def ensure_campaign_trace(campaign_id: str, created_by: str, source: str, company_id: str | None = None) -> CampaignTraceRecord:
    if company_id is None:
        campaign = store.get_campaign(campaign_id)
        if campaign is not None:
            company_id = campaign.company_id

    if persistence is not None:
        existing = persistence.get_campaign_trace_by_campaign_id(campaign_id)
        if existing is not None:
            return to_trace_record(existing)

        trace_id = f"trace_{uuid4().hex[:12]}"
        created_at = now_utc()
        persistence.create_campaign_trace(trace_id, campaign_id, created_by, source, created_at)
        created = persistence.get_campaign_trace_by_campaign_id(campaign_id)
        if created is not None:
            record = {**created, "company_id": company_id}
            return to_trace_record(record)

    existing_fallback = campaign_traces.get(campaign_id)
    if existing_fallback is not None:
        return existing_fallback

    now = now_utc().isoformat()
    trace = CampaignTraceRecord(
        company_id=company_id or "",
        trace_id=f"trace_{uuid4().hex[:12]}",
        campaign_id=campaign_id,
        created_by=created_by,
        source=source,
        created_at=now,
        updated_at=now,
    )
    campaign_traces[campaign_id] = trace
    return trace


def lookup_campaign_trace(campaign_id: str) -> CampaignTraceRecord | None:
    if persistence is not None:
        existing = persistence.get_campaign_trace_by_campaign_id(campaign_id)
        if existing is not None:
            return to_trace_record(existing)
        return None
    return campaign_traces.get(campaign_id)


def append_trace_event(
    campaign_id: str,
    event_type: str,
    actor_id: str,
    actor_role: str,
    summary: str,
    payload: dict[str, Any],
    source: str,
    company_id: str | None = None,
) -> CampaignTraceEventRecord:
    try:
        run_trace_cleanup(force=False)
    except Exception as exc:
        metrics.inc("trace_cleanup_fail_total")
        logger.warning(f"Trace cleanup failed in append_trace_event: {exc}")

    # Resolve company_id from campaign if not provided
    if company_id is None:
        campaign = store.get_campaign(campaign_id)
        if campaign is not None:
            company_id = campaign.company_id

    metrics.inc("trace_event_write_total")
    trace = ensure_campaign_trace(campaign_id, actor_id, source)
    event_id = f"evt_{uuid4().hex[:12]}"
    created_at_dt = now_utc()
    created_at = created_at_dt.isoformat()
    record = CampaignTraceEventRecord(
        company_id=company_id or "",
        event_id=event_id,
        trace_id=trace.trace_id,
        campaign_id=campaign_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=summary,
        payload=payload,
        created_at=created_at,
    )

    if persistence is not None:
        try:
            persistence.append_campaign_trace_event(
                event_id=event_id,
                trace_id=trace.trace_id,
                campaign_id=campaign_id,
                event_type=event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                summary=summary,
                payload_json=json.dumps(payload),
                created_at=created_at_dt,
                company_id=company_id or "",
            )
        except Exception:
            metrics.inc("trace_event_write_fail_total")
            raise
    else:
        campaign_trace_events.setdefault(campaign_id, []).insert(0, record)
        trace.updated_at = created_at
        campaign_traces[campaign_id] = trace

    return record


def append_trace_chat_message(
    campaign_id: str,
    role: str,
    content_masked: str,
    actor_id: str,
    source: str,
    raw_ref: str | None = None,
    company_id: str | None = None,
) -> CampaignTraceChatRecord:
    try:
        run_trace_cleanup(force=False)
    except Exception as exc:
        metrics.inc("trace_cleanup_fail_total")
        logger.warning(f"Trace cleanup failed in append_trace_chat: {exc}")

    # Resolve company_id from campaign if not provided
    if company_id is None:
        campaign = store.get_campaign(campaign_id)
        if campaign is not None:
            company_id = campaign.company_id

    metrics.inc("trace_event_write_total")
    trace = ensure_campaign_trace(campaign_id, actor_id, source)
    message_id = f"msg_{uuid4().hex[:12]}"
    created_at_dt = now_utc()
    created_at = created_at_dt.isoformat()
    record = CampaignTraceChatRecord(
        company_id=company_id or "",
        message_id=message_id,
        trace_id=trace.trace_id,
        campaign_id=campaign_id,
        role=role,
        content_masked=content_masked,
        raw_ref=raw_ref,
        created_at=created_at,
    )

    if persistence is not None:
        try:
            persistence.append_campaign_chat_message(
                message_id=message_id,
                trace_id=trace.trace_id,
                campaign_id=campaign_id,
                role=role,
                content_masked=content_masked,
                raw_ref=raw_ref,
                created_at=created_at_dt,
                company_id=company_id or "",
            )
        except Exception:
            metrics.inc("trace_event_write_fail_total")
            raise
    else:
        campaign_trace_chats.setdefault(campaign_id, []).insert(0, record)
        trace.updated_at = created_at
        campaign_traces[campaign_id] = trace

    return record


def list_trace_events(
    campaign_id: str,
    limit: int,
    cursor_before: tuple[datetime, str] | None,
    event_type: str | None,
    actor_id: str | None,
    keyword: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> list[CampaignTraceEventRecord]:
    if persistence is not None:
        items = persistence.list_campaign_trace_events(
            campaign_id,
            limit,
            cursor_before,
            event_type,
            actor_id,
            keyword,
            from_ts,
            to_ts,
        )
        results: list[CampaignTraceEventRecord] = []
        for payload in items:
            created_at = payload.get("created_at")
            raw_payload = payload.get("payload_json")
            event_payload = raw_payload if isinstance(raw_payload, dict) else {}
            results.append(
                CampaignTraceEventRecord(
                    event_id=str(payload.get("event_id")),
                    trace_id=str(payload.get("trace_id")),
                    campaign_id=str(payload.get("campaign_id")),
                    event_type=str(payload.get("event_type")),
                    actor_id=str(payload.get("actor_id")),
                    actor_role=str(payload.get("actor_role")),
                    summary=str(payload.get("summary")),
                    payload=event_payload,
                    created_at=created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                )
            )
        return results

    items = campaign_trace_events.get(campaign_id, [])
    filtered = items
    if cursor_before is not None:
        cursor_at, cursor_event_id = cursor_before
        filtered = [
            item
            for item in filtered
            if (parse_iso_datetime_or_400(item.created_at, "created_at"), item.event_id) < (cursor_at, cursor_event_id)
        ]
    if event_type:
        filtered = [item for item in filtered if item.event_type == event_type]
    if actor_id:
        filtered = [item for item in filtered if item.actor_id == actor_id]
    if keyword:
        filtered = [item for item in filtered if keyword.lower() in item.summary.lower()]
    if from_ts is not None:
        filtered = [item for item in filtered if parse_iso_datetime_or_400(item.created_at, "created_at") >= from_ts]
    if to_ts is not None:
        filtered = [item for item in filtered if parse_iso_datetime_or_400(item.created_at, "created_at") <= to_ts]
    if from_ts is not None:
        filtered = [item for item in filtered if parse_iso_datetime_or_400(item.created_at, "created_at") >= from_ts]

    filtered = sorted(
        filtered,
        key=lambda item: (parse_iso_datetime_or_400(item.created_at, "created_at"), item.event_id),
        reverse=True,
    )
    return filtered[:limit]


def list_trace_chat(campaign_id: str, limit: int, cursor_before: tuple[datetime, str] | None) -> list[CampaignTraceChatRecord]:
    if persistence is not None:
        items = persistence.list_campaign_trace_chat(campaign_id, limit, cursor_before)
        results: list[CampaignTraceChatRecord] = []
        for payload in items:
            created_at = payload.get("created_at")
            results.append(
                CampaignTraceChatRecord(
                    message_id=str(payload.get("message_id")),
                    trace_id=str(payload.get("trace_id")),
                    campaign_id=str(payload.get("campaign_id")),
                    role=str(payload.get("role")),
                    content_masked=str(payload.get("content_masked")),
                    raw_ref=str(payload.get("raw_ref")) if payload.get("raw_ref") is not None else None,
                    created_at=created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                )
            )
        return results

    items = campaign_trace_chats.get(campaign_id, [])
    filtered = items
    if cursor_before is not None:
        cursor_at, cursor_message_id = cursor_before
        filtered = [
            item
            for item in filtered
            if (parse_iso_datetime_or_400(item.created_at, "created_at"), item.message_id) < (cursor_at, cursor_message_id)
        ]

    filtered = sorted(
        filtered,
        key=lambda item: (parse_iso_datetime_or_400(item.created_at, "created_at"), item.message_id),
        reverse=True,
    )
    return filtered[:limit]


def count_trace_events_filtered(
    campaign_id: str,
    event_type: str | None,
    actor_id: str | None,
    keyword: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> int:
    items = campaign_trace_events.get(campaign_id, [])
    filtered = items
    if event_type:
        filtered = [item for item in filtered if item.event_type == event_type]
    if actor_id:
        filtered = [item for item in filtered if item.actor_id == actor_id]
    if keyword:
        filtered = [item for item in filtered if keyword.lower() in item.summary.lower()]
    if from_ts is not None:
        filtered = [item for item in filtered if parse_iso_datetime_or_400(item.created_at, "created_at") >= from_ts]
    if to_ts is not None:
        filtered = [item for item in filtered if parse_iso_datetime_or_400(item.created_at, "created_at") <= to_ts]
    return len(filtered)


def to_work_order_record(payload: dict[str, Any]) -> WorkOrderRecord:
    created_at = payload.get("created_at")
    updated_at = payload.get("updated_at")
    due_at = payload.get("due_at")
    escalated_at = payload.get("escalated_at")
    due_at_iso = due_at.isoformat() if isinstance(due_at, datetime) else (str(due_at) if due_at is not None else None)
    escalated_at_iso = escalated_at.isoformat() if isinstance(escalated_at, datetime) else (str(escalated_at) if escalated_at is not None else None)
    status = cast(
        Literal["open", "in_progress", "blocked", "review_pending", "approved", "rejected", "done", "cancelled"],
        str(payload.get("status")),
    )
    return WorkOrderRecord(
        company_id=str(payload.get("company_id", "")),
        work_order_id=str(payload.get("work_order_id")),
        campaign_id=str(payload.get("campaign_id")),
        task_id=str(payload.get("task_id")) if payload.get("task_id") is not None else None,
        title=str(payload.get("title")),
        description=str(payload.get("description") or ""),
        assignee=str(payload.get("assignee")) if payload.get("assignee") is not None else None,
        status=status,
        priority=int(payload.get("priority") or 3),
        created_by=str(payload.get("created_by") or "system"),
        due_at=due_at_iso,
        escalated_at=escalated_at_iso,
        escalation_reason=str(payload.get("escalation_reason")) if payload.get("escalation_reason") is not None else None,
        overdue=is_work_order_overdue(status, due_at_iso),
        created_at=created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
        updated_at=updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at),
    )


def to_work_order_message_record(payload: dict[str, Any]) -> WorkOrderMessageRecord:
    created_at = payload.get("created_at")
    return WorkOrderMessageRecord(
        company_id=str(payload.get("company_id", "")),
        message_id=str(payload.get("message_id")),
        work_order_id=str(payload.get("work_order_id")),
        campaign_id=str(payload.get("campaign_id")),
        role=str(payload.get("role")),
        content_masked=str(payload.get("content_masked")),
        actor_id=str(payload.get("actor_id")),
        created_at=created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
    )


def parse_work_order_cursor_or_400(value: str, field_name: str) -> tuple[datetime, str]:
    parts = value.split("|", 1)
    updated_at = parse_iso_datetime_or_400(parts[0], field_name)
    if len(parts) == 2:
        work_order_id = parts[1].strip()
        if not work_order_id:
            raise HTTPException(status_code=400, detail=f"{field_name} must include a cursor id")
        return (updated_at, work_order_id)
    return (updated_at, "wko_~")


def list_campaign_work_orders_data(
    campaign_id: str,
    limit: int,
    cursor_before: tuple[datetime, str] | None,
    status: str | None,
    assignee: str | None,
) -> list[WorkOrderRecord]:
    if persistence is not None:
        rows = persistence.list_campaign_work_orders(campaign_id, limit, cursor_before, status, assignee)
        return [to_work_order_record(row) for row in rows]

    items = campaign_work_orders.get(campaign_id, [])
    filtered = items
    if cursor_before is not None:
        cursor_at, cursor_id = cursor_before
        filtered = [
            item
            for item in filtered
            if (parse_iso_datetime_or_400(item.updated_at, "updated_at"), item.work_order_id) < (cursor_at, cursor_id)
        ]
    if status:
        filtered = [item for item in filtered if item.status == status]
    if assignee:
        filtered = [item for item in filtered if item.assignee == assignee]
    filtered = sorted(
        filtered,
        key=lambda item: (parse_iso_datetime_or_400(item.updated_at, "updated_at"), item.work_order_id),
        reverse=True,
    )
    return filtered[:limit]


def count_campaign_work_orders_data(campaign_id: str, status: str | None, assignee: str | None) -> int:
    if persistence is not None:
        return persistence.count_campaign_work_orders(campaign_id, status, assignee)
    items = campaign_work_orders.get(campaign_id, [])
    filtered = items
    if status:
        filtered = [item for item in filtered if item.status == status]
    if assignee:
        filtered = [item for item in filtered if item.assignee == assignee]
    return len(filtered)


def get_work_order_data(work_order_id: str) -> WorkOrderRecord | None:
    if persistence is not None:
        payload = persistence.get_work_order(work_order_id)
        if payload is None:
            return None
        return to_work_order_record(payload)
    return work_order_by_id.get(work_order_id)


def list_work_order_messages_data(
    work_order_id: str,
    limit: int,
    cursor_before: tuple[datetime, str] | None,
) -> list[WorkOrderMessageRecord]:
    if persistence is not None:
        rows = persistence.list_work_order_messages(work_order_id, limit, cursor_before)
        return [to_work_order_message_record(row) for row in rows]

    items = work_order_messages.get(work_order_id, [])
    filtered = items
    if cursor_before is not None:
        cursor_at, cursor_id = cursor_before
        filtered = [
            item
            for item in filtered
            if (parse_iso_datetime_or_400(item.created_at, "created_at"), item.message_id) < (cursor_at, cursor_id)
        ]
    filtered = sorted(
        filtered,
        key=lambda item: (parse_iso_datetime_or_400(item.created_at, "created_at"), item.message_id),
        reverse=True,
    )
    return filtered[:limit]


def count_work_order_messages_data(work_order_id: str) -> int:
    if persistence is not None:
        return persistence.count_work_order_messages(work_order_id)
    return len(work_order_messages.get(work_order_id, []))


def mask_work_order_text(value: str) -> str:
    condensed = value.replace("\n", " ").strip()
    redacted_email = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", condensed, flags=re.IGNORECASE)
    redacted_token = re.sub(r"[A-Za-z0-9_-]{24,}", "[redacted-token]", redacted_email)
    if len(redacted_token) <= 500:
        return redacted_token
    return f"{redacted_token[:500]}…"


def generate_work_order_assistant_reply(work_order: WorkOrderRecord, user_prompt: str) -> str:
    prompt = user_prompt.strip()
    return (
        f"Work order draft for {work_order.work_order_id}: "
        f"focus on '{work_order.title}'. "
        f"Proposed content: {prompt[:220]}"
    )


WORK_ORDER_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "review_pending", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "review_pending": {"approved", "rejected", "cancelled"},
    "approved": {"done", "cancelled"},
    "rejected": {"in_progress", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


def can_transition_work_order_status(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in WORK_ORDER_ALLOWED_TRANSITIONS.get(current, set())


def enforce_work_order_sla(work_order: WorkOrderRecord) -> WorkOrderRecord:
    if not work_order.due_at:
        return work_order
    if work_order.escalated_at:
        return work_order
    if work_order.status in {"done", "cancelled"}:
        return work_order
    due_at_dt = parse_iso_datetime_or_400(work_order.due_at, "due_at")
    now_dt = now_utc()
    if due_at_dt >= now_dt:
        return work_order

    escalated_iso = now_dt.isoformat()
    updated_record = work_order.model_copy(
        update={
            "escalated_at": escalated_iso,
            "escalation_reason": "sla_overdue",
            "overdue": True,
            "updated_at": escalated_iso,
        }
    )

    if persistence is not None:
        persistence.update_work_order_escalation(
            work_order_id=work_order.work_order_id,
            escalated_at=now_dt,
            escalation_reason="sla_overdue",
            updated_at=now_dt,
        )
        refreshed = get_work_order_data(work_order.work_order_id)
        if refreshed is not None:
            updated_record = refreshed
    else:
        work_order_by_id[work_order.work_order_id] = updated_record
        rows = campaign_work_orders.get(work_order.campaign_id, [])
        for idx, item in enumerate(rows):
            if item.work_order_id == work_order.work_order_id:
                rows[idx] = updated_record
                break

    append_trace_event(
        campaign_id=updated_record.campaign_id,
        event_type="work_order_sla_breached",
        actor_id="system",
        actor_role="system",
        summary=f"Work order {updated_record.work_order_id} SLA breached",
        payload={"work_order_id": updated_record.work_order_id, "due_at": updated_record.due_at},
        source="work_order",
    )
    append_trace_event(
        campaign_id=updated_record.campaign_id,
        event_type="work_order_escalated",
        actor_id="system",
        actor_role="system",
        summary=f"Work order {updated_record.work_order_id} escalated",
        payload={
            "work_order_id": updated_record.work_order_id,
            "reason": "sla_overdue",
            "escalated_at": updated_record.escalated_at,
        },
        source="work_order",
    )
    metrics.inc("work_order_sla_breach_total")
    metrics.inc("work_order_escalated_total")
    notify_escalation(updated_record)
    return updated_record


def notify_escalation(work_order: WorkOrderRecord) -> None:
    if not WEBHOOK_NOTIFY_URL:
        return
    payload = {
        "event": "work_order_escalated",
        "work_order_id": work_order.work_order_id,
        "campaign_id": work_order.campaign_id,
        "title": work_order.title,
        "due_at": work_order.due_at,
        "escalated_at": work_order.escalated_at,
        "reason": work_order.escalation_reason,
    }
    req = request.Request(
        WEBHOOK_NOTIFY_URL,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass  # fire-and-forget


def scan_and_enforce_work_order_sla(limit: int, operator: str | None = None) -> SlaScanResponse:
    max_limit = max(1, min(limit, 5000))
    scanned = 0
    escalated = 0

    if persistence is not None:
        rows = persistence.list_overdue_unescalated_work_orders(max_limit)
        scanned = len(rows)
        for row in rows:
            before = to_work_order_record(row)
            after = enforce_work_order_sla(before)
            if before.escalated_at is None and after.escalated_at is not None:
                escalated += 1
        overdue_pending = persistence.count_overdue_unescalated_work_orders()
    else:
        items = [
            item
            for rows in campaign_work_orders.values()
            for item in rows
            if item.escalated_at is None and is_work_order_overdue(item.status, item.due_at)
        ]
        scanned = min(len(items), max_limit)
        for item in items[:max_limit]:
            after = enforce_work_order_sla(item)
            if item.escalated_at is None and after.escalated_at is not None:
                escalated += 1
        overdue_pending = sum(
            1
            for rows in campaign_work_orders.values()
            for item in rows
            if item.escalated_at is None and is_work_order_overdue(item.status, item.due_at)
        )

    metrics.inc("work_order_sla_scan_total")
    append_trace_event(
        campaign_id="system",
        event_type="work_order_sla_scan_completed",
        actor_id=operator or "system",
        actor_role="admin",
        summary="SLA scan completed",
        payload={"scanned": scanned, "escalated": escalated, "overdue_pending": overdue_pending},
        source="system",
    )
    return SlaScanResponse(scanned=scanned, escalated=escalated, overdue_pending=overdue_pending)


def list_sla_backlog_data(limit: int, overdue_only: bool) -> tuple[list[SlaBacklogEntry], int]:
    if persistence is not None:
        rows = persistence.list_overdue_unescalated_work_orders(limit)
        items = [to_work_order_record(row) for row in rows]
        overdue_pending = persistence.count_overdue_unescalated_work_orders()
    else:
        items = [
            item
            for rows in campaign_work_orders.values()
            for item in rows
            if item.escalated_at is None and is_work_order_overdue(item.status, item.due_at)
        ]
        overdue_pending = sum(
            1
            for rows in campaign_work_orders.values()
            for item in rows
            if item.escalated_at is None and is_work_order_overdue(item.status, item.due_at)
        )
    if overdue_only:
        items = [item for item in items if item.overdue]
    result = [
        SlaBacklogEntry(
            work_order_id=item.work_order_id,
            campaign_id=item.campaign_id,
            title=item.title,
            status=item.status,
            priority=item.priority,
            due_at=item.due_at,
            overdue=item.overdue,
            escalated_at=item.escalated_at,
            escalation_reason=item.escalation_reason,
            assignee=item.assignee,
            created_by=item.created_by,
        )
        for item in items[:limit]
    ]
    return result, overdue_pending


def get_redis_stats() -> RedisStats:
    try:
        import redis as redis_lib
        r = redis_lib.from_url(REDIS_URL)
        info = r.info()
        return RedisStats(
            redis_version=info.get("redis_version"),
            connected_clients=info.get("connected_clients"),
            used_memory_human=info.get("used_memory_human"),
            uptime_days=info.get("uptime_days"),
            total_connections_received=info.get("total_connections_received"),
            instantaneous_ops_modules=info.get("instantaneous_ops_modules"),
            role=info.get("role"),
        )
    except Exception:
        return RedisStats()


def _get_redis_client() -> Any:
    try:
        import redis as redis_lib
        return redis_lib.from_url(REDIS_URL)
    except Exception:
        return None


def _write_llm_usage_to_redis(payload: dict[str, Any]) -> None:
    """Write a usage record to the Redis buffer list (fire-and-forget)."""
    client = _get_redis_client()
    if client is None:
        return
    try:
        import json
        client.rpush(LLM_USAGE_BUFFER_KEY, json.dumps(payload))
    except Exception:
        pass  # fire-and-forget


def _flush_llm_usage_buffer() -> None:
    """Pop all buffered records from Redis and bulk-insert to PostgreSQL."""
    import json as _json

    if persistence is None:
        return
    client = _get_redis_client()
    if client is None:
        return
    try:
        # Atomically pop all items - do NOT delete until insert succeeds
        items_raw = client.lrange(LLM_USAGE_BUFFER_KEY, 0, -1)
        if not items_raw:
            return
        rows = []
        for raw in items_raw:
            try:
                rows.append(_json.loads(raw))
            except Exception as exc:
                logger.warning(f"Failed to parse LLM usage record: {exc}")
                continue
        if not rows:
            client.delete(LLM_USAGE_BUFFER_KEY)
            return
        try:
            persistence.flush_llm_usage_batch(rows)
            client.delete(LLM_USAGE_BUFFER_KEY)
        except Exception as exc:
            logger.error(f"Failed to flush LLM usage batch to DB: {exc}")
            raise  # Re-raise so the data stays in Redis for retry
    except Exception as exc:
        logger.warning(f"LLM usage buffer flush failed: {exc}")
        # Data remains in Redis for next retry


def _compute_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    pricing: dict[str, Any],
) -> float:
    prompt_price = float(pricing.get("prompt_price_per_m", 0))
    completion_price = float(pricing.get("completion_price_per_m", 0))
    cost = (prompt_tokens / 1_000_000) * prompt_price
    cost += (completion_tokens / 1_000_000) * completion_price
    return round(cost, 6)


def _enrich_usage_with_cost(
    row: dict[str, Any],
    pricing_map: dict[str, dict[str, Any]],
) -> LlmUsageRecord:
    model = str(row.get("model", ""))
    pricing = pricing_map.get(model, {"prompt_price_per_m": 0, "completion_price_per_m": 0})
    cost = _compute_cost_usd(
        int(row.get("prompt_tokens", 0)),
        int(row.get("completion_tokens", 0)),
        pricing,
    )
    created_at = row.get("created_at")
    created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
    return LlmUsageRecord(
        usage_id=str(row.get("usage_id", "")),
        company_id=str(row.get("company_id", "")),
        model=model,
        provider=str(row.get("provider", "")),
        prompt_tokens=int(row.get("prompt_tokens", 0)),
        completion_tokens=int(row.get("completion_tokens", 0)),
        request_count=int(row.get("request_count", 1)),
        cost_usd=cost,
        created_at=created_at_str,
    )


def build_trace_health_snapshot() -> SystemTraceHealthResponse:
    if persistence is not None:
        payload = persistence.summarize_trace_health()
        latest_event_at = payload.get("latest_event_at")
        latest_chat_at = payload.get("latest_chat_at")
        return SystemTraceHealthResponse(
            retention_days=max(1, TRACE_RETENTION_DAYS),
            cleanup_interval_hours=max(1, TRACE_CLEANUP_INTERVAL_HOURS),
            last_cleanup_at=last_trace_cleanup_at.isoformat() if last_trace_cleanup_at is not None else None,
            trace_total=int(payload.get("trace_total", 0)),
            event_total=int(payload.get("event_total", 0)),
            chat_total=int(payload.get("chat_total", 0)),
            work_order_total=int(payload.get("work_order_total", 0)),
            work_order_message_total=int(payload.get("work_order_message_total", 0)),
            work_order_overdue_total=int(payload.get("work_order_overdue_total", 0)),
            work_order_escalated_total=int(payload.get("work_order_escalated_total", 0)),
            latest_event_at=latest_event_at.isoformat() if isinstance(latest_event_at, datetime) else None,
            latest_chat_at=latest_chat_at.isoformat() if isinstance(latest_chat_at, datetime) else None,
            top_event_types=[
                TraceEventTypeCount(event_type=str(item.get("event_type", "unknown")), total=int(item.get("total", 0)))
                for item in cast(list[dict[str, Any]], payload.get("top_event_types", []))
            ],
        )

    top_events_counter: Counter[str] = Counter()
    latest_event_at: str | None = None
    latest_chat_at: str | None = None

    for items in campaign_trace_events.values():
        for item in items:
            top_events_counter[item.event_type] += 1
            if latest_event_at is None or item.created_at > latest_event_at:
                latest_event_at = item.created_at

    for items in campaign_trace_chats.values():
        for item in items:
            if latest_chat_at is None or item.created_at > latest_chat_at:
                latest_chat_at = item.created_at

    top_event_types = [
        TraceEventTypeCount(event_type=event_type, total=total)
        for event_type, total in top_events_counter.most_common(10)
    ]

    return SystemTraceHealthResponse(
        retention_days=max(1, TRACE_RETENTION_DAYS),
        cleanup_interval_hours=max(1, TRACE_CLEANUP_INTERVAL_HOURS),
        last_cleanup_at=last_trace_cleanup_at.isoformat() if last_trace_cleanup_at is not None else None,
        trace_total=len(campaign_traces),
        event_total=sum(len(items) for items in campaign_trace_events.values()),
        chat_total=sum(len(items) for items in campaign_trace_chats.values()),
        work_order_total=sum(len(items) for items in campaign_work_orders.values()),
        work_order_message_total=sum(len(items) for items in work_order_messages.values()),
        work_order_overdue_total=sum(1 for items in campaign_work_orders.values() for item in items if is_work_order_overdue(item.status, item.due_at)),
        work_order_escalated_total=sum(1 for items in campaign_work_orders.values() for item in items if item.escalated_at is not None),
        latest_event_at=latest_event_at,
        latest_chat_at=latest_chat_at,
        top_event_types=top_event_types,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics() -> Response:
    running = len([item for item in store.list_campaigns() if item.status == "running"])
    body = metrics.render(running_campaigns=running)
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.post(
    "/api/v1/campaigns",
    response_model=CampaignCreatedResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def create_campaign(req: Request, brief: CampaignBrief) -> CampaignCreatedResponse:
    if is_internal_api_key_request(req):
        actor_company_id = (req.headers.get("x-company-id") or os.getenv("CHATBOT_DEFAULT_COMPANY_ID") or "chatbot_company").strip()
        actor_id = (req.headers.get("x-actor-id") or "chatbot").strip()
        actor_role = "system"
    else:
        payload = require_jwt(req)
        check_permission(payload, "campaign.create")
        actor_company_id = payload.company_id or ""
        actor_id = payload.sub
        actor_role = "member"
    brief = normalize_visual_only_deliverables(brief)
    campaign = store.create_campaign(actor_company_id, brief)
    metrics.inc("campaign_created_total")

    append_trace_event(
        campaign_id=campaign.campaign_id,
        event_type="campaign_created",
        actor_id=actor_id,
        actor_role=actor_role,
        summary="Campaign created",
        payload={"campaign_name": campaign.brief.campaign_name, "budget": campaign.brief.budget},
        source="manual",
        company_id=actor_company_id,
    )

    return CampaignCreatedResponse(campaign_id=campaign.campaign_id, company_id=campaign.company_id, status=campaign.status)


@app.get(
    "/api/v1/campaigns/{campaign_id}",
    response_model=CampaignRecord,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_campaign(req: Request, campaign_id: str) -> CampaignRecord:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Platform admin bypass
    if is_platform_admin_request(req):
        return normalize_campaign_status(campaign)

    # Verify company_id matches
    payload = require_jwt(req)
    actor_company_id = payload.company_id or ""
    if campaign.company_id != actor_company_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this campaign")
    return normalize_campaign_status(campaign)


@app.patch(
    "/api/v1/campaigns/{campaign_id}",
    response_model=CampaignRecord,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def update_campaign(req: Request, campaign_id: str, brief: CampaignBrief) -> CampaignRecord:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this campaign")
        actor_id = payload.sub
    else:
        actor_id = "platform-admin"

    brief = normalize_visual_only_deliverables(brief)
    updated = store.update_campaign_brief(campaign_id, brief)
    if updated is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    append_trace_event(
        campaign_id=campaign_id,
        event_type="campaign_updated",
        actor_id=actor_id,
        actor_role="member",
        summary="Campaign brief updated",
        payload={"campaign_name": brief.campaign_name, "budget": brief.budget},
        source="manual",
        company_id=campaign.company_id,
    )
    return updated


@app.patch(
    "/api/v1/campaigns/{campaign_id}/references/{reference_id}",
    response_model=CampaignReferenceRecord,
    responses={404: {"model": ErrorResponse}},
)
def update_campaign_reference(
    campaign_id: str,
    reference_id: str,
    payload: CampaignReferenceUpdateRequest,
    req: Request,
) -> CampaignReferenceRecord:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign)

    folder = (payload.folder or "General").strip() or "General"
    existing = get_reference_payload_or_404(campaign_id, reference_id)
    if persistence is not None:
        if not persistence.update_campaign_reference_folder(campaign_id, reference_id, folder):
            raise HTTPException(status_code=404, detail="Campaign reference not found")
        updated = persistence.get_campaign_reference(campaign_id, reference_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Campaign reference not found")
    else:
        updated = dict(existing)
        updated["folder"] = folder
        for item in campaign_references.get(campaign_id, []):
            if item.reference_id == reference_id:
                item.folder = folder
                break

    append_trace_event(
        campaign_id=campaign_id,
        event_type="reference_moved",
        actor_id="system",
        actor_role="system",
        summary=f"Reference {reference_id} moved to {folder}",
        payload={"reference_id": reference_id, "folder": folder},
        source="manual",
    )
    return to_reference_record(str(req.base_url).rstrip("/"), updated)


@app.delete(
    "/api/v1/campaigns/{campaign_id}",
    response_model=CampaignDeleteResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_campaign(req: Request, campaign_id: str) -> CampaignDeleteResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this campaign")
        actor_id = payload.sub
    else:
        actor_id = "platform-admin"

    append_trace_event(
        campaign_id=campaign_id,
        event_type="campaign_deleted",
        actor_id=actor_id,
        actor_role="member",
        summary="Campaign soft deleted",
        payload={"campaign_name": campaign.brief.campaign_name},
        source="manual",
        company_id=campaign.company_id,
    )

    deleted = store.delete_campaign(campaign_id)
    return CampaignDeleteResponse(campaign_id=campaign_id, deleted=deleted)


@app.get("/api/v1/campaigns", response_model=CampaignListResponse)
def list_campaigns(req: Request, company_id: str | None = None) -> CampaignListResponse:
    # Internal call: use explicit company_id param
    if is_platform_admin_request(req) or is_internal_api_key_request(req):
        # Platform admin can query all or a specific company
        items = store.list_campaigns(company_id=company_id)
    else:
        # Normal user: JWT required, filter by their company
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        items = store.list_campaigns(company_id=actor_company_id)
    normalized_items = [normalize_campaign_status(item) for item in items]
    return CampaignListResponse(items=normalized_items, total=len(normalized_items))


@app.post(
    "/api/v1/campaigns/{campaign_id}/run",
    response_model=CampaignRunResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def run_campaign(req: Request, campaign_id: str) -> CampaignRunResponse:
    # Verify campaign exists and belongs to user's company
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Platform admin/internal bypass
    if is_internal_api_key_request(req):
        actor_id = (req.headers.get("x-actor-id") or "chatbot").strip()
        actor_role = "system"
    elif not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized to run this campaign")
        actor_id = payload.sub
        actor_role = "member"
    else:
        actor_id = "platform-admin"
        actor_role = "member"

    normalized_brief = normalize_visual_only_deliverables(campaign.brief)
    if normalized_brief != campaign.brief:
        campaign = store.update_campaign_brief(campaign_id, normalized_brief) or campaign

    run_id, run_number = create_campaign_run_record(campaign, actor_id)
    finalize_campaign_workflow(
        campaign_id,
        run_id=run_id,
        run_number=run_number,
        tasks=[],
        operator=actor_id,
        reason="campaign_run_started",
    )
    metrics.inc("campaign_run_total")

    append_trace_event(
        campaign_id=campaign_id,
        event_type="campaign_run_requested",
        actor_id=actor_id,
        actor_role=actor_role,
        summary="Campaign run requested",
        payload={"status": campaign.status, "run_id": run_id, "run_number": run_number},
        source="manual",
        company_id=campaign.company_id,
    )

    try:
        plan = post_json(
            f"{DECISION_SERVICE_URL}/internal/decision/plan",
            {
                "campaign_id": campaign_id,
                "brief": campaign.brief.model_dump(mode="json"),
            },
        )
        # Enrich tasks with company_id and run_id before dispatching to orchestrator
        plan_tasks = plan.get("tasks", [])
        for t in plan_tasks:
            if isinstance(t, dict):
                t["company_id"] = campaign.company_id
                t["run_id"] = run_id
                t["worker_payload"] = build_worker_payload_for_task(campaign, t)
        dispatch = post_json(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/dispatch",
            {
                "campaign_id": campaign_id,
                "tasks": plan_tasks,
            },
        )
        tasks_payload = dispatch.get("tasks", [])
        normalized_tasks = [
            normalize_task_payload(task, campaign_id)
            for task in tasks_payload
            if isinstance(task, dict)
        ]
        normalized_tasks = apply_deliverable_task_gates(normalized_tasks, campaign.brief)
        store.set_tasks(campaign_id, normalized_tasks)
        tasks = normalized_tasks
    except RuntimeError:
        metrics.inc("decision_failover_total")
        tasks = store.create_task_plan(campaign.company_id, campaign_id)
        tasks = [task.model_copy(update={"status": "passed"}) for task in tasks]
        tasks = apply_deliverable_task_gates(tasks, campaign.brief)
        store.set_tasks(campaign_id, tasks)

    finalized_campaign = finalize_campaign_workflow(
        campaign_id,
        run_id=run_id,
        run_number=run_number,
        tasks=tasks,
        operator=actor_id,
        reason="campaign_run_dispatched",
        notify_completed=True,
    )
    campaign_failed = finalized_campaign.status == "failed" if finalized_campaign is not None else any(task.status == "failed" for task in tasks)
    campaign_completed = finalized_campaign.status == "completed" if finalized_campaign is not None else len(tasks) > 0 and all(task.status == "passed" for task in tasks)

    append_trace_event(
        campaign_id=campaign_id,
        event_type="campaign_run_dispatched",
        actor_id=actor_id,
        actor_role="member",
        summary="Campaign run dispatch completed",
        payload={"task_count": len(tasks), "failed": campaign_failed, "completed": campaign_completed, "run_id": run_id, "run_number": run_number},
        source="manual",
        company_id=campaign.company_id,
    )

    updated_campaign = store.get_campaign(campaign_id)
    response_status = updated_campaign.status if updated_campaign is not None else campaign.status

    return CampaignRunResponse(
        campaign_id=campaign_id,
        status=response_status,
        message="Workflow accepted and dispatched to orchestrator event loop.",
        run_id=run_id,
        run_number=run_number,
    )


@app.get(
    "/api/v1/campaigns/{campaign_id}/tasks",
    response_model=TaskListResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_campaign_tasks(req: Request, campaign_id: str) -> TaskListResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Platform admin/internal bypass
    if not is_platform_admin_request(req) and not is_internal_api_key_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this campaign")

    try:
        tasks = sync_tasks_from_orchestrator(campaign_id)
    except RuntimeError:
        tasks = store.get_tasks(campaign_id)

    latest_run_id = latest_campaign_run_id(campaign_id)
    tasks = mark_tasks_from_existing_assets(campaign_id, tasks, latest_run_id)

    finalize_campaign_workflow(
        campaign_id,
        run_id=latest_run_id,
        tasks=tasks,
        operator="task-sync",
        reason="campaign_tasks_synced",
    )

    return TaskListResponse(campaign_id=campaign_id, tasks=tasks)


@app.get(
    "/api/v1/campaigns/{campaign_id}/validation-results",
    response_model=ValidationResultListResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_validation_results(req: Request, campaign_id: str) -> ValidationResultListResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized")

    items = list_validation(campaign_id)
    return ValidationResultListResponse(campaign_id=campaign_id, items=items, total=len(items))


@app.get(
    "/api/v1/campaigns/{campaign_id}/runs",
    response_model=CampaignRunListResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def list_campaign_runs(req: Request, campaign_id: str) -> CampaignRunListResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized")

    if persistence is not None:
        try:
            rows = persistence.list_campaign_runs(campaign_id)
            runs = [
                CampaignRunSummary(
                    run_id=str(r["run_id"]),
                    campaign_id=str(r["campaign_id"]),
                    run_number=int(r["run_number"]),
                    status=str(r["status"]),
                    started_at=r["started_at"],
                    completed_at=r.get("completed_at"),
                    triggered_by=str(r["triggered_by"]),
                    metadata_json=r.get("metadata", {}),
                )
                for r in rows
            ]
            return CampaignRunListResponse(campaign_id=campaign_id, runs=runs, total=len(runs))
        except Exception:
            metrics.inc("db_write_fail_total")

    return CampaignRunListResponse(campaign_id=campaign_id, runs=[], total=0)


@app.get(
    "/api/v1/assets/{asset_id}/versions",
    response_model=AssetVersionListResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def list_asset_versions(req: Request, asset_id: str) -> AssetVersionListResponse:
    asset = get_asset_output_by_id(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    campaign = store.get_campaign(asset.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign)

    if persistence is not None:
        try:
            rows = persistence.list_asset_versions(asset_id)
            versions = []
            for r in rows:
                metadata = dict(r.get("metadata", {}) or {})
                metadata.setdefault("asset_type", asset.asset_type)
                if asset.asset_type == "copy":
                    copy_text = extract_copy_text_from_asset(asset)
                    if copy_text:
                        metadata.setdefault("text", copy_text)
                versions.append(
                    AssetVersion(
                        version_id=str(r["version_id"]),
                        asset_id=str(r["asset_id"]),
                        run_id=str(r["run_id"]),
                        version_number=int(r["version_number"]),
                        url=str(r["url"]),
                        metadata_json=metadata,
                        created_at=r["created_at"],
                    )
                )
            if not versions:
                metadata = dict(asset.metadata or {})
                metadata.setdefault("asset_type", asset.asset_type)
                if asset.asset_type == "copy":
                    copy_text = extract_copy_text_from_asset(asset)
                    if copy_text:
                        metadata.setdefault("text", copy_text)
                versions = [
                    AssetVersion(
                        version_id=f"ver_{asset.asset_id}_current",
                        asset_id=asset.asset_id,
                        run_id=asset.run_id or "current",
                        version_number=1,
                        url=asset.url,
                        metadata_json=metadata,
                        created_at=asset.created_at,
                    )
                ]
            return AssetVersionListResponse(asset_id=asset_id, versions=versions, total=len(versions))
        except Exception:
            metrics.inc("db_write_fail_total")

    metadata = dict(asset.metadata or {})
    metadata.setdefault("asset_type", asset.asset_type)
    if asset.asset_type == "copy":
        copy_text = extract_copy_text_from_asset(asset)
        if copy_text:
            metadata.setdefault("text", copy_text)
    versions = [
        AssetVersion(
            version_id=f"ver_{asset.asset_id}_current",
            asset_id=asset.asset_id,
            run_id=asset.run_id or "current",
            version_number=1,
            url=asset.url,
            metadata_json=metadata,
            created_at=asset.created_at,
        )
    ]
    return AssetVersionListResponse(asset_id=asset_id, versions=versions, total=len(versions))


@app.post(
    "/api/v1/assets/{asset_id}/regenerate",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
def regenerate_asset(
    background_tasks: BackgroundTasks,
    req: Request,
    asset_id: str,
    payload: AssetRegenerateRequest | None = None,
) -> dict[str, str]:
    if persistence is not None:
        asset = persistence.get_asset_output(asset_id)
        if asset is not None:
            campaign = store.get_campaign(asset.campaign_id)
            if campaign is not None:
                require_campaign_access(req, campaign)
                _ensure_latest_asset_version(asset)
    background_tasks.add_task(_run_asset_regeneration_background, req, asset_id, payload)
    return {"status": "queued", "asset_id": asset_id, "asset_name": ""}


def _run_asset_regeneration_background(req: Request, asset_id: str, payload: AssetRegenerateRequest | None = None) -> None:
    try:
        _perform_asset_regeneration(req, asset_id, payload)
    except Exception:
        logger.exception("Background asset regeneration failed for %s", asset_id)


def _ensure_latest_asset_version(asset: AssetOutput) -> None:
    source_metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
    try:
        source_version = int(source_metadata.get("asset_version") or 1)
    except (TypeError, ValueError):
        source_version = 1
    source_base = str(source_metadata.get("asset_base_name") or "")
    source_root = str(source_metadata.get("root_asset_id") or source_metadata.get("parent_asset_id") or asset.asset_id)
    latest_version = source_version
    for candidate in persistence.list_asset_outputs(asset.campaign_id):
        candidate_metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
        candidate_base = str(candidate_metadata.get("asset_base_name") or "")
        candidate_root = str(candidate_metadata.get("root_asset_id") or candidate_metadata.get("parent_asset_id") or candidate.asset_id)
        if candidate_base == source_base and candidate_root == source_root:
            try:
                latest_version = max(latest_version, int(candidate_metadata.get("asset_version") or 1))
            except (TypeError, ValueError):
                continue
    if source_version < latest_version:
        raise HTTPException(status_code=409, detail="Only the latest asset version can be regenerated")


def _perform_asset_regeneration(req: Request, asset_id: str, payload: AssetRegenerateRequest | None = None) -> dict[str, str]:
    actor_payload: JWTPayload | None = None
    if not is_platform_admin_request(req) and not is_internal_api_key_request(req):
        actor_payload = require_jwt(req)

    if persistence is not None:
        asset = persistence.get_asset_output(asset_id)
        if asset is None:
            review_item = persistence.get_review_item_by_asset(asset_id)
            if review_item is not None:
                asset_type = str(review_item.get("asset_type") or "")
                task_type_by_asset_type = {
                    "copy": "copywriting",
                    "image": "image_generation",
                    "video": "video_generation",
                    "ads": "ads_strategy",
                }
                expected_task_type = task_type_by_asset_type.get(asset_type)
                task_id = None
                if expected_task_type:
                    for task in persistence.get_tasks(str(review_item["campaign_id"])):
                        if task.task_type == expected_task_type:
                            task_id = task.task_id
                            break
                if task_id:
                    asset = AssetOutput(
                        asset_id=asset_id,
                        company_id="",
                        campaign_id=str(review_item["campaign_id"]),
                        task_id=task_id,
                        asset_type=asset_type,
                        url="",
                        metadata={"source": "review_item_fallback"},
                        validation_status=str(review_item.get("status") or "review_pending"),
                        created_at=review_item["submitted_at"],
                        run_id=review_item.get("run_id"),
                    )
    else:
        asset = None

    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")

    worker_url = WORKER_TYPE_TO_URL.get(asset.asset_type)
    if not worker_url:
        raise HTTPException(status_code=400, detail=f"Unknown asset type: {asset.asset_type}")

    campaign = store.get_campaign(asset.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"Campaign not found for asset: {asset.campaign_id}")
    require_campaign_access(req, campaign)

    if persistence is not None:
        _ensure_latest_asset_version(asset)

    review_item = persistence.get_review_item_by_asset(asset_id) if persistence is not None else None
    existing_reason = str(review_item.get("reason") or "") if review_item is not None else ""
    reject_reason = (payload.reject_reason if payload else None) or existing_reason or "Regenerate requested from review preview"
    user_instruction = (payload.user_instruction if payload else None) or ""
    operator = (payload.operator if payload else None) or (actor_payload.sub if actor_payload is not None else "admin")
    regeneration_context = prepare_regeneration_naming(campaign, asset)
    if persistence is not None:
        try:
            source_metadata = dict(asset.metadata if isinstance(asset.metadata, dict) else {})
            source_metadata.setdefault("root_asset_id", regeneration_context.get("root_asset_id") or asset.asset_id)
            source_metadata.setdefault("asset_base_name", regeneration_context.get("asset_base_name"))
            source_metadata.setdefault("asset_name", asset_metadata_name(source_metadata) or strip_asset_version_suffix(str(regeneration_context.get("asset_name") or "")) or str(regeneration_context.get("asset_base_name") or ""))
            source_metadata.setdefault("display_name", source_metadata.get("asset_name"))
            persistence.save_asset_outputs([
                AssetOutput(
                    company_id=asset.company_id,
                    asset_id=asset.asset_id,
                    campaign_id=asset.campaign_id,
                    task_id=asset.task_id,
                    asset_type=asset.asset_type,
                    url=asset.url,
                    metadata=source_metadata,
                    validation_status=asset.validation_status,
                    created_at=asset.created_at,
                    run_id=asset.run_id,
                )
            ])
        except Exception:
            metrics.inc("db_write_fail_total")
    instruction_block = ""
    if user_instruction.strip():
        instruction_block = f"\n\nUser regeneration work order instructions:\n{user_instruction.strip()}"
    company_id = asset.company_id or campaign.company_id
    if asset.asset_type == "copy":
        base_prompt = build_copy_generation_prompt(campaign) + instruction_block
        revision_payload = {
            "task_id": asset.task_id,
            "campaign_id": asset.campaign_id,
            "company_id": company_id,
            "prompt": base_prompt,
            "reject_reason": reject_reason,
            "brand_context": {
                "campaign_name": campaign.brief.campaign_name,
                "product_name": campaign.brief.product_name,
                "industry_category": getattr(campaign.brief, "industry_category", ""),
                "project_description": getattr(campaign.brief, "project_description", "") or getattr(campaign.brief, "description", ""),
                "objective": campaign.brief.objective,
                "platforms": campaign.brief.platforms,
                "brand_tone": campaign.brief.brand_tone,
                "target_audience": campaign.brief.target_audience.model_dump(mode="json"),
            },
            "variants": 1,
        }
    elif asset.asset_type == "image":
        base_prompt = build_image_generation_prompt(campaign) + instruction_block
        revision_payload = {
            "task_id": asset.task_id,
            "campaign_id": asset.campaign_id,
            "prompt": base_prompt,
            "reject_reason": reject_reason,
            "sizes": ["1024x1024"],
            "style_profile": {"tone": campaign.brief.brand_tone},
        }
    elif asset.asset_type == "video":
        base_prompt = build_video_generation_prompt(campaign) + instruction_block
        revision_payload = {
            "task_id": asset.task_id,
            "campaign_id": asset.campaign_id,
            "company_id": company_id,
            "prompt": base_prompt,
            "reject_reason": reject_reason,
            "duration": 6,
            "aspect_ratio": "9:16",
        }
    elif asset.asset_type == "ads":
        revision_payload = {
            "task_id": asset.task_id,
            "campaign_id": asset.campaign_id,
            "company_id": company_id,
            "objective": campaign.brief.objective,
            "budget": float(campaign.brief.budget),
            "platforms": campaign.brief.platforms,
            "reject_reason": reject_reason,
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown asset type: {asset.asset_type}")

    try:
        worker_response = post_json(f"{worker_url}/internal/workers/{asset.asset_type}/regenerate", revision_payload)
        # Save the regenerated asset directly
        task_type_map = {
            "copy": "copywriting",
            "image": "image_generation",
            "video": "video_generation",
            "ads": "ads_strategy",
        }
        run_id = asset.run_id or latest_campaign_run_id(asset.campaign_id) or ""
        worker_result = {
            **worker_response,
            "campaign_id": asset.campaign_id,
            "company_id": company_id,
            "run_id": run_id,
            "regeneration_context": regeneration_context,
        }
        result_payload = WorkerResultRequest(
            task_type=task_type_map.get(asset.asset_type, asset.asset_type),
            result=worker_result,
        )
        # Reuse the same save logic
        save_result: dict[str, str] = {"asset_ids": ""}
        if asset.asset_type == "copy":
            save_result = _save_copy_worker_result(worker_result, now_utc())
        elif asset.asset_type == "image":
            save_result = _save_image_worker_result(worker_result, now_utc())
        elif asset.asset_type == "video":
            save_result = _save_video_worker_result(worker_result, now_utc())
        elif asset.asset_type == "ads":
            save_result = _save_ads_worker_result(worker_result, now_utc())
        regenerated_asset_id = (save_result.get("asset_ids") or "").split(",", 1)[0] or asset_id
        finalize_campaign_workflow(
            asset.campaign_id,
            run_id=run_id,
            tasks=store.get_tasks(asset.campaign_id),
            operator=operator,
            reason="asset_regenerated",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Regenerate dispatch failed: {exc}") from exc

    append_trace_event(
        campaign_id=asset.campaign_id,
        event_type="asset_regenerate_requested",
        actor_id=operator,
        actor_role="admin",
        summary=f"Regenerate requested for asset {asset_id}",
        payload={"asset_id": asset_id, "asset_type": asset.asset_type, "task_id": asset.task_id, "reject_reason": reject_reason, "user_instruction": user_instruction, "regenerated_asset_name": regeneration_context.get("asset_name")},
        source="review",
    )
    return {"status": "ok", "asset_id": regenerated_asset_id, "asset_name": str(regeneration_context.get("asset_name") or "")}


@app.get(
    "/api/v1/campaigns/{campaign_id}/bundle",
    response_model=FinalAssetBundle,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_bundle(req: Request, campaign_id: str) -> FinalAssetBundle:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized")

    metrics.inc("bundle_requested_total")
    assets = list_assets(campaign_id)
    validations = {item.asset_id: item for item in list_validation(campaign_id)}
    current_tasks = {task.task_id: task.task_type for task in store.get_tasks(campaign_id)}
    latest_run_id = latest_campaign_run_id(campaign_id)
    deliverables = campaign.brief.deliverables
    allowed_generated_asset_types: set[str] = set()
    if deliverables.copy_variants > 0:
        allowed_generated_asset_types.add("copy")
    if deliverables.image_assets > 0:
        allowed_generated_asset_types.add("image")
    if deliverables.short_video_assets > 0:
        allowed_generated_asset_types.add("video")
    if deliverables.ads_strategy > 0:
        allowed_generated_asset_types.add("ads")
    task_type_to_asset_type = {
        "copywriting": "copy",
        "image_generation": "image",
        "video_generation": "video",
        "ads_strategy": "ads",
    }
    generated_asset_limits = {
        "copy": deliverables.copy_variants,
        "image": deliverables.image_assets,
        "video": deliverables.short_video_assets,
        "ads": deliverables.ads_strategy,
    }
    generated_asset_counts = {"copy": 0, "image": 0, "video": 0, "ads": 0}

    copy_assets = []
    image_assets = []
    video_assets = []
    ads_plan: dict[str, Any] = {}
    visible_generated_asset_ids: set[str] = set()

    for asset in assets:
        if not is_displayable_asset(asset):
            continue
        metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
        is_manual_asset = metadata.get("source") in {"manual", "manual_upload"}
        is_versioned_asset = bool(metadata.get("asset_base_name") or metadata.get("root_asset_id") or metadata.get("is_regenerated"))
        if not is_manual_asset:
            if asset.asset_type not in allowed_generated_asset_types:
                continue
            if not is_versioned_asset:
                if latest_run_id and asset.run_id != latest_run_id:
                    continue
                task_type = current_tasks.get(asset.task_id)
                expected_asset_type = task_type_to_asset_type.get(task_type or "")
                if expected_asset_type != asset.asset_type:
                    continue
                limit = generated_asset_limits.get(asset.asset_type, 0)
                if generated_asset_counts.get(asset.asset_type, 0) >= limit:
                    continue
                generated_asset_counts[asset.asset_type] = generated_asset_counts.get(asset.asset_type, 0) + 1
            visible_generated_asset_ids.add(asset.asset_id)
        validation = validations.get(asset.asset_id)
        enriched = {
            "asset_id": asset.asset_id,
            "asset_name": asset_metadata_name(metadata),
            "url": public_asset_url(asset.url),
            "validated": asset.validation_status == "passed",
            "score": validation.score if validation else None,
        }
        if asset.asset_type == "video":
            fallback_reason = metadata.get("fallback_reason")
            fallback_detail = metadata.get("fallback_detail")
            provider = metadata.get("provider")
            model_name = metadata.get("model_name")
            if isinstance(fallback_reason, str) and fallback_reason:
                enriched["fallback_reason"] = fallback_reason
            if isinstance(fallback_detail, str) and fallback_detail:
                enriched["fallback_detail"] = fallback_detail
            if isinstance(provider, str) and provider:
                enriched["provider"] = provider
            if isinstance(model_name, str) and model_name:
                enriched["model_name"] = model_name
        if asset.asset_type == "copy":
            copy_text = extract_copy_text_from_asset(asset)
            if not copy_text:
                continue
            copy_assets.append({"variant_id": asset.asset_id, "asset_name": asset_metadata_name(metadata), "text": copy_text})
        elif asset.asset_type == "image":
            image_assets.append(enriched)
        elif asset.asset_type == "video":
            video_assets.append(enriched)
        elif asset.asset_type == "ads":
            ads_plan = {
                "facebook": {"budget": campaign.brief.budget * 0.5},
                "google_display": {"budget": campaign.brief.budget * 0.5},
            }

    if persistence is not None:
        try:
            removed = persistence.delete_generated_assets_except(campaign_id, visible_generated_asset_ids)
            if removed:
                metrics.inc("db_write_total")
        except Exception:
            metrics.inc("db_write_fail_total")
    if campaign_id in asset_cache:
        asset_cache[campaign_id] = [
            item
            for item in asset_cache[campaign_id]
            if (isinstance(item.metadata, dict) and item.metadata.get("source") in {"manual", "manual_upload"})
            or item.asset_id in visible_generated_asset_ids
        ]

    return FinalAssetBundle(
        campaign_id=campaign_id,
        status="completed",
        copy_assets=copy_assets,
        image_assets=image_assets,
        video_assets=video_assets,
        ads_strategy=ads_plan,
    )


@app.post(
    "/api/v1/campaigns/{campaign_id}/assets/manual",
    response_model=ManualAssetCreateResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_manual_asset(campaign_id: str, payload: ManualAssetCreateRequest, req: Request) -> ManualAssetCreateResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        actor = require_jwt(req)
        actor_company_id = actor.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized")

    if payload.asset_type == "copy":
        if not payload.text or not payload.text.strip():
            raise HTTPException(status_code=400, detail="text is required for copy asset")
    else:
        if not payload.url or not payload.url.strip():
            raise HTTPException(status_code=400, detail="url is required for image/video asset")

    asset_id = f"ast_{uuid4().hex[:10]}"
    asset = AssetOutput(
        company_id=campaign.company_id,
        asset_id=asset_id,
        campaign_id=campaign_id,
        task_id=f"manual_{payload.asset_type}_{uuid4().hex[:6]}",
        asset_type=payload.asset_type,
        url=payload.url.strip() if payload.url else f"generated://manual/{asset_id}",
        metadata={
            "source": "manual",
            "manual_text": payload.text.strip() if payload.text else None,
            "prompt": payload.prompt.strip() if payload.prompt else None,
        },
        validation_status="pending",
        created_at=now_utc(),
    )
    save_assets_and_validations([asset], [])

    append_trace_event(
        campaign_id=campaign_id,
        event_type="asset_manual_created",
        actor_id="admin" if is_platform_admin_request(req) else "member",
        actor_role="admin" if is_platform_admin_request(req) else "member",
        summary=f"Manual asset created: {payload.asset_type}",
        payload={"asset_id": asset_id, "asset_type": payload.asset_type},
        source="manual",
        company_id=campaign.company_id,
    )

    return ManualAssetCreateResponse(
        campaign_id=campaign_id,
        asset_id=asset_id,
        asset_type=payload.asset_type,
        validation_status="pending",
    )


def _generate_single_asset_background(campaign: CampaignRecord, payload: SingleAssetGenerateRequest, operator: str) -> None:
    task_type = {
        "copy": "copywriting",
        "image": "image_generation",
        "video": "video_generation",
    }[payload.asset_type]
    task = TaskRecord(
        company_id=campaign.company_id,
        task_id=f"manual_{payload.asset_type}_{uuid4().hex[:10]}",
        campaign_id=campaign.campaign_id,
        task_type=task_type,
        status="planned",
        priority=1,
        depends_on=[],
        acceptance=[],
    )
    deliverables = campaign.brief.deliverables.model_copy(update={
        "copy_variants": 1 if payload.asset_type == "copy" else 0,
        "image_assets": 1 if payload.asset_type == "image" else 0,
        "short_video_assets": 1 if payload.asset_type == "video" else 0,
        "ads_strategy": 0,
    })
    project_description = campaign.brief.project_description or campaign.brief.description or ""
    if payload.prompt.strip():
        project_description = f"{project_description}\n\nSingle asset generation instruction: {payload.prompt.strip()}"
    generated_campaign = campaign.model_copy(update={
        "brief": campaign.brief.model_copy(update={
            "deliverables": deliverables,
            "project_description": project_description,
            "description": project_description,
        }),
    })
    try:
        run_id = latest_campaign_run_id(campaign.campaign_id) or ""
        assets, validations = generate_outputs_via_workers(
            campaign.company_id,
            campaign.campaign_id,
            generated_campaign,
            [task],
            run_id=run_id,
        )
        save_assets_and_validations(assets, validations)
        append_trace_event(
            campaign_id=campaign.campaign_id,
            event_type="single_asset_generated",
            actor_id=operator,
            actor_role="operator",
            summary=f"Single {payload.asset_type} asset generated",
            payload={"asset_type": payload.asset_type, "assets": len(assets)},
            source="manual",
            company_id=campaign.company_id,
        )
    except Exception:
        logger.exception("Single asset generation failed for campaign %s", campaign.campaign_id)


@app.post(
    "/api/v1/campaigns/{campaign_id}/assets/generate",
    response_model=SingleAssetGenerateResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def generate_single_asset(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    payload: SingleAssetGenerateRequest,
    req: Request,
) -> SingleAssetGenerateResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign)
    operator = "admin"
    background_tasks.add_task(_generate_single_asset_background, campaign, payload, operator)
    return SingleAssetGenerateResponse(campaign_id=campaign_id, asset_type=payload.asset_type, status="queued")


@app.post(
    "/api/v1/campaigns/{campaign_id}/assets/manual-upload",
    response_model=ManualAssetCreateResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def upload_manual_asset(
    campaign_id: str,
    req: Request,
    asset_type: Literal["copy", "image", "video"] = Form(...),
    prompt: str | None = Form(None),
    file: UploadFile = File(...),
) -> ManualAssetCreateResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not is_platform_admin_request(req):
        actor = require_jwt(req)
        actor_company_id = actor.company_id or ""
        if campaign.company_id != actor_company_id:
            raise HTTPException(status_code=403, detail="Not authorized")

    original_name = os.path.basename(file.filename or "manual-asset.bin")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name).strip("._") or "manual-asset.bin"
    asset_id = f"ast_{uuid4().hex[:10]}"
    target_dir = os.path.join(MANUAL_ASSETS_DIR, campaign.company_id, campaign_id)
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{asset_id}_{safe_name}"
    stored_path = os.path.abspath(os.path.join(target_dir, stored_name))
    root_path = os.path.abspath(target_dir)
    if not stored_path.startswith(root_path):
        raise HTTPException(status_code=400, detail="Invalid file name")

    with open(stored_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    manual_text: str | None = None
    if asset_type == "copy":
        try:
            with open(stored_path, "r", encoding="utf-8") as source:
                manual_text = source.read().strip()
        except UnicodeDecodeError as exc:
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(status_code=400, detail="Copy asset must be a UTF-8 text file") from exc
        if not manual_text:
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(status_code=400, detail="Copy asset cannot be empty")

    public_url = f"/api/v1/campaigns/{campaign_id}/assets/manual-files/{asset_id}/{parse.quote(safe_name)}"
    asset = AssetOutput(
        company_id=campaign.company_id,
        asset_id=asset_id,
        campaign_id=campaign_id,
        task_id=f"manual_{asset_type}_{uuid4().hex[:6]}",
        asset_type=asset_type,
        url=public_url,
        metadata={
            "source": "manual_upload",
            "file_name": safe_name,
            "stored_path": stored_path,
            "prompt": prompt.strip() if prompt else None,
            "manual_text": manual_text,
        },
        validation_status="pending",
        created_at=now_utc(),
    )
    save_assets_and_validations([asset], [])

    append_trace_event(
        campaign_id=campaign_id,
        event_type="asset_manual_uploaded",
        actor_id="admin" if is_platform_admin_request(req) else "member",
        actor_role="admin" if is_platform_admin_request(req) else "member",
        summary=f"Manual asset uploaded: {asset_type}",
        payload={"asset_id": asset_id, "asset_type": asset_type, "file_name": safe_name},
        source="manual",
        company_id=campaign.company_id,
    )

    return ManualAssetCreateResponse(campaign_id=campaign_id, asset_id=asset_id, asset_type=asset_type, validation_status="pending")


@app.get("/api/v1/campaigns/{campaign_id}/assets/manual-files/{asset_id}/{file_name}")
def download_manual_asset(req: Request, campaign_id: str, asset_id: str, file_name: str) -> FileResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign)
    for asset in list_assets(campaign_id):
        if asset.asset_id != asset_id:
            continue
        stored_path = asset.metadata.get("stored_path") if isinstance(asset.metadata, dict) else None
        if isinstance(stored_path, str) and os.path.exists(stored_path):
            return FileResponse(stored_path, filename=file_name)
    raise HTTPException(status_code=404, detail="Manual asset file not found")


@app.get("/api/v1/campaigns/{campaign_id}/assets/generated-files/{asset_id}/{file_name}")
def download_generated_asset(req: Request, campaign_id: str, asset_id: str, file_name: str) -> FileResponse:
    # Generated asset URLs are embedded directly in <img>, <video>, and browser
    # download links. Those browser requests cannot attach the app JWT header, so
    # this endpoint must be directly readable. The URL still contains an
    # unguessable asset_id and only serves files previously persisted in
    # GENERATED_ASSETS_DIR with metadata source=generated_cache.
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for asset in list_assets(campaign_id):
        if asset.asset_id != asset_id:
            continue
        metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
        stored_path = metadata.get("stored_path")
        if metadata.get("source") == "generated_cache" and isinstance(stored_path, str) and os.path.exists(stored_path):
            media_type = metadata.get("content_type") if isinstance(metadata.get("content_type"), str) else None
            return FileResponse(stored_path, media_type=media_type, filename=file_name)
    raise HTTPException(status_code=404, detail="Generated asset file not found")


@app.get("/api/v1/knowledge-items", response_model=KnowledgeItemListResponse)
def list_knowledge_items(req: Request, company_id: str | None = None) -> KnowledgeItemListResponse:
    if is_platform_admin_request(req):
        target_company_id = company_id or "platform"
    else:
        payload = require_jwt(req)
        target_company_id = payload.company_id or ""

    if persistence is not None:
        rows = persistence.list_knowledge_items(target_company_id)
        items = [KnowledgeItemRecord(**row) for row in rows]
    else:
        items = knowledge_items.get(target_company_id, [])
    return KnowledgeItemListResponse(items=items, total=len(items))


@app.post("/api/v1/knowledge-items", response_model=KnowledgeItemRecord)
def create_knowledge_item(req: Request, payload: KnowledgeItemCreateRequest) -> KnowledgeItemRecord:
    if is_platform_admin_request(req):
        company_id = str(payload.metadata.get("company_id") or "platform")
        actor_id = "platform-admin"
    else:
        actor = require_jwt(req)
        company_id = actor.company_id or ""
        actor_id = actor.sub

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    item = KnowledgeItemRecord(
        item_id=f"kh_{uuid4().hex[:12]}",
        company_id=company_id,
        title=title,
        source=payload.source,
        description=payload.description.strip(),
        content_url=payload.content_url,
        metadata={**payload.metadata, "created_by": actor_id},
        created_at=now_utc(),
    )
    if persistence is not None:
        persistence.create_knowledge_item(item.model_dump(mode="python"))
    else:
        knowledge_items.setdefault(company_id, []).insert(0, item)
    return item


@app.post("/api/v1/knowledge-items/upload", response_model=KnowledgeItemRecord)
def upload_knowledge_item(
    req: Request,
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    asset_type: str = Form(""),
    file: UploadFile = File(...),
) -> KnowledgeItemRecord:
    if is_platform_admin_request(req):
        company_id = "platform"
        actor_id = "platform-admin"
    else:
        actor = require_jwt(req)
        company_id = actor.company_id or ""
        actor_id = actor.sub

    cleaned_title = title.strip()
    if not cleaned_title:
        raise HTTPException(status_code=400, detail="title is required")

    original_name = os.path.basename(file.filename or "knowledge-file.bin")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name).strip("._") or "knowledge-file.bin"
    item_id = f"kh_{uuid4().hex[:12]}"
    target_dir = os.path.join(KNOWLEDGE_UPLOADS_DIR, company_id)
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{item_id}_{safe_name}"
    stored_path = os.path.abspath(os.path.join(target_dir, stored_name))
    root_path = os.path.abspath(target_dir)
    if not stored_path.startswith(root_path):
        raise HTTPException(status_code=400, detail="Invalid file name")

    with open(stored_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    content_url = f"/api/v1/knowledge-items/{item_id}/download/{parse.quote(safe_name)}"
    item = KnowledgeItemRecord(
        item_id=item_id,
        company_id=company_id,
        title=cleaned_title,
        source="manual",
        description=description.strip(),
        content_url=content_url,
        metadata={
            "created_by": actor_id,
            "file_name": safe_name,
            "file_type": file.content_type or "application/octet-stream",
            "stored_path": stored_path,
            "category": category.strip(),
            "asset_type": asset_type.strip() or "file",
        },
        created_at=now_utc(),
    )
    if persistence is not None:
        persistence.create_knowledge_item(item.model_dump(mode="python"))
    else:
        knowledge_items.setdefault(company_id, []).insert(0, item)
    return item


@app.get("/api/v1/knowledge-items/{item_id}/download/{file_name}")
def download_knowledge_item(req: Request, item_id: str, file_name: str) -> FileResponse:
    if is_platform_admin_request(req):
        company_id = req.query_params.get("company_id") or "platform"
    else:
        actor = require_jwt(req)
        company_id = actor.company_id or ""

    if persistence is not None:
        candidates = persistence.list_knowledge_items(company_id)
        for item in candidates:
            metadata = item.get("metadata", {})
            stored_path = metadata.get("stored_path") if isinstance(metadata, dict) else None
            if item.get("item_id") == item_id and isinstance(stored_path, str) and os.path.exists(stored_path):
                return FileResponse(stored_path, filename=file_name)
    else:
        for item in knowledge_items.get(company_id, []):
            stored_path = item.metadata.get("stored_path") if isinstance(item.metadata, dict) else None
            if item.item_id == item_id and isinstance(stored_path, str) and os.path.exists(stored_path):
                return FileResponse(stored_path, filename=file_name)
    raise HTTPException(status_code=404, detail="Knowledge item file not found")


@app.patch("/api/v1/knowledge-items/{item_id}", response_model=KnowledgeItemRecord)
def update_knowledge_item(req: Request, item_id: str, payload: KnowledgeItemUpdateRequest) -> KnowledgeItemRecord:
    if is_platform_admin_request(req):
        company_id = req.query_params.get("company_id") or "platform"
    else:
        actor = require_jwt(req)
        company_id = actor.company_id or ""

    updates = payload.model_dump(exclude_unset=True)
    if persistence is not None:
        updated = persistence.update_knowledge_item(company_id, item_id, updates)
        if updated is None:
            raise HTTPException(status_code=404, detail="Knowledge item not found")
        return KnowledgeItemRecord(**updated)

    rows = knowledge_items.get(company_id, [])
    for index, item in enumerate(rows):
        if item.item_id != item_id:
            continue
        metadata = dict(item.metadata or {})
        if isinstance(updates.get("metadata"), dict):
            metadata.update(updates["metadata"])
        if updates.get("category") is not None:
            metadata["category"] = str(updates["category"]).strip()
        updated_item = item.model_copy(update={
            "title": str(updates.get("title") or item.title).strip(),
            "description": str(updates.get("description") if updates.get("description") is not None else item.description).strip(),
            "content_url": updates.get("content_url") if updates.get("content_url") is not None else item.content_url,
            "metadata": metadata,
        })
        rows[index] = updated_item
        knowledge_items[company_id] = rows
        return updated_item
    raise HTTPException(status_code=404, detail="Knowledge item not found")


@app.delete("/api/v1/knowledge-items/{item_id}", response_model=KnowledgeItemDeleteResponse)
def delete_knowledge_item(req: Request, item_id: str) -> KnowledgeItemDeleteResponse:
    if is_platform_admin_request(req):
        company_id = req.query_params.get("company_id") or "platform"
    else:
        actor = require_jwt(req)
        company_id = actor.company_id or ""

    if persistence is not None:
        deleted = persistence.soft_delete_knowledge_item(company_id, item_id)
    else:
        before = len(knowledge_items.get(company_id, []))
        knowledge_items[company_id] = [item for item in knowledge_items.get(company_id, []) if item.item_id != item_id]
        deleted = len(knowledge_items.get(company_id, [])) < before
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return KnowledgeItemDeleteResponse(item_id=item_id, deleted=True)


@app.post(
    "/api/v1/campaigns/{campaign_id}/publish",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def publish_campaign(campaign_id: str, payload: dict[str, Any], req: Request) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    actor_payload = require_campaign_access(req, campaign)
    if actor_payload is not None:
        require_any_permission(actor_payload, {"publish:execute", "role:manage"})

    from .publishing import PublishRequest as PublishPayload, dispatch_publish

    publish_payload = PublishPayload.model_validate(payload)
    results = [item.model_dump() for item in dispatch_publish(campaign_id, publish_payload.targets)]

    append_trace_event(
        campaign_id=campaign_id,
        event_type="campaign_published",
        actor_id=publish_payload.operator or "admin",
        actor_role="admin",
        summary=f"Campaign published to {[r['platform'] for r in results]}",
        payload={"results": results},
        source="publishing",
    )
    return {"campaign_id": campaign_id, "results": results}


@app.get(
    "/api/v1/campaigns/{campaign_id}/trace",
    response_model=CampaignTraceSummaryResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_campaign_trace_summary(campaign_id: str, req: Request) -> CampaignTraceSummaryResponse:
    metrics.inc("trace_read_total")

    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        metrics.inc("trace_read_fail_total")
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_trace_access(req, campaign)

    trace = lookup_campaign_trace(campaign_id)
    if persistence is not None:
        event_total = persistence.count_campaign_trace_events(campaign_id)
        chat_total = persistence.count_campaign_trace_chat(campaign_id)
    else:
        event_total = len(campaign_trace_events.get(campaign_id, []))
        chat_total = len(campaign_trace_chats.get(campaign_id, []))
    return CampaignTraceSummaryResponse(trace=trace, event_total=event_total, chat_total=chat_total)


@app.get(
    "/api/v1/campaigns/{campaign_id}/trace/events",
    response_model=CampaignTraceEventListResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_campaign_trace_events(
    campaign_id: str,
    req: Request,
    limit: int = 50,
    cursor: str | None = None,
    event_type: str | None = None,
    actor_id: str | None = None,
    keyword: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> CampaignTraceEventListResponse:
    metrics.inc("trace_read_total")
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        metrics.inc("trace_read_fail_total")
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_trace_access(req, campaign)

    limit = max(1, min(limit, 200))
    if keyword is not None and len(keyword.strip()) > 120:
        raise HTTPException(status_code=400, detail="keyword must be <= 120 characters")
    cursor_before = parse_trace_cursor_or_400(cursor, "cursor", "event") if cursor else None
    from_dt = parse_iso_datetime_or_400(from_ts, "from_ts") if from_ts else None
    to_dt = parse_iso_datetime_or_400(to_ts, "to_ts") if to_ts else None
    items = list_trace_events(campaign_id, limit, cursor_before, event_type, actor_id, keyword, from_dt, to_dt)
    next_cursor = to_trace_cursor(items[-1].created_at, items[-1].event_id) if len(items) == limit else None
    if persistence is not None:
        total = persistence.count_campaign_trace_events_filtered(campaign_id, event_type, actor_id, keyword, from_dt, to_dt)
    else:
        total = count_trace_events_filtered(campaign_id, event_type, actor_id, keyword, from_dt, to_dt)
    return CampaignTraceEventListResponse(items=items, total=total, next_cursor=next_cursor)


@app.get(
    "/api/v1/campaigns/{campaign_id}/trace/chat",
    response_model=CampaignTraceChatListResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_campaign_trace_chat(
    campaign_id: str,
    req: Request,
    limit: int = 50,
    cursor: str | None = None,
) -> CampaignTraceChatListResponse:
    metrics.inc("trace_read_total")
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        metrics.inc("trace_read_fail_total")
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_trace_access(req, campaign)

    limit = max(1, min(limit, 200))
    cursor_before = parse_trace_cursor_or_400(cursor, "cursor", "chat") if cursor else None
    items = list_trace_chat(campaign_id, limit, cursor_before)
    next_cursor = to_trace_cursor(items[-1].created_at, items[-1].message_id) if len(items) == limit else None
    if persistence is not None:
        total = persistence.count_campaign_trace_chat(campaign_id)
    else:
        total = len(campaign_trace_chats.get(campaign_id, []))
    return CampaignTraceChatListResponse(items=items, total=total, next_cursor=next_cursor)


@app.get(
    "/api/v1/campaigns/{campaign_id}/work-orders",
    response_model=WorkOrderListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_campaign_work_orders(
    campaign_id: str,
    req: Request,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
) -> WorkOrderListResponse:
    require_internal_api_key(req)
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    limit = max(1, min(limit, 200))
    allowed_status = {"open", "in_progress", "blocked", "review_pending", "approved", "rejected", "done", "cancelled"}
    if status is not None and status not in allowed_status:
        raise HTTPException(status_code=400, detail="Invalid work order status")
    cursor_before = parse_work_order_cursor_or_400(cursor, "cursor") if cursor else None
    items = list_campaign_work_orders_data(campaign_id, limit, cursor_before, status, assignee)
    items = [enforce_work_order_sla(item) for item in items]
    next_cursor = to_trace_cursor(items[-1].updated_at, items[-1].work_order_id) if len(items) == limit else None
    total = count_campaign_work_orders_data(campaign_id, status, assignee)
    return WorkOrderListResponse(items=items, total=total, next_cursor=next_cursor)


@app.post(
    "/api/v1/campaigns/{campaign_id}/work-orders",
    response_model=WorkOrderRecord,
    responses={404: {"model": ErrorResponse}},
)
def create_campaign_work_order(campaign_id: str, payload: WorkOrderCreateRequest, req: Request) -> WorkOrderRecord:
    require_internal_api_key(req)
    actor_id, actor_role = resolve_internal_actor(req)
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if payload.priority < 1 or payload.priority > 5:
        raise HTTPException(status_code=400, detail="priority must be between 1 and 5")

    if payload.task_id:
        tasks = store.get_tasks(campaign_id)
        if all(item.task_id != payload.task_id for item in tasks):
            raise HTTPException(status_code=400, detail="task_id does not belong to campaign")

    due_at_dt = parse_optional_iso_datetime_or_400(payload.due_at, "due_at")

    now_dt = now_utc()
    now = now_dt.isoformat()
    record = WorkOrderRecord(
        company_id=campaign.company_id,
        work_order_id=f"wko_{uuid4().hex[:12]}",
        campaign_id=campaign_id,
        task_id=payload.task_id,
        title=title,
        description=payload.description.strip(),
        assignee=payload.assignee,
        status="open",
        priority=payload.priority,
        created_by=actor_id,
        due_at=due_at_dt.isoformat() if due_at_dt is not None else None,
        escalated_at=None,
        escalation_reason=None,
        overdue=False,
        created_at=now,
        updated_at=now,
    )

    if persistence is not None:
        persistence.create_work_order(
            work_order_id=record.work_order_id,
            campaign_id=record.campaign_id,
            task_id=record.task_id,
            title=record.title,
            description=record.description,
            assignee=record.assignee,
            status=record.status,
            priority=record.priority,
            created_by=record.created_by,
            due_at=due_at_dt,
            created_at=now_dt,
        )
        stored = get_work_order_data(record.work_order_id)
        if stored is not None:
            record = stored
    else:
        campaign_work_orders.setdefault(campaign_id, []).insert(0, record)
        work_order_by_id[record.work_order_id] = record

    append_trace_event(
        campaign_id=campaign_id,
        event_type="work_order_created",
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"Work order {record.work_order_id} created",
        payload={"work_order_id": record.work_order_id, "task_id": record.task_id, "priority": record.priority, "due_at": record.due_at},
        source="work_order",
    )
    metrics.inc("work_order_created_total")
    return enforce_work_order_sla(record)


@app.get(
    "/api/v1/work-orders/{work_order_id}",
    response_model=WorkOrderRecord,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_work_order(work_order_id: str, req: Request) -> WorkOrderRecord:
    record = get_work_order_data(work_order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Platform admin bypass
    if is_platform_admin_request(req):
        return enforce_work_order_sla(record)

    # JWT auth + company verification
    payload = require_jwt(req)
    actor_company_id = payload.company_id or ""
    if record.company_id != actor_company_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this work order")
    return enforce_work_order_sla(record)


@app.patch(
    "/api/v1/work-orders/{work_order_id}",
    response_model=WorkOrderRecord,
    responses={404: {"model": ErrorResponse}},
)
def update_work_order(work_order_id: str, payload: WorkOrderUpdateRequest, req: Request) -> WorkOrderRecord:
    require_internal_api_key(req)
    actor_id, actor_role = resolve_internal_actor(req)
    existing = get_work_order_data(work_order_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Work order not found")

    if payload.priority is not None and (payload.priority < 1 or payload.priority > 5):
        raise HTTPException(status_code=400, detail="priority must be between 1 and 5")

    provided = set(payload.model_fields_set)
    if not provided:
        return existing

    next_title: str | None = None
    next_description: str | None = None
    next_assignee: str | None = None
    next_status: Literal["open", "in_progress", "blocked", "review_pending", "approved", "rejected", "done", "cancelled"] | None = None
    next_priority: int | None = None
    next_due_at: datetime | None = None
    reset_escalation = False

    changed = False

    if "title" in provided:
        if payload.title is None:
            raise HTTPException(status_code=400, detail="title must not be null")
        title_trimmed = payload.title.strip()
        if title_trimmed == "":
            raise HTTPException(status_code=400, detail="title must not be empty")
        if title_trimmed != existing.title:
            next_title = title_trimmed
            changed = True

    if "description" in provided:
        if payload.description is None:
            raise HTTPException(status_code=400, detail="description must not be null")
        if payload.description != existing.description:
            next_description = payload.description
            changed = True

    if "assignee" in provided:
        if payload.assignee is None:
            raise HTTPException(status_code=400, detail="assignee must not be null")
        if payload.assignee != (existing.assignee or ""):
            next_assignee = payload.assignee
            changed = True

    if "status" in provided:
        if payload.status is None:
            raise HTTPException(status_code=400, detail="status must not be null")
        if payload.status != existing.status:
            if payload.status in {"approved", "rejected", "done"} and actor_role != "admin":
                append_trace_event(
                    campaign_id=existing.campaign_id,
                    event_type="work_order_status_denied",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    summary=f"Denied privileged status change for {existing.work_order_id}",
                    payload={
                        "work_order_id": existing.work_order_id,
                        "from": existing.status,
                        "to": payload.status,
                        "reason": "admin_required",
                    },
                    source="work_order",
                )
                metrics.inc("work_order_update_denied_total")
                raise HTTPException(status_code=403, detail="admin role required for this status transition")
            if not can_transition_work_order_status(existing.status, payload.status):
                append_trace_event(
                    campaign_id=existing.campaign_id,
                    event_type="work_order_status_denied",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    summary=f"Denied status change for {existing.work_order_id}",
                    payload={
                        "work_order_id": existing.work_order_id,
                        "from": existing.status,
                        "to": payload.status,
                        "reason": "invalid_transition",
                    },
                    source="work_order",
                )
                metrics.inc("work_order_update_denied_total")
                raise HTTPException(status_code=403, detail="status transition is not allowed")
            next_status = payload.status
            changed = True

    if "priority" in provided:
        if payload.priority is None:
            raise HTTPException(status_code=400, detail="priority must not be null")
        if payload.priority != existing.priority:
            next_priority = payload.priority
            changed = True

    if "due_at" in provided:
        parsed_due_at = parse_optional_iso_datetime_or_400(payload.due_at, "due_at")
        existing_due_at = parse_optional_iso_datetime_or_400(existing.due_at, "due_at") if existing.due_at else None
        if parsed_due_at != existing_due_at:
            next_due_at = parsed_due_at
            reset_escalation = True
            changed = True

    if not changed:
        return existing

    now_dt = now_utc()
    now = now_dt.isoformat()

    if persistence is not None:
        updated_flag = persistence.update_work_order(
            work_order_id=work_order_id,
            title=next_title,
            description=next_description,
            assignee=next_assignee,
            status=next_status,
            priority=next_priority,
            due_at=next_due_at,
            clear_escalation=reset_escalation,
            updated_at=now_dt,
        )
        if not updated_flag:
            return existing
        updated = get_work_order_data(work_order_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Work order not found")
        record = updated
    else:
        record = existing.model_copy(
            update={
                **({"title": next_title} if next_title is not None else {}),
                **({"description": next_description} if next_description is not None else {}),
                **({"assignee": next_assignee} if next_assignee is not None else {}),
                **({"status": next_status} if next_status is not None else {}),
                **({"priority": next_priority} if next_priority is not None else {}),
                **({"due_at": next_due_at.isoformat() if next_due_at is not None else None} if "due_at" in provided else {}),
                **({"escalated_at": None, "escalation_reason": None} if reset_escalation else {}),
                "updated_at": now,
            }
        )
        work_order_by_id[work_order_id] = record
        rows = campaign_work_orders.get(record.campaign_id, [])
        for idx, item in enumerate(rows):
            if item.work_order_id == work_order_id:
                rows[idx] = record
                break

    append_trace_event(
        campaign_id=record.campaign_id,
        event_type="work_order_updated",
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"Work order {record.work_order_id} updated",
        payload={
            "work_order_id": record.work_order_id,
            "status": record.status,
            "assignee": record.assignee,
            "priority": record.priority,
            "due_at": record.due_at,
            "escalated_at": record.escalated_at,
        },
        source="work_order",
    )
    metrics.inc("work_order_updated_total")
    return enforce_work_order_sla(record)


@app.get(
    "/api/v1/work-orders/{work_order_id}/messages",
    response_model=WorkOrderMessageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_work_order_messages(
    work_order_id: str,
    req: Request,
    limit: int = 50,
    cursor: str | None = None,
) -> WorkOrderMessageListResponse:
    require_internal_api_key(req)
    work_order = get_work_order_data(work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="Work order not found")
    work_order = enforce_work_order_sla(work_order)

    limit = max(1, min(limit, 200))
    cursor_before = parse_trace_cursor_or_400(cursor, "cursor", "chat") if cursor else None
    items = list_work_order_messages_data(work_order_id, limit, cursor_before)
    next_cursor = to_trace_cursor(items[-1].created_at, items[-1].message_id) if len(items) == limit else None
    total = count_work_order_messages_data(work_order_id)
    return WorkOrderMessageListResponse(items=items, total=total, next_cursor=next_cursor)


@app.post(
    "/api/v1/work-orders/{work_order_id}/messages",
    response_model=WorkOrderMessageRecord,
    responses={404: {"model": ErrorResponse}},
)
def create_work_order_message(
    work_order_id: str,
    payload: WorkOrderMessageCreateRequest,
    req: Request,
) -> WorkOrderMessageRecord:
    require_internal_api_key(req)
    actor_id, actor_role = resolve_internal_actor(req)
    work_order = get_work_order_data(work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="Work order not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    masked = mask_work_order_text(content)
    now_dt = now_utc()
    now = now_dt.isoformat()
    record = WorkOrderMessageRecord(
        company_id=work_order.company_id,
        message_id=f"msg_{uuid4().hex[:12]}",
        work_order_id=work_order_id,
        campaign_id=work_order.campaign_id,
        role=payload.role,
        content_masked=masked,
        actor_id=actor_id,
        created_at=now,
    )

    if persistence is not None:
        persistence.append_work_order_message(
            message_id=record.message_id,
            work_order_id=record.work_order_id,
            campaign_id=record.campaign_id,
            role=record.role,
            content_masked=record.content_masked,
            actor_id=record.actor_id,
            created_at=now_dt,
        )
    else:
        work_order_messages.setdefault(work_order_id, []).insert(0, record)
        updated = work_order.model_copy(update={"updated_at": now})
        work_order_by_id[work_order_id] = updated
        rows = campaign_work_orders.get(work_order.campaign_id, [])
        for idx, item in enumerate(rows):
            if item.work_order_id == work_order_id:
                rows[idx] = updated
                break

    generated_reply: WorkOrderMessageRecord | None = None
    if payload.role == "user":
        assistant_text = generate_work_order_assistant_reply(work_order, content)
        assistant_record = WorkOrderMessageRecord(
            company_id=work_order.company_id,
            message_id=f"msg_{uuid4().hex[:12]}",
            work_order_id=work_order_id,
            campaign_id=work_order.campaign_id,
            role="assistant",
            content_masked=mask_work_order_text(assistant_text),
            actor_id="assistant",
            created_at=now_utc().isoformat(),
        )
        if persistence is not None:
            persistence.append_work_order_message(
                message_id=assistant_record.message_id,
                work_order_id=assistant_record.work_order_id,
                campaign_id=assistant_record.campaign_id,
                role=assistant_record.role,
                content_masked=assistant_record.content_masked,
                actor_id=assistant_record.actor_id,
                created_at=parse_iso_datetime_or_400(assistant_record.created_at, "created_at"),
            )
        else:
            work_order_messages.setdefault(work_order_id, []).insert(0, assistant_record)
        generated_reply = assistant_record

    append_trace_event(
        campaign_id=work_order.campaign_id,
        event_type="work_order_message_appended",
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"Work order {work_order_id} message appended",
        payload={"work_order_id": work_order_id, "role": payload.role},
        source="work_order",
    )
    metrics.inc("work_order_message_total")
    if generated_reply is not None:
        metrics.inc("work_order_message_total")
        append_trace_event(
            campaign_id=work_order.campaign_id,
            event_type="work_order_content_generated",
            actor_id="assistant",
            actor_role="system",
            summary=f"Work order {work_order_id} assistant draft generated",
            payload={"work_order_id": work_order_id, "message_id": generated_reply.message_id},
            source="work_order",
        )
    return record


@app.post(
    "/api/v1/campaigns/{campaign_id}/trace/events",
    response_model=CampaignTraceEventRecord,
    responses={404: {"model": ErrorResponse}},
)
def create_campaign_trace_event(
    campaign_id: str,
    payload: CampaignTraceEventCreateRequest,
    req: Request,
) -> CampaignTraceEventRecord:
    require_internal_api_key(req)
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        run_trace_cleanup(force=False)
    except Exception as exc:
        metrics.inc("trace_cleanup_fail_total")
        logger.warning(f"Trace cleanup failed in append_trace_event_internal: {exc}")

    if payload.event_type == "chat_message":
        role = str(payload.payload.get("role") or "user")
        content_raw = payload.payload.get("content_masked")
        if not isinstance(content_raw, str) or content_raw.strip() == "":
            raise HTTPException(status_code=400, detail="chat_message payload.content_masked is required")
        content_masked = content_raw.strip()
        raw_ref = payload.payload.get("raw_ref")
        record = append_trace_event(
            campaign_id=campaign_id,
            event_type=payload.event_type,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            summary=f"{role} chat message",
            payload=payload.payload,
            source=payload.source or "chatbot",
        )
        append_trace_chat_message(
            campaign_id=campaign_id,
            role=role,
            content_masked=content_masked,
            actor_id=payload.actor_id,
            source=payload.source or "chatbot",
            raw_ref=str(raw_ref) if raw_ref is not None else None,
        )
        return record

    record = append_trace_event(
        campaign_id=campaign_id,
        event_type=payload.event_type,
        actor_id=payload.actor_id,
        actor_role=payload.actor_role,
        summary=payload.summary,
        payload=payload.payload,
        source=payload.source or "system",
    )

    return record


@app.post(
    "/api/v1/system/trace/cleanup",
    responses={503: {"model": ErrorResponse}},
)
def cleanup_campaign_traces(req: Request, force: bool = False) -> dict[str, int]:
    require_internal_api_key(req)
    try:
        return run_trace_cleanup(force=force)
    except Exception as exc:
        metrics.inc("trace_cleanup_fail_total")
        raise HTTPException(status_code=503, detail=f"Trace cleanup failed: {exc}") from exc


@app.get(
    "/api/v1/system/trace/health",
    response_model=SystemTraceHealthResponse,
    responses={401: {"model": ErrorResponse}},
)
def get_system_trace_health(req: Request) -> SystemTraceHealthResponse:
    require_internal_api_key(req)
    return build_trace_health_snapshot()


@app.get(
    "/api/v1/system/queue-health",
    response_model=QueueHealthResponse,
    responses={502: {"model": ErrorResponse}},
)
def get_system_queue_health(req: Request) -> QueueHealthResponse:
    require_authenticated_read_access(req)
    try:
        payload = get_json(f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/monitor/overview")
        return QueueHealthResponse(**payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch orchestrator health: {exc}") from exc


@app.post(
    "/api/v1/system/operations/health-check",
    response_model=OperationHealthCheckResponse,
    responses={502: {"model": ErrorResponse}},
)
def system_operations_health_check(payload: HealthCheckRequest, req: Request) -> OperationHealthCheckResponse:
    require_authenticated_read_access(req)
    try:
        result = post_json(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/ops/health-check",
            payload.model_dump(),
        )
        return OperationHealthCheckResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to trigger health check: {exc}") from exc


@app.post(
    "/api/v1/system/operations/purge-topic",
    response_model=PurgeTopicResponse,
    responses={502: {"model": ErrorResponse}},
)
def system_operations_purge_topic(payload: PurgeTopicRequest, req: Request) -> PurgeTopicResponse:
    require_system_operations_access(req)
    try:
        result = post_json(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/ops/purge-topic",
            payload.model_dump(),
        )
        return PurgeTopicResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to purge topic: {exc}") from exc


@app.post(
    "/api/v1/system/operations/retry-dlq",
    response_model=RetryDlqResponse,
    responses={502: {"model": ErrorResponse}},
)
def system_operations_retry_dlq(payload: RetryDlqRequest, req: Request) -> RetryDlqResponse:
    require_system_operations_access(req)
    try:
        result = post_json(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/ops/retry-dlq",
            payload.model_dump(),
        )
        return RetryDlqResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to retry DLQ message: {exc}") from exc


@app.post(
    "/api/v1/system/operations/trim-topic",
    response_model=TrimTopicResponse,
    responses={502: {"model": ErrorResponse}},
)
def system_operations_trim_topic(payload: TrimTopicRequest, req: Request) -> TrimTopicResponse:
    require_system_operations_access(req)
    try:
        result = post_json(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/ops/trim-topic",
            payload.model_dump(),
        )
        return TrimTopicResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to trim topic: {exc}") from exc


@app.post(
    "/api/v1/system/operations/scan-sla",
    response_model=SlaScanResponse,
    responses={401: {"model": ErrorResponse}},
)
def system_operations_scan_sla(payload: SlaScanRequest, req: Request) -> SlaScanResponse:
    require_authenticated_read_access(req)
    return scan_and_enforce_work_order_sla(limit=payload.limit, operator=payload.operator)


@app.post(
    "/api/v1/system/operations/reconcile-campaign-status",
    responses={401: {"model": ErrorResponse}},
)
def system_operations_reconcile_campaign_status(req: Request, operator: str | None = None) -> dict[str, Any]:
    require_system_operations_access(req)
    return reconcile_campaign_statuses(operator=operator or "manual")


@app.get(
    "/api/v1/system/operations/sla-backlog",
    response_model=SlaBacklogResponse,
    responses={401: {"model": ErrorResponse}},
)
def system_operations_sla_backlog(
    req: Request,
    limit: int = 50,
    overdue_only: bool = True,
) -> SlaBacklogResponse:
    require_authenticated_read_access(req)
    limit = max(1, min(limit, 200))
    items, overdue_pending = list_sla_backlog_data(limit, overdue_only)
    return SlaBacklogResponse(items=items, total=len(items), overdue_pending=overdue_pending)


@app.get(
    "/api/v1/system/operations/redis-stats",
    response_model=RedisStats,
    responses={401: {"model": ErrorResponse}},
)
def get_redis_stats_endpoint(req: Request) -> RedisStats:
    require_authenticated_read_access(req)
    return get_redis_stats()


@app.get(
    "/api/v1/system/operations/audit-logs",
    response_model=OperationAuditResponse,
    responses={502: {"model": ErrorResponse}},
)
def system_operations_audit_logs(
    req: Request,
    page: int = 1,
    page_size: int = 20,
    operator: str | None = None,
    operation: str | None = None,
    result: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> OperationAuditResponse:
    require_authenticated_read_access(req)
    try:
        query_parts = [f"page={page}", f"page_size={page_size}"]
        if operator:
            query_parts.append(f"operator={parse.quote_plus(operator)}")
        if operation:
            query_parts.append(f"operation={parse.quote_plus(operation)}")
        if result:
            query_parts.append(f"result={parse.quote_plus(result)}")
        if from_ts:
            query_parts.append(f"from_ts={parse.quote_plus(from_ts)}")
        if to_ts:
            query_parts.append(f"to_ts={parse.quote_plus(to_ts)}")
        query = "&".join(query_parts)

        payload = get_json(f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/ops/audit-logs?{query}")
        return OperationAuditResponse(**payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch audit logs: {exc}") from exc


@app.get(
    "/api/v1/system/operations/audit-logs.csv",
    responses={502: {"model": ErrorResponse}},
)
def system_operations_audit_logs_csv(
    req: Request,
    operator: str | None = None,
    operation: str | None = None,
    result: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> Response:
    require_authenticated_read_access(req)
    try:
        query_parts: list[str] = []
        if operator:
            query_parts.append(f"operator={parse.quote_plus(operator)}")
        if operation:
            query_parts.append(f"operation={parse.quote_plus(operation)}")
        if result:
            query_parts.append(f"result={parse.quote_plus(result)}")
        if from_ts:
            query_parts.append(f"from_ts={parse.quote_plus(from_ts)}")
        if to_ts:
            query_parts.append(f"to_ts={parse.quote_plus(to_ts)}")

        suffix = f"?{'&'.join(query_parts)}" if query_parts else ""
        req = request.Request(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/ops/audit-logs.csv{suffix}",
            method="GET",
        )
        with request.urlopen(req, timeout=15) as remote:
            csv_body = remote.read().decode("utf-8")

        headers = {"Content-Disposition": 'attachment; filename="operation-audit-logs.csv"'}
        return Response(content=csv_body, media_type="text/csv", headers=headers)
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Unable to export audit logs CSV: {exc}") from exc


@app.post(
    "/api/v1/chatbot/audit-logs",
    response_model=ChatbotAuditRecord,
)
def write_chatbot_audit_log(payload: ChatbotAuditWriteRequest, req: Request) -> ChatbotAuditRecord:
    require_internal_api_key(req)
    validate_actor_role_or_400(payload.actor_role)

    try:
        timestamp = datetime.fromisoformat(payload.timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="timestamp must be ISO-8601") from exc

    record = ChatbotAuditRecord(**payload.model_dump())

    require_persistent_chat_audit()

    if persistence is not None:
        try:
            persistence.save_chatbot_audit_log(
                audit_id=record.audit_id,
                timestamp=timestamp,
                actor_id=record.actor_id,
                actor_role=record.actor_role,
                locale=record.locale,
                message=record.message,
                intent=record.intent,
                ok=record.ok,
                detail=record.detail,
                request_pending_action_type=record.request_pending_action_type,
                request_pending_campaign_id=record.request_pending_campaign_id,
                request_pending_reference_id=record.request_pending_reference_id,
                request_pending_review_id=record.request_pending_review_id,
                result_pending_action_type=record.result_pending_action_type,
                result_pending_campaign_id=record.result_pending_campaign_id,
                result_pending_reference_id=record.result_pending_reference_id,
                result_pending_review_id=record.result_pending_review_id,
            )
            return record
        except Exception as exc:
            if CHAT_AUDIT_REQUIRE_PERSISTENCE:
                raise HTTPException(status_code=503, detail=f"Chatbot audit persistence failed: {exc}") from exc

    chatbot_audit_logs.insert(0, record)
    if len(chatbot_audit_logs) > 500:
        chatbot_audit_logs.pop()
    return record


@app.post(
    "/api/v1/campaigns/{campaign_id}/references/attach-text",
    response_model=CampaignReferenceRecord,
    responses={404: {"model": ErrorResponse}},
)
def attach_campaign_reference_text(campaign_id: str, payload: CampaignReferenceAttachRequest, req: Request) -> CampaignReferenceRecord:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_trace_access(req, campaign)

    reference_id = f"ref_{uuid4().hex[:12]}"
    safe_name = os.path.basename(payload.file_name.strip() or f"{reference_id}.txt")
    if "." not in safe_name:
        safe_name = f"{safe_name}.txt"
    campaign_dir = os.path.join(CAMPAIGN_REFERENCES_DIR, campaign_id)
    os.makedirs(campaign_dir, exist_ok=True)
    stored_path = os.path.join(campaign_dir, f"{reference_id}.txt")
    with open(stored_path, "w", encoding="utf-8") as target:
        target.write(payload.content)

    file_size = os.path.getsize(stored_path)
    uploaded_at_dt = now_utc()
    uploaded_at = uploaded_at_dt.isoformat()
    base_url = str(req.base_url).rstrip("/")
    record = CampaignReferenceRecord(
        reference_id=reference_id,
        campaign_id=campaign_id,
        file_name=safe_name,
        file_type=payload.file_type or "text/plain",
        file_size=file_size,
        uploaded_at=uploaded_at,
        download_url=build_reference_download_url(base_url, campaign_id, reference_id),
    )
    if persistence is not None:
        persistence.save_campaign_reference(reference_id, campaign_id, safe_name, record.file_type, file_size, uploaded_at_dt, stored_path, payload.operator)
    else:
        campaign_references.setdefault(campaign_id, []).append(record)
        campaign_reference_files.setdefault(campaign_id, {})[reference_id] = stored_path
    append_trace_event(
        campaign_id=campaign_id,
        event_type="reference_uploaded",
        actor_id=payload.operator or "system",
        actor_role="operator",
        summary=f"Reference {safe_name} attached",
        payload={"reference_id": reference_id, "file_name": safe_name},
        source="manual",
        company_id=campaign.company_id,
    )
    return record


@app.get(
    "/api/v1/chatbot/audit-logs",
    response_model=ChatbotAuditListResponse,
)
def get_chatbot_audit_logs(
    req: Request,
    limit: int = 50,
    actor_id: str | None = None,
    actor_role: str | None = None,
    intent: str | None = None,
) -> ChatbotAuditListResponse:
    require_internal_api_key(req)
    limit = max(1, min(limit, 200))
    if actor_role is not None:
        validate_actor_role_or_400(actor_role)

    require_persistent_chat_audit()

    if persistence is not None:
        try:
            db_items = persistence.list_chatbot_audit_logs(
                limit=limit,
                actor_id=actor_id,
                actor_role=actor_role,
                intent=intent,
            )
            normalized = [normalize_chatbot_audit_record(item) for item in db_items]
            return ChatbotAuditListResponse(items=normalized, total=len(normalized))
        except Exception as exc:
            if CHAT_AUDIT_REQUIRE_PERSISTENCE:
                raise HTTPException(status_code=503, detail=f"Chatbot audit persistence failed: {exc}") from exc

    filtered = chatbot_audit_logs
    if actor_id:
        filtered = [item for item in filtered if item.actor_id == actor_id]
    if actor_role:
        filtered = [item for item in filtered if item.actor_role == actor_role]
    if intent:
        filtered = [item for item in filtered if item.intent == intent]
    items = filtered[:limit]
    return ChatbotAuditListResponse(items=items, total=len(items))


@app.get(
    "/api/v1/review/items",
    response_model=ReviewQueueResponse,
)
def list_review_queue(
    req: Request,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    campaign_id: str | None = None,
    run_id: str | None = None,
) -> ReviewQueueResponse:
    actor_company_id: str | None = None
    if is_platform_admin_request(req) or is_internal_api_key_request(req):
        actor_company_id = None
    else:
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
        if campaign_id:
            campaign = store.get_campaign(campaign_id)
            if campaign is None:
                raise HTTPException(status_code=404, detail="Campaign not found")
            if campaign.company_id != actor_company_id:
                raise HTTPException(status_code=403, detail="Not authorized")

    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    items = list_review_items_filtered(status=status, campaign_id=campaign_id, run_id=run_id)
    scoped_items: list[ReviewItem] = []
    for item in items:
        campaign = store.get_campaign(item.campaign_id)
        if campaign is None:
            continue
        if actor_company_id is not None and campaign.company_id != actor_company_id:
            continue
        scoped_items.append(item)
    items = scoped_items
    start = (page - 1) * page_size
    end = start + page_size
    return ReviewQueueResponse(items=items[start:end], total=len(items))


@app.post(
    "/api/v1/review/items/{review_id}/approve",
    response_model=ReviewActionResponse,
    responses={404: {"model": ErrorResponse}},
)
def approve_review_item(review_id: str, payload: ReviewActionRequest, req: Request) -> ReviewActionResponse:
    require_review_action_access(req)
    item = find_review_item(review_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    campaign_record = store.get_campaign(item.campaign_id)
    if campaign_record is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign_record)

    review_status_overrides[review_id] = "approved"
    operator = payload.operator or "system"
    if persistence is not None:
        try:
            persistence.update_review_item_status(review_id, "approved", operator)
            persistence.update_asset_validation_status(item.asset_id, "passed")
        except Exception:
            metrics.inc("db_write_fail_total")
    sync_approved_asset_to_knowledge_item(campaign_record, item, operator)
    finalize_campaign_workflow(
        item.campaign_id,
        run_id=item.run_id,
        tasks=store.get_tasks(item.campaign_id),
        operator=operator,
        reason="review_approved",
        notify_completed=True,
    )
    append_review_audit(
        action="approve",
        target=review_id,
        result="ok",
        operator=operator,
    )
    append_trace_event(
        campaign_id=item.campaign_id,
        event_type="review_approved",
        actor_id=operator,
        actor_role="operator",
        summary=f"Review {review_id} approved",
        payload={"review_id": review_id, "asset_id": item.asset_id, "score": item.score},
        source="review",
    )
    _notify_webhook(
        event_type="review_approved",
        campaign_id=item.campaign_id,
        payload={"review_id": review_id, "asset_id": item.asset_id, "score": item.score, "operator": operator},
        company_id=campaign_record.company_id if campaign_record else "",
    )

    return ReviewActionResponse(
        review_id=review_id,
        status="approved",
        detail="Review item approved.",
    )


@app.post(
    "/api/v1/review/items/{review_id}/reject",
    response_model=ReviewActionResponse,
    responses={404: {"model": ErrorResponse}},
)
def reject_review_item(review_id: str, payload: ReviewActionRequest, req: Request) -> ReviewActionResponse:
    require_review_action_access(req)
    item = find_review_item(review_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    campaign_record = store.get_campaign(item.campaign_id)
    if campaign_record is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign_record)

    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Reject reason is required")

    review_status_overrides[review_id] = "rejected"
    operator = payload.operator or "system"
    if persistence is not None:
        try:
            persistence.update_review_item_status(review_id, "rejected", operator, reason)
            persistence.update_asset_validation_status(item.asset_id, "failed")
        except Exception:
            metrics.inc("db_write_fail_total")
    finalize_campaign_workflow(
        item.campaign_id,
        run_id=item.run_id,
        tasks=store.get_tasks(item.campaign_id),
        operator=operator,
        reason="review_rejected",
    )
    append_review_audit(
        action="reject",
        target=review_id,
        result="ok",
        operator=operator,
        reason=reason,
    )
    append_trace_event(
        campaign_id=item.campaign_id,
        event_type="review_rejected",
        actor_id=operator,
        actor_role="operator",
        summary=f"Review {review_id} rejected",
        payload={"review_id": review_id, "asset_id": item.asset_id, "reason": reason},
        source="review",
    )
    _notify_webhook(
        event_type="review_rejected",
        campaign_id=item.campaign_id,
        payload={"review_id": review_id, "asset_id": item.asset_id, "reason": reason, "operator": operator},
        company_id=campaign_record.company_id if campaign_record else "",
    )

    return ReviewActionResponse(
        review_id=review_id,
        status="rejected",
        detail="Review item rejected.",
    )


WORKER_TYPE_TO_URL: dict[str, str] = {
    "copy": WORKER_COPY_URL,
    "image": WORKER_IMAGE_URL,
    "video": WORKER_VIDEO_URL,
    "ads": WORKER_ADS_URL,
}

TASK_TYPE_TO_ASSET_TYPE: dict[str, str] = {
    "copywriting": "copy",
    "image_generation": "image",
    "video_generation": "video",
    "ads_strategy": "ads",
}


# ── Webhook management ───────────────────────────────────────────────────────


@app.get(
    "/api/v1/webhooks",
    response_model=list[WebhookSubscription],
    responses={401: {"model": ErrorResponse}},
)
def list_webhooks(req: Request, company_id: str | None = None, active: bool | None = None) -> list[WebhookSubscription]:
    if not is_platform_admin_request(req):
        payload = require_jwt(req)
        company_id = payload.company_id or ""
    if persistence is None:
        return []
    try:
        rows = persistence.list_webhook_subscriptions(company_id=company_id, active=active)
        return [
            WebhookSubscription(
                sub_id=str(r["sub_id"]),
                company_id=str(r["company_id"]),
                url=str(r["url"]),
                secret=str(r["secret"]),
                events=list(r["events"]) if r["events"] else [],
                active=bool(r["active"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
    except Exception:
        return []


@app.post(
    "/api/v1/webhooks",
    response_model=WebhookSubscriptionResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def create_webhook(req: Request, payload_webhook: WebhookSubscriptionCreateRequest) -> WebhookSubscriptionResponse:
    if not is_platform_admin_request(req):
        payload_jwt = require_jwt(req)
        company_id = payload_jwt.company_id or ""
    else:
        company_id = (req.headers.get("x-company-id") or "").strip()
        if not company_id:
            raise HTTPException(status_code=400, detail="x-company-id header required for platform admin")

    import uuid
    sub_id = f"sub_{uuid.uuid4().hex[:16]}"
    if persistence is not None:
        try:
            persistence.upsert_webhook_subscription(
                sub_id=sub_id,
                company_id=company_id,
                url=payload_webhook.url,
                secret=payload_webhook.secret,
                events=payload_webhook.events,
                active=payload_webhook.active,
            )
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to create webhook subscription")

    return WebhookSubscriptionResponse(
        sub_id=sub_id,
        url=payload_webhook.url,
        events=payload_webhook.events,
        active=payload_webhook.active,
    )


@app.delete(
    "/api/v1/webhooks/{sub_id}",
    response_model=dict[str, bool],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_webhook(req: Request, sub_id: str) -> dict[str, bool]:
    if not is_platform_admin_request(req):
        require_jwt(req)
    if persistence is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    deleted = persistence.delete_webhook_subscription(sub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True}


@app.get(
    "/api/v1/webhooks/{sub_id}/logs",
    response_model=WebhookDeliveryLogResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_webhook_logs(req: Request, sub_id: str, limit: int = 50) -> WebhookDeliveryLogResponse:
    if not is_platform_admin_request(req):
        require_jwt(req)
    if persistence is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    try:
        rows = persistence.list_webhook_delivery_logs(sub_id, limit=limit)
        logs = [
            WebhookDeliveryLog(
                log_id=str(r["log_id"]),
                sub_id=str(r["sub_id"]),
                event_type=str(r["event_type"]),
                payload=r.get("payload", {}),
                response_code=r.get("response_code"),
                response_body=r.get("response_body"),
                attempt=int(r["attempt"]),
                delivered_at=r["delivered_at"],
                next_retry_at=r.get("next_retry_at"),
                status=str(r["status"]),
            )
            for r in rows
        ]
        return WebhookDeliveryLogResponse(sub_id=sub_id, logs=logs, total=len(logs))
    except Exception:
        return WebhookDeliveryLogResponse(sub_id=sub_id, logs=[], total=0)


class RetryWorkerTaskRequest(BaseModel):
    task_id: str


def _dispatch_worker_for_task(campaign: CampaignRecord, task: TaskRecord) -> tuple[list[AssetOutput], list[ValidationResult]]:
    return generate_outputs_via_workers(campaign.company_id, campaign.campaign_id, campaign, [task], run_id=latest_campaign_run_id(campaign.campaign_id))


@app.post(
    "/api/v1/internal/campaigns/{campaign_id}/tasks/retry",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
def retry_worker_task(campaign_id: str, payload: RetryWorkerTaskRequest, req: Request) -> dict[str, Any]:
    require_internal_api_key(req)

    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    task = next((item for item in store.get_tasks(campaign_id) if item.task_id == payload.task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    retried = task.model_copy(update={"status": "retrying"})
    existing_tasks = [retried if item.task_id == payload.task_id else item for item in store.get_tasks(campaign_id)]
    store.set_tasks(campaign_id, existing_tasks)

    try:
        assets, validations = _dispatch_worker_for_task(campaign, retried)
    except RuntimeError as exc:
        _notify_webhook(
            event_type="worker_retry_failed",
            campaign_id=campaign_id,
            payload={"task_id": payload.task_id, "task_type": task.task_type, "error": str(exc)},
            company_id=campaign.company_id,
        )
        append_trace_event(
            campaign_id=campaign_id,
            event_type="worker_retry_failed",
            actor_id="system",
            actor_role="system",
            summary=f"Worker retry failed for task {payload.task_id}",
            payload={"task_type": task.task_type, "error": str(exc)},
            source="workers",
            company_id=campaign.company_id,
        )
        raise HTTPException(status_code=502, detail=f"Worker retry failed: {exc}") from exc

    if assets and validations:
        save_assets_and_validations(assets, validations)

    patched = retried.model_copy(update={"status": "passed" if assets else "failed"})
    final_tasks = [patched if item.task_id == payload.task_id else item for item in store.get_tasks(campaign_id)]
    store.set_tasks(campaign_id, final_tasks)

    append_trace_event(
        campaign_id=campaign_id,
        event_type="worker_retry_succeeded",
        actor_id="system",
        actor_role="system",
        summary=f"Worker retry succeeded for task {payload.task_id}",
        payload={"task_type": task.task_type, "assets": len(assets), "validations": len(validations)},
        source="workers",
        company_id=campaign.company_id,
    )
    _notify_webhook(
        event_type="worker_retry_succeeded",
        campaign_id=campaign_id,
        payload={"task_id": payload.task_id, "task_type": task.task_type, "assets": len(assets)},
        company_id=campaign.company_id,
    )

    return {
        "campaign_id": campaign_id,
        "task_id": payload.task_id,
        "status": patched.status,
        "assets": len(assets),
        "validations": len(validations),
    }


@app.post(
    "/api/v1/internal/review/revision-request",
    responses={401: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
def submit_revision_request(payload: RevisionRequestPayload, req: Request) -> dict[str, str]:
    campaign = store.get_campaign(payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    actor_payload = require_campaign_access(req, campaign)
    if actor_payload is not None:
        require_any_permission(actor_payload, {"review:regenerate", "review:manage", "role:manage"})
    worker_url = WORKER_TYPE_TO_URL.get(payload.asset_type)
    if not worker_url:
        raise HTTPException(status_code=400, detail=f"Unknown asset type: {payload.asset_type}")

    revision_payload = {
        "task_id": payload.task_id,
        "campaign_id": payload.campaign_id,
        "prompt": getattr(payload, "prompt", ""),
        "reject_reason": payload.reject_reason,
    }

    if payload.asset_type == "copy":
        revision_payload["brand_context"] = {}
        revision_payload["variants"] = 3
    elif payload.asset_type == "image":
        revision_payload["sizes"] = getattr(payload, "sizes", ["1024x1024"])
        revision_payload["style_profile"] = {}
    elif payload.asset_type == "video":
        revision_payload["duration"] = getattr(payload, "duration", 6)
        revision_payload["aspect_ratio"] = getattr(payload, "aspect_ratio", "9:16")
    elif payload.asset_type == "ads":
        revision_payload["objective"] = getattr(payload, "objective", "")
        revision_payload["budget"] = getattr(payload, "budget", 0.0)
        revision_payload["platforms"] = getattr(payload, "platforms", [])

    try:
        post_json(f"{worker_url}/internal/workers/{payload.asset_type}/regenerate", revision_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Revision dispatch failed: {exc}") from exc

    append_trace_event(
        campaign_id=payload.campaign_id,
        event_type="review_revision_requested",
        actor_id=payload.operator or "admin",
        actor_role="admin",
        summary=f"Revision requested for asset {payload.asset_id}",
        payload={
            "review_id": payload.review_id,
            "asset_id": payload.asset_id,
            "asset_type": payload.asset_type,
            "reject_reason": payload.reject_reason,
        },
        source="review",
    )
    return {"status": "ok"}


@app.post("/api/v1/campaign-groups", response_model=CampaignGroup)
def create_campaign_group(payload: CampaignGroupCreateRequest, req: Request) -> CampaignGroup:
    company_id = ""
    actor_payload: JWTPayload | None = None
    if not is_internal_api_key_request(req) and not is_platform_admin_request(req):
        actor_payload = require_jwt(req)
        company_id = actor_payload.company_id or ""
    for campaign_id in payload.campaign_ids:
        campaign = store.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")
        if actor_payload is not None and campaign.company_id != company_id:
            raise HTTPException(status_code=403, detail="Not authorized to group one or more campaigns")
        if not company_id:
            company_id = campaign.company_id
    group_id = f"grp_{uuid4().hex[:8]}"
    group = CampaignGroup(
        company_id=company_id,
        group_id=group_id,
        name=payload.name,
        campaign_ids=payload.campaign_ids,
        created_at=now_utc().isoformat(),
    )
    campaign_groups[group_id] = group
    return group


@app.get("/api/v1/campaign-groups", response_model=CampaignGroupListResponse)
def list_campaign_groups(req: Request) -> CampaignGroupListResponse:
    if is_internal_api_key_request(req) or is_platform_admin_request(req):
        items = list(campaign_groups.values())
    else:
        payload = require_jwt(req)
        company_id = payload.company_id or ""
        items = [item for item in campaign_groups.values() if item.company_id == company_id]
    return CampaignGroupListResponse(items=items, total=len(items))


@app.get("/api/v1/campaign-groups/{group_id}", response_model=CampaignGroup)
def get_campaign_group(group_id: str, req: Request) -> CampaignGroup:
    if group_id not in campaign_groups:
        raise HTTPException(status_code=404, detail="Campaign group not found")
    group = campaign_groups[group_id]
    if not is_internal_api_key_request(req) and not is_platform_admin_request(req):
        payload = require_jwt(req)
        if group.company_id != (payload.company_id or ""):
            raise HTTPException(status_code=403, detail="Not authorized")
    return group


@app.get(
    "/api/v1/work-orders/cross-campaign",
    response_model=WorkOrderListResponse,
    responses={401: {"model": ErrorResponse}},
)
def get_cross_campaign_work_orders(
    req: Request,
    status: str | None = None,
    assignee: str | None = None,
    limit: int = 50,
) -> WorkOrderListResponse:
    actor_company_id: str | None = None
    if not is_internal_api_key_request(req) and not is_platform_admin_request(req):
        payload = require_jwt(req)
        actor_company_id = payload.company_id or ""
    limit = max(1, min(limit, 200))
    allowed_status = {"open", "in_progress", "blocked", "review_pending", "approved", "rejected", "done", "cancelled"}
    if status is not None and status not in allowed_status:
        raise HTTPException(status_code=400, detail="Invalid work order status")
    all_items: list[WorkOrderRecord] = []
    for campaign in store.list_campaigns():
        if actor_company_id is not None and campaign.company_id != actor_company_id:
            continue
        items = list_campaign_work_orders_data(campaign.campaign_id, limit, None, status, assignee)
        for item in items:
            enforced = enforce_work_order_sla(item)
            all_items.append(enforced)
    all_items = sorted(all_items, key=lambda item: parse_iso_datetime_or_400(item.updated_at, "updated_at"), reverse=True)[:limit]
    return WorkOrderListResponse(items=all_items, total=len(all_items), next_cursor=None)


class BatchCampaignRunRequest(BaseModel):
    campaign_ids: list[str]
    operator: str | None = None


class BatchCampaignRunResponse(BaseModel):
    results: list[dict[str, str]]


@app.post("/api/v1/campaigns/batch-run", response_model=BatchCampaignRunResponse)
def batch_run_campaigns(payload: BatchCampaignRunRequest, req: Request) -> BatchCampaignRunResponse:
    results: list[dict[str, str]] = []
    for campaign_id in payload.campaign_ids:
        try:
            result = run_campaign(req, campaign_id)
            results.append({"campaign_id": campaign_id, "status": result.status})
        except Exception as exc:
            results.append({"campaign_id": campaign_id, "status": "failed", "detail": str(exc)})
    return BatchCampaignRunResponse(results=results)


@app.get(
    "/api/v1/review/audit-logs",
    response_model=ReviewAuditResponse,
)
def list_review_audit_logs(req: Request, page: int = 1, page_size: int = 20) -> ReviewAuditResponse:
    require_authenticated_read_access(req)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    ordered = sorted(review_audit_logs, key=lambda item: item.timestamp, reverse=True)

    start = (page - 1) * page_size
    end = start + page_size
    return ReviewAuditResponse(items=ordered[start:end], total=len(ordered), page=page, page_size=page_size)


@app.post(
    "/api/v1/workflow/templates",
    response_model=WorkflowTemplateDetailResponse,
)
def create_workflow_template(req: Request, payload: WorkflowTemplateCreateRequest) -> WorkflowTemplateDetailResponse:
    resolve_workflow_actor(req)
    if payload.source_campaign_id:
        source_campaign = store.get_campaign(payload.source_campaign_id)
        if source_campaign is None:
            raise HTTPException(status_code=404, detail="Source campaign not found")
        require_campaign_access(req, source_campaign)
    template_tasks = resolve_template_tasks(payload.source_campaign_id, payload.tasks)
    if len(template_tasks) == 0:
        raise HTTPException(status_code=400, detail="Template tasks cannot be empty")

    created_at = now_utc().isoformat()
    template_id = f"wft_{uuid4().hex[:12]}"

    template = WorkflowTemplate(
        template_id=template_id,
        name=payload.name,
        description=payload.description,
        active_version=1,
        created_at=created_at,
    )
    version = WorkflowTemplateVersion(
        version=1,
        tasks=template_tasks,
        created_at=created_at,
    )

    workflow_templates[template_id] = template
    workflow_template_versions[template_id] = [version]
    persist_workflow_template(template_id)

    return WorkflowTemplateDetailResponse(template=template, versions=[version])


@app.get(
    "/api/v1/workflow/templates",
    response_model=WorkflowTemplateListResponse,
)
def list_workflow_templates(req: Request) -> WorkflowTemplateListResponse:
    resolve_workflow_actor(req)
    load_persisted_workflow_templates()
    items = sorted(workflow_templates.values(), key=lambda item: item.created_at, reverse=True)
    return WorkflowTemplateListResponse(items=items, total=len(items))


@app.get(
    "/api/v1/workflow/templates/{template_id}",
    response_model=WorkflowTemplateDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_workflow_template(req: Request, template_id: str) -> WorkflowTemplateDetailResponse:
    resolve_workflow_actor(req)
    template = get_template_or_404(template_id)
    versions = workflow_template_versions.get(template_id, [])
    return WorkflowTemplateDetailResponse(template=template, versions=versions)


@app.post(
    "/api/v1/workflow/templates/{template_id}/versions",
    response_model=WorkflowTemplateDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
def create_workflow_template_version(
    req: Request,
    template_id: str,
    payload: WorkflowTemplateVersionCreateRequest,
) -> WorkflowTemplateDetailResponse:
    resolve_workflow_actor(req)
    template = get_template_or_404(template_id)
    if len(payload.tasks) == 0:
        raise HTTPException(status_code=400, detail="Template tasks cannot be empty")

    versions = workflow_template_versions.get(template_id, [])
    next_version_no = (versions[-1].version if versions else 0) + 1
    new_version = WorkflowTemplateVersion(
        version=next_version_no,
        tasks=payload.tasks,
        created_at=now_utc().isoformat(),
    )
    versions.append(new_version)
    workflow_template_versions[template_id] = versions

    template.active_version = next_version_no
    workflow_templates[template_id] = template
    persist_workflow_template(template_id)

    return WorkflowTemplateDetailResponse(template=template, versions=versions)


@app.post(
    "/api/v1/workflow/templates/{template_id}/deactivate",
    response_model=WorkflowTemplateStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def deactivate_workflow_template(req: Request, template_id: str) -> WorkflowTemplateStatusResponse:
    _, payload = resolve_workflow_actor(req)
    if payload is not None:
        require_any_permission(payload, {"workflow:manage", "role:manage"})
    template = get_template_or_404(template_id)
    template.status = "inactive"
    workflow_templates[template_id] = template
    if persistence is not None:
        persistence.set_workflow_template_status(template_id, "inactive")
    return WorkflowTemplateStatusResponse(template_id=template_id, status="inactive")


@app.post(
    "/api/v1/workflow/templates/{template_id}/reactivate",
    response_model=WorkflowTemplateStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def reactivate_workflow_template(req: Request, template_id: str) -> WorkflowTemplateStatusResponse:
    _, payload = resolve_workflow_actor(req)
    if payload is not None:
        require_any_permission(payload, {"workflow:manage", "role:manage"})
    template = get_template_or_404(template_id)
    template.status = "active"
    workflow_templates[template_id] = template
    if persistence is not None:
        persistence.set_workflow_template_status(template_id, "active")
    return WorkflowTemplateStatusResponse(template_id=template_id, status="active")


@app.post(
    "/api/v1/workflow/templates/{template_id}/apply",
    response_model=WorkflowTemplateApplyResponse,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
def apply_workflow_template(req: Request, template_id: str, payload: WorkflowTemplateApplyRequest) -> WorkflowTemplateApplyResponse:
    actor_id, _ = resolve_workflow_actor(req)
    template = get_template_or_404(template_id)
    if template.status == "inactive":
        raise HTTPException(status_code=400, detail="Workflow template is inactive")
    campaign = store.get_campaign(payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign)

    versions = workflow_template_versions.get(template_id, [])
    active = next((version for version in versions if version.version == template.active_version), None)
    if active is None:
        raise HTTPException(status_code=404, detail="Workflow template version not found")

    task_id_map: dict[str, str] = {}
    normalized_tasks: list[dict[str, Any]] = []

    for task in active.tasks:
        task_id_map[task.task_type] = f"tsk_{task.task_type}_{uuid4().hex[:8]}"

    for task in active.tasks:
        normalized_tasks.append(
            {
                "task_id": task_id_map[task.task_type],
                "task_type": task.task_type,
                "depends_on": [task_id_map.get(dep, dep) for dep in task.depends_on],
                "priority": task.priority,
                "acceptance": task.acceptance,
            }
        )

    try:
        dispatch = post_json(
            f"{OPENCLAW_CONTROLLER_URL}/internal/orchestrator/dispatch",
            {
                "campaign_id": payload.campaign_id,
                "tasks": normalized_tasks,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to apply workflow template: {exc}") from exc

    dispatched_tasks = dispatch.get("tasks", [])
    normalized = [
        normalize_task_payload(task, payload.campaign_id)
        for task in dispatched_tasks
        if isinstance(task, dict)
    ]
    run_id, run_number = create_campaign_run_record(campaign, actor_id)
    store.set_tasks(payload.campaign_id, normalized)
    finalize_campaign_workflow(
        payload.campaign_id,
        run_id=run_id,
        run_number=run_number,
        tasks=normalized,
        operator=actor_id,
        reason="workflow_template_applied",
    )

    return WorkflowTemplateApplyResponse(
        template_id=template_id,
        campaign_id=payload.campaign_id,
        status="applied",
        dispatched_tasks=len(normalized_tasks),
    )


@app.post(
    "/api/v1/campaigns/{campaign_id}/references/upload",
    response_model=CampaignReferenceRecord,
    responses={404: {"model": ErrorResponse}},
)
def upload_campaign_reference(
    campaign_id: str,
    req: Request,
    file: UploadFile = File(...),
    operator: str | None = Form(default=None),
) -> CampaignReferenceRecord:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    reference_id = f"ref_{uuid4().hex[:12]}"
    original_name = os.path.basename(file.filename or "upload.bin")
    _, ext = os.path.splitext(original_name)

    campaign_dir = os.path.join(CAMPAIGN_REFERENCES_DIR, campaign_id)
    os.makedirs(campaign_dir, exist_ok=True)

    stored_name = f"{reference_id}{ext}"
    stored_path = os.path.join(campaign_dir, stored_name)

    with open(stored_path, "wb") as target:
        shutil.copyfileobj(file.file, target)

    file_size = os.path.getsize(stored_path)
    file_type = file.content_type or "application/octet-stream"
    try:
        validate_reference_upload(original_name, file_type, file_size)
    except HTTPException as exc:
        if os.path.exists(stored_path):
            os.remove(stored_path)
        raise exc

    uploaded_at_dt = now_utc()
    uploaded_at = uploaded_at_dt.isoformat()
    base_url = str(req.base_url).rstrip("/")
    download_url = build_reference_download_url(base_url, campaign_id, reference_id)

    record = CampaignReferenceRecord(
        reference_id=reference_id,
        campaign_id=campaign_id,
        file_name=original_name,
        file_type=file_type,
        file_size=file_size,
        uploaded_at=uploaded_at,
        download_url=download_url,
    )

    if persistence is not None:
        try:
            persistence.save_campaign_reference(
                reference_id=reference_id,
                campaign_id=campaign_id,
                file_name=original_name,
                file_type=file_type,
                file_size=file_size,
                uploaded_at=uploaded_at_dt,
                stored_path=stored_path,
                operator=operator,
            )
        except Exception:
            campaign_references.setdefault(campaign_id, []).append(record)
            campaign_references[campaign_id] = sorted(
                campaign_references[campaign_id],
                key=lambda item: item.uploaded_at,
                reverse=True,
            )
            campaign_reference_files.setdefault(campaign_id, {})[reference_id] = stored_path
    else:
        campaign_references.setdefault(campaign_id, []).append(record)
        campaign_references[campaign_id] = sorted(
            campaign_references[campaign_id],
            key=lambda item: item.uploaded_at,
            reverse=True,
        )
        campaign_reference_files.setdefault(campaign_id, {})[reference_id] = stored_path

    _ = operator  # placeholder for audit extension
    append_trace_event(
        campaign_id=campaign_id,
        event_type="reference_uploaded",
        actor_id=operator or "system",
        actor_role="operator" if operator else "system",
        summary=f"Reference {reference_id} uploaded",
        payload={
            "reference_id": reference_id,
            "file_name": original_name,
            "file_type": file_type,
            "file_size": file_size,
        },
        source="manual",
    )
    return record


@app.get(
    "/api/v1/campaigns/{campaign_id}/references",
    response_model=CampaignReferenceListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_campaign_references(campaign_id: str, req: Request) -> CampaignReferenceListResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if persistence is not None:
        db_items = persistence.list_campaign_references(campaign_id)
        base_url = str(req.base_url).rstrip("/")
        items = [to_reference_record(base_url, payload) for payload in db_items if reference_file_exists(payload)]
    else:
        path_map = campaign_reference_files.get(campaign_id, {})
        items = [item for item in campaign_references.get(campaign_id, []) if os.path.exists(path_map.get(item.reference_id, ""))]
    return CampaignReferenceListResponse(items=items, total=len(items))


@app.get(
    "/api/v1/campaigns/{campaign_id}/references/{reference_id}/download",
    responses={404: {"model": ErrorResponse}},
)
def download_campaign_reference(campaign_id: str, reference_id: str) -> FileResponse:
    payload = get_reference_payload_or_404(campaign_id, reference_id)
    stored_path = str(payload.get("stored_path"))
    record = CampaignReferenceRecord(
        reference_id=str(payload.get("reference_id")),
        campaign_id=str(payload.get("campaign_id")),
        file_name=str(payload.get("file_name")),
        file_type=str(payload.get("file_type")),
        file_size=int(payload.get("file_size") or 0),
        uploaded_at=str(payload.get("uploaded_at")),
        download_url="",
    )

    if not stored_path or not os.path.exists(stored_path):
        raise HTTPException(status_code=404, detail="Campaign reference file not found")

    return FileResponse(
        path=stored_path,
        media_type=record.file_type,
        filename=record.file_name,
    )


@app.delete(
    "/api/v1/campaigns/{campaign_id}/references/{reference_id}",
    response_model=CampaignReferenceDeleteResponse,
    responses={404: {"model": ErrorResponse}},
)
def delete_campaign_reference(campaign_id: str, reference_id: str, req: Request) -> CampaignReferenceDeleteResponse:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    require_campaign_access(req, campaign)

    if persistence is not None:
        stored_path = persistence.delete_campaign_reference(campaign_id, reference_id)
        if stored_path is None:
            raise HTTPException(status_code=404, detail="Campaign reference not found")
    else:
        refs = campaign_references.get(campaign_id, [])
        next_refs = [item for item in refs if item.reference_id != reference_id]
        if len(next_refs) == len(refs):
            raise HTTPException(status_code=404, detail="Campaign reference not found")
        campaign_references[campaign_id] = next_refs
        file_map = campaign_reference_files.get(campaign_id, {})
        stored_path = file_map.pop(reference_id, None)

    if stored_path and os.path.exists(stored_path):
        os.remove(stored_path)

    append_trace_event(
        campaign_id=campaign_id,
        event_type="reference_deleted",
        actor_id="system",
        actor_role="system",
        summary=f"Reference {reference_id} deleted",
        payload={"reference_id": reference_id},
        source="manual",
    )

    return CampaignReferenceDeleteResponse(reference_id=reference_id, deleted=True)


# ─── LLM Usage Internal Ingest ─────────────────────────────────────────────────

@app.post("/internal/usage/ingest", status_code=202)
def ingest_llm_usage(payload: LlmUsageIngestRequest, req: Request) -> dict[str, str]:
    require_internal_api_key(req)
    _write_llm_usage_to_redis({
        "company_id": payload.company_id,
        "model": payload.model,
        "provider": payload.provider,
        "prompt_tokens": payload.prompt_tokens,
        "completion_tokens": payload.completion_tokens,
        "request_count": payload.request_count,
        "created_at": now_utc().isoformat(),
    })
    return {"status": "accepted"}


# ─── Worker Result Ingest ────────────────────────────────────────────────────
# Workers report their results directly here instead of campaign_service re-calling workers.
# This eliminates the double-call pattern and ensures assets are saved immediately.

INTERNAL_API_KEY_HEADER = "X-Internal-Api-Key"


def require_internal_api_key_for_worker(req: Request) -> None:
    """Allow requests with valid internal API key (used by workers)."""
    key = req.headers.get(INTERNAL_API_KEY_HEADER, "")
    if not key:
        raise HTTPException(status_code=401, detail="Missing internal API key")
    expected = os.getenv("CHATBOT_INTERNAL_API_KEY", "").strip() or os.getenv("INTERNAL_API_KEY", "").strip()
    if not expected or key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal API key")


@app.post("/internal/workers/results", status_code=202)
def ingest_worker_result(payload: WorkerResultRequest, req: Request) -> dict[str, str]:
    """
    Workers call this endpoint to report their results directly.
    Saves assets, validations, and review items to the database.
    """
    require_internal_api_key_for_worker(req)

    task_type = payload.task_type
    result = payload.result
    now = now_utc()

    if task_type == "copywriting":
        return _save_copy_worker_result(result, now)
    elif task_type == "image_generation":
        return _save_image_worker_result(result, now)
    elif task_type == "video_generation":
        return _save_video_worker_result(result, now)
    elif task_type == "ads_strategy":
        return _save_ads_worker_result(result, now)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")


def _save_copy_worker_result(result: dict[str, Any], now: datetime) -> dict[str, str]:
    task_id = result.get("task_id", "")
    campaign_id = result.get("campaign_id", "")
    company_id = result.get("company_id", "")
    run_id = result.get("run_id", "")
    variants = result.get("variants", [])

    if not task_id or not campaign_id:
        raise HTTPException(status_code=400, detail="Missing task_id or campaign_id")

    assets: list[AssetOutput] = []
    validations: list[ValidationResult] = []

    for idx, variant in enumerate(variants):
        if not isinstance(variant, dict):
            continue
        body = variant.get("body")
        if not body:
            continue
        asset_id = f"ast_{uuid4().hex[:10]}"
        asset = AssetOutput(
            company_id=company_id,
            asset_id=asset_id,
            campaign_id=campaign_id,
            task_id=task_id,
            asset_type="copy",
            url=f"generated://copy/{campaign_id}/{task_id}/{idx+1}",
            metadata=apply_regeneration_metadata({"variant": variant, "task_type": "copywriting"}, result),
            validation_status="passed",
            created_at=now,
            run_id=run_id,
        )
        if is_displayable_asset(asset):
            assets.append(asset)
            append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

    if assets:
        save_assets_and_validations(assets, validations)

    return {"status": "accepted", "assets_saved": str(len(assets)), "asset_ids": ",".join(asset.asset_id for asset in assets)}


def _save_image_worker_result(result: dict[str, Any], now: datetime) -> dict[str, str]:
    task_id = result.get("task_id", "")
    campaign_id = result.get("campaign_id", "")
    company_id = result.get("company_id", "")
    run_id = result.get("run_id", "")
    image_assets = result.get("image_assets", [])

    if not task_id or not campaign_id:
        raise HTTPException(status_code=400, detail="Missing task_id or campaign_id")

    assets: list[AssetOutput] = []
    validations: list[ValidationResult] = []

    for item in image_assets:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("url", "")).strip()
        if not is_openable_asset_url(image_url):
            continue
        asset_id = f"ast_{uuid4().hex[:10]}"
        metadata = apply_regeneration_metadata({"size": item.get("size"), "task_type": "image_generation"}, result)
        try:
            image_url, cached_metadata = cache_generated_asset_url(
                company_id=company_id,
                campaign_id=campaign_id,
                asset_id=asset_id,
                asset_type="image",
                source_url=image_url,
            )
            metadata.update(cached_metadata)
        except Exception as exc:
            logger.warning(f"Failed to cache image worker result {asset_id}: {exc}")
        asset = AssetOutput(
            company_id=company_id,
            asset_id=asset_id,
            campaign_id=campaign_id,
            task_id=task_id,
            asset_type="image",
            url=image_url,
            metadata=metadata,
            validation_status="passed",
            created_at=now,
            run_id=run_id,
        )
        if is_displayable_asset(asset):
            assets.append(asset)
            append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

    if assets:
        save_assets_and_validations(assets, validations)

    return {"status": "accepted", "assets_saved": str(len(assets)), "asset_ids": ",".join(asset.asset_id for asset in assets)}


def _save_video_worker_result(result: dict[str, Any], now: datetime) -> dict[str, str]:
    task_id = result.get("task_id", "")
    campaign_id = result.get("campaign_id", "")
    company_id = result.get("company_id", "")
    run_id = result.get("run_id", "")
    video_url = str(result.get("video_url", "")).strip()
    thumbnail_url = str(result.get("thumbnail_url", "")).strip()

    if not task_id or not campaign_id:
        raise HTTPException(status_code=400, detail="Missing task_id or campaign_id")

    if not video_url:
        return {"status": "accepted", "assets_saved": "0", "asset_ids": ""}

    assets: list[AssetOutput] = []
    validations: list[ValidationResult] = []

    asset_id = f"ast_{uuid4().hex[:10]}"
    metadata = {
        "thumbnail_url": thumbnail_url,
        "task_type": "video_generation",
        "provider": result.get("provider", "MiniMax"),
        "model_name": result.get("model_name", ""),
        "fallback_reason": result.get("fallback_reason"),
        "fallback_detail": result.get("fallback_detail"),
    }
    metadata = apply_regeneration_metadata(metadata, result)
    if is_openable_asset_url(video_url):
        try:
            video_url, cached_metadata = cache_generated_asset_url(
                company_id=company_id,
                campaign_id=campaign_id,
                asset_id=asset_id,
                asset_type="video",
                source_url=video_url,
            )
            metadata.update(cached_metadata)
        except Exception as exc:
            logger.warning(f"Failed to cache video worker result {asset_id}: {exc}")
    asset = AssetOutput(
        company_id=company_id,
        asset_id=asset_id,
        campaign_id=campaign_id,
        task_id=task_id,
        asset_type="video",
        url=video_url,
        metadata=metadata,
        validation_status="passed",
        created_at=now,
        run_id=run_id,
    )
    if is_displayable_asset(asset):
        assets.append(asset)
        append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

    if assets:
        save_assets_and_validations(assets, validations)

    return {"status": "accepted", "assets_saved": str(len(assets)), "asset_ids": ",".join(asset.asset_id for asset in assets)}


def _save_ads_worker_result(result: dict[str, Any], now: datetime) -> dict[str, str]:
    task_id = result.get("task_id", "")
    campaign_id = result.get("campaign_id", "")
    company_id = result.get("company_id", "")
    run_id = result.get("run_id", "")
    ads_plan = result.get("ads_plan", {})

    if not task_id or not campaign_id:
        raise HTTPException(status_code=400, detail="Missing task_id or campaign_id")

    if not ads_plan:
        return {"status": "accepted", "assets_saved": "0", "asset_ids": ""}

    assets: list[AssetOutput] = []
    validations: list[ValidationResult] = []

    asset_id = f"ast_{uuid4().hex[:10]}"
    asset = AssetOutput(
        company_id=company_id,
        asset_id=asset_id,
        campaign_id=campaign_id,
        task_id=task_id,
        asset_type="ads",
        url=f"generated://ads/{campaign_id}/{task_id}",
        metadata=apply_regeneration_metadata({"ads_plan": ads_plan, "task_type": "ads_strategy"}, result),
        validation_status="passed",
        created_at=now,
        run_id=run_id,
    )
    if is_displayable_asset(asset):
        assets.append(asset)
        append_validation_for_asset(validations, company_id, campaign_id, asset_id, now, run_id=run_id)

    if assets:
        save_assets_and_validations(assets, validations)

    return {"status": "accepted", "assets_saved": str(len(assets)), "asset_ids": ",".join(asset.asset_id for asset in assets)}


# ─── LLM Usage Platform Endpoints ──────────────────────────────────────────────

@app.get(
    "/api/v1/platform/usage",
    response_model=LlmUsageListResponse,
    responses={401: {"model": ErrorResponse}},
)
def list_llm_usage(
    req: Request,
    company_id: str | None = None,
    model: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> LlmUsageListResponse:
    require_platform_admin(req)
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size
    from_dt = parse_iso_datetime_or_400(from_ts, "from_ts") if from_ts else None
    to_dt = parse_iso_datetime_or_400(to_ts, "to_ts") if to_ts else None

    if persistence is not None:
        rows = persistence.list_llm_usage(company_id, model, from_dt, to_dt, page_size, offset)
        total = persistence.count_llm_usage(company_id, model, from_dt, to_dt)
        pricing_list = persistence.list_llm_model_pricing(include_inactive=True)
        pricing_map = {str(p["model"]): p for p in pricing_list}
        items = [_enrich_usage_with_cost(row, pricing_map) for row in rows]
    else:
        items = []
        total = 0

    return LlmUsageListResponse(items=items, total=total, page=page, page_size=page_size)


@app.get(
    "/api/v1/platform/usage/summary",
    response_model=LlmUsageSummaryResponse,
    responses={401: {"model": ErrorResponse}},
)
def summarize_llm_usage(
    req: Request,
    company_id: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> LlmUsageSummaryResponse:
    require_platform_admin(req)
    from_dt = parse_iso_datetime_or_400(from_ts, "from_ts") if from_ts else None
    to_dt = parse_iso_datetime_or_400(to_ts, "to_ts") if to_ts else None

    if persistence is not None:
        summary = persistence.summarize_llm_usage(company_id, from_dt, to_dt)
        pricing_list = persistence.list_llm_model_pricing(include_inactive=True)
        pricing_map = {str(p["model"]): p for p in pricing_list}
        by_model = []
        total_cost = 0.0
        for m in summary.get("by_model", []):
            pricing = pricing_map.get(str(m.get("model", "")), {"prompt_price_per_m": 0, "completion_price_per_m": 0})
            cost = _compute_cost_usd(
                int(m.get("prompt_tokens", 0)),
                int(m.get("completion_tokens", 0)),
                pricing,
            )
            total_cost += cost
            by_model.append(LlmUsageSummaryByModel(
                model=str(m.get("model", "")),
                provider=str(m.get("provider", "")),
                prompt_tokens=int(m.get("prompt_tokens", 0)),
                completion_tokens=int(m.get("completion_tokens", 0)),
                request_count=int(m.get("request_count", 0)),
                cost_usd=round(cost, 6),
            ))
        return LlmUsageSummaryResponse(
            total_prompt_tokens=int(summary.get("total_prompt_tokens", 0)),
            total_completion_tokens=int(summary.get("total_completion_tokens", 0)),
            total_request_count=int(summary.get("total_request_count", 0)),
            total_cost_usd=round(total_cost, 6),
            by_model=by_model,
        )
    return LlmUsageSummaryResponse(
        total_prompt_tokens=0,
        total_completion_tokens=0,
        total_request_count=0,
        total_cost_usd=0.0,
        by_model=[],
    )


# ─── LLM Pricing CRUD ──────────────────────────────────────────────────────────

@app.get(
    "/api/v1/platform/usage/pricing",
    response_model=LlmPricingListResponse,
    responses={401: {"model": ErrorResponse}},
)
def list_llm_pricing(req: Request) -> LlmPricingListResponse:
    require_platform_admin(req)
    if persistence is not None:
        rows = persistence.list_llm_model_pricing(include_inactive=True)
        items = [
            LlmModelPricingRecord(
                pricing_id=str(r["pricing_id"]),
                model=str(r["model"]),
                provider=str(r["provider"]),
                prompt_price_per_m=float(r["prompt_price_per_m"]),
                completion_price_per_m=float(r["completion_price_per_m"]),
                is_active=bool(r["is_active"]),
                created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                updated_at=r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else str(r["updated_at"]),
            )
            for r in rows
        ]
        return LlmPricingListResponse(items=items, total=len(items))
    return LlmPricingListResponse(items=[], total=0)


@app.post(
    "/api/v1/platform/usage/pricing",
    response_model=LlmModelPricingRecord,
    responses={401: {"model": ErrorResponse}},
)
def upsert_llm_pricing(req: Request, payload: LlmPricingUpsertRequest) -> LlmModelPricingRecord:
    require_platform_admin(req)
    if persistence is not None:
        persistence.upsert_llm_model_pricing(
            model=payload.model,
            provider=payload.provider,
            prompt_price_per_m=payload.prompt_price_per_m,
            completion_price_per_m=payload.completion_price_per_m,
        )
        rows = persistence.list_llm_model_pricing(include_inactive=True)
        for r in rows:
            if str(r["model"]) == payload.model:
                return LlmModelPricingRecord(
                    pricing_id=str(r["pricing_id"]),
                    model=str(r["model"]),
                    provider=str(r["provider"]),
                    prompt_price_per_m=float(r["prompt_price_per_m"]),
                    completion_price_per_m=float(r["completion_price_per_m"]),
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                    updated_at=r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else str(r["updated_at"]),
                )
    raise HTTPException(status_code=500, detail="Failed to upsert pricing")


@app.delete(
    "/api/v1/platform/usage/pricing/{model}",
    status_code=204,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_llm_pricing(model: str, req: Request) -> None:
    require_platform_admin(req)
    if persistence is not None:
        persistence.soft_delete_llm_model_pricing(model)
    return None
