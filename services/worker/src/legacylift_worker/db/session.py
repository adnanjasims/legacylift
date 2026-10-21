"""SQLAlchemy engine helpers for DATABASE_URL."""

from __future__ import annotations

import os
from typing import Any

from pgvector.psycopg import register_vector
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from legacylift_worker.db.models import Base
from legacylift_worker.errors import PipelineError


def sqlalchemy_url(raw: str | None = None) -> str:
    """Return a SQLAlchemy URL. psycopg3 needs the +psycopg driver name."""
    value = raw if raw is not None else os.environ.get("DATABASE_URL", "")
    value = value.strip()
    if not value:
        raise PipelineError("DATABASE_URL is empty")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


def make_engine(url: str | None = None) -> Engine:
    """Create an engine and register pgvector on every DBAPI connection."""
    engine = create_engine(sqlalchemy_url(url), pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _register_vector(dbapi_connection: Any, _record: object) -> None:
        register_vector(dbapi_connection)

    return engine


def prepare_schema(engine: Engine) -> None:
    """Create the vector extension and tables if they are missing."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(conn)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
