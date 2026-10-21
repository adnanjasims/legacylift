from pathlib import Path

import pytest

from legacylift_sandbox import (
    PY3_IMAGE,
    DockerBackend,
    SandboxLimits,
    SandboxRequest,
    docker_available,
)

pytestmark = pytest.mark.skipif(
    not docker_available(),
    reason="docker daemon is not running",
)


def test_sandbox_executes_python(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("print(1)\n", encoding="utf-8")
    result = DockerBackend().run(
        SandboxRequest(
            image=PY3_IMAGE,
            workspace=tmp_path,
            argv=["python", "ok.py"],
            limits=SandboxLimits(timeout_sec=60),
        )
    )
    assert result.timed_out is False
    assert result.exit_code == 0
    assert "1" in result.stdout


def test_sandbox_blocks_network(tmp_path: Path) -> None:
    (tmp_path / "net.py").write_text(
        "import socket\n"
        "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "sock.settimeout(3)\n"
        "sock.connect(('1.1.1.1', 80))\n",
        encoding="utf-8",
    )
    result = DockerBackend().run(
        SandboxRequest(
            image=PY3_IMAGE,
            workspace=tmp_path,
            argv=["python", "net.py"],
            limits=SandboxLimits(timeout_sec=20),
        )
    )
    assert result.exit_code != 0
    assert result.timed_out is False


def test_sandbox_enforces_timeout(tmp_path: Path) -> None:
    (tmp_path / "sleep.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    result = DockerBackend().run(
        SandboxRequest(
            image=PY3_IMAGE,
            workspace=tmp_path,
            argv=["python", "sleep.py"],
            limits=SandboxLimits(timeout_sec=2),
        )
    )
    assert result.timed_out is True
    assert result.exit_code == 124
