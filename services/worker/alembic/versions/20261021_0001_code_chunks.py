"""code_chunks table with pgvector column

Revision ID: 20261021_0001
Revises:
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "20261021_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "code_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_chunks_job_id", "code_chunks", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_code_chunks_job_id", table_name="code_chunks")
    op.drop_table("code_chunks")
