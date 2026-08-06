"""Operator search across authoritative identifiers (scope-filtered).

Searches VIN / Vehicle Unit / Sellable Combination / workspace item / Decision / Scenario / correlation
id within the operator's store scope. Results link to authoritative detail; the search index is never
authoritative truth, and it never exposes records outside the operator's scope.
"""
from __future__ import annotations

from ..render import badge, esc, empty, page, safe, table
from ..http import Response


def register(app):
    @app.get("/search")
    def search(app, req):
        s = req.session
        app.require(s, "workspace.view")
        q = (req.q("q") or "").strip()
        results = []
        if q:
            conn = app.stack.db.conn
            # workspace items in scope
            for it in app.store.all_items(scope=s.scope):
                if q in (it["id"] or "") or q in (it["subject_entity_id"] or "") or q in (it["recommendation_ref"] or ""):
                    results.append(("Decision item", it["subject_entity_id"] or it["id"], f"/item/{it['id']}"))
            # scenarios in scope
            for r in conn.execute("SELECT id,scenario_id FROM scenario_administration WHERE store_scope=?",
                                  (s.scope,)).fetchall():
                if q in (r["scenario_id"] or "") or q in (r["id"] or ""):
                    results.append(("Scenario", r["scenario_id"], f"/scenario/{r['id']}"))
            # service loaner VIN in scope
            for r in conn.execute("SELECT vin FROM service_loaner_unit WHERE store_scope=?", (s.scope,)).fetchall():
                if r["vin"] and q in r["vin"]:
                    results.append(("Service Loaner VIN", r["vin"], "/service-loaner"))
        rows = [[esc(kind), esc(label), safe(f'<a href="{esc(href)}">open</a>')] for kind, label, href in results]
        form = ('<form class="card mut" method="get" action="/search">'
                f'<label for=q>Search VIN, Vehicle Unit, Combination, Decision, Scenario, correlation ID</label>'
                f'<input id=q name=q value="{esc(q)}" autofocus>'
                '<div style="margin-top:8px"><button type=submit>Search</button></div></form>')
        body = form + (table(["Type", "Identifier", ""], rows) if q else
                       '<p class="muted">Enter an identifier to search within this store.</p>')
        if q and not results:
            body = form + empty("No results in your store for that identifier.")
        flash, s.flash = s.flash, None
        return Response(page("Search", body, ctx=app.ctx(s), active_path="/", flash=flash))
