from pathlib import Path

from legacylift_sandbox.docker_backend import docker_cli, docker_run_argv
from legacylift_sandbox.models import PY3_IMAGE, SandboxLimits, SandboxRequest


def test_docker_cli_returns_a_binary_name() -> None:
    binary = docker_cli()
    assert binary
    assert "docker" in Path(binary).name


def test_docker_run_argv_includes_isolation_flags(tmp_path: Path) -> None:
    request = SandboxRequest(
        image=PY3_IMAGE,
        workspace=tmp_path,
        argv=["python", "-c", "print(1)"],
        limits=SandboxLimits(memory_mb=128, pids=32),
        platform="linux/amd64",
    )
    argv = docker_run_argv(request, "legacylift-test")
    joined = " ".join(argv)
    assert argv[:3] == ["docker", "run", "--rm"]
    assert "--network" in argv and "none" in argv
    assert "--read-only" in argv
    assert "--user" in argv and "65534:65534" in argv
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--security-opt" in argv and "no-new-privileges" in argv
    assert "--memory" in argv and "128m" in argv
    assert "--pids-limit" in argv and "32" in argv
    assert "--platform" in argv and "linux/amd64" in argv
    assert f"{tmp_path.resolve()}:/input:ro" in argv
    assert "print(1)" in joined
    assert "--network host" not in joined
    assert "--privileged" not in argv


def test_docker_run_argv_mounts_extra_volumes(tmp_path: Path) -> None:
    cache = tmp_path / "m2"
    cache.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    request = SandboxRequest(
        image=PY3_IMAGE,
        workspace=tmp_path,
        argv=["true"],
        extra_ro=((str(cache), "/m2"),),
        extra_rw=((str(out), "/output"),),
    )
    argv = docker_run_argv(request, "legacylift-vol")
    assert f"{cache.resolve()}:/m2:ro" in argv
    assert f"{out.resolve()}:/output" in argv
    assert f"{tmp_path.resolve()}:/input:ro" in argv
