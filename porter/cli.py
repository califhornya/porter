#!/usr/bin/env python3
"""Command-line interface for Riftbound card extraction."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from openai import OpenAI
from pydantic import ValidationError

from .client import extract_card_json
from .models import CardData
from .post_process import post_process_card_data


def clean_filename(name: str) -> str:
    """Turn a card name into a safe filename."""
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    safe = "_".join(safe.strip().split())
    return safe or "card"


def _collect_images(target_path: Path, supported: List[str]) -> List[Path]:
    if target_path.is_dir():
        image_files = [p for p in target_path.iterdir() if p.suffix.lower() in supported]
        if not image_files:
            raise ValueError("No supported image files found in directory.")
        image_files.sort()
        return image_files

    if target_path.suffix.lower() not in supported:
        raise ValueError(f"Unsupported file type: {target_path.suffix}")
    return [target_path]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Riftbound card JSON from image(s).")
    parser.add_argument("path", type=Path, help="Path to an image or a folder.")
    parser.add_argument(
        "--out-dir",
        dest="out_dir",
        type=Path,
        default=Path("output"),
        help="Directory where JSON files will be stored.",
    )
    parser.add_argument("--model", type=str, default="gpt-4o", help="OpenAI model to use.")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for model queries (default: 0 for determinism).",
    )
    parser.add_argument(
        "--top-p",
        dest="top_p",
        type=float,
        default=None,
        help="Optional nucleus sampling parameter for model queries.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for deterministic sampling when supported by the model.",
    )
    parser.add_argument(
        "--print",
        dest="print_json",
        action="store_true",
        help="Print JSON to stdout after writing.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Process cards without writing JSON files to disk.",
    )
    return parser.parse_args(argv)


def extract(
    path: Path,
    out_dir: Path,
    model: str,
    temperature: float,
    top_p: Optional[float],
    seed: Optional[int],
    print_json: bool,
    dry_run: bool,
) -> int:
    """Extract Riftbound card JSON from image(s)."""

    target_path = path.expanduser().resolve()
    if not target_path.exists():
        print(f"Path not found: {target_path}", file=sys.stderr)
        return 1

    supported = [".png", ".webp", ".jpg", ".jpeg"]
    try:
        image_files = _collect_images(target_path, supported)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)

    resolved_out_dir = out_dir.expanduser().resolve()
    resolved_out_dir.mkdir(parents=True, exist_ok=True)

    for image_path in image_files:
        print(f"\nProcessing: {image_path}")
        print(f"Model: {model}")

        try:
            raw_data = extract_card_json(
                client,
                image_path,
                model=model,
                temperature=temperature,
                top_p=top_p,
                seed=seed,
            )
        except Exception as exc:  # pragma: no cover - API failure paths are external
            print(f"  ERROR while processing {image_path.name}: {exc}")
            continue

        processed_data = post_process_card_data(raw_data)

        try:
            card = CardData.model_validate(processed_data)
        except ValidationError as exc:
            print("  Validation error:")
            print(exc)
            print("  Raw model output:")
            print(json.dumps(raw_data, indent=2, ensure_ascii=False))
            continue

        filename = clean_filename(card.name) + ".json"
        out_path = resolved_out_dir / filename

        card_payload = card.model_dump()

        if print_json or dry_run:
            print(json.dumps(card_payload, indent=2, ensure_ascii=False))

        if dry_run:
            print("  Dry run enabled — file not written.")
            continue

        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(card_payload, f, indent=2, ensure_ascii=False)
            print(f"  Saved: {out_path}")
        except OSError as exc:
            print(f"  ERROR while writing {out_path}: {exc}")

    return 0


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    sys.exit(
        extract(
            path=args.path,
            out_dir=args.out_dir,
            model=args.model,
            temperature=args.temperature,
            top_p=args.top_p,
            seed=args.seed,
            print_json=args.print_json,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
