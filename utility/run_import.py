"""Command line entry point for the Riftbound card importer."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Dict, Iterable, Optional

from .effect_parser import EffectParser
from .html_reader import HtmlCardLibrary
from .image_reader import ImageReader, ImageReaderConfig
from .json_writer import JsonWriter
from .normalizer import Normalizer
from .utils import NormalizedCard, PipelineError, RawCardData, get_logger, normalize_keyword, slugify

LOGGER = get_logger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Directory containing .webp files")
    parser.add_argument("--output", required=True, help="Directory for generated JSON")
    parser.add_argument(
        "--html",
        help="Optional HTML export used to fill in missing fields",
    )
    parser.add_argument(
        "--overrides",
        help="Optional JSON file containing manual OCR overrides keyed by filename",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit the number of files processed (useful for testing)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def load_overrides(path: Optional[str]) -> Optional[Dict[str, Dict[str, object]]]:
    if not path:
        return None
    override_path = pathlib.Path(path)
    if not override_path.exists():
        raise FileNotFoundError(override_path)
    with override_path.open("r", encoding="utf8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Overrides file must contain a JSON object")
    return data  # type: ignore[return-value]


class ImportPipeline:
    def __init__(
        self,
        reader: ImageReader,
        normalizer: Normalizer,
        effect_parser: EffectParser,
        writer: JsonWriter,
        html_library: Optional[HtmlCardLibrary] = None,
    ) -> None:
        self.reader = reader
        self.normalizer = normalizer
        self.effect_parser = effect_parser
        self.writer = writer
        self.html_library = html_library

    def run(self, image_paths: Iterable[pathlib.Path]) -> None:
        for path in image_paths:
            LOGGER.info("Processing %s", path.name)
            raw: Optional[RawCardData] = None
            fallback: Optional[RawCardData] = None
            normalized: Optional[NormalizedCard] = None
            effects: Optional[list[Dict[str, object]]] = None
            try:
                raw = self.reader.read(path)
                fallback = self._merge_html(raw)
                normalized = self.normalizer.normalize(fallback)
                effects = self.effect_parser.parse(normalized)
                self.writer.write(normalized, effects)
            except PipelineError as error:
                LOGGER.warning("Pipeline error while processing %s: %s", path.name, error)
                self._dump_partial_output(path, error, raw, fallback, normalized, effects)
            except Exception as error:  # pragma: no cover - defensive programming
                LOGGER.warning(
                    "Unexpected error while processing %s: %s",
                    path.name,
                    error,
                    exc_info=True,
                )
                self._dump_partial_output(path, error, raw, fallback, normalized, effects)

    def _merge_html(self, raw: RawCardData) -> RawCardData:
        if not self.html_library or not raw.name:
            return raw
        payload = self.html_library.lookup(raw.name)
        if not payload:
            return raw
        merged = RawCardData(
            source=raw.source,
            name=raw.name,
            type_line=raw.type_line,
            cost_energy=raw.cost_energy,
            cost_power=raw.cost_power,
            domain_icon=raw.domain_icon,
            might=raw.might,
            damage=raw.damage,
            keywords=list(raw.keywords),
            tags=list(raw.tags),
            rules_text=raw.rules_text,
            notes=list(raw.notes),
        )
        merged.notes.append("html: merged")
        if "type_line" in payload and not raw.type_line:
            merged.type_line = str(payload["type_line"])
        if "domain" in payload and not raw.domain_icon:
            merged.domain_icon = str(payload["domain"])
        if "cost_energy" in payload and raw.cost_energy is None:
            merged.cost_energy = payload.get("cost_energy")  # type: ignore[assignment]
        if "cost_power" in payload and not raw.cost_power:
            merged.cost_power = str(payload["cost_power"])
        if "might" in payload and raw.might is None:
            merged.might = payload.get("might")  # type: ignore[assignment]
        if "damage" in payload and raw.damage is None:
            merged.damage = payload.get("damage")  # type: ignore[assignment]
        if "keywords" in payload and not raw.keywords:
            keywords = payload["keywords"]
            if isinstance(keywords, list):
                merged.keywords.extend(normalize_keyword(str(k)) for k in keywords if k)
        if "tags" in payload and not raw.tags:
            tags = payload["tags"]
            if isinstance(tags, list):
                merged.tags.extend(str(t).strip() for t in tags if t)
        if "rules_text" in payload and not raw.rules_text:
            merged.rules_text = str(payload["rules_text"])
        return merged

def _dump_partial_output(
        self,
        source: pathlib.Path,
        error: Exception,
        raw: Optional[RawCardData],
        merged: Optional[RawCardData],
        normalized: Optional[NormalizedCard],
        effects: Optional[list[Dict[str, object]]],
    ) -> None:
        slug_source: Optional[str] = None
        if normalized and normalized.name:
            slug_source = normalized.name
        elif merged and merged.name:
            slug_source = merged.name
        elif raw and raw.name:
            slug_source = raw.name
        else:
            slug_source = source.stem

        filename = slugify(slug_source)
        if not filename:
            filename = source.stem or "card"

        output_path = self.writer.output_dir / f"{filename}.json"
        payload: Dict[str, object] = {
            "error": str(error),
            "source_image": str(source),
            "partial": True,
        }

        if raw:
            payload["raw_card_data"] = raw.to_dict()
        if merged and merged is not raw:
            payload["merged_card_data"] = merged.to_dict()
        if normalized:
            normalized_payload = normalized.to_card_spec()
            if normalized.raw_rules_text is not None:
                normalized_payload["raw_rules_text"] = normalized.raw_rules_text
            payload["normalized_card"] = normalized_payload
        if effects is not None:
            payload["effects"] = effects

        try:
            with output_path.open("w", encoding="utf8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            LOGGER.warning(
                "Wrote partial output for %s to %s", source.name, output_path
            )
        except Exception as write_error:  # pragma: no cover - logging only
            LOGGER.error(
                "Failed to write partial output for %s: %s", source.name, write_error
            )

def run_cli(argv: Optional[Iterable[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        LOGGER.setLevel("DEBUG")

    overrides = load_overrides(args.overrides)

    reader = ImageReader(ImageReaderConfig(transcription_overrides=overrides))
    normalizer = Normalizer()
    effect_parser = EffectParser()
    writer = JsonWriter(args.output)
    html_library = HtmlCardLibrary(args.html) if args.html else None

    image_dir = pathlib.Path(args.input)
    if not image_dir.exists():
        raise FileNotFoundError(image_dir)

    image_paths = sorted(image_dir.glob("*.webp"))
    if args.limit:
        image_paths = image_paths[: args.limit]

    pipeline = ImportPipeline(reader, normalizer, effect_parser, writer, html_library)
    pipeline.run(image_paths)


if __name__ == "__main__":  # pragma: no cover
    run_cli()
