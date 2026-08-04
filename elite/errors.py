"""Typed error foundation.

Every error carries a stable category, a *safe* user-facing message, restricted
technical detail (never surfaced to users, never logged as secrets), and a
correlation id. No secret ever belongs in `technical_detail`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


def new_correlation_id() -> str:
    return "cor_" + uuid.uuid4().hex[:24]


@dataclass
class EliteError(Exception):
    """Base typed error. `message` is safe to show a user; `technical_detail` is
    restricted and must never contain secrets."""

    category: str = "unknown"
    message: str = "An internal error occurred."
    technical_detail: str = ""
    correlation_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self):
        super().__init__(f"[{self.category}] {self.message} ({self.correlation_id})")

    def safe_payload(self) -> dict:
        """What may cross a trust boundary to a user: category, message, correlation
        id — NEVER technical_detail."""
        return {"category": self.category, "message": self.message,
                "correlation_id": self.correlation_id}


class ValidationError(EliteError):
    def __init__(self, message="Invalid input.", **kw):
        super().__init__(category="validation", message=message, **kw)


class AuthenticationError(EliteError):
    def __init__(self, message="Authentication failed.", **kw):
        super().__init__(category="authentication", message=message, **kw)


class AuthorizationError(EliteError):
    def __init__(self, message="Not authorized.", **kw):
        super().__init__(category="authorization", message=message, **kw)


class ConcurrencyError(EliteError):
    def __init__(self, message="The record changed since you loaded it.", **kw):
        super().__init__(category="concurrency", message=message, **kw)


class PersistenceError(EliteError):
    def __init__(self, message="Could not complete a storage operation.", **kw):
        super().__init__(category="persistence", message=message, **kw)


class ConfigurationError(EliteError):
    def __init__(self, message="Invalid or missing configuration.", **kw):
        super().__init__(category="configuration", message=message, **kw)


class MigrationError(EliteError):
    def __init__(self, message="A schema migration failed.", **kw):
        super().__init__(category="migration", message=message, **kw)


class DependencyError(EliteError):
    def __init__(self, message="A required dependency is unavailable.", **kw):
        super().__init__(category="dependency", message=message, **kw)


class UnknownInternalError(EliteError):
    def __init__(self, message="An unexpected internal error occurred.", **kw):
        super().__init__(category="unknown", message=message, **kw)
