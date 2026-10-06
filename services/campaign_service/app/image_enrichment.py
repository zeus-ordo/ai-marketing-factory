from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .schemas import ImageAnalysisRecord


IMAGE_ANALYSIS_VERSION = "image-rag-v1"
ImageAnalysisStatus = Literal["pending", "processing", "ready", "failed"]
EmbeddingStatus = Literal["pending", "processing", "ready", "failed"]


class SafeImageAttributes(BaseModel):
    """Structured, JSON-only image attributes safe to persist and expose."""

    values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def reject_private_or_binary_values(cls, values: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"stored_path", "private_path", "image_bytes", "base64", "bytes"}
        def walk(value: Any) -> None:
            if isinstance(value, bytes):
                raise ValueError("image attributes cannot contain private paths or binary data")
            if isinstance(value, dict):
                if any(str(key).casefold() in forbidden for key in value):
                    raise ValueError("image attributes cannot contain private paths or binary data")
                for child in value.values():
                    walk(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    walk(child)

        walk(values)
        return values


def validate_image_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    return SafeImageAttributes(values=attributes).values
