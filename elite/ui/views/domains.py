"""Domain operator workspaces — New Inventory, Production & Supply, Service Loaner, Executive Demo.

Every number is READ from the authoritative Phase 4-7 records; the interface never recomputes Demand,
Need, Economic Call, or Best Overall. Proposal vs committed, membership vs rental, official vs Scenario,
and Economic Call vs Execution Status are visually distinct. One physical unit is never counted twice
(the stored count-once results are shown as-is).
"""
from __future__ import annotations
import time

import json
import secrets

from ..render import (badge, esc, esc_text, empty, page, safe, table, kv, form, bars, dist_row,
                      workspace_header, metric, stat_row, chip, disclosure, rec_card)
from ..http import Response


# The one approved zero-mile-rented question — shown verbatim.
ZERO_MILE_QUESTION = "Where is this customer's vehicle, and let's check the miles on the loaner?"


def _conn(app):
    return app.stack.db.conn


def _loaner_store(app):
    """A LoanerStore + DatingService over the live connection — the governed path to resolve an
    authoritative in-service date / mileage when the fleet upload did not carry it."""
    from ...loaner.store import LoanerStore
    from ...loaner.dating import DatingService
    store = LoanerStore(_conn(app), app.stack.clock)
    return store, DatingService(store, app.stack.clock)


def _dating_form(s, u, blocked):
    """Governed manual entry for a unit's authoritative in-service date + last checkout mileage. This is the
    fallback when the fleet upload did not supply them — it is an authoritative operator entry (verified),
    never a guess, and it never substitutes an import/observation date."""
    head = ('Resolve authoritative in-service date / mileage' if blocked
            else 'Correct authoritative in-service date / mileage')
    note = ('This unit is blocked: lifecycle timing needs an authoritative in-service date and latest mileage. '
            'Enter them only from a verified source (never an estimate).' if blocked
            else 'Record a verified correction. Prior values are preserved (history is kept).')
    fields = (f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
              '<label>Authoritative in-service date (verified source only)</label>'
              f'<input type=date name=in_service_date value="{esc(u.in_service_date or "")}" style="max-width:200px">'
              '<label>Last checkout mileage (whole miles; leave blank if unknown — never guessed)</label>'
              '<input type=number name=last_checkout_mileage min=0 style="max-width:160px" '
              f'value="{esc(str(u.mileage) if u.mileage_available and u.mileage is not None else "")}">')
    return (f'<div class="card"><h3>{head}</h3><p class="muted" style="font-size:13px">{note}</p>'
            f'<form method="post" action="/service-loaner/unit/{esc(u.id)}/dating">{fields}'
            '<div style="margin-top:8px"><button type=submit>Record authoritative values</button></div></form></div>')


def _readable(canonical):
    """Render a planning identity 'dms_planning|model=QX65|model_code=8501|exterior=QBE|interior=G' as
    'QX65 8501 QBE/G'. Falls back to the raw string for any other identity form."""
    if not isinstance(canonical, str) or not canonical.startswith("dms_planning|"):
        return canonical
    kv_ = dict(p.split("=", 1) for p in canonical.split("|")[1:] if "=" in p)
    model = kv_.get("model", "").strip()
    code = kv_.get("model_code", "").strip()
    ext, inte = kv_.get("exterior", "").strip(), kv_.get("interior", "").strip()
    return f"{model} {code} {ext}/{inte}".strip()


def _identity_kv(canonical):
    """Parse a 'dms_planning|model=..|model_code=..|exterior=..|interior=..' identity into a dict; {} otherwise."""
    if not isinstance(canonical, str) or not canonical.startswith("dms_planning|"):
        return {}
    return dict(p.split("=", 1) for p in canonical.split("|")[1:] if "=" in p)


def _source_descriptions(app, scope):
    """Read-only lookup {(model, model_code, ext, int): DMS Description} from the latest inventory snapshot. The
    Description ("QX80 LUXE 2WD") is the authoritative human trim/drivetrain for a physical VIN (item 6/22).
    Read-only — never writes to the permanent DB; returns {} when no snapshot is loaded."""
    try:
        from ...loaner.placement import read_new_retail_units
        from ...newinv.dms_identity import dms_planning_key
        out = {}
        for r in read_new_retail_units(app, scope) or []:
            k = dms_planning_key(r)
            desc = (r.get("description") or r.get("Description") or r.get("desc") or "").strip()
            if k and desc:
                out.setdefault(k, desc)
        return out
    except Exception:   # noqa: BLE001 — inventory availability must never break a page
        return {}


def _describe(app, scope, canonical, *, descriptions=None):
    """Governed Described (operator-intelligence vehicle-description standard) for a planning identity, reusing
    the Translation & Identity store — the single governed source of human vehicle language (item 2/3). When a
    `descriptions` map is supplied, the physical VIN's DMS Description supplies human trim/drivetrain (agreement-
    checked, model number stays king). Returns None for a non-planning identity so callers fall back to codes."""
    kv_ = _identity_kv(canonical)
    if not kv_:
        return None
    from ...identity.translation import TranslationStore
    from ...operatorstd import description as _D
    src_desc = ""
    if descriptions:
        key = (kv_.get("model", ""), kv_.get("model_code", ""), kv_.get("exterior", ""), kv_.get("interior", ""))
        src_desc = descriptions.get(key, "")
    return _D.describe(TranslationStore(app.prefs, scope), model=kv_.get("model", ""),
                       model_code=kv_.get("model_code", ""), exterior_code=kv_.get("exterior", ""),
                       interior_code=kv_.get("interior", ""), source_description=src_desc)


def _readable_h(app, scope, canonical, *, dealer=False, descriptions=None):
    """Human vehicle language that ADDS governed names to codes ("QX80 LUXE 2WD — Radiant White (QBE) /
    Graphite (G)"), preserving codes. Degrades gracefully: when the governed store has nothing to add for this
    identity, it returns the compact code form (_readable) so an un-imported store never renders worse. With
    dealer=True the names lead and internal codes are dropped entirely (item 12). `descriptions` (optional) lets
    the physical VIN's DMS Description supply human trim/drivetrain."""
    d = _describe(app, scope, canonical, descriptions=descriptions)
    if d is None:
        return _readable(canonical)
    has_names = bool(d.exterior_name or d.interior_name or d.trim or d.drivetrain)
    if not has_names:
        return _readable(canonical)          # nothing governed to add — keep the compact code form (no regression)
    return d.dealer if dealer else d.operator


# --- Service Loaner Intelligence Layer (A + B) rendering (read-only; economics stay Undetermined) --------
def _q_tone(label):
    return {"Strong": "done", "Moderate": "need", "Thin": "skip"}.get(label, "skip")


def _cohort_line(c, unit=""):
    """One recorded-distribution line with cohort / n / as-of / recency exposed (never a timeless number)."""
    if c is None or c.n == 0:
        return '<p class="muted">No usable sample.</p>'
    d = c.dist
    body = dist_row(c.label, d, scale_max=float(d.maximum or 1), unit=unit)
    gate = "" if c.gated else f' <span class="chip skip">Thin — n {c.n} &lt; gate {c.gate}</span>'
    meta = (f'<div class="muted" style="font-size:12px">cohort: {esc(c.label)} · n={c.n} · as-of {esc(c.as_of or "—")} '
            f'· observations {esc(c.earliest or "?")}–{esc(c.latest or "?")} · {c.recent_n} recent{gate}</div>')
    return body + meta


def _model_intel_card(mi):
    from ...loaner.intelligence import RESALE_MIN_N
    q = mi.quality
    qchip = chip(_q_tone(q.label), f"Evidence: {q.label}") if q else ""
    dts = (dist_row(f"{mi.model} · days to sell", mi.dts, scale_max=float(mi.dts.maximum or 1), unit=" days")
           if mi.dts and mi.dts.count else '<p class="muted">No usable turn sample.</p>')
    headline = next((c for c in mi.resale_years if c.gated), mi.resale_model)
    resale = _cohort_line(headline)
    gross = _cohort_line(mi.gross_model)
    if mi.maturity:
        mat = bars([(f"MY age {b.label}" + (" (thin)" if b.thin else ""), (b.median_price or 0),
                     f"${b.median_price:,.0f} · n={b.n}" if b.median_price is not None else f"n={b.n}")
                    for b in mi.maturity], caption="median recorded price by model-year age at resale")
        if mi.maturity_excluded:
            mat += (f'<p class="muted" style="font-size:12px">{mi.maturity_excluded} observation(s) excluded '
                    '(invalid/missing model-year maturity).</p>')
    else:
        mat = '<p class="muted">Not enough observations to show model-year maturity.</p>'
    proof = kv([("Recorded resale (headline cohort)", headline.label if headline else "—"),
                ("Resale n / gate", f"{headline.n} / {RESALE_MIN_N}" if headline else f"— / {RESALE_MIN_N}"),
                ("Recorded gross cohort", mi.gross_model.label if mi.gross_model else "—"),
                ("Evidence — sample", q.sample if q else "—"),
                ("Evidence — recency", q.recency if q else "—"),
                ("Evidence — spread", q.spread if q else "—"),
                ("Source", "retail_history v3 (recorded prices) — historical evidence, not a current-value estimate")])
    return (f'<div class="card"><h3>{esc(mi.model)} <span class="muted" style="font-size:13px">· '
            f'{mi.active_units} active · {mi.sales_count} historical sales</span> {qchip}</h3>'
            f'<div style="font-size:13px;color:var(--muted);margin:2px 0">Historical turn</div>{dts}'
            f'<div style="font-size:13px;color:var(--muted);margin:6px 0 2px">Historical recorded resale</div>{resale}'
            f'<div style="font-size:13px;color:var(--muted);margin:6px 0 2px">Historical recorded gross</div>{gross}'
            f'<div style="font-size:13px;color:var(--muted);margin:6px 0 2px">Model-year age at resale (maturity)</div>{mat}'
            + disclosure("Why / Proof", proof)
            + f'<p style="margin-top:6px"><a href="/service-loaner/model/{esc(mi.model)}">Resale what-if for {esc(mi.model)} →</a></p></div>')


