"""Deterministic Python 2 to 3 rewrite using CPython 3.12 lib2to3.

Official 3.12 docs: `2to3 -w -n` writes in place without backups.
lib2to3 is deprecated in 3.11 and removed in 3.13. This project pins
Python 3.12 so the stdlib tool is still present. Default fixers only;
the optional `division` fixer is off, so integer `/` stays `/`.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

from legacylift_worker.errors import PipelineError


def migrate_with_2to3(original: Path, migrated: Path) -> str:
    """Copy original to migrated and run 2to3 in place.

    Returns:
        Combined stdout and stderr from 2to3 (diffs disabled).
    """
    if migrated.exists():
        shutil.rmtree(migrated)
    shutil.copytree(original, migrated)
    cmd = [
        sys.executable,
        "-m",
        "lib2to3",
        "-w",
        "-n",
        "--no-diffs",
        str(migrated),
    ]
    completed = subprocess.run(  # nosec B603
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    log = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise PipelineError(f"2to3 failed with exit {completed.returncode}: {log}")
    return log
