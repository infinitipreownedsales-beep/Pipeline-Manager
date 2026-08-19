"""Service-Loaner Program Inputs — effective-dated ICV / Velocity history, reachable cleanly from both
Service Loaners and Data (not buried in an engineering page).

A durable month picker (native <input type="month">) selects any legitimate historical or future effective
month — no fixed recent-month window. Values are effective-dated and append-only: a newer value supersedes
prospectively and never rewrites a prior period. UNKNOWN is never rendered as $0. A read-only coverage summary
tells the operator whether program history actually covers the active fleet's lifecycle; economics are not
called authoritative while required coverage is incomplete.
"""
from __future__ import annotations

from ..render import page, esc, safe, table, badge, form, workspace_header, metric, stat_row, empty, disclosure
from ..http import Response
from ...loaner.program_inputs import (ProgramInputsStore, parse_value, entry_status, coverage, valid_month)


def _now(app):
    from ...clock import to_utc_iso
    return to_utc_iso(app.stack.clock.now())

def _cur_month(app):
    return _now(app)[:7]


def _fleet_context(app, scope):
    """(earliest active in-service month, active models) from the certified/authoritative fleet intelligence."""
    try:
        from ...loaner.intelligence import build_intelligence
        intel = build_intelligence(app.stack.db.conn, scope, app.prefs, app.stack.clock)
        months = [u.in_service_date[:7] for u in intel.units if u.in_service_date]
        models = [m for m, _ in intel.composition]
        return (min(months) if months else None), models
    except Exception:   # noqa: BLE001
        return None, []


def _val_cell(v):
    return safe(badge("unresolved", "unresolved")) if v is None else f"${v:,}"


def _status_badge(st):
    tone = {"current": "healthy", "historical": "completed", "future": "pending", "unresolved": "attention"}
    return safe(badge(tone.get(st, "pending"), st))


def _history_table(store, kind, cur_month):
    ents = sorted(store.entries(kind), key=lambda e: (e.effective_month, e.recorded_at), reverse=True)
    if not ents:
        return empty("No program values recorded yet.")
    rows = []
    for e in ents:
        vy = (f"{_val_cell(e.value)}" if kind == "icv" else
              safe(f'{_val_cell(e.value)}'
                   + (f' · {e.day_cap}d' if e.day_cap is not None else '')
                   + (f' · {e.mile_cap} mi' if e.mile_cap is not None else '')))
        rows.append([esc(e.effective_month or "—"), esc(e.model or "—"), esc(e.trim or "all trims"),
                     vy, _status_badge(entry_status(e, cur_month)), esc(e.actor or "—"),
                     esc((e.recorded_at or "—")[:16].replace("T", " ")), esc(e.provenance or "")])
    return table(["Effective month", "Model", "Trim / scope", "Value", "Status", "Recorded by", "Recorded at",
                  "Provenance"], rows)


def _coverage_line(store, kind, earliest, cur, models):
    cov = coverage(store, kind, earliest, cur, models=tuple(models))
    label = kind.upper()
    if cov["status"] == "complete":
        return f'{badge("healthy", "complete")} {label} coverage complete back to {esc(cov["earliest"])}.'
    if cov["status"] == "unknown":
        return f'{badge("unresolved", "unknown")} {label} coverage cannot be assessed — {esc(cov.get("reason", ""))}.'
    miss = cov["missing"]
    span = (esc(miss[0]) if miss[0] == miss[1] else f'{esc(miss[0])}–{esc(miss[1])}') if miss else "—"
    return (f'{badge("attention", "incomplete")} {label} coverage incomplete — earliest active in-service month '
            f'{esc(cov["earliest"] or "unknown")}; missing program periods: {span}.')


def coverage_summary(app, scope, *, heading=True):
    """Read-only ICV/Velocity coverage banner for the active fleet — safe to embed on the Service Loaner board."""
    store = ProgramInputsStore(app.prefs, scope)
    earliest, models = _fleet_context(app, scope)
    cur = _cur_month(app)
    body = ('<div style="font-size:13px;margin:3px 0">' + _coverage_line(store, "icv", earliest, cur, models) + '</div>'
            '<div style="font-size:13px;margin:3px 0">' + _coverage_line(store, "velocity", earliest, cur, models) + '</div>'
            '<p class="muted" style="font-size:12px">Phase-4 economics are not authoritative while required '
            'historical program coverage is incomplete.</p>')
    head = '<h3 style="margin:2px 0 4px">Program coverage</h3>' if heading else ""
    return head + body


