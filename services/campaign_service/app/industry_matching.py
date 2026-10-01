"""Industry normalization and deterministic knowledge-item matching."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_SEPARATORS = re.compile(r"[\s,/，、|_\-]+")
_INDUSTRY_GROUPS = (
    {"餐酒館", "餐酒吧", "酒吧", "bar", "bars", "cocktail", "cocktails", "調酒", "雞尾酒", "餐飲", "品酒", "夜生活", "餐廳", "restaurant", "restaurants"},
    {"咖啡店", "咖啡館", "咖啡", "cafe", "coffee", "coffee shop"},
    {"零售", "零售業", "retail"},
    {"汽車", "汽車業", "汽車保養", "automotive", "car"},
    {"旅遊", "旅遊業", "travel", "tourism"},
    {"美容", "美妝", "beauty", "cosmetics"},
)


def normalize_industry(value: str) -> str:
    """Return a stable, case-insensitive representation for industry labels."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return _SEPARATORS.sub(" ", normalized).strip()


def industry_terms(value: str) -> set[str]:
    """Expand an industry label into its canonical label and known synonyms."""
    normalized = normalize_industry(value)
    if not normalized:
        return set()
    terms = {normalized, *filter(None, normalized.split())}
    for group in _INDUSTRY_GROUPS:
        normalized_group = {normalize_industry(term) for term in group}
        if normalized in normalized_group or any(term in normalized for term in normalized_group):
            terms.update(normalized_group)
    return terms


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{_flatten(key)} {_flatten(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(item) for item in value)
    return normalize_industry(str(value or ""))


def match_industry_items(
    industry_category: str,
    product_name: str,
    objective: str,
    items: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Select relevant items, preferring exact category matches over synonyms."""
    if limit <= 0:
        return []
    category = normalize_industry(industry_category)
    terms = industry_terms(industry_category)
    if not category or not terms:
        return []
    product_terms = set(filter(None, _SEPARATORS.split(normalize_industry(product_name))))
    objective_terms = set(filter(None, _SEPARATORS.split(normalize_industry(objective))))
    ranked: list[tuple[int, int, int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        category_text = " ".join(
            _flatten(metadata.get(key))
            for key in ("category", "folder", "folder_name", "industry", "industry_category", "keywords")
        )
        searchable = _flatten(item)
        matched_terms = {term for term in terms if term and term in searchable}
        if not matched_terms:
            continue
        # An exact category anywhere in the searchable fields outranks synonyms.
        exact = int(category in searchable)
        relevance = len(matched_terms)
        relevance += sum(term in searchable for term in product_terms | objective_terms)
        ranked.append((exact, relevance, -index, {**item, "source_type": "industry_matched"}))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    return [item for _, _, _, item in ranked[:limit]]
