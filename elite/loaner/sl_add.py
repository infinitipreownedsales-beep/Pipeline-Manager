"""BEST UNITS TO ADD TO SERVICE LOANER NOW — the operator's real "which physical VINs do I place" answer.

This is NOT a new economic model. It runs the SETTLED transaction-price economics (the same rail that drives
KEEP/PULL/SWAP in sl_decision.build_unit_decision) over each physical New-Retail SURPLUS unit, framed as a
placement decision: place this specific vehicle into Service Loaner today instead of leaving it New Retail.

Per candidate the total-dealership result of placing it is, incrementally:

    add_net = expected_front_end_gross_at_release            (used SELLING price at release − adjusted basis − recon)
            + Velocity                                       (only if the projected final sale still beats the 240-day rule)
            + ICV                                            (a program value EARNED by placing — incremental here, not sunk)
            − New-Retail opportunity cost                    (0 for a genuine EXCESS surplus unit)

    adjusted_basis = original authoritative INVOICE − cumulative Service-Loaner write-down (1.25%/mo, daily-prorated)

Write-down is counted ONCE (inside the adjusted basis, never also as a separate cost); ICV and Velocity are
separate program benefits added once each; MSRP is never substituted for the transaction rail (it appears only
inside the settled _market_price SECONDARY normalizer). Every required term is authoritative or the unit is
BLOCKED with the exact missing field — never fabricated to reach a target count.

Retail safety is the certified coverage state (placement.certified_harm_index): only EXCESS surplus is offered
(removing it creates no New-Retail shortage → opportunity cost 0); SHORTAGE units are protected out; COVERED /
UNKNOWN units are deferred because their New-Retail opportunity cost is not yet authoritatively valued — never
guessed into the ranking.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from .sl_policy import SLPolicyStore, cumulative_writedown, DAYS_PER_MONTH
from .program_inputs import ProgramInputsStore
from .sell_time import estimate_sell_time
from .placement import (read_new_retail_units, certified_harm_index, _to_candidate, _authoritative_vin,
                        _eligible, EXCESS, COVERED, SHORTAGE, UNKNOWN)
from .unit_econ import _invoice_of
from .sl_decision import (_market_price, _retail_rows, _inventory_rows, _price_num, _code_norm, _my_int,
                          _iso_today)

DEFAULT_ADD_TARGET = 4          # operator default; adjustable at call time without any code change
TOTAL_TO_RETAIL_DEFAULT = 240   # days from in-service to final retail (the Velocity deadline)


@dataclass(frozen=True)
class AddCandidate:
    # --- physical identity (preserved verbatim; never invented) ---
    stock: str
    vin: str
    vin_authoritative: bool
    serial: str
    year: str
    model: str
    model_code: str
    trim: str
    drivetrain: str
    exterior: str
    interior: str
    msrp: float | None
    inventory_age_days: int | None
    new_retail_state: str
    # --- settled economics (dollars) ---
    invoice: int
    write_down: int
    adjusted_basis: float
    expected_used_price: float
    price_basis: str
    front_end_gross: float
    icv: float
    velocity: float
    velocity_preserved: bool
    retail_opportunity_cost: float
    add_net: float
    # --- expected release timing ---
    hold_days: int
    release_by: str
    expected_sell_days: float | None
    # --- narrative ---
    why: str
    retail_impact: str
    caveat: str

    def describe(self):
        return " ".join(x for x in (self.year, self.model, self.trim, self.drivetrain) if x).strip() or self.model


@dataclass(frozen=True)
class BlockedCandidate:
    stock: str
    vin: str
    vin_authoritative: bool
    serial: str
    identity: str
    model: str
    new_retail_state: str
    missing: str            # the exact authoritative field/source preventing the decision


def _num(v):
    return "—" if v is None else f"${v:,.0f}"


def _ident(cand):
    """Human vehicle identity from a placement candidate (governed year/model/trim/drivetrain)."""
    return " ".join(x for x in (cand.year, cand.model, cand.trim, cand.drivetrain) if x).strip() or (cand.model or "")


def _velocity_incentive(vel_e):
    """(value, total_to_retail_days) from an effective-dated Velocity entry, or (None, default deadline)."""
    if vel_e is None:
        return None, TOTAL_TO_RETAIL_DEFAULT
    cap = vel_e.day_cap if getattr(vel_e, "day_cap", None) is not None else TOTAL_TO_RETAIL_DEFAULT
    return vel_e.value, cap


def _evaluate_unit(app, scope, row, *, pol, pis, today, month, rate, tenure_months, retail_rows, inv):
    """Run the SETTLED transaction-price economics for placing ONE physical New-Retail surplus `row` into
    Service Loaner today. Returns (AddCandidate, None) when fully evaluable, else (None, missing_field)."""
    vin, vin_ok, serial = _authoritative_vin(row)
    cand = _to_candidate(row, {})           # identity only; state is resolved by the caller via harm index
    model = (cand.model or "").upper()
    model_code = _code_norm(row.get("model_code"))
    unit_msrp = _price_num(row.get("msrp"))
    year = cand.year or ""

    # --- projected expected hold (governed program tenure) ---
    if tenure_months is None:
        return None, "projected program tenure (months) — set it in Service-Loaner policy"
    hold_days = int(round(float(tenure_months) * DAYS_PER_MONTH))

    # --- authoritative invoice (row allowlist, else per-VIN override) ---
    invoice = _invoice_of(row, (vin if vin_ok else ""), pol)
    if invoice is None:
        return None, "authoritative original invoice"

    # --- adjusted basis = invoice − cumulative write-down (once; 1.25%/mo daily-prorated) ---
    wd_dollars, _wd_expl, _pa = cumulative_writedown(invoice=invoice, monthly_rate=rate, tenure_days=hold_days)
    if wd_dollars is None:
        return None, "governed write-down rate / tenure"
    adjusted_basis = round(float(invoice) - wd_dollars, 2)

    # --- expected used SELLING price at the release date, on the settled transaction rail (no MSRP substitution) ---
    try:
        release_by = (_dt.date.fromisoformat(today) + _dt.timedelta(days=hold_days)).isoformat()
    except (ValueError, TypeError):
        release_by = today
    price, price_basis, _pconf = _market_price(retail_rows, inv, model, year, release_by, unit_msrp, model_code)
    if price is None:
        return None, "expected used transaction value at release (governed model-code cohort)"
    front_end_gross = round(float(price) - adjusted_basis, 2)   # recon governed-absent = 0 (planning)

    # --- ICV: EARNED by placing (incremental here) ---
    icv_e = pis.applicable("icv", model, month, model_year=year)
    if icv_e is None or icv_e.value is None:
        return None, "ICV (program value by model / in-service month)"
    icv = float(icv_e.value)

    # --- Velocity: separate, contingent on the 240-day rule; absent → 0 (settled treatment), flagged ---
    vel_e = pis.applicable("velocity", model, month, model_year=year)
    velocity, total_to_retail = _velocity_incentive(vel_e)
    sell = estimate_sell_time(retail_rows, model=model, model_year=year, trim=None, drivetrain=None)
    sell_days = sell["days"] if sell else None
    # preserved when the projected FINAL sale (hold + sell time) still lands inside the deadline; unknown → do
    # not fabricate a forfeit (matches sl_decision._within_deadline)
    velocity_preserved = True
    if sell_days is not None and total_to_retail is not None:
        velocity_preserved = (hold_days + sell_days) <= total_to_retail
    velocity_val = float(velocity) if (velocity is not None and velocity_preserved) else 0.0

    # --- total-dealership net of placing THIS specific VIN (EXCESS → retail opportunity cost 0) ---
    retail_opportunity_cost = 0.0
    add_net = round(front_end_gross + velocity_val + icv - retail_opportunity_cost, 2)

    why = (f"Placing this {_ident(cand)} nets ${add_net:,.0f} to the dealership: expected front-end gross "
           f"${front_end_gross:,.0f} at release (used price ${price:,.0f} − adjusted basis ${adjusted_basis:,.0f}) "
           f"+ ICV ${icv:,.0f}"
           + (f" + Velocity ${velocity:,.0f}" if velocity_val else "")
           + " with no New-Retail coverage cost (over-stocked combination).")
    retail_impact = ("Over-stocked combination — removing this VIN does NOT create a New-Retail shortage "
                     "(genuine surplus), so the New-Retail opportunity cost is $0.")
    caveats = []
    if velocity is not None and not velocity_preserved:
        caveats.append("Velocity is forfeited at this projected hold (final sale would exceed the 240-day deadline)"
                       " — counted as $0.")
    elif velocity is None:
        caveats.append("No Velocity incentive is configured for this model/month — counted as $0 (not fabricated).")
    if sell is not None and sell.get("confidence") == "thin":
        caveats.append("Expected sell-time evidence is thin.")
    caveat = " ".join(caveats)

    return AddCandidate(
        stock=cand.stock or "", vin=(vin if vin_ok else ""), vin_authoritative=vin_ok, serial=serial,
        year=year, model=model, model_code=model_code or "", trim=cand.trim or "", drivetrain=cand.drivetrain or "",
        exterior=cand.exterior or "", interior=cand.interior or "", msrp=unit_msrp,
        inventory_age_days=cand.dis, new_retail_state=EXCESS,
        invoice=int(invoice), write_down=int(wd_dollars), adjusted_basis=adjusted_basis,
        expected_used_price=round(float(price), 2), price_basis=price_basis, front_end_gross=front_end_gross,
        icv=icv, velocity=(float(velocity) if velocity is not None else 0.0), velocity_preserved=velocity_preserved,
        retail_opportunity_cost=retail_opportunity_cost, add_net=add_net,
        hold_days=hold_days, release_by=release_by, expected_sell_days=sell_days,
        why=why, retail_impact=retail_impact, caveat=caveat), None


def rank_add_candidates(app, scope, *, n=None, today=None, committed_vins=frozenset(), scenario=None):
    """Rank the physical New-Retail SURPLUS VINs to ADD to Service Loaner now, by total-dealership net on the
    settled transaction-price economics. `n` is the operator quantity (default 4, adjustable). Fail-closed:
    a physical surplus unit missing any authoritative term is BLOCKED (with the exact field), never guessed
    into the ranking.

    Returns {loaded, requested, ready, backups, blocked, protected, covered_deferred, unresolved_state, eligible}.
    """
    n = DEFAULT_ADD_TARGET if not n else max(1, min(20, int(n)))
    today = today or _iso_today(app.stack.clock)
    month = today[:7]
    scenario = scenario or {}
    pol = SLPolicyStore(app.prefs, scope)
    pis = ProgramInputsStore(app.prefs, scope)
    tenure_months = scenario.get("tenure_months")
    if tenure_months is None:
        tenure_months = pol.projected_tenure_months()
    rate = scenario.get("writedown_rate")
    if rate is None:
        rate, _rsrc = pol.writedown_monthly_rate(month)

    rows = read_new_retail_units(app, scope)
    loaded = bool(rows)
    harm = certified_harm_index(app.stack.db.conn, scope)
    retail_rows = _retail_rows(app, scope)
    inv = _inventory_rows(app, scope)

    ready, blocked = [], []
    protected = covered_deferred = unresolved_state = eligible = 0
    committed = set(committed_vins or ())
    for r in rows:
        if not _eligible(r, committed):        # physically on-lot, not sold, not already committed
            continue
        eligible += 1
        cand = _to_candidate(r, harm)
        state = cand.new_retail_state
        if state == SHORTAGE:
            protected += 1
            continue
        if state == COVERED:
            covered_deferred += 1
            continue
        if state == UNKNOWN:
            unresolved_state += 1
            continue
        # EXCESS surplus only from here — retail-safe, opportunity cost 0
        ac, missing = _evaluate_unit(app, scope, r, pol=pol, pis=pis, today=today, month=month, rate=rate,
                                     tenure_months=tenure_months, retail_rows=retail_rows, inv=inv)
        if ac is not None:
            ready.append(ac)
        else:
            vin, vin_ok, serial = _authoritative_vin(r)
            blocked.append(BlockedCandidate(
                stock=cand.stock or "", vin=(vin if vin_ok else ""), vin_authoritative=vin_ok, serial=serial,
                identity=_ident(cand),
                model=(cand.model or "").upper(), new_retail_state=EXCESS, missing=missing))

    ready.sort(key=lambda c: (-c.add_net, c.stock))
    return {"loaded": loaded, "requested": n, "ready": ready[:n], "backups": ready[n:n + 4],
            "blocked": blocked, "protected": protected, "covered_deferred": covered_deferred,
            "unresolved_state": unresolved_state, "eligible": eligible, "all_ready": ready}
