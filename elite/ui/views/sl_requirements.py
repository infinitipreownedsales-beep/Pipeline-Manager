"""Service-Loaner Planned Requirement — the governed, additive, non-economic future need ("we will need N
more QX60 loaners") that CPO / ordering must account for as a SEPARATE dealership requirement.

It never mutates certified Retail demand and is never fabricated onto an exact color combination — the need
is recorded and carried at model level. A companion 'no additional need' acknowledgement lets management
resolve a model's future SL requirement to zero, so ordering can tell 'resolved: none' apart from
'unresolved' (the only state in which CPO must refuse to present a Retail-only order as complete).
"""
from __future__ import annotations

from ..render import page, esc, safe, table, badge, form, workspace_header, empty, disclosure
from ..http import Response
from ...ordering.cross_domain import PlannedRequirementStore


def _now(app):
    from ...clock import to_utc_iso
    return to_utc_iso(app.stack.clock.now())


def _retire_form(s, req_id):
    return safe(f'<form class="mut" method="post" action="/ordering/sl-requirements/retire">'
                f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                f'<input type=hidden name=id value="{esc(req_id)}">'
                f'<button type=submit class=secondary style="padding:3px 9px" '
                'onclick="return confirm(&quot;Retire this planned requirement? History is kept.&quot;)">'
                'Retire</button></form>')


