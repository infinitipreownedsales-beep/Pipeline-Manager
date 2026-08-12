"""Longitudinal inventory snapshot memory (read-only, derived).

This module reads inventory history that ALREADY EXISTS in the durable store — it derives InventorySnapshots
from `import_run` / `import_batch` / `source_observation` lineage with NO new `inventory_snapshot` table, and
it never writes, mutates, resolves identity, or manufactures a business fact / ProductionOrder / VehicleUnit
/ recommendation. Snapshot #1 (the first COMPLETED import) is readable immediately from existing permanent
data with zero modification.

Layers, kept strictly separate:
  * RAW HISTORY      : what the DMS said on each date (source_observation, immutable).
  * DERIVED SIGNALS  : cohort counts / deltas / net cohort movement / DIS aging (pure functions, here).
The PLANNING and DECISION layers live elsewhere and consume these signals; this module does not cross into
them.

Movement inference is deliberately conservative: an ONS decrease alongside an equivalent DLR-INV increase
for the same cohort yields an APPARENT_COHORT_ARRIVAL portfolio observation with preserved uncertainty — it
NEVER asserts that a specific order became a specific VIN. Confounding changes mark the inference ambiguous.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from statistics import mean, median

from ..clock import local_business_date
from .dms_cohort import dms_cohort_key, dms_cohort_label

DEFAULT_TZ = "America/Chicago"
_VALID_STATES = ("COMPLETED", "COMPLETED_WITH_WARNINGS")


def status_bucket(status):
    """Bucket a source status into ONS (incoming) / DLR-INV (arrived) / OTHER. Case/space-insensitive."""
    s = (status or "").strip().upper()
    if s == "ONS":
        return "ONS"
    if s == "DLR-INV":
        return "DLR-INV"
    return "OTHER"


def _as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# ---- snapshot identity (derived) --------------------------------------------------------------------
@dataclass(frozen=True)
class InventorySnapshot:
    import_run_id: str
    import_batch_id: str
    source_id: str
    store_scope: str
    content_hash: str
    observed_time: str        # resolved observation instant (UTC ISO)
    business_date: str        # local business date (America/Chicago)
    received_at: str
    state: str
    row_count: int
    sequence: int = 0         # 1-based chronological index within (source, scope)


class SnapshotReader:
    """Read-only derivation of InventorySnapshots from existing import lineage."""

    def __init__(self, ops_store, data_store, *, tz=DEFAULT_TZ):
        self.ops, self.data, self.tz = ops_store, data_store, tz

    def _observed_anchor(self, run_row, batch):
        # documented fallback so Snapshot #1 (which predates observation-time propagation) still resolves.
        return (run_row["source_effective_time"]
                or (batch.effective_time if batch is not None else None)
                or run_row["received_at"] or run_row["created_at"])

    def list_snapshots(self, source_id, scope):
        """All valid snapshots for (source, scope), chronological by observation time then receipt."""
        runs = self.ops.conn.execute(
            "SELECT * FROM import_run WHERE source_id=? AND store_scope=?"
            " AND state IN ('COMPLETED','COMPLETED_WITH_WARNINGS') AND import_batch_id IS NOT NULL",
            (source_id, scope)).fetchall()
        snaps = []
        for r in runs:
            batch = self.data.get_batch(r["import_batch_id"])
            observed = self._observed_anchor(r, batch)
            snaps.append(InventorySnapshot(
                import_run_id=r["id"], import_batch_id=r["import_batch_id"], source_id=source_id,
                store_scope=scope, content_hash=r["content_hash"], observed_time=observed,
                business_date=local_business_date(observed, self.tz) if observed else "",
                received_at=r["received_at"], state=r["state"],
                row_count=(batch.row_count if batch is not None else 0)))
        snaps.sort(key=lambda s: (s.observed_time or "", s.received_at or "", s.import_run_id))
        return [replace(s, sequence=i + 1) for i, s in enumerate(snaps)]

    def latest_snapshot(self, source_id, scope):
        """The current inventory state: the latest valid snapshot (never a mutable overwrite)."""
        snaps = self.list_snapshots(source_id, scope)
        return snaps[-1] if snaps else None

    def snapshot_rows(self, snapshot):
        """Raw source rows (verbatim) that constitute a snapshot. No identity resolution."""
        return [o.raw_values for o in self.data.list_observations(snapshot.import_batch_id)]

    # ---- DIS / aging (authoritative per-snapshot source data for DLR-INV rows) -----------------------
    def dis_distribution(self, snapshot):
        """DIS (days-in-stock) distribution for the snapshot's DLR-INV rows. Authoritative source data;
        needs no order->VIN lineage to describe current physical aging."""
        vals = [d for r in self.snapshot_rows(snapshot)
                if status_bucket(r.get("status")) == "DLR-INV"
                for d in [_as_int(r.get("dis"))] if d is not None]
        return _summary(vals)

    def current_aging(self, source_id, scope):
        """Current-inventory aging = DIS distribution of the latest snapshot's DLR-INV rows."""
        latest = self.latest_snapshot(source_id, scope)
        return self.dis_distribution(latest) if latest is not None else _summary([])


