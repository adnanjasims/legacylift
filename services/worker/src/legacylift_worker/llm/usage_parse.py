"""Pull token counts out of provider JSON without guessing missing fields."""

from __future__ import annotations

from typing import Any


def tokens_from_watsonx(payload: dict[str, Any]) -> tuple[int, int]:
    """Read prompt and completion tokens from a watsonx chat dict.

    Official chat responses expose usage.prompt_tokens and
    usage.completion_tokens. Missing keys count as zero.
    """
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    return _as_int(usage.get("prompt_tokens")), _as_int(usage.get("completion_tokens"))


def tokens_from_ollama_chat(payload: dict[str, Any]) -> tuple[int, int]:
    """Read prompt_eval_count and eval_count from a non-stream Ollama chat body."""
    return _as_int(payload.get("prompt_eval_count")), _as_int(payload.get("eval_count"))


def tokens_from_ollama_embed(payload: dict[str, Any]) -> tuple[int, int]:
    """Read prompt_eval_count from an Ollama /api/embed body. Output tokens are 0."""
    return _as_int(payload.get("prompt_eval_count")), 0


def message_text(content: object) -> str:
    """Flatten chat content that may be a string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "".join(parts)
    return ""


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
