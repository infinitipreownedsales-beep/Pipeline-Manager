"""Service-Loaner Planned Requirement — the governed, additive, non-economic future need ("we will need N
more QX60 loaners") that CPO / ordering must account for as a SEPARATE dealership requirement.

It never mutates certified Retail demand and is never fabricated onto an exact color combination — the need
is recorded and carried at model level. A companion 'no additional need' acknowledgement lets management
resolve a model's future SL requirement to zero, so ordering can tell 'resolved: none' apart from
'unresolved' (the only state in which CPO must refuse to present a Retail-only order as complete).
"""
from __future__ import annotations

from ..render import page, esc, safe, table, badge, form, workspace_header, empty, disclosure, kv, metric, stat_row
from ..http import Response
from ...ordering.cross_domain import PlannedRequirementStore


def _now(app):
    from ...clock import to_utc_iso
    return to_utc_iso(app.stack.clock.now())


def _sl_engine_card(app, scope):
    """The Elite-calculated Service-Loaner plan (self-balancing), shown before any manual controls: fleet
    position, calculated requirement, source recommendation and human Why."""
    from ...loaner.self_balancing import build_requirement, human_why, source_label
    sb = build_requirement(app.stack.db.conn, scope, app.prefs)
    tone = {"no_target": "attention", "resolved_zero": "healthy", "resolved_need": "pending"}.get(sb.resolution, "pending")
    need_txt = ("— (set target)" if sb.resolution == "no_target"
                else str(sb.calculated_need) + (" (lower bound)" if sb.is_lower_bound and sb.calculated_need else ""))
    band = stat_row([metric(sb.current_active, "Current fleet"),
                     metric(sb.desired if sb.desired is not None else "not set", "Desired target"),
                     metric(sb.releasing_now, "Releasing now"),
                     metric(sb.remaining, "Expected to remain"),
                     metric(need_txt, "Calculated need", attn=(sb.resolution == "resolved_need"))])
    body = (band
            + f'<p style="margin:8px 0 2px">{badge(tone, source_label(sb))}</p>'
            + f'<p style="margin:4px 0"><strong>Why:</strong> {esc(human_why(sb))}</p>'
            + '<details><summary>Proof — calculated inputs</summary>'
            + kv([("Desired operating fleet", sb.desired if sb.desired is not None else "not set"),
                  ("Current active fleet", sb.current_active), ("Releasing now (governed exits)", sb.releasing_now),
                  ("Projected future exits (timing-gated)", sb.projected_future_exits),
                  ("Committed incoming SL supply", sb.committed_incoming),
                  ("Expected to remain", sb.remaining),
                  ("Units with unresolved in-service date", sb.unresolved_timing_units),
                  ("Calculated additional need", sb.calculated_need)]) + '</details>'
            + ('' if sb.desired is not None else
               '<p class="muted" style="font-size:12px">Set the desired fleet on the '
               '<a href="/service-loaner">Service Loaner board</a>.</p>')
            + '<p class="muted" style="font-size:12px">Month-by-month projection (exits/replacements by month) '
              'is pending authoritative lifecycle timing; the release-timing call stays gated until then.</p>')
    return '<div class="card"><h2 style="margin-top:4px">Elite calculated plan (self-balancing)</h2>' + body + '</div>'


def _retire_form(s, req_id):
    return safe(f'<form class="mut" method="post" action="/ordering/sl-requirements/retire">'
                f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                f'<input type=hidden name=id value="{esc(req_id)}">'
                f'<button type=submit class=secondary style="padding:3px 9px" '
                'onclick="return confirm(&quot;Retire this planned requirement? History is kept.&quot;)">'
                'Retire</button></form>')


def _effective_requirement_card(app, scope, store):
    """Reconcile the engine-calculated need with any management directive into ONE effective Service-Loaner
    acquisition requirement, and explain the conflict when they differ (e.g. Elite would add 0 because the
    fleet is above target, but management directed +3). The directive is additive — never a replacement — and
    never touches certified Retail demand."""
    from ...loaner.self_balancing import build_requirement
    sb = build_requirement(app.stack.db.conn, scope, app.prefs)
    calc = sb.calculated_need if sb.resolution == "resolved_need" else 0
    by_model = store.by_model()
    directive = sum(by_model.values())
    effective = calc + directive
    per = (" · ".join(f"{esc(m)} +{q}" for m, q in sorted(by_model.items()))) if by_model else "none"
    rows = kv([("Elite calculated need", calc if sb.resolution != "no_target" else "— (set target)"),
               ("Management directive (additive)", f"+{directive}" if directive else "0"),
               ("By model", safe(per)),
               ("Effective Service-Loaner acquisition requirement", effective)])
    if directive and calc == 0:
        note = ('<div class="callout"><strong>Directive above the calculated baseline.</strong> Elite would add '
                f'<strong>0</strong> because the fleet is at or above target, but management has directed '
                f'<strong>+{directive}</strong>. The effective requirement is <strong>{effective}</strong>; it is '
                'added to the dealership order and Retail demand is unchanged. '
                '<a href="/service-loaner?add=' + str(directive) + '">Rank the safest '
                f'{directive} New-Retail candidate(s)</a>.</div>')
    elif directive:
        note = ('<div class="callout">Management directive of <strong>+' + str(directive) + '</strong> is added on '
                'top of the calculated need of <strong>' + str(calc) + f'</strong> → effective <strong>{effective}'
                '</strong>. <a href="/service-loaner?add=' + str(directive) + '">Rank the safest candidate(s)</a>.</div>')
    else:
        note = ('<p class="muted" style="font-size:12px">No management directive is active — the effective '
                'requirement equals Elite’s calculated need.</p>')
    # honest economic-mix caveat: quantity is known, but WHICH models/vehicles is a Phase-4 economic call
    econ = ""
    try:
        from ...loaner.economics_readiness import phase4_gates, ready, missing
        gates = phase4_gates(app, scope)
        if effective and not ready(gates):
            miss = ", ".join(g.label for g in missing(gates))
            econ = ('<p class="muted" style="font-size:12px">' + safe(badge("attention", "economics pending"))
                    + ' The <strong>quantity</strong> is known, but the strongest <strong>model/vehicle mix</strong> '
                    'is a Phase-4 economic call that cannot run yet (missing: ' + esc(miss) + '). Until then, choose '
                    'the model by management intent and use the '
                    '<a href="/service-loaner">lowest Retail-harm shortlist</a> — not an economic optimum.</p>')
    except Exception:   # noqa: BLE001
        econ = ""
    return ('<div class="card"><h2 style="margin-top:4px">Effective requirement</h2>' + rows + note + econ + '</div>')


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

        parts = [workspace_header("Service Loaner — Planning & Directives",
                                  safe('<a href="/ordering/cpo">← CPO</a> · <a href="/service-loaner">Command Board</a>'))]
        parts.append(_sl_engine_card(app, s.scope))
        parts.append(_effective_requirement_card(app, s.scope, store))
        parts.append('<div class="card"><p class="muted">Elite calculates the Service-Loaner requirement above from '
                     'authoritative fleet state. A <strong>management directive</strong> below is an additive '
                     'override for cases where management has decided to add specific units — it is governed and '
                     'audited, kept at model level, never assigned to an exact colour, and never changes certified '
                     'Retail demand. It is not required to make ordering proceed.</p></div>')
        parts.append('<div class="card"><h2>Management directives</h2>' + listing
                     + disclosure("Record a management directive", add) + '</div>')
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