def _unit_card(u):
    age = f"{u.age_days}d in service" if u.age_days is not None else "in-service date not resolved"
    mi = f"{u.mileage:,} mi" if u.mileage_available else "mileage not reported"
    pos = safe(f'VIN …{esc(u.vin[-6:])} · <strong>{esc(age)}</strong> · <strong>{esc(mi)}</strong> · '
               f'{esc(u.membership_state)} / {esc(u.rental_state or "—")}')
    flags = "".join(chip("skip", f) for f in u.quality_flags)
    actions = safe(f'<a href="/service-loaner/unit/{esc(u.id)}"><button class=secondary style="padding:6px 12px">'
                   'Open unit</button></a>')
    return rec_card("", u.model or "loaner", "", pos, "", actions, chip_html=flags)


def _placement_row(rank, c, *, compact=False):
    """One physical ADD candidate — full unit identity so Kyle never leaves Elite to find the vehicle. The
    economic RETIRE/HOLD/expected-cost call is a reserved Phase-4 slot (Pending Economics)."""
    ident = (f'{esc(c.year)} {esc(c.model)}' + (f' {esc(c.trim)}' if c.trim else '')
             + (f' {esc(c.drivetrain)}' if c.drivetrain else '')).strip()
    colors = " / ".join(x for x in (c.exterior, c.interior) if x)
    tone = {"EXCESS": "healthy", "COVERED": "ok", "UNKNOWN": "attention"}.get(c.new_retail_state, "attention")
    econ = safe(f'{badge("pending", "Pending Economics")}')
    # VIN column shows the AUTHORITATIVE VIN only; never a serial/stock masquerading as a VIN
    vin_cell = (esc(c.vin[-8:]) if c.vin_authoritative and c.vin else
                safe(f'{badge("unresolved", "no VIN")}' + (f' <span class="muted">serial {esc(c.serial)}</span>'
                                                           if c.serial else '')))
    return [esc(rank), esc(c.stock or "—"), vin_cell, safe(esc(ident) or "—"),
            esc(colors or "—"), safe(badge(tone, c.new_retail_state)), esc(c.rank_reason), econ]


def _unit_icv_cell(store, u):
    """Applicable ICV for this physical unit, resolved from its AUTHORITATIVE in-service month. UNKNOWN renders
    as 'Unknown' — never '$0 pending' (the legacy bug): a missing economic value is not zero."""
    from ...loaner.program_inputs import resolve_for_unit
    if not u.in_service_date:
        return safe(badge("unresolved", "Unknown"))
    r = resolve_for_unit(store, "icv", model=u.model or "", in_service_date=u.in_service_date,
                         model_year=getattr(u, "model_year", "") or "")
    if r.get("status") != "resolved":
        return safe(badge("unresolved", "Unknown"))
    v = r["entry"].value
    return f"${v:,}" if v is not None else safe(badge("unresolved", "Unknown"))


def _fleet_decisions(app, scope, intel):
    """The SINGLE per-unit KEEP/PULL/SWAP decision map ({unit_id: decision}) every Service-Loaner surface
    consumes — ONE decision engine (build_unit_decision), computed once with shared inputs so the Command Board,
    Current Fleet, operating plan and per-unit table can never disagree."""
    from ...loaner.sl_decision import build_unit_decision
    from ...clock import to_utc_iso
    out = {}
    units = [u for u in getattr(intel, "units", ()) if u.vin]
    if not units:
        return out
    mi_by_model = {(mi.model or "").upper(): mi for mi in getattr(intel, "models", ())}
    today = to_utc_iso(app.stack.clock.now())[:10]
    from ...loaner.sl_decision import _retail_rows, _inventory_rows
    shared_retail_rows = _retail_rows(app, scope)
    shared_inv = _inventory_rows(app, scope)
    market_cache = {}
    swap_net = None
    try:
        from ...loaner.unit_econ import build_placement_econ
        econ = build_placement_econ(app, scope, today[:7], n=1, intel=intel)
        if econ.get("have_economics") and econ.get("all_econ"):
            swap_net = econ["all_econ"][0].net()
    except Exception:   # noqa: BLE001
        swap_net = None
    for u in units:
        try:
            out[u.id] = build_unit_decision(app, scope, u, mi_by_model.get((u.model or "").upper()),
                                            today=today, swap_candidate_net=swap_net,
                                            retail_rows=shared_retail_rows, inv=shared_inv,
                                            market_cache=market_cache)
        except Exception:   # noqa: BLE001 — a single unit must never break the board
            continue
    return out


_RELEASE_ACTIONS = ("PULL", "SWAP")


def _fleet_unit_row(u, icv_cell, decision=None):
    """Compact current-fleet cascade row: identity + lifecycle facts + the SAME certified per-unit economic call
    (KEEP / PULL / SWAP / UNRESOLVED) the per-unit table shows — never a hardcoded 'Pending Economics'."""
    age = f"{u.age_days}d" if u.age_days is not None else "—"
    miles = f"{u.mileage:,}" if (u.mileage_available and u.mileage is not None) else "—"
    src = esc(u.rental_state or u.membership_state or "—")
    action = (decision or {}).get("action")
    call = (safe(badge(_ACTION_TONE.get(action, "pending"), action)) if action
            else safe(badge("unresolved", "UNRESOLVED")))
    return [safe(f'<a href="/service-loaner/unit/{esc(u.id)}">{esc(u.stock if hasattr(u, "stock") else (u.vin or "")[-8:])}</a>'),
            esc((u.vin or "—")[-8:]), esc(u.model or "—"), src, esc(u.in_service_date or "—"), esc(age), esc(miles),
            icv_cell, call]


def _fleet_position_card(app, scope, decisions=None):

    from ...loaner.self_balancing import build_requirement, source_label

    sb = build_requirement(_conn(app), scope, app.prefs)
    tone = {"no_target": "attention", "resolved_zero": "healthy", "resolved_need": "pending"}.get(
        sb.resolution, "pending"
    )

    releasing = (
        sum(1 for d in decisions.values() if d.get("action") in _RELEASE_ACTIONS)
        if decisions else int(sb.releasing_now or 0)
    )
    remaining = max(0, int(sb.current_active) - releasing)

    if sb.desired is None:
        need_txt = "— set target"
        need_attn = False
        why = f"{releasing} unit(s) are being pulled under the current operating plan; {remaining} are expected to remain."
    else:
        need_val = max(0, int(sb.desired) - remaining)
        need_txt = str(need_val)
        need_attn = need_val > 0
        if remaining == int(sb.desired):
            why = (
                f"{releasing} unit(s) are being pulled under the current operating plan, leaving {remaining} — "
                f"exactly the target of {int(sb.desired)}. No add is required."
            )
        elif remaining > int(sb.desired):
            why = (
                f"{releasing} unit(s) are being pulled under the current operating plan, leaving {remaining} — "
                f"{remaining - int(sb.desired)} above target. No add is required."
            )
        else:
            why = (
                f"{releasing} unit(s) are being pulled under the current operating plan, leaving {remaining} — "
                f"{int(sb.desired) - remaining} below target."
            )

    band = stat_row([
        metric(sb.current_active, "In service"),
        metric(sb.desired if sb.desired is not None else "not set", "Target"),
        metric(releasing, "Pulling"),
        metric(remaining, "Expected to remain"),
        metric(need_txt, "Add (calculated)", attn=need_attn),
    ])

    return (
        '<div class="card"><h2 style="margin-top:4px">Fleet position</h2>' + band
        + f'<p style="margin:6px 0 2px">{badge(tone, source_label(sb))}</p>'
        + f'<p style="margin:4px 0"><strong>Why:</strong> {esc(why)}</p>'
        + '<p style="margin-top:6px"><a href="/ordering/sl-requirements">Open planning &amp; directives →</a></p>'
        + '</div>'
    )


