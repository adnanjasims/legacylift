"""Apply OpenRewrite UpgradeToJava21 via the official Maven plugin CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

from legacylift_sandbox import JAVA21_IMAGE, JAVA_LIMITS, DockerBackend, SandboxLimits
from legacylift_worker.errors import PipelineError
from legacylift_worker.maven import rewrite_argv, run_maven


def migrate_with_rewrite(
    original: Path,
    migrated: Path,
    backend: DockerBackend,
    limits: SandboxLimits = JAVA_LIMITS,
) -> str:
    """Copy the Maven tree and run org.openrewrite.java.migrate.UpgradeToJava21."""
    if migrated.exists():
        shutil.rmtree(migrated)
    shutil.copytree(original, migrated)
    run = run_maven(
        migrated,
        backend,
        image=JAVA21_IMAGE,
        argv=rewrite_argv(),
        limits=limits,
        copy_output=True,
    )
    if run.timed_out:
        raise PipelineError("OpenRewrite timed out")
    if run.exit_code != 0:
        raise PipelineError(
            "OpenRewrite rewrite:run failed: "
            f"exit={run.exit_code}\n{(run.stderr or run.stdout)[-2000:]}"
        )
    return run.stdout + run.stderr
