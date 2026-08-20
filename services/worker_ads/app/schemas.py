from pydantic import BaseModel


class AdsRunRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    objective: str
    budget: float
    platforms: list[str]


class AdsRunResponse(BaseModel):
    task_id: str
    provider: str
    model_name: str
    ads_plan: dict[str, dict[str, float]]


class RevisionRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    objective: str
    budget: float
    platforms: list[str]
    reject_reason: str
