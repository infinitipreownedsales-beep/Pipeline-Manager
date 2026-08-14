"""Service Loaner ECONOMIC Ideal Mix — the governing fleet law.

Ideal Mix is NEVER "we need N vehicles, so find N that qualify". It is the highest-value FEASIBLE fleet
built from the best combination of IN / HOLD / OUT decisions, evaluated alternative-by-alternative on real
economics (the same per-unit incremental values the Phase 6 EconomicService produces). Key rules enforced:

  * A nominal operational fleet target is a CAPACITY objective, not permission to lose money: if only k of
    the target positions are economically defensible, the economic fleet stops at k and the remaining
    (target - k) becomes a FUTURE STOCKING NEED, never a forced bad placement.
  * With the fleet capped at the operational target, a stronger IN candidate DISPLACES a weaker current
    HOLD (OUT + IN rotation at constant fleet size) instead of growing the fleet.
  * A monthly PLACEMENT REQUIREMENT (dealer / OEM objective) is a first-class, temporary override. Any
    placements it forces beyond the economic optimum are labelled OBJECTIVE_DRIVEN and chosen to minimise
    economic sacrifice — they are NOT relabelled as economically ideal, so learning can separate an
    externally-required action from an unconstrained economic preference.
  * Ranking uses total incremental economics (net keep / net placement including retail opportunity cost),
    never youngest / newest / first-seen; duplicate units are counted once.

Pure function: no store, no fabrication. Callers pass real per-unit economics; unknown economics stay out.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UnitEcon:
    id: str
    identity: str = ""
    # HELD units: incremental value of keeping in service vs exiting now.
    keep_value: float = 0.0
    exit_value: float = 0.0
    # IN candidates: incremental value of placing minus the New-Retail opportunity cost of using it.
    in_value: float = 0.0
    opportunity_cost: float = 0.0

    def net_hold(self):
        return round(self.keep_value - self.exit_value, 6)

    def net_in(self):
        return round(self.in_value - self.opportunity_cost, 6)


@dataclass
class MixResult:
    operational_target: int
    economic_fleet_count: int
    recommended_fleet_count: int
    future_stocking_need: int
    decisions: dict = field(default_factory=dict)      # id -> {action, net, objective_driven, reason, identity, swap_out}
    swaps: list = field(default_factory=list)
    objective_driven_ins: list = field(default_factory=list)
    required_placements: int = None
    growth: bool = False
    note: str = ""

    def by_action(self, action):
        return [d for d in self.decisions.values() if d["action"] == action]


def optimize_ideal_mix(held, candidates, *, operational_target, required_placements=None,
                       economic_floor=0.0):
    """`held` / `candidates` are UnitEcon lists. Returns a MixResult of IN / HOLD / OUT / WAIT decisions.

    Economic optimum: fill up to `operational_target` positions with the highest-net positions whose net
    exceeds `economic_floor`, drawn from HOLD (net_hold) and IN (net_in). Held units not selected are OUT;
    the target shortfall is a FUTURE STOCKING NEED. A monthly `required_placements` then forces the best
    remaining candidates as OBJECTIVE_DRIVEN, rotating out the weakest held before growing the fleet."""
    held = list(_dedup(held))
    candidates = list(_dedup(candidates))
    pool = ([("hold", u, u.net_hold()) for u in held] + [("in", u, u.net_in()) for u in candidates])
    # rank by economics only; deterministic tie-break by id, never by age/order
    pool.sort(key=lambda p: (-p[2], p[1].id))

    economic = [p for p in pool if p[2] > economic_floor][:operational_target]
    econ_ids = {p[1].id for p in economic}
    econ_in_count = sum(1 for p in economic if p[0] == "in")

    decisions = {}
    for u in held:
        if u.id in econ_ids:
            decisions[u.id] = _dec("HOLD", u.net_hold(), u, "current loaner is economically superior to exiting")
        else:
            reason = ("exiting improves total economics" if u.net_hold() <= economic_floor
                      else "displaced by an economically stronger placement")
            decisions[u.id] = _dec("OUT", u.net_hold(), u, reason)
    for u in candidates:
        if u.id in econ_ids:
            decisions[u.id] = _dec("IN", u.net_in(), u, "best available economic addition")

    economic_fleet_count = len(economic)
    gap = max(0, operational_target - economic_fleet_count)

    # ---- monthly placement requirement (objective-driven; minimise economic sacrifice) ----
    objective_ins, growth = [], False
    if required_placements is not None and required_placements > econ_in_count:
        extra = required_placements - econ_in_count
        # best remaining candidates by net, even if <= floor; skip those already IN
        remaining = sorted((u for u in candidates if decisions.get(u.id, {}).get("action") != "IN"),
                           key=lambda u: (-u.net_in(), u.id))
        room_at_target = max(0, operational_target - _fleet_size(decisions))
        for i, u in enumerate(remaining[:extra]):
            if room_at_target <= 0:
                # rotate: OUT the weakest current HOLD to keep the fleet at target (not blind growth)
                weakest = _weakest_hold(decisions, held)
                if weakest is not None:
                    decisions[weakest] = _dec("OUT", decisions[weakest]["net"], _find(held, weakest),
                                              "rotated out to place an objective-required unit at constant fleet")
                    decisions[u.id] = _dec("IN", u.net_in(), u, "objective-required placement (rotation)",
                                           objective=True, swap_out=weakest)
                else:
                    decisions[u.id] = _dec("IN", u.net_in(), u, "objective-required placement (fleet growth)",
                                           objective=True)
                    growth = True
            else:
                decisions[u.id] = _dec("IN", u.net_in(), u, "objective-required placement", objective=True)
                room_at_target -= 1
            objective_ins.append(u.id)
        # if the requirement cannot be met from available candidates, the remainder WAITs (capacity need)
        unmet = extra - len(remaining[:extra])
        if unmet > 0:
            growth = growth  # no fabricated unit; the shortfall surfaces as future stocking need below
            gap = max(gap, unmet)

    # ---- swaps: an OUT current unit whose slot an IN candidate took (strongest first) ----
    swaps = _swaps(decisions, held, candidates)

    fleet = _fleet_size(decisions)
    note = ""
    if economic_fleet_count < operational_target:
        note = (f"best economically-defensible fleet is {economic_fleet_count} of a {operational_target} "
                f"target; {gap} position(s) become future stocking need, not a forced placement.")
    if growth:
        note += " Objective-required placements grew the fleet beyond target; normalize by rotation next review."
    return MixResult(operational_target=operational_target, economic_fleet_count=economic_fleet_count,
                     recommended_fleet_count=fleet, future_stocking_need=gap, decisions=decisions,
                     swaps=swaps, objective_driven_ins=objective_ins, required_placements=required_placements,
                     growth=growth, note=note.strip())


# ---- helpers -------------------------------------------------------------------------------------------
def _dec(action, net, unit, reason, *, objective=False, swap_out=None):
    return {"action": action, "net": round(net, 6), "objective_driven": objective, "reason": reason,
            "identity": getattr(unit, "identity", "") or (unit.id if unit else ""),
            "id": unit.id if unit else None, "swap_out": swap_out}


def _dedup(units):
    seen = set()
    for u in units:
        if u.id not in seen:
            seen.add(u.id)
            yield u


def _fleet_size(decisions):
    return sum(1 for d in decisions.values() if d["action"] in ("HOLD", "IN"))


def _weakest_hold(decisions, held):
    holds = [(d["net"], d["id"]) for d in decisions.values() if d["action"] == "HOLD"]
    return min(holds)[1] if holds else None


def _find(units, uid):
    return next((u for u in units if u.id == uid), None)


def _swaps(decisions, held, candidates):
    outs = sorted((d for d in decisions.values() if d["action"] == "OUT"), key=lambda d: d["net"])
    ins = sorted((d for d in decisions.values() if d["action"] == "IN"), key=lambda d: -d["net"])
    swaps = []
    for o, i in zip(outs, ins):
        gain = round(i["net"] - o["net"], 6)
        if gain > 0:
            swaps.append({"out": o["id"], "out_identity": o["identity"], "in": i["id"],
                          "in_identity": i["identity"], "gain": gain,
                          "objective_driven": i["objective_driven"]})
    return swaps
