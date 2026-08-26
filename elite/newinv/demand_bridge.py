"""Real Speed-to-Sell demand bridge (derived; observation-only in, cohort demand out).

Turns accepted, immutable Speed-to-Sell Source Observations into per-cohort monthly demand evidence for the
authoritative Elite DemandService — preserving the dealership-proven business meaning:

  * every source row is preserved upstream; this layer never mutates or deletes evidence;
  * duplicate VINs are reconciled to ONE physical sale (count never inflates); the representative record uses
    the strongest internally-consistent evidence (numeric DTS beats a business code); a materially-conflicting
    duplicate raises a fingerprinted Data-Quality Exception, an identical duplicate a benign one;
  * DT / DNQ (Dealer Trade / Does Not Qualify = externally-satisfied demand) COUNT as real demand and sales
    velocity, are EXCLUDED from numeric days-to-sell averages, are never zeroed or fabricated, and their
    recurrence is preserved so the engine can tell persistent unmet demand from a sporadic one-off;
  * Sales Month is monthly evidence (YYYY-MM); no exact sold date is invented;
  * the current partial month is exposure-adjusted (elapsed fraction), never counted as a full month;
  * legacy PRATE / 90-day / 180-day pace is computed alongside as a PILOT COMPARISON signal only — never
    authoritative, never blended into, never overriding Elite DemandService.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import data_quality as dq
from .dms_identity import dms_planning_identity, dms_planning_key


def midx_of(sales_month):
    """YYYYMM (int or text) -> month index (year*12+month), or None if not a valid YYYYMM."""
    d = "".join(ch for ch in str(sales_month or "").strip() if ch.isdigit())
    if len(d) < 6:
        return None
    y, m = int(d[:4]), int(d[4:6])
    return y * 12 + m if 1 <= m <= 12 else None


def month_str(sales_month):
    """YYYYMM -> 'YYYY-MM' (the key format Elite DemandService uses), or None."""
    d = "".join(ch for ch in str(sales_month or "").strip() if ch.isdigit())
    return f"{d[:4]}-{d[4:6]}" if midx_of(sales_month) is not None else None


def is_business_code(row) -> bool:
    """True for DT/DNQ (a preserved DAYS TO SELL business code), false for a numeric value."""
    sem = row.get("days_to_sell_semantic")
    if sem is not None:
        return sem == "business_code"
    v = str(row.get("days_to_sell") or "").strip().replace(",", "")
    if v == "":
        return False
    try:
        float(v)
        return False
    except ValueError:
        return True


def dts_numeric(row):
    """Numeric days-to-sell, or None for DT/DNQ/blank (never coerced to zero)."""
    if is_business_code(row):
        return None
    v = str(row.get("days_to_sell") or "").strip().replace(",", "")
    try:
        return float(v) if v != "" else None
    except ValueError:
        return None


def _material(row):
    """The business-relevant fields whose difference makes a duplicate 'materially conflicting'."""
    return (month_str(row.get("sales_month")), dms_planning_key(row),
            str(row.get("days_to_sell") or "").strip().upper(),
            str(row.get("model") or "").strip().upper())


def _strength(row):
    """Sort key: strongest evidence first (a numeric DTS beats a business code)."""
    return (0 if is_business_code(row) else 1, )


@dataclass
class CountedSale:
    vin: str
    month: str          # 'YYYY-MM'
    midx: int
    cohort_key: tuple
    cohort_identity: str
    representative: dict  # the row used to resolve the combination + DTS
    dts: float | None
    business_code: bool   # DT/DNQ -> externally satisfied
    source_rows: tuple = field(default_factory=tuple)   # provenance: all rows collapsed into this sale


def reconcile(rows):
    """Reconcile accepted Speed-to-Sell rows into unique counted sales + data-quality exceptions.

    `rows` are raw_values dicts in stable source order. Blank-VIN rows are each their own sale (not deduped).
    A non-blank VIN with multiple rows counts ONCE using the strongest-evidence representative; identical
    duplicates raise a benign exception, materially-conflicting duplicates a warning exception."""
    order = {id(r): i for i, r in enumerate(rows)}
    groups = {}
    singles = []
    for r in rows:
        if midx_of(r.get("sales_month")) is None:
            continue                                   # not a dated sale row
        vin = str(r.get("vin") or "").strip()
        if vin:
            groups.setdefault(vin, []).append(r)
        else:
            singles.append(r)                          # blank VIN: counts individually, never deduped

    counted, exceptions = [], []

    def _emit(vin, rep, members):
        counted.append(CountedSale(
            vin=vin, month=month_str(rep.get("sales_month")), midx=midx_of(rep.get("sales_month")),
            cohort_key=dms_planning_key(rep), cohort_identity=dms_planning_identity(rep),
            representative=rep, dts=dts_numeric(rep), business_code=is_business_code(rep),
            source_rows=tuple(members)))

    for r in singles:
        _emit("", r, [r])

    for vin, members in groups.items():
        members = sorted(members, key=lambda r: order[id(r)])
        if len(members) == 1:
            _emit(vin, members[0], members)
            continue
        rep = sorted(members, key=lambda r: (_strength(r), -order[id(r)]))[-1]   # strongest, then earliest
        _emit(vin, rep, members)                       # ONE physical sale, never inflated
        mats = sorted({_material(m) for m in members}, key=lambda t: str(t))
        identical = len(mats) == 1
        kind = "duplicate_identical" if identical else "duplicate_conflicting"
        detail = ("Duplicate VIN found in Speed-to-Sell data. Elite counted this vehicle once and preserved "
                  "all source records for review.")
        if not identical:
            detail += " The duplicate rows disagree materially (month / configuration / days-to-sell)."
        exceptions.append(dq.make_exception(
            kind, vin, {"materials": [list(map(_jsonable, m)) for m in mats]}, detail,
            severity=("info" if identical else "warning"),
            evidence=tuple(order[id(m)] for m in members)))
    counted.sort(key=lambda c: (c.midx, c.vin, c.cohort_identity))
    return counted, exceptions


def _jsonable(v):
    return list(v) if isinstance(v, tuple) else v


@dataclass
class CohortDemand:
    key: tuple
    identity: str
    representative: dict
    retail_by_month: dict          # 'YYYY-MM' -> count (deduped sales)
    sales_total: int
    dts_values: list               # numeric DTS only
    dts_average: float | None
    business_code_count: int       # DT/DNQ (externally satisfied)
    business_code_months: int      # distinct months with a DT/DNQ (recurrence)
    business_code_midxs: tuple      # sorted distinct month-indices with a DT/DNQ (recency/clustering)
    organic_sales_total: int        # ORGANIC stocked-retail sales (numeric DTS) — the breadth-by-velocity stream
    first_midx: int
    exposure_months: float
    legacy_prate: float            # comparison-only
    legacy_r90: int
    legacy_r180: int


def cohort_demand(counted, *, latest_midx, current_midx, part_frac=1.0):
    """Aggregate counted sales into per-cohort monthly demand + exposure + legacy pace comparison.

    `latest_midx` = latest observed month; `current_midx` = the in-progress month; `part_frac` = elapsed
    fraction of that month (so the partial current month is never treated as complete)."""
    part_frac = max(0.05, min(1.0, float(part_frac)))
    el90, el180 = 2 + part_frac, 5 + part_frac
    by_key = {}
    for c in counted:
        by_key.setdefault(c.cohort_key, []).append(c)
    out = {}
    for key, sales in by_key.items():
        rbm = Counter(s.month for s in sales)
        dts_values = [s.dts for s in sales if s.dts is not None]
        bc = [s for s in sales if s.business_code]
        first_midx = min(s.midx for s in sales)
        span = (latest_midx - first_midx + 1) - ((1 - part_frac) if latest_midx == current_midx else 0)
        exposure = max(part_frac, round(span, 4))
        r90 = sum(1 for s in sales if s.midx > latest_midx - 3)
        r180 = sum(1 for s in sales if s.midx > latest_midx - 6)
        prate = round(r90 / el90 + r180 / el180, 4)
        out[key] = CohortDemand(
            key=key, identity=sales[0].cohort_identity, representative=sales[0].representative,
            retail_by_month=dict(rbm), sales_total=len(sales), dts_values=dts_values,
            dts_average=(round(sum(dts_values) / len(dts_values), 2) if dts_values else None),
            business_code_count=len(bc), business_code_months=len({s.midx for s in bc}),
            business_code_midxs=tuple(sorted({s.midx for s in bc})),
            organic_sales_total=len(sales) - len(bc),
            first_midx=first_midx, exposure_months=exposure, legacy_prate=prate,
            legacy_r90=r90, legacy_r180=r180)
    return out


def build_demand(rows, *, latest_midx, current_midx, part_frac=1.0):
    """Full derived-demand result: reconciled cohorts + data-quality exceptions + totals."""
    counted, exceptions = reconcile(rows)
    cohorts = cohort_demand(counted, latest_midx=latest_midx, current_midx=current_midx, part_frac=part_frac)
    return {"cohorts": cohorts, "exceptions": exceptions,
            "counted_sales": len(counted), "cohort_count": len(cohorts)}


def borrow_cohort(current_key, current_rep, predecessors):
    """Build a CohortDemand for `current_key` (a current supply cohort with NO exact same-code history) that
    BORROWS one or more predecessor cohorts' REAL Speed-to-Sell history as governed lineage supporting evidence.

    The result carries the CURRENT cohort's identity/representative (so current supply stays under its current
    code) while its demand months/DTS come from the predecessor's OWN real observations — never fabricated,
    never relabeled here (the `lineage` evidence tier is applied by DemandService.issue's inherited path). Sales
    are NOT duplicated: each predecessor month is summed once; the predecessor cohorts are read-only and continue
    to issue independently from their own exact history."""
    rbm, dts_values = {}, []
    sales_total = bc_count = r90 = r180 = 0
    bc_midxs, organic = set(), 0
    first = None
    exposure = 0.0
    for c in predecessors:
        for mo, n in c.retail_by_month.items():
            rbm[mo] = rbm.get(mo, 0) + n
        dts_values += list(c.dts_values)
        sales_total += c.sales_total
        bc_count += c.business_code_count
        bc_midxs |= set(c.business_code_midxs)
        organic += c.organic_sales_total
        first = c.first_midx if first is None else min(first, c.first_midx)
        exposure = max(exposure, c.exposure_months)
        r90 += c.legacy_r90
        r180 += c.legacy_r180
    return CohortDemand(
        key=current_key, identity=dms_planning_identity(current_rep), representative=current_rep,
        retail_by_month=rbm, sales_total=sales_total, dts_values=dts_values,
        dts_average=(round(sum(dts_values) / len(dts_values), 2) if dts_values else None),
        business_code_count=bc_count, business_code_months=len(bc_midxs),
        business_code_midxs=tuple(sorted(bc_midxs)), organic_sales_total=organic,
        first_midx=(first if first is not None else 0), exposure_months=exposure,
        legacy_prate=round(sum(c.legacy_prate for c in predecessors), 4), legacy_r90=r90, legacy_r180=r180)


def read_accepted_speed_to_sell_rows(conn, source_id, scope):
    """Read raw_values of ACCEPTED speed_to_sell Source Observations (immutable evidence) for a source/scope,
    in deterministic order. No identity resolution, no mutation."""
    import json
    rows = conn.execute(
        "SELECT o.raw_values FROM source_observation o JOIN import_batch b ON o.import_batch_id=b.id "
        "WHERE b.source_id=? AND b.store_scope=? AND b.lifecycle_status='completed' "
        "ORDER BY b.received_at, o.id", (source_id, scope)).fetchall()
    return [json.loads(r["raw_values"]) for r in rows]
