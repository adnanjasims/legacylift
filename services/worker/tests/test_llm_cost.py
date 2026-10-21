import pytest

from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.cost import estimate_cost


def test_estimate_cost_none_when_rates_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATSONX_INPUT_USD_PER_1K", raising=False)
    monkeypatch.delenv("WATSONX_OUTPUT_USD_PER_1K", raising=False)
    assert estimate_cost("watsonx", 1000, 500) is None


def test_estimate_cost_uses_env_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATSONX_INPUT_USD_PER_1K", "0.001")
    monkeypatch.setenv("WATSONX_OUTPUT_USD_PER_1K", "0.002")
    assert estimate_cost("watsonx", 1000, 500) == pytest.approx(0.002)


def test_estimate_cost_rejects_non_numeric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_INPUT_USD_PER_1K", "nope")
    monkeypatch.setenv("OLLAMA_OUTPUT_USD_PER_1K", "1")
    with pytest.raises(PipelineError, match="must be numbers"):
        estimate_cost("local", 10, 10)
