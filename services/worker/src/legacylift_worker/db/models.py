"""SQLAlchemy models for retrieval chunks. Job tables arrive with M3."""

from __future__ import annotations

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CodeChunkRow(Base):
    """One embedded window of a source file for a single job."""

    __tablename__ = "code_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(String(512))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Dimension is left open so granite-embedding-107m (384) and 278m (768) both fit.
    embedding: Mapped[list[float]] = mapped_column(VECTOR())
