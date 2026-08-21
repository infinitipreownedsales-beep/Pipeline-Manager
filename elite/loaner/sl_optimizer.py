"""Sequential Service-Loaner placement portfolio optimizer.

Placement is NOT "sort all candidates once and take the top N". Pulling a physical unit into Service Loaner
changes Retail coverage for that unit's combination, which changes whether the NEXT pull is safe. So this
optimizer is sequential: pick the best dealership-level placement, apply it to a DISPOSABLE planning copy of
the certified coverage, recompute, then choose the next — until the requirement is met or no
economically/operationally safe candidate remains.

Architectural boundary (reported, not crossed):
  * `ideal_mix.py` is the certified single-shot economic-optimum allocator (rank by net, fill to target). It
    does NOT recompute Retail coverage between placements, so it is the wrong LAYER for sequential
    coverage-aware placement. It is left UNTOUCHED.
  * This module is the dedicated Service-Loaner placement layer. It consumes the same per-unit economics
    (`unit_econ.compute_placement_econ`) and the certified coverage index, and never mutates certified state
    (the planning copy is disposable and in-memory).

Economic certification gate (Stage 1B finding): NO authoritative dealership write-down cumulative treatment
exists in the repo/specs/legacy artifacts. The monthly-rate × ICV × tenure figure is PROVISIONAL, so no
placement can be labelled ECONOMICALLY_RECOMMENDED (certified) yet — the best reachable outcome is
OPERATIONALLY_SAFE_ECON_INCOMPLETE, with the net shown as provisional. Flat-dollar one-time is likewise
unproven and provisional.
"""
from __future__ import annotations

from dataclasses import dataclass

from .placement import (EXCESS, COVERED, SHORTAGE, UNKNOWN, certified_harm_index, read_new_retail_units,
                        _to_candidate, _eligible, _first)
from ..newinv.dms_identity import dms_planning_identity
from .unit_econ import compute_placement_econ

# The dealership write-down cumulative treatment is not yet governed; until it is, economic recommendations
# stay provisional and the certified "ECONOMICALLY_RECOMMENDED" outcome is unreachable. Flip only when a
# governed, source-cited treatment exists.
WRITEDOWN_TREATMENT_CERTIFIED = False

ECON_RECOMMENDED = "ECONOMICALLY_RECOMMENDED"                 # certified economics support the placement
OPS_SAFE = "OPERATIONALLY_SAFE_ECON_INCOMPLETE"              # Retail-safe; economics provisional/incomplete
DO_NOT_PLACE = "DO_NOT_PLACE"                                # would create unacceptable Retail/fleet harm
UNRESOLVED = "UNRESOLVED"                                    # critical evidence missing (coverage unknown)


@dataclass(frozen=True)
class PlacementStep:
    rank: int
    unit_id: str
    stock: str
    vin: str
    vin_authoritative: bool
    identity: str
    model: str
    model_year: str
    outcome: str
    provisional: bool          # economics are provisional (write-down governance-required)
    net: float | None          # provisional dealership net, when computable
    econ_terms: tuple          # per-term breakdown for Proof (empty when economics not computable)
    retail_after: str          # certified Retail coverage state of the combo AFTER this placement
    why: str


def _combo_of(row):
    # mirror _to_candidate's combo derivation exactly so the planning-copy key matches the harm index
    return dms_planning_identity({"model_code": _first(row, "model_code"),
                                  "exterior": _first(row, "exterior", "exterior_code", "ext"),
                                  "interior": _first(row, "interior", "interior_code", "int")})


def _gross_by_model(app, scope):
    from .unit_econ import _used_gross_by_model
    return _used_gross_by_model(app, scope)


