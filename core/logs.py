"""Logging setup: one 'deepdive' logger tree, stderr only, secrets redacted, optional JSON lines.

Progress and diagnostics go to stderr; stdout is reserved for the final report so
``harness.py --format json`` is always machine-readable.

    DR_LOG_LEVEL   DEBUG|INFO|WARNING|ERROR (default INFO)
    DR_LOG_FORMAT  text (default) | json   (json adds ts, level, logger, run_id)
"""

import json
import logging
import os
import re
import sys
import time

ROOT = "deepdive"
_SECRETS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "[REDACTED]"),
    (re.compile(r"(?i)((?:api[_-]?key|token|secret|password|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;&]{6,}"),
     r"\1[REDACTED]"),
    (re.compile(r"(?i)([?&](?:key|api_key|token|access_token)=)[^&\s]+"), r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


class _RedactingFormatter(logging.Formatter):
    def __init__(self, as_json: bool = False):
        super().__init__("%(message)s")
        self._json = as_json

    def format(self, record: logging.LogRecord) -> str:
        message = redact(record.getMessage())
        if not self._json:
            return message
        return json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname, "logger": record.name,
            "run_id": getattr(record, "run_id", "-"), "msg": message,
        }, ensure_ascii=False)


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{ROOT}.{name}" if name else ROOT)


def ensure_configured(stream=None) -> None:
    """Install the stderr handler once, unless the application already configured 'deepdive'."""
    logger = logging.getLogger(ROOT)
    if logger.handlers:
        return
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(_RedactingFormatter(os.environ.get("DR_LOG_FORMAT", "text").lower() == "json"))
    logger.addHandler(handler)
    level = os.environ.get("DR_LOG_LEVEL", "INFO").upper()
    logger.setLevel(level if level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO")
    logger.propagate = False

