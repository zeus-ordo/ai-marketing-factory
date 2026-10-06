from pydantic import BaseModel, Field, model_validator


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
    reference_images: list[ReferenceImage] = Field(default_factory=list)
    reference_audit: dict[str, object] = Field(default_factory=dict)
    attributes: list[dict[str, object]] = Field(default_factory=list)
    visual_anchors: list[dict[str, object]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reference_contract(self) -> "ImageRunRequest":
        if len(self.reference_images) > 6:
            raise ValueError("at most six image parts are allowed")

        def contains_private_path(value: object) -> bool:
            if isinstance(value, dict):
                if any(str(key).casefold() in {"stored_path", "storage_key", "private_path"} for key in value):
                    return True
                return any(contains_private_path(nested) for nested in value.values())
            if isinstance(value, list):
                return any(contains_private_path(nested) for nested in value)
            return False

        if contains_private_path(self.attributes) or contains_private_path(self.visual_anchors) or contains_private_path(self.reference_audit):
            raise ValueError("private path fields are not allowed")
        return self


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
