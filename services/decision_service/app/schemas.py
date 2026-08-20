from typing import Literal

from pydantic import BaseModel, Field


class CampaignBrief(BaseModel):
    campaign_name: str
    product_name: str
    description: str = ""
    objective: str
    target_audience: dict[str, str]
    platforms: list[str]
    budget: float
    brand_tone: list[str]
    deliverables: dict[str, int]
    mandatory_elements: list[str] = []
    forbidden_elements: list[str] = []
    deadline: str
    workflow_template_id: str | None = None


class DecisionPlanRequest(BaseModel):
    campaign_id: str
    brief: CampaignBrief


class DecisionTask(BaseModel):
    task_id: str
    task_type: Literal["copywriting", "image_generation", "video_generation", "ads_strategy"]
    depends_on: list[str] = []
    priority: int = Field(default=1, ge=1)
    acceptance: list[str] = []


class DecisionPlanResponse(BaseModel):
    campaign_id: str
    plan_version: int
    summary: str
    tasks: list[DecisionTask]
