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

from . import credibility as cr
from . import data_quality as dq
from . import demand_bridge as db_
from . import supply_bridge as sb_
from .dms_identity import resolve_or_create_planning_combination
from .planning_settings import resolve_target_days_supply

# Breadth thresholds (decision, not demand): a cohort is worth CARRYING (represented) if its 60-day
# velocity depth is at least half a unit, OR if externally-satisfied (DT/DNQ) demand recurs strongly.
# These gate the BREADTH question only; DEPTH remains velocity/risk-driven and DT/DNQ never scales it.
_REPRESENT_VELOCITY_FLOOR = 0.5
_REPRESENT_RECURRENCE = 0.5


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
    need: float = None                 # NET actionable acquisition (units to commit now); never gross
    excess: float = None               # NET surplus vs the 60-day level (time-aware)
    current_supply: int = 0
    future_supply: int = 0
    evidence_tier: str = None
    legacy_prate: float = None
    refused_reason: str = None
    coverage_evidence: dict = field(default_factory=dict)
    # decision transparency
    target_level: float = None
    breadth: str = None
    represented: bool = None
    evidence_level: str = None
    credibility_z: float = None
    dts_burden: float = None
    dtdnq_strength: float = None
    incoming_in_horizon: int = 0
    incoming_post_horizon: int = 0
    pending_timing: int = 0
    near_term_trough: float = None


# ---- calibration + per-cohort decision --------------------------------------------------------------
def calibrate(cohorts, *, latest_midx, part_frac):
    """Calibrate the credibility model + hierarchical prior index from the whole cohort panel."""
    series = [cr.month_series(c.retail_by_month, c.first_midx, latest_midx) for c in cohorts]
    model = cr.estimate_k(series)
    index = cr.build_parent_index(cohorts, latest_midx=latest_midx, part_frac=part_frac)
    return model, index


def cohort_credibility(cohort, index, model):
    """The governed credibility block DemandService blends with (prior from nearest valid higher level)."""
    prior = cr.nearest_prior(cohort.key, cohort.representative, index)
    return {"applied": True, "min_exposure": 1.0, "exact_n": cohort.sales_total, "k": model.k,
            "z_cap": 1.0, "prior_rate": prior.rate, "evidence_level": prior.level,
            "prior_sample": prior.sample, "credibility_z": model.weight(cohort.sales_total),
            "k_method": model.method, "k_stable": model.stable,
            "calibration_sample": model.calibration_sample, "fallback_reason": model.fallback_reason}


def decide_target_level(demand_result, cohort, supply, dtdnq, target_days_supply):
    """Two-stage decision. DEPTH: 60-day velocity coverage from the credibility-shrunk rate, dampened by
    historical-DTS risk (evidence-weighted, never a hard cutoff). BREADTH: should the cohort be represented
    at all? Strong DT/DNQ recurrence justifies carrying ONE unit (representation), but never scales depth."""
    monthly = demand_result.monthly_expected
    avg_monthly = (sum(monthly.values()) / len(monthly)) if monthly else 0.0
    daily = avg_monthly / 30.0
    dis = supply.dis_values if supply else []
    dis_med = median(dis) if dis else None
    burden = cr.dts_burden(cohort.dts_average, len(cohort.dts_values), dis_med)
    velocity_depth = round(daily * float(target_days_supply) * burden, 6)

    by_velocity = velocity_depth >= _REPRESENT_VELOCITY_FLOOR
    by_recurrence = dtdnq >= _REPRESENT_RECURRENCE
    if not (by_velocity or by_recurrence):
        target, breadth, represented = 0.0, "not_represented", False
    elif by_velocity:
        target, breadth, represented = velocity_depth, "represented_by_velocity", True
    else:  # represented only by recurrent externally-satisfied demand -> carry ONE, do not scale depth
        target, breadth, represented = max(velocity_depth, 1.0), "represented_by_recurrence", True
    decision = {"target_level": round(target, 6), "breadth": breadth, "represented": represented,
                "velocity_depth": velocity_depth, "avg_monthly_demand": round(avg_monthly, 4),
                "daily_rate": round(daily, 5), "target_days_supply": target_days_supply,
                "dts_average": cohort.dts_average, "dts_sample": len(cohort.dts_values),
                "dts_burden": burden, "aging_median_dis": dis_med, "dtdnq_strength": dtdnq,
                "business_code_months": cohort.business_code_months}
    return target, decision


