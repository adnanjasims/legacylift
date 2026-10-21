"""LLM provider interface and per-call usage records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    estimated_cost: float | None
    attempt: int


@dataclass(frozen=True)
class ChatResult:
    text: str
    usage: UsageRecord


@dataclass
class EmbedResult:
    vectors: list[list[float]]
    usage: UsageRecord
    extra: dict[str, str] = field(default_factory=dict)


class LLMProvider(ABC):
    """Chat and embed. Implementations talk to a real endpoint or a test double."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider id, for example watsonx or local."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Chat model id supplied by configuration, never a baked-in default."""

    @abstractmethod
    def chat(self, messages: list[ChatMessage], *, attempt: int) -> ChatResult:
        """Return one assistant reply and the usage for that call."""

    @abstractmethod
    def embed(self, texts: list[str], *, attempt: int = 1) -> EmbedResult:
        """Return one vector per input text."""