def _summary(vals):
    vals = sorted(vals)
    return {
        "count": len(vals), "values": vals,
        "min": vals[0] if vals else None, "max": vals[-1] if vals else None,
        "mean": round(mean(vals), 2) if vals else None,
        "median": median(vals) if vals else None,
    }


# ---- snapshot delta (derived, portfolio observations only) ------------------------------------------
@dataclass(frozen=True)
class CohortDelta:
    key: tuple
    label: str
    total_prev: int
    total_curr: int
    total_delta: int
    ons_prev: int
    ons_curr: int
    ons_delta: int
    dlr_prev: int
    dlr_curr: int
    dlr_delta: int
    other_prev: int
    other_curr: int
    other_delta: int
    production_month_prev: dict = field(default_factory=dict)
    production_month_curr: dict = field(default_factory=dict)
    eta_prev: dict = field(default_factory=dict)
    eta_curr: dict = field(default_factory=dict)
    dis_curr: dict = field(default_factory=dict)     # DLR-INV DIS distribution at N


@dataclass(frozen=True)
class SnapshotDeltaReport:
    prev: object            # InventorySnapshot | None
    curr: object            # InventorySnapshot
    cohorts: list = field(default_factory=list)      # list[CohortDelta]
    new_cohorts: list = field(default_factory=list)  # keys observed at N but not N-1
    gone_cohorts: list = field(default_factory=list)  # keys observed at N-1 but not N


def _aggregate(rows):
    """Aggregate a snapshot's rows into per-cohort buckets. Pure; no identity, no fabrication."""
    agg = {}
    for r in rows:
        k = dms_cohort_key(r)
        b = agg.get(k)
        if b is None:
            b = agg[k] = {"label": dms_cohort_label(r), "ONS": 0, "DLR-INV": 0, "OTHER": 0,
                          "pmonth": Counter(), "eta": Counter(), "dis": []}
        bucket = status_bucket(r.get("status"))
        b[bucket] += 1
        if r.get("production_month"):
            b["pmonth"][str(r["production_month"]).strip()] += 1
        if r.get("eta"):
            b["eta"][str(r["eta"]).strip()] += 1
        if bucket == "DLR-INV":
            d = _as_int(r.get("dis"))
            if d is not None:
                b["dis"].append(d)
    return agg