_OUTCOME_BADGE = {
    "ECONOMICALLY_RECOMMENDED": ("healthy", "economically recommended"),
    "OPERATIONALLY_SAFE_ECON_INCOMPLETE": ("pending", "operationally safe · economics pending"),
    "DO_NOT_PLACE": ("attention", "do not place"),
    "UNRESOLVED": ("unresolved", "unresolved"),
}


_ACTION_TONE = {"KEEP": "healthy", "PULL": "attention", "SWAP": "pending", "UNRESOLVED": "unresolved"}


def _fleet_plan_card(app, scope, intel, add_n=0, decisions=None):
    """The unmistakable operating plan (item 10): the per-unit economic decisions consolidated into KEEP /
    PULL·RETIRE / SWAP·BALANCE / ADD / ORDER / UPCOMING, each naming the exact physical vehicle. It REUSES the
    SHARED KEEP/PULL/SWAP decision map (one engine) and the certified placement econ — it does not re-derive
    economics. SWAP names the incoming New-Retail replacement VIN whenever it is physically known; ORDER is only
    the residual that physical placement/swap cannot satisfy (never a fabricated model order)."""
    from ...clock import to_utc_iso
    units = [u for u in getattr(intel, "units", ()) if u.vin]
    if not units:
        return ""
    if decisions is None:
        decisions = _fleet_decisions(app, scope, intel)
    today = to_utc_iso(app.stack.clock.now())[:10]

    # Build physical replacement economics only when the operating plan can use them.
    repl_by_model, all_repl = {}, []
    swap_net = None
    _needs_swap = any((d.get("action") if isinstance(d, dict) else None) == "SWAP"
                      for d in decisions.values()) if isinstance(decisions, dict) else False
    try:
        from ...loaner.self_balancing import build_requirement
        _sb_repl = build_requirement(_conn(app), scope, app.prefs)
        _needs_add = bool(_sb_repl.desired is not None and int(_sb_repl.calculated_need) > 0)
    except Exception:   # noqa: BLE001
        _needs_add = False
    try:
        from ...ordering.cross_domain import PlannedRequirementStore
        _needs_order = bool(PlannedRequirementStore(app.prefs, scope).by_model())
    except Exception:   # noqa: BLE001
        _needs_order = False

    if _needs_swap or _needs_add or _needs_order:
        try:
            from ...loaner.unit_econ import build_placement_econ
            econ = build_placement_econ(app, scope, today[:7], n=max(1, int(add_n or 1)), intel=intel)
            if econ.get("have_economics") and econ.get("all_econ"):
                swap_net = econ["all_econ"][0].net()
                for pe in econ["all_econ"]:
                    repl_by_model.setdefault((pe.model or "").upper(), []).append(pe)
                    all_repl.append(pe)
        except Exception:   # noqa: BLE001
            repl_by_model, all_repl, swap_net = {}, [], None

    keep, pull, swap, upcoming = [], [], [], []
    used_repl = set()

    def _take_replacement(model):
        """Assign the best still-unused physical replacement, preferring the same model, then any (count-once)."""
        for pe in repl_by_model.get((model or "").upper(), []):
            if pe.unit_id not in used_repl:
                used_repl.add(pe.unit_id)
                return pe
        for pe in all_repl:
            if pe.unit_id not in used_repl:
                used_repl.add(pe.unit_id)
                return pe
        return None

    for u in units:
        d = decisions.get(u.id)
        if d is None:
            continue
        f = d["facts"]
        vin = (f.get("vin") or u.vin or "")
        veh = " ".join(x for x in (f.get("model_year"), f.get("model")) if x)
        rel = (f.get("release") or {}).get("release_by") if f.get("release") else None
        if d["action"] == "PULL":
            pull.append((vin, veh, rel, d["why"]))
        elif d["action"] == "SWAP":
            pe = _take_replacement(f.get("model"))
            swap.append((vin, veh, pe, d["why"]))
        elif d["action"] == "KEEP":
            keep.append((vin, veh, rel))
        if rel:
            upcoming.append((rel, vin, veh, d["action"]))

    def _vin8(v):
        return esc((v or "")[-8:])

    seg = []
    # KEEP
    seg.append('<h3 style="margin:10px 0 4px">KEEP — remain in the fleet</h3>'
               + (table(["VIN", "Vehicle", "Watch release by"],
                        [[_vin8(v), esc(veh), esc(rel or "—")] for v, veh, rel in keep])
                  if keep else empty("No active unit is a clear KEEP right now.")))
    # PULL / RETIRE
    seg.append('<h3 style="margin:14px 0 4px">PULL / RETIRE — exit these</h3>'
               + (table(["VIN", "Vehicle", "Latest prudent release", "Why"],
                        [[_vin8(v), esc(veh), esc(rel or "—"), safe(f'<span class="muted">{esc(why)}</span>')]
                         for v, veh, rel, why in pull])
                  if pull else empty("No unit's best current decision is to exit.")))
    # SWAP / BALANCE — PULL current → REPLACE WITH physical New-Retail unit
    if swap:
        srows = []
        for v, veh, pe, why in swap:
            if pe is not None:
                repl = safe(f'<strong>{esc((pe.unit_id or "")[-8:])}</strong> · {esc(pe.identity)} '
                            f'({_money(pe.net())} net)')
            else:
                repl = safe('<span class="muted">no physically-known New-Retail replacement — hold or order</span>')
            srows.append([_vin8(v), esc(veh), repl, safe(f'<span class="muted">{esc(why)}</span>')])
        seg.append('<h3 style="margin:14px 0 4px">SWAP / BALANCE — put the better physical vehicle in the slot</h3>'
                   '<p class="muted" style="font-size:12px">Balance = the physical vehicle that should occupy the '
                   'slot now for the highest total dealership outcome — never mileage/Velocity/model staggering.</p>'
                   + table(["PULL (current SL)", "Vehicle", "REPLACE WITH (New-Retail VIN)", "Why"], srows))
    # ADD ??? actual self-balancing fleet need controls whether another slot exists.
    # add_n is candidate-inspection quantity only.
    try:
        from ...loaner.self_balancing import build_requirement
        _sb_add = build_requirement(_conn(app), scope, app.prefs)
        _fleet_add_need = None if _sb_add.desired is None else max(0, int(_sb_add.calculated_need))
    except Exception:  # noqa: BLE001
        _fleet_add_need = None

    if _fleet_add_need and _fleet_add_need > 0:
        best = next((pe for pe in all_repl if pe.unit_id not in used_repl and pe.net() > 0), None)
        seg.append('<h3 style="margin:14px 0 4px">ADD - fill an additional slot</h3>'
                   + (safe(f'<p>Best physical unit to add: <strong>{esc((best.unit_id or "")[-8:])}</strong> - '
                           f'{esc(best.identity)} ({_money(best.net())} net).</p>') if best
                      else empty("Fleet needs another slot, but no positive-net physical candidate is certified.")))
    elif _fleet_add_need == 0:
        seg.append('<h3 style="margin:14px 0 4px">ADD</h3>'
                   + empty("No additional Service-Loaner slot is required by the current fleet target."))
    else:
        seg.append('<h3 style="margin:14px 0 4px">ADD</h3>'
                   + empty("Fleet ADD requirement is unresolved; no ADD command is issued."))
    # ORDER — residual only (governed planned requirement minus physical surplus); never fabricated
    seg.append(_fleet_order_residual(app, scope, all_repl, used_repl))
    # UPCOMING — planned future exits/swaps before they become emergencies
    upcoming = [x for x in upcoming if x[0]]
    upcoming.sort(key=lambda t: t[0])
    if upcoming:
        seg.append('<h3 style="margin:14px 0 4px">UPCOMING — planned exits/swaps</h3>'
                   + table(["Release by", "VIN", "Vehicle", "Planned action"],
                           [[esc(rel), _vin8(v), esc(veh), esc(act)] for rel, v, veh, act in upcoming[:8]]))

    return ('<div class="card"><h2>Fleet operating plan '
            '<span class="badge">KEEP · PULL · SWAP · ADD · ORDER</span></h2>'
            '<p class="muted">The economic KEEP/PULL/SWAP core, consolidated into the actual operating plan — '
            'each line names the physical vehicle. Detail and Proof are in the per-unit table below.</p>'
            + "".join(seg) + '</div>')


