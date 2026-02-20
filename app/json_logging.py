"""
Structured JSON logging utilities.

Provides a stdlib-based JSON formatter for consistent structured logging
across the application and Lambda handlers.
"""

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """JSON log formatter using stdlib only."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra fields
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in (
                    "args", "asctime", "created", "exc_info", "exc_text", "filename",
                    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                    "message", "msg", "name", "pathname", "process", "processName",
                    "relativeCreated", "stack_info", "thread", "threadName", "taskName"
                ):
                    try:
                        json.dumps(value)
                        log_entry[key] = value
                    except (TypeError, ValueError):
                        log_entry[key] = str(value)

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_json_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with JSON formatting."""
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
