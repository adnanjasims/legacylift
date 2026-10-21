"""RabbitMQ topology shared with the orchestrator broker module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

JOBS_QUEUE = "legacylift.jobs"
DLQ_QUEUE = "legacylift.jobs.dlq"
DLX_EXCHANGE = "legacylift.dlx"
MAX_ATTEMPTS = 3


@dataclass
class QueueMessage:
    job_id: str
    source: str
    attempt: int = 1


def declare_topology(channel: Any) -> None:
    channel.exchange_declare(
        exchange=DLX_EXCHANGE, exchange_type="fanout", durable=True
    )
    channel.queue_declare(queue=DLQ_QUEUE, durable=True)
    channel.queue_bind(queue=DLQ_QUEUE, exchange=DLX_EXCHANGE)
    channel.queue_declare(
        queue=JOBS_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX_EXCHANGE},
    )


def parse_message(body: bytes) -> QueueMessage:
    payload = json.loads(body.decode("utf-8"))
    return QueueMessage(
        job_id=str(payload["job_id"]),
        source=str(payload["source"]),
        attempt=int(payload.get("attempt", 1)),
    )


def encode_message(message: QueueMessage) -> bytes:
    return json.dumps(
        {
            "job_id": message.job_id,
            "source": message.source,
            "attempt": message.attempt,
        }
    ).encode("utf-8")
