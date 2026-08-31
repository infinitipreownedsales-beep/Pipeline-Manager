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

The prospective HOLD is not a typed/fixed tenure — it is DERIVED from the already-governed release backsolve
(sell_time.latest_prudent_release), exactly as the active-loaner board does. For a NEW add placed today:
prospective in-service = today; final retail deadline = today + total-to-retail (Velocity day_cap, else the
governed 240-day rule); latest prudent release = deadline − learned post-loaner sell time − governed process/
protection buffer; hold_days = today → release_by. The write-down and the expected used transaction value at
release both use THAT derived hold. It fails closed only when a real release-timing input is unresolved (no
sell-time evidence, no protection buffer, no applicable total-to-retail rule) — never by hardwiring a tenure.

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

from .sl_policy import SLPolicyStore, cumulative_writedown
from .program_inputs import ProgramInputsStore
from .sell_time import estimate_sell_time, latest_prudent_release
from .placement import (read_new_retail_units, certified_harm_index, _to_candidate, _authoritative_vin,
                        _eligible, EXCESS, COVERED, SHORTAGE, UNKNOWN)
from .unit_econ import _invoice_of
from .sl_decision import (_market_price, _retail_rows, _inventory_rows, _price_num, _code_norm, _iso_today, _recon_assumption)

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


