"""Explicit environment identity.

No hidden default may turn a missing environment into a business environment.
The environment MUST be stated explicitly (via ELITE_ENV); an unset or unknown
value is a safe startup failure, never a silent fallback to development/production.
"""
from __future__ import annotations

import enum
import os

from .errors import ConfigurationError


class Environment(enum.Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"
    DEMO = "demo"
    PILOT = "pilot"          # controlled dealership pilot runtime — distinct from TEST and PRODUCTION

    @property
    def is_production(self) -> bool:
        return self is Environment.PRODUCTION


_VALID = {e.value: e for e in Environment}


def resolve_environment(env: dict | None = None) -> Environment:
    """Resolve the environment from ELITE_ENV. Raises ConfigurationError on a
    missing or unrecognized value — dev and prod can never be silently confused."""
    env = os.environ if env is None else env
    raw = (env.get("ELITE_ENV") or "").strip().lower()
    if not raw:
        raise ConfigurationError(
            message="Environment is not configured.",
            technical_detail="ELITE_ENV is unset; refusing to assume an environment.")
    if raw not in _VALID:
        raise ConfigurationError(
            message="Environment is not configured.",
            technical_detail=f"ELITE_ENV={raw!r} is not one of {sorted(_VALID)}.")
    return _VALID[raw]


def resolve_pilot_scope(env: dict | None = None, *, default: str | None = None) -> str:
    """Resolve the authoritative pilot store scope from ELITE_PILOT_SCOPE — the single source of truth
    for the store scope the real launcher, login UI, and ops CLI all operate at.

    The real runtime passes no ``default`` and fails closed on a missing/empty value: it must never
    silently assume a store. Test and fixture callers pass an explicit ``default`` (e.g. "store:HG") to
    keep deterministic construction without letting the real runtime borrow that fallback.
    """
    env = os.environ if env is None else env
    raw = (env.get("ELITE_PILOT_SCOPE") or "").strip()
    if raw:
        return raw
    if default is not None:
        return default
    raise ConfigurationError(
        message="The store scope is not configured.",
        technical_detail="ELITE_PILOT_SCOPE is unset/empty; refusing to assume a store scope "
                         "(never silently falls back to store:HG).")
