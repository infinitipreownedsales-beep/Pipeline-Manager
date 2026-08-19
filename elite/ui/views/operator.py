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

from ..render import (ADMIN_NAV, badge, esc, page, safe, table, kv, empty, form,
                      workspace_header, month_nav, metric, stat_row, progress, chip, disclosure,
                      action_group, rec_card, rec_row, work_group, restraint_note, coverage_lane,
                      horizon_strip)
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


_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]


def _month_label(ym):
    try:
        y, m = ym.split("-")
        return f"{_MONTHS[int(m) - 1]} {y}"
    except Exception:   # noqa: BLE001
        return ym


def _month_short(ym):
    """Compact month label for the coverage lane, e.g. '2026-09' -> \"Sep '26\"."""
    try:
        y, m = ym.split("-")
        return f"{_MONTHS[int(m) - 1][:3]} '{y[2:]}"
    except Exception:   # noqa: BLE001
        return ym


def _model_coverage(app, scope, month, *, base_path="/ordering/cpo", window=3):
    """Model-level certified month coverage from inventory_plan_month (AGGREGATION ONLY — no recompute). For
    each model, sum the certified per-combination month rows (expected demand, supply position, shortage,
    excess) to the model, then return a compact window of months centred on the selected month. Coverage
    state is read straight from the certified summed shortage/excess signs. Non-selected cells carry a
    server-backed ?month= link so the lane doubles as month navigation."""
    conn = _conn(app)
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    plan_model = {}
    for r in conn.execute("SELECT id, combination_id FROM inventory_plan_result "
                          "WHERE store_scope=? AND status='issued'", (scope,)).fetchall():
        plan_model[r["id"]] = _model_of(_readable(ident.get(r["combination_id"], r["combination_id"])))
    agg = {}   # (model, month) -> summed certified quantities
    try:
        for mr in conn.execute(
                "SELECT m.plan_id, m.month, m.expected_demand, m.cumulative_supply, m.shortage, m.excess "
                "FROM inventory_plan_month m JOIN inventory_plan_result p ON m.plan_id=p.id "
                "WHERE p.store_scope=? AND p.status='issued'", (scope,)).fetchall():
            mdl = plan_model.get(mr["plan_id"])
            if not mdl:
                continue
            d = agg.setdefault((mdl, mr["month"]),
                               {"demand": 0.0, "supply": 0.0, "shortage": 0.0, "excess": 0.0})
            d["demand"] += mr["expected_demand"] or 0.0
            d["supply"] += mr["cumulative_supply"] or 0.0
            d["shortage"] += mr["shortage"] or 0.0
            d["excess"] += mr["excess"] or 0.0
    except Exception:   # noqa: BLE001
        return {}
    months_by_model = {}
    for (mdl, m) in agg:
        months_by_model.setdefault(mdl, set()).add(m)
    out = {}
    for mdl, mset in months_by_model.items():
        months = sorted(mset | ({month} if month else set()))
        i = months.index(month) if month in months else len(months) // 2
        lo, hi = max(0, i - window), min(len(months), i + window + 1)
        cells = []
        for m in months[lo:hi]:
            a = agg.get((mdl, m))
            if a is None:
                state = "none"
            elif a["shortage"] > 1e-9:
                state = "short"
            elif a["excess"] > 1e-9:
                state = "over"
            else:
                state = "covered"
            cells.append({"month": m, "label": _month_short(m), "selected": (m == month),
                          "demand": (a["demand"] if a else None), "supply": (a["supply"] if a else None),
                          "shortage": (a["shortage"] if a else None), "excess": (a["excess"] if a else None),
                          "state": state,
                          "href": None if m == month else f"{base_path}?month={m}"})
        out[mdl] = cells
    return out


def _month_options(app, selected, *, back=1, fwd=12):
    now = app.stack.clock.now()
    y0, m0 = now.year, now.month
    out = []
    for off in range(-back, fwd + 1):
        y = y0 + (m0 - 1 + off) // 12
        m = (m0 - 1 + off) % 12 + 1
        ym = f"{y:04d}-{m:02d}"
        out.append(f'<option value="{esc(ym)}"{" selected" if ym == selected else ""}>{esc(_month_label(ym))}</option>')
    return "".join(out)


def _month_select(app, name, selected, *, onchange=False):
    oc = ' onchange="this.form.submit()"' if onchange else ""
    return f'<select name="{esc(name)}"{oc}>{_month_options(app, selected)}</select>'


