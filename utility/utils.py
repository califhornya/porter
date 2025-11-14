"""Utility helpers for the card import pipeline."""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

LOGGER_NAME = "riftbound.importer"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a module level logger configured for the utility."""
    logger_name = name or LOGGER_NAME
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def ensure_directory(path: str | os.PathLike[str]) -> pathlib.Path:
    """Create *path* if it does not already exist and return it as Path."""
    directory = pathlib.Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_json_file(path: str | os.PathLike[str]) -> Any:
    """Load JSON data from *path* if it exists, returning ``None`` otherwise."""
    file_path = pathlib.Path(path)
    if not file_path.exists():
        return None
    with file_path.open("r", encoding="utf8") as handle:
        return json.load(handle)


def slugify(value: str) -> str:
    """Generate a filesystem friendly slug from ``value``."""
    value = value.strip().replace(" ", "_")
    value = re.sub(r"[^0-9A-Za-z_\-]", "", value)
    value = re.sub(r"_+", "_", value)
    return value


@dataclass
class RawCardData:
    """Container for information coming from the OCR layer."""

    source: pathlib.Path
    name: Optional[str] = None
    type_line: Optional[str] = None
    cost_energy: Optional[int] = None
    cost_power: Optional[str] = None
    domain_icon: Optional[str] = None
    might: Optional[int] = None
    damage: Optional[int] = None
    keywords: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    rules_text: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": str(self.source),
            "name": self.name,
            "type_line": self.type_line,
            "cost_energy": self.cost_energy,
            "cost_power": self.cost_power,
            "domain_icon": self.domain_icon,
            "might": self.might,
            "damage": self.damage,
            "keywords": list(self.keywords),
            "tags": list(self.tags),
            "rules_text": self.rules_text,
            "notes": list(self.notes),
        }


@dataclass
class NormalizedCard:
    """Normalized structure consumed by downstream systems."""

    name: str
    category: str
    domain: Optional[str]
    cost_energy: Optional[int]
    cost_power: Optional[Dict[str, Any]]
    might: Optional[int]
    damage: Optional[int]
    keywords: List[str]
    tags: List[str]
    rules_text: Optional[str]
    raw_rules_text: Optional[str] = None

    def to_card_spec(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "category": self.category,
            "domain": self.domain,
            "cost_energy": self.cost_energy,
            "cost_power": self.cost_power,
            "might": self.might,
            "damage": self.damage,
            "keywords": list(self.keywords),
            "tags": list(self.tags),
        }
        if self.rules_text is not None:
            payload["rules_text"] = self.rules_text
        if self.raw_rules_text and self.raw_rules_text != self.rules_text:
            payload["raw_rules_text"] = self.raw_rules_text
        return payload


class PipelineError(RuntimeError):
    """Raised when the importer encounters an unrecoverable error."""


def coerce_int(value: Any) -> Optional[int]:
    """Attempt to convert ``value`` to ``int`` returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_")


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        key = value.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
