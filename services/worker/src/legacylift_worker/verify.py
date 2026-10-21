"""Re-run kept characterization tests and compile migrated code in the sandbox."""

from __future__ import annotations

from pathlib import Path

from legacylift_sandbox import PY3_IMAGE, DockerBackend, SandboxLimits, SandboxRequest
from legacylift_worker.characterize import SuiteRun, run_unittest
from legacylift_worker.errors import PipelineError


def compile_migrated(
    migrated: Path,
    backend: DockerBackend,
    limits: SandboxLimits,
) -> SuiteRun:
    """Run python -m compileall on the migrated tree."""
    result = backend.run(
        SandboxRequest(
            image=PY3_IMAGE,
            workspace=migrated,
            argv=["python", "-m", "compileall", "-q", "."],
            limits=limits,
        )
    )
    return SuiteRun(
        records=[],
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
    )


def verify_migrated(
    migrated: Path,
    backend: DockerBackend,
    limits: SandboxLimits,
) -> tuple[SuiteRun, SuiteRun]:
    """Compile then run characterization tests on migrated code under Python 3.12."""
    compiled = compile_migrated(migrated, backend, limits)
    if compiled.timed_out:
        raise PipelineError("compileall timed out on migrated code")
    tests = run_unittest(migrated, backend, limits, PY3_IMAGE)
    return compiled, tests
