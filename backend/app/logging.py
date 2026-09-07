import logging
import re
from typing import Any

import structlog

_REDACT_KEYS = {"password", "api_key", "token", "secret", "authorization", "cookie"}
_REDACT_KEY_SUFFIXES = ("_ct", "_password", "_token", "_key")
_REDACT_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI keys
    re.compile(r"gAAAA[A-Za-z0-9_\-=]{40,}"),  # Fernet ciphertexts
]
_REDACTED = "[REDACTED]"


def _redact(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: (_REDACTED if _should_redact_key(k) else scrub(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            for pat in _REDACT_VALUE_PATTERNS:
                if pat.search(value):
                    return _REDACTED
        if isinstance(value, bytes):
            return _REDACTED
        return value

    return {k: (_REDACTED if _should_redact_key(k) else scrub(v)) for k, v in event_dict.items()}


def _should_redact_key(key: str) -> bool:
    low = key.lower()
    if low in _REDACT_KEYS:
        return True
    return any(low.endswith(suffix) for suffix in _REDACT_KEY_SUFFIXES)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
