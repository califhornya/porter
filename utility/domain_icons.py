"""Mappings that translate icon hints into Riftbound domains."""
from __future__ import annotations

from typing import Dict

ICON_TO_DOMAIN: Dict[str, str] = {
    "order": "ORDER",
    "chaos": "CHAOS",
    "nature": "NATURE",
    "fury": "FURY",
    "shadow": "SHADOW",
    "light": "LIGHT",
    "tech": "TECH",
    "arcane": "ARCANE",
}


def resolve_domain(icon_hint: str | None) -> str | None:
    if not icon_hint:
        return None
    key = icon_hint.lower().strip()
    return ICON_TO_DOMAIN.get(key)
