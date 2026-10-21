"""Retrieve related source chunks by embedding cosine similarity."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select

from legacylift_worker.chunk import CodeChunk, chunk_tree
from legacylift_worker.db.models import CodeChunkRow
from legacylift_worker.db.session import make_engine, prepare_schema, session_factory
from legacylift_worker.llm.base import LLMProvider, UsageRecord
from legacylift_worker.redact import redact_secrets

logger = logging.getLogger("legacylift.worker")


@dataclass(frozen=True)
class RetrievedChunk:
    path: str
    index: int
    text: str
    score: float


class RetrievalIndex(Protocol):
    def add(self, chunks: list[CodeChunk]) -> list[UsageRecord]: ...

    def query(
        self, text: str, *, k: int = 4
    ) -> tuple[list[RetrievedChunk], UsageRecord]: ...


class MemoryIndex:
    """Cosine search over vectors held for the current job."""

    def __init__(self, job_id: str, provider: LLMProvider) -> None:
        self.job_id = job_id
        self._provider = provider
        self._rows: list[tuple[CodeChunk, list[float]]] = []

    def add(self, chunks: list[CodeChunk]) -> list[UsageRecord]:
        if not chunks:
            return []
        texts = [redact_secrets(chunk.text) for chunk in chunks]
        result = self._provider.embed(texts, attempt=1)
        if len(result.vectors) != len(chunks):
            raise ValueError("embed returned a different count than the chunk list")
        for chunk, vector in zip(chunks, result.vectors, strict=True):
            self._rows.append((chunk, vector))
        return [result.usage]

    def query(
        self, text: str, *, k: int = 4
    ) -> tuple[list[RetrievedChunk], UsageRecord]:
        result = self._provider.embed([redact_secrets(text)], attempt=1)
        if not result.vectors:
            return [], result.usage
        query_vec = result.vectors[0]
        ranked = sorted(
            (
                RetrievedChunk(
                    path=chunk.path,
                    index=chunk.index,
                    text=chunk.text,
                    score=_cosine(query_vec, vector),
                )
                for chunk, vector in self._rows
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return ranked[:k], result.usage


class PgvectorIndex:
    """Store chunks in Postgres and rank with pgvector cosine distance."""

    def __init__(self, job_id: str, provider: LLMProvider, engine_url: str) -> None:
        self.job_id = job_id
        self._provider = provider
        self._engine = make_engine(engine_url)
        prepare_schema(self._engine)
        self._sessions = session_factory(self._engine)

    def add(self, chunks: list[CodeChunk]) -> list[UsageRecord]:
        if not chunks:
            return []
        texts = [redact_secrets(chunk.text) for chunk in chunks]
        result = self._provider.embed(texts, attempt=1)
        if len(result.vectors) != len(chunks):
            raise ValueError("embed returned a different count than the chunk list")
        with self._sessions() as session:
            session.execute(
                delete(CodeChunkRow).where(CodeChunkRow.job_id == self.job_id)
            )
            for chunk, vector in zip(chunks, result.vectors, strict=True):
                session.add(
                    CodeChunkRow(
                        job_id=self.job_id,
                        path=chunk.path,
                        chunk_index=chunk.index,
                        text=chunk.text,
                        embedding=vector,
                    )
                )
            session.commit()
        return [result.usage]

    def query(
        self, text: str, *, k: int = 4
    ) -> tuple[list[RetrievedChunk], UsageRecord]:
        result = self._provider.embed([redact_secrets(text)], attempt=1)
        if not result.vectors:
            return [], result.usage
        query_vec = result.vectors[0]
        with self._sessions() as session:
            stmt = (
                select(
                    CodeChunkRow.path,
                    CodeChunkRow.chunk_index,
                    CodeChunkRow.text,
                    CodeChunkRow.embedding.cosine_distance(query_vec),
                )
                .where(CodeChunkRow.job_id == self.job_id)
                .order_by(CodeChunkRow.embedding.cosine_distance(query_vec))
                .limit(k)
            )
            rows = session.execute(stmt).all()
        found = [
            RetrievedChunk(
                path=str(row[0]),
                index=int(row[1]),
                text=str(row[2]),
                score=1.0 - float(row[3]),
            )
            for row in rows
        ]
        return found, result.usage


def open_index(job_id: str, provider: LLMProvider) -> RetrievalIndex:
    """Use pgvector when DATABASE_URL connects, otherwise an in-memory index."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        try:
            index = PgvectorIndex(job_id, provider, url)
            logger.info(
                "retrieval using pgvector",
                extra={"job_id": job_id},
            )
            return index
        except Exception as exc:
            logger.warning(
                "pgvector unavailable, using memory index",
                extra={"job_id": job_id, "detail": str(exc)},
            )
    else:
        logger.info(
            "DATABASE_URL unset, using memory index",
            extra={"job_id": job_id},
        )
    return MemoryIndex(job_id, provider)


def index_tree(root: Path, index: RetrievalIndex) -> list[UsageRecord]:
    """Chunk and embed every source module under root."""
    chunks = chunk_tree(root)
    return index.add(chunks)


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return dot / (norm_l * norm_r)
