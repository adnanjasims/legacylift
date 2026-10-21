"""Consume migrate jobs from RabbitMQ. Retry then dead-letter."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pika

from legacylift_worker.jsonlog import configure_logging
from legacylift_worker.pipeline import run_migration
from legacylift_worker.queue import (
    JOBS_QUEUE,
    MAX_ATTEMPTS,
    QueueMessage,
    declare_topology,
    encode_message,
    parse_message,
)

logger = logging.getLogger("legacylift.worker")


def orchestrator_url() -> str:
    return os.environ.get("ORCHESTRATOR_URL", "http://127.0.0.1:8000").rstrip("/")


def internal_headers() -> dict[str, str]:
    return {"x-internal-token": os.environ.get("INTERNAL_TOKEN", "")}


def process_message(message: QueueMessage, client: httpx.Client | None = None) -> None:
    """Run one migrate job. Raise on failure so the consumer can retry or DLQ."""
    close = False
    http = client
    if http is None:
        http = httpx.Client(timeout=30.0)
        close = True
    base = orchestrator_url()
    headers = internal_headers()
    try:
        running = http.post(
            f"{base}/internal/jobs/{message.job_id}/running", headers=headers
        )
        running.raise_for_status()
        out_dir = Path(tempfile.mkdtemp(prefix=f"job-{message.job_id}-"))
        try:
            run_migration(message.source, out_dir)
        except Exception as exc:
            http.post(
                f"{base}/internal/jobs/{message.job_id}/fail",
                headers=headers,
                json={"attempt": message.attempt, "error": str(exc)[:500]},
            )
            raise
        done = http.post(
            f"{base}/internal/jobs/{message.job_id}/complete",
            headers=headers,
            json={"report_dir": str(out_dir)},
        )
        done.raise_for_status()
    finally:
        if close:
            http.close()


def on_message(
    channel: Any,
    method: Any,
    _properties: Any,
    body: bytes,
) -> None:
    message = parse_message(body)
    logger.info(
        "job consume",
        extra={"job_id": message.job_id, "attempt": message.attempt},
    )
    try:
        process_message(message)
    except Exception:
        if message.attempt < MAX_ATTEMPTS:
            retry = QueueMessage(
                job_id=message.job_id,
                source=message.source,
                attempt=message.attempt + 1,
            )
            channel.basic_publish(
                exchange="",
                routing_key=JOBS_QUEUE,
                body=encode_message(retry),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    channel.basic_ack(delivery_tag=method.delivery_tag)


def consume_forever(url: str) -> None:
    """Block on the jobs queue until the process is killed."""
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=JOBS_QUEUE, on_message_callback=on_message)
    logger.info("worker consuming")
    channel.start_consuming()


def main() -> None:
    url = os.environ.get("RABBITMQ_URL", "").strip()
    if not url:
        raise SystemExit("RABBITMQ_URL is empty")
    consume_forever(url)


if __name__ == "__main__":
    main()
