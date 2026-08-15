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


def local_business_date(t, tz_name: str = "America/Chicago") -> str:
    """The local civil date (YYYY-MM-DD) at instant `t` in `tz_name`.

    Accepts a timezone-aware datetime or a UTC ISO string (a naive value is read as UTC). This is the
    business-date anchor for longitudinal snapshot idempotency: two uploads on different local business
    days are different observations even when their bytes are identical. Falls back to the UTC date only
    if the zoneinfo database is unavailable (documented, deterministic degradation)."""
    if isinstance(t, str):
        t = _dt.datetime.fromisoformat(t)
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    except Exception:
        # Windows/Python installations may not include the IANA tz database.
        # Preserve the dealership's America/Chicago business-date semantics
        # deterministically instead of silently degrading to UTC.
        if tz_name == "America/Chicago":
            utc = t.astimezone(_dt.timezone.utc)
            year = utc.year

            # U.S. DST: second Sunday in March, transition at 08:00 UTC
            # (02:00 CST -> 03:00 CDT).
            march_1 = _dt.date(year, 3, 1)
            first_sun_march = 1 + ((6 - march_1.weekday()) % 7)
            second_sun_march = first_sun_march + 7
            dst_start = _dt.datetime(
                year, 3, second_sun_march, 8, 0, tzinfo=_dt.timezone.utc
            )

            # U.S. DST: first Sunday in November, transition at 07:00 UTC
            # (02:00 CDT -> 01:00 CST).
            nov_1 = _dt.date(year, 11, 1)
            first_sun_nov = 1 + ((6 - nov_1.weekday()) % 7)
            dst_end = _dt.datetime(
                year, 11, first_sun_nov, 7, 0, tzinfo=_dt.timezone.utc
            )

            offset_hours = -5 if dst_start <= utc < dst_end else -6
            local = utc + _dt.timedelta(hours=offset_hours)
            return local.strftime("%Y-%m-%d")

        return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d")


def present_in_dealership_tz(t: _dt.datetime, tz_name: str) -> str:
    """Presentation-only conversion for display in the dealership timezone. Falls
    back to a fixed offset label if the zoneinfo database is unavailable."""
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