def _known_models(app, scope):
    conn = app.stack.db.conn
    ids = [c["canonical_identity"] for c in conn.execute(
        "SELECT canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()
        if c["canonical_identity"]]
    return sorted({_model_of(_readable(i)) for i in ids}) or ["QX50", "QX55", "QX60", "QX65", "QX80"]


def _known_combos(app, scope):
    conn = app.stack.db.conn
    out = [(c["id"], _readable(c["canonical_identity"] or c["id"])) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()]
    out.sort(key=lambda t: t[1])
    return out


def _known_vins(app, scope):
    conn = app.stack.db.conn
    vins = set()
    for tbl in ("service_loaner_unit", "vehicle_unit", "executive_demo_unit"):
        try:
            for row in conn.execute(f"SELECT vin FROM {tbl} WHERE store_scope=?", (scope,)).fetchall():
                if row["vin"]:
                    vins.add(row["vin"])
        except Exception:   # noqa: BLE001
            pass
    return sorted(vins)


def _select(name, options, selected=None, *, onchange=False):
    oc = ' onchange="this.form.submit()"' if onchange else ""
    opts = "".join(f'<option value="{esc(v)}"{" selected" if v == selected else ""}>{esc(lbl)}</option>'
                   for v, lbl in options)
    return f'<select name="{esc(name)}"{oc}>{opts}</select>'


def _datalist_input(name, list_id, values, *, value="", placeholder=""):
    """A searchable canonical selector: a native datalist (select-or-type) so a known value is chosen from
    the enumerated list, with free typing available only as fallback for a truly external value."""
    opts = "".join(f'<option value="{esc(v)}">' for v in values)
    return (f'<input name="{esc(name)}" list="{esc(list_id)}" value="{esc(value)}" '
            f'placeholder="{esc(placeholder)}" style="max-width:360px" autocomplete="off">'
            f'<datalist id="{esc(list_id)}">{opts}</datalist>')


def _benched(app, scope):
    return set(app.prefs.get_pref(f"scope::{scope}", "benched", default=[]) or [])


def _is_benched(bench, combo_id, identity):
    return combo_id in bench or identity in bench


def _plan_months(app, scope):
    """Map plan_id -> {month: certified time-phased row} from inventory_plan_month (no recompute)."""
    idx = {}
    try:
        for mr in _conn(app).execute(
                "SELECT m.plan_id, m.month, m.expected_demand, m.cumulative_demand, m.cumulative_supply, "
                "m.shortage, m.excess, m.confidence, m.seq FROM inventory_plan_month m "
                "JOIN inventory_plan_result p ON m.plan_id=p.id "
                "WHERE p.store_scope=? AND p.status='issued'", (scope,)).fetchall():
            idx.setdefault(mr["plan_id"], {})[mr["month"]] = mr
    except Exception:   # noqa: BLE001
        pass
    return idx


def _acquire_board(app, scope, month=None):
    """Certified issued ACQUIRE recommendations (no recompute). When `month` is given, each row is bound to
    the certified time-phased state for that planning month: Relevant Future is the supply POSITION available
    by that month (so a later arrival is not credited to an earlier month), and month shortage/demand/excess/
    confidence become the ranking + Why/Proof context. The discrete ORDER-now quantity stays exactly the
    certified actionability decision — a projected later shortage is never turned into an order now.
    Benched combinations are excluded. Ordering: month-shortage first when month data exists, else -order."""
    conn = _conn(app)
    rows = conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                        (scope,)).fetchall()
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    bench = _benched(app, scope)
    pmonths = _plan_months(app, scope) if month else {}
    out = []
    for r in rows:
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        order = int(dec.get("acquire_units", 0) or 0)   # commit-now action — certified, month-independent
        if not dec or order <= 0:
            continue
        readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
        if _is_benched(bench, r["combination_id"], readable):
            continue
        certified_future = dec.get("incoming_in_horizon", r["future_supply"])
        mrow = (pmonths.get(r["id"]) or {}).get(month) if month else None
        # Relevant Future = certified supply position available BY the selected month (excludes later arrivals)
        relevant_future = (mrow["cumulative_supply"] if mrow is not None and mrow["cumulative_supply"] is not None
                           else certified_future)
        out.append({"pid": r["id"], "combo": r["combination_id"], "identity": readable,
                    "model": _model_of(readable), "order": order, "current": r["current_supply"],
                    "future": relevant_future, "certified_future": certified_future,
                    "m_present": mrow is not None,
                    "m_shortage": (mrow["shortage"] if mrow is not None else None),
                    "m_demand": (mrow["expected_demand"] if mrow is not None else None),
                    "m_cum_demand": (mrow["cumulative_demand"] if mrow is not None else None),
                    "m_cum_supply": (mrow["cumulative_supply"] if mrow is not None else None),
                    "m_excess": (mrow["excess"] if mrow is not None else None),
                    "m_confidence": (mrow["confidence"] if mrow is not None else None)})
    if month and any(b["m_shortage"] is not None for b in out):
        out.sort(key=lambda d: (d["model"],
                                -(d["m_shortage"]) if d["m_shortage"] is not None else float("inf"),
                                -d["order"], d["identity"]))
    else:
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
        bench = _benched(app, s.scope)

        models = {}          # model -> list of (call_kind, label, readable, current, incoming, target, pid)
        totals = {"acquire": 0, "arrived_excess": 0, "incoming_excess": 0, "combos": 0}
        for r in rows:
            try:
                dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
            except Exception:   # noqa: BLE001
                dec = {}
            if not dec:
                continue
            readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
            incoming = dec.get("incoming_in_horizon", r["future_supply"]) or 0
            benched = _is_benched(bench, r["combination_id"], readable)
            # Bench law: no-longer-orderable + no incoming -> drop from the active pipeline; keep (labelled)
            # only while incoming supply still needs management.
            if benched and not incoming:
                continue
            kind, _q, label = plan_call(dec)
            if benched:
                label += " · No longer orderable"
            totals["acquire"] += int(dec.get("acquire_units", 0) or 0)
            totals["arrived_excess"] += int(dec.get("arrived_excess", 0) or 0)
            totals["incoming_excess"] += int(dec.get("incoming_excess", 0) or 0)
            totals["combos"] += 1
            models.setdefault(_model_of(readable), []).append(
                (kind, label, readable, r["current_supply"], incoming,
                 round(dec.get("target_level", 0) or 0, 1), r["id"]))

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
        # month-specific certified time-phased context, when the caller (CPO) passed a planning month
        month = req.q("month")
        mrow = None
        if month:
            mrow = conn.execute("SELECT * FROM inventory_plan_month WHERE plan_id=? AND month=?",
                                (r["id"], month)).fetchone()
        why_rows = [("Target (60-day level)", round(dec.get("target_level", 0) or 0, 2)),
                    ("On the ground now", r["current_supply"])]
        if mrow is not None:
            why_rows += [(f"Expected demand — {month}", round(mrow["expected_demand"] or 0, 2)),
                         (f"Cumulative demand through {month}", round(mrow["cumulative_demand"] or 0, 2)),
                         (f"Supply position by {month}", mrow["cumulative_supply"]),
                         (f"Projected shortage — {month}", round(mrow["shortage"] or 0, 2)),
                         (f"Projected excess — {month}", round(mrow["excess"] or 0, 2)),
                         (f"Confidence — {month}", mrow["confidence"] or "—")]
        else:
            why_rows += [("Incoming (in horizon)", dec.get("incoming_in_horizon", r["future_supply"])),
                         ("Incoming (pending ETA)", dec.get("pending_timing", 0))]
        why_rows += [("Watch months", mons), ("Historical days-to-sell burden", dec.get("dts_burden", "—")),
                     ("Evidence level", dec.get("evidence_level", "—"))]
        if month and mrow is None:
            why_rows.append((f"Planning month {month}", "outside the certified planning horizon for this combination"))
        why = kv(why_rows)
        proof = kv([("Combination", subject), ("Issued plan (audit id)", r["id"]),
                    ("Planning month", month or "— (overall)"),
                    ("Credibility Z", round(cred.get("credibility_z", 0) or 0, 4)),
                    ("Calculation version", r["calculation_version"] or "—"),
                    ("Reproducibility package", r["reproducibility_package"] or "—")])
        benched = subject in _benched(app, s.scope)
        bench_card = (f'<div class="card"><h3>Ordering availability</h3>'
                      + (f'<p>{badge("stale", "No longer orderable")} This combination is benched. '
                         + _ws_btn(s, "/data/bench/restore", "combo", subject, "Restore (make orderable)") + '</p>'
                         if benched else
                         '<p class="muted">Bench only if this combination is genuinely no longer obtainable / '
                         'orderable (not a skip or a preference). History is preserved.</p>'
                         + _bench_button(s, subject, f"/combination/{r['id']}")) + '</div>')
        body = (f'<p><a href="/">← Pipeline</a></p>'
                f'<div class="card"><h2>Recommendation</h2><p>{esc(label)}</p></div>'
                f'<div class="card"><h2>Why</h2>{why}</div>'
                f'<div class="card"><h2>Proof</h2>{proof}'
                '<p class="muted">Read from the certified issued plan — not recomputed.</p></div>'
                + bench_card)
        return _resp(app, s, subject, body, "/")

    @app.post("/bench")
    def bench_context(app, req):
        s = req.session
        app.require(s, "workspace.view")
        combo = (req.form.get("combo") or "").strip()
        back = req.form.get("back") or "/"
        if not back.startswith("/"):
            back = "/"
        bench = _ws_get(app, s.scope, "benched", []) or []
        if combo and combo not in bench:
            bench.append(combo)
            _ws_put(app, s.scope, "benched", bench)
            s.flash = f"Benched {combo} — no longer orderable; removed from ordering recommendations. History kept."
        return Response.redirect(back)

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
        month = _cpo_resolve_month(app, s, req)
        alloc = _ws_get(app, s.scope, f"cpo_alloc::{month}", {}) or {}
        lines = _ws_get(app, s.scope, f"cpo_line::{month}", {}) or {}
        board = _acquire_board(app, s.scope, month)
        coverage = _model_coverage(app, s.scope, month)
        pmonths = _plan_months(app, s.scope)     # certified per-plan month rows (for the horizon sparkline)
        models = {}
        for b in board:
            b["month"] = month
            models.setdefault(b["model"], []).append(b)

        # --- month context: deterministic server-backed prev/current/next links (no submit-dependent JS),
        #     with the visible-submit dropdown kept as a secondary jump control ---
        prev_ym, next_ym = _month_neighbours(app, month)
        jump = (f'<form method="get" action="/ordering/cpo" class="mut">'
                f'{_month_select(app, "month", month, onchange=True)} '
                f'<button type=submit class=secondary>Jump</button></form>')
        nav = month_nav("/ordering/cpo",
                        (prev_ym, _month_label(prev_ym)) if prev_ym else None,
                        (month, _month_label(month)),
                        (next_ym, _month_label(next_ym)) if next_ym else None, jump_html=safe(jump))
        parts = [workspace_header("CPO Ordering", nav)]

        if not models:
            parts.append('<div class="card"><p class="muted">No certified ACQUIRE recommendations are issued '
                         'for this store yet. Load or refresh the New-Inventory plan to populate CPO.</p></div>')
            return Response(page("CPO Ordering", "".join(parts), ctx=app.ctx(s), active_path="/ordering",
                                 flash=_flash(s), wide=True, hide_title=True))

        for mo in sorted(models):
            recs = models[mo]
            cap = int(alloc.get(mo, len(recs)) or 0)
            active, nextbest = recs[:cap], recs[cap:]
            not_ordered_active = sum(1 for b in active if lines.get(b["combo"]) == "not_ordered")
            promoted = nextbest[:not_ordered_active]
            shown = active + promoted
            worked = sum(1 for b in shown if lines.get(b["combo"]) in ("confirmed", "not_ordered"))
            remaining = len(shown) - worked
            open_cap = max(0, cap - len(recs))

            # hero work summary — the operator sees state immediately
            hero = stat_row([metric(len(recs), "Recommended", attn=remaining > 0),
                             metric(worked, "Worked"),
                             metric(remaining, "Remaining", attn=remaining > 0),
                             metric(cap, "Allocation ceiling")])
            hero += progress(worked, len(shown))
            # compact horizontal time/coverage lane: the operator SEES the surrounding-month supply/need
            # story (why these orders are recommended now) before opening any Why. Certified data only.
            cov = coverage.get(mo) or []
            lane = coverage_lane(cov, caption="Coverage by month — expected need vs certified supply "
                                 "position (selected month centred)") if cov else ""
            window_months = [c["month"] for c in cov]

            def _strip(b):
                hz = _combo_horizon(pmonths, b["pid"], window_months, month, b["current"]) if window_months else []
                return horizon_strip(safe(f'On lot now <b>{esc(b["current"])}</b>'), hz) if hz else ""
            edit = disclosure("Edit allocation ceiling",
                              form("/ordering/cpo/allocation",
                                   f'<input type=hidden name=month value="{esc(month)}">'
                                   f'<label for=a_{esc(mo)}>{esc(mo)} monthly allocation (ceiling)</label>'
                                   f'<input id=a_{esc(mo)} name="alloc_{esc(mo)}" type=number min=0 '
                                   f'style="max-width:120px" value="{esc(alloc.get(mo, ""))}">',
                                   csrf=s.csrf_token, submit="Save ceiling"))
            block = [f'<div class="card"><h2 style="margin-top:4px">{esc(mo)}</h2>{hero}{lane}{edit}']

            # work queue: unresolved recommendations, in certified rank order. The top 3 get the rich card;
            # ranks 4..N compress to compact rows so a whole model stays scannable in ~one viewport. Handled
            # (worked) items leave the active queue and collapse into a receded, still-undoable group.
            ranked = list(enumerate(shown, 1))     # (certified rank, rec)
            unresolved = [(r, b) for r, b in ranked if lines.get(b["combo"]) not in ("confirmed", "not_ordered")]
            worked = [(r, b) for r, b in ranked if lines.get(b["combo"]) in ("confirmed", "not_ordered")]
            queue = []
            for i, (r, b) in enumerate(unresolved):
                if i < 3:
                    queue.append(_cpo_rec_card(s, b, r, lines.get(b["combo"]), month,
                                               promoted=b in promoted, horizon_html=_strip(b)))
                else:
                    queue.append(_cpo_rec_row(s, b, r, lines.get(b["combo"]), month,
                                              promoted=b in promoted, horizon_html=_strip(b)))
            if queue:
                block.append('<div class="queue">' + "".join(queue) + '</div>')
            elif worked:
                block.append('<p class="muted" style="margin:8px 0">Every recommendation for this model is '
                             'handled — see the worked items below.</p>')
            if worked:
                n_conf = sum(1 for _r, b in worked if lines.get(b["combo"]) == "confirmed")
                n_not = len(worked) - n_conf
                bits = ([f"{n_conf} confirmed"] if n_conf else []) + ([f"{n_not} not ordering"] if n_not else [])
                rows = "".join(_cpo_rec_row(s, b, r, lines.get(b["combo"]), month,
                                            promoted=b in promoted, horizon_html=_strip(b))
                               for r, b in worked)
                block.append(work_group(f"Worked — {len(worked)} · {' · '.join(bits)}", safe(rows)))

            # intentionally-open capacity — a positive Elite judgment (restraint), not leftover work
            if open_cap:
                block.append(restraint_note(safe(
                    f'<strong>Elite is holding {open_cap} of your {cap} {esc(mo)} slots open on purpose.</strong> '
                    f'Only {len(recs)} combination(s) are economically justified for {esc(_month_label(month))}; '
                    'the rest stay open rather than manufacturing a weak order. This is restraint, not unfinished '
                    'work. <span class="muted">Why open: demand and coverage do not support consuming the full '
                    'ceiling.</span>')))

            if nextbest[len(promoted):]:
                nb = "".join(
                    f'<div class="pos" style="padding:2px 0">'
                    f'<a href="/combination/{esc(b["pid"])}?month={esc(month)}">{esc(b["identity"])}</a> — '
                    f'ORDER {esc(b["order"])} · Current {esc(b["current"])} · By {esc(month)} {esc(b["future"])}</div>'
                    for b in nextbest[len(promoted):])
                block.append(disclosure(f"Next best reserves ({len(nextbest[len(promoted):])})", safe(nb)))

            block.append(form("/ordering/cpo/revert", f'<input type=hidden name=month value="{esc(month)}">'
                              f'<input type=hidden name=model value="{esc(mo)}">',
                              csrf=s.csrf_token, submit="Revert this model", ))
            parts.append("".join(block) + '</div>')
        return Response(page("CPO Ordering", "".join(parts), ctx=app.ctx(s), active_path="/ordering",
                             flash=_flash(s), wide=True, hide_title=True))

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
        windows = _ws_get(app, s.scope, "ppo_windows", []) or []
        pick = (f'<form method="get" action="/ordering/ppo" class="mut"><label>Open PPO window</label>'
                + _select("window", [(w, w) for w in windows] or [("", "— none yet —")], window, onchange=True)
                + '<noscript><button type=submit class=secondary>Open</button></noscript></form>') if windows else ""
        create = form("/ordering/ppo/new",
                      '<label>Create PPO window (month)</label>' + _month_select(app, "month", _default_month(app)),
                      csrf=s.csrf_token, submit="Create window")
        parts = [f'<div class="card"><h2>PPO</h2>{pick}{create}'
                 '<p class="muted">Enter each manufacturer-offered unit as you receive it. Firm adds it to this '
                 'window\'s <strong>simulated</strong> future supply only — it never changes authoritative '
                 'inventory. We only know what you enter, so there is no total-offer count.</p></div>']
        if window:
            saved = _ws_get(app, s.scope, f"ppo_saved_at::{window}", None)
            combos = [lbl for _cid, lbl in _known_combos(app, s.scope)]
            entry = form("/ordering/ppo/offer",
                         f'<input type=hidden name=window value="{esc(window)}">'
                         '<label>Offered combination (select a known combination; type only for a truly external one)</label>'
                         + _datalist_input("combo", "ppo_combos", combos, placeholder="select or type external")
                         + '<label>Decision</label>'
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

    @app.post("/ordering/ppo/new")
    def ppo_new(app, req):
        s = req.session
        app.require(s, "workspace.view")
        month = req.form.get("month") or _default_month(app)
        name = f"{_month_label(month)} PPO"
        windows = _ws_get(app, s.scope, "ppo_windows", []) or []
        if name not in windows:
            windows.append(name)
            _ws_put(app, s.scope, "ppo_windows", windows)
        _ws_put(app, s.scope, "ppo_current_window", name)
        return Response.redirect(f"/ordering/ppo?window={name}")

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
            windows = _ws_get(app, s.scope, "ppo_windows", []) or []
            if window not in windows:
                windows.append(window)
                _ws_put(app, s.scope, "ppo_windows", windows)
        return Response.redirect(f"/ordering/ppo?window={window}")

    @app.post("/ordering/ppo/revert")
    def ppo_revert(app, req):
        s = req.session
        app.require(s, "workspace.view")
        window = req.form.get("window") or ""
        _ws_put(app, s.scope, f"ppo_offers::{window}", [])
        s.flash = "PPO window reverted."
        return Response.redirect(f"/ordering/ppo?window={window}")

    # ---- Wholesale — ranked disposition-readiness + dealer-safe copy list -----------------------------
    @app.get("/wholesale")
    def wholesale(app, req):
        s = req.session
        app.require(s, "workspace.view")
        app.ensure_inventory_published(s.scope)
        conn = _conn(app)
        rows = conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                            (s.scope,)).fetchall()
        ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
            "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (s.scope,)).fetchall()}
        now, future = [], []
        for r in rows:
            try:
                dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
            except Exception:   # noqa: BLE001
                dec = {}
            arr, inc = int(dec.get("arrived_excess", 0) or 0), int(dec.get("incoming_excess", 0) or 0)
            readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
            if arr > 0:
                now.append({"identity": readable, "qty": arr, "pid": r["id"],
                            "dts": dec.get("dts_burden", "—")})
            if inc > 0:
                future.append({"identity": readable, "qty": inc, "pid": r["id"]})
        now.sort(key=lambda d: (-d["qty"], d["identity"]))
        future.sort(key=lambda d: (-d["qty"], d["identity"]))

        nrows = [[esc(i + 1),
                  safe(f'<a href="/combination/{esc(d["pid"])}">{esc(d["identity"])}</a>'),
                  esc(d["qty"]), esc(d["dts"])] for i, d in enumerate(now)]
        dealer_text = "\n".join(f'{d["identity"]} — {d["qty"]} available' for d in now)
        copy = ('<h3>Dealer list (safe to send)</h3>'
                f'<textarea id="dl" readonly rows="{max(2, len(now)+1)}" '
                'style="max-width:520px;font-family:monospace">' + esc(dealer_text) + '</textarea>'
                '<div style="margin-top:8px"><button type=button onclick="'
                "navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('dl').value);"
                'this.textContent=&quot;Copied&quot;">Copy dealer list</button></div>'
                '<p class="muted">Copied text is combination + quantity only — no rank, age, or internal reasoning.</p>')
        frows = [[safe(f'<a href="/combination/{esc(d["pid"])}">{esc(d["identity"])}</a>'), esc(d["qty"])]
                 for d in future]
        body = ('<div class="card"><h2>What to move first</h2>'
                '<p class="muted">Ranked by disposition readiness (arrived over-stock). Click a combination for '
                'Recommendation → Why → Proof. Within a combination, dispose the oldest appropriate unit first.</p>'
                + table(["#", "Combination", "To move", "DTS burden"], nrows) + copy + '</div>'
                '<div class="card"><h2>Future changes (incoming to redirect)</h2>'
                + table(["Combination", "Redirect"], frows) + '</div>')
        return _resp(app, s, "Wholesale", body, "/wholesale")

    # ---- Dealer Trade — Our Trade / Their Trade (uses the certified short/over board) ------------------
    @app.get("/dealer-trade")
    def dealer_trade(app, req):
        s = req.session
        app.require(s, "workspace.view")
        short, over = _short_over(app, s.scope)     # combos we ACQUIRE (short) / have EXCESS (over)
        tab = req.q("tab") or "their"
        nav = ('<div class="card"><a href="/dealer-trade?tab=their"><button class="'
               + ("primary" if tab == "their" else "secondary") + '">Their Trade</button></a> '
               '<a href="/dealer-trade?tab=our"><button class="'
               + ("primary" if tab == "our" else "secondary") + '">Our Trade</button></a></div>')
        if tab == "our":
            body = nav + _our_trade(app, s, short, over)
        else:
            body = nav + _their_trade(app, s, short, over)
        return _resp(app, s, "Dealer Trade", body, "/dealer-trade")

    @app.post("/dealer-trade/their")
    def their_save(app, req):
        s = req.session
        app.require(s, "workspace.view")
        inv_raw = req.form.get("inv") or ""
        _ws_put(app, s.scope, "trade_their", {
            "requested": (req.form.get("requested") or "").strip(),
            "inv_raw": inv_raw,
            # Keep legacy line storage for backward compatibility with old sessions.
            "inv": [ln.strip() for ln in inv_raw.splitlines() if ln.strip()],
            "unavail": []})
        s.flash = "Their-trade session saved."
        return Response.redirect("/dealer-trade?tab=their")

    @app.post("/dealer-trade/their/unavailable")
    def their_unavail(app, req):
        s = req.session
        app.require(s, "workspace.view")
        st = _ws_get(app, s.scope, "trade_their", {}) or {}
        try:
            idx = int(req.form.get("idx"))
            un = set(st.get("unavail", []))
            un.add(idx)
            st["unavail"] = sorted(un)
            _ws_put(app, s.scope, "trade_their", st)
        except (TypeError, ValueError):
            pass
        return Response.redirect("/dealer-trade?tab=their")

    @app.post("/dealer-trade/our")
    def our_save(app, req):
        s = req.session
        app.require(s, "workspace.view")
        _ws_put(app, s.scope, "trade_our", {"needed": (req.form.get("needed") or "").strip(),
                                            "demanded": (req.form.get("demanded") or "").strip()})
        s.flash = "Our-trade session saved."
        return Response.redirect("/dealer-trade?tab=our")

    # ---- Demos — user-first roster + call-up board ----------------------------------------------------
    @app.get("/demos")
    def demos(app, req):
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        short, _over = _short_over(app, s.scope)
        rows = []
        for u in roster:
            cur = u.get("current") or {}
            vel = _mileage_velocity(u)
            rows.append([safe(f'<a href="/demos/user/{esc(u["id"])}">{esc(u["name"])}</a>'),
                         esc(u.get("role", "")), esc(u.get("model_pref", "")),
                         esc(cur.get("vin", "—")), esc(vel if vel is not None else "—")])
        add = form("/demos/user",
                   '<label>Name</label><input name=name required style="max-width:260px">'
                   '<label>Role / title</label><input name=role style="max-width:260px">'
                   '<label>Model preference</label>'
                   + _select("model_pref", [("", "— any —")] + [(m, m) for m in _known_models(app, s.scope)])
                   + '<label>Trim preference</label><input name=trim_pref style="max-width:200px">',
                   csrf=s.csrf_token, submit="Add user")
        callup = _callup_board(short)
        body = ('<div class="card"><h2>Current Roster</h2>'
                + table(["User", "Role", "Prefers", "Current demo VIN", "Miles/day"], rows)
                + '</div><div class="card"><h3>Add a demo user</h3>' + add + '</div>'
                + callup)
        return _resp(app, s, "Demos", body, "/demos")

    @app.post("/demos/user")
    def demos_add(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...ids import new_id
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        name = (req.form.get("name") or "").strip()
        if name:
            roster.append({"id": new_id("demu"), "name": name, "role": (req.form.get("role") or "").strip(),
                           "model_pref": (req.form.get("model_pref") or "").strip().upper(),
                           "trim_pref": (req.form.get("trim_pref") or "").strip(),
                           "current": None, "history": []})
            _ws_put(app, s.scope, "demo_roster", roster)
            s.flash = "User added."
        return Response.redirect("/demos")

    @app.get("/demos/user/{uid}")
    def demos_user(app, req):
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        u = next((x for x in roster if x["id"] == req.params["uid"]), None)
        if u is None:
            return app._safe_page(s, "Not found", "That demo user is not on the roster.", 404)
        cur = u.get("current") or {}
        vel = _mileage_velocity(u)
        info = kv([("Role", u.get("role", "")), ("Prefers", f'{u.get("model_pref","")} {u.get("trim_pref","")}'.strip()),
                   ("Current demo VIN", cur.get("vin", "—")), ("Start date", cur.get("start", "—")),
                   ("Mileage at assignment", cur.get("mi_in", "—")),
                   ("Personal mileage velocity", f"{vel} mi/day" if vel is not None else "—")])
        assign = form("/demos/user/" + u["id"] + "/assign",
                      '<label>Demo VIN</label>'
                      + _datalist_input("vin", "assign_vins", _known_vins(app, s.scope),
                                        placeholder="select or type VIN")
                      + '<label>Start date</label><input name=start type=date style="max-width:180px">'
                      '<label>Mileage at assignment</label><input name=mi type=number style="max-width:160px">',
                      csrf=s.csrf_token, submit="Assign demo")
        ret = (form("/demos/user/" + u["id"] + "/return",
                    '<label>Return / swap mileage</label><input name=mi type=number required style="max-width:160px">'
                    '<label>Swap date</label><input name=date type=date style="max-width:180px">',
                    csrf=s.csrf_token, submit="Record return / swap") if cur else "")
        # preference-first next demo
        short, _o = _short_over(app, s.scope)
        pref = (u.get("model_pref") or "").upper()
        picks = [b for b in short if b["model"] == pref] or short
        nb = table(["Rank", "Best next demo"], [[esc(i + 1), esc(b["identity"])] for i, b in enumerate(picks[:3])]) \
            if picks else empty("No available combination supports a next demo yet.")
        hrows = [[esc(h.get("vin", "")), esc(h.get("mi_in", "")), esc(h.get("mi_out", "")),
                  esc(h.get("miles", "")), esc(h.get("start", "")), esc(h.get("end", ""))] for h in u.get("history", [])]
        body = (f'<p><a href="/demos">← Roster</a></p><div class="card"><h2>{esc(u["name"])}</h2>{info}</div>'
                f'<div class="card"><h3>Next demo — prefers {esc(pref or "any")}</h3>{nb}</div>'
                '<div class="card"><h3>Assign / swap</h3>' + assign + ret + '</div>'
                '<div class="card"><h3>Demo history</h3>'
                + table(["VIN", "Miles in", "Miles out", "Driven", "Start", "End"], hrows) + '</div>')
        return _resp(app, s, u["name"], body, "/demos")

    @app.post("/demos/user/{uid}/assign")
    def demos_assign(app, req):
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        for u in roster:
            if u["id"] == req.params["uid"]:
                u["current"] = {"vin": (req.form.get("vin") or "").strip(),
                                "start": (req.form.get("start") or "").strip(),
                                "mi_in": _int_or0(req.form.get("mi"))}
                _ws_put(app, s.scope, "demo_roster", roster)
                s.flash = "Demo assigned."
                break
        return Response.redirect("/demos/user/" + req.params["uid"])

    @app.post("/demos/user/{uid}/return")
    def demos_return(app, req):
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        for u in roster:
            if u["id"] == req.params["uid"] and u.get("current"):
                cur = u["current"]
                mi_out = _int_or0(req.form.get("mi"))
                cur["mi_out"] = mi_out
                cur["end"] = (req.form.get("date") or "").strip()
                cur["miles"] = max(0, mi_out - _int_or0(cur.get("mi_in")))
                u.setdefault("history", []).append(cur)
                u["current"] = None
                _ws_put(app, s.scope, "demo_roster", roster)
                s.flash = "Return recorded; demo returned to retail pool."
                break
        return Response.redirect("/demos/user/" + req.params["uid"])

    # ---- CTP — expose existing governed CTP actions in plain language ---------------------------------
    @app.get("/ctp")
    def ctp(app, req):
        s = req.session
        app.require(s, "workspace.view")
        conn = _conn(app)
        try:
            acts = conn.execute(
                "SELECT a.* FROM ctp_action a JOIN supply_workflow w ON a.workflow_id=w.id "
                "WHERE w.store_scope=? ORDER BY a.created_at DESC", (s.scope,)).fetchall()
        except Exception:   # noqa: BLE001
            acts = []
        ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
            "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (s.scope,)).fetchall()}
        rows = []
        for a in acts:
            frm = _readable(ident.get(a["original_combination_id"], a["original_combination_id"] or "—"))
            to = _readable(ident.get(a["proposed_combination_id"], a["proposed_combination_id"] or "—"))
            rows.append([esc(frm), esc(to), esc(a["resulting_order_state"] or "proposed"),
                         esc((a["created_at"] or "")[:10])])
        if rows:
            body = ('<div class="card"><h2>Change-to-plan actions</h2>'
                    '<p class="muted">Recommendation: change an incoming order to a stronger combination before '
                    'it arrives. Why/Proof: driven by the certified need/excess that opened each action.</p>'
                    + table(["From", "To", "State", "Recorded"], rows) + '</div>')
        else:
            body = ('<div class="card"><h2>Change-to-plan</h2>'
                    '<p>No change-to-plan actions are currently open for this store. When the engine identifies '
                    'an incoming order that should be re-specified before arrival, it appears here as '
                    'Recommendation → Why → Proof.</p></div>')
        return _resp(app, s, "CTP", body, "/ctp")

    # ---- Data control room — imports, bench, unavailable inventory, Service-Loaner program settings ---
    @app.get("/data")
    def data_room(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ..app import source_health, SOURCE_INDICATORS
        srows = [[esc(label), safe(badge("healthy" if tone == "green" else "attention" if tone == "yellow"
                                         else "stale" if tone == "red" else "unresolved",
                                         "current" if tone == "green" else "aging" if tone == "yellow"
                                         else "stale" if tone == "red" else "not loaded")), esc(word)]
                 for (label, word, tone) in source_health(app, s.scope)]
        # import controls: one browser file-upload per source, staged then run through the existing orchestrator
        _fmt = {"new_inventory_current": ".xlsx,.csv", "speed_to_sell": ".xlsx",
                "service_loaner_fleet": ".csv", "retail_history": ".csv"}
        imp = ""
        for label, key, _g, _y in SOURCE_INDICATORS:
            fid = "f_" + key
            imp += (f'<form class="mut" method="post" action="/data/import" enctype="multipart/form-data">'
                    f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                    f'<input type=hidden name=contract value="{esc(key)}">'
                    f'<label>Update {esc(label)} (accepts {esc(_fmt.get(key, ""))})</label>'
                    f'<input type=file name=file id="{fid}" accept="{esc(_fmt.get(key, ""))}" '
                    f'onchange="var n=this.files[0]?this.files[0].name:&quot;&quot;;'
                    f'document.getElementById(&quot;{fid}_n&quot;).textContent=n">'
                    f'<div id="{fid}_n" class="muted" style="margin:4px 0"></div>'
                    f'<div style="margin-top:6px"><button type="submit">Import {esc(label)}</button></div></form>')
        combos = [lbl for _cid, lbl in _known_combos(app, s.scope)]
        bench = _ws_get(app, s.scope, "benched", []) or []
        brows = [[esc(b), safe(_ws_btn(s, "/data/bench/restore", "combo", b, "Restore"))] for b in bench]
        bench_form = form("/data/bench", '<label>Bench a combination (no longer orderable)</label>'
                          + _select("combo", [(c, c) for c in combos] or [("", "— no combinations —")]),
                          csrf=s.csrf_token, submit="Bench")
        vins = _known_vins(app, s.scope)
        un = _ws_get(app, s.scope, "unavailable", []) or []
        urows = []
        for i, iv in enumerate(un):
            act = _ws_btn(s, "/data/unavailable/return", "idx", str(i), "Mark available") if not iv.get("end") \
                else esc("returned " + iv.get("end", ""))
            urows.append([esc(iv.get("vin", "")), esc(iv.get("reason", "")), esc(iv.get("start", "")),
                          esc(iv.get("end", "—")), safe(act)])
        un_form = form("/data/unavailable",
                       '<label>VIN</label>'
                       + _datalist_input("vin", "un_vins", vins, placeholder="select or type VIN")
                       + '<label>Reason</label>'
                       + _select("reason", [(r, r) for r in ("body shop", "mechanical", "event damage", "other")])
                       + '<label>Unavailable start</label><input name=start type=date style="max-width:180px">',
                       csrf=s.csrf_token, submit="Mark unavailable")
        # translation / identity health — unresolved source language actually observed from real sources
        from ...identity.translation import TranslationStore
        _xlat = TranslationStore(app.prefs, s.scope)
        if not _xlat.is_initialized():
            xlat_card = ('<div class="card"><h2>Translation &amp; Identity</h2>'
                         f'<p>{badge("unresolved", "not initialized")} No identity mappings imported yet. '
                         '<a href="/admin/translation">Open Translation Center →</a></p></div>')
        else:
            _unresolved = _xlat.unresolved_translations()
            tone, word = ("attention", f"{len(_unresolved)} unresolved") if _unresolved else ("healthy", "resolved")
            msg = ("source value(s) have no approved translation yet. Resolve them so imports translate "
                   "automatically." if _unresolved else "All observed source language is translated.")
            xlat_card = ('<div class="card"><h2>Translation &amp; Identity</h2>'
                         f'<p>{badge(tone, word)} {msg} '
                         '<a href="/admin/translation">Open Translation Center →</a></p></div>')
        body = ('<div class="card"><h2>Sources</h2>' + table(["Source", "State", "Age / status"], srows) + '</div>'
                + xlat_card
                + '<div class="card"><h2>Update data</h2><p class="muted">Place the export in the uploads folder and '
                'enter its path; the import runs through the certified ingestion pipeline and updates freshness '
                'above. Nothing is marked loaded unless the import actually succeeds.</p>' + imp + '</div>'
                '<div class="card"><h2>Benched combinations</h2><p class="muted">A benched combination is no longer '
                'orderable and is excluded from ordering recommendations.</p>'
                + table(["Combination", ""], brows) + bench_form + '</div>'
                '<div class="card"><h2>Temporarily unavailable inventory</h2>'
                + table(["VIN", "Reason", "Since", "Returned", ""], urows) + un_form + '</div>'
                '<div class="card"><h2>Service-Loaner program inputs</h2>'
                '<p class="muted">Effective-dated ICV / Velocity program values (durable historical months; '
                'unresolved is never $0) are maintained on the dedicated Program Inputs page — reachable here '
                'and from the Service Loaner board.</p>'
                '<p><a href="/program-inputs"><button type=button>Open Program Inputs →</button></a></p></div>')
        return _resp(app, s, "Data", body, "/data")

    @app.post("/data/import")
    def data_import(app, req):
        s = req.session
        app.require(s, "workspace.view")
        contract = req.form.get("contract")
        upload = req.files.get("file")
        if contract == "new_inventory_current" and upload:
            filename = (upload[0] or "").lower()
            if filename.endswith(".xlsx"):
                contract = "new_inventory_pipeline_summary"
        s.flash = _run_upload(app, s.scope, contract, upload)
        return Response.redirect("/data")

    @app.post("/data/bench")
    def data_bench(app, req):
        s = req.session
        app.require(s, "workspace.view")
        combo = (req.form.get("combo") or "").strip()
        bench = _ws_get(app, s.scope, "benched", []) or []
        if combo and combo not in bench:
            bench.append(combo)
            _ws_put(app, s.scope, "benched", bench)
            s.flash = "Combination benched (excluded from ordering)."
        return Response.redirect("/data")

    @app.post("/data/bench/restore")
    def data_bench_restore(app, req):
        s = req.session
        app.require(s, "workspace.view")
        combo = req.form.get("combo")
        bench = [b for b in (_ws_get(app, s.scope, "benched", []) or []) if b != combo]
        _ws_put(app, s.scope, "benched", bench)
        s.flash = "Combination restored."
        return Response.redirect("/data")

    @app.post("/data/unavailable")
    def data_unavailable(app, req):
        s = req.session
        app.require(s, "workspace.view")
        vin = (req.form.get("vin") or "").strip()
        un = _ws_get(app, s.scope, "unavailable", []) or []
        if vin:
            un.append({"vin": vin, "reason": (req.form.get("reason") or "").strip(),
                       "start": (req.form.get("start") or "").strip(), "end": ""})
            _ws_put(app, s.scope, "unavailable", un)
            s.flash = "Unit marked temporarily unavailable."
        return Response.redirect("/data")

    @app.post("/data/unavailable/return")
    def data_unavailable_return(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...clock import to_utc_iso
        un = _ws_get(app, s.scope, "unavailable", []) or []
        try:
            i = int(req.form.get("idx"))
            if 0 <= i < len(un):
                un[i]["end"] = to_utc_iso(app.stack.clock.now())[:10]
                _ws_put(app, s.scope, "unavailable", un)
                s.flash = "Unit returned to availability; unavailable interval preserved."
        except (TypeError, ValueError):
            pass
        return Response.redirect("/data")


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


def _flash(s):
    f = s.flash
    s.flash = None
    return f


def _num(v):
    return round(v, 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else (v if v is not None else "—")


def _month_neighbours(app, month):
    """Adjacent selectable months (prev, next) within the selector window (current-1 .. current+12),
    or None at an edge. Used to build deterministic prev/next month links."""
    now = app.stack.clock.now()
    cur = now.year * 12 + (now.month - 1)
    lo, hi = cur - 1, cur + 12
    try:
        y, m = month.split("-")
        mi = int(y) * 12 + (int(m) - 1)
    except Exception:   # noqa: BLE001
        return (None, None)
    def ym(i):
        return f"{i // 12:04d}-{i % 12 + 1:02d}"
    return (ym(mi - 1) if mi - 1 >= lo else None, ym(mi + 1) if mi + 1 <= hi else None)


def _month_in_window(app, month):
    """True iff `month` (YYYY-MM) parses and falls inside the CPO selector window (current-1 .. current+12).
    A remembered month that has fallen out of the window (e.g. stale from a prior run) is treated as invalid."""
    now = app.stack.clock.now()
    cur = now.year * 12 + (now.month - 1)
    try:
        y, m = str(month).split("-")
        mi = int(y) * 12 + (int(m) - 1)
    except Exception:   # noqa: BLE001
        return False
    return cur - 1 <= mi <= cur + 12


def _cpo_resolve_month(app, s, req):
    """Resolve the CPO working month with per-principal, store-scoped memory. Presentation state ONLY — it
    never feeds the certified plan calculation (the resolved month is bound exactly as an explicit ?month
    always was). An explicit ?month overrides and updates the memory; otherwise the last remembered month is
    restored; an invalid / out-of-window value (explicit or remembered) falls back to the default current
    month. Store-scoped (keyed under scope::<scope>) so one store's memory can never leak into another; the
    pref key is principal-qualified so operators do not overwrite each other."""
    key = f"cpo_last_month::{s.principal_id}"
    explicit = req.q("month")
    if explicit:
        month = explicit if _month_in_window(app, explicit) else _default_month(app)
    else:
        remembered = _ws_get(app, s.scope, key, None)
        month = remembered if (remembered and _month_in_window(app, remembered)) else _default_month(app)
    _ws_put(app, s.scope, key, month)          # heal to a valid value; record explicit overrides
    return month


def _cpo_rec_pieces(s, b, rank, state, month, promoted):
    """Compute the shared parts of a CPO recommendation (identity, hero call, position, month-specific Why
    drawer, status chip, action group, resolved flag) once, so the rich card and the compact row present the
    SAME information and the SAME actions — only the density differs."""
    ident = safe(f'<a href="/combination/{esc(b["pid"])}?month={esc(month)}">{esc(b["identity"])}</a>'
                 + (' ' + badge("completed", "promoted") if promoted else ''))
    call = f'ORDER {b["order"]}'
    pos = safe(f'Current <strong>{esc(b["current"])}</strong> · By {esc(month)} <strong>{esc(b["future"])}</strong>')
    if b.get("m_present"):
        why_body = kv([("Why now", f"ranked by the {_month_label(month)} coverage condition"),
                       (f"Projected shortage — {month}", _num(b.get("m_shortage"))),
                       (f"Expected demand — {month}", _num(b.get("m_demand"))),
                       (f"Supply position by {month}", b.get("m_cum_supply")),
                       (f"Confidence — {month}", b.get("m_confidence") or "—"),
                       ("Order now (certified action)", b["order"])])
    else:
        why_body = kv([("Why", "certified acquire-now decision for this combination"),
                       (f"Planning month {month}", "outside the certified planning horizon for this combination"),
                       ("Order now (certified action)", b["order"])])
    common = dict(ident=ident, call=call, pos=pos, why_body=why_body, rank=rank)
    if state == "confirmed":
        return dict(resolved=True, chip=chip("done", "Confirmed"),
                    actions=action_group(_line_btn(s, b, "clear", "Undo", "secondary")), **common)
    if state == "not_ordered":
        return dict(resolved=True, chip=chip("skip", "Not ordering"),
                    actions=action_group(_line_btn(s, b, "clear", "Undo", "secondary")), **common)
    actions = action_group(_line_btn(s, b, "confirmed", "Confirm order")
                           + _line_btn(s, b, "not_ordered", "Not ordering", "secondary")
                           + _bench_button(s, b["identity"], f"/ordering/cpo?month={month}"))
    return dict(resolved=False, chip=chip("need", "Needs decision"), actions=actions, **common)


def _combo_horizon(pmonths, pid, window_months, month, current):
    """Per-combination certified horizon cells for the sparkline. For each window month: this combination's
    certified supply position + expected demand + coverage state, plus the certified ARRIVAL delta into that
    month — the month-over-month change in the certified supply position (baselined to on-lot-now for the
    plan's first month). All read straight from inventory_plan_month; the delta is not a forward order."""
    rows = pmonths.get(pid) or {}
    prev_supply, base = {}, (current or 0)
    for m in sorted(rows.keys()):                 # baseline each plan month against the one before it
        prev_supply[m] = base
        base = rows[m]["cumulative_supply"]
    cells = []
    for m in window_months:
        mr = rows.get(m)
        if mr is None:
            cells.append({"month": m, "label": _month_short(m).split(" ")[0], "selected": (m == month),
                          "supply": None, "demand": None, "arrival": None, "shortage": None,
                          "excess": None, "state": "none"})
            continue
        sup, dem = mr["cumulative_supply"], mr["expected_demand"]
        arrival = None if sup is None else sup - prev_supply.get(m, current or 0)
        state = ("short" if (mr["shortage"] or 0) > 1e-9 else "over" if (mr["excess"] or 0) > 1e-9
                 else "covered")
        cells.append({"month": m, "label": _month_short(m).split(" ")[0], "selected": (m == month),
                      "supply": sup, "demand": dem, "arrival": arrival,
                      "shortage": mr["shortage"], "excess": mr["excess"], "state": state})
    return cells


def _cpo_rec_card(s, b, rank, state, month, *, promoted=False, horizon_html=""):
    """A rich recommendation card (top 1-3 of a model): the ORDER call is the hero, and — when available —
    the certified horizon sparkline is shown INLINE so the operator reads this combination's whole-horizon
    position on one glance (the legacy planning grid's strongest habit), without opening Why."""
    p = _cpo_rec_pieces(s, b, rank, state, month, promoted)
    pos = safe(p["pos"] + horizon_html) if horizon_html else p["pos"]
    why = disclosure(f"Why #{rank}", p["why_body"])
    return rec_card(rank, p["ident"], p["call"], pos, why, p["actions"],
                    resolved=p["resolved"], chip_html=p["chip"])


def _cpo_rec_row(s, b, rank, state, month, *, promoted=False, horizon_html=""):
    """A compact recommendation row (ranks 4..N, and every worked item): compact by default. Expanding it
    reveals the SAME certified horizon sparkline + Why in place, so every recommendation is equally
    inspectable without permanently costing whole-model density."""
    p = _cpo_rec_pieces(s, b, rank, state, month, promoted)
    inner = (horizon_html + p["why_body"]) if horizon_html else p["why_body"]
    why = disclosure(f"Why & horizon #{rank}" if horizon_html else f"Why #{rank}", safe(inner))
    return rec_row(rank, p["ident"], p["call"], p["pos"], why, p["actions"],
                   resolved=p["resolved"], chip_html=p["chip"])


def _line_btn(s, b, state, text, cls="primary"):
    from ..render import _js  # noqa
    return (f'<form class="mut" method="post" action="/ordering/cpo/line">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=month value="{esc(b.get("month", ""))}">'
            f'<input type=hidden name=combo value="{esc(b["combo"])}">'
            f'<input type=hidden name=state value="{esc(state)}">'
            f'<button type=submit class="{esc(cls)}" style="padding:3px 9px">{esc(text)}</button></form>')


def _int_or0(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _bench_button(s, identity, back):
    """A native in-context Bench control (with the required confirmation). Bench means ONLY 'no longer
    orderable' — it removes the combination from future ordering feasibility while preserving history."""
    return (f'<form class="mut" method="post" action="/bench">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=combo value="{esc(identity)}">'
            f'<input type=hidden name=back value="{esc(back)}">'
            '<button type=submit class="secondary" style="padding:3px 9px" '
            'onclick="return confirm(&quot;Bench this combination because it is no longer orderable?&quot;)">'
            'Bench</button></form>')


def _ws_btn(s, action, name, value, text):
    return (f'<form class="mut" method="post" action="{esc(action)}">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name="{esc(name)}" value="{esc(value)}">'
            f'<button type=submit class="secondary" style="padding:3px 9px">{esc(text)}</button></form>')


def _short_over(app, scope):
    """The certified board split into what we are SHORT on (ACQUIRE) and what we are OVER on (EXCESS),
    each as {identity, model, qty}. Used by Dealer Trade + Demos call-up. Read-only, no recompute."""
    conn = app.stack.db.conn
    rows = conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                        (scope,)).fetchall()
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    short, over = [], []
    for r in rows:
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
        acq = int(dec.get("acquire_units", 0) or 0)
        exc = int(dec.get("arrived_excess", 0) or 0)
        if acq > 0:
            short.append({"identity": readable, "model": _model_of(readable), "qty": acq})
        if exc > 0:
            over.append({"identity": readable, "model": _model_of(readable), "qty": exc})
    short.sort(key=lambda d: (-d["qty"], d["identity"]))
    over.sort(key=lambda d: (-d["qty"], d["identity"]))
    return short, over


def _callup_board(short):
    cards = ""
    for model in ("QX60", "QX65", "QX80"):
        picks = [b for b in short if b["model"] == model]
        best = picks[0]["identity"] if picks else "none available in the current plan"
        cards += f'<p><strong>Best available {model} demo:</strong> {esc(best)}</p>'
    return f'<div class="card"><h2>Call-Up Board</h2>{cards}</div>'


def _mileage_velocity(u):
    """Miles/day from the user's completed history (total driven / total days), else None."""
    total_mi, total_days = 0, 0
    import datetime as _dt
    for h in u.get("history", []):
        total_mi += _int_or0(h.get("miles"))
        try:
            d0 = _dt.date.fromisoformat(h.get("start", "")[:10])
            d1 = _dt.date.fromisoformat(h.get("end", "")[:10])
            total_days += max(1, (d1 - d0).days)
        except Exception:   # noqa: BLE001
            pass
    return round(total_mi / total_days, 1) if total_days else None



def _parse_external_trade_inventory(raw):
    """Parse temporary counterparty inventory.

    Supports:
      * copied NNA markdown-table inventory rows;
      * legacy one-unit-per-line free text.

    Counterparty units remain external evidence only. Nothing here creates Supply.
    """
    import re

    if isinstance(raw, (list, tuple)):
        text = "\n".join(str(x) for x in raw)
    else:
        text = str(raw or "")

    units = []

    # Actual browser clipboard from NNA is tab-separated plain text:
    # Mi, Dealer, Stock#, Serial, Description, Trans, Ext, Int,
    # MSRP, Inv, DIS, ETA, Body Style.
    #
    # The browser strips the hidden Model Code metadata. For QX65 the same
    # authoritative NNA feed established these description -> certified-code
    # relationships:
    #   QX65 LUXE AWD  -> 8501
    #   QX65 SPORT AWD -> 8511
    #   QX65 AUTO AWD  -> 8521
    qx65_description_codes = {
        "QX65 LUXE AWD": "8501",
        "QX65 SPORT AWD": "8511",
        "QX65 AUTO AWD": "8521",
    }

    for line in text.splitlines():
        if "\t" not in line:
            continue
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) < 13:
            continue

        mi, dealer, stock, serial, description, trans, ext, interior, \
            msrp_cell, inv_cell, dis_cell, eta, body_style = cells[:13]

        description_u = description.upper()
        model_match = re.search(r"\b(QX\d+)\b", description_u)
        model = model_match.group(1) if model_match else ""
        model_code = qx65_description_codes.get(description_u, "")

        def money(v):
            m = re.search(r"([\d,]+)", v or "")
            return int(m.group(1).replace(",", "")) if m else None

        dm = re.search(r"\d+", dis_cell or "")
        dis = int(dm.group(0)) if dm else 0

        ext = ext.upper()
        interior = interior.upper()
        identity = " ".join(x for x in (
            model,
            model_code,
            f"{ext}/{interior}" if ext and interior else ""
        ) if x)

        units.append({
            "source_index": len(units),
            "dealer": dealer,
            "miles": mi,
            "stock_number": stock,
            "serial": serial,
            "model_code_raw": "",
            "model_code": model_code,
            "model": model,
            "description": description,
            "trans": trans,
            "ext": ext,
            "int": interior,
            "msrp": money(msrp_cell),
            "invoice": money(inv_cell),
            "dis": dis,
            "eta": eta,
            "body_style": body_style,
            "identity": identity or description,
            "raw": line,
            "structured": True,
        })

    if units:
        return units

    # NNA copied table rows. A real vehicle row contains the Stock# followed by
    # a markdown Serial link whose title carries "Model Code - NNNNN".
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "Model Code -" not in line:
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 14:
            continue

        try:
            # Expected NNA layout:
            # blank, Mi, Dealer, Stock#, Serial-link, Description, Trans,
            # Ext, Int, MSRP, Inv, DIS, ETA, Body Style
            mi = cells[1]
            dealer = cells[2]
            stock = cells[3]
            serial_cell = cells[4]
            description = cells[5]
            trans = cells[6]
            ext = cells[7].upper()
            interior = cells[8].upper()
            msrp_cell = cells[9]
            inv_cell = cells[10]
            dis_cell = cells[11]
            eta = cells[12]
            body_style = cells[13]

            mm = re.search(r"Model Code\s*-\s*(\d+)", serial_cell, re.I)
            model_code_raw = mm.group(1) if mm else ""
            # NNA feed currently carries a five-digit lifecycle code such as
            # 85217 while Elite's certified sellable identity uses 8521.
            model_code = model_code_raw[:4] if len(model_code_raw) >= 4 else model_code_raw

            sm = re.search(r"\[([A-Za-z0-9]+)\]", serial_cell)
            serial = sm.group(1) if sm else ""

            model_match = re.search(r"\b(QX\d+)\b", description.upper())
            model = model_match.group(1) if model_match else ""

            def money(v):
                m = re.search(r"([\d,]+)", v or "")
                return int(m.group(1).replace(",", "")) if m else None

            dm = re.search(r"\d+", dis_cell or "")
            dis = int(dm.group(0)) if dm else 0

            identity = " ".join(x for x in (
                model,
                model_code,
                f"{ext}/{interior}" if ext and interior else ""
            ) if x)

            units.append({
                "source_index": len(units),
                "dealer": dealer,
                "miles": mi,
                "stock_number": stock,
                "serial": serial,
                "model_code_raw": model_code_raw,
                "model_code": model_code,
                "model": model,
                "description": description,
                "trans": trans,
                "ext": ext,
                "int": interior,
                "msrp": money(msrp_cell),
                "invoice": money(inv_cell),
                "dis": dis,
                "eta": eta,
                "body_style": body_style,
                "identity": identity or description,
                "raw": line,
                "structured": True,
            })
        except Exception:   # noqa: BLE001
            # A malformed counterparty row is ignored rather than fabricated.
            continue

    if units:
        return units

    # Backward-compatible free-text mode for quick/manual candidate entry.
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        model_match = re.search(r"\b(QX\d+)\b", line.upper())
        model = model_match.group(1) if model_match else ""
        units.append({
            "source_index": len(units),
            "model": model,
            "model_code": "",
            "ext": "",
            "int": "",
            "stock_number": "",
            "serial": "",
            "description": line,
            "dis": 0,
            "identity": line,
            "raw": line,
            "structured": False,
        })
    return units


def _score_external_trade_candidate(unit, short):
    """Rank a counterparty unit against the certified current shortage board.

    Specificity dominates:
      exact certified combination > same model-code/color neighborhood >
      same model-code > generic same-model relief.

    Returns (score, reason, matched_shortage_qty).
    """
    model = (unit.get("model") or "").upper()
    code = (unit.get("model_code") or "").upper()
    ext = (unit.get("ext") or "").upper()
    interior = (unit.get("int") or "").upper()

    best_score = 0
    best_reason = "No current shortage match"
    best_qty = 0

    for need in short:
        need_identity = (need.get("identity") or "").upper()
        need_model = (need.get("model") or "").upper()
        qty = int(need.get("qty", 0) or 0)

        if not model or model != need_model:
            continue

        # Parse certified readable identity, e.g. QX65 8521 GAT/N.
        parts = need_identity.split()
        need_code = parts[1] if len(parts) > 1 else ""
        colors = parts[2] if len(parts) > 2 else ""
        if "/" in colors:
            need_ext, need_int = colors.split("/", 1)
        else:
            need_ext, need_int = "", ""

        if code and code == need_code and ext == need_ext and interior == need_int:
            score = 1000 + qty * 100
            reason = f"Exact shortage: {need['identity']} (need {qty})"
        elif code and code == need_code and ext and ext == need_ext:
            score = 700 + qty * 50
            reason = f"Same model code + exterior as shortage: {need['identity']}"
        elif code and code == need_code and interior and interior == need_int:
            score = 650 + qty * 50
            reason = f"Same model code + interior as shortage: {need['identity']}"
        elif code and code == need_code:
            score = 500 + qty * 40
            reason = f"Same model code as shortage: {need['identity']}"
        else:
            score = 100 + qty * 10
            reason = f"Model-level shortage relief: {need_model}"

        if score > best_score:
            best_score = score
            best_reason = reason
            best_qty = qty

    return best_score, best_reason, best_qty

def _their_trade(app, s, short, over):
    st = _ws_get(app, s.scope, "trade_their", {}) or {}
    combos = [lbl for _cid, lbl in _known_combos(app, s.scope)]
    entry = form("/dealer-trade/their",
                 '<label>Unit / combination the other dealer requested from us (our inventory)</label>'
                 + _datalist_input("requested", "their_req_combos", combos, value=st.get("requested", ""),
                                   placeholder="select our combination")
                 + '<label>Their inventory snapshot (external — one unit / combination per line)</label>'
                 '<textarea name=inv rows=10 style="max-width:760px">' + esc(
                     st.get("inv_raw", "\n".join(st.get("inv", [])))) + '</textarea>',
                 csrf=s.csrf_token, submit="Evaluate trade")
    out = '<div class="card"><h2>Their Trade</h2><p class="muted">Help the other store while protecting our own '
    out += 'inventory. External inventory never becomes our supply until a trade is committed.</p>' + entry + '</div>'
    req = st.get("requested", "")
    if req:
        # is what they asked for something WE are short on? then propose a lower-harm alternative from our over-stock
        harmful = any(b["model"] in req.upper() or b["identity"] in req for b in short)
        alt = over[0]["identity"] if over else None
        rec = (f'Releasing “{esc(req)}” is costly — it is a combination we are short on. '
               + (f'Lower-harm alternative to offer instead: <strong>{esc(alt)}</strong> (we are over-stocked there).'
                  if alt else 'No over-stocked alternative is available to offer instead.')) if harmful \
            else f'Releasing “{esc(req)}” is reasonable — it is not a combination we are short on.'
        out += f'<div class="card"><h3>Should we release what they asked for?</h3><p>{rec}</p></div>'
    # Parse the counterparty snapshot into actual external vehicles, then rank each
    # against the certified combination-level shortage board.
    raw_inventory = st.get("inv_raw", "\n".join(st.get("inv", [])))
    candidates = _parse_external_trade_inventory(raw_inventory)
    unavail = set(st.get("unavail", []))

    scored = []
    for i, unit in enumerate(candidates):
        score, reason, shortage_qty = _score_external_trade_candidate(unit, short)
        # Older external units are preferred only as a tie-breaker: they may be easier
        # for the counterparty dealer to release. Business fit always dominates age.
        scored.append((i, unit, score, reason, shortage_qty))

    scored.sort(key=lambda t: (
        t[0] in unavail,             # available first
        -t[2],                       # strongest business fit
        -int(t[1].get("dis", 0) or 0),  # older first only within equal fit
        t[1].get("stock_number", ""),
        t[1].get("identity", ""),
    ))

    rows = []
    available = [t for t in scored if t[0] not in unavail]
    for rank, (i, unit, score, reason, shortage_qty) in enumerate(available, 1):
        tag = "Best ask" if rank == 1 else f"#{rank}"

        if unit.get("structured"):
            label = unit.get("identity") or unit.get("description")
            detail = []
            if unit.get("stock_number"):
                detail.append(f"Stock {unit['stock_number']}")
            if unit.get("description"):
                detail.append(unit["description"])
            if unit.get("dis"):
                detail.append(f"DIS {unit['dis']}")
            display = label + (" | " + " | ".join(detail) if detail else "")
        else:
            display = unit.get("identity", "")

        fit = f"{score} | {reason}"
        rows.append([
            esc(tag),
            esc(display),
            esc(fit),
            safe(_ws_btn(s, "/dealer-trade/their/unavailable", "idx", str(i), "Unavailable"))
        ])

    for i, unit, score, reason, shortage_qty in scored:
        if i not in unavail:
            continue
        display = unit.get("identity") or unit.get("description") or unit.get("raw", "")
        rows.append([
            safe(badge("stale", "unavailable")),
            esc(display),
            esc("?"),
            safe("")
        ])

    if candidates:
        parsed_note = (
            f'<p class="muted">{len(candidates)} external candidate'
            f'{"s" if len(candidates) != 1 else ""} parsed. '
            'Exact certified combination shortages rank ahead of model-level matches. '
            'External units do not become our supply until a trade is committed.</p>'
        )
        out += ('<div class="card"><h3>What we should ask for back (ranked)</h3>'
                + parsed_note
                + table(["Rank", "Their unit / combination", "Fit", ""], rows)
                + '</div>')
    else:
        out += empty("Paste their inventory to rank the best ask.")
    return out



def _our_trade(app, s, short, over):
    st = _ws_get(app, s.scope, "trade_our", {}) or {}
    combos = [lbl for _cid, lbl in _known_combos(app, s.scope)]
    entry = form("/dealer-trade/our",
                 '<label>Exact unit we need from them (external — we already have the sold customer)</label>'
                 '<input name=needed value="' + esc(st.get("needed", "")) + '" style="max-width:360px">'
                 '<label>What they are demanding from us (our inventory; leave blank if flexible)</label>'
                 + _datalist_input("demanded", "our_dem_combos", combos, value=st.get("demanded", ""),
                                   placeholder="select our combination"),
                 csrf=s.csrf_token, submit="Evaluate trade")
    out = ('<div class="card"><h2>Our Trade</h2><p class="muted">We know the unit we need. Protect what we give '
           'away while obtaining it.</p>' + entry + '</div>')
    demanded = st.get("demanded", "")
    if demanded:
        harmful = any(b["model"] in demanded.upper() or b["identity"] in demanded for b in short)
        alt = over[0]["identity"] if over else None
        rec = (f'They demand “{esc(demanded)}”, which we are short on — high business impact. '
               + (f'Best alternative to offer: <strong>{esc(alt)}</strong> (over-stocked).' if alt
                  else 'No over-stocked alternative is available to offer.')) if harmful \
            else f'They demand “{esc(demanded)}”, which is not a combination we are short on — acceptable to release.'
        out += f'<div class="card"><h3>Impact of their demand</h3><p>{rec}</p></div>'
    elif st.get("needed"):
        rows = [[esc(i + 1), esc(b["identity"]), esc(b["qty"])] for i, b in enumerate(over[:5])]
        out += ('<div class="card"><h3>Best units for us to release (they are flexible)</h3>'
                '<p class="muted">Ranked from our over-stock, lowest business harm first.</p>'
                + (table(["Rank", "Combination", "Over by"], rows) if rows
                   else empty("We have no over-stocked combination to release without harm.")) + '</div>')
    return out


def _ops_stack(app):
    """Locate the Phase 11 ops stack that carries the import orchestrator + source-id resolver, however the
    operator app was built (runtime serve sets app._p11; a Phase12/Phase11 fixture nests it under
    _pilot_stack.p11 or exposes it directly)."""
    for cand in (getattr(app, "_p11", None),
                 getattr(getattr(app, "_pilot_stack", None), "p11", None),
                 getattr(app, "_pilot_stack", None)):
        if cand is not None and hasattr(cand, "orch") and hasattr(cand, "source_id"):
            return cand
    return None


def _upload_dir(app):
    import os
    d = os.environ.get("ELITE_UPLOAD_DIR")
    if not d:
        dbp = os.environ.get("ELITE_DB_PATH")
        if dbp:
            d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(dbp))), "uploads")
        else:
            d = os.path.join(os.getcwd(), "uploads")
    os.makedirs(d, exist_ok=True)
    return d


