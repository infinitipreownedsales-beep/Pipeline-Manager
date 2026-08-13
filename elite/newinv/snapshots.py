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
from .dms_cohort import (SOURCE_STAGES, classify_source_stage, dms_cohort_key, dms_cohort_label,
                         dms_planning_state, dms_source_stage, planning_state_of)

DEFAULT_TZ = "America/Chicago"
_VALID_STATES = ("COMPLETED", "COMPLETED_WITH_WARNINGS")

# Backward-compatible generic value classifier. For vehicleInventorySummary the exact source stage
# (ONS / SIT / NNA-INV / DLR-INV / OTHER) comes from Location via dms_source_stage(row) — NEVER Status —
# and the coarser planning bucket (INCOMING / ARRIVED / OTHER) is derived separately via dms_planning_state.
status_bucket = classify_source_stage


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
        # Only physically-arrived DLR-INV rows contribute to dealer DIS aging; SIT / NNA-INV / ONS never do.
        vals = [d for r in self.snapshot_rows(snapshot)
                if dms_source_stage(r) == "DLR-INV"
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
    # exact source-stage deltas (preserved, distinct supply-stage evidence)
    ons_prev: int
    ons_curr: int
    ons_delta: int
    sit_prev: int
    sit_curr: int
    sit_delta: int
    nna_prev: int
    nna_curr: int
    nna_delta: int
    dlr_prev: int
    dlr_curr: int
    dlr_delta: int
    other_prev: int
    other_curr: int
    other_delta: int
    # derived planning-state deltas (INCOMING = ONS+SIT+NNA-INV ; ARRIVED = DLR-INV)
    incoming_prev: int
    incoming_curr: int
    incoming_delta: int
    arrived_prev: int
    arrived_curr: int
    arrived_delta: int
    production_month_prev: dict = field(default_factory=dict)
    production_month_curr: dict = field(default_factory=dict)
    eta_prev: dict = field(default_factory=dict)
    eta_curr: dict = field(default_factory=dict)
    dis_curr: dict = field(default_factory=dict)     # DLR-INV (ARRIVED) DIS distribution at N
    status_curr: dict = field(default_factory=dict)  # preserved Status evidence at N (never drives buckets)


@dataclass(frozen=True)
class SnapshotDeltaReport:
    prev: object            # InventorySnapshot | None
    curr: object            # InventorySnapshot
    cohorts: list = field(default_factory=list)      # list[CohortDelta]
    new_cohorts: list = field(default_factory=list)  # keys observed at N but not N-1
    gone_cohorts: list = field(default_factory=list)  # keys observed at N-1 but not N


def _aggregate(rows):
    """Aggregate a snapshot's rows into per-cohort buckets by EXACT source stage. Pure; no identity, no
    fabrication. Status is retained as evidence only; DIS is collected for arrived (DLR-INV) rows only."""
    agg = {}
    for r in rows:
        k = dms_cohort_key(r)
        b = agg.get(k)
        if b is None:
            b = agg[k] = {"label": dms_cohort_label(r), "pmonth": Counter(), "eta": Counter(),
                          "dis": [], "status": Counter()}
            for s in SOURCE_STAGES:
                b[s] = 0
        stage = dms_source_stage(r)                  # exact source stage from Location, NOT Status
        b[stage] += 1
        if r.get("status"):                          # Status preserved as evidence (never drives bucketing)
            b["status"][str(r["status"]).strip()] += 1
        if r.get("production_month"):
            b["pmonth"][str(r["production_month"]).strip()] += 1
        if r.get("eta"):
            b["eta"][str(r["eta"]).strip()] += 1
        if stage == "DLR-INV":                       # only arrived rows contribute to dealer DIS aging
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
        empty = {s: 0 for s in SOURCE_STAGES}
        cohorts = []
        for k in sorted(set(prev_agg) | set(curr_agg)):
            p = prev_agg.get(k)
            c = curr_agg.get(k)
            label = (c or p)["label"]
            pp = p or dict(empty, pmonth={}, eta={}, dis=[], status={})
            cc = c or dict(empty, pmonth={}, eta={}, dis=[], status={})

            def g(d, s):
                return d.get(s, 0)
            tot_p = sum(g(pp, s) for s in SOURCE_STAGES)
            tot_c = sum(g(cc, s) for s in SOURCE_STAGES)
            inc_p = g(pp, "ONS") + g(pp, "SIT") + g(pp, "NNA-INV")
            inc_c = g(cc, "ONS") + g(cc, "SIT") + g(cc, "NNA-INV")
            arr_p, arr_c = g(pp, "DLR-INV"), g(cc, "DLR-INV")
            cohorts.append(CohortDelta(
                key=k, label=label,
                total_prev=tot_p, total_curr=tot_c, total_delta=tot_c - tot_p,
                ons_prev=g(pp, "ONS"), ons_curr=g(cc, "ONS"), ons_delta=g(cc, "ONS") - g(pp, "ONS"),
                sit_prev=g(pp, "SIT"), sit_curr=g(cc, "SIT"), sit_delta=g(cc, "SIT") - g(pp, "SIT"),
                nna_prev=g(pp, "NNA-INV"), nna_curr=g(cc, "NNA-INV"),
                nna_delta=g(cc, "NNA-INV") - g(pp, "NNA-INV"),
                dlr_prev=arr_p, dlr_curr=arr_c, dlr_delta=arr_c - arr_p,
                other_prev=g(pp, "OTHER"), other_curr=g(cc, "OTHER"),
                other_delta=g(cc, "OTHER") - g(pp, "OTHER"),
                incoming_prev=inc_p, incoming_curr=inc_c, incoming_delta=inc_c - inc_p,
                arrived_prev=arr_p, arrived_curr=arr_c, arrived_delta=arr_c - arr_p,
                production_month_prev=dict(pp.get("pmonth", {})), production_month_curr=dict(cc.get("pmonth", {})),
                eta_prev=dict(pp.get("eta", {})), eta_curr=dict(cc.get("eta", {})),
                dis_curr=_summary(cc.get("dis", [])), status_curr=dict(cc.get("status", {}))))
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


# ---- conservative stage-progression / arrival signals -----------------------------------------------
@dataclass(frozen=True)
class MovementSignal:
    key: tuple
    label: str
    signal: str                 # stage-progression type (see below)
    from_stage: str             # earlier supply stage whose count fell
    to_stage: str               # later supply stage whose count rose
    from_delta: int
    to_delta: int
    inferred_net_movement: int  # cohort-level net, NEVER a same-unit identity claim
    confidence: str             # "provisional" | "ambiguous" (never "proven")
    ambiguity_reasons: list = field(default_factory=list)


# Ordered stage-progression patterns. Each is a cohort-level portfolio observation only — a decrease at an
# earlier stage alongside an increase at a later stage. It NEVER asserts a specific vehicle changed stages.
_PROGRESSIONS = [
    ("APPARENT_SEA_TO_US_INVENTORY", "SIT", "NNA-INV",
     lambda c: (c.sit_delta, c.nna_delta)),
    ("APPARENT_US_INVENTORY_TO_DEALER_ARRIVAL", "NNA-INV", "DLR-INV",
     lambda c: (c.nna_delta, c.dlr_delta)),
    ("APPARENT_ONS_PIPELINE_PROGRESSION", "ONS", "SIT+NNA-INV+DLR-INV",
     lambda c: (c.ons_delta, c.sit_delta + c.nna_delta + c.dlr_delta)),
    ("APPARENT_COHORT_ARRIVAL", "INCOMING", "ARRIVED",
     lambda c: (c.incoming_delta, c.arrived_delta)),
]


def movement_signals(report):
    """Derive conservative cohort stage-progression signals from a delta report.

    For each cohort, a signal is raised only where an earlier stage DECREASED and the corresponding later
    stage INCREASED (e.g. SIT down + NNA-INV up; NNA-INV down + DLR-INV up; ONS down + later stages up; or
    the broad INCOMING down + ARRIVED up). The inferred movement is a cohort-level net quantity (min of the
    two magnitudes) and is explicitly NOT a same-unit claim. Any confounder — unequal magnitudes, an OTHER
    (undefined-stage) change, or a net cohort total change implying external additions/removals — marks the
    signal ambiguous. Cause is never manufactured; physical identity is never asserted."""
    out = []
    for c in report.cohorts:
        for signal, from_stage, to_stage, get in _PROGRESSIONS:
            from_delta, to_delta = get(c)
            if not (from_delta < 0 and to_delta > 0):
                continue
            reasons = []
            if -from_delta != to_delta:
                reasons.append(f"{from_stage} decrease does not equal {to_stage} increase (net not clean)")
            if c.total_delta != 0:
                reasons.append("cohort total changed (external additions/removals present)")
            if c.other_delta != 0:
                reasons.append("undefined-stage (OTHER) units changed in the same cohort")
            out.append(MovementSignal(
                key=c.key, label=c.label, signal=signal, from_stage=from_stage, to_stage=to_stage,
                from_delta=from_delta, to_delta=to_delta,
                inferred_net_movement=min(-from_delta, to_delta),
                confidence="ambiguous" if reasons else "provisional",
                ambiguity_reasons=reasons))
    return out
