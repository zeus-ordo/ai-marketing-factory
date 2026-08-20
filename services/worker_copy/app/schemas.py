from pydantic import BaseModel, Field, field_validator


class CopyRunRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    prompt: str
    brand_context: dict[str, object] = Field(default_factory=dict)
    variants: int = 3

    @field_validator("variants")
    @classmethod
    def variants_bounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError("variants must be at least 1")
        if v > 10:
            raise ValueError("variants must be at most 10")
        return v


class CopyVariant(BaseModel):
    title: str
    body: str
    cta: str


class CopyRunResponse(BaseModel):
    task_id: str
    provider: str
    model_name: str
    variants: list[CopyVariant]


class RevisionRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    prompt: str
    reject_reason: str
    brand_context: dict[str, object] = Field(default_factory=dict)
    variants: int = 3

    @field_validator("variants")
    @classmethod
    def variants_bounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError("variants must be at least 1")
        if v > 10:
            raise ValueError("variants must be at most 10")
        return v