def _run_upload(app, scope, contract_key, upload):
    """Stage a browser-uploaded file into the Elite uploads directory and run it through the EXISTING
    ingestion orchestrator. Never fabricates success — freshness only changes because the orchestrator
    records a successful import_run. The operator never sees or types a server path."""
    import os
    from ...errors import ValidationError
    from ...ops.intake import sanitize_filename, content_hash
    if not contract_key:
        return "No source selected; nothing was imported."
    if not upload or not upload[1]:
        return "Choose a file to upload first; nothing was imported."
    filename, data = upload
    try:
        safe = sanitize_filename(filename)               # strips directories, rejects traversal / null bytes
    except ValidationError as e:
        return f"{e.message} Nothing was imported."
    ops = _ops_stack(app)
    if ops is None:
        return "The import service is not available in this runtime; no data was changed."
    try:
        src_id = ops.source_id(contract_key)
    except Exception:   # noqa: BLE001
        return f"Unknown source '{contract_key}'; nothing was imported."
    # stage the uploaded bytes durably in the uploads folder (audit + operator never types a path)
    try:
        staged = os.path.join(_upload_dir(app), safe)
        with open(staged, "wb") as fh:
            fh.write(data)
    except Exception as e:   # noqa: BLE001
        return f"Could not stage the uploaded file: {e}. Nothing was imported."
    # decode CSV-family payloads as text for the orchestrator; binary (xlsx) is passed through as bytes.
    try:
        payload = data.decode("utf-8")
    except Exception:   # noqa: BLE001
        payload = data
    try:
        run = ops.orch.run(contract_key=contract_key, payload=payload, source_id=src_id, scope=scope,
                           initiated_by="operator", claimed_snapshot=("full" if contract_key == "service_loaner_fleet" else "partial"),
                           content_hash=content_hash(payload))
        state = (run["state"] if run else "UNKNOWN")
        if state in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
            if contract_key == "service_loaner_fleet" and run["import_batch_id"]:
                try:
                    from ...loaner.snapshot import SnapshotService

                    p6 = app.p9.p8.p7.p6
                    batch = ops.data.get_batch(run["import_batch_id"])
                    already_projected = (
                        p6.store.conn.execute(
                            "SELECT 1 FROM service_loaner_snapshot_reconciliation "
                            "WHERE import_batch_id=? AND store_scope=? LIMIT 1",
                            (batch.id, scope),
                        ).fetchone()
                        if batch else None
                    )
                    if batch and not already_projected:
                        accepted_rows = []
                        for obs in ops.data.list_observations(batch.id):
                            if obs is None or obs.acceptance_status != "accepted":
                                continue
                            row = dict(obs.raw_values or {})
                            normalized = obs.normalized_values or {}
                            row["rental_status"] = normalized.get("status") or row.get("status")
                            accepted_rows.append(row)
                        projector = SnapshotService(
                            p6.store, ops.data, ops.ingestion, app.stack.clock, scope
                        )
                        projector.reconcile(batch, accepted_rows)
                except Exception as e:
                    return (
                        f"Imported {safe} into {contract_key} - {state}, but the Service Loaner "
                        f"operating-fleet projection did not complete: {e}. Review required."
                    )
            # upload-resolution hook: record identity observations from the accepted rows; known vocabulary
            # resolves automatically, only genuinely-new raw values surface for human resolution. This records
            # observations only — it never interprets family/segment/order and never touches certified plans.
            id_note = ""
            try:
                from ...identity.translation import TranslationStore
                from ...identity.ingest import observe_source_rows
                from ...clock import to_utc_iso
                acc = [dict(o.raw_values or {}) for o in ops.data.list_observations(run["import_batch_id"])
                       if o is not None and o.acceptance_status == "accepted"]
                summ = observe_source_rows(TranslationStore(app.prefs, scope), contract_key, acc,
                                           as_of=to_utc_iso(app.stack.clock.now())[:10],
                                           proof_ref=f"{contract_key}:{safe}", actor="operator")
                n_new = len(summ["new_unresolved"])
                if n_new:
                    id_note = (f" Identity: {n_new} new source value(s) need resolution — open the Translation "
                               "Center from Data Health.")
                elif summ["recorded"]:
                    id_note = " Identity: all source values recognized."
            except Exception:   # noqa: BLE001 — identity observation must never fail an accepted import
                id_note = ""
            return f"Imported {safe} into {contract_key} - {state}.{id_note}"
        return (f"Import of {safe} did not complete ({state}); previous data is unchanged and freshness "
                "was not updated.")
    except Exception as e:   # noqa: BLE001
        return f"Import failed and nothing was changed: {e}"
