from pydantic import BaseModel


class VideoRunRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    prompt: str
    duration: int = 6
    aspect_ratio: str = "9:16"


class VideoRunResponse(BaseModel):
    task_id: str
    provider: str
    model_name: str
    video_url: str
    thumbnail_url: str
    fallback_reason: str | None = None
    fallback_detail: str | None = None


class RevisionRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    prompt: str
    reject_reason: str
    duration: int = 6
    aspect_ratio: str = "9:16"
