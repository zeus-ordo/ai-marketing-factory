from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field


class TargetAudience(BaseModel):
    age_range: str
    gender: str
    persona: str


class Deliverables(BaseModel):
    copy_variants: int = Field(default=3, ge=0)
    image_assets: int = Field(default=2, ge=0)
    short_video_assets: int = Field(default=1, ge=0)
    ads_strategy: int = Field(default=0, ge=0)


class CampaignBrief(BaseModel):
    campaign_name: str
    product_name: str
    description: str = ""
    industry_category: str = Field(default="", validation_alias=AliasChoices("industry_category", "industryCategory"))
    project_description: str = Field(default="", validation_alias=AliasChoices("project_description", "projectDescription"))
    objective: str
    target_audience: TargetAudience
    platforms: list[str]
    budget: float
    brand_tone: list[str]
    deliverables: Deliverables
    mandatory_elements: list[str] = []
    forbidden_elements: list[str] = []
    deadline: datetime
    workflow_template_id: str | None = None


class CampaignRecord(BaseModel):
    company_id: str
    campaign_id: str
    status: Literal["draft", "running", "completed", "failed"] = "running"
    created_at: datetime
    brief: CampaignBrief
    deleted_at: datetime | None = None


class TaskRecord(BaseModel):
    company_id: str
    task_id: str
    campaign_id: str
    task_type: Literal["copywriting", "image_generation", "video_generation", "ads_strategy"]
    status: Literal["pending", "planned", "running", "validating", "passed", "failed", "retrying"]
    priority: int
    depends_on: list[str] = []
    acceptance: list[str] = []


class CampaignCreatedResponse(BaseModel):
    campaign_id: str
    company_id: str
    status: str


class CampaignRunResponse(BaseModel):
    campaign_id: str
    status: str
    message: str
    run_id: str | None = None
    run_number: int | None = None


class CampaignRunSummary(BaseModel):
    run_id: str
    campaign_id: str
    run_number: int
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    triggered_by: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CampaignRunListResponse(BaseModel):
    campaign_id: str
    runs: list[CampaignRunSummary]
    total: int


class AssetVersion(BaseModel):
    version_id: str
    asset_id: str
    run_id: str
    version_number: int
    url: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AssetVersionListResponse(BaseModel):
    asset_id: str
    versions: list[AssetVersion]
    total: int


class WebhookSubscription(BaseModel):
    sub_id: str
    company_id: str
    url: str
    secret: str
    events: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryLog(BaseModel):
    log_id: str
    sub_id: str
    event_type: str
    payload: dict[str, Any]
    response_code: int | None
    response_body: str | None
    attempt: int
    delivered_at: datetime
    next_retry_at: datetime | None
    status: str


class WebhookSubscriptionCreateRequest(BaseModel):
    url: str
    secret: str = ""
    events: list[str]
    active: bool = True


class WebhookSubscriptionResponse(BaseModel):
    sub_id: str
    url: str
    events: list[str]
    active: bool


class WebhookDeliveryLogResponse(BaseModel):
    sub_id: str
    logs: list[WebhookDeliveryLog]
    total: int


class ErrorResponse(BaseModel):
    detail: str


class TaskListResponse(BaseModel):
    campaign_id: str
    tasks: list[TaskRecord]


class CampaignListResponse(BaseModel):
    items: list[CampaignRecord]
    total: int


class TaskPlanResponse(BaseModel):
    campaign_id: str
    plan_version: int
    summary: str
    tasks: list[dict[str, Any]]


class AssetOutput(BaseModel):
    company_id: str
    asset_id: str
    campaign_id: str
    task_id: str
    asset_type: Literal["copy", "image", "video", "ads"]
    url: str
    metadata: dict[str, Any] = {}
    validation_status: Literal["pending", "passed", "failed"] = "pending"
    created_at: datetime
    run_id: str | None = None


class ValidationResult(BaseModel):
    company_id: str
    validation_id: str
    campaign_id: str
    asset_id: str
    validator: str
    score: float
    result: Literal["passed", "failed"]
    reasons: list[str] = []
    created_at: datetime
    run_id: str | None = None


class ValidationResultListResponse(BaseModel):
    campaign_id: str
    items: list[ValidationResult]
    total: int


class FinalAssetBundle(BaseModel):
    campaign_id: str
    status: str
    copy_assets: list[dict[str, Any]]
    image_assets: list[dict[str, Any]]
    video_assets: list[dict[str, Any]]
    ads_strategy: dict[str, Any]


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


# Worker result schemas - workers report their results directly to campaign_service
class WorkerCopyResult(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    run_id: str
    variants: list[dict[str, Any]]  # [{title, body, cta}]


class WorkerImageResult(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    run_id: str
    image_assets: list[dict[str, Any]]  # [{url, size}]


class WorkerVideoResult(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    run_id: str
    video_url: str
    thumbnail_url: str
    provider: str = "MiniMax"
    model_name: str = ""
    fallback_reason: str | None = None
    fallback_detail: str | None = None


class WorkerAdsResult(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    run_id: str
    ads_plan: dict[str, Any]


class WorkerResultRequest(BaseModel):
    task_type: Literal["copywriting", "image_generation", "video_generation", "ads_strategy"]
    result: dict[str, Any]
