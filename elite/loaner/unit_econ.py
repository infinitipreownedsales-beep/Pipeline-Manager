"""Live per-unit UnitEcon adapter — the missing WIRE (not a new engine).

It gathers, per Retail-safe (EXCESS surplus) placement candidate, the authoritative economic terms that
already exist —

  * ICV and Velocity: effective-dated Program Inputs resolved for the model / model-year at the planning month;
  * expected used gross: the dealership's own preowned resale evidence (median recorded gross), only when the
    sample is defensible;
  * write-down: the governed dealership dollar (or percent-of-ICV) policy (SLPolicyStore);
  * Retail opportunity cost: derived from the certified New-Retail coverage state (0 for a genuine surplus /
    EXCESS unit — SHORT combinations are protected out upstream and never reach the economic ranking).

The governed PROTECTION BUFFER is a DAY count (release-timing) and is deliberately NOT part of these dollar
economics — days are never summed with dollars.

— combines them into a transparent per-unit dollar net, and hands UnitEcon rows to the UNCHANGED certified
`optimize_ideal_mix`. Every term is sourced; any unit missing a required authoritative term is EXCLUDED from
the economic ranking (its economics stay UNKNOWN — never fabricated, never zero) and falls back to the
Retail-harm shortlist. A scenario override is applied only at call time and is NEVER persisted.
"""
from __future__ import annotations

from collections import defaultdict
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


def compute_placement_econ(*, unit_id, identity, model, stock, icv, velocity, used_gross, writedown_dollars,
                           writedown_explain="", retail_opportunity_cost=0):
    """Pure per-unit DOLLAR economics. Every term is dollars — the time protection buffer (DAYS) is a
    release-timing input and is deliberately NOT part of this sum. Returns (PlacementEcon | None,
    missing_labels): a missing required term (ICV / Velocity / used gross / write-down is None) excludes the
    unit — economics UNKNOWN, never coerced to zero. An explicit 0 (a real $0 write-down or gross) is valid."""
    terms, missing = [], []

    def term(label, v, role, source):
        terms.append(EconTerm(label, v, role, source))
        if v is None and role != "info":
            missing.append(label)
        return v if v is not None else 0

    icv_v = term("ICV (program value, $)", icv, "value", "effective-dated ICV")
    vel_v = term("Velocity (program incentive, $)", velocity, "value", "effective-dated Velocity")
    gross_v = term("Expected used gross ($)", used_gross, "value", "preowned evidence — median recorded gross")
    wd_v = term("Write-down ($)", writedown_dollars, "cost", writedown_explain or "governed dealership policy")
    terms.append(EconTerm("Retail opportunity cost ($)", retail_opportunity_cost, "cost",
                          "certified New-Retail coverage (0 for a surplus unit)"))
    if missing:
        return None, missing
    in_value = icv_v + vel_v + gross_v
    opportunity_cost = wd_v + (retail_opportunity_cost or 0)
    return PlacementEcon(unit_id, identity, model, stock, float(in_value), float(opportunity_cost),
                         tuple(terms)), []


# Authoritative original-invoice headers on a New-Retail inventory row (governed allowlist; never MSRP/ICV, never
# generic Vehicle Cost). `inv` is the canonical field the governed source contract new_inventory_pipeline_summary
# maps the real DMS "Inv" column onto (ops/contracts.py header_aliases: "Inv" -> "inv"); it is the dealer invoice
# carried on each physical pipeline row, distinct from retail_history.vehicle_cost (which is a separate rail and
# is never read here). Reading it here consumes the authoritative invoice the source ALREADY supplies.
_INVOICE_HEADERS = ("invoice", "invoice_price", "original_invoice", "dealer_invoice", "Invoice", "InvoicePrice",
                    "inv")


def _invoice_of(row, vin, pol):
    """The authoritative original invoice for a unit: from the inventory row (governed allowlist), else a
    governed per-VIN invoice override, else None (write-down then fails closed — never MSRP/ICV/estimate)."""
    from .sl_policy import _to_num
    if isinstance(row, dict):
        for k in _INVOICE_HEADERS:
            v = row.get(k)
            if v not in (None, ""):
                n = _to_num(v)
                if n is not None:
                    return int(round(n))
    return pol.invoice_for_vin(vin) if vin else None


