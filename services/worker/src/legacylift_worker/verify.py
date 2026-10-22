"""Re-run kept characterization tests and compile migrated code in the sandbox."""

from __future__ import annotations

from pathlib import Path

from legacylift_sandbox import (
    JAVA21_IMAGE,
    JAVA_LIMITS,
    PY3_IMAGE,
    SandboxBackend,
    SandboxLimits,
    SandboxRequest,
)
from legacylift_worker.characterize import SuiteRun, run_unittest
from legacylift_worker.errors import PipelineError
from legacylift_worker.maven import compile_java, is_maven_tree, run_maven_tests


def compile_migrated(
    migrated: Path,
    backend: SandboxBackend,
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
    backend: SandboxBackend,
    limits: SandboxLimits,
) -> tuple[SuiteRun, SuiteRun]:
    """Compile then run tests on the migrated tree (Python 3.12 or Java 21)."""
    if is_maven_tree(migrated):
        compiled = compile_java(migrated, backend, JAVA_LIMITS)
        if compiled.timed_out:
            raise PipelineError("Java test-compile timed out")
        tests = run_maven_tests(
            migrated, backend, image=JAVA21_IMAGE, limits=JAVA_LIMITS
        )
        return compiled, tests
    compiled = compile_migrated(migrated, backend, limits)
    if compiled.timed_out:
        raise PipelineError("compileall timed out on migrated code")
    tests = run_unittest(migrated, backend, limits, PY3_IMAGE)
    return compiled, tests
