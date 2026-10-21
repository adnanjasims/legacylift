"""JSON log lines with optional job_id and run_id fields."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_EXTRA_KEYS = (
    "job_id",
    "run_id",
    "provider",
    "model",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "estimated_cost",
    "attempt",
    "detail",
)


class JsonFormatter(logging.Formatter):
    """Render each log record as a single JSON object on stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "service": "worker",
        }
        for key in _EXTRA_KEYS:
            if not hasattr(record, key):
                continue
            payload[key] = getattr(record, key)
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
