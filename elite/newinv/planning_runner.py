"""Governed DATA_ONLY New-Inventory planning runner.

Ties the real permanent DMS snapshots + real Speed-to-Sell demand into governed, issued Phase 4 plans that
the existing New Inventory UI reads — with NO execution, NO shadow escalation, NO ProductionOrder/VehicleUnit
fabrication, NO Serial identity. Elite DemandService is authoritative; legacy PRATE is carried alongside as a
pilot comparison only. Target Days Supply is the dealer's plain objective; the engine still decides
combination-level coverage from evidence (velocity via the demand rate, aging via DLR-INV DIS, reliance on
incoming supply via month-bucketed qualifying). Need/Excess is REFUSED for any cohort whose demand evidence
is materially insufficient — never fabricated from defaults, sample data, or broad averages.

Layering: `run_planning` is the pure, testable core (it takes already-built services + computed supply and
demand and issues governed plans); `PlanningContext` bundles the services; `plan_from_stores` reads supply
(latest snapshot) and demand (accepted Speed-to-Sell observations) from the DB and calls the core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from . import data_quality as dq
from . import demand_bridge as db_
from . import supply_bridge as sb_
from .dms_identity import resolve_or_create_planning_combination
from .planning_settings import resolve_target_days_supply


# ---- horizon derivation (engine-derived, not a dealer knob) ------------------------------------------
def _month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    t = (y * 12 + (m - 1)) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _month_cmp_key(ym):
    return int(ym[:4]) * 12 + int(ym[5:7])


def derive_horizon(current_month, supply_by_key, *, min_months=3, max_months=6):
    """Derive the actionable forward horizon from now through the known incoming-supply arrival window
    (production_month / ETA), bounded to [min_months, max_months]. No manual order-month/horizon knob."""
    start = _month_add(current_month, 1)
    arrivals = [q["available_month"] for c in supply_by_key.values() for q in c.qualifying
                if q["stage"] in ("ONS", "SIT", "NNA-INV") and q.get("available_month")]
    last = max([_month_cmp_key(start)] + [_month_cmp_key(a) for a in arrivals])
    span = max(min_months, min(max_months, last - _month_cmp_key(start) + 1))
    return [_month_add(start, i) for i in range(span)]


# ---- Target-Days-Supply coverage objective (engine-decided per cohort) --------------------------------
def _aging_factor(dis_values):
    """Persistently-aged arrived inventory dampens desired coverage (don't pile onto a slow mover). Bounded."""
    if not dis_values:
        return 1.0, None
    med = median(dis_values)
    factor = 0.5 if med > 120 else (0.75 if med > 90 else 1.0)
    return factor, med


def coverage_from_target_days_supply(demand_result, horizon, target_days_supply, supply_cohort):
    """Desired ending coverage (units) = the cohort's own daily demand rate x Target Days Supply, dampened for
    persistent aging. Returns (coverage_target_units, evidence). Never a naive 'own exactly N-day demand'."""
    monthly = demand_result.monthly_expected
    avg_monthly = (sum(monthly.values()) / len(monthly)) if monthly else 0.0
    daily_rate = avg_monthly / 30.0
    base_units = daily_rate * float(target_days_supply)
    dis = supply_cohort.dis_values if supply_cohort else []
    factor, med = _aging_factor(dis)
    coverage = round(max(0.0, base_units * factor), 6)
    return coverage, {"target_days_supply": target_days_supply, "avg_monthly_demand": round(avg_monthly, 4),
                      "daily_rate": round(daily_rate, 5), "base_target_units": round(base_units, 4),
                      "aging_median_dis": med, "aging_dampening_factor": factor}


@dataclass
class PlanningContext:
    scope: str
    store: object            # NewInvStore
    clock: object
    demand: object           # DemandService
    forecast: object         # ForecastService
    planning: object         # PlanningService
    demand_cv: str
    plan_cv: str
    metadata: object = None  # key/value store for Data-Quality acknowledgements (optional)


@dataclass
class CohortPlanOutcome:
    key: tuple
    identity: str
    issued: bool
    plan_id: str = None
    planning_state: str = None
    need: float = None
    excess: float = None
    current_supply: int = 0
    future_supply: int = 0
    evidence_tier: str = None
    legacy_prate: float = None
    refused_reason: str = None
    coverage_evidence: dict = field(default_factory=dict)


def run_planning(ctx, supply_by_key, demand_by_key, exceptions, *, target_days_supply, current_month,
                 horizon=None):
    """Pure core: issue governed DATA_ONLY plans for cohorts with sufficient demand evidence; refuse (record
    supply-intelligence-only) otherwise. `demand_by_key` are CohortDemand records; `supply_by_key` SupplyCohort
    records. Returns a structured summary."""
    horizon = horizon or derive_horizon(current_month, supply_by_key)
    keys = sorted(set(supply_by_key) | set(demand_by_key), key=lambda t: str(t))
    outcomes = []
    for key in keys:
        sup = supply_by_key.get(key)
        dem = demand_by_key.get(key)
        rep = (dem.representative if dem else sup.representative)
        comb = resolve_or_create_planning_combination(ctx.store, ctx.clock, rep, ctx.scope,
                                                       source_ref="dms_planning_runner")
        cur = sup.current if sup else 0
        fut = sup.future if sup else 0
        # ---- low-evidence safety: refuse Need/Excess without real accepted demand history ----
        if dem is None or not dem.retail_by_month:
            outcomes.append(CohortPlanOutcome(
                key=key, identity=(dem.identity if dem else sup.identity), issued=False,
                current_supply=cur, future_supply=fut,
                refused_reason="no_accepted_demand_history",
                legacy_prate=(dem.legacy_prate if dem else None)))
            continue
        demand_result = ctx.demand.issue(
            comb, ctx.scope, horizon, retail_by_month=dem.retail_by_month,
            exposure_months=dem.exposure_months, sample_size=dem.sales_total,
            calculation_version=ctx.demand_cv, source_refs=[comb.id])
        if demand_result.evidence_tier != "exact":       # defence-in-depth; should be exact given rbm
            outcomes.append(CohortPlanOutcome(
                key=key, identity=dem.identity, issued=False, current_supply=cur, future_supply=fut,
                evidence_tier=demand_result.evidence_tier, refused_reason="insufficient_evidence_tier",
                legacy_prate=dem.legacy_prate))
            continue
        ctx.forecast.issue(demand_result, calculation_version=ctx.demand_cv)
        coverage_target, cov_ev = coverage_from_target_days_supply(demand_result, horizon,
                                                                   target_days_supply, sup)
        counts = {"current": cur, "future": fut, "committed": 0}
        qualifying = list(sup.qualifying) if sup else []
        plan = ctx.planning.issue(demand_result, horizon=horizon, qualifying=qualifying,
                                  coverage_target=coverage_target, counts=counts,
                                  calculation_version=ctx.plan_cv)
        outcomes.append(CohortPlanOutcome(
            key=key, identity=dem.identity, issued=True, plan_id=plan.id, planning_state=plan.planning_state,
            need=plan.need, excess=plan.excess, current_supply=cur, future_supply=fut,
            evidence_tier=demand_result.evidence_tier, legacy_prate=dem.legacy_prate, coverage_evidence=cov_ev))
    # data-quality exceptions, filtered by acknowledgement (unchanged acks suppressed; changed ones resurface)
    is_ack = dq.metadata_ack_lookup(ctx.metadata) if ctx.metadata is not None else (lambda fp: False)
    active_exceptions = dq.filter_unacknowledged(exceptions, is_ack)
    issued = [o for o in outcomes if o.issued]
    return {"horizon": horizon, "target_days_supply": target_days_supply, "outcomes": outcomes,
            "issued_count": len(issued), "refused_count": len(outcomes) - len(issued),
            "total_need": round(sum(o.need for o in issued), 4),
            "total_excess": round(sum(o.excess for o in issued), 4),
            "data_quality_exceptions": active_exceptions,
            "data_quality_exception_count": len(active_exceptions)}


def plan_from_stores(ctx, reader, *, dms_source_id, sts_source_id, current_month, part_frac=1.0,
                     latest_midx=None, target_days_supply=None):
    """Read supply (latest snapshot) + demand (accepted Speed-to-Sell observations) from the DB and run the
    governed DATA_ONLY planning. Does not import, migrate, execute, or change shadow state."""
    tds = target_days_supply if target_days_supply is not None else resolve_target_days_supply(ctx.metadata)
    supply_rows = sb_.read_latest_snapshot_rows(reader, dms_source_id, ctx.scope)
    supply_by_key = sb_.build_supply(supply_rows, current_month=current_month)
    demand_rows = db_.read_accepted_speed_to_sell_rows(ctx.store.conn, sts_source_id, ctx.scope)
    midxs = [db_.midx_of(r.get("sales_month")) for r in demand_rows]
    midxs = [m for m in midxs if m is not None]
    latest = latest_midx if latest_midx is not None else (max(midxs) if midxs else db_.midx_of(current_month.replace("-", "")))
    current_midx = db_.midx_of(current_month.replace("-", ""))
    built = db_.build_demand(demand_rows, latest_midx=latest, current_midx=current_midx, part_frac=part_frac)
    return run_planning(ctx, supply_by_key, built["cohorts"], built["exceptions"],
                        target_days_supply=tds, current_month=current_month)
