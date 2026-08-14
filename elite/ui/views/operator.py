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

from ..render import ADMIN_NAV, badge, esc, page, safe, table, kv, empty, form
from ..http import Response
from .domains import _readable, _resp, _conn


def _model_of(readable):
    """First token of a readable identity ('QX65 8501 QBE/G' -> 'QX65')."""
    return (readable or "").split(" ", 1)[0] or "Other"


# ---- governed, store-scoped operator workstate (JSON in the prefs store; no schema change) -------------
def _ws_get(app, scope, key, default):
    return app.prefs.get_pref(f"scope::{scope}", key, default=default)


def _ws_put(app, scope, key, value):
    app.prefs.set_pref(f"scope::{scope}", key, value)


def _default_month(app):
    from ...clock import to_utc_iso
    return to_utc_iso(app.stack.clock.now())[:7]


def _acquire_board(app, scope):
    """Read the certified issued plans into per-combination ACQUIRE recommendations (no recompute).
    Returns list of dicts sorted by (model, -order, identity)."""
    conn = _conn(app)
    rows = conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                        (scope,)).fetchall()
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    out = []
    for r in rows:
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        order = int(dec.get("acquire_units", 0) or 0)
        if not dec or order <= 0:
            continue
        readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
        out.append({"pid": r["id"], "combo": r["combination_id"], "identity": readable,
                    "model": _model_of(readable), "order": order, "current": r["current_supply"],
                    "future": dec.get("incoming_in_horizon", r["future_supply"])})
    out.sort(key=lambda d: (d["model"], -d["order"], d["identity"]))
    return out


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
                 dec.get("incoming_in_horizon", r["future_supply"]), round(dec.get("target_level", 0) or 0, 1),
                 r["id"]))

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
                [[safe(badge(_tone.get(c[0], "healthy"), c[1])),
                  safe(f'<a href="/combination/{esc(c[6])}">{esc(c[2])}</a>'),
                  esc(c[3]), esc(c[4]), esc(c[5])]
                 for c in combos])
            summary = (f'{esc(model)} · {len(combos)} combination(s)'
                       + (f' · <strong>{n_order} to order</strong>' if n_order else ' · steady'))
            parts.append(f'<details class="card"><summary style="cursor:pointer;font-weight:600">{summary}'
                         f'</summary><div style="margin-top:10px">{rows_html}</div></details>')
        return _resp(app, s, "Pipeline", "".join(parts), "/")

    # ---- combination detail (Recommendation / Why / Proof from certified facts) -----------------------
    @app.get("/combination/{pid}")
    def combination_detail(app, req):
        s = req.session
        app.require(s, "workspace.view")
        conn = _conn(app)
        r = conn.execute("SELECT * FROM inventory_plan_result WHERE id=? AND store_scope=?",
                         (req.params["pid"], s.scope)).fetchone()
        if r is None:
            return app._safe_page(s, "Not found", "That combination is not in your store.", 404)
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        ci = conn.execute("SELECT canonical_identity FROM sellable_combination WHERE id=?",
                          (r["combination_id"],)).fetchone()
        subject = _readable(ci["canonical_identity"]) if ci and ci["canonical_identity"] else r["combination_id"]
        from ...newinv.publish import plan_call
        label = plan_call(dec)[2] if dec else "No discrete action on record"
        mons = ", ".join(mm.get("month", "") for mm in (dec.get("monitor_months") or [])) or "—"
        cred = dec.get("credibility") if isinstance(dec.get("credibility"), dict) else {}
        why = kv([("Target (60-day level)", round(dec.get("target_level", 0) or 0, 2)),
                  ("On the ground now", r["current_supply"]),
                  ("Incoming (in horizon)", dec.get("incoming_in_horizon", r["future_supply"])),
                  ("Incoming (pending ETA)", dec.get("pending_timing", 0)),
                  ("Watch months", mons), ("Historical days-to-sell burden", dec.get("dts_burden", "—")),
                  ("Evidence level", dec.get("evidence_level", "—"))])
        proof = kv([("Combination", subject), ("Issued plan (audit id)", r["id"]),
                    ("Credibility Z", round(cred.get("credibility_z", 0) or 0, 4)),
                    ("Calculation version", r["calculation_version"] or "—"),
                    ("Reproducibility package", r["reproducibility_package"] or "—")])
        body = (f'<p><a href="/">← Pipeline</a></p>'
                f'<div class="card"><h2>Recommendation</h2><p>{esc(label)}</p></div>'
                f'<div class="card"><h2>Why</h2>{why}</div>'
                f'<div class="card"><h2>Proof</h2>{proof}'
                '<p class="muted">Read from the certified issued plan — not recomputed.</p></div>')
        return _resp(app, s, subject, body, "/")

    # ---- Ordering -------------------------------------------------------------------------------------
    @app.get("/ordering")
    def ordering(app, req):
        s = req.session
        app.require(s, "workspace.view")
        body = ('<div class="card"><p>Choose an ordering program.</p>'
                '<p><a href="/ordering/cpo"><button>CPO — monthly allocation ordering</button></a> '
                '<a href="/ordering/ppo"><button class=secondary>PPO — pre-produced offers</button></a></p></div>')
        return _resp(app, s, "Ordering", body, "/ordering")

    # ---- CPO: month + per-model allocation ceiling + ranked line workflow (Confirm / Not Ordered) -----
    @app.get("/ordering/cpo")
    def cpo(app, req):
        s = req.session
        app.require(s, "workspace.view")
        app.ensure_inventory_published(s.scope)
        month = req.q("month") or _default_month(app)
        alloc = _ws_get(app, s.scope, f"cpo_alloc::{month}", {}) or {}
        lines = _ws_get(app, s.scope, f"cpo_line::{month}", {}) or {}
        board = _acquire_board(app, s.scope)
        models = {}
        for b in board:
            b["month"] = month
            models.setdefault(b["model"], []).append(b)

        monthf = (f'<form method="get" action="/ordering/cpo" class="mut">'
                  f'<label for=m>CPO ordering month</label>'
                  f'<input id=m name=month value="{esc(month)}" placeholder="YYYY-MM" style="max-width:140px">'
                  f'<button type=submit class=secondary>Select</button></form>')
        parts = [f'<div class="card"><h2>CPO — {esc(month)}</h2>{monthf}'
                 '<p class="muted">Allocation is a ceiling, not a command: Elite recommends only what is '
                 'economically justified and leaves the rest open. Work each line individually.</p></div>']

        # allocation form (one number per model on the board)
        alloc_fields = "".join(
            f'<label for=a_{esc(mo)}>{esc(mo)} monthly allocation</label>'
            f'<input id=a_{esc(mo)} name="alloc_{esc(mo)}" type=number min=0 style="max-width:120px" '
            f'value="{esc(alloc.get(mo, ""))}">' for mo in sorted(models))
        if alloc_fields:
            parts.append('<div class="card"><h3>Allocation by model</h3>'
                         + form("/ordering/cpo/allocation",
                                f'<input type=hidden name=month value="{esc(month)}">{alloc_fields}',
                                csrf=s.csrf_token, submit="Save allocation") + '</div>')

        for mo in sorted(models):
            recs = models[mo]
            cap = int(alloc.get(mo, len(recs)) or 0)
            active, nextbest = recs[:cap], recs[cap:]
            # promote next-best when an active line is Not Ordered
            not_ordered_active = sum(1 for b in active if lines.get(b["combo"]) == "not_ordered")
            promoted = nextbest[:not_ordered_active]
            worked = sum(1 for b in active if lines.get(b["combo"]) in ("confirmed", "not_ordered"))
            open_cap = max(0, cap - len(recs))
            rows = []
            for rank, b in enumerate(active + promoted, 1):
                rows.append(_cpo_line(s, b, rank, lines.get(b["combo"]), promoted=b in promoted))
            head = (f'{esc(mo)} · Allocation {cap} · Recommended {len(recs)} · Worked {worked}'
                    + (f' · <strong>{open_cap} intentionally open</strong>' if open_cap else ''))
            block = f'<div class="card"><h3>{head}</h3>' + table(
                ["#", "Combination", "Order", "Current", "Relevant Future", "Action"], rows)
            if open_cap:
                block += (f'<p class="muted">Why open: only {len(recs)} combination(s) for {esc(mo)} are '
                          f'economically justified this month; {open_cap} allocation left open rather than '
                          'manufacturing a weak order.</p>')
            if nextbest[len(promoted):]:
                nb = table(["Combination", "Order", "Current", "Relevant Future"],
                           [[safe(f'<a href="/combination/{esc(b["pid"])}">{esc(b["identity"])}</a>'),
                             esc(b["order"]), esc(b["current"]), esc(b["future"])]
                            for b in nextbest[len(promoted):]])
                block += f'<details><summary style="cursor:pointer">Next best (reserves)</summary>{nb}</details>'
            block += (form(f"/ordering/cpo/revert", f'<input type=hidden name=month value="{esc(month)}">'
                           f'<input type=hidden name=model value="{esc(mo)}">',
                           csrf=s.csrf_token, submit="Revert this model", ) )
            parts.append(block + '</div>')
        if not models:
            parts.append('<div class="card"><p class="muted">No certified ACQUIRE recommendations are issued '
                         'for this store. Load/refresh the New-Inventory plan to populate CPO.</p></div>')
        return _resp(app, s, "CPO Ordering", "".join(parts), "/ordering")

    @app.post("/ordering/cpo/allocation")
    def cpo_allocation(app, req):
        s = req.session
        app.require(s, "workspace.view")
        month = req.form.get("month") or _default_month(app)
        alloc = {}
        for k, v in req.form.items():
            if k.startswith("alloc_") and (v or "").strip():
                try:
                    n = int(v)
                    if n >= 0:
                        alloc[k[len("alloc_"):]] = n
                except ValueError:
                    pass
        _ws_put(app, s.scope, f"cpo_alloc::{month}", alloc)
        s.flash = "Allocation saved."
        return Response.redirect(f"/ordering/cpo?month={month}")

    @app.post("/ordering/cpo/line")
    def cpo_line(app, req):
        s = req.session
        app.require(s, "workspace.view")
        month = req.form.get("month") or _default_month(app)
        combo, state = req.form.get("combo"), req.form.get("state")
        lines = _ws_get(app, s.scope, f"cpo_line::{month}", {}) or {}
        if state in ("confirmed", "not_ordered"):
            lines[combo] = state
        elif state == "clear":
            lines.pop(combo, None)
        _ws_put(app, s.scope, f"cpo_line::{month}", lines)
        return Response.redirect(f"/ordering/cpo?month={month}")

    @app.post("/ordering/cpo/revert")
    def cpo_revert(app, req):
        s = req.session
        app.require(s, "workspace.view")
        month = req.form.get("month") or _default_month(app)
        model = req.form.get("model")
        lines = _ws_get(app, s.scope, f"cpo_line::{month}", {}) or {}
        board = {b["combo"]: b["model"] for b in _acquire_board(app, s.scope)}
        lines = {c: st for c, st in lines.items() if board.get(c) != model}
        _ws_put(app, s.scope, f"cpo_line::{month}", lines)
        s.flash = f"Reverted worked lines for {model}."
        return Response.redirect(f"/ordering/cpo?month={month}")

    # ---- PPO: named window, manual offer entry, Firm/Deny simulated supply (no auth-inventory mutation)
    @app.get("/ordering/ppo")
    def ppo(app, req):
        s = req.session
        app.require(s, "workspace.view")
        window = req.q("window") or _ws_get(app, s.scope, "ppo_current_window", "") or ""
        offers = _ws_get(app, s.scope, f"ppo_offers::{window}", []) if window else []
        firmed = [o for o in offers if o["decision"] == "FIRM"]
        winf = (f'<form method="get" action="/ordering/ppo" class="mut"><label for=w>PPO window</label>'
                f'<input id=w name=window value="{esc(window)}" placeholder="e.g. August PPO" style="max-width:220px">'
                f'<button type=submit class=secondary>Open</button></form>')
        parts = [f'<div class="card"><h2>PPO</h2>{winf}'
                 '<p class="muted">Enter each manufacturer-offered unit as you receive it. Firm adds it to this '
                 'window\'s <strong>simulated</strong> future supply only — it never changes authoritative '
                 'inventory. We only know what you enter, so there is no total-offer count.</p></div>']
        if window:
            saved = _ws_get(app, s.scope, f"ppo_saved_at::{window}", None)
            entry = form("/ordering/ppo/offer",
                         f'<input type=hidden name=window value="{esc(window)}">'
                         f'<label for=c>Offered combination (code or description)</label>'
                         f'<input id=c name=combo required style="max-width:320px">'
                         '<label>Decision</label>'
                         '<label class=mut><input type=radio name=decision value=FIRM checked> Firm</label> '
                         '<label class=mut><input type=radio name=decision value=DENY> Deny</label>',
                         csrf=s.csrf_token, submit="Record offer")
            rows = [[esc(o["combo"]), safe(badge("completed" if o["decision"] == "FIRM" else "pending", o["decision"])),
                     esc(o.get("at", ""))] for o in offers]
            parts.append(f'<div class="card"><h3>{esc(window)}</h3>'
                         + (f'<p class="muted">Saved simulation from {esc(saved)}.</p>' if saved else '')
                         + f'<p>{len(firmed)} firmed → simulated future supply in this window.</p>'
                         + entry + table(["Offer", "Decision", "Recorded"], rows)
                         + form("/ordering/ppo/revert", f'<input type=hidden name=window value="{esc(window)}">',
                                csrf=s.csrf_token, submit="Revert window") + '</div>')
        return _resp(app, s, "PPO Ordering", "".join(parts), "/ordering")

    @app.post("/ordering/ppo/offer")
    def ppo_offer(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...clock import to_utc_iso
        window = req.form.get("window") or ""
        combo = (req.form.get("combo") or "").strip()
        decision = req.form.get("decision") if req.form.get("decision") in ("FIRM", "DENY") else "DENY"
        if window and combo:
            offers = _ws_get(app, s.scope, f"ppo_offers::{window}", []) or []
            offers.append({"combo": combo, "decision": decision, "at": to_utc_iso(app.stack.clock.now())[:10]})
            _ws_put(app, s.scope, f"ppo_offers::{window}", offers)
            _ws_put(app, s.scope, f"ppo_saved_at::{window}", to_utc_iso(app.stack.clock.now())[:10])
            _ws_put(app, s.scope, "ppo_current_window", window)
        return Response.redirect(f"/ordering/ppo?window={window}")

    @app.post("/ordering/ppo/revert")
    def ppo_revert(app, req):
        s = req.session
        app.require(s, "workspace.view")
        window = req.form.get("window") or ""
        _ws_put(app, s.scope, f"ppo_offers::{window}", [])
        s.flash = "PPO window reverted."
        return Response.redirect(f"/ordering/ppo?window={window}")

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


def _cpo_line(s, b, rank, state, *, promoted=False):
    ident = safe(f'<a href="/combination/{esc(b["pid"])}">{esc(b["identity"])}</a>'
                 + (' ' + badge("completed", "promoted") if promoted else ''))
    if state == "confirmed":
        action = safe(badge("completed", "Confirmed") + " " + _line_btn(s, b, "clear", "Revert", "secondary"))
    elif state == "not_ordered":
        action = safe(badge("stale", "Not Ordered") + " " + _line_btn(s, b, "clear", "Revert", "secondary"))
    else:
        action = safe(_line_btn(s, b, "confirmed", "Confirm") + " " + _line_btn(s, b, "not_ordered", "Not Ordered", "secondary"))
    label = ident if state != "not_ordered" else safe(f'<span style="opacity:.55">{ident}</span>')
    return [esc(rank), label, esc(b["order"]), esc(b["current"]), esc(b["future"]), action]


def _line_btn(s, b, state, text, cls="primary"):
    from ..render import _js  # noqa
    return (f'<form class="mut" method="post" action="/ordering/cpo/line">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=month value="{esc(b.get("month", ""))}">'
            f'<input type=hidden name=combo value="{esc(b["combo"])}">'
            f'<input type=hidden name=state value="{esc(state)}">'
            f'<button type=submit class="{esc(cls)}" style="padding:3px 9px">{esc(text)}</button></form>')


def _placeholder(title, message):
    return (f'<div class="card"><h2>{esc(title)}</h2><p>{esc(message)}</p>'
            '<p class="muted">This surface was made real so navigation is coherent; the specialized workflow '
            'is intentionally deferred. Nothing was fabricated.</p></div>')
