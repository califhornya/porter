import json
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

from .image_utils import image_to_data_url
from .prompts import SYSTEM_PROMPT
from .post_process import strip_markdown_fences


def _extract_json_text_from_responses(response: Any) -> str:
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


def _extract_json_text_from_chat(response: Any) -> str:
    """Extract the text blob from a Chat Completions response."""
    try:
        choice = response.choices[0]
        content = choice.message.content
        if isinstance(content, list):
            # Multi-part message; concatenate any text parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    except Exception as exc:  # defensive
        raise RuntimeError("Unexpected response structure from OpenAI Chat API.") from exc

    if not content:
        raise RuntimeError("Model returned no text.")

    return strip_markdown_fences(content)


def _is_response_format_error(exc: Exception) -> bool:
    """Return True if an exception appears to be from response_format incompatibility."""

    message = str(exc)
    return "response_format" in message or "responses" in message


def _responses_input_to_messages(request_input: Any, *, force_json_hint: bool) -> Any:
    messages = []
    for item in request_input:
        contents = []
        for content in item["content"]:
            if content["type"] == "input_text":
                contents.append({"type": "text", "text": content["text"]})
            elif content["type"] == "input_image":
                contents.append({"type": "image_url", "image_url": {"url": content["image_url"]}})
        if force_json_hint and item["role"] == "user":
            contents.append({"type": "text", "text": "Return a single JSON object."})
            force_json_hint = False
        messages.append({"role": item["role"], "content": contents})
    if force_json_hint:
        messages.append({
            "role": "system",
            "content": [{"type": "text", "text": "Return a single JSON object."}],
        })
    return messages


def _create_response_with_fallback(client: OpenAI, request_kwargs: Dict[str, Any]) -> str:
    """Attempt Responses API call, falling back to Chat Completions when unsupported."""

    try:
        response = client.responses.create(**request_kwargs)
        return _extract_json_text_from_responses(response)
    except (TypeError, AttributeError) as exc:
        if not _is_response_format_error(exc):
            raise

    # response_format not supported; fall back to chat completions without response_format
    messages = _responses_input_to_messages(
        request_kwargs["input"], force_json_hint="response_format" in request_kwargs
    )

    chat_kwargs: Dict[str, Any] = {
        "model": request_kwargs["model"],
        "messages": messages,
        "temperature": request_kwargs.get("temperature", 0.0),
    }

    if "max_output_tokens" in request_kwargs:
        chat_kwargs["max_tokens"] = request_kwargs["max_output_tokens"]
    if "top_p" in request_kwargs:
        chat_kwargs["top_p"] = request_kwargs["top_p"]
    if "seed" in request_kwargs:
        chat_kwargs["seed"] = request_kwargs["seed"]

    response = client.chat.completions.create(**chat_kwargs)
    return _extract_json_text_from_chat(response)


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

    repaired_text = _create_response_with_fallback(client, request_kwargs)

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

    sanitized = _create_response_with_fallback(client, request_kwargs)

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