def run_planning(ctx, supply_by_key, demand_by_key, exceptions, *, target_days_supply, current_month,
                 horizon=None, latest_midx=None, part_frac=1.0):
    """Governed DATA_ONLY decision engine (corrected). For each cohort: shrink the exact velocity toward a
    higher-level prior by calibrated credibility; decide BREADTH (represent?) then DEPTH (how many, velocity
    + DTS-risk); then compute NET actionable acquisition via the time-phased order-up-to model. Refuse only
    when there is no accepted demand history at all. Totals sum NET (actionable) Need/Excess — never gross."""
    horizon = horizon or derive_horizon(current_month, supply_by_key)
    if latest_midx is None:
        latest_midx = db_.midx_of(current_month.replace("-", ""))
    cohorts = list(demand_by_key.values())
    cred_model, prior_index = calibrate(cohorts, latest_midx=latest_midx, part_frac=part_frac)
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
        # ---- low-evidence safety: refuse Need/Excess without any accepted demand history ----
        if dem is None or not dem.retail_by_month:
            outcomes.append(CohortPlanOutcome(
                key=key, identity=(dem.identity if dem else sup.identity), issued=False,
                current_supply=cur, future_supply=fut, refused_reason="no_accepted_demand_history",
                legacy_prate=(dem.legacy_prate if dem else None)))
            continue
        credibility = cohort_credibility(dem, prior_index, cred_model)
        demand_result = ctx.demand.issue(
            comb, ctx.scope, horizon, retail_by_month=dem.retail_by_month,
            exposure_months=dem.exposure_months, sample_size=dem.sales_total,
            calculation_version=ctx.demand_cv, source_refs=[comb.id], credibility=credibility)
        if demand_result.evidence_tier != "exact":       # defence-in-depth; should be exact given rbm
            outcomes.append(CohortPlanOutcome(
                key=key, identity=dem.identity, issued=False, current_supply=cur, future_supply=fut,
                evidence_tier=demand_result.evidence_tier, refused_reason="insufficient_evidence_tier",
                legacy_prate=dem.legacy_prate))
            continue
        ctx.forecast.issue(demand_result, calculation_version=ctx.demand_cv)
        dtdnq = cr.dtdnq_strength(dem.business_code_midxs, latest_midx=latest_midx)
        target, decision = decide_target_level(demand_result, dem, sup, dtdnq, target_days_supply)
        decision.update({"credibility": credibility, "evidence_level": credibility["evidence_level"],
                         "legacy_prate": dem.legacy_prate})
        counts = {"current": cur, "future": fut, "committed": 0}
        qualifying = list(sup.qualifying) if sup else []
        plan = ctx.planning.issue_position(demand_result, horizon=horizon, qualifying=qualifying,
                                           target_level=target, counts=counts,
                                           calculation_version=ctx.plan_cv, decision=decision)
        cov = plan.desired_ending_coverage
        outcomes.append(CohortPlanOutcome(
            key=key, identity=dem.identity, issued=True, plan_id=plan.id, planning_state=plan.planning_state,
            need=plan.need, excess=plan.excess, current_supply=cur, future_supply=fut,
            evidence_tier=demand_result.evidence_tier, legacy_prate=dem.legacy_prate, coverage_evidence=decision,
            target_level=decision["target_level"], breadth=decision["breadth"],
            represented=decision["represented"], evidence_level=credibility["evidence_level"],
            credibility_z=credibility["credibility_z"], dts_burden=decision["dts_burden"],
            dtdnq_strength=dtdnq, incoming_in_horizon=cov.get("incoming_in_horizon", 0),
            incoming_post_horizon=cov.get("incoming_post_horizon", 0),
            pending_timing=cov.get("pending_timing", 0), near_term_trough=cov.get("near_term_trough")))
    # data-quality exceptions, filtered by acknowledgement (unchanged acks suppressed; changed ones resurface)
    is_ack = dq.metadata_ack_lookup(ctx.metadata) if ctx.metadata is not None else (lambda fp: False)
    active_exceptions = dq.filter_unacknowledged(exceptions, is_ack)
    issued = [o for o in outcomes if o.issued]
    acquire = [o for o in issued if (o.need or 0) > 0]
    return {"horizon": horizon, "target_days_supply": target_days_supply, "outcomes": outcomes,
            "issued_count": len(issued), "refused_count": len(outcomes) - len(issued),
            "represented_count": sum(1 for o in issued if o.represented),
            "acquire_count": len(acquire),
            "total_need": round(sum(o.need for o in issued), 4),          # NET actionable acquisition
            "total_excess": round(sum(o.excess for o in issued), 4),      # NET surplus (time-aware)
            "credibility_model": {"k": cred_model.k, "method": cred_model.method,
                                  "stable": cred_model.stable, "n_cohorts": cred_model.n_cohorts,
                                  "calibration_sample": cred_model.calibration_sample,
                                  "fallback_reason": cred_model.fallback_reason},
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
                        target_days_supply=tds, current_month=current_month, latest_midx=latest,
                        part_frac=part_frac)
