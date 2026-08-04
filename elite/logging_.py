"""Structured technical logging — distinct from Audit Events.

Technical logs are diagnostics (operation, result, duration, error category). They
are NOT the governance record. Secrets, passwords, and tokens must never be logged.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass

from .environment import Environment

_SECRET_KEYS = ("secret", "password", "passwd", "token", "authorization",
                "api_key", "apikey", "pepper", "credential")


def _scrub(value):
    if isinstance(value, dict):
        return {k: ("***" if any(s in k.lower() for s in _SECRET_KEYS) else _scrub(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


@dataclass
class StructuredLogger:
    environment: Environment
    revision: str
    stream = None  # defaults to stderr

    def _emit(self, level, operation, result, correlation_id=None,
              error_category=None, duration_ms=None, **fields):
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level,
            "environment": self.environment.value,
            "revision": self.revision,
            "operation": operation,
            "result": result,
            "correlation_id": correlation_id,
            "error_category": error_category,
            "duration_ms": duration_ms,
        }
        rec.update(_scrub(fields))
        out = self.stream or sys.stderr
        out.write(json.dumps({k: v for k, v in rec.items() if v is not None}) + "\n")

    def info(self, operation, result="ok", **kw):
        self._emit("INFO", operation, result, **kw)

    def error(self, operation, error_category, correlation_id, **kw):
        self._emit("ERROR", operation, "error",
                   correlation_id=correlation_id, error_category=error_category, **kw)


class timed:
    """Context manager to record duration for an operation log field."""

    def __enter__(self):
        self._t = time.perf_counter(); return self

    def __exit__(self, *a):
        self.duration_ms = round((time.perf_counter() - self._t) * 1000, 2)
        return False
