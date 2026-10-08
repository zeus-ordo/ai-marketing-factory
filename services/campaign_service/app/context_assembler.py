"""Deterministic, auditable assembly of campaign generation context."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
import hashlib
import json
from math import floor
import math
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .schemas import CampaignRecord
from .safe_attributes import validate_safe_attributes


IMAGE_REFERENCE_TOTAL_LIMIT = 12
MANDATORY_PACK_IMAGE_LIMIT = 6
USER_REFERENCE_IMAGE_LIMIT = 3
RAG_VISUAL_ANCHOR_LIMIT = 3


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
    image_reference_ids: tuple[str, ...] = ()
    image_reference_partitions: dict[str, tuple[str, ...]] = field(default_factory=dict)


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


def select_image_reference_partitions(
    items: list[ContextSourceItem],
    campaign_id: str,
    run_id: str,
) -> tuple[tuple[ContextSourceItem, ...], tuple[ContextSourceItem, ...], tuple[ContextSourceItem, ...]]:
    """Select the fixed visual partitions without allowing optional sources to consume slots."""
    mandatory = select_reference_pack_items(
        [item for item in items if item.metadata.get("selection_mode") == "mandatory"],
        campaign_id,
        run_id,
        total_limit=MANDATORY_PACK_IMAGE_LIMIT,
    )
    manual_types = {"campaign_reference", "user_selected", "immediate_upload"}

    def is_image(item: ContextSourceItem) -> bool:
        mime_type = str(
            item.metadata.get("mime_type")
            or item.metadata.get("file_type")
            or item.metadata.get("content_type")
            or ""
        )
        return mime_type.lower().startswith("image/")

    user = tuple(item for item in items if item.source_type in manual_types and is_image(item))[:USER_REFERENCE_IMAGE_LIMIT]
    occupied = {item.source_id for item in (*mandatory, *user)}
    remaining = max(0, IMAGE_REFERENCE_TOTAL_LIMIT - len(mandatory) - len(user))
    rag = tuple(
        item for item in select_visual_anchor_items(items, limit=min(RAG_VISUAL_ANCHOR_LIMIT, remaining))
        if item.source_id not in occupied
    )
    return mandatory, user, rag


def snapshot_image_reference_selection(snapshot: GenerationContextSnapshot) -> dict[str, Any] | None:
    """Read persisted image partitions, including metadata markers from legacy loads."""
    partitions = {
        str(key): [str(item_id) for item_id in value]
        for key, value in (snapshot.image_reference_partitions or {}).items()
    }
    if not partitions:
        for item in snapshot.items:
            partition = item.metadata.get("image_reference_partition")
            if item.metadata.get("image_reference_selected") is True and isinstance(partition, str):
                try:
                    position = int(item.metadata.get("image_reference_position", len(partitions.get(partition, ()))))
                except (TypeError, ValueError):
                    position = len(partitions.get(partition, ()))
                partitions.setdefault(partition, []).append((
                    position,
                    item.source_id,
                ))
        partitions = {
            key: [item_id for _, item_id in sorted(value)]
            for key, value in partitions.items()
        }
    ids = list(snapshot.image_reference_ids)
    if not ids:
        ids = [item_id for partition in partitions.values() for item_id in partition]
    if not ids:
        return None
    partition_limits = {"mandatory": MANDATORY_PACK_IMAGE_LIMIT, "user": USER_REFERENCE_IMAGE_LIMIT, "rag": RAG_VISUAL_ANCHOR_LIMIT}
    bounded_partitions: dict[str, list[str]] = {}
    partition_order = [*partition_limits, *(key for key in partitions if key not in partition_limits)]
    for key in partition_order:
        value = partitions.get(key, [])
        bounded_partitions[key] = list(value[:partition_limits.get(key, IMAGE_REFERENCE_TOTAL_LIMIT)])
    bounded_ids = [item_id for partition in bounded_partitions.values() for item_id in partition]
    bounded_ids.extend(item_id for item_id in ids if item_id not in bounded_ids)
    ids = list(dict.fromkeys(bounded_ids))[:IMAGE_REFERENCE_TOTAL_LIMIT]
    return {"selected_reference_ids": ids, "image_reference_partitions": bounded_partitions}


def build_regeneration_reference_metadata(
    snapshot: GenerationContextSnapshot,
    run_id: str | None = None,
    persisted_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the original image partitions without transient attachment data."""
    stored_selection = snapshot_image_reference_selection(snapshot)
    if persisted_selection is None:
        persisted_selection = stored_selection
    persisted_ids = persisted_selection.get("selected_reference_ids") if persisted_selection is not None else None
    persisted_partitions = persisted_selection.get("partitions") if persisted_selection is not None else None
    if not isinstance(persisted_ids, (list, tuple)) and isinstance(persisted_partitions, Mapping):
        persisted_ids = [
            entry.get("reference_id")
            for partition in (persisted_partitions.get("immutable"), persisted_partitions.get("adjustable"))
            if isinstance(partition, (list, tuple))
            for entry in partition
            if isinstance(entry, Mapping) and entry.get("selected") and entry.get("reference_id")
        ]
    if persisted_selection is not None and not isinstance(persisted_ids, (list, tuple)):
        persisted_ids = list(snapshot.selected_reference_ids) if snapshot.selected_reference_ids else []
    persisted_ids = [str(reference_id) for reference_id in (persisted_ids or []) if reference_id]
    if persisted_ids:
        selected_ids = set(persisted_ids)
        selected_items = tuple(
            item
            for reference_id in persisted_ids
            for item in snapshot.items
            if item.source_id == reference_id
            and str(item.metadata.get("mime_type") or item.metadata.get("file_type") or item.metadata.get("content_type") or "").lower().startswith("image/")
        )
        mandatory = tuple(item for item in selected_items if item.metadata.get("selection_mode") == "mandatory")
        user = tuple(item for item in selected_items if item.source_type in {"campaign_reference", "user_selected", "immediate_upload"})
        anchors = tuple(item for item in selected_items if item.source_type == "industry_attribute_rag")
    else:
        mandatory, user, anchors = select_image_reference_partitions(
            list(snapshot.items), snapshot.campaign_id, run_id or snapshot.run_id or ""
        )
        selected_ids = {item.source_id for item in (*mandatory, *user, *anchors)}
    image_items = [
        item for item in snapshot.items
        if str(
            item.metadata.get("mime_type")
            or item.metadata.get("file_type")
            or item.metadata.get("content_type")
            or ""
        ).lower().startswith("image/")
    ]

    def is_immutable(item: ContextSourceItem) -> bool:
        metadata = item.metadata
        role = str(metadata.get("pack_role") or metadata.get("role") or "").casefold()
        protected = metadata.get("immutable") is True or metadata.get("protected") is True
        return role in {"brand_identity", "product", "logo", "real_product"} or protected

    def safe_metadata_value(value: Any) -> Any:
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if not isinstance(value, str):
            return None
        normalized = value.casefold()
        if (
            value.startswith(("/", "\\"))
            or len(value) > 2 and value[1] == ":" and value[2:3] in {"/", "\\"}
            or normalized.startswith(("file:", "private:", "storage:", "data:"))
        ):
            return None
        return value

    def describe(item: ContextSourceItem) -> dict[str, Any]:
        metadata = item.metadata
        return {
            "reference_id": item.source_id,
            "source_type": item.source_type,
            "file_name": item.label,
            "mime_type": safe_metadata_value(metadata.get("mime_type") or metadata.get("file_type") or metadata.get("content_type")),
            "folder": safe_metadata_value(metadata.get("folder") or metadata.get("folder_name")),
            "reference_pack_id": safe_metadata_value(metadata.get("pack_id")),
            "pack_role": safe_metadata_value(metadata.get("pack_role")),
            "role": safe_metadata_value(metadata.get("role")),
            "analysis_version": safe_metadata_value(metadata.get("analysis_version")),
            "similarity": safe_metadata_value(metadata.get("score")),
            "selection_reason": safe_metadata_value(metadata.get("selection_reason")),
            "selected": item.source_id in selected_ids,
            "provenance": "immutable" if is_immutable(item) else "adjustable",
        }

    described = [describe(item) for item in image_items]
    described = [
        {key: value for key, value in item.items() if value is not None}
        for item in described
    ]
    immutable = [item for item in described if item["provenance"] == "immutable"]
    adjustable = [item for item in described if item["provenance"] == "adjustable"]
    if isinstance(persisted_partitions, Mapping):
        partition_keys = {
            "reference_id", "source_type", "file_name", "mime_type", "folder", "reference_pack_id",
            "pack_role", "role", "analysis_version", "similarity", "selection_reason", "selected", "provenance",
        }

        def safe_partition(item: Any) -> dict[str, Any] | None:
            if not isinstance(item, Mapping) or not item.get("reference_id"):
                return None
            safe_item = {
                key: (item[key] if key in {"selected", "provenance"} else safe_metadata_value(item.get(key)))
                for key in partition_keys
                if key in item
            }
            return {key: value for key, value in safe_item.items() if value is not None}

        immutable = [item for entry in persisted_partitions.get("immutable", ()) if (item := safe_partition(entry)) is not None]
        adjustable = [item for entry in persisted_partitions.get("adjustable", ()) if (item := safe_partition(entry)) is not None]
    return {
        "immutable": immutable,
        "adjustable": adjustable,
        "immutable_reference_ids": [item["reference_id"] for item in immutable],
        "adjustable_reference_ids": [item["reference_id"] for item in adjustable],
        "selected_reference_ids": persisted_ids or [item.source_id for item in (*mandatory, *user, *anchors)],
    }


