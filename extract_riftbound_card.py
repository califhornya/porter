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
    """Energy and power cost of a card.

    - energy: generic energy cost (top-left number).
    - power: single-domain power requirement, or null if:
        * the card has no power cost, or
        * the power cost uses multiple domains (e.g. Fury + Body).
      In those cases, use the card's `domains` list to know which domains it belongs to.
    """

    energy: int = Field(..., ge=0)
    power: Optional[str] = None


class CardStats(BaseModel):
    """Combat stats.

    - might: main attack stat for units, or null otherwise.
    - damage / armor: optional extra stats; null if not present.
    """

    might: Optional[int] = None
    damage: Optional[int] = None
    armor: Optional[int] = None


class CardEffect(BaseModel):
    """Normalized effect description."""

    effect: str
    params: Dict[str, Any] = Field(default_factory=dict)


class CardData(BaseModel):
    """Canonical representation of a single Riftbound card."""

    schema_version: int = Field(default=1, ge=1)

    # Name, including champion subtitle if present (e.g. "Volibear Furious").
    name: str

    # Card classification
    supertypes: List[str] = Field(default_factory=list)
    type: str  # UNIT | SPELL | GEAR | RUNE | LEGEND | BATTLEFIELD

    # Domain information
    domain: Optional[str] = None              # primary domain (or None)
    domains: List[str] = Field(default_factory=list)  # all domains (0–2, typically)

    # Cost and stats
    cost: CardCost
    stats: CardStats

    # Gameplay labels
    keywords: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # Rules text and effects
    rules_text: str
    effects: List[CardEffect] = Field(default_factory=list)

    # Extra info
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
    """Remove ``` or ```json fences if the model insists on adding them."""
    text = text.strip()

    # Remove opening ``` or ```json
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :].strip()

    # Remove trailing ```
    if text.endswith("```"):
        text = text[:-3].strip()

    return text


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """You are a strict Riftbound card data extractor.

You receive an image of a single Riftbound card. Your job:
- Read the card as accurately as possible.
- Interpret its mechanics using Riftbound's rules.
- Output ONLY a single JSON object.
- Do NOT include explanation, markdown, comments, or backticks.
- Never wrap the JSON in code fences such as ``` or ```json.
- Output raw JSON only.

JSON schema (all keys required unless marked optional):

{
  "name": "string",

  "supertypes": [ "CHAMPION", "SIGNATURE", "TOKEN", ... ],
  "type": "UNIT | SPELL | GEAR | RUNE | LEGEND | BATTLEFIELD",

  "domain": "FURY | CALM | MIND | BODY | CHAOS | ORDER | null",
  "domains": [ "FURY", "CALM", "MIND", "BODY", "CHAOS", "ORDER" ],

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
      "effect": "string",
      "params": { }
    }
  ],

  "flavor": "string or null",
  "artist": "string or null",
  "card_id": "string or null"
}

CARD TYPE RULES:

- Valid "type" values are:
  - "UNIT"
  - "SPELL"
  - "GEAR"
  - "RUNE"
  - "LEGEND"
  - "BATTLEFIELD"

- Champion Units:
  - Champion units are still type "UNIT".
  - They are NOT type "CHAMPION UNIT".
  - If the frame and banner show that this is a Champion Unit, then:
    - type = "UNIT"
    - "CHAMPION" MUST be included in "supertypes".
  - Do NOT ever output "CHAMPION UNIT" as a type.

- Legends:
  - Legend cards are type "LEGEND".
  - Legends are not units.
  - Legends do NOT get "CHAMPION" in "supertypes".
  - Both Legends and their corresponding Champion Units share the same Champion tag
    (for example "Volibear") which must appear in "tags".

SUPERTYPES:

- "supertypes" is a list of labels above the main type line, such as:
  - "CHAMPION" (for Champion Units only)
  - "SIGNATURE" (for cards marked as signature)
  - "TOKEN" (for token cards)
- If no supertype is visible, use [].

CHAMPION NAME + SUBTITLE (VERY IMPORTANT):

- Champion Units often show a main name and a subtitle line directly under it.
  Example: big name "Volibear" and smaller subtitle "FURIOUS" or "IMPOSING".
- If such a subtitle exists, the FULL card name MUST be:
  "MainName Subtitle"
  Examples:
    "Volibear Furious"
    "Volibear Imposing"
- Never output only the base name if a visible subtitle is present.
- The subtitle is part of the card name, not a keyword, not a tag, and not flavor.

DOMAIN RULES:

- Valid domains and their typical colors:
  - FURY  = red
  - CALM  = green
  - MIND  = blue
  - BODY  = orange
  - CHAOS = purple
  - ORDER = gold / yellow

- All non-token cards normally have one or two domains.
- Some special tokens or objects may have no domain.
- IMPORTANT: Cards can have up to two domains. Domains:[ ] with 3 values is invalid.

UNIT and LEGEND cards:
- Domains are indicated in the domain icons on the card frame (for example, in or near the cost gem).
- One color = one domain.
- Two distinct colors = two domains.
- Read the domain icons and map them to the appropriate domain names.

SPELL cards:
- Domains are determined by the color(s) of the power cost symbol(s).
- If there is a single-domain power cost, set "domain" to that domain and "domains" to [that domain].
- If there are multiple domain colors in the power cost, set:
  - "domain": null
  - "domains": [all domain names in visual order].

RUNE cards:
- A Rune is always exactly one domain.
- Its background and sigil coloring correspond to that domain.
- For Runes, set:
  - "domain" to that one domain,
  - "domains" to [that domain].

OUTPUT BOTH DOMAIN FIELDS CONSISTENTLY:

- If the card has exactly one domain:
  - "domain": that domain string
  - "domains": [that domain]
- If the card has multiple domains:
  - "domain": null
  - "domains": [all domain strings]
- If the card truly has no domains:
  - "domain": null
  - "domains": []

COST RULES:

- "cost.energy" is the numeric energy cost in the upper-left of the card (0 if none).
- "cost.power" is:
  - The single domain of power required, if there is exactly one domain in the power cost.
  - null if there is no power cost or if the power cost uses multiple domains.

STATS:

- "stats.might" is the card's Might value if present (usually for units).
- "stats.damage" and "stats.armor" are additional stats if present.
- If a stat is not on the frame, use null.

KEYWORDS:

- Extract and include all game keywords you see, such as:
  - "Accelerate"
  - "Assault 2" (include numbers as part of the string)
  - "Deathknell"
  - "Deflect 1"
  - "Ganking"
  - "Hidden"
  - "Legion"
  - "Reaction"
  - "Shield 3"
  - "Tank"
  - "Temporary"
  - "Vision"
- Also include any other bolded or named mechanics as plain strings.

TAGS:

- Use "tags" for:
  - Champion tags (e.g. "Volibear") that link Legends, Champion Units, and Signature cards.
  - Factions, regions, races, tribes, or other non-keyword labels on the type line.
- Make sure that:
  - A Legend and its Champion Unit both share the same Champion tag.
  - Do NOT put card type words (UNIT, SPELL, LEGEND, etc.) into "tags".

RULES TEXT:

- "rules_text" must be the full rules text as it appears on the card,
  normalized to a clean multi-line string.
- Preserve line breaks and bullet structure where possible.
- Use appropriate pronouns, following the printed text:
  - Units and Legends usually say "I", "me", "my".
  - Spells and Gear usually refer to "this" card.
  - Battlefields usually refer to "here".
- If some text is partially unreadable, infer the most likely rules text
  from the visible words and Riftbound conventions.

EFFECTS:

- "effects" is a normalized, structured representation of what the card does.
- Break complex rules text into a small list of effect objects.
- Each effect has:
  - "effect": a concise identifier such as "deal_damage", "buff", "draw_cards",
    "spawn_token", "score_vp", "move", "stun", "destroy", "custom", etc.
  - "params": a JSON object with enough information to re-apply the effect.
- If you are unsure how to structure the effect, set:
  - "effect": "custom"
  - "params": { "summary": "short English summary of what the card does" }

STRICT OUTPUT RULES:

- Output EXACTLY one JSON object.
- Do not output any text before or after the JSON.
- Do not output comments or markdown.
- Do not use trailing commas.
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

DOMAIN_SYNONYMS = {
    "fury": "FURY",
    "calm": "CALM",
    "mind": "MIND",
    "body": "BODY",
    "chaos": "CHAOS",
    "order": "ORDER",
}

SUPERTYPE_SYNONYMS = {
    "champion": "CHAMPION",
    "signature": "SIGNATURE",
    "token": "TOKEN",
}


def _canonicalize_terms(values: Iterable[str], synonyms: Dict[str, str]) -> List[str]:
    """Normalize a list of strings using a synonym map, uppercasing by default."""
    seen = set()
    result: List[str] = []
    for raw in values:
        if not raw:
            continue
        canonical = str(raw).strip()
        if not canonical:
            continue
        lower = canonical.lower()
        canonical = synonyms.get(lower, canonical.upper())
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def normalize_effects(effects: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize effect names and keep params as-is."""
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
    """Normalize line endings and trim empty lines."""
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)

