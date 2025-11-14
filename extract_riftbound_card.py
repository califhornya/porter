#!/usr/bin/env python3
"""
Riftbound Card Extractor (Vision LLM, standalone)

Usage:
    python extract_riftbound_card.py path/to/card.webp
    python extract_riftbound_card.py path/to/folder/ --out-dir output --model gpt-4o
"""

import argparse
import base64
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from PIL import Image


# ============================================================
# Pydantic Models (Canonical JSON Schema)
# ============================================================

class CardCost(BaseModel):
    energy: int = Field(..., ge=0)
    power: Optional[str] = None


class CardStats(BaseModel):
    might: Optional[int] = None
    damage: Optional[int] = None
    armor: Optional[int] = None


class CardEffect(BaseModel):
    effect: str
    params: Dict[str, Any] = Field(default_factory=dict)


class CardData(BaseModel):
    schema_version: int = Field(default=1, ge=1)

    name: str
    type: str
    domain: Optional[str] = None

    cost: CardCost
    stats: CardStats

    keywords: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    rules_text: str
    effects: List[CardEffect] = Field(default_factory=list)

    flavor: Optional[str] = None
    artist: Optional[str] = None
    card_id: Optional[str] = None


# ============================================================
# Utility: Convert Image → Data URL for OpenAI (with compression)
# ============================================================

def image_to_data_url(image_path: Path) -> str:
    """Return a JPEG-compressed data URL for the provided image."""

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        max_dim = 1024
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        payload = buffer.getvalue()

    b64 = base64.b64encode(payload).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


# ============================================================
# Output Sanitization: remove markdown fences
# ============================================================

def strip_markdown_fences(text: str) -> str:
    text = text.strip()

    # Remove opening ``` or ```json
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:].strip()

    # Remove trailing ```
    if text.endswith("```"):
        text = text[:-3].strip()

    return text


# ============================================================
# SYSTEM PROMPT (Strengthened)
# ============================================================

SYSTEM_PROMPT = """You are a strict Riftbound card data extractor.

You receive an image of a single Riftbound card. Your job:
- Read the card as accurately as possible.
- Interpret its mechanics.
- Output ONLY a single JSON object.
- Do NOT include explanation, markdown, comments, or backticks.
- Never wrap the JSON in code fences such as ``` or ```json.
- Output raw JSON only.

Important naming rules:
- Card names must match the printed name EXACTLY, including spaces, punctuation, and suffixes.
- Champion units can have multiple variants (for example: "Volibear Furious", "Volibear Imposing").
- You MUST include the full variant in the name field. Do NOT shorten these to only "Volibear" or any other truncated base name.
- Never normalize, translate, or simplify card names. Copy the printed title as-is.

JSON schema:

{
  "name": "string",
  "type": "UNIT | SPELL | GEAR | RUNE | LEGEND | BATTLEFIELD",
  "domain": "FURY | CALM | MIND | BODY | CHAOS | ORDER | null",

  "cost": { "energy": integer, "power": domain-string-or-null },
  "stats": { "might": int?, "damage": int?, "armor": int? },

  "keywords": [...],
  "tags": [...],

  "rules_text": "string",
  "effects": [ { "effect": "string", "params": {...} } ],

  "flavor": string|null,
  "artist": string|null,
  "card_id": string|null
}

Rules:
- If a field does not exist, output null or [] as appropriate.
- Output VALID JSON ONLY.
"""


# ============================================================
# Post-processing utilities
# ============================================================

KEYWORD_SYNONYMS = {
    "gear": "GEAR",
    "legend": "LEGEND",
    "unit": "UNIT",
    "rune": "RUNE",
    "spell": "SPELL",
}

TAG_SYNONYMS = {
    "equipment": "EQUIPMENT",
    "legend": "LEGEND",
    "unit": "UNIT",
}

EFFECT_SYNONYMS = {
    "score_point": "score_vp",
    "gain_point": "score_vp",
    "gain_vp": "score_vp",
    "deal dmg": "deal_damage",
    "deal_dmg": "deal_damage",
    "draw_card": "draw_cards",
}