def build_generation_reference_payload(
    snapshot: GenerationContextSnapshot,
    task_type: str,
) -> dict[str, Any]:
    """Build the serializable split between attributes and image references."""
    enriched = [item for item in snapshot.items if item.source_type == "industry_attribute_rag"]

    def safe_attributes(value: Any) -> dict[str, Any] | None:
        def thaw(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {str(key): thaw(child) for key, child in value.items()}
            if isinstance(value, (list, tuple)):
                return [thaw(child) for child in value]
            return value

        value = thaw(value)
        if not isinstance(value, dict):
            return None
        try:
            validated = validate_safe_attributes(value)
            return json.loads(json.dumps(validated, ensure_ascii=True, allow_nan=False))
        except (TypeError, ValueError, OverflowError):
            return None

    def provenance(item: ContextSourceItem) -> dict[str, Any]:
        metadata = dict(item.metadata)
        return {
            "source_item_id": item.source_id,
            "source_type": item.source_type,
            "analysis_version": metadata.get("analysis_version"),
            "similarity": metadata.get("score"),
            "selection_reason": metadata.get("selection_reason"),
            "sha256": metadata.get("sha256"),
            "role": metadata.get("role"),
        }

    attributes = []
    for item in enriched:
        metadata = dict(item.metadata)
        raw_values = metadata.get("attributes")
        values = safe_attributes(raw_values)
        if raw_values is None:
            values = safe_attributes({"text": item.text})
        if values is None:
            continue
        attributes.append({"source_item_id": item.source_id, "attributes": values, "provenance": provenance(item)})

    legacy = select_reference_pack_items(list(snapshot.items), snapshot.campaign_id, snapshot.run_id or "")
    legacy_references = [
        {
            "source_id": item.source_id,
            "source_type": item.source_type,
            "file_name": item.label,
            "mime_type": dict(item.metadata).get("mime_type") or dict(item.metadata).get("file_type"),
            "pack_id": dict(item.metadata).get("pack_id"),
            "pack_role": dict(item.metadata).get("pack_role"),
        }
        for item in legacy
    ]
    anchors = select_visual_anchor_items(enriched) if task_type == "image_generation" else ()
    visual_anchors = [
        {
            "source_id": item.source_id,
            "file_name": item.label,
            "mime_type": dict(item.metadata).get("mime_type") or dict(item.metadata).get("file_type"),
            "analysis_version": dict(item.metadata).get("analysis_version"),
            "similarity": dict(item.metadata).get("score"),
            "selection_reason": dict(item.metadata).get("selection_reason"),
            "sha256": dict(item.metadata).get("sha256"),
            "role": dict(item.metadata).get("role"),
        }
        for item in anchors
    ]
    return {"attributes": attributes, "visual_anchors": visual_anchors, "legacy_references": legacy_references}


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
    run_id: str | None = None,
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
    mandatory_images, user_images, rag_images = select_image_reference_partitions(items, campaign.campaign_id, run_id or "")
    image_partitions = {
        "mandatory": tuple(item.source_id for item in mandatory_images),
        "user": tuple(item.source_id for item in user_images),
        "rag": tuple(item.source_id for item in rag_images),
    }
    partition_by_id = {
        item_id: partition
        for partition, item_ids in image_partitions.items()
        for item_id in item_ids
    }
    image_reference_position = {
        item_id: position
        for position, item_id in enumerate(item_id for item_ids in image_partitions.values() for item_id in item_ids)
    }
    items = tuple(
        ContextSourceItem(
            item.source_type,
            item.source_id,
            item.label,
            item.text,
            {
                **dict(item.metadata),
                "image_reference_partition": partition_by_id[item.source_id],
                "image_reference_selected": True,
                "image_reference_position": image_reference_position[item.source_id],
            } if item.source_id in partition_by_id else dict(item.metadata),
            item.transient_stored_path,
        )
        for item in items
    )
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
        image_reference_ids=tuple(item_id for partition in image_partitions.values() for item_id in partition),
        image_reference_partitions=image_partitions,
    )
