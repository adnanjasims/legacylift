"""Run untrusted commands as Kubernetes Jobs with a locked-down securityContext."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess  # nosec B404
import tarfile
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Final

from legacylift_sandbox.docker_backend import DockerBackend, SandboxError
from legacylift_sandbox.models import SandboxRequest, SandboxResult

KUBECTL_BIN: Final = "kubectl"
SANDBOX_NAMESPACE: Final = "legacylift-sandbox"
MAX_ARCHIVE_BYTES: Final = 900_000
MAX_OUTPUT_BYTES: Final = 1_000_000


def kubectl_cli() -> str:
    """Return kubectl. CI and kind nodes sometimes omit it from PATH."""
    return shutil.which(KUBECTL_BIN) or "/usr/local/bin/kubectl"


def k8s_available() -> bool:
    """Return True when kubectl can reach a cluster."""
    try:
        probe = subprocess.run(  # nosec B603
            [kubectl_cli(), "get", "ns", SANDBOX_NAMESPACE],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def pod_security_context() -> dict[str, Any]:
    """Restrictive context applied to every sandbox Job pod."""
    return {
        "runAsNonRoot": True,
        "runAsUser": 65534,
        "runAsGroup": 65534,
        "fsGroup": 65534,
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def container_security_context() -> dict[str, Any]:
    """Container flags: no extra caps, no privilege escalation, read-only root."""
    return {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "runAsNonRoot": True,
        "runAsUser": 65534,
        "runAsGroup": 65534,
        "capabilities": {"drop": ["ALL"]},
    }


def job_manifest(
    request: SandboxRequest,
    *,
    job_name: str,
    config_map: str,
    namespace: str = SANDBOX_NAMESPACE,
) -> dict[str, Any]:
    """Build a batch/v1 Job for one SandboxRequest. No cluster call."""
    memory = f"{request.limits.memory_mb}Mi"
    tmpfs = f"{request.limits.tmpfs_mb}Mi"
    volumes: list[dict[str, Any]] = [
        {"name": "input", "configMap": {"name": config_map}},
        {"name": "tmp", "emptyDir": {"sizeLimit": tmpfs}},
    ]
    mounts: list[dict[str, Any]] = [
        {"name": "input", "mountPath": "/input", "readOnly": True},
        {"name": "tmp", "mountPath": "/tmp"},  # nosec B108
    ]
    for index, (host, dest) in enumerate(request.extra_ro):
        name = f"ro{index}"
        volumes.append(
            {
                "name": name,
                "hostPath": {
                    "path": str(Path(host).resolve()),
                    "type": "Directory",
                },
            }
        )
        mounts.append({"name": name, "mountPath": dest, "readOnly": True})
    for index, (host, dest) in enumerate(request.extra_rw):
        name = f"rw{index}"
        volumes.append(
            {
                "name": name,
                "hostPath": {
                    "path": str(Path(host).resolve()),
                    "type": "Directory",
                },
            }
        )
        mounts.append({"name": name, "mountPath": dest})
    env = [{"name": key, "value": value} for key, value in request.env.items()]
    inner = (
        "mkdir -p /tmp/work && tar -C /tmp/work -xf /input/workspace.tar "
        '&& cd /tmp/work && exec "$@"'  # nosec B108
    )
    container: dict[str, Any] = {
        "name": "run",
        "image": request.image,
        "imagePullPolicy": "IfNotPresent",
        "securityContext": container_security_context(),
        "resources": {
            "limits": {"memory": memory, "cpu": request.limits.cpus},
            "requests": {"memory": "32Mi", "cpu": "100m"},
        },
        "volumeMounts": mounts,
        "command": ["sh", "-c", inner, "sh", *request.argv],
    }
    if env:
        container["env"] = env
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "namespace": namespace},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 120,
            "activeDeadlineSeconds": int(request.limits.timeout_sec),
            "template": {
                "metadata": {"labels": {"job-name": job_name}},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "securityContext": pod_security_context(),
                    "containers": [container],
                    "volumes": volumes,
                },
            },
        },
    }


class K8sJobBackend:
    """Execute SandboxRequest values as Jobs via kubectl."""

    def __init__(self, namespace: str = SANDBOX_NAMESPACE) -> None:
        self.namespace = namespace

    def run(self, request: SandboxRequest) -> SandboxResult:
        """Create a Job, wait, collect logs, then delete the Job and ConfigMap."""
        binary = kubectl_cli()
        if not k8s_available():
            raise SandboxError("kubectl cannot reach the sandbox namespace")
        if not request.workspace.is_dir():
            raise SandboxError(f"workspace is not a directory: {request.workspace}")
        stamp = uuid.uuid4().hex[:12]
        job_name = f"legacylift-{stamp}"
        config_name = f"{job_name}-input"
        archive = _workspace_tar(request.workspace)
        started = time.monotonic()
        timed_out = False
        try:
            _apply_config_map(binary, self.namespace, config_name, archive)
            manifest = job_manifest(
                request,
                job_name=job_name,
                config_map=config_name,
                namespace=self.namespace,
            )
            _apply_json(binary, manifest)
            timed_out = not _wait_for_job(
                binary, self.namespace, job_name, request.limits.timeout_sec
            )
            stdout, stderr, exit_code = _job_outcome(
                binary, self.namespace, job_name, timed_out
            )
        finally:
            _delete(binary, self.namespace, "job", job_name)
            _delete(binary, self.namespace, "configmap", config_name)
        duration_ms = int((time.monotonic() - started) * 1000)
        argv = [binary, "apply", "-f", "-", job_name]
        return SandboxResult(
            exit_code=exit_code,
            stdout=_clip(stdout),
            stderr=_clip(stderr),
            timed_out=timed_out,
            duration_ms=duration_ms,
            argv=argv,
        )


def _workspace_tar(workspace: Path) -> bytes:
    buffer = tempfile.SpooledTemporaryFile(max_size=MAX_ARCHIVE_BYTES)
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path in sorted(workspace.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            tar.add(path, arcname=path.relative_to(workspace).as_posix())
    buffer.seek(0)
    data = buffer.read()
    buffer.close()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise SandboxError(
            f"workspace tar exceeds {MAX_ARCHIVE_BYTES} bytes (ConfigMap limit)"
        )
    return data


def _apply_config_map(binary: str, namespace: str, name: str, archive: bytes) -> None:
    payload = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": namespace},
        "binaryData": {"workspace.tar": base64.b64encode(archive).decode("ascii")},
    }
    _apply_json(binary, payload)


def _apply_json(binary: str, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload)
    completed = subprocess.run(  # nosec B603
        [binary, "apply", "-f", "-"],
        input=encoded,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise SandboxError(f"kubectl apply failed: {completed.stderr.strip()}")


def _wait_for_job(binary: str, namespace: str, name: str, timeout_sec: float) -> bool:
    completed = subprocess.run(  # nosec B603
        [
            binary,
            "wait",
            "--for=condition=complete",
            f"job/{name}",
            "-n",
            namespace,
            f"--timeout={max(int(timeout_sec), 1)}s",
        ],
        capture_output=True,
        text=True,
        timeout=timeout_sec + 15,
        check=False,
    )
    return completed.returncode == 0


def _job_outcome(
    binary: str, namespace: str, name: str, timed_out: bool
) -> tuple[str, str, int]:
    logs = subprocess.run(  # nosec B603
        [binary, "logs", f"job/{name}", "-n", namespace],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    stdout = logs.stdout or ""
    stderr = logs.stderr or ""
    if timed_out:
        return stdout, stderr, 124
    failed = subprocess.run(  # nosec B603
        [
            binary,
            "get",
            f"job/{name}",
            "-n",
            namespace,
            "-o",
            "jsonpath={.status.failed}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if (failed.stdout or "").strip() not in {"", "0"}:
        return stdout, stderr, 1
    return stdout, stderr, 0


def _delete(binary: str, namespace: str, kind: str, name: str) -> None:
    subprocess.run(  # nosec B603
        [binary, "delete", kind, name, "-n", namespace, "--ignore-not-found"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def sandbox_backend() -> DockerBackend | K8sJobBackend:
    """Return the backend selected by SANDBOX_BACKEND (docker or k8s)."""
    kind = os.environ.get("SANDBOX_BACKEND", "docker").strip().lower()
    if kind in {"k8s", "kubernetes"}:
        return K8sJobBackend()
    return DockerBackend()


def _clip(text: str) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