def _canonicalize_terms(values: Iterable[str], synonyms: Dict[str, str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for raw in values:
        if not raw:
            continue
        canonical = raw.strip()
        if not canonical:
            continue
        canonical = canonical.upper()
        canonical = synonyms.get(canonical.lower(), canonical)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def normalize_effects(effects: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for effect in effects or []:
        if not isinstance(effect, dict):
            continue
        name = str(effect.get("effect", "")).strip()
        params = effect.get("params") or {}
        canonical = name.lower()
        canonical = EFFECT_SYNONYMS.get(canonical, canonical)
        normalized.append({"effect": canonical, "params": params})
    return normalized


def normalize_rules_text(text: Optional[str]) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


def post_process_card_data(data: Dict[str, Any]) -> Dict[str, Any]:
    processed = dict(data)
    processed.setdefault("schema_version", 1)

    processed["keywords"] = _canonicalize_terms(
        processed.get("keywords") or [], KEYWORD_SYNONYMS
    )
    processed["tags"] = _canonicalize_terms(processed.get("tags") or [], TAG_SYNONYMS)

    processed["effects"] = normalize_effects(processed.get("effects", []))

    processed["rules_text"] = normalize_rules_text(processed.get("rules_text"))

    return processed


# ============================================================
# OpenAI Extraction Logic
# ============================================================

def _extract_json_text(response: Any) -> str:
    try:
        output = response.output
        json_text = None
        for item in output:
            if item.type == "message":
                for c in item.content:
                    if c.type == "output_text":
                        json_text = c.text
                        break
            if json_text is not None:
                break
    except Exception:
        raise RuntimeError("Unexpected response structure from OpenAI Responses API.")

    if not json_text:
        raise RuntimeError("Model returned no text.")

    return strip_markdown_fences(json_text)


def attempt_repair_json(client: OpenAI, raw_text: str, *, model: str) -> Optional[Dict[str, Any]]:
    repair_prompt = (
        "The following text was intended to be a JSON object describing a Riftbound card. "
        "It may contain trailing commas or other mistakes. Return ONLY valid JSON for the same data.\n"
        f"Broken JSON:\n{raw_text}"
    )

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": "You fix invalid JSON without explanation."}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": repair_prompt}],
            },
        ],
        max_output_tokens=1024,
    )

    repaired_text = _extract_json_text(response)

    try:
        return json.loads(repaired_text)
    except json.JSONDecodeError:
        return None


def extract_card_json(client: OpenAI, image_path: Path, model: str) -> Dict[str, Any]:
    data_url = image_to_data_url(image_path)

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Extract the card data as JSON."},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        max_output_tokens=2048,
    )

    sanitized = _extract_json_text(response)

    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        repaired = attempt_repair_json(client, sanitized, model=model)
        if repaired is None:
            raise RuntimeError(
                "Model output was not valid JSON and automatic repair failed. "
                f"Raw output was:\n{sanitized}"
            )
        return repaired


# ============================================================
# Filename Sanitizer
# ============================================================

def clean_filename(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    safe = "_".join(safe.strip().split())
    return safe or "card"


def make_unique_filename(base_stem: str, used: set, out_dir: Path) -> str:
    """
    Ensure that the filename is unique within this run and does not overwrite existing files.

    base_stem: filename stem without extension (already sanitized).
    used: a set of stems used so far in this process.
    out_dir: output directory where JSON files are written.

    Returns the final filename (with .json extension).
    """
    stem = base_stem
    counter = 1
    filename = stem + ".json"
    out_path = out_dir / filename

    while filename in used or out_path.exists():
        counter += 1
        stem = f"{base_stem}_{counter}"
        filename = stem + ".json"
        out_path = out_dir / filename

    if filename != base_stem + ".json":
        print(f"WARNING: Duplicate card name detected, saving as: {filename}")

    used.add(filename)
    return filename


# ============================================================
# MAIN / CLI  (Batch Folder Support)
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Riftbound card JSON from image(s).")
    parser.add_argument("path", type=str, help="Path to an image or a folder.")
    parser.add_argument(
        "--out-dir",
        type=str,
        default="output",
        help="Directory where JSON files will be stored.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="OpenAI model to use.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print JSON to stdout after writing.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process cards without writing JSON files to disk.",
    )

    args = parser.parse_args()

    target_path = Path(args.path).expanduser().resolve()
    if not target_path.exists():
        raise SystemExit(f"Path not found: {target_path}")

    SUPPORTED = [".png", ".webp", ".jpg", ".jpeg"]

    if target_path.is_dir():
        image_files = [p for p in target_path.iterdir() if p.suffix.lower() in SUPPORTED]
        if not image_files:
            raise SystemExit("No supported image files found in directory.")
        image_files.sort()
    else:
        if target_path.suffix.lower() not in SUPPORTED:
            raise SystemExit(f"Unsupported file type: {target_path.suffix}")
        image_files = [target_path]

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=api_key)

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Track used filenames to avoid collisions in a single run
    used_filenames: set = set()

    for image_path in image_files:
        print(f"\nProcessing: {image_path}")
        print(f"Model: {args.model}")

        raw_data = extract_card_json(client, image_path, model=args.model)

        processed_data = post_process_card_data(raw_data)

        try:
            card = CardData.model_validate(processed_data)
        except ValidationError as e:
            print("Validation error:")
            print(e)
            print("Raw model output:")
            print(json.dumps(raw_data, indent=2, ensure_ascii=False))
            continue

        base_stem = clean_filename(card.name)
        filename = make_unique_filename(base_stem, used_filenames, out_dir)
        out_path = out_dir / filename

        card_payload = card.model_dump()

        if args.print or args.dry_run:
            print(json.dumps(card_payload, indent=2, ensure_ascii=False))

        if args.dry_run:
            print("Dry run enabled — file not written.")
            continue

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(card_payload, f, indent=2, ensure_ascii=False)

        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
