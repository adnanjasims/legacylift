from legacylift_worker.llm.base import ChatMessage
from legacylift_worker.llm.fake import FakeProvider


def test_fake_returns_scripted_replies_then_empty() -> None:
    provider = FakeProvider(replies=["```python\nprint(1)\n```"])
    first = provider.chat(
        [ChatMessage(role="user", content="fix")],
        attempt=1,
    )
    second = provider.chat(
        [ChatMessage(role="user", content="fix")],
        attempt=2,
    )
    assert "print(1)" in first.text
    assert second.text == ""
    assert first.usage.provider == "fake"
    assert first.usage.attempt == 1
    assert provider.chat_calls == 2


def test_fake_embed_is_deterministic() -> None:
    provider = FakeProvider()
    once = provider.embed(["abc"], attempt=1)
    twice = provider.embed(["abc"], attempt=1)
    other = provider.embed(["xyz"], attempt=1)
    assert once.vectors == twice.vectors
    assert once.vectors != other.vectors
    assert len(once.vectors[0]) == 8