def register(app):
    def _model_options(app, scope):
        from .operator import _known_models
        return [(m, m) for m in (_known_models(app, scope) or [])]

    @app.get("/ordering/sl-requirements")
    def sl_requirements(app, req):
        s = req.session
        app.require(s, "workspace.view")
        store = PlannedRequirementStore(app.prefs, s.scope)
        from .operator import _select
        model_opts = _select("model", _model_options(app, s.scope))

        # active planned requirements
        rows = []
        for e in store.active():
            rows.append([esc(e.model), esc(str(e.quantity)), esc(e.model_year or "all MY"),
                         esc(e.trim or "all trims"), esc(e.required_by or "—"), esc(e.reason or "—"),
                         esc(e.actor or "—"), esc((e.recorded_at or "—")[:16].replace("T", " ")),
                         _retire_form(s, e.id)])
        listing = (table(["Model", "Qty", "MY", "Trim", "Required by", "Reason", "Recorded by", "Recorded at", ""],
                         rows) if rows else empty("No planned Service-Loaner requirements are recorded."))

        add = form("/ordering/sl-requirements/add",
                   '<label>Model</label>' + model_opts
                   + '<label>Additional loaners needed (whole number — never zero; use “No additional need” below '
                     'to resolve a model as none)</label><input name=quantity type=number min=1 '
                     'style="max-width:120px" required>'
                     '<label>Model year (optional)</label><input name=model_year type=number min=2000 max=2100 '
                     'style="max-width:140px" placeholder="e.g. 2026">'
                     '<label>Trim (optional)</label><input name=trim style="max-width:220px">'
                     '<label>Required by (optional)</label><input name=required_by type=month style="max-width:200px">'
                     '<label>Reason / authority (who directed this, and why)</label>'
                     '<input name=reason style="max-width:420px" placeholder="e.g. GM directive — winter loaner demand">',
                   csrf=s.csrf_token, submit="Record planned requirement")

        # governed 'no additional need' acknowledgement
        ack_active = sorted(store.acknowledged_models())
        ack_chips = (" ".join(f'{badge("healthy", m)} ' for m in ack_active)
                     if ack_active else '<span class="muted">none recorded</span>')
        clear_forms = "".join(
            f'<form class="mut" method="post" action="/ordering/sl-requirements/ack-clear">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}"><input type=hidden name=model value="{esc(m)}">'
            f'<button type=submit class=secondary style="padding:2px 8px">Reopen {esc(m)}</button></form> '
            for m in ack_active)
        ack = form("/ordering/sl-requirements/ack",
                   '<label>Model</label>' + _select("model", _model_options(app, s.scope))
                   + '<p class="muted" style="font-size:12px">Records that no additional loaners of this model are '
                     'needed. This RESOLVES the model’s future Service-Loaner requirement to zero so CPO stops '
                     'flagging it as incomplete.</p>',
                   csrf=s.csrf_token, submit="Confirm no additional need")

        parts = [workspace_header("Service Loaner — Planned Requirement",
                                  safe('<a href="/ordering/cpo">← CPO</a> · <a href="/service-loaner">Command Board</a>'))]
        parts.append('<div class="card"><p class="muted">A planned Service-Loaner requirement is an additive future '
                     'need that ordering must satisfy <strong>in addition to</strong> certified Retail demand. It is '
                     'kept at model level — it is never assigned to an exact color combination here, and it never '
                     'changes certified Retail demand math.</p></div>')
        parts.append('<div class="card"><h2>Active planned requirements</h2>' + listing
                     + disclosure("Record a planned requirement", add) + '</div>')
        parts.append('<div class="card"><h2>No additional need</h2>'
                     '<p style="margin:2px 0">Resolved as “none”: ' + ack_chips + '</p>'
                     + (('<p style="margin:6px 0">' + clear_forms + '</p>') if clear_forms else "")
                     + disclosure("Confirm no additional need for a model", ack) + '</div>')
        flash, s.flash = s.flash, None
        return Response(page("Planned Requirement", "".join(parts), ctx=app.ctx(s), active_path="/ordering",
                             flash=flash, wide=True, hide_title=True))

    @app.post("/ordering/sl-requirements/add")
    def sl_requirements_add(app, req):
        s = req.session
        app.require(s, "workspace.view")
        store = PlannedRequirementStore(app.prefs, s.scope)
        model = (req.f("model", "") or "").strip()
        qty = (req.f("quantity", "") or "").strip()
        if not model:
            s.flash = "Choose a model; nothing was recorded."
            return Response.redirect("/ordering/sl-requirements")
        try:
            store.add(model=model, quantity=qty, actor=s.principal_id, recorded_at=_now(app),
                      model_year=req.f("model_year", "").strip(), trim=req.f("trim", "").strip(),
                      required_by=req.f("required_by", "").strip(), reason=req.f("reason", "").strip())
        except ValueError as e:
            s.flash = f"Not recorded — {e}."
            return Response.redirect("/ordering/sl-requirements")
        s.flash = f"Planned Service-Loaner requirement recorded for {model.upper()} (model-level; additive to Retail)."
        return Response.redirect("/ordering/sl-requirements")

    @app.post("/ordering/sl-requirements/retire")
    def sl_requirements_retire(app, req):
        s = req.session
        app.require(s, "workspace.view")
        PlannedRequirementStore(app.prefs, s.scope).retire(req.f("id", ""), actor=s.principal_id, at=_now(app))
        s.flash = "Planned requirement retired (history preserved)."
        return Response.redirect("/ordering/sl-requirements")

    @app.post("/ordering/sl-requirements/ack")
    def sl_requirements_ack(app, req):
        s = req.session
        app.require(s, "workspace.view")
        model = (req.f("model", "") or "").strip()
        if model:
            PlannedRequirementStore(app.prefs, s.scope).acknowledge_no_need(model, actor=s.principal_id, at=_now(app))
            s.flash = f"Recorded: no additional {model.upper()} loaners needed — future requirement resolved as none."
        return Response.redirect("/ordering/sl-requirements")

    @app.post("/ordering/sl-requirements/ack-clear")
    def sl_requirements_ack_clear(app, req):
        s = req.session
        app.require(s, "workspace.view")
        model = (req.f("model", "") or "").strip()
        if model:
            PlannedRequirementStore(app.prefs, s.scope).clear_acknowledgement(model)
            s.flash = f"{model.upper()} reopened — its future Service-Loaner requirement is unresolved again."
        return Response.redirect("/ordering/sl-requirements")
