import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is not installed")
def test_kind_overlay_renders_network_policy_and_ubi_worker() -> None:
    completed = subprocess.run(
        ["kubectl", "kustomize", str(_ROOT / "deploy" / "k8s" / "overlays" / "kind")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    text = completed.stdout
    assert "kind: NetworkPolicy" in text
    assert "name: deny-all" in text
    assert "legacylift-sandbox" in text
    assert "path: /health" in text
    assert "path: /ready" in text
    assert "legacylift-worker:local" in text
    assert "SANDBOX_BACKEND" in text
    assert "k8s" in text
