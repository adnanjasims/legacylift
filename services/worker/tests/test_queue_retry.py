from legacylift_worker.queue import (
    MAX_ATTEMPTS,
    QueueMessage,
    encode_message,
    parse_message,
)


def test_encode_roundtrip() -> None:
    message = QueueMessage(job_id="abc", source="corpus/x", attempt=2)
    parsed = parse_message(encode_message(message))
    assert parsed == message


def test_max_attempts_is_three() -> None:
    assert MAX_ATTEMPTS == 3
