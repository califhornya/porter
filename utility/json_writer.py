"""Persist normalized card specs as JSON files."""
from __future__ import annotations

import json
import pathlib
from typing import Dict

from .utils import NormalizedCard, ensure_directory, get_logger, slugify

LOGGER = get_logger(__name__)


class JsonWriter:
    def __init__(self, output_dir: str | pathlib.Path) -> None:
        self.output_dir = ensure_directory(output_dir)

    def write(self, card: NormalizedCard, effects: list[Dict[str, object]]) -> pathlib.Path:
        payload = card.to_card_spec()
        payload["effects"] = effects

        filename = slugify(card.name)
        if not filename:
            filename = "card"
        output_path = self.output_dir / f"{filename}.json"
        with output_path.open("w", encoding="utf8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        LOGGER.info("Wrote %s", output_path)
        return output_path
