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
    actual: Optional[int] = None            # the latest OBSERVED odometer (never an estimate)
    actual_date: Optional[str] = None
    estimated: Optional[int] = None         # forecast from last actual + velocity*elapsed — clearly labeled
    velocity: Optional[float] = None        # learned miles/day (observed points only)
    confidence: str = "none"                # none / low / moderate / high
    source: str = "unknown"                 # observed / estimated / unknown

    def display(self) -> str:
        if self.actual is not None and self.source == "observed":
            return f"{self.actual:,} mi (actual, {self.actual_date})"
        if self.estimated is not None:
            return f"~{self.estimated:,} mi (estimated)"
        return "mileage not recently observed"


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


def mileage_state(assignment_date, observations, today, *, completed_cycles=()):
    """Resolve the driver's mileage picture WITHOUT ever presenting an estimate as an actual reading."""
    velocity, conf = learn_velocity(observations, completed_cycles)
    obs = sorted([o for o in observations if o.get("miles") is not None and o.get("date")],
                 key=lambda o: str(o["date"]))
    if obs:
        last = obs[-1]
        actual, actual_date = int(last["miles"]), str(last["date"])[:10]
        est = actual
        if velocity is not None:
            elapsed = _days_between(actual_date, today)
            if elapsed and elapsed > 0:
                est = int(round(actual + velocity * elapsed))
        return MileageState(actual=actual, actual_date=actual_date,
                            estimated=est if est != actual else actual,
                            velocity=velocity, confidence=conf if velocity is not None else "low",
                            source="observed")
    # no observation at all: forecast only from age if a velocity was learned from prior cycles
    if velocity is not None:
        elapsed = _days_between(assignment_date, today)
        if elapsed and elapsed > 0:
            return MileageState(estimated=int(round(velocity * elapsed)), velocity=velocity,
                                confidence=conf, source="estimated")
    return MileageState(source="unknown", velocity=velocity, confidence="none")


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
