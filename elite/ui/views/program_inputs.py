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
    tone = {"current": "healthy", "historical": "completed", "future": "pending", "unresolved": "attention",
            "retired": "stale"}
    return safe(badge(tone.get(st, "pending"), st))


def _row_actions(s, kind, e):
    if e.status == "retired":
        return safe('<span class="muted">retired</span>')
    retire = (f'<form class="mut" method="post" action="/program-inputs/retire">'
              f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
              f'<input type=hidden name=kind value="{esc(kind)}"><input type=hidden name=id value="{esc(e.id)}">'
              f'<button type=submit class=secondary style="padding:3px 9px" '
              'onclick="return confirm(&quot;Retire this record from active resolution? History is kept.&quot;)">'
              'Retire</button></form>')
    correct = (f'<form class="mut" method="post" action="/program-inputs/correct">'
               f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
               f'<input type=hidden name=kind value="{esc(kind)}"><input type=hidden name=id value="{esc(e.id)}">'
               f'<input name=value type=number placeholder="corrected $" style="max-width:110px"> '
               f'<button type=submit style="padding:3px 9px">Correct</button></form>')
    return safe(retire + " " + correct)


def _history_table(store, kind, cur_month, s):
    ents = sorted(store.entries(kind), key=lambda e: (e.effective_month, e.recorded_at), reverse=True)
    if not ents:
        return empty("No program values recorded yet.")
    rows = []
    for e in ents:
        vy = (f"{_val_cell(e.value)}" if kind == "icv" else
              safe(f'{_val_cell(e.value)}'
                   + (f' · {e.day_cap}d' if e.day_cap is not None else '')
                   + (f' · {e.mile_cap} mi' if e.mile_cap is not None else '')))
        prov = (e.provenance or "") + (" · corrects a prior record" if e.correction_of else "")
        rows.append([esc(e.effective_month or "—"), esc(e.model or "—"), esc(e.model_year or "all MY"),
                     esc(e.trim or "all trims"), vy, _status_badge(entry_status(e, cur_month)), esc(e.actor or "—"),
                     esc((e.recorded_at or "—")[:16].replace("T", " ")), esc(prov), _row_actions(s, kind, e)])
    return table(["Effective month", "Model", "MY", "Trim / scope", "Value", "Status", "Recorded by",
                  "Recorded at", "Provenance", ""], rows)


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


def phase4_gate_line(app, scope):
    """Conditional Phase-4 readiness line. NEVER the stale static claim that coverage is incomplete: if ICV /
    Velocity coverage is actually complete it says so and lists the REAL remaining economic gates (write-down
    policy, protection buffer, used-market evidence). When the engine is fully ready it says the economic
    ranking can proceed."""
    from ...loaner.economics_readiness import phase4_gates, ready, missing
    gates = phase4_gates(app, scope)
    unit_note = (' <span class="muted">Per-unit KEEP/PULL/SWAP economics are separate — they resolve for any '
                 'individual unit once that unit\'s own invoice and used-market evidence are present, and do not '
                 'wait on full program coverage.</span>')
    if ready(gates):
        return ('<p class="muted" style="font-size:12px">' + safe(badge("healthy", "ready"))
                + ' All required authoritative economic inputs are present — the Service-Loaner economic '
                'placement ranking can proceed under its certified contract (the ADD / acquisition ranking).'
                + unit_note + '</p>')
    miss = missing(gates)
    cov_incomplete = any(g.key in ("icv", "velocity") and not g.present for g in gates)
    lead = ("Historical program coverage is incomplete." if cov_incomplete
            else "Program coverage complete.")
    items = "; ".join(f"{esc(g.label)} ({esc(g.detail)})" for g in miss)
    return ('<p class="muted" style="font-size:12px">' + safe(badge("attention", "pending")) + f' {lead} '
            f'The economic placement (ADD) ranking stays Pending until these authoritative inputs exist: {items}.'
            + unit_note + '</p>')


