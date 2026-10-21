"""Estimated cost from caller-supplied rates. No invented prices."""

from __future__ import annotations

import os

from legacylift_worker.errors import PipelineError

_PROVIDER_RATE_VARS: dict[str, tuple[str, str]] = {
    "watsonx": ("WATSONX_INPUT_USD_PER_1K", "WATSONX_OUTPUT_USD_PER_1K"),
    "local": ("OLLAMA_INPUT_USD_PER_1K", "OLLAMA_OUTPUT_USD_PER_1K"),
    "fake": ("FAKE_INPUT_USD_PER_1K", "FAKE_OUTPUT_USD_PER_1K"),
}


def estimate_cost(provider: str, tokens_in: int, tokens_out: int) -> float | None:
    """USD for this call when both per-1k rates are set. None when unset.

    Args:
        provider: Provider name used to pick env var names.
        tokens_in: Prompt tokens from the provider response.
        tokens_out: Completion tokens from the provider response.
    """
    names = _PROVIDER_RATE_VARS.get(provider)
    if names is None:
        return None
    raw_in = os.environ.get(names[0], "").strip()
    raw_out = os.environ.get(names[1], "").strip()
    if raw_in == "" or raw_out == "":
        return None
    try:
        rate_in = float(raw_in)
        rate_out = float(raw_out)
    except ValueError as exc:
        raise PipelineError(
            f"{names[0]} and {names[1]} must be numbers (USD per 1k tokens)"
        ) from exc
    return (tokens_in / 1000.0) * rate_in + (tokens_out / 1000.0) * rate_out
