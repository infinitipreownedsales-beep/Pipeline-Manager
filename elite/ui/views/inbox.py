"""Today / Decision Inbox + recommendation detail (Call / Why / Proof / Raw History).

The inbox is built from Phase 9 workspace records; counts reconcile to those source items. Scenario-only
and stale items are visually distinct. Detail reads authoritative domain records and never recomputes
domain logic; missing explanation stays unknown; official vs Scenario and current vs historical are
distinguishable.
"""
from __future__ import annotations

from ..render import badge, esc, empty, page, safe, table, kv
from ..http import Response

ATTENTION_STATES = {"READY_FOR_REVIEW", "UNDER_REVIEW", "AWAITING_INFORMATION", "UNRESOLVED",
                    "DECISION_PENDING", "DECIDED", "AWAITING_EXECUTION", "IN_EXECUTION", "FAILED", "STALE"}


def attention_count(app, session):
    return sum(1 for it in app.store.all_items(scope=session.scope)
               if it["workspace_state"] in ATTENTION_STATES or it["stale"])


def _row(it):
    state = it["workspace_state"]
    kind = "scenario" if it["scenario_id"] else ("stale" if it["stale"] else
            ("failed" if state == "FAILED" else "completed" if state == "COMPLETED" else "attention"))
    call = f'<a href="/item/{esc(it["id"])}">{esc(_call_text(state))}</a>'
    tags = badge("scenario", "Scenario") + " " if it["scenario_id"] else ""
    tags += badge("stale", "Stale") + " " if it["stale"] else ""
    return [safe(call), esc(it["subject_entity_id"] or "—"), esc(it["owning_domain"]),
            safe(badge(kind, state) + " " + tags), esc(it["priority"] or "normal"),
            esc(it["assigned_reviewer"] or "—"), esc(_next_action(state))]


def _call_text(state):
    return {"READY_FOR_REVIEW": "Review recommendation", "DECIDED": "Route for approval",
            "APPROVED": "Authorize execution", "AWAITING_EXECUTION": "Authorize execution",
            "IN_EXECUTION": "In execution", "COMPLETED": "Completed", "FAILED": "Execution failed",
            "STALE": "Renew review (stale)", "REJECTED": "Rejected", "DEFERRED": "Deferred",
            "AWAITING_INFORMATION": "Awaiting information"}.get(state, state)


def _next_action(state):
    return {"READY_FOR_REVIEW": "Issue Decision", "DECIDED": "Approve", "APPROVED": "Authorize execution",
            "AWAITING_EXECUTION": "Authorize execution", "IN_EXECUTION": "Complete", "STALE": "Renew / override",
            "FAILED": "Re-diagnose"}.get(state, "—")