def optimize_sl_placement(app, scope, planning_month, n, *, loaner_vins=frozenset(), scenario=None):
    """Sequentially choose up to `n` Service-Loaner placements from eligible on-lot Retail units, recomputing
    certified Retail coverage on a disposable planning copy after each pick. Returns steps (placed, best-first),
    rejected units (DO NOT PLACE / UNRESOLVED), the remaining unmet requirement, and whether the sequential
    result diverges from a naive static top-N."""
    from .program_inputs import ProgramInputsStore
    from .sl_policy import SLPolicyStore
    conn = app.stack.db.conn
    pis = ProgramInputsStore(app.prefs, scope)
    pol = SLPolicyStore(app.prefs, scope)
    scenario = scenario or {}
    scen_wd = {(k or "").upper(): v for k, v in (scenario.get("writedown") or {}).items()}
    tenure = scenario.get("tenure_months")
    if tenure is None:
        tenure = pol.projected_tenure_months()
    gross_by_model = _gross_by_model(app, scope)

    rows = read_new_retail_units(app, scope)
    loaded = bool(rows)
    harm = certified_harm_index(conn, scope)
    # disposable planning copy of per-combo remaining EXCESS surplus (never touches certified state)
    remaining_excess = {k: int(v.get("excess", 0) or 0) for k, v in harm.items()}

    # build the eligible physical candidates once, tagged with their combo + economics
    pool = []
    for r in rows:
        if not (isinstance(r, dict) and _eligible(r, set(loaner_vins))):
            continue
        c = _to_candidate(r, harm)
        combo = _combo_of(r)
        model = (c.model or "").upper()
        icv_e = pis.applicable("icv", model, planning_month, model_year=c.year or "")
        vel_e = pis.applicable("velocity", model, planning_month, model_year=c.year or "")
        icv_v = icv_e.value if icv_e else None
        wd_dollars, wd_expl = pol.resolve_writedown_dollars(model, icv=icv_v, spec=scen_wd.get(model),
                                                            tenure_months=tenure)
        pe, _missing = compute_placement_econ(
            unit_id=(c.vin if c.vin_authoritative else c.stock) or c.serial or "unit",
            identity=" ".join(x for x in (c.year, c.model, c.trim, c.drivetrain) if x).strip() or model,
            model=model, stock=c.stock or "", icv=icv_v, velocity=(vel_e.value if vel_e else None),
            used_gross=gross_by_model.get(model), writedown_dollars=wd_dollars, writedown_explain=wd_expl,
            retail_opportunity_cost=0)
        pool.append({"c": c, "combo": combo, "econ": pe})

    def _net(item):
        return item["econ"].net() if item["econ"] is not None else None

    steps, rejected, placed_ids = [], [], set()
    for rank in range(1, max(0, int(n or 0)) + 1):
        # eligible-now = not yet placed AND its combo still has surplus to give without harming Retail
        avail = [it for it in pool if id(it) not in placed_ids
                 and remaining_excess.get(it["combo"], 0) > 0]
        if not avail:
            break
        # rank by: economics-known first (net desc), then oldest-aging-first — provisional net, honest tie-break
        avail.sort(key=lambda it: (0 if _net(it) is not None else 1, -(_net(it) or 0), -(it["c"].dis or 0)))
        pick = avail[0]
        c, combo, pe = pick["c"], pick["combo"], pick["econ"]
        placed_ids.add(id(pick))
        remaining_excess[combo] = remaining_excess.get(combo, 0) - 1
        retail_after = EXCESS if remaining_excess[combo] > 0 else COVERED
        provisional = True                              # write-down treatment governance-required
        outcome = OPS_SAFE if pe is not None else OPS_SAFE   # safe either way; economics may be incomplete
        if pe is None:
            why = (f"Operationally safe to place — {c.model} surplus protects Retail coverage. Economic "
                   "certification pending (missing authoritative economic inputs).")
        else:
            why = (f"Operationally safe — placing this {c.model} leaves Retail coverage {retail_after.lower()}. "
                   f"Provisional dealership net ${pe.net():,.0f} (write-down treatment governance-required, so "
                   "not yet an economic certification).")
        steps.append(PlacementStep(
            rank=rank, unit_id=pe.unit_id if pe else (c.stock or c.vin or "unit"), stock=c.stock or "",
            vin=c.vin or "", vin_authoritative=c.vin_authoritative,
            identity=(pe.identity if pe else " ".join(x for x in (c.year, c.model, c.trim) if x)),
            model=(c.model or "").upper(), model_year=c.year or "", outcome=outcome, provisional=provisional,
            net=(pe.net() if pe else None), econ_terms=(pe.terms if pe else ()),
            retail_after=retail_after, why=why))

    # units we could NOT safely place (surplus exhausted -> would create shortage) or coverage unknown
    for it in pool:
        if id(it) in placed_ids:
            continue
        c = it["c"]
        if c.new_retail_state == UNKNOWN:
            rejected.append({"identity": " ".join(x for x in (c.year, c.model, c.trim) if x), "stock": c.stock,
                             "model": (c.model or "").upper(), "outcome": UNRESOLVED,
                             "why": "New-Retail coverage is unresolved for this combination (no issued plan)."})
        elif c.new_retail_state == SHORTAGE or remaining_excess.get(it["combo"], 0) <= 0:
            rejected.append({"identity": " ".join(x for x in (c.year, c.model, c.trim) if x), "stock": c.stock,
                             "model": (c.model or "").upper(), "outcome": DO_NOT_PLACE,
                             "why": "Placing this would reduce New-Retail coverage below plan — protected."})

    requested = max(0, int(n or 0))
    placed = len(steps)
    # would a naive static top-N (ignore sequential coverage recompute) have offered MORE from exhausted combos?
    static_safe = sum(1 for it in pool if it["c"].new_retail_state in (EXCESS, COVERED))
    diverged = (min(requested, static_safe) > placed)
    return {"loaded": loaded, "requested": requested, "placed": placed,
            "remaining_to_order": max(0, requested - placed), "steps": steps, "rejected": rejected,
            "sequential_diverges_from_static": diverged,
            "economics_certifiable": WRITEDOWN_TREATMENT_CERTIFIED}
