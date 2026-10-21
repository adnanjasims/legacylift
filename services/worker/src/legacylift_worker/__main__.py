"""Run the worker health server with uvicorn."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Start uvicorn on HOST and PORT from the environment.

    HOST defaults to 127.0.0.1. Compose sets HOST=0.0.0.0 so the
    container is reachable on the published port.
    """
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run(
        "legacylift_worker.main:app",
        host=host,
        port=port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
