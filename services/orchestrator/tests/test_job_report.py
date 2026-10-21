import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from legacylift_orchestrator.broker import MemoryBroker
from legacylift_orchestrator.main import create_app
from legacylift_orchestrator.store import MemoryJobStore


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-at-least-32b")
    store = MemoryJobStore()
    store.ensure_user("alice", "dev-alice", "user")
    return TestClient(create_app(store=store, broker=MemoryBroker()))


def _token(client: TestClient) -> str:
    response = client.post(
        "/auth/login", json={"username": "alice", "password": "dev-alice"}
    )
    assert response.status_code == 200
    return str(response.json()["token"])


def test_report_not_ready_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    token = _token(client)
    created = client.post(
        "/jobs",
        json={"source": "corpus/py2_pricing"},
        headers={"authorization": f"Bearer {token}"},
    )
    job_id = created.json()["id"]
    missing = client.get(
        f"/jobs/{job_id}/report", headers={"authorization": f"Bearer {token}"}
    )
    assert missing.status_code == 404


def test_events_snapshot_for_queued_job(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    token = _token(client)
    created = client.post(
        "/jobs",
        json={"source": "corpus/py2_pricing"},
        headers={"authorization": f"Bearer {token}"},
    )
    job_id = created.json()["id"]
    with client.stream(
        "GET",
        f"/jobs/{job_id}/events",
        headers={"authorization": f"Bearer {token}"},
    ) as stream:
        chunk = next(stream.iter_text())
    assert "queued" in chunk
    assert job_id in chunk


def test_upload_zip_creates_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    client = _client(monkeypatch)
    token = _token(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mod.py", "print 1\n")
    response = client.post(
        "/jobs/upload",
        headers={"authorization": f"Bearer {token}"},
        files={"file": ("sample.zip", buf.getvalue(), "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    job_id = response.json()["id"]
    assert (tmp_path / f"{job_id}.zip").is_file()


def test_complete_exposes_report_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "report.json").write_text(
        json.dumps({"job_id": "x", "files": [], "usage": []}), encoding="utf-8"
    )
    monkeypatch.setenv("INTERNAL_TOKEN", "unit-internal")
    client = _client(monkeypatch)
    token = _token(client)
    created = client.post(
        "/jobs",
        json={"source": "corpus/py2_pricing"},
        headers={"authorization": f"Bearer {token}"},
    )
    job_id = created.json()["id"]
    done = client.post(
        f"/internal/jobs/{job_id}/complete",
        headers={"x-internal-token": "unit-internal"},
        json={"report_dir": str(tmp_path)},
    )
    assert done.status_code == 200
    report = client.get(
        f"/jobs/{job_id}/report", headers={"authorization": f"Bearer {token}"}
    )
    assert report.status_code == 200
    assert report.json()["job_id"] == "x"
