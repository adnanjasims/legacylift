"""JSON log lines with optional job_id and run_id fields."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render each log record as a single JSON object on stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "service": "sandbox",
        }
        job_id = getattr(record, "job_id", None)
        if job_id:
            payload["job_id"] = job_id
        run_id = getattr(record, "run_id", None)
        if run_id:
            payload["run_id"] = run_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Replace root handlers with a JSON formatter on stdout.

    Args:
        level: Standard logging level name, for example INFO or DEBUG.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
