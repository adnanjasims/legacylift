"""Select a real LLM provider from the CLI name or the environment."""

from __future__ import annotations

import os

from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.base import LLMProvider
from legacylift_worker.llm.local import LocalProvider
from legacylift_worker.llm.watsonx import WatsonxProvider


def provider_from_name(name: str | None) -> LLMProvider | None:
    """Return watsonx, local, or None.

    `fake` raises PipelineError. Eval and the CLI construct FakeProvider
    only from tests that import the class.
    """
    key = (name or "none").strip().lower()
    if key in {"", "none"}:
        return None
    if key == "fake":
        raise PipelineError("FakeProvider is for unit tests only")
    if key == "watsonx":
        return WatsonxProvider.from_env()
    if key == "local":
        return LocalProvider.from_env()
    raise PipelineError(f"unknown LLM provider {name!r}; use none, watsonx, or local")


def configured_provider() -> LLMProvider | None:
    """Pick watsonx or local when their required env vars are present.

    LLM_PROVIDER, when set to none/watsonx/local, wins. Otherwise watsonx
    is used when WATSONX_* is complete, else local when OLLAMA_* is complete.
    """
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return provider_from_name(explicit)
    if _watsonx_ready():
        return WatsonxProvider.from_env()
    if _ollama_ready():
        return LocalProvider.from_env()
    return None


def _watsonx_ready() -> bool:
    names = (
        "WATSONX_API_KEY",
        "WATSONX_PROJECT_ID",
        "WATSONX_URL",
        "WATSONX_MODEL_ID",
        "WATSONX_EMBED_MODEL_ID",
    )
    return all(os.environ.get(name, "").strip() for name in names)


def _ollama_ready() -> bool:
    return bool(
        os.environ.get("OLLAMA_MODEL", "").strip()
        and os.environ.get("OLLAMA_EMBED_MODEL", "").strip()
    )
