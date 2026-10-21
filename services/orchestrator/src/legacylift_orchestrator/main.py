"""HTTP app: health, login, jobs, and worker callbacks."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from legacylift_orchestrator.broker import (
    Broker,
    MemoryBroker,
    PikaBroker,
    QueueMessage,
)
from legacylift_orchestrator.jsonlog import configure_logging
from legacylift_orchestrator.models import JobStatus, User
from legacylift_orchestrator.store import JobStore, MemoryJobStore
from legacylift_orchestrator.tokens import decode_token, issue_token, jwt_secret

SERVICE_NAME = "orchestrator"


class LoginBody(BaseModel):
    username: str
    password: str


class CreateJobBody(BaseModel):
    source: str = Field(min_length=1)


class JobFailBody(BaseModel):
    attempt: int
    error: str = ""


class JobCompleteBody(BaseModel):
    report_dir: str = ""


def health_payload() -> dict[str, str]:
    """Return the liveness body used by GET /health."""
    return {"status": "ok", "service": SERVICE_NAME}


def ready_payload() -> dict[str, str]:
    """Return the readiness body used by GET /ready when deps are up."""
    return {"status": "ok", "service": SERVICE_NAME}


def seed_store(store: JobStore) -> JobStore:
    """Create the two local users used by isolation tests."""
    store.ensure_user(
        "alice", os.environ.get("SEED_PASSWORD_ALICE", "dev-alice"), "user"
    )
    store.ensure_user("bob", os.environ.get("SEED_PASSWORD_BOB", "dev-bob"), "user")
    return store


def create_app(
    store: JobStore | None = None,
    broker: Broker | None = None,
) -> FastAPI:
    """Build the FastAPI application without binding a socket."""
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    job_store = store if store is not None else seed_store(MemoryJobStore())
    rabbit_url = os.environ.get("RABBITMQ_URL", "").strip()
    job_broker: Broker
    if broker is not None:
        job_broker = broker
    elif rabbit_url:
        job_broker = PikaBroker(rabbit_url)
    else:
        job_broker = MemoryBroker()

    application = FastAPI(title="LegacyLift Orchestrator", version="0.1.0")
    application.state.store = job_store
    application.state.broker = job_broker

    @application.get("/health")
    def health() -> Mapping[str, str]:
        """Liveness: the process is accepting HTTP."""
        return health_payload()

    @application.get("/ready")
    def ready() -> JSONResponse:
        """Readiness: HTTP is up. RabbitMQ is probed when RABBITMQ_URL is set."""
        if rabbit_url:
            try:
                import pika

                connection = pika.BlockingConnection(pika.URLParameters(rabbit_url))
                connection.close()
            except Exception:
                return JSONResponse(
                    {"status": "unavailable", "service": SERVICE_NAME},
                    status_code=503,
                )
        return JSONResponse(ready_payload())

    @application.post("/auth/login")
    def login(body: LoginBody) -> dict[str, str]:
        if not jwt_secret():
            raise HTTPException(status_code=503, detail="JWT_SECRET is not set")
        user = job_store.authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        return {
            "token": issue_token(user),
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
        }

    @application.post("/jobs")
    def create_job(body: CreateJobBody, request: Request) -> dict[str, str]:
        actor = _actor(request, job_store)
        job = job_store.create_job(actor.id, body.source)
        job_broker.publish(QueueMessage(job_id=job.id, source=job.source, attempt=1))
        return {"id": job.id, "status": job.status}

    @application.get("/jobs/{job_id}")
    def read_job(job_id: str, request: Request) -> dict[str, Any]:
        actor = _actor(request, job_store)
        job = job_store.visible_job(job_id, actor)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "id": job.id,
            "source": job.source,
            "status": job.status,
            "attempt": job.attempt,
            "error": job.error,
            "report_dir": job.report_dir,
        }

    @application.get("/internal/jobs/{job_id}")
    def internal_job(
        job_id: str, x_internal_token: str = Header(default="")
    ) -> dict[str, Any]:
        _require_internal(x_internal_token)
        job = job_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "id": job.id,
            "source": job.source,
            "status": job.status,
            "attempt": job.attempt,
        }

    @application.post("/internal/jobs/{job_id}/running")
    def internal_running(
        job_id: str, x_internal_token: str = Header(default="")
    ) -> dict[str, str]:
        _require_internal(x_internal_token)
        job = job_store.set_status(job_id, "running")
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"id": job.id, "status": job.status}

    @application.post("/internal/jobs/{job_id}/complete")
    def internal_complete(
        job_id: str,
        body: JobCompleteBody,
        x_internal_token: str = Header(default=""),
    ) -> dict[str, str]:
        _require_internal(x_internal_token)
        job = job_store.set_status(job_id, "completed", report_dir=body.report_dir)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"id": job.id, "status": job.status}

    @application.post("/internal/jobs/{job_id}/fail")
    def internal_fail(
        job_id: str,
        body: JobFailBody,
        x_internal_token: str = Header(default=""),
    ) -> dict[str, str]:
        _require_internal(x_internal_token)
        status: JobStatus = "dead_lettered" if body.attempt >= 3 else "failed"
        job = job_store.set_status(
            job_id, status, attempt=body.attempt, error=body.error
        )
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"id": job.id, "status": job.status}

    return application


def _actor(request: Request, store: JobStore) -> User:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    user_id = str(payload.get("sub", ""))
    user = store.user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user


def _require_internal(token: str) -> None:
    expected = os.environ.get("INTERNAL_TOKEN", "").strip()
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="invalid internal token")


app = create_app()
