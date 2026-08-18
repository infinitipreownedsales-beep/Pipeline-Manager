"""Domain operator workspaces — New Inventory, Production & Supply, Service Loaner, Executive Demo.

Every number is READ from the authoritative Phase 4-7 records; the interface never recomputes Demand,
Need, Economic Call, or Best Overall. Proposal vs committed, membership vs rental, official vs Scenario,
and Economic Call vs Execution Status are visually distinct. One physical unit is never counted twice
(the stored count-once results are shown as-is).
"""
from __future__ import annotations

import json
import secrets

from ..render import badge, esc, esc_text, empty, page, safe, table, kv, form, bars, dist_row
from ..http import Response


def _planning_month(app):
    from ...clock import to_utc_iso
    return to_utc_iso(app.stack.clock.now())[:7]      # 'YYYY-MM'


def _preowned_evidence_card(app, s):
    """Read-only historical resale evidence for models in the active Service Loaner fleet.

    This is evidence only. It does not create ICV, Velocity, or IN / HOLD / OUT economics.
    """
    from ...loaner.preowned_evidence import build_preowned_evidence

    ev = build_preowned_evidence(_conn(app), s.scope)

    if not ev.fleet_models_resolved:
        return (
            '<div class="card"><h2>Preowned Market Evidence</h2>'
            '<p class="muted">Active Service Loaner model identity is not yet available from '
            'the authoritative fleet snapshot, so historical resale evidence cannot be matched safely.</p>'
            '</div>'
        )

    if not ev.retail_history_loaded:
        return (
            '<div class="card"><h2>Preowned Market Evidence</h2>'
            '<p class="muted">No completed preowned-history v3 import is available yet. '
            'No resale absorption estimate has been invented.</p></div>'
        )

    models = list(ev.models)
    # 1) Fleet composition — where is the current authoritative fleet concentrated?
    comp = bars([(m.model, m.active_units, f"{m.active_units} loaner(s)") for m in models],
                caption="Active Service Loaner fleet composition by model")
    composition = ('<h3>Current fleet composition</h3>'
                   '<p class="muted">Where the authoritative active fleet is concentrated by model.</p>' + comp)

    # 2) Historical Days-to-Sell distribution — how quickly, and how consistently, does each model resell?
    dscale = max([float(getattr(m.distribution, "maximum", 0) or 0)
                  for m in models if m.distribution] + [1.0])
    dist_rows = "".join(dist_row(m.model, m.distribution, scale_max=dscale)
                        for m in models if m.distribution and m.distribution.count)
    distribution = ""
    if dist_rows:
        distribution = ('<h3>Historical resale speed (Days to Sell)</h3>'
                        '<p class="muted">Median marker with the middle-50% (IQR) band and min/max, from '
                        'accepted preowned sales. Faster-selling models sit to the left.</p>' + dist_rows)

    # 3) Model-year absorption where the sample is defensible — how do model-years compare?
    myrows = [my for my in ev.model_years if my.defensible]
    under = [my for my in ev.model_years if not my.defensible]
    modelyear = ""
    if myrows:
        mtable = table(["Model-year", "Historical sales", "Usable DTS", "Median DTS"],
                       [[esc(f"{my.model} {my.year}"), esc(my.sales_count), esc(my.numeric_dts_count),
                         esc(f"{my.median_dts:g} days" if my.median_dts is not None else "?")] for my in myrows])
        note = (f'<p class="muted">{len(under)} additional model-year(s) had too small a sample to compare '
                'and are held back.</p>' if under else "")
        modelyear = ('<h3>Model-year resale absorption</h3>'
                     '<p class="muted">Only model-years with a defensible sample are compared.</p>' + mtable + note)

    # base per-model table retained as the auditable Proof detail
    proof = table(["Model", "Active loaners", "Historical sales", "Usable DTS", "Median DTS"],
                  [[esc(m.model), esc(m.active_units), esc(m.sales_count), esc(m.numeric_dts_count),
                    esc(f"{m.median_dts:g} days" if m.median_dts is not None else "?")] for m in models])
    asof = f' · as of {esc(ev.retail_received_at[:10])}' if ev.retail_received_at else ""

    return (
        '<div class="card"><h2>Preowned Market Evidence</h2>'
        f'<p class="muted">Source-backed dealership resale history for models in the authoritative Service '
        f'Loaner fleet{asof}. Evidence only.</p>'
        + composition + distribution + modelyear
        + '<h3>Proof — per-model detail</h3>' + proof
        + '<p class="muted">Historical absorption evidence only. It does not create ICV, Velocity, IN, HOLD, '
          'or OUT values. Economic Ideal Mix remains undetermined until the complete real per-unit economics '
          'are available.</p>'
        '</div>'
    )


