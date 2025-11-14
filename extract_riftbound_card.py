#!/usr/bin/env python3
"""
Riftbound Card Extractor (Vision LLM, standalone)

Usage:
    python extract_riftbound_card.py path/to/card.webp
    python extract_riftbound_card.py path/to/folder/ --out-dir output --model gpt-4o
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
# Utility: Convert Image → Data URL for OpenAI
# ============================================================

def image_to_data_url(image_path: Path) -> str:
    with Image.open(image_path) as img:
        img = img.convert("RGBA")
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


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
# OpenAI Extraction Logic
# ============================================================

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

    # Locate first message.output_text
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

    sanitized = strip_markdown_fences(json_text)

    try:
        data = json.loads(sanitized)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Model output was not valid JSON: {e}\nRaw output was:\n{json_text}"
        )

    return data


# ============================================================
# Filename Sanitizer
# ============================================================

def clean_filename(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    safe = "_".join(safe.strip().split())
    return safe or "card"


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

    for image_path in image_files:
        print(f"\nProcessing: {image_path}")
        print(f"Model: {args.model}")

        raw_data = extract_card_json(client, image_path, model=args.model)

        try:
            card = CardData.model_validate(raw_data)
        except ValidationError as e:
            print("Validation error:")
            print(e)
            print("Raw model output:")
            print(json.dumps(raw_data, indent=2, ensure_ascii=False))
            continue

        filename = clean_filename(card.name) + ".json"
        out_path = out_dir / filename

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(card.model_dump(), f, indent=2, ensure_ascii=False)

        print(f"Saved: {out_path}")

        if args.print:
            print(json.dumps(card.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
