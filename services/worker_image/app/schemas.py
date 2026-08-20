from pydantic import BaseModel


class ImageRunRequest(BaseModel):
    task_id: str
    campaign_id: str
    prompt: str
    sizes: list[str]
    style_profile: dict[str, object] = {}
    lora_id: str | None = None


class ImageAsset(BaseModel):
    url: str
    size: str


class ImageRunResponse(BaseModel):
    task_id: str
    provider: str
    model_name: str
    image_assets: list[ImageAsset]


class RevisionRequest(BaseModel):
    task_id: str
    campaign_id: str
    prompt: str
    reject_reason: str
    sizes: list[str]
    style_profile: dict[str, object] = {}
    lora_id: str | None = None
