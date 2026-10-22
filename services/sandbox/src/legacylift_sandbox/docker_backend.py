"""Run untrusted commands in Docker with isolation flags.

Uploaded code is copied from a read-only bind mount into a tmpfs work
dir. The container has no network, a read-only root, dropped caps, a
non-root user, and memory/cpu/pid caps.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import time
import uuid
from pathlib import Path
from typing import Final

from legacylift_sandbox.models import SandboxRequest, SandboxResult

DOCKER_BIN: Final = "docker"
SANDBOX_USER: Final = "65534:65534"
MAX_OUTPUT_BYTES: Final = 1_000_000
_DOCKER_CANDIDATES: Final = (
    "/usr/bin/docker",
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
)


class SandboxError(RuntimeError):
    """Docker is missing, the daemon is down, or the run cannot start."""


def docker_cli() -> str:
    """Return a docker binary that can talk to the daemon, if one exists."""
    found = shutil.which(DOCKER_BIN)
    for candidate in (found, *_DOCKER_CANDIDATES):
        if candidate and _docker_talks(candidate):
            return candidate
    return found or "/usr/bin/docker"


def docker_available() -> bool:
    """Return True when the docker CLI can talk to a daemon."""
    return _docker_talks(docker_cli())


def docker_subprocess_env() -> dict[str, str]:
    """Keep DOCKER_HOST so uv-launched Python can reach the GHA socket."""
    env = os.environ.copy()
    socket = Path("/var/run/docker.sock")
    if "DOCKER_HOST" not in env and socket.exists():
        env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    return env


def _docker_talks(binary: str) -> bool:
    if not binary:
        return False
    path = Path(binary)
    if path.is_absolute() and not path.is_file():
        return False
    env = docker_subprocess_env()
    for argv in (
        [binary, "version", "--format", "{{.Server.Version}}"],
        [binary, "info"],
    ):
        try:
            probe = subprocess.run(  # nosec B603
                argv,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return True
    return False


def docker_run_argv(request: SandboxRequest, container_name: str) -> list[str]:
    """Build the docker run command. Tests assert isolation flags here."""
    workspace = request.workspace.resolve()
    memory = f"{request.limits.memory_mb}m"
    tmpfs = f"/tmp:rw,noexec,nosuid,size={request.limits.tmpfs_mb}m"  # nosec B108
    argv: list[str] = [
        DOCKER_BIN,
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--user",
        SANDBOX_USER,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        memory,
        "--memory-swap",
        memory,
        "--cpus",
        request.limits.cpus,
        "--pids-limit",
        str(request.limits.pids),
        "--tmpfs",
        tmpfs,
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "PYTHONUNBUFFERED=1",
        "-v",
        f"{workspace}:/input:ro",
        "-w",
        "/tmp",  # nosec B108
    ]
    if request.platform:
        argv.extend(["--platform", request.platform])
    for host, dest in request.extra_ro:
        argv.extend(["-v", f"{host}:{dest}:ro"])
    for host, dest in request.extra_rw:
        argv.extend(["-v", f"{host}:{dest}"])
    for key, value in request.env.items():
        argv.extend(["-e", f"{key}={value}"])
    inner = (
        "mkdir -p /tmp/work && cp -a /input/. /tmp/work/ "
        '&& cd /tmp/work && exec "$@"'  # nosec B108
    )
    argv.extend([request.image, "sh", "-c", inner, "sh", *request.argv])
    return argv


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _clip(text: str) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")


class DockerBackend:
    """Execute SandboxRequest values via the local docker CLI."""

    def run(self, request: SandboxRequest) -> SandboxResult:
        """Run argv inside an isolated container.

        Args:
            request: Image, workspace, command, and limits.

        Returns:
            Captured stdout/stderr, exit code, and timeout flag.

        Raises:
            SandboxError: docker CLI or daemon is not usable.
        """
        binary = docker_cli()
        if not docker_available():
            raise SandboxError("docker daemon is not running")
        if not request.workspace.is_dir():
            raise SandboxError(f"workspace is not a directory: {request.workspace}")

        name = f"legacylift-{uuid.uuid4().hex[:12]}"
        argv = docker_run_argv(request, name)
        argv[0] = binary
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(  # nosec B603
                argv,
                capture_output=True,
                text=True,
                timeout=request.limits.timeout_sec,
                check=False,
                env=docker_subprocess_env(),
            )
            exit_code = completed.returncode
            stdout = _as_text(completed.stdout)
            stderr = _as_text(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = 124
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            subprocess.run(  # nosec B603
                [binary, "kill", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=docker_subprocess_env(),
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        return SandboxResult(
            exit_code=exit_code,
            stdout=_clip(stdout),
            stderr=_clip(stderr),
            timed_out=timed_out,
            duration_ms=duration_ms,
            argv=argv,
        )
