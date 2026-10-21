import pytest

from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.factory import configured_provider, provider_from_name


def test_provider_from_name_none() -> None:
    assert provider_from_name("none") is None
    assert provider_from_name(None) is None


def test_provider_from_name_rejects_fake() -> None:
    with pytest.raises(PipelineError, match="unit tests only"):
        provider_from_name("fake")


def test_configured_provider_empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LLM_PROVIDER",
        "WATSONX_API_KEY",
        "WATSONX_PROJECT_ID",
        "WATSONX_URL",
        "WATSONX_MODEL_ID",
        "WATSONX_EMBED_MODEL_ID",
        "OLLAMA_MODEL",
        "OLLAMA_EMBED_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    assert configured_provider() is None
