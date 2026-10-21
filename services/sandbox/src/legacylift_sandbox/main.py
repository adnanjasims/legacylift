"""HTTP app for the sandbox. M0 exposes health and readiness only."""

from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from legacylift_sandbox.jsonlog import configure_logging

SERVICE_NAME = "sandbox"


def health_payload() -> dict[str, str]:
    """Return the liveness body used by GET /health."""
    return {"status": "ok", "service": SERVICE_NAME}


def ready_payload() -> dict[str, str]:
    """Return the readiness body used by GET /ready.

    Docker and Kubernetes backends start in M1 and M7. M0 is ready when
    HTTP is up.
    """
    return {"status": "ok", "service": SERVICE_NAME}


def create_app() -> FastAPI:
    """Build the FastAPI application without binding a socket."""
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    application = FastAPI(title="LegacyLift Sandbox", version="0.1.0")

    @application.get("/health")
    def health() -> Mapping[str, str]:
        """Liveness: the process is accepting HTTP."""
        return health_payload()

    @application.get("/ready")
    def ready() -> JSONResponse:
        """Readiness: HTTP is up. Backend probes arrive in M1."""
        return JSONResponse(ready_payload())

    return application


app = create_app()