def _fleet_order_residual(app, scope, all_repl, used_repl):
    """ORDER = only the residual a governed planned Service-Loaner requirement cannot fill from physical surplus.
    Fail-closed: if a model's future SL requirement is unresolved, say so — never manufacture a model order."""
    try:
        from ...ordering.cross_domain import PlannedRequirementStore
        prs = PlannedRequirementStore(app.prefs, scope)
        planned = prs.by_model()
    except Exception:   # noqa: BLE001
        planned = {}
    if not planned:
        return ('<h3 style="margin:14px 0 4px">ORDER — residual only</h3>'
                + empty("No governed additive Service-Loaner requirement is set, so there is no residual to "
                        "order. Physical placement/swap covers today's plan."))
    avail_by_model = {}
    for pe in all_repl:
        if pe.unit_id not in used_repl:
            avail_by_model[(pe.model or "").upper()] = avail_by_model.get((pe.model or "").upper(), 0) + 1
    rows = []
    for model, need in sorted(planned.items()):
        have = avail_by_model.get(model, 0)
        residual = max(0, need - have)
        rows.append([esc(model), esc(need), esc(have), esc(residual),
                     esc("order residual" if residual else "covered by physical surplus")])
    return ('<h3 style="margin:14px 0 4px">ORDER — residual only</h3>'
            '<p class="muted" style="font-size:12px">Order only what physical placement/swap cannot satisfy. '
            'Residual = governed planned requirement − physically-available surplus.</p>'
            + table(["Model", "Planned need", "Physical surplus", "Residual to order", "Call"], rows))


def _unit_actions_card(app, scope, intel, decisions=None):
    """Concise per-active-unit KEEP / PULL / SWAP / UNRESOLVED recommendation. The economic detail lives in
    Proof; the operator sees the call, the advantage vs next-best, key facts, and one human Why. Uses the SHARED
    decision map (one engine) when provided."""
    units = [u for u in getattr(intel, "units", ()) if u.vin]
    if not units:
        return ""
    if decisions is None:
        decisions = _fleet_decisions(app, scope, intel)
    rows = []
    for u in units:
        d = decisions.get(u.id)
        if d is None:
            continue
        c, f = d["components"], d["facts"]
        nets = d["nets"]
        adv = "—"
        if len(nets) >= 2 and d["action"] in nets:
            second = max((v for k, v in nets.items() if k != d["action"]), default=None)
            if second is not None:
                adv = f"${nets[d['action']] - second:,.0f}"
        vel = ("unknown" if f.get("velocity") is None
               else "preserved" if c["velocity_now"] or c["velocity_future"] else "at risk / forfeited")
        rel = (f.get("release") or {}).get("release_by", "—") if f.get("release") else "—"
        # unknown program values render as "—" (never a misleading $0); real computed zeros show $0
        vel_cell = ("Unknown" if f.get("velocity") is None
                    else f"{_money(c['velocity_now'])} / {_money(c['velocity_future'])}")
        icv_cell = "Unknown" if f.get("icv") is None else _money(c["icv_earned_sunk"])
        proof = kv([("Adjusted basis now", _money(c["adjusted_basis_now"])),
                    ("Cumulative write-down now", _money(c["cumulative_write_down_now"])),
                    ("Front-end gross now", _money(c["front_end_gross_now"])),
                    ("Front-end gross if kept", _money(c["front_end_gross_future"])),
                    ("Velocity (contingent) now / future", vel_cell),
                    ("ICV earned (sunk — not in delta)", icv_cell),
                    ("Expected used price now / future", f"{_money(f['price_now'])} / {_money(f['price_future'])}"),
                    ("Latest prudent release", esc(rel)),
                    ("Missing / gated", esc(", ".join(d["gated"]) or "none")),
                    ("Nets (PULL / KEEP / SWAP)", esc(" / ".join(f"{k} ${v:,.0f}" for k, v in nets.items()) or "—")),
                    ("Source", "invoice+write-down basis · front-end gross only (no backend) · maturity evidence")])
        rows.append([
            esc((f.get("vin") or "")[-8:]),
            esc(" ".join(x for x in (f.get("model_year"), f.get("model")) if x)),
            safe(badge(_ACTION_TONE.get(d["action"], "pending"), d["action"])),
            esc(adv), _money(c["adjusted_basis_now"]), _money(c["front_end_gross_now"]), esc(vel), esc(rel),
            esc(d["confidence"]),
            safe(f'<span class="muted">{esc(d["why"])}</span> ' + disclosure("Proof", proof))])
    return ('<div class="card"><h2>Recommended action per unit '
            '<span class="badge">KEEP / PULL / SWAP</span></h2>'
            '<p class="muted" style="font-size:12px">Incremental from now: already-earned ICV is sunk (shown in '
            'Proof, not in the delta); Velocity is contingent on the 240-day deadline; write-down counts once in '
            'the adjusted basis; gross is front-end only. A unit gates to UNRESOLVED when an authoritative input '
            'is missing.</p>'
            + table(["VIN", "Vehicle", "Action", "Advantage", "Adj. basis", "Front gross", "Velocity",
                     "Release by", "Conf.", "Why / Proof"], rows) + '</div>')


def _money(v):
    return "—" if v is None else f"${v:,.0f}"


def _add_id_cell(c):
    """Physical identity for the command line / table: Stock# and authoritative VIN (or last-8), else the
    source Serial clearly marked as not-a-VIN. A physical unit is always named by stock# + VIN/serial."""
    stock = c.stock or "—"
    if c.vin_authoritative and c.vin:
        return f"{stock} / VIN {c.vin[-8:]}"
    if c.serial:
        return f"{stock} / serial {c.serial} (no VIN in feed)"
    return stock


def _human_sl_price_basis(raw):
    """Operator wording for certified pricing provenance; raw trace remains available separately."""
    s = str(raw or "")
    low = s.lower()
    if "exact full model code" in low:
        return "Observed used sale evidence from the same exact configuration."
    if "explicit market predecessor" in low:
        return "Observed used sale evidence from the approved predecessor configuration."
    if "same raw code4" in low:
        return "Observed used sale evidence from the same configuration family."
    if "observed used transaction price" in low:
        return "Observed used transaction evidence from the governed comparable set."
    if "insufficient" in low or "gated" in low:
        return "Used-market evidence is not strong enough yet to issue a price."
    return "Observed used-market evidence under the certified comparable hierarchy."


def _exec_demo_reassignment_card(app, scope):
    """Visibility only: active Executive Demos may be reassignment candidates, never free supply."""
    try:
        demos = _conn(app).execute(
            "SELECT vin,membership_state,assigned_role,portfolio_role FROM executive_demo_unit "
            "WHERE store_scope=? AND superseded_by IS NULL AND retirement_event IS NULL "
            "ORDER BY created_at", (scope,)).fetchall()
    except Exception:   # noqa: BLE001
        return ""
    if not demos:
        return ""
    rows = []
    for d in demos:
        vin = str(d["vin"] or "")
        if not vin:
            continue
        role = str(d["assigned_role"] or d["portfolio_role"] or "Executive Demo")
        state = str(d["membership_state"] or "")
        rows.append([esc(vin[-8:]), esc(role), esc(state),
                     safe('<strong>REASSIGNMENT REVIEW</strong>'),
                     safe('<span class="muted">May be evaluated for Executive Demo -> Service Loaner '
                          'when total-dealership economics justify the move. Demo replacement/opportunity '
                          'cost must resolve before any command.</span>')])
    if not rows:
        return ""
    return ('<div class="card"><h2>Executive Demo -> Service Loaner opportunities '
            '<span class="badge">cross-domain review</span></h2>'
            '<p class="muted" style="font-size:12px">Executive Demo is a current-use state, not a '
            'permanent exclusion. These units stay count-once and are not treated as free Retail supply.</p>'
            + table(["VIN", "Current assignment", "Demo state", "Status", "Rule"], rows) + '</div>')


_SL_ADD_RUNTIME_CACHE = {}


def _cached_sl_add_ranking(app, scope, committed, target):
    """Compute the full physical ADD ranking once, then slice for operator inspection quantity.
    Cache is process-local, write-sensitive, and short-lived."""
    from ...loaner.sl_add import rank_add_candidates
    conn = _conn(app)
    changes = getattr(conn, "total_changes", 0)
    key = (scope, changes, tuple(sorted(committed or ())))
    now = time.monotonic()
    hit = _SL_ADD_RUNTIME_CACHE.get(key)
    if hit and now - hit["at"] <= 120:
        full = hit["res"]
    else:
        full = rank_add_candidates(app, scope, n=20, committed_vins=committed)
        _SL_ADD_RUNTIME_CACHE.clear()
        _SL_ADD_RUNTIME_CACHE[key] = {"at": now, "res": full}

    res = dict(full)
    all_ready = list(full.get("all_ready") or full.get("ready") or ())
    n = max(0, min(20, int(target or 0)))
    res["requested"] = n
    res["ready"] = all_ready[:n]
    res["backups"] = all_ready[n:n + 4]
    res["commandable"] = [c for c in all_ready if getattr(c, "add_net", 0) > 0][:n]
    return res


