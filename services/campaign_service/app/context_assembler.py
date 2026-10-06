"""Deterministic, auditable assembly of campaign generation context."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from math import floor
import math
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
    transient_stored_path: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        metadata = dict(self.metadata)
        stored_path = metadata.pop("stored_path", None)
        if self.transient_stored_path is None and isinstance(stored_path, str):
            object.__setattr__(self, "transient_stored_path", stored_path)
        object.__setattr__(self, "metadata", _freeze(metadata))


def sanitize_context_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep persisted/displayable context metadata free of local file paths."""
    return {key: value for key, value in metadata.items() if key != "stored_path"}


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
    run_id: str | None = None
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


def select_visual_anchor_items(
    items: list[ContextSourceItem],
    limit: int = 3,
) -> tuple[ContextSourceItem, ...]:
    """Select a stable, bounded set of ready enriched image references."""
    limit = min(3, max(0, limit))
    if limit == 0:
        return ()

    def is_image(item: ContextSourceItem) -> bool:
        mime_type = str(
            item.metadata.get("mime_type")
            or item.metadata.get("file_type")
            or item.metadata.get("content_type")
            or ""
        )
        return mime_type.lower().startswith("image/")

    def score(item: ContextSourceItem) -> float:
        try:
            value = float(item.metadata.get("score", 0))
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) else 0.0

    candidates = [
        item for item in items
        if item.source_type == "industry_attribute_rag" and is_image(item)
    ]
    return tuple(sorted(candidates, key=lambda item: (-score(item), item.source_id))[:limit])


def build_structured_attribute_text(attributes: dict[str, Any]) -> str:
    """Build deterministic, bounded prompt text from validated image attributes."""
    private_keys = {"stored_path", "storage_key", "binary_data", "base64", "image_data", "bytes"}
    max_field_length = 400
    max_total_length = 2400

    def safe_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): safe_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                if str(key).casefold() not in private_keys
            }
        if isinstance(value, (list, tuple)):
            return [safe_value(item) for item in value]
        return value

    lines: list[str] = []
    keys = sorted(attributes, key=str)
    if "source_item_id" in keys:
        keys.remove("source_item_id")
        keys.insert(0, "source_item_id")
    for key in keys:
        if key == "source_item_id":
            lines.append(f"source_item_id: {str(attributes[key])[:max_field_length]}")
            continue
        if str(key).casefold() in private_keys:
            continue
        value = json.dumps(safe_value(attributes[key]), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        lines.append(f"{key}: {value[:max_field_length]}")
    return "\n".join(lines)[:max_total_length]


def select_reference_pack_items(
    items: list[ContextSourceItem],
    campaign_id: str,
    run_id: str,
    total_limit: int = 6,
) -> tuple[ContextSourceItem, ...]:
    """Select Pack and campaign image sources with deterministic bounded priority."""
    def pack_id(item: ContextSourceItem) -> str:
        return str(item.metadata.get("pack_id") or "").strip()

    pack_items = [
        item for item in items
        if item.source_type in {"platform_default", "industry_default"} and pack_id(item)
    ]
    manual_types = {"campaign_reference", "user_selected", "immediate_upload"}
    manual = [item for item in items if item.source_type in manual_types]
    company = [item for item in items if item.source_type == "industry_matched"]

    def image(item: ContextSourceItem) -> bool:
        mime = str(item.metadata.get("mime_type") or item.metadata.get("file_type") or item.metadata.get("content_type") or "")
        return mime.lower().startswith("image/")

    pack_items = [item for item in pack_items if image(item)]
    manual = [item for item in manual if image(item)]
    company = [item for item in company if image(item)]

    def rotation(item: ContextSourceItem) -> str:
        key = f"{campaign_id}:{run_id}:{pack_id(item)}:{item.source_id}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def pack_rank(item: ContextSourceItem) -> tuple[int, int, int, int, str, str]:
        mode_rank = 0 if item.metadata.get("selection_mode") == "mandatory" else 1
        role_rank = {"brand_identity": 0, "product": 1}.get(str(item.metadata.get("pack_role") or ""), 2)
        scope_rank = 0 if item.source_type == "platform_default" else 1
        return (mode_rank, role_rank, scope_rank, -int(item.metadata.get("priority") or 0), rotation(item), item.source_id)

    selected: list[ContextSourceItem] = []
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    pack_counts: dict[str, int] = {}

    def add(item: ContextSourceItem) -> bool:
        if len(selected) >= max(0, total_limit) or item.source_id in seen_ids:
            return False
        item_pack_id = pack_id(item)
        if item_pack_id and pack_counts.get(item_pack_id, 0) >= pack_limits.get(item_pack_id, total_limit):
            return False
        sha = str(item.metadata.get("sha256") or "")
        if sha and sha in seen_hashes:
            return False
        selected.append(item)
        seen_ids.add(item.source_id)
        if item_pack_id:
            pack_counts[item_pack_id] = pack_counts.get(item_pack_id, 0) + 1
        if sha:
            seen_hashes.add(sha)
        return True

    packs: dict[str, list[ContextSourceItem]] = {}
    for candidate in pack_items:
        packs.setdefault(pack_id(candidate), []).append(candidate)
    ordered_packs = sorted(packs.values(), key=lambda group: pack_rank(group[0]))
    global_hashes: set[str] = set()
    unique_packs: dict[str, list[ContextSourceItem]] = {}
    for group in ordered_packs:
        unique_group: list[ContextSourceItem] = []
        for candidate in sorted(group, key=lambda item: (rotation(item), item.source_id)):
            sha = str(candidate.metadata.get("sha256") or "")
            if sha and sha in global_hashes:
                continue
            if sha:
                global_hashes.add(sha)
            unique_group.append(candidate)
        if unique_group:
            unique_packs[pack_id(unique_group[0])] = unique_group
    packs = unique_packs
    pack_items = [candidate for group in packs.values() for candidate in group]
    pack_limits = {
        pack_id: max(0, int(group[0].metadata.get("max_images") or len(group)))
        for pack_id, group in packs.items()
    }
    ordered_packs = sorted(packs.values(), key=lambda group: pack_rank(group[0]))
    for group in ordered_packs:
        if group[0].metadata.get("selection_mode") != "mandatory":
            continue
        group = sorted(group, key=lambda candidate: (rotation(candidate), candidate.source_id))
        unique_group: list[ContextSourceItem] = []
        group_hashes: set[str] = set()
        for candidate in group:
            sha = str(candidate.metadata.get("sha256") or "")
            if sha and sha in group_hashes:
                continue
            if sha:
                group_hashes.add(sha)
            unique_group.append(candidate)
        limit = max(0, int(group[0].metadata.get("max_images") or len(group)))
        if group[0].metadata.get("selection_mode") == "mandatory" and group[0].metadata.get("pack_role") in {"brand_identity", "product"}:
            limit = min(limit, 2)
        for candidate in unique_group[:limit]:
            add(candidate)

    # Manual campaign References outrank optional Pack and company images.
    for candidate in manual:
        if len(selected) >= total_limit:
            break
        add(candidate)
    for candidate in sorted(pack_items, key=pack_rank):
        if len(selected) >= total_limit:
            break
        if candidate.metadata.get("selection_mode") == "optional":
            candidate_pack_id = pack_id(candidate)
            if candidate_pack_id and pack_counts.get(candidate_pack_id, 0) >= pack_limits.get(candidate_pack_id, total_limit):
                continue
            add(candidate)
    for candidate in company:
        if len(selected) >= total_limit:
            break
        add(candidate)
    return tuple(selected)


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
