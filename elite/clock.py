"""Controlled clock and time contract.

- Internal time is ALWAYS UTC, timezone-aware.
- The clock is injectable so tests are deterministic (FixedClock / a step clock).
- Dealership-timezone rendering is a *presentation* concern, never stored.
"""
from __future__ import annotations

import datetime as _dt
from typing import Protocol


class Clock(Protocol):
    def now(self) -> _dt.datetime: ...


class SystemClock:
    """Real wall clock, UTC, timezone-aware."""

    def now(self) -> _dt.datetime:
        return _dt.datetime.now(_dt.timezone.utc)


class FixedClock:
    """Deterministic clock for tests. Optionally advances by a fixed step each read."""

    def __init__(self, start: _dt.datetime, step: _dt.timedelta | None = None):
        if start.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware UTC datetime")
        self._t = start.astimezone(_dt.timezone.utc)
        self._step = step

    def now(self) -> _dt.datetime:
        t = self._t
        if self._step:
            self._t = self._t + self._step
        return t

    def set(self, t: _dt.datetime):
        self._t = t.astimezone(_dt.timezone.utc)


def to_utc_iso(t: _dt.datetime) -> str:
    """Canonical internal string form: UTC ISO-8601."""
    if t.tzinfo is None:
        raise ValueError("refusing to store a naive datetime; provide a UTC-aware value")
    return t.astimezone(_dt.timezone.utc).isoformat()


def present_in_dealership_tz(t: _dt.datetime, tz_name: str) -> str:
    """Presentation-only conversion for display in the dealership timezone. Falls
    back to a fixed offset label if the zoneinfo database is unavailable."""
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