def _best_add_card(app, scope, add_n):



    from ...loaner.intelligence import build_intelligence
    from ...loaner.preowned_evidence import latest_retail_rows
    from ...loaner.sl_add import rank_add_candidates, _iso_today
    from ...loaner.self_balancing import build_requirement
    from ...loaner import sl_decision as _sd
    import re as _re

    _today = _iso_today(app.stack.clock)
    _intel = build_intelligence(app.stack.db.conn, scope, app.prefs, app.stack.clock)
    _retail_rows, _ = latest_retail_rows(app.stack.db.conn, scope)
    _inv = _sd._inventory_rows(app, scope)
    _mi = {(m.model or "").upper(): m for m in _intel.models}
    _market_cache = {}

    _pulls = []
    for _u in _intel.units:
        _d = _sd.build_unit_decision(
            app, scope, _u, _mi.get((_u.model or "").upper()),
            today=_today, swap_candidate_net=None,
            retail_rows=_retail_rows, inv=_inv, market_cache=_market_cache,
        )
        if str(_d.get("action") or "").upper() != "PULL":
            continue

        _facts = _d.get("facts") or {}
        _vm = _facts.get("velocity_mileage") or {}

        _unit_id = str(
            getattr(_u, "serial", "") or
            getattr(_u, "stock_number", "") or
            getattr(_u, "stock", "") or
            ""
        ).strip()
        if not _unit_id:
            _vin = str(getattr(_u, "vin", "") or "").strip()
            _m = _re.search(r"([0-9]{6})$", _vin)
            if _m:
                _unit_id = _m.group(1)
        if not _unit_id:
            raise RuntimeError("PULL unit lacks a short operational identifier.")

        _reason = "Over mileage cap" if _vm.get("status") in ("breached", "at_cap") else "Release due"
        _pulls.append((_unit_id, _reason))

    _current = len(_intel.units)
    _remaining = max(0, _current - len(_pulls))

    _pull_rows = ''.join(
        '<tr>'
        '<td style="font-weight:800;font-size:16px">' + esc(_unit_id) + '</td>'
        '<td>' + esc(_reason) + '</td>'
        '</tr>'
        for _unit_id, _reason in _pulls
    )

    _sb = build_requirement(_conn(app), scope, app.prefs)
    if _sb.desired is None:
        # Fail closed VISIBLY — never raise, and never fabricate a target, ADD requirement, candidates, or
        # economics. The PULL calls stand on their own governed evidence and are still shown; the ADD command is
        # withheld until the governed Service Loaner target is set.
        return (
            '<div class="card" style="border:2px solid var(--line);padding:18px">'
            '<h2 style="margin:0 0 6px">Service Loaner - Manager Action</h2>'
            '<div style="font-size:19px;font-weight:900;margin:4px 0 10px">'
            + esc(f"{_current} current | {len(_pulls)} pull now | {_remaining} remain | Target not set")
            + '</div>'
            + safe(badge("attention", "Target unresolved"))
            + '<p class="muted" style="margin:8px 0 16px">The governed Service Loaner target is not set, so no '
            'ADD command can be issued. Set the desired fleet target to enable placement — no target, ADD '
            'requirement, candidates, or economics are assumed.</p>'
            '<h3 style="margin:0 0 6px">PULL NOW - ' + str(len(_pulls)) + '</h3>'
            '<table><thead><tr><th>Unit</th><th>Why</th></tr></thead>'
            '<tbody>' + _pull_rows + '</tbody></table>'
            '</div>'
        )
    _target = int(_sb.desired)
    _add_required = max(0, _target - _remaining)

    # Economics govern ranking internally but are intentionally not rendered.
    _ranked = rank_add_candidates(
        app, scope, n=max(7, int(add_n or 0)),
        today=_today,
    )
    _candidates = list(_ranked.get("commandable") or [])[:7]

    _candidate_rows = []
    for _rank, _c in enumerate(_candidates, 1):
        # Positive economics still govern inclusion; value stays private.
        if float(getattr(_c, "add_net", 0) or 0) <= 0:
            continue

        _unit = str(getattr(_c, "stock", "") or "").strip()
        if not _unit:
            _unit = str(getattr(_c, "serial", "") or "").strip()
        if not _unit:
            continue

        _trim = str(getattr(_c, "trim", "") or "").strip()
        _model = str(getattr(_c, "model", "") or "").strip()
        if _trim.upper().startswith((_model + " ").upper()):
            _trim = _trim[len(_model) + 1:]

        _vehicle = " ".join(
            str(x or "").strip() for x in (
                getattr(_c, "year", ""),
                _model,
                _trim,
            ) if str(x or "").strip()
        )

        _candidate_rows.append(
            '<tr>'
            f'<td style="font-weight:800">#{_rank}</td>'
            f'<td style="font-weight:800">{esc(_unit)}</td>'
            f'<td>{esc(_vehicle)}</td>'
            '</tr>'
        )

    _status = (
        f"{_current} current | {len(_pulls)} pull now | {_remaining} remain | "
        f"Target {_target} | Add required {_add_required}"
    )

    return (
        '<div class="card" style="border:2px solid var(--line);padding:18px">'
        '<h2 style="margin:0 0 6px">Service Loaner - Manager Action</h2>'
        '<div style="font-size:19px;font-weight:900;margin:4px 0 16px">'
        + esc(_status) +
        '</div>'
        '<div style="display:grid;grid-template-columns:1fr 1.2fr;gap:18px;align-items:start">'
        '<div>'
        '<h3 style="margin:0 0 6px">PULL NOW - ' + str(len(_pulls)) + '</h3>'
        '<table><thead><tr><th>Unit</th><th>Why</th></tr></thead>'
        '<tbody>' + _pull_rows + '</tbody></table>'
        '</div>'
        '<div>'
        '<h3 style="margin:0 0 3px">NEXT PLACEMENT - IF NEEDED</h3>'
        '<div class="muted" style="font-size:12px;margin-bottom:6px">Retail-safe priority order</div>'
        '<table><thead><tr><th>#</th><th>Unit</th><th>Vehicle</th></tr></thead>'
        '<tbody>' + ''.join(_candidate_rows) + '</tbody></table>'
        '</div>'
        '</div>'
        '</div>'
    )


def _sequential_placement_card(app, scope, add_n):
    """The sequential portfolio answer to 'add N loaners': pick the best placement, recompute Retail coverage,
    pick the next — with per-step outcome, human Why, a VIN/stock identity, provisional economics (Proof), the
    Retail state left behind, the units that must NOT be pulled, and the remaining quantity to ORDER."""
    if not add_n:
        return ""

    # Requested candidate count is not an ADD requirement.
    try:
        from ...loaner.self_balancing import build_requirement
        _sb_seq = build_requirement(_conn(app), scope, app.prefs)
        if _sb_seq.desired is not None and max(0, int(_sb_seq.calculated_need)) == 0:
            return ""
    except Exception:  # noqa: BLE001
        pass
    from ...loaner.sl_optimizer import optimize_sl_placement
    from ...ordering.cross_domain import committed_vins
    from ...clock import to_utc_iso
    month = to_utc_iso(app.stack.clock.now())[:7]
    try:
        committed = frozenset(committed_vins(_conn(app), scope, app.prefs).keys())
        res = optimize_sl_placement(app, scope, month, add_n, loaner_vins=committed)
    except Exception:   # noqa: BLE001 — placement must never break the board
        return ""
    if not res.get("loaded"):
        return ('<div class="card"><h2>What to do — add ' + esc(str(add_n)) + ' Service Loaners</h2>'
                + empty("No New-Retail inventory snapshot is loaded yet — load Inventory in Data. No candidates "
                        "are invented.") + '</div>')
    head = ('<div class="card"><h2>What to do — add ' + esc(str(add_n)) + ' Service Loaners '
            '<span class="badge">sequential portfolio</span></h2>'
            '<p class="muted" style="font-size:12px">Each placement is chosen, then Retail coverage is '
            'recomputed before the next — so a unit that would push its combination into a Retail shortage is '
            'NOT pulled. Economics are provisional until the write-down treatment is governed, so no placement '
            'is yet an economic certification.</p>')
    rows = []
    for st in res["steps"]:
        vin_cell = (esc(st.vin[-8:]) if st.vin_authoritative and st.vin else safe(badge("unresolved", "no VIN")))
        tone, label = _OUTCOME_BADGE.get(st.outcome, ("pending", st.outcome))
        proof = kv([(f"{t.label} ({t.role})",
                     safe(("Unknown" if t.value is None else f"${int(t.value):,}")
                          + (f' <span class="muted" style="font-size:12px">{esc(t.source)}</span>'
                             if t.source and any(c in t.source for c in "×%") else '')))
                    for t in st.econ_terms]
                   + ([("Provisional net", f"${st.net:,.0f}")] if st.net is not None else [])) if st.econ_terms \
            else safe('<p class="muted" style="font-size:12px">Economics not computable — required inputs missing.</p>')
        rows.append([esc(str(st.rank)), esc(st.stock or "—"), vin_cell,
                     esc((st.model_year + " " if st.model_year else "") + st.identity),
                     safe(badge(tone, label)), esc(st.retail_after.title()),
                     safe(f'<span class="muted">{esc(st.why)}</span> ' + disclosure("Proof", proof))])
    body = [head]
    if rows:
        body.append(table(["#", "Stock", "VIN", "Vehicle", "Outcome", "Retail after", "Why / Proof"], rows))
    else:
        body.append(empty("No unit can be safely placed from current surplus."))
    if res["remaining_to_order"]:
        body.append('<div class="callout"><strong>Order ' + esc(str(res["remaining_to_order"]))
                    + ' specifically for Service Loaner.</strong> Only ' + esc(str(res["placed"])) + ' of '
                    + esc(str(res["requested"])) + ' can be safely placed from existing Retail surplus; the '
                    'remaining ' + esc(str(res["remaining_to_order"])) + ' become a Service-Loaner ORDER '
                    'obligation (Retail demand unchanged). <a href="/ordering/sl-requirements">Record it</a>.</div>')
    dnp = [x for x in res["rejected"] if x["outcome"] == "DO_NOT_PLACE"]
    if dnp:
        body.append(disclosure(f"Do NOT pull ({len(dnp)}) — would harm Retail",
                               table(["Vehicle", "Stock", "Why"],
                                     [[esc(x["identity"]), esc(x["stock"] or "—"), esc(x["why"])] for x in dnp])))
    if res.get("sequential_diverges_from_static"):
        body.append('<p class="muted" style="font-size:12px">Note: a naive top-N of the static shortlist would '
                    'have over-placed here — the sequential recompute stopped at the real surplus.</p>')
    return "".join(body) + '</div>'


