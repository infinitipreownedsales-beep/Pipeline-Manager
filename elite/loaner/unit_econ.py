"""Live per-unit UnitEcon adapter — the missing WIRE (not a new engine).

It gathers, per Retail-safe (EXCESS surplus) placement candidate, the authoritative economic terms that
already exist —

  * ICV and Velocity: effective-dated Program Inputs resolved for the model / model-year at the planning month;
  * expected used gross: the dealership's own preowned resale evidence (median recorded gross), only when the
    sample is defensible;
  * write-down and protection buffer: the two governed dealership POLICY inputs (SLPolicyStore);
  * Retail opportunity cost: derived from the certified New-Retail coverage state (0 for a genuine surplus /
    EXCESS unit — SHORT combinations are protected out upstream and never reach the economic ranking);

— combines them into a transparent per-unit net, and hands UnitEcon rows to the UNCHANGED certified
`optimize_ideal_mix`. Every term is sourced; any unit missing a required authoritative term is EXCLUDED from
the economic ranking (its economics stay UNKNOWN — never fabricated, never zero) and falls back to the
Retail-harm shortlist. A scenario override is applied only at call time and is NEVER persisted.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ideal_mix import UnitEcon, optimize_ideal_mix
from .placement import EXCESS, certified_harm_index, read_new_retail_units, _to_candidate, _authoritative_vin


@dataclass(frozen=True)
class EconTerm:
    label: str
    value: float | None
    role: str          # "value" | "cost" | "info"
    source: str

    @property
    def present(self):
        return self.value is not None


@dataclass(frozen=True)
class PlacementEcon:
    unit_id: str
    identity: str
    model: str
    stock: str
    in_value: float
    opportunity_cost: float
    terms: tuple

    def net(self):
        return round(self.in_value - self.opportunity_cost, 2)

    def unit_econ(self):
        return UnitEcon(id=self.unit_id, identity=self.identity, in_value=self.in_value,
                        opportunity_cost=self.opportunity_cost)


def compute_placement_econ(*, unit_id, identity, model, stock, icv, velocity, used_gross, writedown, buffer,
                           retail_opportunity_cost=0):
    """Pure per-unit economics. Returns (PlacementEcon | None, missing_labels). A missing required term (ICV /
    Velocity / used gross / write-down / buffer is None) excludes the unit — its economics are UNKNOWN, never
    coerced to zero. An explicit 0 (e.g. a real $0 write-down or gross) is a valid value and is used."""
    terms, missing = [], []

    def term(label, v, role, source):
        terms.append(EconTerm(label, v, role, source))
        if v is None and role != "info":
            missing.append(label)
        return v if v is not None else 0

    icv_v = term("ICV (program value)", icv, "value", "effective-dated ICV")
    vel_v = term("Velocity (program incentive)", velocity, "value", "effective-dated Velocity")
    gross_v = term("Expected used gross", used_gross, "value", "preowned evidence — median recorded gross")
    wd_v = term("Write-down (policy)", writedown, "cost", "governed dealership policy")
    buf_v = term("Protection buffer (policy)", buffer, "cost", "governed dealership policy")
    terms.append(EconTerm("Retail opportunity cost", retail_opportunity_cost, "cost",
                          "certified New-Retail coverage (0 for a surplus unit)"))
    if missing:
        return None, missing
    in_value = icv_v + vel_v + gross_v
    opportunity_cost = wd_v + buf_v + (retail_opportunity_cost or 0)
    return PlacementEcon(unit_id, identity, model, stock, float(in_value), float(opportunity_cost),
                         tuple(terms)), []


def _used_gross_by_model(app, scope):
    out = {}
    try:
        from .intelligence import build_intelligence
        intel = build_intelligence(app.stack.db.conn, scope, app.prefs, app.stack.clock)
        for mi in intel.models:
            g = getattr(mi, "gross_model", None)
            if g is not None and getattr(g, "gated", False):
                out[(mi.model or "").upper()] = getattr(g.dist, "median", None)
    except Exception:   # noqa: BLE001
        pass
    return out


def build_placement_econ(app, scope, planning_month, *, n=0, scenario=None):
    """Live economic placement ranking for up to `n` additions, computed from authoritative inputs and ranked
    by the certified optimize_ideal_mix. `scenario` (e.g. {"writedown": {"QX80": 5000}, "buffer": 400}) is a
    what-if applied ONLY here and never written to policy. Returns a dict with the ranked economic result, the
    excluded units (with reasons), and readiness."""
    from .program_inputs import ProgramInputsStore
    from .sl_policy import SLPolicyStore
    conn = app.stack.db.conn
    pis = ProgramInputsStore(app.prefs, scope)
    pol = SLPolicyStore(app.prefs, scope)
    scenario = scenario or {}
    scen_wd = {(k or "").upper(): v for k, v in (scenario.get("writedown") or {}).items()}
    scen_buf = scenario.get("buffer")

    rows = read_new_retail_units(app, scope)
    loaded = bool(rows)
    harm = certified_harm_index(conn, scope)
    gross_by_model = _used_gross_by_model(app, scope)

    econs, excluded = [], []
    for r in rows:
        c = _to_candidate(r, harm)
        # only Retail-genuine surplus (EXCESS) is economically ranked; SHORT is protected out, COVERED's
        # Retail opportunity cost is not authoritatively valued yet so it stays in the Retail-harm fallback.
        if c.new_retail_state != EXCESS:
            continue
        vin, ok, _serial = _authoritative_vin(r)
        uid = (vin if ok else c.stock) or c.serial or "unit"
        model = (c.model or "").upper()
        ident = " ".join(x for x in (c.year, c.model, c.trim, c.drivetrain) if x).strip() or model
        icv_e = pis.applicable("icv", model, planning_month, model_year=c.year or "")
        vel_e = pis.applicable("velocity", model, planning_month, model_year=c.year or "")
        wd = scen_wd.get(model, pol.writedown(model))
        buf = scen_buf if scen_buf is not None else pol.buffer()
        pe, missing = compute_placement_econ(
            unit_id=uid, identity=ident, model=model, stock=c.stock or "",
            icv=(icv_e.value if icv_e else None), velocity=(vel_e.value if vel_e else None),
            used_gross=gross_by_model.get(model), writedown=wd, buffer=buf, retail_opportunity_cost=0)
        if pe is None:
            excluded.append({"unit_id": uid, "identity": ident, "model": model, "missing": missing})
        else:
            econs.append(pe)

    by_id = {pe.unit_id: pe for pe in econs}
    mix = optimize_ideal_mix([], [pe.unit_econ() for pe in econs], operational_target=max(0, int(n or 0)))
    ranked_ins = sorted((d for d in mix.decisions.values() if d["action"] == "IN"),
                        key=lambda d: (-d["net"], d["identity"]))
    ranked = [{"econ": by_id.get(d["id"]), "net": d["net"], "identity": d["identity"]}
              for d in ranked_ins if by_id.get(d["id"]) is not None]
    # a placement that is economically negative would be a losing move — ideal_mix already excludes it.
    return {"loaded": loaded, "ready": bool(econs) or bool(excluded), "have_economics": bool(econs),
            "ranked": ranked, "all_econ": sorted(econs, key=lambda p: -p.net()), "excluded": excluded,
            "mix": mix}
