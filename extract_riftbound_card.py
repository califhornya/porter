#!/usr/bin/env python3
"""
Riftbound Card Extractor (Vision LLM, standalone)

Usage:
    python extract_riftbound_card.py path/to/card.webp
    python extract_riftbound_card.py path/to/card.webp --out-dir output --model gpt-4o

Requirements:
    - Python 3.9+
    - pip install:
        openai
        pillow
        pydantic

Env:
    - OPENAI_API_KEY must be set in your environment.

This script:
    - Loads a .webp image of a Riftbound card
    - Sends it to a vision model (default: gpt-4o)
    - Asks for a strict JSON card description in the canonical schema
    - Validates it with Pydantic
    - Writes {clean-name}.json into the chosen output directory
"""

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from PIL import Image


# =========================
# JSON SCHEMA (CANONICAL)
# =========================

class CardCost(BaseModel):
    energy: int = Field(..., ge=0)
    power: Optional[str] = Field(
        None,
        description="Domain string or null: FURY|CALM|MIND|BODY|CHAOS|ORDER|null",
    )


class CardStats(BaseModel):
    might: Optional[int] = None
    damage: Optional[int] = None
    armor: Optional[int] = None


class CardEffect(BaseModel):
    effect: str = Field(..., description="Machine-readable effect identifier")
    params: Dict[str, Any] = Field(default_factory=dict)


class CardData(BaseModel):
    name: str
    type: str = Field(
        ...,
        description="UNIT | SPELL | GEAR | RUNE | LEGEND | BATTLEFIELD",
    )
    domain: Optional[str] = Field(
        None,
        description="FURY | CALM | MIND | BODY | CHAOS | ORDER | null",
    )

    cost: CardCost
    stats: CardStats

    keywords: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    rules_text: str

    effects: List[CardEffect] = Field(default_factory=list)

    flavor: Optional[str] = None
    artist: Optional[str] = None
    card_id: Optional[str] = None


# =========================
# IMAGE HANDLING
# =========================

def image_to_data_url(image_path: Path) -> str:
    """
    Load the image and return a data URL suitable for the Responses API.
    Converts to PNG in-memory for maximum compatibility.
    """
    with Image.open(image_path) as img:
        img = img.convert("RGBA")
        # Encode as PNG bytes
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


# =========================
# OPENAI / VISION CALL
# =========================