def _economic_ranking_card(app, scope, add_n, intel=None):
    """When the authoritative economic inputs exist, this is the REAL answer to 'which N should we place' —
    ranked by total-dealership net (via the certified ideal_mix), with a human Why and a per-term Proof. Units
    whose economics are unknown are listed as excluded (never guessed into the ranking). Returns '' when no
    unit is economically rankable yet (the caller then shows the Retail-harm fallback)."""
    from ...loaner.unit_econ import build_placement_econ
    from ...clock import to_utc_iso
    month = to_utc_iso(app.stack.clock.now())[:7]
    try:
        res = build_placement_econ(app, scope, month, n=add_n or 0, intel=intel)
    except Exception:   # noqa: BLE001
        return ""
    if not res.get("have_economics"):
        return ""
    body = ['<div class="card"><h2>Economic placement ranking '
            '<span class="badge">total-dealership net</span></h2>'
            '<p class="muted" style="font-size:12px">Ranked by total-dealership economic net (ICV + Velocity + '
            'expected used gross − write-down − protection buffer − Retail opportunity cost) via the certified '
            'ideal-mix. This is the economic answer, not just lowest Retail-harm.</p>']
    show = res["ranked"] or [{"econ": pe, "net": pe.net(), "identity": pe.identity}
                             for pe in res["all_econ"][:max(1, add_n or 3)]]
    rows = []
    for i, item in enumerate(show, 1):
        pe = item["econ"]
        proof = kv([(f"{t.label} ({t.role})",
                     safe(("Unknown" if t.value is None else f"${int(t.value):,}")
                          + (f' <span class="muted" style="font-size:12px">{esc(t.source)}</span>'
                             if t.source and any(c in t.source for c in "×%") else '')))
                    for t in pe.terms]
                   + [("Net (in − cost)", f"${pe.net():,.0f}")])
        rows.append([esc(str(i)), esc(pe.stock or pe.unit_id[-8:]), esc(pe.identity),
                     safe(f'<strong>${pe.net():,.0f}</strong>'), safe(disclosure("Proof — terms", proof))])
    body.append(table(["#", "Stock/VIN", "Model / trim", "Net", "Proof"], rows))
    if res["excluded"]:
        ex = "; ".join(f'{esc(e["identity"])} (missing {esc(", ".join(e["missing"]))})' for e in res["excluded"][:6])
        body.append('<p class="muted" style="font-size:12px">Excluded — economics unknown, never guessed: '
                    + ex + '.</p>')
    body.append('<p class="muted" style="font-size:12px">Why: Elite prefers the highest-net surplus units — a '
                'high write-down (value lost as a loaner) can make an older/excess unit rank BELOW a newer model '
                'with better retained value, even though it looks attractive on age alone.</p>')
    return "".join(body) + '</div>'


def _phase4_gates_html(app, scope):
    """Compact list of Phase-4 economic-readiness gates (present vs the actual missing inputs) — so the
    operator sees EXACTLY what remains before the economic placement ranking can run, not a static claim."""
    try:
        from ...loaner.economics_readiness import phase4_gates, ready
        gates = phase4_gates(app, scope)
        if ready(gates):
            return (' ' + badge("healthy", "ready")
                    + ' all required economic inputs are present — the ranking can proceed.')
        items = "".join(
            f'<li>{safe(badge("healthy", "have") if g.present else badge("attention", "need"))} '
            f'{esc(g.label)} — {esc(g.detail)}</li>' for g in gates)
        return f'<ul style="margin:6px 0 0;padding-left:18px;font-size:12.5px">{items}</ul>'
    except Exception:   # noqa: BLE001
        return ""


def _program_coverage(app, scope, intel=None, decisions=None):
    # Fast operator coverage: reuse already-computed current-fleet decisions.
    try:
        units = [u for u in getattr(intel, "units", ()) if getattr(u, "vin", None)] if intel is not None else []
        if units and isinstance(decisions, dict):
            total = len(units)
            icv_known = 0
            vel_known = 0
            my_known = 0
            for u in units:
                d = decisions.get(u.id) or {}
                f = d.get("facts") or {}
                if f.get("icv") is not None:
                    icv_known += 1
                if f.get("velocity") is not None:
                    vel_known += 1
                if f.get("model_year"):
                    my_known += 1

            tone = "healthy" if icv_known == total and vel_known == total else "attention"
            note = ""
            if icv_known < total:
                note = (' <strong>ICV Unknown here means a physical-unit/model-year resolution gap; '
                        'it does not mean your monthly ICV table is missing.</strong>')
            return ('<div class="callout" style="margin:8px 0">'
                    + badge(tone, f"Current fleet program resolution: ICV {icv_known}/{total} | "
                                  f"Velocity {vel_known}/{total} | MY {my_known}/{total}")
                    + f'<span class="muted">{note}</span>'
                    + '<p style="margin-top:6px"><a href="/program-inputs">Open effective-dated Program Inputs</a></p>'
                    + '</div>')

        from .program_inputs import coverage_summary
        return ('<div class="callout" style="margin:8px 0">' + coverage_summary(app, scope)
                + '<p style="margin-top:6px"><a href="/program-inputs">Open effective-dated Program Inputs</a></p></div>')
    except Exception:   # noqa: BLE001
        return ""


def _loaner_command_body(app, s, intel, placement, add_n):

    """Service Loaner execution board. Economics drive the recommendation internally; the default board shows
    only the actions needed to operate the fleet."""
    asof = (
        f'inventory + fleet evidence · as of {esc(intel.retail_as_of)}'
        if intel.retail_as_of else 'inventory + fleet evidence'
    )
    parts = [workspace_header("Service Loaner Command Board", safe(f'<span class="muted">{asof}</span>'))]

    # One shared decision engine. A rented unit can still be a PULL NOW because PULL initiates
    # the retirement process; rental state does not suppress the economic/operating call.
    decisions = _fleet_decisions(app, s.scope, intel)

    parts.append(_best_add_card(app, s.scope, add_n))
    parts.append(_fleet_position_card(app, s.scope, decisions))

    parts.append(
        '<div class="card">'
        '<h3 style="margin:0 0 4px">Program maintenance</h3>'
        '<p class="muted" style="margin:0">Program terms, write-down assumptions and economic proof are kept '
        'off the normal execution board. Use the governed maintenance views when those inputs need review.</p>'
        '<p style="margin-top:8px"><a href="/program-inputs">Program Inputs</a> · '
        '<a href="/ordering/sl-requirements">Planning &amp; directives</a></p>'
        '</div>'
    )

    return "".join(parts)


