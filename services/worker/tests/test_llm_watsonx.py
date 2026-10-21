import pytest

from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.base import ChatMessage
from legacylift_worker.llm.watsonx import WatsonxProvider


class _StubInference:
    def chat(self, messages: list[dict[str, str]]) -> dict[str, object]:
        assert messages[0]["role"] == "user"
        return {
            "choices": [{"message": {"role": "assistant", "content": "print(1)\n"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }


class _StubEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.5] for text in texts]


def test_watsonx_from_env_requires_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATSONX_MODEL_ID", raising=False)
    monkeypatch.setenv("WATSONX_API_KEY", "k")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "p")
    monkeypatch.setenv("WATSONX_URL", "https://example.invalid")
    with pytest.raises(PipelineError, match="WATSONX_MODEL_ID"):
        WatsonxProvider.from_env()


def test_watsonx_chat_and_embed_use_injected_clients() -> None:
    provider = WatsonxProvider(
        api_key="k",
        project_id="p",
        url="https://example.invalid",
        model_id="ibm/test-instruct",
        embed_model_id="ibm/test-embed",
        inference=_StubInference(),
        embeddings=_StubEmbeddings(),
    )
    chat = provider.chat([ChatMessage(role="user", content="hello")], attempt=2)
    assert chat.text == "print(1)\n"
    assert chat.usage.tokens_in == 10
    assert chat.usage.tokens_out == 4
    assert chat.usage.model == "ibm/test-instruct"
    assert chat.usage.attempt == 2
    embedded = provider.embed(["ab", "cd"])
    assert embedded.vectors == [[2.0, 0.5], [2.0, 0.5]]
    assert embedded.usage.model == "ibm/test-embed"
