from pydantic import BaseModel, Field, field_validator, model_validator


class CopyRunRequest(BaseModel):
    task_id: str
    campaign_id: str
    company_id: str
    prompt: str
    brand_context: dict[str, object] = Field(default_factory=dict)
    variants: int = 3
    provider: str | None = None
    model: str | None = None
    body_min_length: int = 80
    body_max_length: int = 200

    @field_validator("variants")
    @classmethod
    def variants_bounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError("variants must be at least 1")
        if v > 10:
            raise ValueError("variants must be at most 10")
        return v

    @model_validator(mode="after")
    def body_length_bounds(self):
        if self.body_min_length < 0:
            raise ValueError("body_min_length must be non-negative")
        if self.body_max_length < self.body_min_length:
            raise ValueError("body_max_length must be at least body_min_length")
        return self


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
    provider: str | None = None
    model: str | None = None
    body_min_length: int = 80
    body_max_length: int = 200

    @field_validator("variants")
    @classmethod
    def variants_bounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError("variants must be at least 1")
        if v > 10:
            raise ValueError("variants must be at most 10")
        return v

    @model_validator(mode="after")
    def body_length_bounds(self):
        if self.body_min_length < 0:
            raise ValueError("body_min_length must be non-negative")
        if self.body_max_length < self.body_min_length:
            raise ValueError("body_max_length must be at least body_min_length")
        return self