def register(app):
    @app.get("/new-inventory")
    def new_inventory(app, req):
        s = req.session
        app.require(s, "workspace.view")
        app.ensure_inventory_published(s.scope)     # keep the review workflow in sync with the issued board
        conn = _conn(app)
        rows = conn.execute(
            "SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued' ORDER BY issued_time,id",
            (s.scope,)).fetchall()
        ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
            "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (s.scope,)).fetchall()}

        from ...newinv.publish import plan_call
        _rank = {"ACQUIRE": 0, "EXCESS": 1, "MONITOR": 2, "NO_ACTION": 3}
        int_need = arr_excess = inc_excess = acquiring = 0
        board = []
        for r in rows:
            try:
                dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
            except Exception:
                dec = {}
            if not dec:
                continue                            # legacy (non-discrete) plan -> only the portfolio table below
            kind, _qty, label = plan_call(dec)
            acq = int(dec.get("acquire_units", 0) or 0)
            ax, ix = int(dec.get("arrived_excess", 0) or 0), int(dec.get("incoming_excess", 0) or 0)
            int_need += acq; arr_excess += ax; inc_excess += ix
            acquiring += 1 if acq > 0 else 0
            mon = ", ".join(mm.get("month", "") for mm in (dec.get("monitor_months") or [])) or "—"
            tone = {"ACQUIRE": "attention", "EXCESS": "pending", "MONITOR": "healthy"}.get(kind, "healthy")
            cred = dec.get("credibility") if isinstance(dec.get("credibility"), dict) else {}
            board.append((_rank.get(kind, 3), [
                safe(badge(tone, label)), esc(_readable(ident.get(r["combination_id"], r["combination_id"]))),
                esc(round(dec.get("target_level", 0) or 0, 2)), esc(r["current_supply"]),
                esc(dec.get("incoming_in_horizon", r["future_supply"])), esc(dec.get("pending_timing", 0)),
                esc(mon), esc(dec.get("dts_burden", "—")),
                esc(f'{dec.get("evidence_level", "—")}/Z{round(cred.get("credibility_z", 0) or 0, 3)}')]))
        board.sort(key=lambda t: t[0])

        parts = []
        if board:                                   # discrete whole-vehicle operating board (certified plan)
            summary = kv([("INTEGER TOTAL NEED (vehicles to ACQUIRE now)", int_need),
                          ("Acquiring combinations", acquiring),
                          ("ARRIVED EXCESS (disposition)", arr_excess),
                          ("INCOMING EXCESS (redirect)", inc_excess),
                          ("Target Days Supply", 60)])
            parts.append(
                f'<div class="card"><h2>Inventory board (issued)</h2>{summary}'
                '<p class="muted">Whole-vehicle actions are read from the certified issued plan — not recomputed '
                'here. ACQUIRE = commit now; MONITOR = future coverage risk (no commitment due yet); EXCESS = '
                'arrived disposition / incoming redirect. Autonomous external execution is not enabled.</p></div>'
                + '<h2>Combination actions</h2>'
                + table(["Call", "Combination", "Target(60d)", "Arrived", "Incoming (in-horizon)",
                         "Pending ETA", "Monitor", "DTS burden", "Evidence"], [b[1] for b in board]))

        # legacy portfolio view (retained; also serves plans issued without a discrete decision) --------------
        total_need = sum(r["need"] for r in rows)
        total_excess = sum(r["excess"] for r in rows)
        trows = []
        for r in rows:
            st = r["planning_state"]
            trows.append([esc(r["combination_id"]), esc(round(r["expected_demand"], 2)),
                          esc(r["current_supply"]), esc(r["future_supply"]), esc(r["committed_supply"]),
                          esc(round(r["need"], 2)), esc(round(r["excess"], 2)),
                          safe(badge("healthy" if st == "balanced" else "attention", st))])
        parts.append(
            f'<div class="card"><h2>Portfolio</h2>{kv([("Combinations planned", len(rows)), ("Total Need", round(total_need,2)), ("Total Excess", round(total_excess,2))])}'
            '<p class="muted">Analytical totals and Need/Excess are read from the issued Phase 4 plan — not '
            'recomputed here. Current / Future / Committed Supply are shown separately; one unit is counted once.</p></div>'
            + '<h2>Combination plans (issued)</h2>'
            + table(["Combination", "Demand", "Current", "Future", "Committed", "Need", "Excess", "State"], trows))
        return _resp(app, s, "New Inventory", "".join(parts), "/new-inventory")

    @app.get("/production")
    def production(app, req):
        s = req.session
        app.require(s, "workspace.view")
        commits = _conn(app).execute(
            "SELECT * FROM supply_commitment WHERE store_scope=? ORDER BY created_at", (s.scope,)).fetchall()
        rows = []
        for c in commits:
            proposed = c["lifecycle_status"] in ("proposed",)
            rows.append([esc(c["unit_or_order_id"]), esc(c["commitment_type"]), esc(c["combination_id"]),
                         safe(badge("pending" if proposed else "completed",
                                    "Proposed (not yet Supply)" if proposed else c["lifecycle_status"]))])
        recon = _conn(app).execute(
            "SELECT outcome,COUNT(*) n FROM commitment_reconciliation_result GROUP BY outcome").fetchall()
        rsum = ", ".join(f"{esc(r['outcome'])}: {r['n']}" for r in recon) or "none"
        body = ('<div class="card"><p>A <strong>proposal</strong> is shown distinctly from '
                '<strong>committed</strong> Supply; the same unit or order never appears as multiple '
                f'qualifying Supply effects. Reconciliation outcomes: {esc(rsum)}.</p></div>'
                + table(["Unit / Order", "Type", "Combination", "State"], rows))
        return _resp(app, s, "Production & Supply", body, "/production")

    @app.get("/service-loaner")
    def service_loaner(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.intelligence import build_intelligence
        intel = build_intelligence(_conn(app), s.scope, app.prefs, app.stack.clock)
        try:
            add_n = max(0, min(20, int(req.q("add") or 0)))
        except (TypeError, ValueError):
            add_n = 0
        # The certified ADD ranking is the only candidate computation on the default page.
        body = _loaner_command_body(app, s, intel, None, add_n)
        flash, s.flash = s.flash, None
        return Response(page("Service Loaners", body, ctx=app.ctx(s), active_path="/service-loaner",
                             flash=flash, wide=True, hide_title=True))

    @app.get("/service-loaner/unit/{unit_id}")
    def service_loaner_unit(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.intelligence import build_intelligence
        intel = build_intelligence(_conn(app), s.scope, app.prefs, app.stack.clock)
        u = next((x for x in intel.units if x.id == req.params["unit_id"]), None)
        if u is None:
            return app._safe_page(s, "Not found", "That loaner unit is not in the active fleet.", 404)
        age = f"{u.age_days} days" if u.age_days is not None else "not resolved (data-quality condition)"
        mi = f"{u.mileage:,} mi" if u.mileage_available else "not reported (data-quality condition)"
        facts = kv([("VIN", u.vin), ("Model", u.model or "—"),
                    ("Authoritative in-service date", u.in_service_date or "—"),
                    ("In-service age", age), ("Last checkout mileage", mi),
                    ("Membership state", u.membership_state), ("Rental state", u.rental_state or "—")])
        model_ev = next((m for m in intel.models if m.model == u.model), None)
        ev = ""
        if model_ev:
            headline = next((c for c in model_ev.resale_years if c.gated), model_ev.resale_model)
            ev = ('<div class="card"><h3>Source-backed evidence for this model</h3>'
                  '<div style="font-size:13px;color:var(--muted)">Historical turn</div>'
                  + (dist_row(f"{u.model} · days to sell", model_ev.dts, scale_max=float(model_ev.dts.maximum or 1),
                              unit=" days") if model_ev.dts and model_ev.dts.count else '<p class="muted">No usable turn sample.</p>')
                  + '<div style="font-size:13px;color:var(--muted);margin-top:6px">Historical recorded resale</div>'
                  + _cohort_line(headline) + '</div>')
        else:
            ev = '<div class="card"><p class="muted">No source-backed resale evidence for this unit\'s model yet.</p></div>'
        flags = ("".join(f'<p>{chip("skip", f)}</p>' for f in u.quality_flags)) or '<p class="muted">No data-quality gaps.</p>'
        blocked = (not u.in_service_date) or (not u.mileage_available)
        dating = _dating_form(s, u, blocked)
        body = (f'<p><a href="/service-loaner">← Service Loaners</a></p>'
                f'<div class="card"><h2>{esc(u.model or "Loaner unit")} — VIN …{esc(u.vin[-6:])}</h2>{facts}</div>'
                f'<div class="card"><h3>Data quality</h3>{flags}</div>' + dating + ev
                + '<p class="muted">Operational + source-backed evidence only. No economic retire/hold/release-by '
                'call is produced — those remain Undetermined until Phase-4 inputs are authoritative.</p>')
        fl, s.flash = getattr(s, "flash", None), None
        return Response(page(f"Loaner {u.vin[-6:]}", body, ctx=app.ctx(s), active_path="/service-loaner",
                             flash=fl, wide=True, hide_title=True))

    @app.post("/service-loaner/unit/{unit_id}/dating")
    def service_loaner_unit_dating(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.snapshot import _clean_in_service_date
        store, dating = _loaner_store(app)
        uid = req.params["unit_id"]
        unit = store.get_unit(uid)
        if unit is None or unit.store_scope != s.scope:
            return app._safe_page(s, "Not found", "That loaner unit is not in this store.", 404)
        did = []
        isd = _clean_in_service_date(req.f("in_service_date", ""))
        if isd:
            if unit.accepted_in_service_date:
                if isd != unit.accepted_in_service_date:
                    dating.correct_in_service_date(unit, isd, source="operator_entry")  # preserves prior lineage
                    did.append("in-service date corrected")
            else:
                dating.resolve_in_service_date(unit, [{"value": isd, "source": "operator_entry",
                                                       "authority": "verified"}])
                did.append("in-service date resolved")
        raw_mi = (req.f("last_checkout_mileage", "") or "").strip()
        if raw_mi != "":
            m = dating.record_mileage(store.get_unit(uid), raw_mi, source="operator_entry")
            if m.value_kind in ("value", "zero"):
                with store.conn:
                    store.set_unit_field(store.conn, uid, last_checkout_mileage=str(m.value))
                did.append("mileage recorded")
        s.flash = ("Recorded authoritative " + " · ".join(did) + " (verified; history preserved)."
                   if did else "Nothing recorded — enter a verified in-service date and/or a whole-mile value.")
        return Response.redirect(f"/service-loaner/unit/{uid}")

    @app.get("/service-loaner/model/{model}")
    def service_loaner_model(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.intelligence import build_intelligence
        intel = build_intelligence(_conn(app), s.scope, app.prefs, app.stack.clock)
        mi = next((m for m in intel.models if m.model == req.params["model"].upper()), None)
        if mi is None:
            return app._safe_page(s, "Not found", "No source-backed evidence for that model.", 404)
        years = "".join('<div style="margin:8px 0">' + _cohort_line(c) + '</div>' for c in mi.resale_years) \
            or '<p class="muted">No model-year cohort meets the sample gate.</p>'
        gross_years = "".join('<div style="margin:8px 0">' + _cohort_line(c) + '</div>' for c in mi.gross_years) \
            or '<p class="muted">No model-year gross cohort meets the sample gate.</p>'
        body = (f'<p><a href="/service-loaner">← Service Loaners</a></p>'
                f'<div class="card"><h2>{esc(mi.model)} — resale what-if (historical evidence)</h2>'
                '<p class="muted">Read-only comparison across model-years using recorded prices. Each cohort '
                'exposes its definition, n, as-of and observation recency. No current-value estimate, no '
                'inflation adjustment, no economics.</p></div>'
                + _model_intel_card(mi)
                + f'<div class="card"><h3>Recorded resale by model-year</h3>{years}</div>'
                + f'<div class="card"><h3>Recorded gross by model-year</h3>{gross_years}</div>')
        return Response(page(f"{mi.model} resale", body, ctx=app.ctx(s), active_path="/service-loaner",
                             flash=None, wide=True, hide_title=True))

    @app.post("/service-loaner/desired-fleet")
    def set_desired(app, req):
        from ...loaner.loaner_cockpit import MetaPrefs, set_desired_fleet
        s = req.session
        app.require(s, "workspace.view")
        raw = (req.form.get("desired") or "").strip()
        try:
            n = int(raw) if raw else None
            if n is not None and n < 0:
                n = None
        except ValueError:
            n = None
        set_desired_fleet(MetaPrefs(app.prefs, s.scope), n)
        s.flash = "Desired Service-Loaner fleet size saved." if n is not None else "Desired fleet size cleared."
        return Response.redirect("/service-loaner")

    @app.post("/service-loaner/{unit_id}/used-cars")
    def confirm_used_cars(app, req):
        s = req.session
        u = app.p9.p8.p7.p6.store.get_unit(req.params["unit_id"])
        if u is None:
            return app._safe_page(s, "Not found", "That loaner unit is not available.", 404)
        # one simple confirmation, no checklist — routed through the real Phase 6 service
        app.p9.p8.p7.p6.retirement.confirm_used_cars_receipt(s.principal_id, s.scope, u)
        s.flash = "Used Cars receipt confirmed (one action, no checklist)."
        return Response.redirect("/service-loaner")

    @app.get("/executive-demo")
    def executive_demo(app, req):
        s = req.session
        app.require(s, "workspace.view")
        plans = _conn(app).execute(
            "SELECT * FROM executive_demo_portfolio_plan WHERE store_scope=? ORDER BY issued_time DESC",
            (s.scope,)).fetchall()
        body_parts = ['<div class="card"><p>Best Overall shows <strong>why</strong> the chosen candidate '
                      'wins; tradeoffs stay visible; necessary sacrifice is labeled; New Retail opportunity '
                      'cost and Executive Demo benefit stay separate. Designation approval is not active '
                      'membership. Executive Demo is separate from Service Loaner.</p></div>']
        if not plans:
            body_parts.append(empty("No Executive Demo portfolio plan issued yet."))
        else:
            p = plans[0]
            best = json.loads(p["best_overall"] or "{}").get("pick", {})
            tradeoffs = json.loads(p["tradeoffs"] or "[]")
            sacrifices = json.loads(p["sacrifices"] or "[]")
            body_parts.append('<h2>Best Overall recommendation</h2>')
            body_parts.append('<div class="card">' + kv([
                ("Chosen candidate", best.get("vehicle_unit_id", "—")),
                ("Why it wins", safe("Highest full-objective score: " + esc(json.dumps(best.get("tradeoffs", {}))))),
                ("Need", p["need"])]) + '</div>')
            trows = [[esc(t.get("vehicle_unit_id")), esc(t.get("tradeoffs", {}).get("executive_demo_benefit")),
                      esc(t.get("tradeoffs", {}).get("new_retail_opportunity_cost")),
                      esc(t.get("tradeoffs", {}).get("portfolio_fit"))] for t in tradeoffs]
            body_parts.append('<h2>Candidate tradeoffs</h2>')
            body_parts.append(table(["Candidate", "Demo benefit", "NR opportunity cost", "Portfolio fit"], trows))
            if sacrifices:
                body_parts.append('<div class="card">' + badge("attention", "Necessary sacrifice") +
                                  " " + esc(json.dumps(sacrifices)) + '</div>')
        # Retirement disposition — governed operator confirmations routed to the real Phase 7 service.
        eunits = _conn(app).execute(
            "SELECT * FROM executive_demo_unit WHERE store_scope=? ORDER BY created_at", (s.scope,)).fetchall()
        drows = []
        for u in eunits:
            st = u["membership_state"]
            if st == "RETIRED":
                idem = "idem-" + secrets.token_urlsafe(8)
                act = (f'<form class="mut" method="post" action="/executive-demo/{esc(u["id"])}/return-to-retail">'
                       f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                       f'<input type=hidden name=_idem value="{esc(idem)}">'
                       '<button type=submit>Confirm return to New Retail</button></form>')
            elif st == "AWAITING_USED_CARS_RECEIPT":
                idem = "idem-" + secrets.token_urlsafe(8)
                act = (f'<form class="mut" method="post" action="/executive-demo/{esc(u["id"])}/used-cars">'
                       f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                       f'<input type=hidden name=_idem value="{esc(idem)}">'
                       '<button type=submit>Confirm Used Cars receipt</button></form>')
            elif st in ("RETURNED_TO_NEW_RETAIL", "USED_CARS_RECEIVED"):
                act = badge("completed", st.replace("_", " ").title())
            else:
                act = '<span class="muted">—</span>'
            actionable = st in ("RETIRED", "AWAITING_USED_CARS_RECEIPT")
            drows.append([esc(u["vin"] or u["id"]),
                          safe(badge("attention" if actionable else "ok", st)), safe(act)])
        if drows:
            body_parts.append('<h2>Retirement disposition</h2>')
            body_parts.append('<div class="card"><p>After retirement, confirm the disposition through the '
                              'authoritative Phase 7 service. Return to New Retail restores Current Supply '
                              'exactly once; Used Cars receipt is a single confirmation (no checklist). '
                              'Each is governed, scoped, idempotent, and audited.</p></div>')
            body_parts.append(table(["VIN", "State", "Confirmation"], drows))
        return _resp(app, s, "Executive Demos", "".join(body_parts), "/executive-demo")

    @app.post("/executive-demo/{unit_id}/return-to-retail")
    def confirm_execdemo_return(app, req):
        s = req.session
        u = app.p9.p8.p7.store.get_unit(req.params["unit_id"])
        if u is None or u.store_scope != s.scope:
            return app._safe_page(s, "Not found", "That Executive Demo unit is not in your store.", 404)
        # governed, scoped, idempotent, audited — routed through the real Phase 7 service (no table write here)
        app.p9.p8.p7.retirement.return_to_new_retail(s.principal_id, s.scope, u)
        s.flash = "Return to New Retail confirmed through the authoritative Phase 7 service."
        return Response.redirect("/executive-demo")

    @app.post("/executive-demo/{unit_id}/used-cars")
    def confirm_execdemo_used_cars(app, req):
        s = req.session
        u = app.p9.p8.p7.store.get_unit(req.params["unit_id"])
        if u is None or u.store_scope != s.scope:
            return app._safe_page(s, "Not found", "That Executive Demo unit is not in your store.", 404)
        # one simple confirmation, no checklist — routed through the real Phase 7 service
        app.p9.p8.p7.retirement.confirm_used_cars_receipt(s.principal_id, s.scope, u,
                                                          correlation_id=req.correlation_id)
        s.flash = "Used Cars receipt confirmed (one action, no checklist)."
        return Response.redirect("/executive-demo")


def _resp(app, s, title, body, active):
    flash, s.flash = s.flash, None
    app.prefs.set_context(s.principal_id, last_domain=title, last_scope=s.scope)
    return Response(page(title, body, ctx=app.ctx(s), active_path=active, flash=flash))
