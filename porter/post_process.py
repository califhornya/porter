from typing import Any, Dict, Iterable, List, Optional


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

    # Apply champion domain overrides
    processed = override_signature_spell_domains(processed)
    processed = override_champion_domains(processed)

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