def coverage_summary(app, scope, *, heading=True):
    """Read-only ICV/Velocity coverage banner for the active fleet — safe to embed on the Service Loaner board."""
    store = ProgramInputsStore(app.prefs, scope)
    earliest, models = _fleet_context(app, scope)
    cur = _cur_month(app)
    body = ('<div style="font-size:13px;margin:3px 0">' + _coverage_line(store, "icv", earliest, cur, models) + '</div>'
            '<div style="font-size:13px;margin:3px 0">' + _coverage_line(store, "velocity", earliest, cur, models) + '</div>'
            + phase4_gate_line(app, scope))
    head = '<h3 style="margin:2px 0 4px">Program coverage</h3>' if heading else ""
    return head + body


def _sl_fleet_vin_map(app, scope):
    """{normalized VIN: UnitIntel} for the active fleet — for vehicle labels beside each stored invoice."""
    try:
        from ...loaner.intelligence import build_intelligence
        intel = build_intelligence(app.stack.db.conn, scope, app.prefs, app.stack.clock)
        return {(u.vin or "").strip().upper(): u for u in intel.units}
    except Exception:   # noqa: BLE001
        return {}


def _invoice_readback(app, s, pol):
    """The visible list of stored per-VIN invoice overrides — VIN / Vehicle / Invoice / Recorded by / Recorded
    at / Status / Action. This is the readback that was missing (a saved invoice appeared to vanish); each row
    can be retired, and re-saving the same VIN corrects it (history kept in policy audit)."""
    records = pol.invoice_records()
    units = _sl_fleet_vin_map(app, s.scope)
    fleet_vins = set(units)
    on_file = {r["vin"] for r in records}
    missing = sorted(fleet_vins - on_file)
    cov = stat_row([metric(len(records), "Invoices on file"),
                    metric(len(fleet_vins) or "—", "Active fleet VINs"),
                    metric(len(missing) if fleet_vins else "—", "Fleet VINs still unresolved",
                           attn=bool(fleet_vins and missing))])
    if not records:
        listing = empty("No per-unit invoices recorded yet. Add one below, or bulk-import the checklist CSV.")
    else:
        rows = []
        for r in records:
            u = units.get(r["vin"])
            vehicle = (u.model if u and u.model else "—")
            retire = (f'<form class="mut" method="post" action="/program-inputs/invoice/retire">'
                      f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                      f'<input type=hidden name=vin value="{esc(r["vin"])}">'
                      f'<button type=submit class=secondary style="padding:3px 9px" '
                      'onclick="return confirm(&quot;Retire this invoice? The write-down basis for this VIN '
                      'becomes unresolved.&quot;)">Retire</button></form>')
            rows.append([esc(r["vin"]), esc(vehicle), f'${r["amount"]:,}',
                         esc("operator-provided invoice entry"), esc(r["actor"] or "—"),
                         esc((r["at"] or "—")[:16].replace("T", " ")),
                         safe(badge("healthy", "active")), safe(retire)])
        listing = table(["VIN", "Vehicle", "Original invoice", "Source", "Recorded by", "Recorded at",
                         "Status", "Action"], rows)
    return cov + listing


