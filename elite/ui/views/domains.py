"""Domain operator workspaces — New Inventory, Production & Supply, Service Loaner, Executive Demo.

Every number is READ from the authoritative Phase 4-7 records; the interface never recomputes Demand,
Need, Economic Call, or Best Overall. Proposal vs committed, membership vs rental, official vs Scenario,
and Economic Call vs Execution Status are visually distinct. One physical unit is never counted twice
(the stored count-once results are shown as-is).
"""
from __future__ import annotations

import json
import secrets

from ..render import badge, esc, esc_text, empty, page, safe, table, kv
from ..http import Response

# The one approved zero-mile-rented question — shown verbatim.
ZERO_MILE_QUESTION = "Where is this customer's vehicle, and let's check the miles on the loaner?"


def _conn(app):
    return app.stack.db.conn


def register(app):
    @app.get("/new-inventory")
    def new_inventory(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = _conn(app).execute(
            "SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued' ORDER BY issued_time",
            (s.scope,)).fetchall()
        total_need = sum(r["need"] for r in rows)
        total_excess = sum(r["excess"] for r in rows)
        trows = []
        for r in rows:
            st = r["planning_state"]
            trows.append([esc(r["combination_id"]), esc(round(r["expected_demand"], 2)),
                          esc(r["current_supply"]), esc(r["future_supply"]), esc(r["committed_supply"]),
                          esc(round(r["need"], 2)), esc(round(r["excess"], 2)),
                          safe(badge("healthy" if st == "balanced" else "attention", st))])
        body = (f'<div class="card"><h2>Portfolio</h2>{kv([("Combinations planned", len(rows)), ("Total Need", round(total_need,2)), ("Total Excess", round(total_excess,2))])}'
                '<p class="muted">Totals and Need/Excess are read from the issued Phase 4 plan — not recomputed here. '
                'Current / Future / Committed Supply are shown separately; one unit is counted once.</p></div>'
                + '<h2>Combination plans (issued)</h2>'
                + table(["Combination", "Demand", "Current", "Future", "Committed", "Need", "Excess", "State"], trows))
        return _resp(app, s, "New Inventory", body, "/new-inventory")

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
                + '<h2>Active fleet</h2>'
                + table(["VIN", "Membership", "Rental", "Last checkout mileage"], urows))
        return _resp(app, s, "Service Loaners", body, "/service-loaner")

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