class SnapshotDelta:
    """Pure comparison of Snapshot N-1 vs Snapshot N. Read-only; emits portfolio observations only."""

    def __init__(self, reader):
        self.reader = reader

    def compare(self, prev_snapshot, curr_snapshot):
        prev_agg = _aggregate(self.reader.snapshot_rows(prev_snapshot)) if prev_snapshot is not None else {}
        curr_agg = _aggregate(self.reader.snapshot_rows(curr_snapshot))
        cohorts = []
        for k in sorted(set(prev_agg) | set(curr_agg)):
            p = prev_agg.get(k)
            c = curr_agg.get(k)
            label = (c or p)["label"]
            pp = p or {"ONS": 0, "DLR-INV": 0, "OTHER": 0, "pmonth": {}, "eta": {}}
            cc = c or {"ONS": 0, "DLR-INV": 0, "OTHER": 0, "pmonth": {}, "eta": {}, "dis": []}
            tot_p = pp["ONS"] + pp["DLR-INV"] + pp["OTHER"]
            tot_c = cc["ONS"] + cc["DLR-INV"] + cc["OTHER"]
            cohorts.append(CohortDelta(
                key=k, label=label,
                total_prev=tot_p, total_curr=tot_c, total_delta=tot_c - tot_p,
                ons_prev=pp["ONS"], ons_curr=cc["ONS"], ons_delta=cc["ONS"] - pp["ONS"],
                dlr_prev=pp["DLR-INV"], dlr_curr=cc["DLR-INV"], dlr_delta=cc["DLR-INV"] - pp["DLR-INV"],
                other_prev=pp["OTHER"], other_curr=cc["OTHER"], other_delta=cc["OTHER"] - pp["OTHER"],
                production_month_prev=dict(pp.get("pmonth", {})), production_month_curr=dict(cc.get("pmonth", {})),
                eta_prev=dict(pp.get("eta", {})), eta_curr=dict(cc.get("eta", {})),
                dis_curr=_summary(cc.get("dis", []))))
        new_cohorts = [k for k in curr_agg if k not in prev_agg]
        gone_cohorts = [k for k in prev_agg if k not in curr_agg]
        return SnapshotDeltaReport(prev=prev_snapshot, curr=curr_snapshot, cohorts=cohorts,
                                   new_cohorts=sorted(new_cohorts), gone_cohorts=sorted(gone_cohorts))

    def latest_delta(self, source_id, scope):
        """Delta of the latest snapshot vs the one before it (or vs nothing if only one exists)."""
        snaps = self.reader.list_snapshots(source_id, scope)
        if not snaps:
            return None
        curr = snaps[-1]
        prev = snaps[-2] if len(snaps) >= 2 else None
        return self.compare(prev, curr)


# ---- conservative movement / arrival signal ---------------------------------------------------------
@dataclass(frozen=True)
class MovementSignal:
    key: tuple
    label: str
    signal: str                 # APPARENT_COHORT_ARRIVAL
    ons_prev: int
    ons_curr: int
    ons_delta: int
    dlr_prev: int
    dlr_curr: int
    dlr_delta: int
    inferred_net_movement: int  # cohort-level net, NEVER same-unit identity
    confidence: str             # "provisional" | "ambiguous" (never "proven")
    ambiguity_reasons: list = field(default_factory=list)


def movement_signals(report):
    """Derive conservative cohort movement signals from a delta report.

    A candidate APPARENT_COHORT_ARRIVAL is raised only where ONS decreased AND DLR-INV increased for the same
    cohort. The net movement is a cohort-level quantity (min of the two magnitudes) and is explicitly not a
    same-unit claim. Any confounder (unequal magnitudes, other-status change, or a net cohort total change
    implying additions/removals) marks the signal ambiguous. Cause is never manufactured."""
    out = []
    for c in report.cohorts:
        if not (c.ons_delta < 0 and c.dlr_delta > 0):
            continue
        reasons = []
        if -c.ons_delta != c.dlr_delta:
            reasons.append("ONS decrease does not equal DLR-INV increase (net not clean)")
        if c.other_delta != 0:
            reasons.append("other-status units in the same cohort changed")
        if c.total_delta != 0:
            reasons.append("cohort total changed (additions/removals present, not pure internal movement)")
        out.append(MovementSignal(
            key=c.key, label=c.label, signal="APPARENT_COHORT_ARRIVAL",
            ons_prev=c.ons_prev, ons_curr=c.ons_curr, ons_delta=c.ons_delta,
            dlr_prev=c.dlr_prev, dlr_curr=c.dlr_curr, dlr_delta=c.dlr_delta,
            inferred_net_movement=min(-c.ons_delta, c.dlr_delta),
            confidence="ambiguous" if reasons else "provisional",
            ambiguity_reasons=reasons))
    return out
