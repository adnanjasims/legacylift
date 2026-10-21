from legacylift_orchestrator.broker import MAX_ATTEMPTS, MemoryBroker, QueueMessage


def test_failed_task_retries_then_dead_letters() -> None:
    broker = MemoryBroker()
    message = QueueMessage(job_id="job1", source="corpus/x", attempt=1)
    broker.publish(message)
    current = broker.jobs.pop(0)
    while True:
        try:
            raise RuntimeError("sandbox failed")
        except RuntimeError:
            broker.handle_failure(current)
        if broker.dlq:
            break
        current = broker.jobs.pop(0)
    assert current.attempt == MAX_ATTEMPTS
    assert len(broker.dlq) == 1
    assert broker.dlq[0].job_id == "job1"
    assert broker.jobs == []
