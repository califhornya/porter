"""Keyword definitions used to generate simple effect specs."""
from __future__ import annotations

from typing import Dict, List

KeywordEffect = Dict[str, object]

KEYWORD_EFFECTS: Dict[str, List[KeywordEffect]] = {
    "DEFLECT": [{"effect": "deflect", "amount": 1}],
    "CHARGE": [{"effect": "charge", "amount": 1}],
    "LEECH": [{"effect": "leech", "amount": 1}],
    "BARRAGE": [{"effect": "barrage", "amount": 1}],
    "HASTE": [{"effect": "haste"}],
    "SLOW": [{"effect": "slow"}],
}


def keyword_to_effects(keyword: str) -> List[KeywordEffect]:
    return KEYWORD_EFFECTS.get(keyword.upper(), [])
