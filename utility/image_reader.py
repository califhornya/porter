"""Image reader responsible for extracting raw fields from card images.

The implementation is intentionally defensive – the production OCR model used
by the original Riftbound tooling is not available inside this kata
environment.  The :class:`ImageReader` therefore attempts to use Pillow and
``pytesseract`` when available but gracefully falls back to lightweight
heuristics.  When OCR is not available the reader still returns a
:class:`~utility.utils.RawCardData` instance populated with best effort values
(including notes describing that a fallback path was used).  Downstream stages
log warnings when data is missing, ensuring that the pipeline never aborts
while iterating a directory of cards.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - pillow missing in kata environment
    Image = None  # type: ignore

from .utils import RawCardData, PipelineError, coerce_int, get_logger, normalize_keyword

LOGGER = get_logger(__name__)

try:  # pragma: no cover - optional dependency
    import pytesseract
except Exception:  # pragma: no cover - dependency missing in kata container
    pytesseract = None  # type: ignore


@dataclass
class ImageReaderConfig:
    """Configuration values for :class:`ImageReader`."""

    transcription_overrides: Optional[Dict[str, Dict[str, object]]] = None
    strict: bool = False


class ImageReader:
    """Extract information from Riftbound card images."""

    def __init__(self, config: Optional[ImageReaderConfig] = None) -> None:
        self.config = config or ImageReaderConfig()
        self._overrides = self.config.transcription_overrides or {}

    # ------------------------------------------------------------------
    def read(self, path: str | os.PathLike[str]) -> RawCardData:
        """Return :class:`RawCardData` for ``path``.

        When OCR is available the method feeds the image to Tesseract and uses
        simple pattern extraction helpers to identify relevant fields.  In
        environments where OCR is unavailable the reader falls back to
        heuristic extraction and optional override data stored alongside the
        images.
        """

        file_path = pathlib.Path(path)
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        LOGGER.debug("Reading image %s", file_path)
        if Image is None:
            if self.config.strict:
                raise PipelineError("Pillow is required for strict image parsing")
            image = None
        else:
            image = Image.open(file_path)  # Pillow can load .webp natively

        override = self._load_override(file_path)
        text_blob = None
        if image is not None and pytesseract is not None:  # pragma: no cover - optional path
            try:
                text_blob = pytesseract.image_to_string(image)
                LOGGER.debug("OCR text for %s: %s", file_path.name, text_blob)
            except Exception as exc:  # pragma: no cover
                LOGGER.warning("OCR failed for %s: %s", file_path, exc)

        raw = RawCardData(source=file_path)
        if override:
            raw.notes.append("override: transcription file loaded")
        if text_blob:
            raw.notes.append("ocr: pytesseract")
            self._apply_text_blob(raw, text_blob)
        elif override:
            raw.notes.append("ocr: overrides only")
        else:
            raw.notes.append("ocr: fallback heuristics")

        if override:
            self._apply_override(raw, override)
        else:
            self._apply_filename_heuristics(raw)

        if image is not None:
            try:
                image.close()
            except Exception:  # pragma: no cover - Pillow optional
                pass

        return raw

    # ------------------------------------------------------------------
    def _load_override(self, image_path: pathlib.Path) -> Optional[Dict[str, object]]:
        key = image_path.stem
        if key in self._overrides:
            return self._overrides[key]

        sidecar = image_path.with_suffix(image_path.suffix + ".json")
        if sidecar.exists():
            try:
                with sidecar.open("r", encoding="utf8") as handle:
                    data = json.load(handle)
                LOGGER.debug("Loaded override for %s from %s", image_path.name, sidecar)
                return data
            except Exception as exc:  # pragma: no cover - sidecar errors are rare
                LOGGER.warning("Failed to read %s: %s", sidecar, exc)
        return None

    # ------------------------------------------------------------------
    def _apply_override(self, raw: RawCardData, override: Dict[str, object]) -> None:
        raw.name = override.get("name") or raw.name
        raw.type_line = override.get("type_line") or raw.type_line
        raw.cost_energy = coerce_int(override.get("cost_energy")) or raw.cost_energy
        raw.cost_power = override.get("cost_power") or raw.cost_power
        raw.domain_icon = override.get("domain_icon") or raw.domain_icon
        raw.might = coerce_int(override.get("might")) or raw.might
        raw.damage = coerce_int(override.get("damage")) or raw.damage
        raw.rules_text = override.get("rules_text") or raw.rules_text

        keywords = override.get("keywords") or []
        tags = override.get("tags") or []
        if isinstance(keywords, str):
            keywords = re.split(r"[,;]", keywords)
        if isinstance(tags, str):
            tags = re.split(r"[,;]", tags)
        raw.keywords.extend(normalize_keyword(str(k)) for k in keywords if k)
        raw.tags.extend(str(t).strip() for t in tags if t)

    # ------------------------------------------------------------------
    def _apply_filename_heuristics(self, raw: RawCardData) -> None:
        """Populate baseline fields derived from the filename."""
        stem = raw.source.stem
        raw.name = raw.name or stem.replace("_", " ").replace("-", " ").title()
        if raw.type_line is None:
            raw.type_line = "Unknown"
        if raw.rules_text is None:
            raw.rules_text = ""

    # ------------------------------------------------------------------
    def _apply_text_blob(self, raw: RawCardData, text_blob: str) -> None:
        lines = [line.strip() for line in text_blob.splitlines() if line.strip()]
        if not lines:
            return

        raw.name = raw.name or lines[0].title()

        for line in lines[1:]:
            lowered = line.lower()
            if "unit" in lowered or "spell" in lowered or "gear" in lowered:
                raw.type_line = raw.type_line or line
            if "might" in lowered:
                maybe = re.findall(r"(\d+)", line)
                if maybe:
                    raw.might = raw.might or int(maybe[0])
            if "damage" in lowered:
                maybe = re.findall(r"(\d+)", line)
                if maybe:
                    raw.damage = raw.damage or int(maybe[0])
            if "energy" in lowered and raw.cost_energy is None:
                maybe = re.findall(r"(\d+)", line)
                if maybe:
                    raw.cost_energy = int(maybe[0])
            if "power" in lowered and raw.cost_power is None:
                match = re.search(r"([A-Za-z]+)\s*(\d+)", line)
                if match:
                    raw.cost_power = f"{match.group(1).upper()} {match.group(2)}"
            if "domain" in lowered and raw.domain_icon is None:
                match = re.search(r"domain[:\s]+([A-Za-z]+)", line)
                if match:
                    raw.domain_icon = match.group(1).upper()

        keyword_lines: Iterable[str] = (
            line for line in lines if line.isupper() and len(line.split()) <= 3
        )
        for keyword in keyword_lines:
            raw.keywords.append(normalize_keyword(keyword))

        if raw.rules_text is None:
            raw.rules_text = "\n".join(lines[1:])