def _invoice_import_form(s):
    return (f'<form method="post" action="/program-inputs/invoice/import" enctype="multipart/form-data">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            '<p class="muted" style="font-size:12px">One-time bulk load of the completed invoice checklist. '
            'Columns recognized: <code>Full VIN</code> and <code>Original Invoice</code>. Idempotent — a VIN '
            'whose invoice already matches is skipped, so re-running is safe.</p>'
            '<input type=file name=file accept=".csv,text/csv" required style="margin:6px 0"> '
            '<button type=submit>Import invoice CSV</button></form>')


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
        my_field = ('<label>Model year (optional — blank = all model years; ICV/Velocity can differ by MY)</label>'
                    '<input name=model_year type=number min=2000 max=2100 style="max-width:140px" '
                    'placeholder="e.g. 2026">')
        icv_form = form("/program-inputs/icv",
                        month_field + '<label>Model</label>' + model_opts + my_field
                        + '<label>Trim / scope (optional — blank = all trims)</label>'
                        '<input name=trim style="max-width:220px">'
                        '<label>ICV $ (leave blank for unresolved — never stored as $0)</label>'
                        '<input name=value type=number style="max-width:160px">'
                        '<label>Provenance / source (optional)</label><input name=provenance style="max-width:320px">',
                        csrf=s.csrf_token, submit="Add ICV value")
        vel_form = form("/program-inputs/velocity",
                        month_field + '<label>Model</label>' + model_opts + my_field
                        + '<label>Trim / scope (optional)</label><input name=trim style="max-width:220px">'
                        '<label>Velocity $ (blank = unresolved)</label><input name=value type=number style="max-width:160px">'
                        '<label>Day cap</label><input name=day_cap type=number style="max-width:120px">'
                        '<label>Mileage cap</label><input name=mile_cap type=number style="max-width:140px">'
                        '<label>Provenance / source (optional)</label><input name=provenance style="max-width:320px">',
                        csrf=s.csrf_token, submit="Add Velocity terms")
        recon_form = form("/program-inputs/recon",
                          month_field + '<label>Model</label>' + model_opts + my_field
                          + '<label>Trim / scope (optional — blank = all trims)</label>'
                          '<input name=trim style="max-width:220px">'
                          '<label>Expected reconditioning $ (blank = unresolved; never stored as $0). This is the '
                          'business-approved expected recon that feeds the placement front-end gross.</label>'
                          '<input name=value type=number style="max-width:160px">'
                          '<label>Provenance / source (optional)</label><input name=provenance style="max-width:320px">',
                          csrf=s.csrf_token, submit="Add recon value")

        parts = [workspace_header("Service Loaner — Program Inputs",
                                  safe('<a href="/service-loaner">← Command Board</a> · <a href="/data">Data</a>'))]
        parts.append('<div class="card"><h2>Coverage</h2>'
                     + stat_row([metric(earliest or "unknown", "Earliest active in-service"),
                                 metric(len(models), "Active models")])
                     + coverage_summary(app, s.scope, heading=False) + '</div>')
        parts.append('<div class="card"><h2>ICV program history</h2>'
                     '<p class="muted">Effective-dated by model year. A newer value supersedes prospectively and '
                     'never rewrites a prior period; correct or retire an erroneous record (history is kept). '
                     'Unresolved is never $0.</p>' + _history_table(store, "icv", cur, s)
                     + disclosure("Add ICV value", icv_form) + '</div>')
        parts.append('<div class="card"><h2>Velocity program history</h2>' + _history_table(store, "velocity", cur, s)
                     + disclosure("Add Velocity terms", vel_form) + '</div>')
        parts.append('<div class="card"><h2>Recon program history</h2>'
                     '<p class="muted">Governed expected reconditioning $ per model, effective-dated (the placement '
                     'economics use this — a higher recon lowers front-end gross and can change which candidates '
                     'stay commandable). Absent → an explicit governed default band, never a silent constant. '
                     'Unresolved is never $0.</p>' + _history_table(store, "recon", cur, s)
                     + disclosure("Add recon value", recon_form) + '</div>')
        parts.append(_policy_card(app, s))
        flash, s.flash = s.flash, None
        return Response(page("Program Inputs", "".join(parts), ctx=app.ctx(s), active_path="/service-loaner",
                             flash=flash, wide=True, hide_title=True))

    def _policy_card(app, s):
        """Governed Service-Loaner economic POLICY — the only two economic inputs Elite cannot derive: the
        per-model write-down and a flat protection buffer. Saving is the explicit apply (no scenario writes)."""
        from ...loaner.sl_policy import SLPolicyStore
        from .operator import _known_models, _select
        from ...loaner.sl_policy import SLPolicyStore as _SLP
        pol = SLPolicyStore(app.prefs, s.scope)
        buf_days = pol.protection_buffer_days()
        tenure = pol.projected_tenure_months()
        cur_month = _cur_month(app)
        rate, rate_src = pol.writedown_monthly_rate(cur_month)
        rate_rows = [[esc(e.get("effective_month") or "—"), f"{float(e['rate']):g}%/mo"]
                     for e in sorted(pol.writedown_rate_entries(), key=lambda e: e.get("effective_month", ""))] or None
        wtable = (table(["Effective month", "Rate"], rate_rows) if rate_rows
                  else empty(f"No governed rate recorded — using the default {rate:g}%/mo of invoice."))
        wform = form("/program-inputs/writedown",
                     '<label>Effective month (the rate applies from this month forward)</label>'
                     f'<input name=effective_month type=month value="{esc(cur_month)}" style="max-width:200px" required>'
                     '<label>Monthly write-down rate (% of original INVOICE per month — the authoritative basis '
                     'is invoice, never ICV/MSRP; no cap; accrues daily)</label>'
                     f'<input name=rate type=number min=0 step="0.01" value="1.25" style="max-width:160px" required>',
                     csrf=s.csrf_token, submit="Save write-down rate")
        inv_form = form("/program-inputs/invoice",
                        '<label>VIN</label><input name=vin style="max-width:240px" required>'
                        '<label>Original authoritative invoice $ (the write-down basis, when the source lacks it)'
                        '</label><input name=amount type=number min=0 style="max-width:160px" required>',
                        csrf=s.csrf_token, submit="Save unit invoice")
        tform = form("/program-inputs/tenure",
                     '<label>Projected loaner-program tenure (MONTHS) — turns a monthly % write-down into a '
                     'cumulative dollar figure. This is program tenure, NOT the 240-day total-to-retail deadline.'
                     f'</label><input name=months type=number min=1 style="max-width:160px" '
                     f'value="{esc(tenure if tenure is not None else "")}" required>',
                     csrf=s.csrf_token, submit="Save projected tenure (months)")
        bform = form("/program-inputs/buffer",
                     '<label>Protection buffer — DAYS (release-timing reserve protecting the 240-day '
                     'total-to-retail deadline; this is a day count, never dollars)</label>'
                     f'<input name=days type=number min=0 style="max-width:160px" '
                     f'value="{esc(buf_days if buf_days is not None else "")}" required>',
                     csrf=s.csrf_token, submit="Save protection buffer (days)")
        return ('<div class="card"><h2>Service-Loaner economic policy</h2>'
                '<p class="muted">Governed dealership policy — Elite derives everything else (ICV / Velocity are '
                'above; used gross / DTS come from your preowned evidence). <strong>Write-down</strong> is a dollar '
                '(or percent-of-ICV) input that feeds the placement DOLLAR economics. The <strong>protection '
                'buffer</strong> is a DAY count that feeds the release-timing backsolve — the two live in '
                'different dimensions and are never mixed. Saving applies immediately; scenario what-ifs never '
                'overwrite policy.</p>'
                + f'<h3 style="margin:8px 0 4px">Write-down rate — currently {esc(rate_src)}</h3>' + wtable
                + disclosure("Set write-down rate (effective-dated)", wform)
                + '<h3 style="margin:12px 0 4px">Per-unit original invoice (write-down basis)</h3>'
                + '<p class="muted" style="font-size:12px">The write-down is a % of the vehicle\'s original '
                'authoritative invoice. When the inventory source carries it, Elite reads it automatically; use '
                'this to supply an authoritative invoice the source is missing. Never MSRP/ICV. Saved invoices '
                'are listed below and can be retired or re-saved.</p>'
                + _invoice_readback(app, s, pol)
                + disclosure("Add / correct a unit invoice", inv_form)
                + disclosure("Bulk-import the invoice checklist CSV", _invoice_import_form(s))
                + '<h3 style="margin:12px 0 4px">Projected program tenure (months)</h3><p style="margin:2px 0">'
                + (f'<strong>{tenure} months</strong>' if tenure is not None else safe(badge("unresolved", "not set")))
                + ' <span class="muted" style="font-size:12px">— a monthly % write-down needs this to become a '
                'cumulative dollar figure; changing it re-computes the economics. Scenario what-ifs never overwrite '
                'it.</span></p>' + disclosure("Set projected tenure (months)", tform)
                + '<h3 style="margin:12px 0 4px">Protection buffer (days · release-timing)</h3><p style="margin:2px 0">'
                + (f'<strong>{buf_days} days</strong>' if buf_days is not None else safe(badge("unresolved", "not set")))
                + '</p>' + disclosure("Set protection buffer (days)", bform) + '</div>')

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
                  model_year=req.f("model_year", "").strip(),
                  actor=s.principal_id, recorded_at=_now(app), provenance=req.f("provenance", "").strip(), **kw)
        my = req.f("model_year", "").strip()
        s.flash = f"{kind.upper()} value recorded (effective {month}{', MY' + my if my else ''}; history retained)."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/icv")
    def program_icv(app, req):
        return _add(app, req, "icv")

    @app.post("/program-inputs/velocity")
    def program_velocity(app, req):
        return _add(app, req, "velocity")

    @app.post("/program-inputs/recon")
    def program_recon(app, req):
        return _add(app, req, "recon")

    @app.post("/program-inputs/writedown")
    def program_writedown(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.sl_policy import SLPolicyStore
        try:
            r = SLPolicyStore(app.prefs, s.scope).set_writedown_rate(
                req.f("rate", ""), effective_month=req.f("effective_month", "").strip(),
                actor=s.principal_id, at=_now(app))
            s.flash = f"Write-down rate saved: {r:g}%/mo of invoice (applied)."
        except ValueError as e:
            s.flash = f"Not saved — {e}."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/invoice")
    def program_invoice(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.sl_policy import SLPolicyStore
        try:
            SLPolicyStore(app.prefs, s.scope).set_invoice(req.f("vin", ""), req.f("amount", ""),
                                                          actor=s.principal_id, at=_now(app))
            s.flash = "Unit invoice saved (applied) — used as the write-down basis."
        except ValueError as e:
            s.flash = f"Not saved — {e}."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/invoice/retire")
    def program_invoice_retire(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.sl_policy import SLPolicyStore
        removed = SLPolicyStore(app.prefs, s.scope).remove_invoice(req.f("vin", ""), actor=s.principal_id, at=_now(app))
        s.flash = ("Invoice retired — the write-down basis for that VIN is now unresolved." if removed
                   else "No active invoice was found for that VIN.")
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/invoice/import")
    def program_invoice_import(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.sl_policy import SLPolicyStore, parse_invoice_csv
        f = req.files.get("file")
        if not f or not f[1]:
            s.flash = "No CSV file was uploaded; nothing was imported."
            return Response.redirect("/program-inputs")
        rows = parse_invoice_csv(f[1])
        if not rows:
            s.flash = ("Could not read any invoice rows — the CSV needs a VIN column (Full VIN / VIN) and an "
                       "invoice column (Original Invoice / Invoice). Nothing was imported.")
            return Response.redirect("/program-inputs")
        res = SLPolicyStore(app.prefs, s.scope).bulk_set_invoices(rows, actor=s.principal_id, at=_now(app))
        s.flash = (f"Imported {res['applied']} invoice(s); {res['skipped_existing']} already on file, "
                   f"{res['skipped_invalid']} skipped (missing VIN or non-positive amount). Unit economics "
                   "recomputed on the Service Loaner board.")
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/tenure")
    def program_tenure(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.sl_policy import SLPolicyStore
        try:
            SLPolicyStore(app.prefs, s.scope).set_projected_tenure_months(req.f("months", ""),
                                                                          actor=s.principal_id, at=_now(app))
            s.flash = "Projected program tenure saved (applied) — used to accrue the monthly write-down."
        except ValueError as e:
            s.flash = f"Not saved — {e}."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/buffer")
    def program_buffer(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...loaner.sl_policy import SLPolicyStore
        try:
            SLPolicyStore(app.prefs, s.scope).set_protection_buffer_days(req.f("days", ""),
                                                                         actor=s.principal_id, at=_now(app))
            s.flash = "Protection buffer (days) saved (applied) — used for release timing, not dollar economics."
        except ValueError as e:
            s.flash = f"Not saved — {e}."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/retire")
    def program_retire(app, req):
        s = req.session
        app.require(s, "workspace.view")
        kind = req.f("kind", "")
        if kind in ("icv", "velocity"):
            ProgramInputsStore(app.prefs, s.scope).retire(kind, req.f("id", ""), actor=s.principal_id, at=_now(app))
            s.flash = "Record retired from active resolution (history preserved)."
        return Response.redirect("/program-inputs")

    @app.post("/program-inputs/correct")
    def program_correct(app, req):
        s = req.session
        app.require(s, "workspace.view")
        kind = req.f("kind", "")
        v = req.f("value", "").strip()
        if kind in ("icv", "velocity") and v != "":
            ProgramInputsStore(app.prefs, s.scope).correct(kind, req.f("id", ""), actor=s.principal_id,
                                                           recorded_at=_now(app), value=parse_value(v))
            s.flash = "Record corrected — a superseding value was recorded and the original retired (lineage kept)."
        return Response.redirect("/program-inputs")