# ============================================================
# Signature Spell Domain Override
# ============================================================

# Fill this as your card set expands
CHAMPION_DOMAINS = {
    "Teemo": ["MIND", "CHAOS"],
    "Garen": ["ORDER", "BODY"],
    "Darius": ["FURY", "ORDER"],
    "Ahri": ["MIND", "CALM"],
    "Kai'Sa": ["FURY", "MIND"],
    "Volibear": ["FURY", "BODY"],
    "Jinx": ["FURY", "CHAOS"],
    "Lee Sin": ["FURY", "CALM"],
    "Yasuo": ["CALM", "CHAOS"],
    "Irelia": ["CALM", "CHAOS"],
    "Leona": ["ORDER", "CALM"],
    "Viktor": ["MIND", "ORDER"],
    "Miss Fortune": ["FURY", "CHAOS"],
    "Sett": ["ORDER", "BODY"],
    "Annie": ["FURY", "CHAOS"],
    "Master Yi": ["BODY", "CALM"],
    "Lux": ["MIND", "ORDER"],
    "Draven": ["FURY", "CHAOS"],
    "Azir": ["ORDER", "CALM"],
    "Renata Glasc": ["MIND", "ORDER"],
    "Sivir": ["ORDER", "CHAOS"],
}


def detect_signature_spell(data: Dict[str, Any]) -> Optional[str]:
    """
    Detect if this is a Signature Spell and return champion name if present.
    Looks at rules_text and nameplate area that the model outputs.
    """
    text = (data.get("rules_text") or "").upper()
    tags = [t.upper() for t in data.get("tags", [])]

    # The card header extracted by the model usually writes:
    # "SIGNATURE SPELL · TEEMO" or similar
    if "SIGNATURE SPELL" in text:
        # Try to identify the champion name after the dot
        # Example the model often emits: "SIGNATURE SPELL · TEEMO"
        parts = text.split("SIGNATURE SPELL")
        if len(parts) > 1:
            tail = parts[1]
            # Extract the first uppercase token that matches a champion
            for champ in CHAMPION_DOMAINS:
                if champ.upper() in tail:
                    return champ

    return None


