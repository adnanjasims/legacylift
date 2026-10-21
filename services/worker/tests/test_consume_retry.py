from types import SimpleNamespace

import pytest

from legacylift_worker.queue import (
    JOBS_QUEUE,
    QueueMessage,
    encode_message,
    parse_message,
)


class _Channel:
    def __init__(self) -> None:
        self.acks: list[int] = []
        self.nacks: list[tuple[int, bool]] = []
        self.published: list[tuple[str, bytes]] = []

    def basic_ack(self, delivery_tag: int) -> None:
        self.acks.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool = True) -> None:
        self.nacks.append((delivery_tag, requeue))

    def basic_publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: object | None = None,
    ) -> None:
        self.published.append((routing_key, body))


def test_failed_consume_republishes_then_dead_letters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from legacylift_worker import consume

    def boom(_message: QueueMessage, client: object | None = None) -> None:
        raise RuntimeError("sandbox failed")

    monkeypatch.setattr(consume, "process_message", boom)
    channel = _Channel()
    method = SimpleNamespace(delivery_tag=7)
    first = QueueMessage(job_id="job1", source="corpus/x", attempt=1)
    consume.on_message(channel, method, None, encode_message(first))
    assert channel.acks == [7]
    assert channel.nacks == []
    assert channel.published[0][0] == JOBS_QUEUE
    retry = parse_message(channel.published[0][1])
    assert retry.attempt == 2

    channel = _Channel()
    consume.on_message(channel, method, None, encode_message(retry))
    retry2 = parse_message(channel.published[0][1])
    assert retry2.attempt == 3

    channel = _Channel()
    consume.on_message(channel, method, None, encode_message(retry2))
    assert channel.acks == []
    assert channel.nacks == [(7, False)]
    assert channel.published == []
