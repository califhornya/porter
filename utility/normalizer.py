"""Normalize :class:`RawCardData` into :class:`NormalizedCard` objects."""
from __future__ import annotations

from typing import Dict, Optional

from .domain_icons import resolve_domain
from .utils import (
    NormalizedCard,
    PipelineError,
    RawCardData,
    coerce_int,
    dedupe_preserve_order,
    get_logger,
    normalize_keyword,
)

LOGGER = get_logger(__name__)

CATEGORY_ALIASES = {
    "unit": "UNIT",
    "spell": "SPELL",
    "gear": "GEAR",
    "rune": "RUNE",
    "legend": "LEGEND",
    "battlefield": "BATTLEFIELD",
}


class Normalizer:
    """Convert OCR output into simulator ready card dictionaries."""

    def normalize(self, raw: RawCardData) -> NormalizedCard:
        if not raw.name:
            raise PipelineError(f"Image {raw.source} is missing a name")

        category = self._resolve_category(raw.type_line)
        if category == "UNKNOWN":
            LOGGER.warning("Could not determine card category for %s", raw.source)

        domain = resolve_domain(raw.domain_icon)

        keywords = [normalize_keyword(k) for k in raw.keywords if k]
        keywords = dedupe_preserve_order(keywords)

        tags = [str(tag).strip() for tag in raw.tags if str(tag).strip()]
        tags = dedupe_preserve_order(tags)

        cost_power = self._parse_power_cost(raw.cost_power)

        normalized = NormalizedCard(
            name=raw.name.strip(),
            category=category,
            domain=domain,
            cost_energy=coerce_int(raw.cost_energy),
            cost_power=cost_power,
            might=coerce_int(raw.might),
            damage=coerce_int(raw.damage),
            keywords=keywords,
            tags=tags,
            rules_text=raw.rules_text.strip() if raw.rules_text else None,
            raw_rules_text=raw.rules_text,
        )
        return normalized

    # ------------------------------------------------------------------
    def _resolve_category(self, type_line: Optional[str]) -> str:
        if not type_line:
            return "UNKNOWN"
        lowered = type_line.lower()
        for alias, canonical in CATEGORY_ALIASES.items():
            if alias in lowered:
                return canonical
        return "UNKNOWN"

    # ------------------------------------------------------------------
    def _parse_power_cost(self, value: Optional[str]) -> Optional[Dict[str, object]]:
        if not value:
            return None
        parts = str(value).split()
        if len(parts) == 2 and parts[1].isdigit():
            return {"domain": parts[0].upper(), "amount": int(parts[1])}
        return None
