from pathlib import Path

import pytest

from legacylift_sandbox.docker_backend import DockerBackend
from legacylift_sandbox.k8s_backend import (
    K8sJobBackend,
    container_security_context,
    job_manifest,
    sandbox_backend,
)
from legacylift_sandbox.models import PY3_IMAGE, SandboxLimits, SandboxRequest


def test_job_manifest_locks_down_security(tmp_path: Path) -> None:
    request = SandboxRequest(
        image=PY3_IMAGE,
        workspace=tmp_path,
        argv=["python", "-c", "print(1)"],
        limits=SandboxLimits(memory_mb=128, pids=32),
    )
    manifest = job_manifest(request, job_name="legacylift-test", config_map="input")
    spec = manifest["spec"]["template"]["spec"]
    container = spec["containers"][0]
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["runAsUser"] == 65534
    assert spec["automountServiceAccountToken"] is False
    ctx = container["securityContext"]
    assert ctx == container_security_context()
    assert ctx["allowPrivilegeEscalation"] is False
    assert ctx["readOnlyRootFilesystem"] is True
    assert ctx["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["limits"]["memory"] == "128Mi"
    assert manifest["spec"]["backoffLimit"] == 0


def test_job_manifest_mounts_extra_ro(tmp_path: Path) -> None:
    cache = tmp_path / "m2"
    cache.mkdir()
    request = SandboxRequest(
        image=PY3_IMAGE,
        workspace=tmp_path,
        argv=["true"],
        extra_ro=((str(cache), "/m2"),),
    )
    manifest = job_manifest(request, job_name="legacylift-vol", config_map="input")
    spec = manifest["spec"]["template"]["spec"]
    mounts = spec["containers"][0]["volumeMounts"]
    assert any(item["mountPath"] == "/m2" and item.get("readOnly") for item in mounts)
    volumes = spec["volumes"]
    assert any("hostPath" in item for item in volumes)


def test_sandbox_backend_defaults_to_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_BACKEND", raising=False)
    assert isinstance(sandbox_backend(), DockerBackend)
    monkeypatch.setenv("SANDBOX_BACKEND", "k8s")
    assert isinstance(sandbox_backend(), K8sJobBackend)
