"""Quick smoke test for the Riftbound card import pipeline."""
from __future__ import annotations

import pathlib
from pprint import pprint

from .effect_parser import EffectParser
from .image_reader import ImageReader, ImageReaderConfig
from .json_writer import JsonWriter
from .normalizer import Normalizer
from .run_import import ImportPipeline
from .utils import get_logger

LOGGER = get_logger(__name__)

SAMPLE_OVERRIDES = {
    "OGN-001": {
        "name": "Blazing Initiate",
        "type_line": "Unit — Warrior",
        "cost_energy": 1,
        "cost_power": "Fury 1",
        "domain_icon": "fury",
        "might": 2,
        "keywords": ["Deflect"],
        "tags": ["WARRIOR"],
        "rules_text": "Deal 2 damage to an enemy unit.",
    },
    "OGN-032": {
        "name": "Stormcall Adept",
        "type_line": "Unit — Mage",
        "cost_energy": 2,
        "cost_power": "Light 1",
        "domain_icon": "light",
        "might": 3,
        "keywords": ["Barrage"],
        "tags": ["MAGE"],
        "rules_text": "Draw 1 card. Deal 1 damage to an enemy unit.",
    },
    "OGN-081": {
        "name": "Rift Scholar",
        "type_line": "Spell",
        "cost_energy": 3,
        "domain_icon": "order",
        "damage": None,
        "keywords": ["Haste"],
        "tags": ["SCHOLAR"],
        "rules_text": "Heal 3 to your hero.",
    },
}


def main() -> None:
    base_dir = pathlib.Path(__file__).resolve().parent.parent
    images_dir = base_dir / "webp_files"
    output_dir = base_dir / "self_test_output"

    reader = ImageReader(ImageReaderConfig(transcription_overrides=SAMPLE_OVERRIDES))
    normalizer = Normalizer()
    effect_parser = EffectParser()
    writer = JsonWriter(output_dir)

    sample_files = [images_dir / f"{name}.webp" for name in SAMPLE_OVERRIDES]
    sample_files = [path for path in sample_files if path.exists()]
    if not sample_files:
        raise SystemExit("Sample assets are missing")

    pipeline = ImportPipeline(reader, normalizer, effect_parser, writer)
    for path in sample_files:
        raw = reader.read(path)
        LOGGER.info("Raw OCR data for %s", path.name)
        pprint(raw.to_dict())
        normalized = normalizer.normalize(raw)
        LOGGER.info("Normalized card for %s", path.name)
        pprint(normalized.to_card_spec())
        effects = effect_parser.parse(normalized)
        LOGGER.info("Derived effects for %s", path.name)
        pprint(effects)
        writer.write(normalized, effects)

    LOGGER.info("Self test completed. JSON files written to %s", output_dir)


if __name__ == "__main__":  # pragma: no cover
    main()
