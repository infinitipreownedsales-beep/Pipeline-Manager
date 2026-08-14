"""Daily OPERATOR cockpit shell — the dealership-facing product.

This module owns the routes a GSM uses every day: the Pipeline Horizon home (`/`), the ordering / trade /
wholesale / demos / CTP entry surfaces, the Data control room, and a secondary Admin index that gathers the
governance / engineering screens so normal navigation never hits an engineering permission wall.

It reuses the certified New-Inventory records unchanged — no recompute, no schema change. Where a domain's
full workflow is not built yet, the operator surface is honest about what data exists rather than fabricating
functionality.
"""
from __future__ import annotations

import json

from ..render import ADMIN_NAV, badge, esc, page, safe, table, kv, empty
from ..http import Response
from .domains import _readable, _resp, _conn


def _model_of(readable):
    """First token of a readable identity ('QX65 8501 QBE/G' -> 'QX65')."""
    return (readable or "").split(" ", 1)[0] or "Other"


def register(app):
    @app.get("/")
    def pipeline_home(app, req):
        """Pipeline Horizon — the default landing screen. Whole dealership first: models collapsed, expand a
        model in place to reveal its combinations. Reads the certified issued plans (no recompute)."""
        s = req.session
        app.require(s, "workspace.view")
        app.ensure_inventory_published(s.scope)
        conn = _conn(app)
        rows = conn.execute(
            "SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued' ORDER BY id",
            (s.scope,)).fetchall()
        ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
            "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (s.scope,)).fetchall()}
        from ...newinv.publish import plan_call

        models = {}          # model -> list of (call_kind, label, readable, current, incoming, target)
        totals = {"acquire": 0, "arrived_excess": 0, "incoming_excess": 0, "combos": 0}
        for r in rows:
            try:
                dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
            except Exception:   # noqa: BLE001
                dec = {}
            if not dec:
                continue
            readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
            kind, _q, label = plan_call(dec)
            totals["acquire"] += int(dec.get("acquire_units", 0) or 0)
            totals["arrived_excess"] += int(dec.get("arrived_excess", 0) or 0)
            totals["incoming_excess"] += int(dec.get("incoming_excess", 0) or 0)
            totals["combos"] += 1
            models.setdefault(_model_of(readable), []).append(
                (kind, label, readable, r["current_supply"],
                 dec.get("incoming_in_horizon", r["future_supply"]), round(dec.get("target_level", 0) or 0, 1)))

        if not models:
            body = ('<div class="card"><p class="muted">No certified inventory plan is loaded for this store yet. '
                    'Once the New-Inventory board is issued it appears here as the dealership pipeline.</p></div>')
            return _resp(app, s, "Pipeline", body, "/")

        headline = kv([("Vehicles to order now", totals["acquire"]),
                       ("Combinations in the plan", totals["combos"]),
                       ("Arrived, over-stocked (review disposition)", totals["arrived_excess"]),
                       ("Incoming to redirect", totals["incoming_excess"])])
        parts = [f'<div class="card"><h2>Today across the whole dealership</h2>{headline}'
                 '<p class="muted">Expand a model to see its combinations. Numbers are read from the certified '
                 'plan — nothing is recomputed here.</p></div>']
        _tone = {"ACQUIRE": "attention", "EXCESS": "pending", "MONITOR": "healthy"}
        _rank = {"ACQUIRE": 0, "EXCESS": 1, "MONITOR": 2}
        for model in sorted(models):
            combos = sorted(models[model], key=lambda c: (_rank.get(c[0], 3), c[2]))
            n_order = sum(1 for c in combos if c[0] == "ACQUIRE")
            rows_html = table(
                ["Call", "Combination", "On ground now", "Incoming", "Target (60-day)"],
                [[safe(badge(_tone.get(c[0], "healthy"), c[1])), esc(c[2]), esc(c[3]), esc(c[4]), esc(c[5])]
                 for c in combos])
            summary = (f'{esc(model)} · {len(combos)} combination(s)'
                       + (f' · <strong>{n_order} to order</strong>' if n_order else ' · steady'))
            parts.append(f'<details class="card"><summary style="cursor:pointer;font-weight:600">{summary}'
                         f'</summary><div style="margin-top:10px">{rows_html}</div></details>')
        return _resp(app, s, "Pipeline", "".join(parts), "/")

    # ---- Ordering -------------------------------------------------------------------------------------
    @app.get("/ordering")
    def ordering(app, req):
        s = req.session
        app.require(s, "workspace.view")
        body = ('<div class="card"><p>Choose an ordering program.</p>'
                '<p><a href="/new-inventory"><button class=secondary>CPO — view the certified inventory board</button></a></p>'
                '<p class="muted">PPO (pre-produced offer Firm/Deny) is not yet built as an operator workflow. '
                'The certified New-Inventory board — what to order now, by combination — is available under CPO.</p>'
                '</div>')
        return _resp(app, s, "Ordering", body, "/ordering")

    # ---- Dealer Trade ---------------------------------------------------------------------------------
    @app.get("/dealer-trade")
    def dealer_trade(app, req):
        s = req.session
        app.require(s, "workspace.view")
        body = _placeholder(
            "Dealer Trade",
            "Our Trade (a unit we need from another store) and Their Trade (a unit they want from us) are not "
            "yet built as guided operator workflows. The governed dealer-trade domain remains intact in the "
            "backend and can be reached by an administrator from the Admin area.")
        return _resp(app, s, "Dealer Trade", body, "/dealer-trade")

    # ---- Wholesale ------------------------------------------------------------------------------------
    @app.get("/wholesale")
    def wholesale(app, req):
        s = req.session
        app.require(s, "workspace.view")
        body = _placeholder(
            "Wholesale",
            "A ranked disposition-readiness list (what to move first) is not yet built as an operator workflow. "
            "Arrived over-stocked combinations flagged for disposition are visible today on the Pipeline home "
            "and the CPO board.")
        return _resp(app, s, "Wholesale", body, "/wholesale")

    # ---- Demos ----------------------------------------------------------------------------------------
    @app.get("/demos")
    def demos(app, req):
        s = req.session
        app.require(s, "workspace.view")
        n = _conn(app).execute("SELECT COUNT(*) FROM executive_demo_unit WHERE store_scope=?",
                               (s.scope,)).fetchone()[0]
        roster = (f'<p class="muted">{esc(n)} demo vehicle record(s) exist in the backend, but no operator demo '
                  'roster (users, mileage behaviour, swap timing) has been entered yet.</p>' if n else
                  '<p class="muted">No demo roster has been entered yet.</p>')
        body = (f'<div class="card"><h2>Current Roster</h2>{roster}'
                '<p class="muted">The user-first roster / call-up board is not yet built. Executive-Demo backend '
                'behaviour remains DATA_ONLY and unchanged.</p></div>')
        return _resp(app, s, "Demos", body, "/demos")

    # ---- CTP ------------------------------------------------------------------------------------------
    @app.get("/ctp")
    def ctp(app, req):
        s = req.session
        app.require(s, "workspace.view")
        body = _placeholder(
            "CTP",
            "CTP remains its own governed domain. A dedicated operator-facing CTP page is not yet built; the "
            "underlying CTP engine and records are unchanged and available to an administrator.")
        return _resp(app, s, "CTP", body, "/ctp")

    # ---- Data control room ----------------------------------------------------------------------------
    @app.get("/data")
    def data_room(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ..app import source_health
        srows = [[esc(label), safe(badge("healthy" if tone == "green" else "attention" if tone == "yellow"
                                         else "stale" if tone == "red" else "unresolved",
                                         "current" if tone == "green" else "aging" if tone == "yellow"
                                         else "stale" if tone == "red" else "not loaded")),
                  esc(word)]
                 for (label, word, tone) in source_health(app, s.scope)]
        body = ('<div class="card"><h2>Sources</h2>'
                + table(["Source", "State", "Age / status"], srows)
                + '<p class="muted">Update Data (file upload) is not yet wired into this screen; freshness above '
                'is read honestly from recorded imports. A source with no successful load shows "not loaded".</p>'
                '</div>'
                '<div class="card"><h2>Settings &amp; preferences</h2>'
                '<p class="muted">Benched combinations, program settings and UI preferences will live here. '
                'The Service-Loaner desired-fleet size and monthly placement requirement are managed today on '
                'the <a href="/service-loaner">Service Loaners</a> screen.</p></div>')
        return _resp(app, s, "Data", body, "/data")

    # ---- Admin index (secondary; gathers governance / engineering screens) ----------------------------
    @app.get("/admin")
    def admin_index(app, req):
        s = req.session
        app.require(s, "workspace.view")
        links = "".join(f'<li><a href="{esc(p)}">{esc(label)}</a></li>' for p, label in ADMIN_NAV)
        body = ('<div class="card"><p>Internal governance and engineering surfaces. These enforce their own '
                'permissions; they are not part of the daily operator navigation.</p>'
                f'<ul>{links}</ul></div>')
        return _resp(app, s, "Admin", body, "/admin")


def _placeholder(title, message):
    return (f'<div class="card"><h2>{esc(title)}</h2><p>{esc(message)}</p>'
            '<p class="muted">This surface was made real so navigation is coherent; the specialized workflow '
            'is intentionally deferred. Nothing was fabricated.</p></div>')
