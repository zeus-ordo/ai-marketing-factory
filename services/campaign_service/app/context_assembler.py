"""Deterministic, auditable assembly of campaign generation context."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import floor
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .schemas import CampaignRecord


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple, set)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ContextSourceItem:
    source_type: str
    source_id: str
    label: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))


@dataclass(frozen=True)
class GenerationContextSnapshot:
    generation_context_id: str
    campaign_id: str
    internal_token_count: int
    external_token_count: int
    internal_ratio: float
    external_ratio: float
    items: tuple[ContextSourceItem, ...]
    external_source_urls: tuple[str, ...]
    external_search_status: str = "not_requested"
    external_search_error: str | None = None
    task_id: str | None = None
    selected_reference_ids: tuple[str, ...] = ()
    matched_folder_names: tuple[str, ...] = ()


def estimate_tokens(text: str) -> int:
    """Estimate tokens consistently as ceil(UTF-8 bytes / 4), with one token minimum."""
    return max(1, (len(str(text).encode("utf-8")) + 3) // 4)


def select_image_reference_items(items: list[ContextSourceItem]) -> tuple[ContextSourceItem, ...]:
    """Select a stable, bounded set of image references for multimodal generation."""
    manual_types = {"campaign_reference", "user_selected", "immediate_upload"}
    def is_image(item: ContextSourceItem) -> bool:
        mime_type = str(item.metadata.get("mime_type") or item.metadata.get("file_type") or item.metadata.get("content_type") or "")
        return mime_type.lower().startswith("image/")
    manual = [item for item in items if item.source_type in manual_types and is_image(item)]
    industry = [item for item in items if item.source_type == "industry_matched" and is_image(item)]
    return tuple([*manual[:4], *industry[:2]])


def assemble_generation_context(
    campaign: CampaignRecord,
    selected_items: list[ContextSourceItem],
    industry_items: list[ContextSourceItem],
    external_items: list[ContextSourceItem],
    total_budget: int,
) -> GenerationContextSnapshot:
    internal_budget = max(0, floor(total_budget * 0.75))
    external_budget = max(0, total_budget - internal_budget)
    ranking = {"user_selected": 0, "immediate_upload": 0, "campaign_reference": 0, "industry_matched": 1, "external_web": 2}
    internal: list[ContextSourceItem] = []
    internal_used = 0
    for source in sorted([*selected_items, *industry_items], key=lambda item: ranking.get(item.source_type, 1)):
        tokens = estimate_tokens(source.text)
        if internal_used + tokens <= internal_budget:
            internal.append(source)
            internal_used += tokens
    external: list[ContextSourceItem] = []
    external_used = 0
    for source in external_items:
        tokens = estimate_tokens(source.text)
        if external_used + tokens <= external_budget:
            external.append(source)
            external_used += tokens
    items = [*internal, *external]
    total_used = internal_used + external_used
    return GenerationContextSnapshot(
        generation_context_id=f"gctx_{uuid4().hex[:12]}",
        campaign_id=campaign.campaign_id,
        internal_token_count=internal_used,
        external_token_count=external_used,
        internal_ratio=internal_used / total_used if total_used else 0.0,
        external_ratio=external_used / total_used if total_used else 0.0,
        items=tuple(items),
        external_source_urls=tuple(str(item.metadata.get("url") or "") for item in external if item.metadata.get("url")),
        selected_reference_ids=tuple(item.source_id for item in selected_items if item.source_type in {"user_selected", "immediate_upload", "campaign_reference"}),
        matched_folder_names=tuple(dict.fromkeys(str(item.metadata.get("folder") or item.metadata.get("folder_name") or "") for item in industry_items if item.metadata.get("folder") or item.metadata.get("folder_name"))),
    )
