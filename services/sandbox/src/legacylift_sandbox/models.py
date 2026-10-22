"""Request and result types for untrusted code execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


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
JAVA8_IMAGE = "maven:3.9-eclipse-temurin-8"
JAVA21_IMAGE = "maven:3.9-eclipse-temurin-21"
JAVA_LIMITS = SandboxLimits(
    timeout_sec=300.0, memory_mb=1536, cpus="1", pids=256, tmpfs_mb=1024
)


@dataclass(frozen=True)
class SandboxRequest:
    """One command to run against a read-only workspace copy."""

    image: str
    workspace: Path
    argv: list[str]
    limits: SandboxLimits = DEFAULT_LIMITS
    platform: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    extra_ro: tuple[tuple[str, str], ...] = ()
    extra_rw: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of a sandbox run. timed_out means the hard timeout fired."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    argv: list[str]


class SandboxBackend(Protocol):
    """DockerBackend and K8sJobBackend both implement run()."""

    def run(self, request: SandboxRequest) -> SandboxResult:
        """Execute argv against the workspace and return captured output."""
        ...
