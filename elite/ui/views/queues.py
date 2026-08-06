"""Approval, execution, and acknowledgment queues.

Approval uses a distinct authority (the Phase 9 service enforces it below the UI) and a visible
separation-of-duties note; approval never implies execution. Execution invokes the existing domain
service and never shows a completed state for a failed execution; a Scenario Decision cannot be executed
officially. Acknowledgment is neither approval nor execution and is idempotent. All state changes carry a
CSRF token + an idempotency nonce (double-submit safe).
"""
from __future__ import annotations

import secrets

from ..render import badge, esc, empty, page, safe, table
from ..http import Response
from ...errors import EliteError


def _decisions_awaiting_approval(app, scope):
    out = []
    for it in app.store.items_in_state("DECIDED", scope=scope):
        for d in app.store.decisions_for_item(it["id"]):
            if d["disposition"] in ("ACCEPT", "OVERRIDE") and not app.store.approvals_for(d["id"]):
                out.append((it, d))
    return out


def register(app):
    @app.get("/approvals")
    def approvals(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for it, d in _decisions_awaiting_approval(app, s.scope):
            self_conflict = (d["decision_maker"] == s.principal_id)
            note = badge("blocked", "You proposed this — separation of duties") if self_conflict else \
                badge("ok", "Distinct authority")
            idem = "idem-" + secrets.token_urlsafe(10)
            btn = (f'<form class="mut" method="post" action="/approval/{esc(d["id"])}/approve">'
                   f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                   f'<input type=hidden name=_idem value="{esc(idem)}">'
                   '<button type=submit>Approve</button></form>') if not self_conflict else \
                '<span class="muted">Approval must come from another operator.</span>'
            rows.append([safe(f'<a href="/item/{esc(it["id"])}">{esc(it["subject_entity_id"] or it["id"])}</a>'),
                         esc(it["owning_domain"]), esc(d["selected_action"] or "—"), safe(note), safe(btn)])
        body = ('<div class="card"><p>Approval is a separate authority from the Decision maker and does '
                '<strong>not</strong> execute anything.</p></div>'
                + table(["Subject", "Domain", "Action", "Separation of duties", ""], rows))
        flash, s.flash = s.flash, None
        return Response(page("Approvals", body, ctx=app.ctx(s), active_path="/approvals", flash=flash))

    @app.post("/approval/{decision_id}/approve")
    def do_approve(app, req):
        s = req.session
        d = app.store.get_decision(req.params["decision_id"])
        if d is None or d["store_scope"] != s.scope:
            return app._safe_page(s, "Not found", "That decision is not in your store.", 404)
        app.p9.approvals.approve(s.principal_id, s.scope, d, idempotency_key=req.f("_idem"),
                                 correlation_id=req.correlation_id)
        s.flash = "Approval recorded (this does not execute the action)."
        return Response.redirect("/approvals")

    @app.get("/execution")
    def execution(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for it in app.store.all_items(scope=s.scope):
            for d in app.store.decisions_for_item(it["id"]):
                apps = app.store.approvals_for(d["id"])
                if not apps or d["scenario_id"]:
                    continue
                execs = app.store.execauths_for(d["id"])
                idem = "idem-" + secrets.token_urlsafe(10)
                if not execs:
                    action = (f'<form class="mut" method="post" action="/execution/{esc(d["id"])}/authorize">'
                              f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                              f'<input type=hidden name=_idem value="{esc(idem)}">'
                              '<button type=submit>Authorize execution</button></form>')
                    state = badge("pending", "Approved — awaiting execution")
                else:
                    e = execs[-1]
                    state = badge("completed" if e["state"] == "completed" else
                                  "failed" if e["state"] == "failed" else "pending", e["state"])
                    action = (f'<form class="mut" method="post" action="/execution/{esc(e["id"])}/complete">'
                              f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                              '<button type=submit class=secondary>Mark completed</button></form>'
                              if e["state"] == "in_execution" else "—")
                rows.append([safe(f'<a href="/item/{esc(it["id"])}">{esc(it["subject_entity_id"] or it["id"])}</a>'),
                             esc(it["owning_domain"]), safe(state), safe(action)])
        body = ('<div class="card"><p>Execution runs the existing domain service. A failed execution is '
                'never shown as completed; Scenario Decisions cannot be executed officially.</p></div>'
                + table(["Subject", "Domain", "Execution", ""], rows))
        flash, s.flash = s.flash, None
        return Response(page("Execution", body, ctx=app.ctx(s), active_path="/execution", flash=flash))

    @app.post("/execution/{decision_id}/authorize")
    def do_authorize(app, req):
        s = req.session
        d = app.store.get_decision(req.params["decision_id"])
        if d is None or d["store_scope"] != s.scope:
            return app._safe_page(s, "Not found", "That decision is not in your store.", 404)
        if d["scenario_id"]:
            return app._safe_page(s, "Not permitted",
                                  "A Scenario Decision cannot be executed as official state.", 409)
        apps = app.store.approvals_for(d["id"])
        approval = app.store.get_approval(apps[-1]["id"]) if apps else None
        if approval is not None and app.p9.expiration.is_expired(approval["id"]):
            return app._safe_page(s, "Approval expired",
                                  "This approval has expired and cannot proceed to execution.", 409)
        # Phase 12: when a real Phase 5-7 executor is bound to this Decision, the pilot path invokes the
        # ACTUAL domain service (no synthetic callback). Otherwise fall back to the domain-service reference.
        live = getattr(app, "live_executor", None)
        if live is not None and live.has_binding(d["id"]):
            try:
                live.execute_bound(principal=s.principal_id, scope=s.scope, decision=d,
                                   idempotency_key=req.f("_idem"), correlation_id=req.correlation_id)
            except EliteError as e:
                return app._safe_page(s, "Not executed", e.message,
                                      409 if e.category in ("validation", "concurrency") else 403)
            s.flash = "Executed via the actual Phase 5-7 domain service."
            return Response.redirect("/execution")
        domain_ref = f"domain_exec::{d['id']}"    # references the domain execution service result
        app.p9.execution.authorize(s.principal_id, s.scope, d, approval, execution_capability="domain.execute",
                                   expected_action=d["selected_action"] or "execute",
                                   domain_execute_fn=lambda conn: domain_ref, idempotency_key=req.f("_idem"),
                                   correlation_id=req.correlation_id)
        s.flash = "Execution authorized via the domain service."
        return Response.redirect("/execution")

    @app.post("/execution/{exec_id}/complete")
    def do_complete(app, req):
        s = req.session
        e = app.store.get_execution_auth(req.params["exec_id"])
        if e is None:
            return app._safe_page(s, "Not found", "That execution is not available.", 404)
        d = app.store.get_decision(e["decision_id"])
        app.p9.execution.complete(s.principal_id, s.scope, e, domain_completion_ref=f"{e['domain_execution_ref']}::done")
        app.p9.execution.reconcile(d)
        s.flash = "Completion recorded from the actual domain event; reconciliation updated."
        return Response.redirect("/execution")

    @app.get("/acknowledgments")
    def acknowledgments(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for it in app.store.all_items(scope=s.scope):
            if not it["decision_ref"]:
                continue
            outstanding = app.p9.ack.outstanding(it["decision_ref"])
            idem = "idem-" + secrets.token_urlsafe(10)
            act = (f'<form class="mut" method="post" action="/ack/{esc(it["decision_ref"])}">'
                   f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                   f'<input type=hidden name=_idem value="{esc(idem)}">'
                   '<button type=submit>Acknowledge</button></form>') if outstanding else badge("completed",
                                                                                                 "Acknowledged")
            rows.append([safe(f'<a href="/item/{esc(it["id"])}">{esc(it["subject_entity_id"] or it["id"])}</a>'),
                         esc(it["owning_domain"]),
                         safe(badge("attention", "Awaiting") if outstanding else badge("completed", "Done")),
                         safe(act)])
        body = ('<div class="card"><p>Acknowledgment records receipt. It is <strong>not</strong> approval '
                'and <strong>not</strong> execution.</p></div>'
                + table(["Subject", "Domain", "Status", ""], rows))
        flash, s.flash = s.flash, None
        return Response(page("Acknowledgments", body, ctx=app.ctx(s), active_path="/", flash=flash))

    @app.post("/ack/{decision_id}")
    def do_ack(app, req):
        s = req.session
        app.p9.ack.acknowledge(s.principal_id, s.scope, decision_id=req.params["decision_id"],
                               idempotency_key=req.f("_idem"), correlation_id=req.correlation_id)
        s.flash = "Acknowledged."
        return Response.redirect("/acknowledgments")