def _ideal_mix_card(app, s):
    """Service Loaner ECONOMIC Ideal Mix summary: the three fleet counts (Current / Desired / Ideal) never
    conflated, the governed monthly placement requirement, and the IN/HOLD/OUT ranking when real per-unit
    economics are available. When economics are not loaded, it says so honestly (no fabricated mix)."""
    from ...loaner.loaner_cockpit import build_cockpit
    ck = build_cockpit(_conn(app), s.scope, app.prefs, _planning_month(app))
    ideal = ck.ideal_fleet if ck.economically_determined else "—"
    counts = kv([("Current fleet (authoritative)", ck.current_fleet),
                 ("Desired fleet (operator)", ck.desired_fleet if ck.desired_fleet is not None else "not set"),
                 ("Ideal fleet (economic optimum)", ideal),
                 ("Planning month", ck.planning_month)])
    req = ck.requirement
    req_html = ""
    if req and req.get("required") is not None:
        req_html = (f'<p class="callout">Monthly placement requirement in force: '
                    f'<strong>{esc(req["required"])}</strong> for {esc(ck.planning_month)}'
                    + (f' — {esc(req.get("reason"))}' if req.get("reason") else "")
                    + '. Any placement beyond the economic optimum is <strong>objective-driven</strong>, '
                    'not economically ideal, and can be met by IN/OUT rotation.</p>')
    mix_html = ""
    if ck.economically_determined and ck.mix is not None:
        rows = []
        order = {"IN": 0, "HOLD": 1, "OUT": 2, "WAIT": 3}
        for d in sorted(ck.mix.decisions.values(), key=lambda d: (order.get(d["action"], 9), -d["net"])):
            tag = "objective-driven" if d.get("objective_driven") else ""
            rows.append([safe(badge({"IN": "attention", "HOLD": "healthy", "OUT": "pending"}.get(d["action"], "ok"),
                                     d["action"] + (f" ({tag})" if tag else ""))),
                         esc(d.get("identity") or d.get("id")), esc(round(d["net"], 2)), esc(d.get("reason", ""))])
        mix_html = ('<h3>Recommended mix (IN / HOLD / OUT)</h3>'
                    + table(["Call", "Combination / unit", "Net economics", "Why"], rows))
        if ck.mix.future_stocking_need:
            mix_html += (f'<p class="muted">Future stocking need: {esc(ck.mix.future_stocking_need)} position(s) '
                         'left open — not filled with an economically inferior unit.</p>')
    note = f'<p class="muted">{esc(ck.note())}</p>' if ck.note() else ""
    setf = form("/service-loaner/desired-fleet",
                f'<label for=df>Desired fleet size (optional operational target)</label>'
                f'<input id=df name=desired type=number min=0 style="max-width:160px" '
                f'value="{esc(ck.desired_fleet if ck.desired_fleet is not None else "")}">',
                csrf=s.csrf_token, submit="Save desired fleet")
    return (f'<div class="card"><h2>Ideal Mix / Additions</h2>{counts}{req_html}{note}{mix_html}'
            f'<div style="margin-top:10px">{setf}</div></div>')

# The one approved zero-mile-rented question — shown verbatim.
ZERO_MILE_QUESTION = "Where is this customer's vehicle, and let's check the miles on the loaner?"


def _conn(app):
    return app.stack.db.conn


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
        units = _conn(app).execute(
            "SELECT * FROM service_loaner_unit WHERE store_scope=? ORDER BY created_at", (s.scope,)).fetchall()
        urows = []
        for u in units:
            urows.append([esc(u["vin"]), safe(badge("ok", u["membership_state"])),
                          safe(badge("attention" if u["current_rental_state"] == "rented" else "ok",
                                     u["current_rental_state"] or "—")),
                          esc(u["last_checkout_mileage"] if u["last_checkout_mileage"] is not None else "—")])
        alerts = _conn(app).execute(
            "SELECT a.* FROM service_loaner_monitoring_alert a JOIN service_loaner_unit u "
            "ON a.service_loaner_unit_id=u.id WHERE u.store_scope=? AND a.status='active' ORDER BY a.created_at",
            (s.scope,)).fetchall()
        alert_html = ""
        for a in alerts:
            alert_html += (f'<div class="callout" role="status">{badge("attention","Zero-mile rented alert")} '
                           f'<strong>{esc_text(a["prompt"])}</strong></div>')
        body = ('<div class="card"><p>Membership state and rental state are shown <strong>separately</strong>. '
                'Service Loaner is a separate domain from Executive Demo. The Economic Call does not change '
                'because execution is blocked.</p>' + alert_html + '</div>'
                + _preowned_evidence_card(app, s)
                + _ideal_mix_card(app, s)
                + '<h2>Active fleet</h2>'
                + table(["VIN", "Membership", "Rental", "Last checkout mileage"], urows))
        return _resp(app, s, "Service Loaners", body, "/service-loaner")

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
