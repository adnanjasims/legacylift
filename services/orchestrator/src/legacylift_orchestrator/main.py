"""HTTP app: health, login, jobs, and worker callbacks."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from legacylift_orchestrator.broker import (
    Broker,
    MemoryBroker,
    PikaBroker,
    QueueMessage,
)
from legacylift_orchestrator.events import EventHub, iter_sse
from legacylift_orchestrator.jsonlog import configure_logging
from legacylift_orchestrator.models import Job, JobStatus, User
from legacylift_orchestrator.store import JobStore, MemoryJobStore
from legacylift_orchestrator.tokens import decode_token, issue_token, jwt_secret

SERVICE_NAME = "orchestrator"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def upload_dir() -> Path:
    raw = os.environ.get("UPLOAD_DIR", "").strip()
    path = Path(raw) if raw else Path("/tmp/legacylift-uploads")  # nosec B108
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    hub = EventHub()
    application = FastAPI(title="LegacyLift Orchestrator", version="0.1.0")
    application.state.store = job_store
    application.state.broker = job_broker
    application.state.events = hub

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
    def create_job(body: CreateJobBody, request: Request) -> dict[str, Any]:
        actor = _actor(request, job_store)
        job = job_store.create_job(actor.id, body.source)
        job_broker.publish(QueueMessage(job_id=job.id, source=job.source, attempt=1))
        hub.publish(job.id, _job_payload(job))
        return _job_payload(job)

    @application.post("/jobs/upload")
    async def upload_job(
        request: Request, file: Annotated[UploadFile, File()]
    ) -> dict[str, Any]:
        actor = _actor(request, job_store)
        name = file.filename or "source.zip"
        if not name.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="upload must be a .zip file")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="zip exceeds 10 MB")
        job = job_store.create_job(actor.id, "upload.zip")
        dest = upload_dir() / f"{job.id}.zip"
        dest.write_bytes(data)
        job.source = str(dest)
        job_broker.publish(QueueMessage(job_id=job.id, source=job.source, attempt=1))
        hub.publish(job.id, _job_payload(job))
        return _job_payload(job)

    @application.get("/jobs/{job_id}")
    def read_job(job_id: str, request: Request) -> dict[str, Any]:
        actor = _actor(request, job_store)
        job = job_store.visible_job(job_id, actor)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_payload(job)

    @application.get("/jobs/{job_id}/report")
    def read_report(job_id: str, request: Request) -> Any:
        actor = _actor(request, job_store)
        job = job_store.visible_job(job_id, actor)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        report = _load_report(job)
        if report is None:
            raise HTTPException(status_code=404, detail="report not ready")
        return report

    @application.get("/jobs/{job_id}/events")
    def job_events(job_id: str, request: Request) -> StreamingResponse:
        actor = _actor(request, job_store)
        job = job_store.visible_job(job_id, actor)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return StreamingResponse(
            iter_sse(hub, job_id, _job_payload(job)),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

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
        hub.publish(job_id, _job_payload(job))
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
        hub.publish(job_id, _job_payload(job))
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
        hub.publish(job_id, _job_payload(job))
        return {"id": job.id, "status": job.status}

    return application


def _job_payload(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "source": job.source,
        "status": job.status,
        "attempt": job.attempt,
        "error": job.error,
        "report_dir": job.report_dir,
    }


def _load_report(job: Job) -> dict[str, Any] | None:
    if not job.report_dir:
        return None
    path = Path(job.report_dir) / "report.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


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
