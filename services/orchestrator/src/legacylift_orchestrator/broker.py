"""Job queue. In-memory for tests, pika for RabbitMQ."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

JOBS_QUEUE = "legacylift.jobs"
DLQ_QUEUE = "legacylift.jobs.dlq"
DLX_EXCHANGE = "legacylift.dlx"
MAX_ATTEMPTS = 3


@dataclass
class QueueMessage:
    job_id: str
    source: str
    attempt: int = 1


class Broker(Protocol):
    def publish(self, message: QueueMessage) -> None: ...

    def dead_letter(self, message: QueueMessage) -> None: ...


@dataclass
class MemoryBroker:
    """List-backed broker so retry and DLQ tests do not need RabbitMQ."""

    jobs: list[QueueMessage] = field(default_factory=list)
    dlq: list[QueueMessage] = field(default_factory=list)

    def publish(self, message: QueueMessage) -> None:
        self.jobs.append(message)

    def dead_letter(self, message: QueueMessage) -> None:
        self.dlq.append(message)

    def handle_failure(self, message: QueueMessage) -> None:
        if message.attempt < MAX_ATTEMPTS:
            self.publish(
                QueueMessage(
                    job_id=message.job_id,
                    source=message.source,
                    attempt=message.attempt + 1,
                )
            )
        else:
            self.dead_letter(message)


class PikaBroker:
    """Publish to RabbitMQ with a dead-letter exchange on the jobs queue."""

    def __init__(self, url: str) -> None:
        self._url = url

    def publish(self, message: QueueMessage) -> None:
        self._publish(JOBS_QUEUE, message)

    def dead_letter(self, message: QueueMessage) -> None:
        self._publish(DLQ_QUEUE, message)

    def _publish(self, queue: str, message: QueueMessage) -> None:
        import pika

        params = pika.URLParameters(self._url)
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            declare_topology(channel)
            body = json.dumps(
                {
                    "job_id": message.job_id,
                    "source": message.source,
                    "attempt": message.attempt,
                }
            )
            channel.basic_publish(
                exchange="",
                routing_key=queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        finally:
            connection.close()


def declare_topology(channel: Any) -> None:
    """Jobs queue dead-letters into DLX, which binds the DLQ."""
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
