"""HTTP app for the orchestrator. M0 exposes health and readiness only."""

from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from legacylift_orchestrator.jsonlog import configure_logging

SERVICE_NAME = "orchestrator"


def health_payload() -> dict[str, str]:
    """Return the liveness body used by GET /health."""
    return {"status": "ok", "service": SERVICE_NAME}


def ready_payload() -> dict[str, str]:
    """Return the readiness body used by GET /ready.

    M0 has no in-process Postgres or queue client. The process is ready
    when it can serve HTTP. Database and RabbitMQ probes start in M3.
    """
    return {"status": "ok", "service": SERVICE_NAME}


def create_app() -> FastAPI:
    """Build the FastAPI application without binding a socket.

    Tests use this factory with Starlette's TestClient. Uvicorn imports
    `app` below for process start.
    """
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    application = FastAPI(title="LegacyLift Orchestrator", version="0.1.0")

    @application.get("/health")
    def health() -> Mapping[str, str]:
        """Liveness: the process is accepting HTTP."""
        return health_payload()

    @application.get("/ready")
    def ready() -> JSONResponse:
        """Readiness: HTTP is up. Downstream probes arrive in M3."""
        return JSONResponse(ready_payload())

    return application


app = create_app()
