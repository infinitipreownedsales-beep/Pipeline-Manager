"""Executive-Demo manager cockpit intelligence (operational rebuild 2026-09-03).

Pure, stdlib-only decision layer for the daily Demo board. It turns the roster + governed physical replacement
pools into the operating vocabulary KEEP / PLAN SWAP / SWAP NOW / PULL / REVIEW, learns a per-driver mileage
velocity from OBSERVED readings only (never invents an odometer), and solves the active demos as ONE portfolio
so a single physical replacement is never handed to two executives. It imports no DB and no economics rail; the
caller supplies governed physical pools and identity, and Demo economics (Demo->SL, exit basis) stay in the
existing Service-Loaner Strategy engine.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional

# policy guidance (never blind hard triggers)
SWAP_MILES = 2000          # preferred swap around ~2,000 mi (ideally still 1,xxx)
CADENCE_DAYS = 90          # rough replacement cadence — planning guidance
PLAN_WINDOW_DAYS = 75      # approaching the cadence window — begin positioning a replacement
APPROACHING_MILES = 1500   # estimated/observed miles that put a demo in the planning window

# operating vocabulary
KEEP = "KEEP"
PLAN_SWAP = "PLAN SWAP"
SWAP_NOW = "SWAP NOW"
PULL = "PULL / REASSIGN"
REVIEW = "REVIEW"


def _date(v):
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except Exception:   # noqa: BLE001
        return None


def _days_between(a, b):
    da, db = _date(a), _date(b)
    return (db - da).days if (da and db) else None


# ---------------- mileage learning (observed only) --------------------------------------------------------
@dataclass
class MileageState:
    actual: Optional[int] = None            # the latest CURRENT observed odometer (post-assignment); never an estimate
    actual_date: Optional[str] = None
    assignment_mileage: Optional[int] = None  # mileage AT ASSIGNMENT — its own fact, NOT a current odometer
    estimated: Optional[int] = None         # forecast from last known point + velocity*elapsed — clearly labeled
    velocity: Optional[float] = None        # learned miles/day (observed points only)
    confidence: str = "none"                # none / low / moderate / high
    source: str = "unknown"                 # observed (a current reading exists) / assignment_only / unknown

    def display(self) -> str:
        # a real CURRENT observation is the only thing shown as an actual odometer
        if self.actual is not None and self.source == "observed":
            return f"{self.actual:,} mi (actual, {self.actual_date})"
        # assignment mileage is explicitly labeled as such — never presented as current actual mileage
        if self.assignment_mileage is not None:
            return f"Assigned {self.assignment_mileage:,} mi · current unknown · driver velocity learning"
        return "current mileage unknown · driver velocity learning"


def learn_velocity(observations, completed_cycles=()):
    """Miles/day learned from OBSERVED evidence only: successive dated readings within the current assignment
    and whole completed Demo cycles (mi_in→mi_out over start→end). Returns (velocity|None, confidence).

    One weak observation → no velocity / low confidence. More real points → stronger confidence. Nothing is
    fabricated: a reading with no elapsed time, or a single point, yields no velocity."""
    miles = days = points = 0
    obs = sorted([o for o in observations if o.get("miles") is not None and o.get("date")],
                 key=lambda o: str(o["date"]))
    for a, b in zip(obs, obs[1:]):
        d = _days_between(a["date"], b["date"])
        dm = int(b["miles"]) - int(a["miles"])
        if d and d > 0 and dm >= 0:
            miles += dm
            days += d
            points += 1
    for cyc in completed_cycles or ():
        d, dm = cyc.get("days"), cyc.get("miles")
        if d and int(d) > 0 and dm is not None and int(dm) >= 0:
            miles += int(dm)
            days += int(d)
            points += 1
    if days <= 0 or points == 0:
        return None, "low" if obs else "none"
    velocity = round(miles / days, 1)
    confidence = "high" if points >= 3 else ("moderate" if points >= 2 else "low")
    return velocity, confidence


def mileage_state(assignment_date, assignment_mileage, current_observations, today, *, completed_cycles=()):
    """Resolve the driver's mileage picture. ASSIGNMENT mileage is its own fact and is NEVER presented as a
    current actual odometer. A CURRENT actual reading comes only from a post-assignment observation (a recorded
    reading, a return/swap, or an authoritative dated exact-VIN odometer). Velocity is learned from observed
    intervals only: the assignment reading plus a later reading is ONE observed interval; completed cycles add
    evidence. An estimate is always a distinct forecast, never an odometer."""
    am = int(assignment_mileage) if assignment_mileage is not None else None
    cur = sorted([o for o in (current_observations or []) if o.get("miles") is not None and o.get("date")],
                 key=lambda o: str(o["date"]))
    # velocity learns from ALL observed points: the assignment reading anchors the first interval
    points = ([{"date": str(assignment_date)[:10], "miles": am}] if (am is not None and assignment_date) else []) + cur
    velocity, conf = learn_velocity(points, completed_cycles)
    if cur:                                          # a genuine CURRENT observation exists
        last = cur[-1]
        actual, actual_date = int(last["miles"]), str(last["date"])[:10]
        est = actual
        if velocity is not None:
            elapsed = _days_between(actual_date, today)
            if elapsed and elapsed > 0:
                est = int(round(actual + velocity * elapsed))
        return MileageState(actual=actual, actual_date=actual_date, assignment_mileage=am,
                            estimated=est, velocity=velocity,
                            confidence=conf if velocity is not None else "low", source="observed")
    # only the assignment reading (or nothing): current odometer is UNKNOWN; forecast from velocity if learned
    est = None
    if velocity is not None:
        base_mi, base_date = (am if am is not None else 0), (assignment_date if am is not None else None)
        elapsed = _days_between(base_date, today) if base_date else None
        if elapsed and elapsed > 0:
            est = int(round(base_mi + velocity * elapsed))
    return MileageState(assignment_mileage=am, estimated=est, velocity=velocity,
                        confidence=conf if velocity is not None else ("low" if am is not None else "none"),
                        source="assignment_only" if am is not None else "unknown")


def cadence_window_date(assignment_date):
    """The ~cadence swap-planning date from the assignment date (age-based; always available when an assignment
    date exists, so the Forecast is never blank merely because mileage has not been learned)."""
    d = _date(assignment_date)
    if d is None:
        return None
    return (d + _dt.timedelta(days=CADENCE_DAYS)).isoformat()


# ---------------- decision vocabulary --------------------------------------------------------------------
@dataclass
class DemoDecision:
    state: str
    detail: str
    days: Optional[int] = None
    mileage: MileageState = field(default_factory=MileageState)
    needs_odometer: bool = False            # an actual odometer is required to authorize the consequential swap
    pull_reason: str = ""                   # dealership reason to end Demo use independent of cadence


def decide(assignment_date, today, ms: MileageState, *, pull_reason="", identity_ok=True):
    """The operating call for one active demo. Missing current mileage downgrades certainty (an estimate/age
    window), it never erases the recommendation, and it never invents an odometer to authorize a swap."""
    if not identity_ok:
        return DemoDecision(REVIEW, "Vehicle identity is unresolved — resolve it before any Demo action.",
                            mileage=ms)
    days = _days_between(assignment_date, today)
    if days is not None and days < 0:
        days = 0                                # a future-dated assignment (clock skew) is treated as brand-new
    if pull_reason:
        return DemoDecision(PULL, f"Dealership reason to end Demo use now: {pull_reason}.", days=days,
                            mileage=ms, pull_reason=pull_reason)

    actual = ms.actual if ms.source == "observed" else None
    est = ms.estimated

    # SWAP NOW requires an ACTUAL odometer at/over the swap point (never an estimate)
    if actual is not None and actual >= SWAP_MILES:
        return DemoDecision(SWAP_NOW, f"Actual odometer {actual:,} mi — at/past the ~{SWAP_MILES:,} mi swap "
                            f"point. Replace now.", days=days, mileage=ms)

    in_window = (days is not None and days >= PLAN_WINDOW_DAYS) or (est is not None and est >= APPROACHING_MILES)
    if in_window:
        # a fresh actual odometer is required to authorize the swap whenever the actual isn't itself at/over the
        # swap point — i.e. an estimate (or age) put it in the window but no observed reading confirms the swap.
        needs_odo = not (actual is not None and actual >= SWAP_MILES)
        if actual is not None and (est is None or est < SWAP_MILES):
            detail = (f"Actual odometer {actual:,} mi and ~{days}d in service — approaching the swap window. "
                      f"Prepare the replacement.")
        elif est is not None:
            _base = (f"Actual odometer {actual:,} mi; " if actual is not None else "")
            detail = (f"{_base}~{days}d in service; estimated ~{est:,} mi from learned velocity — cadence window "
                      f"reached. Prepare the replacement. Actual odometer required before final swap execution.")
        else:
            detail = (f"~{days}d in service — cadence window reached. Prepare the replacement. Actual odometer "
                      f"required before final swap execution.")
        return DemoDecision(PLAN_SWAP, detail, days=days, mileage=ms, needs_odometer=needs_odo)

    # healthy / young
    age_bit = f"~{days}d in service" if days is not None else "recently assigned"
    mi_bit = (f", actual {actual:,} mi" if actual is not None
              else (f", estimated ~{est:,} mi" if est is not None else ", mileage not recently observed"))
    return DemoDecision(KEEP, f"Healthy Demo — {age_bit}{mi_bit}; no dealership reason to disturb it.",
                        days=days, mileage=ms)


# ---------------- portfolio allocation (one replacement unit is never assigned twice) ---------------------
_URGENCY = {SWAP_NOW: 0, PLAN_SWAP: 1, PULL: 2, KEEP: 3, REVIEW: 4}


def allocate_replacements(entries, pools):
    """Solve all active demos together. `entries` is a list of {id, decision (DemoDecision), pool_key} in roster
    order; `pools` maps pool_key -> {"current": [unit,...], "incoming": [unit,...], "order": bool} where each
    unit is any object with a `.vin` (or a dict with 'vin'). Assigns at most ONE physical replacement per demo,
    consuming it so it can never be handed to a second executive; recomputes each subsequent demo against the
    remaining units. Returns {id: {"path": "USE NOW"|"WAIT"|"ORDER"|"NONE", "unit": vin|None, "sequence": n}}.

    This does not rank Demo economics (that stays governed elsewhere); it sequences by operational urgency and
    protects the count-once physical rule."""
    used = set()
    order = sorted(range(len(entries)),
                   key=lambda i: (_URGENCY.get(entries[i]["decision"].state, 5),
                                  -(entries[i]["decision"].days or 0)))
    out = {}
    seq = 0
    for rank, i in enumerate(order, start=1):
        e = entries[i]
        dec = e["decision"]
        if dec.state in (KEEP, REVIEW):
            out[e["id"]] = {"path": "NONE", "unit": None, "sequence": rank, "state": dec.state}
            continue
        pool = pools.get(e.get("pool_key")) or {}
        chosen, path = None, "NONE"
        for u in pool.get("current", []):
            vin = _vin_of(u)
            if vin and vin not in used:
                chosen, path = vin, "USE NOW"
                break
        if chosen is None:
            for u in pool.get("incoming", []):
                vin = _vin_of(u)
                if vin and vin not in used:
                    chosen, path = vin, "WAIT"
                    break
        if chosen is None and pool.get("order"):
            path = "ORDER"
        if chosen is not None:
            used.add(chosen)
        seq += 1
        out[e["id"]] = {"path": path, "unit": chosen, "sequence": rank, "state": dec.state}
    return out


def _vin_of(u):
    if u is None:
        return None
    v = u.get("vin") if isinstance(u, dict) else getattr(u, "vin", None)
    return (str(v).strip().upper() or None) if v else None


# ---------------- Demo-suitability ranking (proven fast movers, not the largest shortage) -----------------
from dataclasses import dataclass as _dc  # noqa: E402


@_dc
class Suitability:
    cid: str
    label: str
    model: str
    score: float
    eligible: bool
    reasons: list                 # business-language phrases for the manager board (no raw numbers)
    note: str = ""
    proof: dict = None            # exact numbers / scoring — for the collapsed Technical Proof only


# objective weights — retail velocity dominates; a bigger shortage never wins on size alone
_W_VELOCITY, _W_DEPTH, _W_PREFERENCE, _W_CAVITY, _W_DTS = 3.0, 0.4, 2.0, 2.0, 0.01
# availability-timing weight — BOUNDED so it breaks near-ties (on-ground > near incoming > distant) without
# overpowering a materially better retail position: the largest timing swing (1.0) is below the cavity penalty
# (2.0) and below a single retail-velocity tier (3.0). Scaled by how urgently the executive must move.
_W_TIMING = 1.0
_TIMING_CAP_DAYS = 60         # beyond ~2 months out, the timing disadvantage saturates


def rank_demo_candidates(candidates, *, preferred_model=None, urgency=0.0):
    """Rank governed Demo replacement combinations by DEMO SUITABILITY — a Demo removes a unit from retail and
    adds miles, so the best asset is a proven fast mover that still protects the retail position, NOT simply the
    largest certified shortage.

    Each candidate: {cid, label, model, need, dts_burden, expected_demand, depth, last_on_lot,
    has_incoming_or_order, governed, timing_days(optional), post_demo_evidence(optional bool)}. Eligibility gates
    FIRST (governed + physically placeable or a defensible incoming/order path); then real-evidence scoring:
    retail velocity (Speed-to-Sell expected demand / days-to-sell), inventory depth, executive preference, minus
    a retail-cavity penalty and a BOUNDED availability-timing penalty. `urgency` (0..1) is how urgently this
    executive must move — it scales the timing factor only, so timing matters when a swap is pressing and is
    inert otherwise. `timing_days` is days until the candidate's soonest placeable unit (0 = on-ground, None =
    no placeable physical unit / order-only = maximally distant). Where no former-Demo mileage-resilience history
    exists, that limitation is STATED, not fabricated."""
    ranked = []
    u = min(max(float(urgency or 0.0), 0.0), 1.0)
    for c in candidates:
        if not c.get("governed"):
            continue                                    # ungoverned/phantom identity can never be a Demo asset
        depth = int(c.get("depth") or 0)
        has_path = bool(c.get("has_incoming_or_order"))
        eligible = bool(depth > 0 or has_path)          # placeable now, or a defensible incoming/order path
        if preferred_model and c.get("model") != preferred_model:
            # preference is honored as a hard filter only when at least one preferred candidate exists (caller
            # decides); here we keep it but heavily deprioritize non-preferred so a preferred match ranks above.
            pass
        vel = float(c.get("expected_demand") or 0.0)
        dts = float(c.get("dts_burden") or 0.0)
        pref = 1.0 if (preferred_model and c.get("model") == preferred_model) else 0.0
        cavity = 1.0 if (c.get("last_on_lot") and not has_path) else 0.0
        # availability timing: 0d (on-ground) → no penalty; farther out → more penalty, scaled by urgency, capped
        td = c.get("timing_days")
        t_norm = 1.0 if td is None else min(max(float(td), 0.0), _TIMING_CAP_DAYS) / _TIMING_CAP_DAYS
        timing_penalty = _W_TIMING * u * t_norm
        score = round(_W_VELOCITY * vel + _W_DEPTH * min(depth, 3) + _W_PREFERENCE * pref
                      - _W_CAVITY * cavity - _W_DTS * dts - timing_penalty, 4)
        # business language for the manager board — no raw decimals (exact numbers go in `proof`)
        reasons = []
        reasons.append("FAST MOVER · strong retail demand" if vel >= 3.0
                       else ("steady retail demand" if vel >= 1.0 else "limited retail demand"))
        reasons.append(f"planning depth {depth} (breadth of the plan, not on-ground stock)")
        if pref:
            reasons.append("matches executive preference")
        if u > 0:
            if td == 0:
                reasons.append("available now")
            elif td is not None:
                reasons.append(f"arrives in ~{int(td)}d")
            else:
                reasons.append("no on-ground/near unit — furthest to place")
        if cavity:
            reasons.append("would leave a retail cavity — protect/reorder first")
        note = "" if c.get("post_demo_evidence") else "no former-Demo mileage-resilience history yet"
        proof = {"expected_demand": vel, "days_to_sell_burden": dts, "planning_depth": depth,
                 "certified_need": int(c.get("need") or 0), "preference_match": bool(pref),
                 "timing_days": td, "urgency": round(u, 2), "score": score}
        ranked.append(Suitability(c.get("cid"), c.get("label", ""), c.get("model", ""), score, eligible,
                                  reasons, note, proof))
    ranked.sort(key=lambda s: (s.eligible, s.score), reverse=True)
    return ranked


# candidate action verbs for the "Best Demo Candidates" section
USE_NOW = "USE NOW"
WAIT_FOR_INCOMING = "WAIT FOR INCOMING"
REORDER_BEFORE_PULLING = "REORDER BEFORE PULLING"
ORDER_FOR_DEMO = "ORDER FOR DEMO"
ORDER_REVIEW = "ORDER PATH — REVIEW"
NOT_SAFE = "NOT CURRENTLY SAFE TO DEMO"


def candidate_action(current_count, has_incoming, *, orderable, order_available=True):
    """The operator action for one governed Demo candidate, from real physical availability + orderability.

    Backup-depth law: 2+ safe on-ground copies → USE NOW; exactly ONE on-ground (last retail unit) → REORDER
    BEFORE PULLING (never silently pull the last one); none on-ground but a committed incoming unit → WAIT FOR
    INCOMING; no physical anywhere → a governed ORDER FOR DEMO, but only when current orderability is confirmed
    — otherwise ORDER PATH — REVIEW (fail closed; deterministic identity is not proof the factory accepts an
    order today). If there is no physical unit and no order path at all, it is NOT CURRENTLY SAFE TO DEMO."""
    cc = int(current_count or 0)
    if cc >= 2:
        return USE_NOW
    if cc == 1:
        return REORDER_BEFORE_PULLING
    if has_incoming:
        return WAIT_FOR_INCOMING
    if not order_available:
        return NOT_SAFE
    return ORDER_FOR_DEMO if orderable else ORDER_REVIEW


def anticipated_returns(entries):
    """The physical units expected to return to retail soon (active demos whose call is a swap/pull), each
    counted ONCE by unit identity — so Ordering can represent a returning Demo as future supply exactly once and
    not reorder a vehicle that is about to come back. `entries`: [{unit, state}]. Returns a deduped unit list."""
    swap_states = {PLAN_SWAP, SWAP_NOW, PULL}
    seen, out = set(), []
    for e in entries:
        u = _vin_of({"vin": e.get("unit")}) if isinstance(e, dict) else None
        if u and e.get("state") in swap_states and u not in seen:
            seen.add(u)
            out.append(u)
    return out
