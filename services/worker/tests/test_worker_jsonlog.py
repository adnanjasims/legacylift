import json
import logging

from legacylift_worker.jsonlog import JsonFormatter


def test_json_formatter_includes_usage_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="legacylift.worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="llm call",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-1"
    record.provider = "watsonx"
    record.model = "ibm/test"
    record.tokens_in = 10
    record.tokens_out = 4
    record.latency_ms = 12
    record.estimated_cost = None
    record.attempt = 2
    payload = json.loads(formatter.format(record))
    assert payload["job_id"] == "job-1"
    assert payload["provider"] == "watsonx"
    assert payload["tokens_in"] == 10
    assert payload["attempt"] == 2
    assert payload["estimated_cost"] is None
