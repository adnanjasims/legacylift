"""Request and result types for untrusted code execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SandboxLimits:
    """Resource caps applied to every sandbox run."""

    timeout_sec: float = 60.0
    memory_mb: int = 256
    cpus: str = "1"
    pids: int = 64
    tmpfs_mb: int = 64


DEFAULT_LIMITS = SandboxLimits()

PY2_IMAGE = "python:2.7.18-slim"
PY3_IMAGE = "python:3.12-slim-bookworm"


@dataclass(frozen=True)
class SandboxRequest:
    """One command to run against a read-only workspace copy."""

    image: str
    workspace: Path
    argv: list[str]
    limits: SandboxLimits = DEFAULT_LIMITS
    platform: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of a sandbox run. timed_out means the hard timeout fired."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    argv: list[str]
