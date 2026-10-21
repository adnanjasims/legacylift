import pytest
from fastapi.testclient import TestClient

from legacylift_orchestrator.broker import MemoryBroker
from legacylift_orchestrator.main import create_app
from legacylift_orchestrator.store import MemoryJobStore


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, MemoryBroker]:
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-at-least-32b")
    store = MemoryJobStore()
    store.ensure_user("alice", "dev-alice", "user")
    store.ensure_user("bob", "dev-bob", "user")
    broker = MemoryBroker()
    return TestClient(create_app(store=store, broker=broker)), broker


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    token = response.json()["token"]
    assert isinstance(token, str)
    return token


def test_bob_cannot_read_alice_job(monkeypatch: pytest.MonkeyPatch) -> None:
    client, broker = _client(monkeypatch)
    alice = _login(client, "alice", "dev-alice")
    bob = _login(client, "bob", "dev-bob")
    created = client.post(
        "/jobs",
        json={"source": "corpus/py2_pricing"},
        headers={"authorization": f"Bearer {alice}"},
    )
    assert created.status_code == 200
    job_id = created.json()["id"]
    assert len(broker.jobs) == 1
    assert broker.jobs[0].job_id == job_id
    forbidden = client.get(
        f"/jobs/{job_id}", headers={"authorization": f"Bearer {bob}"}
    )
    assert forbidden.status_code == 404
    allowed = client.get(
        f"/jobs/{job_id}", headers={"authorization": f"Bearer {alice}"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["id"] == job_id


def test_login_rejects_bad_password(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _broker = _client(monkeypatch)
    response = client.post(
        "/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 401


def test_admin_can_read_alice_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-at-least-32b")
    store = MemoryJobStore()
    store.ensure_user("alice", "dev-alice", "user")
    store.ensure_user("root", "dev-root", "admin")
    broker = MemoryBroker()
    client = TestClient(create_app(store=store, broker=broker))
    alice = _login(client, "alice", "dev-alice")
    admin = _login(client, "root", "dev-root")
    created = client.post(
        "/jobs",
        json={"source": "corpus/py2_pricing"},
        headers={"authorization": f"Bearer {alice}"},
    )
    job_id = created.json()["id"]
    allowed = client.get(
        f"/jobs/{job_id}", headers={"authorization": f"Bearer {admin}"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["id"] == job_id
