"""Ollama HTTP chat and embeddings for a local model."""

from __future__ import annotations

import os
from time import perf_counter
from typing import Any

import httpx

from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.base import (
    ChatMessage,
    ChatResult,
    EmbedResult,
    LLMProvider,
    UsageRecord,
)
from legacylift_worker.llm.cost import estimate_cost
from legacylift_worker.llm.usage_parse import (
    message_text,
    tokens_from_ollama_chat,
    tokens_from_ollama_embed,
)

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class LocalProvider(LLMProvider):
    """POST /api/chat and POST /api/embed on an Ollama-compatible server.

    Official Ollama docs: non-stream chat uses stream=false. Embeddings use
    /api/embed with `input` as a string or array. Model names come from env.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        embed_model_id: str,
        timeout_sec: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not model_id.strip():
            raise PipelineError("OLLAMA_MODEL is empty")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id.strip()
        self._embed_model_id = embed_model_id.strip()
        self._timeout_sec = timeout_sec
        self._client = client

    @classmethod
    def from_env(cls) -> LocalProvider:
        """Build from OLLAMA_* environment variables."""
        model = os.environ.get("OLLAMA_MODEL", "").strip()
        if not model:
            raise PipelineError("local provider needs OLLAMA_MODEL in the environment")
        embed = os.environ.get("OLLAMA_EMBED_MODEL", "").strip()
        if not embed:
            raise PipelineError(
                "local provider needs OLLAMA_EMBED_MODEL in the environment"
            )
        raw_timeout = os.environ.get("OLLAMA_TIMEOUT_SEC", "120").strip()
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise PipelineError("OLLAMA_TIMEOUT_SEC must be a number") from exc
        base = os.environ.get("OLLAMA_URL", "").strip() or DEFAULT_OLLAMA_URL
        return cls(
            base_url=base,
            model_id=model,
            embed_model_id=embed,
            timeout_sec=timeout,
        )

    @property
    def name(self) -> str:
        return "local"

    @property
    def model_id(self) -> str:
        return self._model_id

    def chat(self, messages: list[ChatMessage], *, attempt: int) -> ChatResult:
        body = {
            "model": self._model_id,
            "messages": [
                {"role": item.role, "content": item.content} for item in messages
            ],
            "stream": False,
        }
        started = perf_counter()
        payload = self._post("/api/chat", body)
        latency_ms = int((perf_counter() - started) * 1000)
        message = payload.get("message")
        if not isinstance(message, dict):
            raise PipelineError("ollama chat response had no message")
        text = message_text(message.get("content"))
        tokens_in, tokens_out = tokens_from_ollama_chat(payload)
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
        if not texts:
            return EmbedResult(
                vectors=[],
                usage=UsageRecord(
                    provider=self.name,
                    model=self._embed_model_id,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=0,
                    estimated_cost=estimate_cost(self.name, 0, 0),
                    attempt=attempt,
                ),
            )
        if not self._embed_model_id:
            raise PipelineError("OLLAMA_EMBED_MODEL is empty")
        body: dict[str, Any] = {"model": self._embed_model_id, "input": texts}
        started = perf_counter()
        payload = self._post("/api/embed", body)
        latency_ms = int((perf_counter() - started) * 1000)
        raw = payload.get("embeddings")
        if not isinstance(raw, list) or any(not isinstance(row, list) for row in raw):
            raise PipelineError("ollama embed response had no embeddings array")
        vectors = [[float(n) for n in row] for row in raw]
        tokens_in, tokens_out = tokens_from_ollama_embed(payload)
        return EmbedResult(
            vectors=vectors,
            usage=UsageRecord(
                provider=self.name,
                model=self._embed_model_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                estimated_cost=estimate_cost(self.name, tokens_in, tokens_out),
                attempt=attempt,
            ),
        )

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = self._base_url + path
        client = self._client
        try:
            if client is None:
                response = httpx.post(url, json=body, timeout=self._timeout_sec)
            else:
                response = client.post(url, json=body, timeout=self._timeout_sec)
        except httpx.HTTPError as exc:
            raise PipelineError(f"ollama request to {path} failed: {exc}") from exc
        if response.status_code >= 400:
            snippet = response.text[:300]
            raise PipelineError(
                f"ollama {path} returned HTTP {response.status_code}: {snippet}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PipelineError(f"ollama {path} returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise PipelineError(f"ollama {path} returned a non-object JSON body")
        return payload