def _used_gross_by_model(app, scope):
    # AUTHORITATIVE PREOWNED PROFIT RULE: expected used gross is FRONT-END only. The recorded gross fed here
    # (retail_history gross_profit) must be the dealership's front-end gross — backend / F&I income is never
    # included and never influences Service-Loaner economics. The KEEP/PULL/SWAP comparator enforces this by
    # construction (price − adjusted basis − recon); this model-level figure relies on the source being front-end.
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
    by the certified optimize_ideal_mix. `scenario` (e.g. {"writedown": {"QX80": {"kind": "amount", "value":
    5000}}}) is a what-if write-down spec applied ONLY here and never written to policy. Returns a dict with
    the ranked economic result, the excluded units (with reasons), and readiness."""
    from .program_inputs import ProgramInputsStore
    from .sl_policy import SLPolicyStore, cumulative_writedown, DAYS_PER_MONTH
    conn = app.stack.db.conn
    pis = ProgramInputsStore(app.prefs, scope)
    pol = SLPolicyStore(app.prefs, scope)
    scenario = scenario or {}
    # projected program tenure (months) — scenario overrides governed default; write-down monthly rate too
    tenure_months = scenario.get("tenure_months")
    if tenure_months is None:
        tenure_months = pol.projected_tenure_months()
    rate = scenario.get("writedown_rate")
    if rate is None:
        rate, _rsrc = pol.writedown_monthly_rate(planning_month)

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
        icv_v = icv_e.value if icv_e else None
        # write-down: invoice (never ICV) × governed monthly rate × projected tenure, daily-prorated; fail closed
        invoice = _invoice_of(r, (vin if ok else ""), pol)
        if tenure_months is None:
            wd_dollars, wd_explain = None, "projected program tenure (months) not set"
        else:
            wd_dollars, wd_explain, _pa = cumulative_writedown(
                invoice=invoice, monthly_rate=rate, tenure_days=float(tenure_months) * DAYS_PER_MONTH)
        pe, missing = compute_placement_econ(
            unit_id=uid, identity=ident, model=model, stock=c.stock or "",
            icv=icv_v, velocity=(vel_e.value if vel_e else None),
            used_gross=gross_by_model.get(model), writedown_dollars=wd_dollars, writedown_explain=wd_explain,
            retail_opportunity_cost=0)
        if pe is None:
            if wd_dollars is None:
                missing = [m for m in missing if m != "Write-down ($)"] + [f"Write-down ({wd_explain})"]
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


@dataclass(frozen=True)
class ModelSourcing:
    """How a model-level Service-Loaner requirement is met: place K from existing Retail surplus (economically
    defensible), order the remainder specifically for Service Loaner. Never invents Covered-unit economics;
    when economics for the model are unavailable the split is UNRESOLVED (never fabricated)."""
    model: str
    requested: int
    placed: tuple            # PlacementEcon placed from existing EXCESS surplus (net > 0), best-first
    order_count: int         # remaining need -> ORDER specifically for Service Loaner (future acquisition)
    unresolved: bool         # economics could not be assessed for this model, so place-vs-order is unknown

    @property
    def place_count(self):
        return len(self.placed)


def sourcing_plan(app, scope, planning_month, need_by_model, *, scenario=None):
    """Decompose a model-level Service-Loaner requirement into PLACE-from-surplus vs ORDER-specifically.

    For each model, the economically-positive EXCESS units are placed first (best net first, up to the need);
    any shortfall is a future acquisition that must be ORDERED specifically for Service Loaner. A physical unit
    is used once. Covered/Short units are never economically fabricated — the unmet need is sourced through
    ordering instead. When the model's economics are not yet available, the split is UNRESOLVED and the whole
    requirement is reported as order-pending (never silently under- or over-ordered)."""
    econ = build_placement_econ(app, scope, planning_month, n=0, scenario=scenario)
    ready = econ["have_economics"]
    pos_by_model = defaultdict(list)
    for pe in econ["all_econ"]:
        if pe.net() > 0:                       # only economically defensible surplus placements
            pos_by_model[pe.model].append(pe)
    for m in pos_by_model:
        pos_by_model[m].sort(key=lambda p: -p.net())
    out = {}
    for model, need in need_by_model.items():
        m = (model or "").upper()
        need = max(0, int(need or 0))
        if not ready:
            # economics cannot assess place-vs-order at all -> conservative: order the full requirement, and say
            # so (never fabricate a split, never under-order and leave Retail exposed).
            out[m] = ModelSourcing(m, need, (), need, True)
            continue
        avail = pos_by_model.get(m, [])
        place = tuple(avail[:need])
        order = max(0, need - len(place))
        out[m] = ModelSourcing(m, need, place, order, False)
    return {"by_model": out, "econ": econ}
