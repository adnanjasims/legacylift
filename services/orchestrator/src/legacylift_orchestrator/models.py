"""Users and jobs. Status values are written by the orchestrator and worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "admin"]
JobStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "dead_lettered",
]


@dataclass
class User:
    id: str
    username: str
    password_hash: str
    role: Role


@dataclass
class Job:
    id: str
    user_id: str
    source: str
    status: JobStatus
    attempt: int
    error: str | None = None
    report_dir: str | None = None
