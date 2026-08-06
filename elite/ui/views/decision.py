"""The governed Decision-issuance experience.

Shows the exact recommendation revision, the presented alternatives, confidence/uncertainty, a rationale
field (blank allowed unless policy requires it), the required authority, expiration, Scenario status, and
a stale warning. Submission invokes the Phase 9 Decision service with a per-render idempotency nonce so a
double submit does not duplicate the Decision. Override requires a reason; a stale recommendation needs a
renewed review or an authorized override. Nothing here recomputes domain logic.
"""
from __future__ import annotations

import secrets

from ..render import badge, esc, page, safe
from ..http import Response

DISPOSITIONS = ["ACCEPT", "REJECT", "DEFER", "REQUEST_INFORMATION", "NO_ACTION", "OVERRIDE", "CANCEL"]


def register(app):
    @app.get("/item/{id}/decide")
    def decide_form(app, req):
        s = req.session
        app.require(s, "workspace.review")
        it = app.store.get_workspace_item(req.params["id"])
        if it is None or it["store_scope"] != s.scope:
            return app._safe_page(s, "Not found", "That item is not in your store.", 404)
        review = app.p9.workspace.review(it)
        stale_warn = ('<div class="err" role="alert">This recommendation is <strong>stale</strong>. '
                      'Renew review or choose <em>Override</em> with a reason.</div>' if it["stale"] else "")
        scen = badge("scenario", "Scenario — hypothetical only") if it["scenario_id"] else ""
        opts = "".join(f'<option value="{d}">{d.replace("_"," ").title()}</option>' for d in DISPOSITIONS)
        idem = "idem-" + secrets.token_urlsafe(12)
        fields = (f'<p>Recommendation <strong>{esc(it["recommendation_ref"])}</strong> '
                  f'(revision {esc(it["version"])}). {scen}</p>{stale_warn}'
                  '<label for=disp>Disposition</label>'
                  f'<select id=disp name=disposition required>{opts}</select>'
                  '<label for=act>Selected action</label><input id=act name=selected_action>'
                  '<label for=alts>Presented alternatives (comma-separated)</label>'
                  '<input id=alts name=alternatives value="A,B">'
                  '<label for=rat>Rationale (optional unless policy requires it)</label>'
                  '<textarea id=rat name=rationale rows=2></textarea>'
                  '<label for=ovr>Override reason (required only for Override)</label>'
                  '<input id=ovr name=override_reason>'
                  f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                  f'<input type=hidden name=_idem value="{esc(idem)}">')
        body = (f'<form class="card" method="post" action="/item/{esc(it["id"])}/decide">{fields}'
                '<div style="margin-top:10px"><button type=submit>Issue Decision</button> '
                f'<a href="/item/{esc(it["id"])}"><button type=button class=secondary>Cancel</button></a></div></form>')
        return Response(page("Issue a Decision", body, ctx=app.ctx(s), active_path="/"))

    @app.post("/item/{id}/decide")
    def do_decide(app, req):
        s = req.session
        it = app.store.get_workspace_item(req.params["id"])
        if it is None or it["store_scope"] != s.scope:
            return app._safe_page(s, "Not found", "That item is not in your store.", 404)
        disposition = req.f("disposition", "ACCEPT")
        alts = [a.strip() for a in (req.f("alternatives", "") or "").split(",") if a.strip()]
        app.p9.decisions.issue(
            s.principal_id, s.scope, it, disposition=disposition,
            selected_action=req.f("selected_action") or None, rationale=req.f("rationale") or None,
            presented_alternatives=alts, override_reason=req.f("override_reason") or None,
            idempotency_key=req.f("_idem"), correlation_id=req.correlation_id)
        s.flash = f"Decision recorded: {disposition}."
        return Response.redirect(f"/item/{it['id']}")
