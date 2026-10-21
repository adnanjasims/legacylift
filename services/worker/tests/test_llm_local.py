import httpx

from legacylift_worker.llm.base import ChatMessage
from legacylift_worker.llm.local import LocalProvider


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/api/chat"):
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "ok"},
                "prompt_eval_count": 5,
                "eval_count": 2,
            },
        )
    if request.url.path.endswith("/api/embed"):
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2, 0.3]], "prompt_eval_count": 3},
        )
    return httpx.Response(404, text="missing")


def test_local_chat_and_embed_parse_ollama_json() -> None:
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    provider = LocalProvider(
        base_url="http://127.0.0.1:11434",
        model_id="test-chat",
        embed_model_id="test-embed",
        client=client,
    )
    chat = provider.chat([ChatMessage(role="user", content="hi")], attempt=1)
    assert chat.text == "ok"
    assert chat.usage.tokens_in == 5
    assert chat.usage.tokens_out == 2
    assert chat.usage.provider == "local"
    embedded = provider.embed(["hello"])
    assert embedded.vectors == [[0.1, 0.2, 0.3]]
    assert embedded.usage.tokens_in == 3
