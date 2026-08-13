"""Continuous 60-day replenishment + discrete whole-vehicle action engine.

Operates ON TOP OF the corrected continuous engine (credibility-shrunk demand -> timed supply -> projected
position -> 60-day target). It translates the continuous portfolio optimum into whole-vehicle actions using
a time-phased coverage trajectory, and separates a projected FUTURE Need from a currently-ACTIONABLE Need so
future replenishment is not front-loaded into a buy-now recommendation.

CHECKPOINT CONVENTION (one convention everywhere; no month counted twice):
  P(m) = projected inventory position at the END of month m, AFTER demand THROUGH month m is consumed and
         AFTER supply available by that checkpoint has arrived.
  T(m) = forward productive-stock requirement for the NEXT 60 DAYS AFTER checkpoint m (the two months
         following m) -- so T(September) = October + November forward demand, NOT September + October.
  Therefore P(September) subtracts September demand and T(September) never includes September again.

ACTION HORIZON vs FORECAST TAIL:
  action_horizon = how far forward current replenishment decisions are evaluated (e.g. Sep/Oct/Nov).
  forecast tail  = the extra months (e.g. Dec/Jan) needed ONLY to compute T at the end of the action
                   horizon. Tail demand is never purchased now and never becomes an action-horizon buy.

ACTIONABILITY (DATA_ONLY):
  A projected future gap becomes ACQUIRE-now only if a commitment is REQUIRED NOW (its coverage falls inside
  the near-term protection window and a now-commitment can arrive in time). Otherwise it is MONITOR. This
  engine determines that a commitment is required now from governed lead/review timing; it does NOT claim a
  specific dealer-trade / allocation / production channel exists unless real source evidence establishes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Governed replenishment timing (DATA_ONLY defaults; evidence/policy may override, never hand-tuned to output).
DEFAULT_LEAD_MONTHS = 1        # a commitment made now can contribute to coverage this many months out
DEFAULT_REVIEW_MONTHS = 1      # replenishment is revisited on this cadence
FORWARD_DAYS = 60              # the 60-day productive-coverage objective
TAIL_MONTHS = 2               # forecast tail needed to compute forward-60-day T at the last action checkpoint


def month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    t = (y * 12 + (m - 1)) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _idx(ym):
    return int(ym[:4]) * 12 + int(ym[5:7])


def extended_months(action_horizon, tail=TAIL_MONTHS):
    """action_horizon + the forecast tail (extra months used ONLY to compute forward T at the horizon end)."""
    last = action_horizon[-1]
    return list(action_horizon) + [month_add(last, i) for i in range(1, tail + 1)]


def forward_target(monthly_expected, checkpoint, *, forward_days=FORWARD_DAYS, burden=1.0):
    """T(m): forward productive-stock requirement for the next `forward_days` AFTER checkpoint m, dampened by
    the historical-DTS burden (slow movers want less depth). ~60 days == the two months following m."""
    n_months = max(1, round(forward_days / 30.0))
    total = 0.0
    for k in range(1, n_months + 1):
        total += float(monthly_expected.get(month_add(checkpoint, k), 0.0))
    return round(total * float(burden), 6)


@dataclass
class Checkpoint:
    month: str
    position: float          # P(m): end-of-month net inventory after demand-through-m and arrivals-by-m
    target: float            # T(m): forward 60-day requirement after m
    actionable: bool         # within the near-term protection window (a now-decision must cover it)


def _demand_through(monthly_expected, action_horizon, i):
    """Cumulative expected demand consumed by END of action_horizon[i] (inclusive of that month)."""
    return round(sum(float(monthly_expected.get(action_horizon[k], 0.0)) for k in range(i + 1)), 6)


def build_checkpoints(*, arrived, confirmed_avail, action_avail, monthly_expected, action_horizon,
                      current_month, burden=1.0, lead_months=DEFAULT_LEAD_MONTHS,
                      review_months=DEFAULT_REVIEW_MONTHS):
    """Build the end-of-month checkpoint trajectory. `confirmed_avail` / `action_avail` are lists of
    availability months (unknown-timing inbound is excluded upstream). A checkpoint is `actionable` when it
    falls inside the near-term protection window [now, now + review + lead]."""
    protection_end = _idx(month_add(current_month, review_months + lead_months))
    out = []
    for i, m in enumerate(action_horizon):
        end = _idx(m)
        pos = (arrived
               + sum(1 for a in confirmed_avail if _idx(a) <= end)
               + sum(1 for a in action_avail if _idx(a) <= end)
               - _demand_through(monthly_expected, action_horizon, i))
        out.append(Checkpoint(month=m, position=round(pos, 6),
                              target=forward_target(monthly_expected, m, burden=burden),
                              actionable=(end <= protection_end)))
    return out


def trajectory_loss(checkpoints, *, cu=1.0, co=1.0, actionable_only=False):
    """Time-phased coverage-deviation loss. Timing is expressed by P(m); there is NO urgency multiplier."""
    total = 0.0
    for c in checkpoints:
        if actionable_only and not c.actionable:
            continue
        total += cu * max(0.0, c.target - c.position) + co * max(0.0, c.position - c.target)
    return round(total, 6)


@dataclass
class ActionPlan:
    acquire_units: int = 0
    action_availability: str = None          # when a committed unit contributes (now + lead)
    monitor_months: list = field(default_factory=list)   # future gaps not yet requiring a commitment
    arrived_excess: int = 0
    incoming_excess: int = 0
    excess_slot_months: list = field(default_factory=list)
    analytical_deficit: float = 0.0
    analytical_excess: float = 0.0
    marginal_trace: list = field(default_factory=list)    # acquire checkpoint objective (evidence)
    trajectory: list = field(default_factory=list)        # [{m, P, T}] final projected trajectory (evidence)
    excess_trace: list = field(default_factory=list)      # per-removal Delta_remove trace (evidence)
    loss_before: float = 0.0
    loss_after: float = 0.0


def allocate(*, arrived, confirmed_avail, monthly_expected, action_horizon, current_month, burden=1.0,
             cu=1.0, co=1.0, lead_months=DEFAULT_LEAD_MONTHS, review_months=DEFAULT_REVIEW_MONTHS):
    """Discrete whole-vehicle allocation. ACQUIRE integer units (available now+lead) greedily while each
    reduces the loss over the ACTIONABLE protection window (Delta_add > 0). Future gaps outside that window,
    or unrepairable near-term gaps, become MONITOR -- never a buy-now. Then run the mirror to find whole-unit
    ARRIVED / INCOMING excess. Continuous deficits/excess are retained as analytical evidence only."""
    action_avail_month = month_add(current_month, lead_months)

    def cps(action_avail):
        return build_checkpoints(arrived=arrived, confirmed_avail=confirmed_avail, action_avail=action_avail,
                                 monthly_expected=monthly_expected, action_horizon=action_horizon,
                                 current_month=current_month, burden=burden, lead_months=lead_months,
                                 review_months=review_months)

    base_cps = cps([])
    plan = ActionPlan(action_availability=action_avail_month,
                      loss_before=trajectory_loss(base_cps, cu=cu, co=co))
    # ---- ACQUIRE: order-up-to at the CURRENT PROTECTION checkpoint only (now + lead) ----
    # Today's commitment can first affect coverage at month now+lead; earlier months are unrepairable-now and
    # LATER months are protected by future normal reviews. So the quantity is a discrete newsvendor order-up-to
    # at that single protected checkpoint's PROJECTED position (demand-through-checkpoint already consumed) --
    # NOT a sum over Sep+Oct, which front-loaded October's re-order into today. Future months remain MONITOR.
    lead_i = next((i for i, c in enumerate(base_cps) if _idx(c.month) >= _idx(action_avail_month)), None)
    q = 0
    if lead_i is not None:
        p0 = base_cps[lead_i].position                 # projected position at the protected checkpoint, no action
        tl = base_cps[lead_i].target

        def _cl(qq):                                    # discrete checkpoint loss for qq whole units
            pos = p0 + qq
            return cu * max(0.0, tl - pos) + co * max(0.0, pos - tl)
        best = _cl(0)
        while _cl(q + 1) < best - 1e-12:                # convex -> advance while it strictly improves
            q += 1
            best = _cl(q)
        plan.marginal_trace.append({"protection_checkpoint": base_cps[lead_i].month, "p0": round(p0, 6),
                                    "target": round(tl, 6), "chosen_q": q,
                                    "loss_by_q": {qq: round(_cl(qq), 6) for qq in range(0, q + 3)}})
    plan.acquire_units = q
    final_cps = cps([action_avail_month] * q)
    plan.loss_after = trajectory_loss(final_cps, cu=cu, co=co)
    # ---- MONITOR: FUTURE coverage gaps whose replenishment is deferred to a later normal review. The
    # protected checkpoint itself has already been ordered up-to (any residual there is whole-vehicle
    # granularity, not a monitor); only checkpoints AFTER it are future-review risk. ----
    protected = base_cps[lead_i].month if lead_i is not None else action_avail_month
    for c in final_cps:
        if _idx(c.month) > _idx(protected) and c.target - c.position > 1e-9:
            plan.monitor_months.append({"month": c.month, "shortfall": round(c.target - c.position, 6),
                                        "actionable": c.actionable})
    plan.analytical_deficit = round(sum(max(0.0, c.target - c.position) for c in final_cps), 6)
    plan.trajectory = [{"m": c.month, "P": round(c.position, 4), "T": round(c.target, 4)} for c in final_cps]
    # ---- EXCESS mirror: remove confirmed slots (arrived / timed incoming) while it improves the trajectory ----
    arrived_rem, incoming_rem, ex_months, ex_trace = _excess(
        arrived, confirmed_avail, monthly_expected, action_horizon, current_month, burden, cu, co,
        lead_months, review_months)
    plan.arrived_excess, plan.incoming_excess = arrived_rem, incoming_rem
    plan.excess_slot_months, plan.excess_trace = ex_months, ex_trace
    plan.analytical_excess = round(sum(max(0.0, c.position - c.target) for c in final_cps), 6)
    return plan


_FEAS_EPS = 1e-9


def _excess(arrived, confirmed_avail, monthly_expected, action_horizon, current_month, burden, cu, co,
            lead_months, review_months):
    """Greedy whole-unit removal with a FEASIBILITY constraint. A positive summed Delta_remove is NOT
    sufficient: early-month overstock savings can outweigh a shortage the removal creates in a later month.
    A removal is applied only if FEASIBLE(s) AND Delta_remove(s) > 0, where FEASIBLE means the resulting
    trajectory keeps P(m) >= T(m) at every checkpoint the removal affects -- i.e. the retained inventory (plus
    only CONFIRMED/timed arrivals already in the trajectory) never drops below the 60-day target at a
    checkpoint it must protect. A later hypothetical replenishment is never used to justify disposing an
    arrived unit. For an arrived removal, every checkpoint is affected; for a timed-incoming removal, only
    checkpoints at/after its availability month are affected (earlier months are unchanged)."""
    def cps(a, conf):
        return build_checkpoints(arrived=a, confirmed_avail=conf, action_avail=[],
                                 monthly_expected=monthly_expected, action_horizon=action_horizon,
                                 current_month=current_month, burden=burden, lead_months=lead_months,
                                 review_months=review_months)

    def traj(a, conf):
        return [{"m": c.month, "P": round(c.position, 4), "T": round(c.target, 4)} for c in cps(a, conf)]

    def min_slack(a, conf, from_month=None):
        """Smallest P(m)-T(m) over the affected checkpoints (all, or only those at/after from_month)."""
        vals = [c.position - c.target for c in cps(a, conf)
                if from_month is None or _idx(c.month) >= _idx(from_month)]
        return min(vals) if vals else 0.0

    a, conf = arrived, list(confirmed_avail)
    arrived_rem = incoming_rem = 0
    removed_months, trace = [], []
    while True:
        cur = trajectory_loss(cps(a, conf), cu=cu, co=co)
        candidates = []                            # (delta, kind, slot, feasible, slack)
        if a > 0:
            d = round(cur - trajectory_loss(cps(a - 1, conf), cu=cu, co=co), 6)
            slack = round(min_slack(a - 1, conf), 6)          # arrived removal affects ALL checkpoints
            candidates.append((d, "arrived", None, slack >= -_FEAS_EPS, slack))
        for s in sorted(set(conf), key=_idx):
            trial = list(conf); trial.remove(s)
            d = round(cur - trajectory_loss(cps(a, trial), cu=cu, co=co), 6)
            slack = round(min_slack(a, trial, from_month=s), 6)   # incoming affects only checkpoints >= its month
            candidates.append((d, "incoming", s, slack >= -_FEAS_EPS, slack))
        feasible = [c for c in candidates if c[0] > 0 and c[3]]
        if not feasible:
            # record any positive-Delta removal that FEASIBILITY blocked (evidence: why removal stopped)
            for d, kind, slot, feas, slack in candidates:
                if d > 0 and not feas:
                    trace.append({"removed": kind, "slot_month": (slot or "now/arrived"), "delta_remove": d,
                                  "rejected": True,
                                  "reason": f"infeasible: would leave min P(m)-T(m)={slack} < 0 at a protected checkpoint",
                                  "before": traj(a, conf),
                                  "after": traj(a - 1, conf) if kind == "arrived"
                                  else traj(a, [x for x in conf if x != slot])})
            break
        best = max(feasible, key=lambda c: c[0])
        d, kind, slot, _feas, slack = best
        before = traj(a, conf)
        if kind == "arrived":
            a -= 1; arrived_rem += 1; removed_months.append("arrived")
        else:
            conf.remove(slot); incoming_rem += 1; removed_months.append(slot)
        trace.append({"removed": kind, "slot_month": (slot or "now/arrived"), "delta_remove": d,
                      "feasible": True, "min_slack_after": slack, "before": before, "after": traj(a, conf)})
    return arrived_rem, incoming_rem, removed_months, trace
