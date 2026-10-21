"""HTTP app for the worker. M0 exposes health and readiness only."""

from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from legacylift_worker.jsonlog import configure_logging

SERVICE_NAME = "worker"


def health_payload() -> dict[str, str]:
    """Return the liveness body used by GET /health."""
    return {"status": "ok", "service": SERVICE_NAME}


def ready_payload() -> dict[str, str]:
    """Return the readiness body used by GET /ready when deps are up."""
    return {"status": "ok", "service": SERVICE_NAME}


def create_app() -> FastAPI:
    """Build the FastAPI application without binding a socket."""
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    application = FastAPI(title="LegacyLift Worker", version="0.1.0")
    rabbit_url = os.environ.get("RABBITMQ_URL", "").strip()

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

    return application


app = create_app()
