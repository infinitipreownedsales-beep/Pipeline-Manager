"""Governance operator screens — Scenarios, Calibration, Authority, Audit, Exceptions, Readiness,
operational-control summaries.

Built on the Phase 9 output slices + Phase 8 Calibration records + the Phase 1 authority store. Scenarios
stay visibly hypothetical; sharing is not approval; Calibration approval is distinct from activation and a
scheduled activation is shown as future-effective; authority uses the Phase 1 records with visible grant
chains and immediate revocation; Audit is read-only with correlated traces and missing-event exceptions;
exception dismissal requires authority + reason and never resolves the source; readiness is evidence-based
and never deploys; summaries reconcile to source items.
"""
from __future__ import annotations

import json
import secrets

from ...govern import output
from ..render import badge, esc, empty, page, safe, table, kv
from ..http import Response


def _resp(app, s, title, body, active):
    flash, s.flash = s.flash, None
    return Response(page(title, body, ctx=app.ctx(s), active_path=active, flash=flash))


def register(app):
    # ---- Scenarios --------------------------------------------------------
    @app.get("/scenarios")
    def scenarios(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for sc in output.scenario_admin_slice(app.store):
            rows.append([safe(f'<a href="/scenario/{esc(sc["scenario_admin_id"])}">{esc(sc["scenario_id"])}</a>'),
                         esc(sc["owner"]), esc(sc["domain"]),
                         safe(badge("scenario", sc["status"])), esc(sc["expiration"] or "—")])
        body = ('<div class="card"><p>Scenarios are <strong>hypothetical</strong>. Shared does not mean '
                'approved; approved-for-discussion does not mean official; a promotion request changes '
                'nothing directly.</p></div>' + table(["Scenario", "Owner", "Domain", "Status", "Expires"], rows))
        return _resp(app, s, "Scenarios", body, "/scenarios")

    @app.get("/scenario/{id}")
    def scenario_detail(app, req):
        s = req.session
        cmp = output.scenario_comparison(app.store, req.params["id"])
        if cmp is None:
            return app._safe_page(s, "Not found", "That scenario is not available.", 404)
        overrides = cmp["overrides"]
        orows = [[esc(k), esc(v), safe(badge("scenario", "override"))] for k, v in overrides.items()]
        body = (f'<div class="card">{badge("scenario","Hypothetical — not official")} '
                f'{kv([("Official baseline", cmp["official_baseline_ref"] or "—"), ("Status", cmp["status"])])}</div>'
                '<h2>Overrides vs official baseline</h2>'
                + table(["Field", "Scenario value", ""], orows))
        return _resp(app, s, "Scenario comparison", body, "/scenarios")

    # ---- Calibration ------------------------------------------------------
    @app.get("/calibration")
    def calibration(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for st in ("PROPOSED", "VALIDATION_REQUIRED", "VALIDATED", "APPROVED", "SCHEDULED", "ACTIVATED"):
            for c in app.store.conn.execute("SELECT * FROM calibration_proposal WHERE review_state=? ORDER BY "
                                            "created_at", (st,)).fetchall():
                review = app.p9.calibration_ws.review(c["id"])
                scheduled = review["scheduled"]
                state_badge = badge("pending", "Scheduled — future-effective") if scheduled else \
                    badge("completed" if st == "ACTIVATED" else "attention", st)
                rows.append([safe(f'<a href="/calibration/{esc(c["id"])}">{esc(c["target_type"])}</a>'),
                             esc(review["current_version"] or "—"),
                             esc(", ".join(review["cohort_improvements"]) or "—"),
                             esc(", ".join(review["cohort_regressions"]) or "—"), safe(state_badge)])
        body = ('<div class="card"><p>Proposal, validation, approval, activation, and rollback are separate '
                'steps. Approval is not activation. A policy target routes to a policy review. Prior '
                'Predictions are never changed.</p></div>'
                + table(["Target", "Current version", "Improved cohorts", "Worsened cohorts", "State"], rows))
        return _resp(app, s, "Learning & Calibration", body, "/calibration")

    @app.get("/calibration/{id}")
    def calibration_detail(app, req):
        s = req.session
        review = app.p9.calibration_ws.review(req.params["id"])
        if review is None:
            return app._safe_page(s, "Not found", "That calibration is not available.", 404)
        act = review["activation"]
        body = '<div class="card">' + kv([
            ("Target", review["target_type"]), ("Current version", review["current_version"] or "—"),
            ("Proposed change", safe(esc(json.dumps(review["proposed_change"])))),
            ("Review state", review["review_state"]),
            ("Approval", review["approval_state"] or "—"),
            ("Activation", safe(badge("pending", "Scheduled (future-effective)") if review["scheduled"]
                                else (badge("completed", "Activated") if act else badge("attention", "Not activated")))),
            ("Learning signals", ", ".join(review["learning_signals"]) or "—"),
            ("Improved cohorts", ", ".join(review["cohort_improvements"]) or "—"),
            ("Worsened cohorts", ", ".join(review["cohort_regressions"]) or "—"),
            ("Leakage checked", "yes" if review["leakage_checked"] else "no"),
            ("Policy review recommendation", review["policy_review_recommendation"] or "—")]) + '</div>'
        return _resp(app, s, "Calibration review", body, "/calibration")

    # ---- Authority --------------------------------------------------------
    @app.get("/authority")
    def authority(app, req):
        s = req.session
        app.require(s, "authority.view")
        from ...clock import to_utc_iso
        now = to_utc_iso(app.stack.clock.now())
        rows = []
        for d in output.authority_admin_slice(app.store):
            g = app.store.conn.execute("SELECT authority,active FROM capability_grant WHERE id=?",
                                       (d["grant_ref"],)).fetchone()
            chain = g["authority"] if g else "—"
            expired = bool(d["expiration"]) and d["expiration"] <= now
            active = d["active"] and (g is not None) and g["active"] and not expired
            rows.append([esc(d["delegate"]), esc(d["capability"]), esc(d["scope"]),
                         safe(badge("ok" if active else "expired", "Active" if active else "Inactive / revoked")),
                         esc(chain), esc(d["expiration"] or "—")])
        idem = secrets.token_urlsafe(8)
        form = (f'<form class="card mut" method="post" action="/authority/delegate">'
                f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                '<label for=dg>Delegate to (operator id)</label><input id=dg name=delegate required>'
                '<label for=cap>Capability</label><input id=cap name=capability value="decision.approve" required>'
                '<label for=sc>Scope</label><input id=sc name=scope value="*" required>'
                '<div style="margin-top:8px"><button type=submit>Delegate authority</button></div></form>')
        body = ('<div class="card"><p>Authority uses the platform permission records. Delegation cannot '
                'exceed your own capability or scope; the grant chain is shown; revoked authority is '
                'inactive immediately.</p></div>'
                + table(["Delegate", "Capability", "Scope", "Status", "Grant chain", "Expires"], rows) + form)
        return _resp(app, s, "Authority", body, "/authority")

    @app.post("/authority/delegate")
    def do_delegate(app, req):
        s = req.session
        app.p9.authority.delegate(s.principal_id, s.scope, delegate=req.f("delegate"),
                                  capability=req.f("capability"), delegate_scope=req.f("scope", "*"),
                                  reason="operator delegation")
        s.flash = "Authority delegated (governed + audited)."
        return Response.redirect("/authority")

    # ---- Audit ------------------------------------------------------------
    @app.get("/audit")
    def audit(app, req):
        s = req.session
        corr = req.q("correlation_id")
        action = req.q("action")
        rows = output.audit_review_slice(app.p9.audit_admin, s.principal_id, s.scope,
                                         correlation_id=corr or None, action=action or None)
        trows = [[esc(r["actor"]), esc(r["action"]), safe(badge("completed" if r["result"] == "success"
                                                                else "failed", r["result"])),
                  esc(r["target_ref"]), esc(r["correlation_id"] or "—")] for r in rows]
        filt = ('<form class="mut" method="get" action="/audit"><label for=ca>Correlation ID</label>'
                f'<input id=ca name=correlation_id value="{esc(corr or "")}" style="max-width:280px">'
                '<button type=submit class=secondary>Trace</button></form>')
        body = ('<div class="card"><p>Audit events are <strong>read-only</strong> and immutable. Filter by '
                'correlation ID to see a correlated action as a trace.</p>' + filt + '</div>'
                + table(["Actor", "Action", "Result", "Target", "Correlation"], trows))
        return _resp(app, s, "Audit", body, "/audit")

    # ---- Exceptions -------------------------------------------------------
    @app.get("/exceptions")
    def exceptions(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for e in output.exception_queue_slice(app.store):
            idem = secrets.token_urlsafe(8)
            dism = (f'<form class="mut" method="post" action="/exception/{esc(e["exception_id"])}/dismiss">'
                    f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                    '<input name=reason placeholder="reason (required)" style="max-width:200px" required> '
                    '<button type=submit class=secondary>Dismiss</button></form>')
            rows.append([safe(badge("attention", e["queue"])), esc(e["domain"] or "—"),
                         esc(e["source_type"]), esc(e["source_ref"]), esc(e["priority"]), safe(dism)])
        body = ('<div class="card"><p>Each item links to its authoritative source. Closing or dismissing a '
                'queue item does <strong>not</strong> resolve the source; dismissal requires a reason.</p></div>'
                + table(["Queue", "Domain", "Source type", "Source", "Priority", ""], rows))
        return _resp(app, s, "Exceptions", body, "/exceptions")

    @app.post("/exception/{id}/dismiss")
    def do_dismiss(app, req):
        s = req.session
        item = app.store.get_op_exception(req.params["id"])
        if item is None:
            return app._safe_page(s, "Not found", "That exception is not available.", 404)
        app.p9.queues.dismiss(s.principal_id, s.scope, item, reason=req.f("reason", ""))
        s.flash = "Exception dismissed (the source record is unchanged)."
        return Response.redirect("/exceptions")

    # ---- Readiness --------------------------------------------------------
    @app.get("/readiness")
    def readiness(app, req):
        s = req.session
        app.require(s, "workspace.view")
        rows = []
        for domain in ("new_inventory", "production_workflows", "service_loaner", "executive_demo",
                       "learning_calibration", "governance_foundation"):
            r = output.readiness_slice(app.store, domain)
            if r is None:
                rows.append([esc(domain), safe(badge("unresolved", "Not assessed")), "—", "—"])
                continue
            cls = r["classification"]
            kind = {"READY": "healthy", "READY_WITH_WARNINGS": "attention", "NOT_READY": "blocked"}.get(cls, "unresolved")
            rows.append([esc(domain), safe(badge(kind, cls)),
                         esc("; ".join(r["blockers"]) or "—"), esc("; ".join(r["warnings"]) or "—")])
        body = ('<div class="card"><p>Readiness is evidence-based and does <strong>not</strong> deploy '
                'anything. Missing required policy or authority blocks readiness; passing synthetic tests '
                'alone is not fully ready.</p></div>'
                + table(["Domain", "Classification", "Blockers", "Warnings"], rows))
        return _resp(app, s, "Readiness", body, "/readiness")

    # ---- Operational-control summaries ------------------------------------
    @app.get("/summaries")
    def summaries(app, req):
        s = req.session
        app.require(s, "workspace.view")
        summary = app.p9.summaries.summarize(scope=s.scope)
        rows = [[esc(k.replace("_", " ")), esc(v)] for k, v in summary["counts"].items()]
        body = (f'<div class="card"><p>Counts reconcile to {summary["total_items"]} source workspace items '
                'in this store. Drill into the inbox for the exact records.</p></div>'
                + table(["Category", "Count"], rows))
        return _resp(app, s, "Operational control", body, "/")
