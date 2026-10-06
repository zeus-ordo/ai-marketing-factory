import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


_PRIVATE_PATH_VALUE = re.compile(r"^(?:[a-zA-Z]:[\\/]|[\\/]|file:|private:|storage:|\.\.?[\\/])")


class ReferenceImage(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

        forbidden_parts = ("private", "storage", "path", "base64", "binary", "bytes", "blob")

        def contains_unsafe(value: object) -> bool:
            if isinstance(value, dict):
                if any(
                    any(part in "".join(character for character in str(key).casefold() if character.isalnum()) for part in forbidden_parts)
                    for key in value
                ):
                    return True
                return any(contains_unsafe(nested) for nested in value.values())
            if isinstance(value, (list, tuple)):
                return any(contains_unsafe(nested) for nested in value)
            if isinstance(value, str):
                return bool(_PRIVATE_PATH_VALUE.match(value) or (value.casefold().startswith("data:") and ";base64," in value.casefold()))
            return False

        if contains_unsafe(self.attributes) or contains_unsafe(self.visual_anchors) or contains_unsafe(self.reference_audit):
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
