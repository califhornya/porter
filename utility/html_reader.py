"""HTML fallback reader for Riftbound card data.

The official card library is often exported as a single HTML document.  This
module extracts a mapping of card name to structured data by accepting a range
of simple document formats:

* ``<script type="application/json">`` blocks containing a dictionary
* ``<pre id="card-data">`` blocks with JSON text
* ``data-card-json="..."`` attributes containing inline JSON

If none of these markers exist, the reader falls back to parsing ``<table>``
rows that contain ``data-card-name`` attributes.  The design goal is to remain
robust across variations while keeping the implementation dependency free.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional

from .utils import get_logger

LOGGER = get_logger(__name__)


@dataclass
class HtmlCardRecord:
    name: str
    payload: Dict[str, object]


class _CardHtmlParser(HTMLParser):
    """Minimal parser capable of extracting JSON blobs from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.json_blocks: List[str] = []
        self._capture: Optional[List[str]] = None
        self._capture_tag: Optional[str] = None

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        attrs_dict = dict(attrs)
        json_attr = attrs_dict.get("data-card-json")
        if json_attr:
            self.json_blocks.append(json_attr)
        if tag in {"script", "pre"} and (
            attrs_dict.get("type") == "application/json"
            or attrs_dict.get("id") == "card-data"
        ):
            self._capture = []
            self._capture_tag = tag

        if attrs_dict.get("data-card-name") and tag == "tr":
            payload = {k.replace("data-card-", ""): v for k, v in attrs if k.startswith("data-card-")}
            name = attrs_dict.get("data-card-name")
            if name:
                try:
                    self.json_blocks.append(json.dumps({name: payload}))
                except Exception:
                    pass

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if self._capture is not None and tag == self._capture_tag:
            self.json_blocks.append("".join(self._capture))
            self._capture = None
            self._capture_tag = None

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._capture is not None:
            self._capture.append(data)


class HtmlCardLibrary:
    """Parse HTML exports into a name → payload mapping."""

    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        LOGGER.debug("Parsing HTML library %s", self.path)
        self.records = self._parse()

    def _parse(self) -> Dict[str, Dict[str, object]]:
        parser = _CardHtmlParser()
        parser.feed(self.path.read_text(encoding="utf8"))

        combined: Dict[str, Dict[str, object]] = {}
        for block in parser.json_blocks:
            for payload in self._extract_json(block):
                combined.update(payload)
        LOGGER.info("Loaded %s cards from HTML fallback", len(combined))
        return combined

    # ------------------------------------------------------------------
    def _extract_json(self, blob: str) -> List[Dict[str, Dict[str, object]]]:
        results: List[Dict[str, Dict[str, object]]] = []
        candidates = self._split_candidates(blob)
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                if all(isinstance(v, dict) for v in payload.values()):
                    results.append(payload)
                else:
                    # assume flat record {"name": {...}}
                    for name, value in payload.items():
                        if isinstance(value, dict):
                            results.append({name: value})
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict) and "name" in item:
                        results.append({str(item["name"]): item})
        return results

    # ------------------------------------------------------------------
    def _split_candidates(self, blob: str) -> List[str]:
        if blob.strip().startswith("{"):
            return [blob]
        candidates = re.findall(r"\{.*?\}", blob, flags=re.DOTALL)
        return candidates or [blob]

    # ------------------------------------------------------------------
    def lookup(self, name: str) -> Optional[Dict[str, object]]:
        return self.records.get(name) or self.records.get(name.title())
