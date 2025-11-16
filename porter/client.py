import json
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

from .image_utils import image_to_data_url
from .prompts import SYSTEM_PROMPT
from .post_process import strip_markdown_fences


def _extract_json_text(response: Any) -> str:
    """Extract the text blob from a Responses API response."""
    try:
        output = response.output
        json_text = None
        for item in output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        json_text = content.text
                        break
            if json_text is not None:
                break
    except Exception as exc:  # defensive
        raise RuntimeError("Unexpected response structure from OpenAI Responses API.") from exc

    if not json_text:
        raise RuntimeError("Model returned no text.")

    return strip_markdown_fences(json_text)


def attempt_repair_json(
    client: OpenAI,
    raw_text: str,
    *,
    model: str,
    temperature: float = 0.0,
    top_p: Optional[float] = None,
    seed: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Second-pass: ask the model to fix invalid JSON."""
    repair_prompt = (
        "The following text was intended to be a JSON object describing a Riftbound card. "
        "It may contain trailing commas or other mistakes. Return ONLY valid JSON for the same data.\n"
        f"Broken JSON:\n{raw_text}"
    )

    request_kwargs: Dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": "You fix invalid JSON without explanation."}
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": repair_prompt}],
            },
        ],
        "max_output_tokens": 1024,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    if top_p is not None:
        request_kwargs["top_p"] = top_p
    if seed is not None:
        request_kwargs["seed"] = seed

    response = client.responses.create(**request_kwargs)

    repaired_text = _extract_json_text(response)

    try:
        return json.loads(repaired_text)
    except json.JSONDecodeError:
        return None


def extract_card_json(
    client: OpenAI,
    image_path: Path,
    model: str,
    *,
    temperature: float = 0.0,
    top_p: Optional[float] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Call the model on a single image and return the raw JSON dict."""
    data_url = image_to_data_url(image_path)

    request_kwargs: Dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Extract the card data as JSON."},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        "max_output_tokens": 2048,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    if top_p is not None:
        request_kwargs["top_p"] = top_p
    if seed is not None:
        request_kwargs["seed"] = seed

    response = client.responses.create(**request_kwargs)

    sanitized = _extract_json_text(response)

    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        repaired = attempt_repair_json(
            client,
            sanitized,
            model=model,
            temperature=temperature,
            top_p=top_p,
            seed=seed,
        )
        if repaired is None:
            raise RuntimeError(
                "Model output was not valid JSON and automatic repair failed. "
                f"Raw output was:\n{sanitized}"
            )
        return repaired
