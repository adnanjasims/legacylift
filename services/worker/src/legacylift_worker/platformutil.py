"""Image platform selection for sandbox runs."""

from __future__ import annotations

import platform


def py2_docker_platform() -> str | None:
    """Return linux/amd64 on ARM hosts because python:2.7 images are amd64."""
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "linux/amd64"
    return None