def override_signature_spell_domains(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    If this is a Signature Spell, override domains from champion metadata.
    """
    champ = detect_signature_spell(data)
    if not champ:
        return data

    domains = CHAMPION_DOMAINS.get(champ)
    if not domains:
        return data

    # Override
    data["domain"] = domains[0]
    data["domains"] = domains[:]  # list copy
    return data


def post_process_card_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply normalization and compatibility fixes on raw model output."""
    processed: Dict[str, Any] = dict(data)
    processed.setdefault("schema_version", 1)

    # Ensure expected fields exist
    processed.setdefault("supertypes", [])
    processed.setdefault("domains", [])
    processed.setdefault("keywords", [])
    processed.setdefault("tags", [])
    processed.setdefault("effects", [])
    processed.setdefault("rules_text", "")

    # Canonicalize list-like fields
    processed["keywords"] = _canonicalize_terms(
        processed.get("keywords") or [], KEYWORD_SYNONYMS
    )
    processed["tags"] = _canonicalize_terms(
        processed.get("tags") or [], TAG_SYNONYMS
    )

    # Normalize supertypes and domains
    processed["supertypes"] = _canonicalize_terms(
        processed.get("supertypes") or [], SUPERTYPE_SYNONYMS
    )

    domains_raw = processed.get("domains")
    if isinstance(domains_raw, str):
        domains_iterable: Iterable[str] = [domains_raw]
    elif isinstance(domains_raw, Iterable):
        domains_iterable = list(domains_raw)
    elif domains_raw:
        domains_iterable = [str(domains_raw)]
    else:
        domains_iterable = []

    processed["domains"] = _canonicalize_terms(domains_iterable, DOMAIN_SYNONYMS)

    # Harmonize primary domain with domains[]
    primary_raw = processed.get("domain")
    primary_list = (
        _canonicalize_terms([primary_raw], DOMAIN_SYNONYMS) if primary_raw else []
    )
    primary = primary_list[0] if primary_list else None

    if primary and primary not in processed["domains"]:
        processed["domains"].append(primary)

    domain_count = len(processed["domains"])
    if domain_count == 1:
        processed["domain"] = processed["domains"][0]
    else:
        processed["domain"] = None

    # Normalize effects
    processed["effects"] = normalize_effects(processed.get("effects", []))

    # Normalize rules text
    processed["rules_text"] = normalize_rules_text(processed.get("rules_text"))

    return processed


# ============================================================
# OpenAI Extraction Logic
# ============================================================

def _extract_json_text(response: Any) -> str:
    """Extract the text blob from a Responses API response."""
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
    except Exception as exc:  # defensive
        raise RuntimeError("Unexpected response structure from OpenAI Responses API.") from exc

    if not json_text:
        raise RuntimeError("Model returned no text.")

    return strip_markdown_fences(json_text)


def attempt_repair_json(client: OpenAI, raw_text: str, *, model: str) -> Optional[Dict[str, Any]]:
    """Second-pass: ask the model to fix invalid JSON."""
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
                "content": [
                    {"type": "input_text", "text": "You fix invalid JSON without explanation."}
                ],
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
    """Call the model on a single image and return the raw JSON dict."""
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
    """Turn a card name into a safe filename."""
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

    for image_path in image_files:
        print(f"\nProcessing: {image_path}")
        print(f"Model: {args.model}")

        try:
            raw_data = extract_card_json(client, image_path, model=args.model)
        except Exception as exc:
            print(f"  ERROR while processing {image_path.name}: {exc}")
            continue

        processed_data = post_process_card_data(raw_data)

        try:
            card = CardData.model_validate(processed_data)
        except ValidationError as e:
            print("  Validation error:")
            print(e)
            print("  Raw model output:")
            print(json.dumps(raw_data, indent=2, ensure_ascii=False))
            continue

        filename = clean_filename(card.name) + ".json"
        out_path = out_dir / filename

        card_payload = card.model_dump()

        if args.print or args.dry_run:
            print(json.dumps(card_payload, indent=2, ensure_ascii=False))

        if args.dry_run:
            print("  Dry run enabled — file not written.")
            continue

        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(card_payload, f, indent=2, ensure_ascii=False)
            print(f"  Saved: {out_path}")
        except OSError as exc:
            print(f"  ERROR while writing {out_path}: {exc}")


if __name__ == "__main__":
    main()
