import json
import logging
import re
from datetime import UTC, datetime

_PATTERN = re.compile(
    r"(?i)([\"']?(?:[\w-]*(?:token|secret|password|api[_-]?key)|authorization)[\"']?\s*[:=]\s*)(?:[\"'][^\"']*[\"']|(?:Bearer\s+)?[^\s,;}]+)"
)


def redact(value: str) -> str:
    return _PATTERN.sub(r"\1[REDACTED]", value)


class ContextFormatter(logging.Formatter):
    def __init__(self, json_logs: bool = False) -> None:
        super().__init__()
        self.json_logs = json_logs

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": redact(message),
            "experiment_id": redact(str(getattr(record, "experiment_id", ""))),
            "run_id": redact(str(getattr(record, "run_id", ""))),
        }
        if self.json_logs:
            return json.dumps(payload, sort_keys=True)
        return " ".join(f"{key}={value}" for key, value in payload.items())


def configure_logging(level: str = "INFO", json_logs: bool = False) -> logging.Logger:
    """Configure only the ArchGuard logger, explicitly and idempotently."""
    logger = logging.getLogger("archguard")
    for old in logger.handlers[:]:
        logger.removeHandler(old)
        old.close()
    handler = logging.StreamHandler()
    handler.setFormatter(ContextFormatter(json_logs))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
