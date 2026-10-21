"""Deterministic canned provider for unit tests. Never selected from env."""

from __future__ import annotations

from time import perf_counter

from legacylift_worker.llm.base import (
    ChatMessage,
    ChatResult,
    EmbedResult,
    LLMProvider,
    UsageRecord,
)
from legacylift_worker.llm.cost import estimate_cost


class FakeProvider(LLMProvider):
    """Returns scripted chat replies and hash embeddings.

    Construct this class in tests. `provider_from_env` refuses the name
    `fake` so eval and the CLI cannot present these replies as a model run.
    """

    def __init__(
        self,
        replies: list[str] | None = None,
        *,
        model_id: str = "fake-test-model",
        embed_dim: int = 8,
    ) -> None:
        self._replies = list(replies or [])
        self._index = 0
        self._model_id = model_id
        self._embed_dim = embed_dim
        self.chat_calls = 0
        self.embed_calls = 0

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model_id(self) -> str:
        return self._model_id

    def chat(self, messages: list[ChatMessage], *, attempt: int) -> ChatResult:
        del messages
        started = perf_counter()
        self.chat_calls += 1
        if self._index < len(self._replies):
            text = self._replies[self._index]
            self._index += 1
        else:
            text = ""
        latency_ms = int((perf_counter() - started) * 1000)
        tokens_in = 1
        tokens_out = max(len(text.split()), 1) if text else 0
        return ChatResult(
            text=text,
            usage=UsageRecord(
                provider=self.name,
                model=self.model_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                estimated_cost=estimate_cost(self.name, tokens_in, tokens_out),
                attempt=attempt,
            ),
        )

    def embed(self, texts: list[str], *, attempt: int = 1) -> EmbedResult:
        started = perf_counter()
        self.embed_calls += 1
        vectors = [_hash_vector(text, self._embed_dim) for text in texts]
        latency_ms = int((perf_counter() - started) * 1000)
        tokens_in = sum(max(len(text.split()), 1) for text in texts)
        return EmbedResult(
            vectors=vectors,
            usage=UsageRecord(
                provider=self.name,
                model=self.model_id,
                tokens_in=tokens_in,
                tokens_out=0,
                latency_ms=latency_ms,
                estimated_cost=estimate_cost(self.name, tokens_in, 0),
                attempt=attempt,
            ),
        )


def _hash_vector(text: str, dim: int) -> list[float]:
    """Bag-of-token hashes so overlapping words raise cosine in tests."""
    vec = [0.0] * dim
    tokens = text.lower().split()
    if not tokens:
        vec[0] = 1.0
        return vec
    for token in tokens:
        bucket = 0
        for byte in token.encode("utf-8", errors="replace"):
            bucket = (bucket * 31 + byte) % dim
        vec[bucket] += 1.0
    return vec
