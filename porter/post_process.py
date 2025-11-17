from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .image_utils import DomainColorSample, infer_domains_from_image


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

    if "SIGNATURE" in tags:
        for champ in CHAMPION_DOMAINS:
            if champ.upper() in tags:
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

    data["domain"] = domains[0]
    data["domains"] = domains[:]  # list copy
    return data


def override_champion_domains(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    If the card references a champion by name, enforce canonical domains.
    """
    tags_upper = {str(tag).upper() for tag in data.get("tags", []) if tag}
    name_upper = str(data.get("name") or "").upper()

    champ = None
    for champ_name in CHAMPION_DOMAINS:
        champ_upper = champ_name.upper()
        if champ_upper in tags_upper or champ_upper in name_upper:
            champ = champ_name
            break

    if not champ:
        return data

    domains = CHAMPION_DOMAINS.get(champ)
    if not domains:
        return data

    data["domain"] = domains[0]
    data["domains"] = domains[:]  # list copy
    return data


def _apply_spell_power_domains(processed: Dict[str, Any]) -> Dict[str, Any]:
    """For spells, derive domains directly from power cost order."""

    card_type = str(processed.get("type") or "").strip().upper()
    if card_type != "SPELL":
        return processed

    power_items = processed.get("cost", {}).get("power") or []
    if not isinstance(power_items, Iterable):
        return processed

    domains_from_power = []
    for item in power_items:
        domain = item.get("domain") if isinstance(item, dict) else None
        if domain:
            domains_from_power.append(domain)

    domains_from_power = _canonicalize_terms(domains_from_power, DOMAIN_SYNONYMS)
    if not domains_from_power:
        return processed

    processed["domains"] = domains_from_power
    processed["domain"] = domains_from_power[0] if len(domains_from_power) == 1 else None
    return processed


def _apply_domain_color_hint(
    processed: Dict[str, Any], color_hint: Optional[DomainColorSample]
) -> Dict[str, Any]:
    """Use a sampled color hint to override obvious domain mistakes."""

    if not color_hint or color_hint.confidence < 0.6 or not color_hint.domains:
        return processed

    power_items = processed.get("cost", {}).get("power", []) or []
    existing_domains = processed.get("domains") or []
    if power_items or existing_domains or processed.get("domain"):
        # When the model already provided power icons or domain info, treat the
        # color hint as advisory and leave the structured data untouched.
        return processed

    inferred = _canonicalize_terms(color_hint.domains, DOMAIN_SYNONYMS)
    if not inferred:
        return processed

    power_domains = [
        item.get("domain") for item in power_items if isinstance(item, dict) and item.get("domain")
    ]

    # Build a replacement power list, preserving total amount if the domain matches.
    replacement_power: List[Dict[str, Any]] = []
    if len(inferred) == 1:
        total_amount = 0
        for item in power_items:
            if isinstance(item, dict) and item.get("domain") == inferred[0]:
                try:
                    total_amount += int(item.get("amount", 0))
                except (TypeError, ValueError):
                    continue
        replacement_power = [
            {"domain": inferred[0], "amount": total_amount or 1},
        ]
    else:
        replacement_power = [{"domain": domain, "amount": 1} for domain in inferred]

    mismatch = set(power_domains) != set(inferred[: len(power_domains)])
    if mismatch or not power_domains or color_hint.confidence >= 0.8:
        processed.setdefault("cost", {})["power"] = replacement_power

    processed["domains"] = inferred
    processed["domain"] = inferred[0] if len(inferred) == 1 else None
    return processed


def post_process_card_data(
    data: Dict[str, Any], image_path: Optional[Path] = None
) -> Dict[str, Any]:
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

    cost_raw = processed.get("cost") or {}
    if not isinstance(cost_raw, dict):
        cost_raw = {}

    raw_energy = cost_raw.get("energy")
    try:
        energy = int(raw_energy) if raw_energy is not None else None
    except (TypeError, ValueError):
        energy = None

    power_raw = cost_raw.get("power", [])
    if power_raw is None:
        power_iterable = []
    elif isinstance(power_raw, list):
        power_iterable = power_raw
    else:
        power_iterable = [power_raw]

    power_items: List[Dict[str, Any]] = []
    for entry in power_iterable:
        if isinstance(entry, dict):
            domain_raw = entry.get("domain")
            amount_raw = entry.get("amount", 1)
        else:
            domain_raw = entry
            amount_raw = 1

        domains = (
            _canonicalize_terms([domain_raw], DOMAIN_SYNONYMS) if domain_raw else []
        )
        if not domains:
            continue

        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            continue

        if amount < 1:
            continue

        power_items.append({"domain": domains[0], "amount": amount})

    processed["cost"] = {"energy": energy, "power": power_items}

    color_hint: Optional[DomainColorSample] = None
    if image_path:
        try:
            color_hint = infer_domains_from_image(image_path)
        except OSError:
            color_hint = None

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

    processed = _apply_domain_color_hint(processed, color_hint)

    # Apply champion domain overrides
    processed = override_signature_spell_domains(processed)
    processed = override_champion_domains(processed)
    processed = _apply_spell_power_domains(processed)

    # Normalize effects
    processed["effects"] = normalize_effects(processed.get("effects", []))

    # Normalize rules text
    processed["rules_text"] = normalize_rules_text(processed.get("rules_text"))

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

    return processed
