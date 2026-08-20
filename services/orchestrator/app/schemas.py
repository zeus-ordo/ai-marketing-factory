from typing import Any, Literal

from pydantic import BaseModel, Field


class OrchestratorTask(BaseModel):
    task_id: str
    task_type: Literal["copywriting", "image_generation", "video_generation", "ads_strategy"]
    depends_on: list[str]
    priority: int
    acceptance: list[str]
    status: Literal["pending", "planned", "running", "validating", "passed", "failed", "retrying"] = "planned"
    company_id: str = ""
    run_id: str = ""
    worker_payload: dict[str, Any] = Field(default_factory=dict)


class DispatchRequest(BaseModel):
    campaign_id: str
    tasks: list[OrchestratorTask]


class DispatchResponse(BaseModel):
    campaign_id: str
    status: str
    tasks: list[OrchestratorTask]


class TaskCompleteRequest(BaseModel):
    campaign_id: str
    task_id: str
    result: Literal["passed", "failed"]


class TaskCompleteResponse(BaseModel):
    campaign_id: str
    task_id: str
    result: str
    next_tasks: list[OrchestratorTask]
    tasks: list[OrchestratorTask]


class TaskStateResponse(BaseModel):
    campaign_id: str
    tasks: list[OrchestratorTask]


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
