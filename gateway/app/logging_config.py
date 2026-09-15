"""Structured JSON logging.

Per the root README's logging rules: every log line is one JSON object, we
never log secrets (API keys/tokens/authorization headers), and request/
response content is only logged when LOG_REQUEST_CONTENT=true.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_REDACT_KEYS = {
    "authorization",
    "gateway_api_token",
    "llm_api_key",
    "plane_api_key",
    "anthropic_auth_token",
    "copilot_provider_api_key",
    "x-api-key",
}


def redact(data: dict) -> dict:
    out = {}
    for key, value in data.items():
        if key.lower() in _REDACT_KEYS:
            out[key] = "***redacted***"
        elif isinstance(value, dict):
            out[key] = redact(value)
        else:
            out[key] = value
    return out


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(redact(extra))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers to our chosen level, but keep
    # uvicorn's access logger since it's useful and contains no secrets.
    for name in ("uvicorn", "uvicorn.error", "httpx"):
        logging.getLogger(name).setLevel(level.upper())


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    logger.log(level, message, extra={"fields": fields})