def register(app):
    @app.get("/")
    def inbox(app, req):
        s = req.session
        app.require(s, "workspace.view")
        items = app.store.all_items(scope=s.scope)
        f_domain, f_status, f_priority = req.q("domain"), req.q("status"), req.q("priority")
        shown = [it for it in items
                 if (not f_domain or it["owning_domain"] == f_domain)
                 and (not f_status or it["workspace_state"] == f_status)
                 and (not f_priority or (it["priority"] or "normal") == f_priority)]
        rows = [_row(it) for it in shown]
        # counts reconcile to Phase 9 source items
        counts = {}
        for it in items:
            counts[it["workspace_state"]] = counts.get(it["workspace_state"], 0) + 1
        summary = " · ".join(f"{esc(k)}: {v}" for k, v in sorted(counts.items())) or "no items"
        filt = ('<form method="get" action="/" class="mut"><label for=fd>Domain</label>'
                f'<input id=fd name=domain value="{esc(f_domain or "")}" style="max-width:200px">'
                '<label for=fs>Status</label>'
                f'<input id=fs name=status value="{esc(f_status or "")}" style="max-width:200px">'
                '<button type=submit class=secondary>Filter</button></form>')
        body = (f'<div class="card"><strong>What needs attention right now.</strong>'
                f'<p class="muted">Totals (reconcile to Phase 9 workspace records): {summary}</p>{filt}</div>'
                + table(["Call", "Subject", "Domain", "Status", "Priority", "Owner", "Next action"], rows))
        app.prefs.set_context(s.principal_id, last_domain="inbox", last_scope=s.scope)
        flash, s.flash = s.flash, None
        return Response(page("Today", body, ctx=app.ctx(s), active_path="/", flash=flash))

    @app.get("/item/{id}")
    def detail(app, req):
        s = req.session
        app.require(s, "workspace.view")
        it = app.store.get_workspace_item(req.params["id"])
        if it is None or it["store_scope"] != s.scope:
            return app._safe_page(s, "Not found", "That item is not in your store.", 404)
        review = app.p9.workspace.review(it)
        official = "Scenario (hypothetical)" if it["scenario_id"] else "Official"
        decisions = app.store.decisions_for_item(it["id"])
        history = _raw_history(app, it, decisions)
        proof = kv([("Recommendation", it["recommendation_ref"] or "—"),
                    ("Economic Call", it["economic_call_ref"] or "—"),
                    ("Execution Status", it["execution_status_ref"] or "—"),
                    ("Accepted facts", ", ".join(review["applicable_facts"]) or "—"),
                    ("Applicable versions", ", ".join(f"{k}={v}" for k, v in review["applicable_versions"].items()) or "—")])
        why = "<p>" + esc(_call_text(it["workspace_state"])) + ".</p>"
        if not review["explanation_present"]:
            why += '<p class="muted">Additional reasoning: <em>unknown</em> (not recorded).</p>'
        badges = badge("scenario", "Scenario") if it["scenario_id"] else badge("attention", official)
        if it["stale"]:
            badges += " " + badge("stale", "Stale — renew review")
        actions = (f'<a href="/item/{esc(it["id"])}/decide"><button class=secondary>Issue a Decision</button></a>'
                   if it["workspace_state"] in ("READY_FOR_REVIEW", "STALE", "AWAITING_INFORMATION") else "")
        body = (f'<div class="card"><h2>Call</h2>{badges}<p>{esc(_call_text(it["workspace_state"]))}</p>{actions}</div>'
                f'<div class="card"><h2>Why</h2>{why}</div>'
                f'<div class="card"><h2>Proof</h2>{proof}</div>'
                f'<div class="card"><h2>Raw History</h2><p class="muted">Evidence trail ({official}).</p>{history}</div>')
        flash, s.flash = s.flash, None
        return Response(page(f"{it['owning_domain']} — {it['subject_entity_id'] or 'item'}", body,
                             ctx=app.ctx(s), active_path="/", flash=flash))


def _raw_history(app, it, decisions):
    events = [("Item opened", it["created_at"], f"workspace item {it['id']}")]
    for rev in app.store.workspace_revisions(it["id"]):
        events.append((f"Recommendation revised (rev {rev['revision_no']})", rev["at"],
                       f"prior rec {rev['recommendation_ref']}"))
    for d in decisions:
        events.append((f"Decision: {d['disposition']}", d["created_at"],
                       f"by {d['decision_maker']}" + (" (override)" if d["override"] else "")))
        for a in app.store.approvals_for(d["id"]):
            events.append(("Approval", a["created_at"], f"by {a['approving_principal']}"))
        for e in app.store.execauths_for(d["id"]):
            events.append((f"Execution {e['state']}", e["created_at"], f"domain ref {e['domain_execution_ref'] or '—'}"))
        for r in app.store.reconciliations_for(d["id"]):
            events.append((f"Reconciliation: {r['outcome']}", r["recorded_at"], r["detail"] or ""))
    lis = "".join(f"<li><strong>{esc(t)}</strong> — <span class=muted>{esc(when)}</span><br>{esc(what)}</li>"
                  for t, when, what in events)
    return f'<ol class="timeline">{lis}</ol>' if events else empty("No recorded evidence yet.")
