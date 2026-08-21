"""Live wiring for the per-active-unit KEEP / PULL / SWAP decision.

Gathers each authoritative input from the EXISTING readers — never re-asking the operator for data that
already exists in inventory, Service Loaner, Program Inputs, historical used data, or governed policy — and
hands them to the incremental-from-now comparator (keep_pull_swap.compare_actions). Everything is classified:

  AUTHORITATIVE fact  — invoice (governed / inventory), in-service date, tenure, ICV/Velocity terms
  LEARNED estimate    — expected used sale price now / at the future exit, expected sell-time
  PLANNING assumption — daily-prorated write-down, process buffer, recon when governed-absent (=0, flagged)
  UNRESOLVED input    — anything missing; it GATES only the actions that depend on it, never the whole unit

Front-end gross only (no backend / F&I anywhere). Write-down counts once (embedded in adjusted basis). ICV
already earned is sunk/common; Velocity is contingent on meeting the 240-day deadline.
"""
from __future__ import annotations

import datetime as _dt

from .sl_policy import SLPolicyStore
from .program_inputs import ProgramInputsStore
from .keep_pull_swap import compare_actions
from .sell_time import estimate_sell_time, latest_prudent_release


def _iso_today(clock):
    from ..clock import to_utc_iso
    return to_utc_iso(clock.now())[:10]


def _price_at_model_year_age(mi, age_years):
    """Expected used SELLING PRICE from the dealership's own maturity evidence (median recorded price by
    model-year age at resale). Returns (price, basis_label, confidence). Degrades to the model resale median
    (flat, thin) when the specific maturity bin is thin/absent; None price when there is no defensible
    resale evidence at all (the KEEP/PULL economics that need it are then gated, not fabricated)."""
    if mi is None:
        return None, "no model evidence", "none"
    label = "5+" if age_years is None or age_years >= 5 else str(max(0, int(age_years)))
    for b in getattr(mi, "maturity", ()) or ():
        if b.label == label and b.median_price is not None and not b.thin:
            return float(b.median_price), f"maturity age {label}", "moderate"
    rm = getattr(mi, "resale_model", None)
    if rm is not None and getattr(rm, "gated", False):
        return float(rm.dist.median), "model resale median (maturity age thin)", "thin"
    return None, "no defensible resale evidence", "none"