SYSTEM_PROMPT = """You are a strict Riftbound card data extractor.

You receive an image of a single Riftbound card. Your job:
- Read the card as accurately as possible.
- Interpret its mechanics.
- Output ONLY a single JSON object.
- Do NOT include any explanation, markdown, or extra text.

JSON schema (all keys required unless marked optional):

{
  "name": "string",
  "type": "UNIT | SPELL | GEAR | RUNE | LEGEND | BATTLEFIELD",
  "domain": "FURY | CALM | MIND | BODY | CHAOS | ORDER | null",

  "cost": {
    "energy": integer,
    "power": "FURY | CALM | MIND | BODY | CHAOS | ORDER | null"
  },

  "stats": {
    "might": integer or null,
    "damage": integer or null,
    "armor": integer or null
  },

  "keywords": [ "string", ... ],
  "tags": [ "string", ... ],

  "rules_text": "full human-readable rules text exactly as printed (or oracle-style if needed)",

  "effects": [
    {
      "effect": "string",       // short machine name like "deal_damage", "draw_cards", "buff_might", "deflect_tax"
      "params": { ... }         // key-value parameters (numbers, strings, booleans, small arrays)
    }
  ],

  "flavor": "optional string or null",
  "artist": "optional string or null",
  "card_id": "optional string or null"
}

Guidelines:

- If a field does NOT exist on the card, set it to null or empty where appropriate:
  - domain: null (for domainless cards, like some battlefields)
  - stats.might/damage/armor: null if not applicable
  - flavor/artist/card_id: null if unknown
  - keywords/tags/effects: [] if none are explicitly present.

- type:
  - Units are creatures that contest battlefields.
  - Spells are one-shot effects.
  - Gear is equipment / attachments.
  - Runes are special resource/enabler cards.
  - Legends are unique leader/hero cards.
  - Battlefields are locations used for scoring.

- domain:
  - Map any domain symbol or domain text to one of:
    FURY, CALM, MIND, BODY, CHAOS, ORDER.
  - If the card clearly has no domain, use null.

- cost.energy:
  - The numeric energy cost printed on the card.
  - If no numeric cost is printed, use 0.

- cost.power:
  - If the card requires power of a specific domain, set that domain string.
  - Otherwise, null.

- stats:
  - Units and Legends typically have might; read it from the card.
  - Some spells might have a fixed damage number; fill stats.damage if explicitly numeric.
  - If the card has armor/defense/armor-like stat, put it into stats.armor.
  - If a stat does not exist, use null, not 0.

- keywords:
  - Include mechanical keywords like GUARD, EVASIVE, DEFLECT, ENTRENCH, ACCELERATE, etc.
  - Uppercase or Title Case; be consistent across cards.

- tags:
  - Include tribes, classes, special labels, or legend tags if readable.
  - If unsure, you may leave tags empty.

- rules_text:
  - Include the full rules text, line breaks allowed.
  - Preserve the meaning even if you must correct small OCR errors.

- effects:
  - Interpret rules_text into structured machine-readable effects.
  - Choose concise effect names:
      - "deal_damage"
      - "buff_might"
      - "draw_cards"
      - "discard_cards"
      - "deflect_tax"
      - "rune_gain"
      - etc.
  - Put numeric quantities and targets into params, for example:
      { "effect": "deal_damage", "params": { "amount": 2, "target": "enemy_unit" } }

Output rules:
- Output JSON ONLY.
- NO comments.
- NO markdown.
- NO backticks.
- NO additional keys.
- Ensure the JSON is syntactically valid and parsable.
"""


def extract_card_json(
    client: OpenAI,
    image_path: Path,
    model: str = "gpt-4o",
) -> Dict[str, Any]:
    """
    Send the image to the OpenAI Responses API and return parsed JSON as dict.
    """
    data_url = image_to_data_url(image_path)

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": SYSTEM_PROMPT},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Extract the card data as JSON according to the schema.",
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                    },
                ],
            },
        ],
        max_output_tokens=2048,
    )

    # The Responses API returns a structured object. We need the text output part.
    # This assumes the model replies with a single text output containing only JSON.
    try:
        output = response.output
        # Find the first text item in the output
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
        # Fallback: older-style access or future changes
        # Try to stringify whole response and fail clearly
        raise RuntimeError("Unexpected response structure from OpenAI Responses API.")

    if not json_text:
        raise RuntimeError("No text content returned by the model.")

    # The model should have returned pure JSON
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model output was not valid JSON: {e}\nOutput:\n{json_text}")

    return data


# =========================
# MAIN / CLI
# =========================

def clean_filename(name: str) -> str:
    """Make a filesystem-safe filename from the card name."""
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    safe = "_".join(safe.strip().split())
    return safe or "card"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Riftbound card JSON from a .webp image using GPT-Vision.")
    parser.add_argument("image", type=str, help="Path to the card image (.webp, .png, .jpg, etc.)")
    parser.add_argument(
        "--out-dir",
        type=str,
        default="output",
        help="Directory where the JSON file will be written (default: ./output)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="OpenAI model name (default: gpt-4o)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print the validated JSON to stdout.",
    )

    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    print(f"Reading card from image: {image_path}")
    print(f"Using model: {args.model}")

    raw_data = extract_card_json(client, image_path, model=args.model)

    # Validate against our canonical schema
    try:
        card = CardData.model_validate(raw_data)
    except ValidationError as e:
        print("Model output failed validation against CardData schema.")
        print(e)
        print("Raw data returned by the model:")
        print(json.dumps(raw_data, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = clean_filename(card.name) + ".json"
    out_path = out_dir / filename

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(card.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"Saved card JSON to: {out_path}")

    if args.print:
        print()
        print(json.dumps(card.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