def register(app):
    @app.get("/program-inputs")
    def program_inputs(app, req):
        s = req.session
        app.require(s, "workspace.view")
        store = ProgramInputsStore(app.prefs, s.scope)
        cur = _cur_month(app)
        earliest, models = _fleet_context(app, s.scope)
        from .operator import _known_models, _select
        model_opts = _select("model", [(m, m) for m in (_known_models(app, s.scope) or [])])
        # durable native month picker — any legitimate historical/future month, no fixed window
        month_field = ('<label for=effm>Effective month</label>'
                       f'<input id=effm type=month name=effective_month value="{esc(cur)}" '
                       'style="max-width:200px" required>')
        icv_form = form("/program-inputs/icv",
                        month_field + '<label>Model</label>' + model_opts
                        + '<label>Trim / scope (optional — blank = all trims)</label>'
                        '<input name=trim style="max-width:220px">'
                        '<label>ICV $ (leave blank for unresolved — never stored as $0)</label>'
                        '<input name=value type=number style="max-width:160px">'
                        '<label>Provenance / source (optional)</label><input name=provenance style="max-width:320px">',
                        csrf=s.csrf_token, submit="Add ICV value")
        vel_form = form("/program-inputs/velocity",
                        month_field + '<label>Model</label>' + model_opts
                        + '<label>Trim / scope (optional)</label><input name=trim style="max-width:220px">'
                        '<label>Velocity $ (blank = unresolved)</label><input name=value type=number style="max-width:160px">'
                        '<label>Day cap</label><input name=day_cap type=number style="max-width:120px">'
                        '<label>Mileage cap</label><input name=mile_cap type=number style="max-width:140px">'
                        '<label>Provenance / source (optional)</label><input name=provenance style="max-width:320px">',
                        csrf=s.csrf_token, submit="Add Velocity terms")

        parts = [workspace_header("Service Loaner — Program Inputs",
                                  safe('<a href="/service-loaner">← Command Board</a> · <a href="/data">Data</a>'))]
        parts.append('<div class="card"><h2>Coverage</h2>'
                     + stat_row([metric(earliest or "unknown", "Earliest active in-service"),
                                 metric(len(models), "Active models")])
                     + coverage_summary(app, s.scope, heading=False) + '</div>')
        parts.append('<div class="card"><h2>ICV program history</h2>'
                     '<p class="muted">Effective-dated. A newer value supersedes prospectively and never rewrites '
                     'a prior period. Unresolved is never $0.</p>' + _history_table(store, "icv", cur)
                     + disclosure("Add ICV value", icv_form) + '</div>')
        parts.append('<div class="card"><h2>Velocity program history</h2>' + _history_table(store, "velocity", cur)
                     + disclosure("Add Velocity terms", vel_form) + '</div>')
        flash, s.flash = s.flash, None
        return Response(page("Program Inputs", "".join(parts), ctx=app.ctx(s), active_path="/service-loaner",
                             flash=flash, wide=True, hide_title=True))

    def _add(app, req, kind):
        s = req.session
        app.require(s, "workspace.view")
        store = ProgramInputsStore(app.prefs, s.scope)
        month = (req.f("effective_month", "") or "").strip()
        if not valid_month(month):
            s.flash = "Enter a valid effective month (YYYY-MM); nothing was recorded."
            return Response.redirect("/program-inputs")
        kw = {}
        if kind == "velocity":
            kw = {"day_cap": parse_value(req.f("day_cap", "")), "mile_cap": parse_value(req.f("mile_cap", ""))}
        store.add(kind, effective_month=month, model=req.f("model", ""), trim=req.f("trim", ""),
                  value=parse_value(req.f("value", "")),          # UNKNOWN stays None; explicit 0 stays 0
                  actor=s.principal_id, recorded_at=_now(app), provenance=req.f("provenance", "").strip(), **kw)
        s.flash = f"{kind.upper()} value recorded (effective {month}; history retained)."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/icv")
    def program_icv(app, req):
        return _add(app, req, "icv")

    @app.post("/program-inputs/velocity")
    def program_velocity(app, req):
        return _add(app, req, "velocity")
