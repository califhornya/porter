#!/usr/bin/env python3
"""Command-line interface for Riftbound card extraction."""

import json
import os
from pathlib import Path
from typing import List, Optional

from openai import OpenAI
from pydantic import ValidationError
import typer

from .client import extract_card_json
from .models import CardData
from .post_process import post_process_card_data


app = typer.Typer(help="Extract Riftbound card JSON from image(s).", invoke_without_command=True)


def clean_filename(name: str) -> str:
    """Turn a card name into a safe filename."""
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    safe = "_".join(safe.strip().split())
    return safe or "card"


def _collect_images(target_path: Path, supported: List[str]) -> List[Path]:
    if target_path.is_dir():
        image_files = [p for p in target_path.iterdir() if p.suffix.lower() in supported]
        if not image_files:
            typer.echo("No supported image files found in directory.")
            raise typer.Exit(code=1)
        image_files.sort()
        return image_files

    if target_path.suffix.lower() not in supported:
        raise typer.BadParameter(f"Unsupported file type: {target_path.suffix}", param_name="path")
    return [target_path]


@app.callback()
def extract(
    path: Path = typer.Argument(..., help="Path to an image or a folder."),
    out_dir: Path = typer.Option(
        Path("output"),
        "--out-dir",
        help="Directory where JSON files will be stored.",
    ),
    model: str = typer.Option("gpt-4o", "--model", help="OpenAI model to use."),
    temperature: float = typer.Option(
        0.0, "--temperature", help="Sampling temperature for model queries (default: 0 for determinism)."
    ),
    top_p: Optional[float] = typer.Option(
        None, "--top-p", help="Optional nucleus sampling parameter for model queries."
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed",
        help="Optional random seed for deterministic sampling when supported by the model.",
    ),
    print_json: bool = typer.Option(
        False, "--print", help="Print JSON to stdout after writing.", show_default=False
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Process cards without writing JSON files to disk.", show_default=False
    ),
) -> None:
    """Extract Riftbound card JSON from image(s)."""

    target_path = path.expanduser().resolve()
    if not target_path.exists():
        raise typer.BadParameter(f"Path not found: {target_path}", param_name="path")

    supported = [".png", ".webp", ".jpg", ".jpeg"]
    image_files = _collect_images(target_path, supported)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        typer.echo("OPENAI_API_KEY is not set.")
        raise typer.Exit(code=1)

    client = OpenAI(api_key=api_key)

    resolved_out_dir = out_dir.expanduser().resolve()
    resolved_out_dir.mkdir(parents=True, exist_ok=True)

    for image_path in image_files:
        typer.echo(f"\nProcessing: {image_path}")
        typer.echo(f"Model: {model}")

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
            typer.echo(f"  ERROR while processing {image_path.name}: {exc}")
            continue

        processed_data = post_process_card_data(raw_data)

        try:
            card = CardData.model_validate(processed_data)
        except ValidationError as exc:
            typer.echo("  Validation error:")
            typer.echo(exc)
            typer.echo("  Raw model output:")
            typer.echo(json.dumps(raw_data, indent=2, ensure_ascii=False))
            continue

        filename = clean_filename(card.name) + ".json"
        out_path = resolved_out_dir / filename

        card_payload = card.model_dump()

        if print_json or dry_run:
            typer.echo(json.dumps(card_payload, indent=2, ensure_ascii=False))

        if dry_run:
            typer.echo("  Dry run enabled — file not written.")
            continue

        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(card_payload, f, indent=2, ensure_ascii=False)
            typer.echo(f"  Saved: {out_path}")
        except OSError as exc:
            typer.echo(f"  ERROR while writing {out_path}: {exc}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
