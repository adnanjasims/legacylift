import json
import logging

from legacylift_orchestrator.jsonlog import JsonFormatter


def test_json_formatter_includes_job_and_run_ids() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="orchestrator.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="job started",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-1"
    record.run_id = "run-9"
    payload = json.loads(formatter.format(record))
    assert payload["msg"] == "job started"
    assert payload["job_id"] == "job-1"
    assert payload["run_id"] == "run-9"
    assert payload["service"] == "orchestrator"
    assert payload["level"] == "info"
