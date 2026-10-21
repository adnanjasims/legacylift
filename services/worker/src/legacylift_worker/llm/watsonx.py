"""IBM watsonx.ai chat and embeddings via the official Python SDK."""

from __future__ import annotations

import os
from time import perf_counter
from typing import Any

from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.base import (
    ChatMessage,
    ChatResult,
    EmbedResult,
    LLMProvider,
    UsageRecord,
)
from legacylift_worker.llm.cost import estimate_cost
from legacylift_worker.llm.usage_parse import message_text, tokens_from_watsonx

_REQUIRED = (
    "WATSONX_API_KEY",
    "WATSONX_PROJECT_ID",
    "WATSONX_URL",
    "WATSONX_MODEL_ID",
)


class WatsonxProvider(LLMProvider):
    """ModelInference.chat and Embeddings.embed_documents from ibm-watsonx-ai.

    Model ids come from the environment. Region catalogs differ; list them
    with APIClient.foundation_models.ChatModels.show() and
    EmbeddingModels.show() against the configured URL.
    """

    def __init__(
        self,
        *,
        api_key: str,
        project_id: str,
        url: str,
        model_id: str,
        embed_model_id: str,
        inference: Any | None = None,
        embeddings: Any | None = None,
    ) -> None:
        if not model_id.strip():
            raise PipelineError("WATSONX_MODEL_ID is empty")
        self._api_key = api_key
        self._project_id = project_id
        self._url = url
        self._model_id = model_id.strip()
        self._embed_model_id = embed_model_id.strip()
        self._inference = inference
        self._embeddings = embeddings

    @classmethod
    def from_env(cls) -> WatsonxProvider:
        """Build from WATSONX_* environment variables."""
        missing = [name for name in _REQUIRED if not os.environ.get(name, "").strip()]
        if missing:
            raise PipelineError(
                "watsonx provider needs " + ", ".join(missing) + " in the environment"
            )
        embed_id = os.environ.get("WATSONX_EMBED_MODEL_ID", "").strip()
        if not embed_id:
            raise PipelineError(
                "watsonx provider needs WATSONX_EMBED_MODEL_ID in the environment"
            )
        return cls(
            api_key=os.environ["WATSONX_API_KEY"].strip(),
            project_id=os.environ["WATSONX_PROJECT_ID"].strip(),
            url=os.environ["WATSONX_URL"].strip(),
            model_id=os.environ["WATSONX_MODEL_ID"].strip(),
            embed_model_id=embed_id,
        )

    @property
    def name(self) -> str:
        return "watsonx"

    @property
    def model_id(self) -> str:
        return self._model_id

    def chat(self, messages: list[ChatMessage], *, attempt: int) -> ChatResult:
        model = self._get_inference()
        payload = [{"role": item.role, "content": item.content} for item in messages]
        started = perf_counter()
        raw = model.chat(messages=payload)
        latency_ms = int((perf_counter() - started) * 1000)
        if not isinstance(raw, dict):
            raise PipelineError("watsonx chat returned a non-object response")
        text = _choice_text(raw)
        tokens_in, tokens_out = tokens_from_watsonx(raw)
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
        client = self._get_embeddings()
        started = perf_counter()
        vectors = client.embed_documents(texts=texts)
        latency_ms = int((perf_counter() - started) * 1000)
        if not isinstance(vectors, list) or any(
            not isinstance(row, list) for row in vectors
        ):
            raise PipelineError("watsonx embeddings returned an unexpected shape")
        typed = [[float(n) for n in row] for row in vectors]
        tokens_in = sum(max(len(text.split()), 1) for text in texts)
        return EmbedResult(
            vectors=typed,
            usage=UsageRecord(
                provider=self.name,
                model=self._embed_model_id,
                tokens_in=tokens_in,
                tokens_out=0,
                latency_ms=latency_ms,
                estimated_cost=estimate_cost(self.name, tokens_in, 0),
                attempt=attempt,
            ),
        )

    def _get_inference(self) -> Any:
        if self._inference is not None:
            return self._inference
        credentials, project_id = self._credentials()
        from ibm_watsonx_ai.foundation_models import ModelInference

        self._inference = ModelInference(
            model_id=self._model_id,
            credentials=credentials,
            project_id=project_id,
        )
        return self._inference

    def _get_embeddings(self) -> Any:
        if self._embeddings is not None:
            return self._embeddings
        if not self._embed_model_id:
            raise PipelineError("WATSONX_EMBED_MODEL_ID is empty")
        credentials, project_id = self._credentials()
        from ibm_watsonx_ai.foundation_models import Embeddings

        self._embeddings = Embeddings(
            model_id=self._embed_model_id,
            credentials=credentials,
            project_id=project_id,
        )
        return self._embeddings

    def _credentials(self) -> tuple[Any, str]:
        from ibm_watsonx_ai import Credentials

        return (
            Credentials(url=self._url, api_key=self._api_key),
            self._project_id,
        )


def _choice_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise PipelineError("watsonx chat response had no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise PipelineError("watsonx chat choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise PipelineError("watsonx chat choice had no message")
    return message_text(message.get("content"))
