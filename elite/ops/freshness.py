"""Domain-aware data freshness.

Freshness is computed from the source EFFECTIVE time and the expected cadence — never from file import
time. A freshly uploaded snapshot carrying a stale effective date is therefore STALE, not CURRENT. Stale
or missing sources reduce visible confidence and block readiness for their domain. Each evaluation appends
a new freshness result (immutable); a later restored-current reading never erases prior stale history, and
freshness never rewrites a historical issued result.
"""
from __future__ import annotations

import datetime as _dt

from ..clock import to_utc_iso


def _parse(ts):
    if not ts:
        return None
    try:
        return _dt.datetime.fromisoformat(ts)
    except ValueError:
        return None


class FreshnessService:
    def __init__(self, ops_store, clock):
        self.ops, self.clock = ops_store, clock

    def evaluate(self, *, source_id, scope, domain, last_received_at, source_effective_time,
                 expected_cadence_seconds, stale_threshold_seconds, affected=None, now=None,
                 conflicting=False, failed=False):
        now = now or self.clock.now()
        eff = _parse(source_effective_time)
        age = int((now - eff).total_seconds()) if eff else None

        if failed:
            status, blocking, conf = "FAILED", "blocks readiness", "no confidence"
        elif last_received_at is None:
            status, blocking, conf = "MISSING", "blocks readiness", "no confidence"
        elif conflicting:
            status, blocking, conf = "CONFLICTING", "blocks readiness", "confidence withheld"
        elif eff is None:
            status, blocking, conf = "UNRESOLVED", "review required", "unknown"
        elif age <= expected_cadence_seconds:
            status, blocking, conf = "CURRENT", "none", "full"
        elif age <= stale_threshold_seconds:
            status, blocking, conf = "AGING", "reduces confidence", "reduced"
        else:
            status, blocking, conf = "STALE", "blocks readiness", "low"

        evidence = {"now": to_utc_iso(now), "effective": source_effective_time,
                    "cadence_s": expected_cadence_seconds, "stale_threshold_s": stale_threshold_seconds}
        return self.ops.add_freshness(
            source_id=source_id, store_scope=scope, domain=domain, last_received_at=last_received_at,
            source_effective_time=source_effective_time, expected_cadence_seconds=expected_cadence_seconds,
            age_seconds=age, stale_threshold_seconds=stale_threshold_seconds, status=status,
            blocking_impact=blocking, affected=affected or [domain], evidence=evidence)

    def current_status(self, source_id, scope=None):
        row = self.ops.latest_freshness(source_id, scope)
        return row["status"] if row else "MISSING"

    def blocking_sources(self, scope=None):
        """Sources whose LATEST freshness result blocks readiness (STALE/MISSING/FAILED/CONFLICTING)."""
        rows = self.ops.conn.execute(
            "SELECT source_id, store_scope FROM source_freshness_result GROUP BY source_id, store_scope"
        ).fetchall()
        out = []
        for r in rows:
            if scope and r["store_scope"] != scope:
                continue
            latest = self.ops.latest_freshness(r["source_id"], r["store_scope"])
            if latest and latest["status"] in ("STALE", "MISSING", "FAILED", "CONFLICTING"):
                out.append(latest)
        return out