def _evaluate_unit(app, scope, row, *, pol, pis, today, month, rate, retail_rows, inv, scenario=None, market_cache=None):
    """Run the SETTLED transaction-price economics for placing ONE physical New-Retail surplus `row` into
    Service Loaner today. Returns (AddCandidate, None) when fully evaluable, else (None, missing_field)."""
    vin, vin_ok, serial = _authoritative_vin(row)
    cand = _to_candidate(row, {})           # identity only; state is resolved by the caller via harm index
    model = (cand.model or "").upper()
    model_code = _code_norm(row.get("model_code"))
    unit_msrp = _price_num(row.get("msrp"))
    year = cand.year or ""

    # --- prospective hold DERIVED from the already-governed release backsolve (no separate fixed tenure input) ---
    # For a NEW add placed today: prospective in-service = today; the latest prudent loaner release is
    #   final retail deadline (in-service + total-to-retail) − learned post-loaner sell time − governed buffer,
    # exactly the architecture the active-loaner board uses. hold_days = today → release_by. Fail closed only when
    # one of those governed release-timing inputs is genuinely unresolved (never hardwire a tenure).
    sell = estimate_sell_time(retail_rows, model=model, model_year=year, trim=None, drivetrain=None)
    sell_days = sell["days"] if sell else None
    if sell_days is None:
        return None, "expected post-loaner sell-time evidence (no resale history for this model)"
    buffer_days = pol.protection_buffer_days()
    if buffer_days is None:
        return None, "governed protection / process buffer (days) — set it in Service-Loaner policy"
    vel_e = pis.applicable("velocity", model, month, model_year=year)
    velocity, total_to_retail = _velocity_incentive(vel_e)     # Velocity day_cap, else the governed 240-day rule
    if total_to_retail is None:
        return None, "applicable total-to-retail deadline (Velocity / program rule)"
    rel = latest_prudent_release(in_service_date=today, total_to_retail_days=total_to_retail,
                                 expected_sell_time_days=sell_days, process_buffer_days=buffer_days)
    if not rel:
        return None, "release timing unresolved (total-to-retail / sell-time / buffer)"
    release_by = rel["release_by"]
    try:
        hold_days = max(0, (_dt.date.fromisoformat(release_by) - _dt.date.fromisoformat(today)).days)
    except (ValueError, TypeError):
        return None, "release timing unresolved (cannot place today → release_by on the calendar)"

    # --- authoritative invoice (row allowlist, else per-VIN override) ---
    invoice = _invoice_of(row, (vin if vin_ok else ""), pol)
    if invoice is None:
        return None, "authoritative original invoice"

    # --- adjusted basis = invoice − cumulative write-down (once; 1.25%/mo daily-prorated over the derived hold) ---
    wd_dollars, _wd_expl, _pa = cumulative_writedown(invoice=invoice, monthly_rate=rate, tenure_days=hold_days)
    if wd_dollars is None:
        return None, "governed write-down rate / tenure"
    adjusted_basis = round(float(invoice) - wd_dollars, 2)

    # --- expected used SELLING price at the derived release date, on the settled transaction rail (no MSRP sub) ---
    price, price_basis, _pconf = _market_price(retail_rows, inv, model, year, release_by, unit_msrp, model_code,
                                                    market_cache=market_cache)
    if price is None:
        return None, "expected used transaction value at release (governed model-code cohort)"
    scenario = scenario or {}
    recon_map = scenario.get("recon") if isinstance(scenario.get("recon"), dict) else {}
    recon_override = recon_map.get((model or "").upper()) if isinstance(recon_map, dict) else None
    recon = _recon_assumption(model, recon_override)
    expected_recon = float(recon["expected"])
    front_end_gross = round(float(price) - adjusted_basis - expected_recon, 2)

    # --- ICV: EARNED by placing (incremental here) ---
    icv_e = pis.applicable("icv", model, month, model_year=year)
    if icv_e is None or icv_e.value is None:
        return None, "ICV (program value by model / in-service month)"
    icv = float(icv_e.value)

    # --- Velocity: separate, contingent on the 240-day rule; absent → 0 (settled treatment), flagged. Placing by
    # the prudent release keeps the projected final sale inside the deadline by construction, so it is preserved. ---
    velocity_preserved = (hold_days + sell_days) <= total_to_retail
    velocity_val = float(velocity) if (velocity is not None and velocity_preserved) else 0.0

    # --- total-dealership net of placing THIS specific VIN (EXCESS → retail opportunity cost 0) ---
    retail_opportunity_cost = 0.0
    add_net = round(front_end_gross + velocity_val + icv - retail_opportunity_cost, 2)

    why = (f"Placing this {_ident(cand)} nets ${add_net:,.0f} to the dealership: expected front-end gross "

           f"${front_end_gross:,.0f} at release (used price ${price:,.0f} - adjusted basis ${adjusted_basis:,.0f} "

           f"- expected recon ${expected_recon:,.0f}) + ICV ${icv:,.0f}"
           + (f" + Velocity ${velocity:,.0f}" if velocity_val else "")
           + " with no New-Retail coverage cost (over-stocked combination).")
    retail_impact = ("Over-stocked combination — removing this VIN does NOT create a New-Retail shortage "
                     "(genuine surplus), so the New-Retail opportunity cost is $0.")
    caveats = [f"Recon planning assumption for {model}: low ${recon['low']:,.0f} / expected ${recon['expected']:,.0f} / high ${recon['high']:,.0f}. Break-even recon is ${max(0.0, add_net + expected_recon):,.0f}."]
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
    rate = scenario.get("writedown_rate")
    if rate is None:
        rate, _rsrc = pol.writedown_monthly_rate(month)

    rows = read_new_retail_units(app, scope)
    loaded = bool(rows)
    harm = certified_harm_index(app.stack.db.conn, scope)
    retail_rows = _retail_rows(app, scope)
    inv = _inventory_rows(app, scope)

    market_cache = {}
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
                                     retail_rows=retail_rows, inv=inv, scenario=scenario,
                                     market_cache=market_cache)
        if ac is not None:
            ready.append(ac)
        else:
            vin, vin_ok, serial = _authoritative_vin(r)
            blocked.append(BlockedCandidate(
                stock=cand.stock or "", vin=(vin if vin_ok else ""), vin_authoritative=vin_ok, serial=serial,
                identity=_ident(cand),
                model=(cand.model or "").upper(), new_retail_state=EXCESS, missing=missing))

    ready.sort(key=lambda c: (-c.add_net, c.stock))
    commandable = [c for c in ready if c.add_net > 0]
    return {"loaded": loaded, "requested": n, "ready": ready[:n], "backups": ready[n:n + 4],
            "commandable": commandable[:n],
            "blocked": blocked, "protected": protected, "covered_deferred": covered_deferred,
            "unresolved_state": unresolved_state, "eligible": eligible, "all_ready": ready}
