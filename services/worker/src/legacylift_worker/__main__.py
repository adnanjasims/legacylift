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
    rabbit = os.environ.get("RABBITMQ_URL", "").strip()
    if os.environ.get("WORKER_CONSUME", "").strip() == "1" and rabbit:
        import threading

        from legacylift_worker.consume import consume_forever

        threading.Thread(target=consume_forever, args=(rabbit,), daemon=True).start()
    uvicorn.run(
        "legacylift_worker.main:app",
        host=host,
        port=port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
