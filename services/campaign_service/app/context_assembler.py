"""Deterministic, auditable assembly of campaign generation context."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import floor
from typing import Any
from uuid import uuid4

from .schemas import CampaignRecord


@dataclass(frozen=True)
class ContextSourceItem:
    source_type: str
    source_id: str
    label: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationContextSnapshot:
    generation_context_id: str
    campaign_id: str
    internal_token_count: int
    external_token_count: int
    internal_ratio: float
    external_ratio: float
    items: list[ContextSourceItem]
    external_source_urls: list[str]
    external_search_status: str = "not_requested"


def estimate_tokens(text: str) -> int:
    """Estimate tokens consistently as ceil(UTF-8 bytes / 4), with one token minimum."""
    return max(1, (len(str(text).encode("utf-8")) + 3) // 4)


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
        items=items,
        external_source_urls=[str(item.metadata.get("url") or "") for item in external if item.metadata.get("url")],
    )
