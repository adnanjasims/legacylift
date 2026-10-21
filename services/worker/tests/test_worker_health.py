import pytest
from fastapi.testclient import TestClient

from legacylift_worker.main import create_app, health_payload, ready_payload


def test_worker_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == health_payload()
    assert response.json()["service"] == "worker"


def test_worker_ready_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    client = TestClient(create_app())
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == ready_payload()
