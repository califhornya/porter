"""Porter Riftbound card extraction package."""

from .models import CardCost, CardStats, CardEffect, CardData, PowerCostItem
from .image_utils import DomainColorSample, image_to_data_url, infer_domains_from_image
from .prompts import SYSTEM_PROMPT
from .post_process import (
    CHAMPION_DOMAINS,
    TAG_SYNONYMS,
    KEYWORD_SYNONYMS,
    DOMAIN_SYNONYMS,
    SUPERTYPE_SYNONYMS,
    EFFECT_SYNONYMS,
    detect_signature_spell,
    normalize_effects,
    normalize_rules_text,
    strip_markdown_fences,
    override_signature_spell_domains,
    post_process_card_data,
)
from .client import attempt_repair_json, extract_card_json
from .cli import clean_filename, main

__all__ = [
    "CardCost",
    "CardStats",
    "CardEffect",
    "CardData",
    "PowerCostItem",
    "DomainColorSample",
    "image_to_data_url",
    "infer_domains_from_image",
    "SYSTEM_PROMPT",
    "CHAMPION_DOMAINS",
    "TAG_SYNONYMS",
    "KEYWORD_SYNONYMS",
    "DOMAIN_SYNONYMS",
    "SUPERTYPE_SYNONYMS",
    "EFFECT_SYNONYMS",
    "detect_signature_spell",
    "normalize_effects",
    "normalize_rules_text",
    "strip_markdown_fences",
    "override_signature_spell_domains",
    "post_process_card_data",
    "attempt_repair_json",
    "extract_card_json",
    "clean_filename",
    "main",
]
