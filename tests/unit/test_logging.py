import json
import logging
import sys

import pytest

from archguard.infrastructure.logging import ContextFormatter, configure_logging, redact

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text",
    [
        "token=private-value",
        "api_key: private-value",
        "Authorization: Bearer private-value",
        "secret='private-value'",
        '{"password": "private-value"}',
        "access_token=private-value",
        "x-api-key: private-value",
    ],
)
def test_redaction(text: str) -> None:
    assert "private-value" not in redact(text)
    assert "[REDACTED]" in redact(text)


@pytest.mark.parametrize("json_logs", [True, False])
def test_logging_context_and_exception(json_logs: bool) -> None:
    try:
        raise ValueError("token=private-value")
    except ValueError:
        record = logging.LogRecord(
            "archguard", logging.ERROR, "", 1, "api_key=%s", ("private-value",), sys.exc_info()
        )
    record.experiment_id = "exp"
    record.run_id = "run"
    output = ContextFormatter(json_logs).format(record)
    assert "private-value" not in output
    assert "exp" in output and "run" in output
    if json_logs:
        payload = json.loads(output)
        assert payload["timestamp"].endswith("+00:00")
        assert "ValueError" in payload["message"]


def test_idempotent_configuration() -> None:
    root_handlers = logging.getLogger().handlers[:]
    logger = configure_logging()
    configure_logging("DEBUG", True)
    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG
    assert logging.getLogger().handlers == root_handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
