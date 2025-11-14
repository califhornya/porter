"""Translate normalized card data into effect dictionaries."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .keyword_schemas import keyword_to_effects
from .utils import NormalizedCard, get_logger

LOGGER = get_logger(__name__)


class EffectParser:
    """Generate effect specs from keywords and rules text."""

    def parse(self, card: NormalizedCard) -> List[Dict[str, object]]:
        effects: List[Dict[str, object]] = []

        for keyword in card.keywords:
            mapped = keyword_to_effects(keyword)
            if mapped:
                effects.extend(mapped)
            else:
                LOGGER.debug("No effect mapping for keyword %s on %s", keyword, card.name)

        rules_effects = self._parse_rules_text(card.rules_text)
        if rules_effects:
            effects.extend(rules_effects)

        deduped: List[Dict[str, object]] = []
        seen = set()
        for effect in effects:
            key = tuple(sorted(effect.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(effect)
        return deduped

    # ------------------------------------------------------------------
    def _parse_rules_text(self, rules_text: Optional[str]) -> List[Dict[str, object]]:
        if not rules_text:
            return []

        effects: List[Dict[str, object]] = []
        for line in rules_text.splitlines():
            line = line.strip()
            if not line:
                continue
            damage_match = re.search(r"deal (\d+) damage", line, flags=re.IGNORECASE)
            if damage_match:
                effects.append(
                    {
                        "effect": "deal_damage",
                        "amount": int(damage_match.group(1)),
                        "target": "opponent",
                    }
                )
                continue
            heal_match = re.search(r"heal (\d+)", line, flags=re.IGNORECASE)
            if heal_match:
                effects.append({"effect": "heal", "amount": int(heal_match.group(1))})
                continue
            draw_match = re.search(r"draw (\d+)", line, flags=re.IGNORECASE)
            if draw_match:
                effects.append({"effect": "draw", "amount": int(draw_match.group(1))})
                continue

        return effects
