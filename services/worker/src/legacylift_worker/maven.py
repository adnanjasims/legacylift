"""Maven helpers for Java characterization and OpenRewrite."""

from __future__ import annotations

import os
import re
from pathlib import Path

from legacylift_sandbox import (
    JAVA8_IMAGE,
    JAVA21_IMAGE,
    JAVA_LIMITS,
    DockerBackend,
    SandboxLimits,
    SandboxRequest,
)
from legacylift_worker.characterize import SuiteRun
from legacylift_worker.errors import PipelineError

REWRITE_PLUGIN = "org.openrewrite.maven:rewrite-maven-plugin:6.46.1"
REWRITE_RECIPES = "org.openrewrite.recipe:rewrite-migrate-java:3.42.1"
REWRITE_RECIPE = "org.openrewrite.java.migrate.UpgradeToJava21"

_CLASS_LINE = re.compile(r"Running ([A-Za-z0-9_.]+)")
_COUNT_LINE = re.compile(
    r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)(?:.*-- in ([A-Za-z0-9_.]+))?"
)


def is_maven_tree(root: Path) -> bool:
    return (root / "pom.xml").is_file()


def maven_repo() -> Path:
    raw = os.environ.get("MAVEN_REPO_LOCAL", "").strip()
    path = Path(raw) if raw else Path(__file__).resolve().parents[4] / "reports" / "m2"
    if not path.is_dir() or not any(path.iterdir()):
        raise PipelineError(
            "Maven local repo is empty. Run make java-deps so mvn can run offline."
        )
    return path.resolve()


def maven_argv(*goals: str, copy_output: bool = False) -> list[str]:
    """Offline Maven. Copy /m2 to /tmp/m2 so the ro cache is not written."""
    mvn = [
        "mvn",
        "-B",
        "-o",
        "-Dmaven.repo.local=/tmp/m2",
        "-Duser.home=/tmp",
        *goals,
    ]
    if copy_output:
        script = 'cp -a /m2 /tmp/m2 && "$@" ; st=$? ; cp -a . /output/ ; exit $st'
    else:
        script = 'cp -a /m2 /tmp/m2 && exec "$@"'
    return ["sh", "-c", script, "sh", *mvn]


def rewrite_argv() -> list[str]:
    """Official plugin coordinates plus Central recipe artifact (no pom edit)."""
    return maven_argv(
        f"{REWRITE_PLUGIN}:run",
        f"-Drewrite.activeRecipes={REWRITE_RECIPE}",
        f"-Drewrite.recipeArtifactCoordinates={REWRITE_RECIPES}",
        "-Drewrite.pomCacheEnabled=false",
        copy_output=True,
    )


def run_maven(
    workspace: Path,
    backend: DockerBackend,
    *,
    image: str,
    argv: list[str],
    limits: SandboxLimits = JAVA_LIMITS,
    copy_output: bool = False,
) -> SuiteRun:
    repo = maven_repo()
    extra_rw: tuple[tuple[str, str], ...] = ()
    if copy_output:
        _world_writable(workspace)
        extra_rw = ((str(workspace.resolve()), "/output"),)
    result = backend.run(
        SandboxRequest(
            image=image,
            workspace=workspace,
            argv=argv,
            limits=limits,
            extra_ro=((str(repo), "/m2"),),
            extra_rw=extra_rw,
            env={
                "MAVEN_OPTS": "-Xmx512m -Djava.awt.headless=true",
            },
        )
    )
    return SuiteRun(
        records=parse_surefire(result.stdout + "\n" + result.stderr),
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
    )


def run_maven_tests(
    workspace: Path,
    backend: DockerBackend,
    *,
    image: str,
    limits: SandboxLimits = JAVA_LIMITS,
) -> SuiteRun:
    return run_maven(
        workspace, backend, image=image, argv=maven_argv("test"), limits=limits
    )


def compile_java(
    workspace: Path,
    backend: DockerBackend,
    limits: SandboxLimits = JAVA_LIMITS,
) -> SuiteRun:
    return run_maven(
        workspace,
        backend,
        image=JAVA21_IMAGE,
        argv=maven_argv("-DskipTests", "test-compile"),
        limits=limits,
    )


def characterize_java(
    original: Path,
    backend: DockerBackend,
    limits: SandboxLimits = JAVA_LIMITS,
) -> SuiteRun:
    """Run the project's JUnit 5 suite on Java 8, (tests ship with the sample)"""
    run = run_maven_tests(original, backend, image=JAVA8_IMAGE, limits=limits)
    if run.timed_out:
        raise PipelineError("Java 8 mvn test timed out")
    if run.exit_code != 0:
        raise PipelineError(
            "Java 8 characterization tests failed on the original tree: "
            f"exit={run.exit_code}\n{run.stderr[-1500:]}"
        )
    return run


def parse_surefire(log: str) -> list[dict[str, str]]:
    """Turn Maven surefire console lines into SuiteRun records."""
    records: list[dict[str, str]] = []
    current = ""
    for line in log.splitlines():
        class_match = _CLASS_LINE.search(line)
        if class_match:
            current = class_match.group(1)
        count = _COUNT_LINE.search(line)
        if count is None:
            continue
        total = int(count.group(1))
        failed = int(count.group(2)) + int(count.group(3))
        ident = count.group(4) or current or "unknown"
        passed = max(total - failed, 0)
        records.extend({"id": ident, "status": "pass"} for _ in range(passed))
        records.extend(
            {"id": ident, "status": "fail", "detail": line.strip()}
            for _ in range(failed)
        )
    return records


def _world_writable(root: Path) -> None:
    """nobody (65534) must write rewrite output back onto the host tree."""
    for path in [root, *root.rglob("*")]:
        path.chmod(0o777 if path.is_dir() else 0o666)  # nosec B103
