from pathlib import Path

import pytest

from legacylift_sandbox import docker_available
from legacylift_worker.errors import PipelineError
from legacylift_worker.maven import maven_repo
from legacylift_worker.pipeline import run_migration

_REPO = Path(__file__).resolve().parents[3]


def _java_ready() -> bool:
    if not docker_available():
        return False
    try:
        maven_repo()
    except PipelineError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _java_ready(),
    reason="docker daemon or reports/m2 (make java-deps) is missing",
)


def test_java8_box_rewrite_verifies(tmp_path: Path) -> None:
    report = run_migration(str(_REPO / "corpus" / "java8_box"), tmp_path)
    assert report.language == "java"
    assert report.files
    box = next(item for item in report.files if item.path.endswith("Box.java"))
    migrated = (tmp_path / "migrated" / box.path).read_text(encoding="utf-8")
    assert "new Integer(" not in migrated
    assert box.tests_before_passed >= 2
    assert box.tests_before_failed == 0
    assert box.status == "verified"
