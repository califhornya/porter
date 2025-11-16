#!/usr/bin/env python3
"""Backward-compatible entry point for the Riftbound card extractor."""

from porter import (
    CardCost,
    CardStats,
    CardEffect,
    CardData,
    SYSTEM_PROMPT,
    attempt_repair_json,
    clean_filename,
    extract_card_json,
    image_to_data_url,
    main,
    normalize_effects,
    normalize_rules_text,
    post_process_card_data,
    strip_markdown_fences,
)

__all__ = [
    "CardCost",
    "CardStats",
    "CardEffect",
    "CardData",
    "SYSTEM_PROMPT",
    "attempt_repair_json",
    "clean_filename",
    "extract_card_json",
    "image_to_data_url",
    "main",
    "normalize_effects",
    "normalize_rules_text",
    "post_process_card_data",
    "strip_markdown_fences",
]


if __name__ == "__main__":
    main()
