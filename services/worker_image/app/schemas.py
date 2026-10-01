from pydantic import BaseModel


class ReferenceImage(BaseModel):
    reference_id: str
    file_name: str
    mime_type: str
    data: str
    folder: str = ""
    sha256: str | None = None


class ImageRunRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    prompt: str
    sizes: list[str]
    style_profile: dict[str, object] = {}
    lora_id: str | None = None
    provider: str | None = None
    model: str | None = None
    reference_images: list[ReferenceImage] = []
    reference_audit: dict[str, object] = {}


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
    company_id: str
    prompt: str
    reject_reason: str
    sizes: list[str]
    style_profile: dict[str, object] = {}
    lora_id: str | None = None
    provider: str | None = None
    model: str | None = None
