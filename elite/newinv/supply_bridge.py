"""Snapshot supply bridge (derived; cohort quantities, never fabricated entities).

Turns the latest immutable DMS inventory snapshot into per-planning-cohort supply quantities for
PlanningService.issue, WITHOUT creating VehicleUnits / ProductionOrders / Serial identity and WITHOUT
writing count-many null-ID projection rows: the counts are passed straight to PlanningService as integers
(persisted natively on the issued plan) and the cumulative-by-month math is fed a transient `qualifying`
list of anonymous supply SLOTS (a quantity list, not stored fake units).

Source stage (from Location) → planning state:
  DLR-INV                    -> ARRIVED (current dealer inventory; DIS is aging evidence; available now)
  ONS + SIT + NNA-INV        -> INCOMING (future; available at production_month / ETA)
  anything else              -> OTHER (retained, never counted as supply)

Exact source stage, production_month, ETA, DIS, and snapshot provenance are all preserved on the result.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .dms_cohort import dms_source_stage
from .dms_identity import dms_planning_identity, dms_planning_key


def _month_str(v):
    """Parse a production_month ('YYYY-MM'/'YYYYMM') or an ETA date into 'YYYY-MM', else None."""
    d = "".join(ch for ch in str(v or "").strip() if ch.isdigit())
    if len(d) >= 6:
        y, m = d[:4], d[4:6]
        if 1 <= int(m) <= 12:
            return f"{y}-{m}"
    return None


def _arrival_month(row):
    """Best available arrival month for an incoming unit: production_month, else ETA month, else None."""
    return _month_str(row.get("production_month")) or _month_str(row.get("eta"))


def _as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


@dataclass
class SupplyCohort:
    key: tuple
    identity: str
    representative: dict
    current: int                       # ARRIVED (DLR-INV)
    future: int                        # INCOMING (ONS + SIT + NNA-INV)
    other: int                         # undefined stage
    stages: dict                       # exact source-stage counts (ONS/SIT/NNA-INV/DLR-INV/OTHER)
    dis_values: list                   # DLR-INV days-in-stock (aging evidence)
    qualifying: list = field(default_factory=list)   # transient supply slots: {key, available_month, stage}


def build_supply(rows, *, current_month):
    """Aggregate snapshot rows into per-planning-cohort supply quantities + month-bucketed qualifying slots.

    `current_month` = 'YYYY-MM' of now (ARRIVED units are available now). Returns {cohort_key: SupplyCohort}."""
    by_key = {}
    for r in rows:
        if not dms_planning_key(r)[1]:                 # no usable model code -> cannot place as supply
            continue
        k = dms_planning_key(r)
        b = by_key.get(k)
        if b is None:
            b = by_key[k] = {"identity": dms_planning_identity(r), "rep": r,
                             "stages": Counter(), "dis": [], "qual": []}
        stage = dms_source_stage(r)                    # ONS/SIT/NNA-INV/DLR-INV/OTHER (from Location)
        b["stages"][stage] += 1
        if stage == "DLR-INV":
            d = _as_int(r.get("dis"))
            if d is not None:
                b["dis"].append(d)
            b["qual"].append({"key": f"{b['identity']}#arrived{len(b['qual'])}",
                              "available_month": current_month, "stage": stage})
        elif stage in ("ONS", "SIT", "NNA-INV"):
            b["qual"].append({"key": f"{b['identity']}#incoming{len(b['qual'])}",
                              "available_month": _arrival_month(r), "stage": stage})
    out = {}
    for k, b in by_key.items():
        st = b["stages"]
        current = st.get("DLR-INV", 0)
        future = st.get("ONS", 0) + st.get("SIT", 0) + st.get("NNA-INV", 0)
        out[k] = SupplyCohort(
            key=k, identity=b["identity"], representative=b["rep"], current=current, future=future,
            other=st.get("OTHER", 0), stages=dict(st), dis_values=b["dis"], qualifying=b["qual"])
    return out


def read_latest_snapshot_rows(reader, source_id, scope):
    """Rows (raw_values) of the latest completed inventory snapshot for a source/scope, or [] if none."""
    latest = reader.latest_snapshot(source_id, scope)
    return reader.snapshot_rows(latest) if latest is not None else []