def build_unit_decision(app, scope, unit, mi, *, today=None, swap_candidate_net=None, keep_horizon_days=None):
    """Assemble the KEEP/PULL/SWAP decision for one active Service-Loaner `unit` (a UnitIntel) whose model
    evidence is `mi` (a ModelIntel). Reads governed policy + Program Inputs; forecasts the future exit price
    from maturity evidence. Returns {action, nets, components, missing, gated, confidence, why, facts}."""
    pol = SLPolicyStore(app.prefs, scope)
    pis = ProgramInputsStore(app.prefs, scope)
    today = today or _iso_today(app.stack.clock)
    vin = unit.vin
    model = (unit.model or "").upper()
    my = getattr(unit, "model_year", "") or ""
    in_service = unit.in_service_date
    tenure_days_now = unit.age_days
    gated = []

    # --- authoritative facts ---
    invoice = pol.invoice_for_vin(vin)
    if invoice is None:
        gated.append("authoritative invoice")
    if not in_service or tenure_days_now is None:
        gated.append("authoritative in-service date / tenure")
    in_month = in_service[:7] if in_service else None
    rate, rate_src = pol.writedown_monthly_rate(in_month)
    icv_e = pis.applicable("icv", model, in_month, model_year=my) if in_month else None
    vel_e = pis.applicable("velocity", model, in_month, model_year=my) if in_month else None
    icv = icv_e.value if icv_e else None
    velocity = vel_e.value if vel_e else None
    total_to_retail = (vel_e.day_cap if (vel_e and vel_e.day_cap is not None) else 240)  # 240 = total-to-retail

    # --- learned estimates ---
    sell = estimate_sell_time(_retail_rows(app, scope), model=model, model_year=my,
                              trim=None, drivetrain=None)
    sell_days = sell["days"] if sell else None
    buffer_days = pol.protection_buffer_days()
    release = latest_prudent_release(in_service_date=in_service, total_to_retail_days=total_to_retail,
                                     expected_sell_time_days=sell_days, process_buffer_days=buffer_days)
    # KEEP horizon: hold to the latest prudent release point (never beyond); 0 when already at/over it
    if keep_horizon_days is None:
        keep_horizon_days = 0
        if release:
            try:
                keep_horizon_days = max(0, (_dt.date.fromisoformat(release["release_by"])
                                            - _dt.date.fromisoformat(today)).days)
            except (ValueError, TypeError):
                keep_horizon_days = 0

    # --- forward exit prices (front-end) from maturity evidence ---
    def _age_years(days_from_in_service):
        if not in_service:
            return None
        try:
            exit_date = _dt.date.fromisoformat(in_service[:10]) + _dt.timedelta(days=int(days_from_in_service))
            return exit_date.year - int(my) if my.isdigit() else None
        except (ValueError, TypeError):
            return None
    price_now, pn_basis, pn_conf = _price_at_model_year_age(mi, _age_years(tenure_days_now or 0))
    price_future, pf_basis, pf_conf = _price_at_model_year_age(
        mi, _age_years((tenure_days_now or 0) + keep_horizon_days + (sell_days or 0)))
    if price_now is None:
        gated.append("expected used price now")
    if price_future is None:
        gated.append("expected future used price (KEEP)")

    # --- Velocity contingency: is the projected FINAL SALE within the 240-day deadline? ---
    def _within_deadline(extra_hold_days):
        if not in_service or sell_days is None or total_to_retail is None:
            return True                                     # unknown -> do not fabricate a forfeit
        return (tenure_days_now or 0) + extra_hold_days + sell_days <= total_to_retail
    vel_now = _within_deadline(0)
    vel_future = _within_deadline(keep_horizon_days)

    recon = 0                                               # governed recon not modelled yet -> 0 (planning), flagged

    res = compare_actions(invoice=invoice, monthly_rate=rate, tenure_days_now=tenure_days_now,
                          keep_extra_days=keep_horizon_days, used_price_now=price_now,
                          used_price_future=price_future, recon=recon, velocity_contingent=velocity or 0,
                          velocity_preserved_now=vel_now, velocity_preserved_future=vel_future,
                          icv_earned=icv or 0, swap_candidate_net=swap_candidate_net)

    action = res["best"] or "UNRESOLVED"
    confidence = _confidence(pn_conf, pf_conf, gated)
    why = _why(action, res, vel_now, vel_future, keep_horizon_days, model, sell, gated)
    facts = {"vin": vin, "model": model, "model_year": my, "in_service": in_service,
             "tenure_days": tenure_days_now, "mileage": (unit.mileage if unit.mileage_available else None),
             "invoice": invoice, "rate": rate, "rate_src": rate_src, "icv": icv, "velocity": velocity,
             "total_to_retail_days": total_to_retail, "sell_time": sell, "release": release,
             "price_now": price_now, "price_now_basis": pn_basis, "price_future": price_future,
             "price_future_basis": pf_basis, "recon": recon}
    return {"action": action, "nets": res["nets"], "components": res["components"],
            "missing": res["missing"], "gated": gated, "confidence": confidence, "why": why, "facts": facts}


def _confidence(pn_conf, pf_conf, gated):
    if gated:
        return "gated"
    order = {"none": 0, "thin": 1, "moderate": 2, "strong": 3}
    return min((pn_conf, pf_conf), key=lambda c: order.get(c, 0))


def _why(action, res, vel_now, vel_future, keep_days, model, sell, gated):
    if action == "UNRESOLVED":
        return ("Cannot recommend an action yet — missing: " + ", ".join(gated) + ". The available facts are "
                "shown; supply the missing authoritative input to resolve.")
    c = res["components"]
    if action == "KEEP":
        base = (f"Keep this {model} in service: holding lowers its basis (more write-down) and the expected "
                f"exit gross improves to ${_n(c['front_end_gross_future'])} vs ${_n(c['front_end_gross_now'])} now")
        if not vel_future and vel_now:
            base += " even though keeping risks the Velocity deadline"
        return base + "."
    if action == "PULL":
        why = f"Pull this {model} now: releasing today yields the better total position (${_n(c['front_end_gross_now'])} front-end gross"
        if vel_now and not vel_future:
            why += "; keeping longer would forfeit Velocity"
        why += ")."
        return why
    if action == "SWAP":
        return (f"Swap: pull this {model} now and place the stronger New-Retail candidate into the slot — the "
                "combined dealership result beats keeping the current unit.")
    return ""


def _n(v):
    return "—" if v is None else f"{v:,.0f}"


def _retail_rows(app, scope):
    try:
        from .preowned_evidence import latest_retail_rows
        rows, _as_of = latest_retail_rows(app.stack.db.conn, scope)
        return rows
    except Exception:   # noqa: BLE001
        return []
