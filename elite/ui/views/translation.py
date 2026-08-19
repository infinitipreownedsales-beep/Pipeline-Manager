"""Translation & Identity Center — the authorized, user-maintainable maintenance surface (`/admin/translation`).

Governance boundary (enforced here):
  * The GET view is READ-ONLY. Opening this page never creates or approves identity truth.
  * Identity is created only through an explicit, capability-gated, idempotent initialization/import action, or
    through explicit human resolve/approve/retire — each requiring the `identity.govern` capability and each
    written to the append-only audit trail (who + when), with prior state preserved and nothing hard-deleted.
  * Source-backed OBSERVATIONS (raw codes, colours the chart itself displays) are imported as truth; INTERPRETATION
    (SAME FAMILY / generation segment / VARIANT OF BASE / preferred order) is `proposed` until a person approves it.
"""
from __future__ import annotations

from ..render import (page, esc, safe, table, kv, badge, metric, stat_row, workspace_header, esc_text, form)
from ..http import Response
from ...identity.translation import TranslationStore, SemanticMapping, FamilyKey
from ...identity import seed_infiniti as SEED
from ...audit import make_event

GOVERN = "identity.govern"


def _store(app, scope):
    return TranslationStore(app.prefs, scope)          # READ-ONLY construction — never seeds


def _now(app):
    from ...clock import to_utc_iso
    return to_utc_iso(app.stack.clock.now())[:19].replace("T", " ")


def _gov_event(app, s, action, target, *, result="success"):
    """Write the mutation to the system append-only audit trail (who / when), in addition to the store's own
    before/after history."""
    try:
        ev = make_event(app.stack.clock, app.environment, s.principal_id, f"identity.{action}",
                        result=result, target_ref=target, scope=s.scope)
        app.stack.audit.append(app.stack.db.conn, ev)
    except Exception:   # noqa: BLE001 — audit failure must not corrupt the governed store write already done
        pass


def register(app):
    @app.get("/admin/translation")
    def translation_center(app, req):
        s = req.session
        app.require(s, "workspace.view")               # viewing requires only read access; it mutates nothing
        st = _store(app, s.scope)
        mappings = st.semantic_mappings()
        unresolved = st.unresolved_translations()
        proposed_rows = [r for r in st.variant_rows() if r.approval == "proposed"]
        approved_fams = st.families(approved_only=True)

        hero = stat_row([metric(len(st.observations()), "Observations"),
                         metric(sum(1 for m in mappings if m.approval == "approved" and m.active), "Approved mappings"),
                         metric(len(proposed_rows), "Proposed interpretations", attn=bool(proposed_rows)),
                         metric(len(unresolved), "Unresolved", attn=bool(unresolved))])
        parts = [workspace_header("Translation & Identity", safe('<a href="/data">← Data Health</a>')), hero]

        # governed initialization — an explicit, idempotent, capability-gated action (NOT a page GET side effect)
        init = form("/admin/translation/import-reviewed-charts", "", csrf=s.csrf_token,
                    submit="Import reviewed charts (QX60/QX65/QX80)")
        parts.append('<div class="card"><h2>Initialization</h2>'
                     + ('<p class="muted">Not initialized yet. This imports the raw observations + literal '
                        'colour/model-line mappings from the three reviewed charts as source truth, and files the '
                        'family / generation / variant interpretations as <strong>proposed</strong> for approval. '
                        'Idempotent — safe to run again; it never reverts an approval.</p>'
                        if not st.is_initialized() else
                        '<p class="muted">Initialized. Re-running the import is idempotent: it adds only genuinely '
                        'new observations/mappings and never reverts an approval.</p>')
                     + init + '</div>')

        # 1) Needs attention — unresolved language actually observed from sources
        if unresolved:
            urows = [[esc(o["source_system"]), esc(o["semantic_type"]), esc(o["raw_value"]),
                      esc(o.get("seen_state", "")), safe(_resolve_form(s, o))] for o in unresolved]
            parts.append('<div class="card"><h2>Needs attention — unresolved language</h2>'
                         '<p class="muted">Raw values observed on an import with no approved translation. '
                         'Name each to make it reusable; raw values are never changed or deleted.</p>'
                         + table(["Source", "Type", "Raw value", "Seen", "Resolve"], urows) + '</div>')

        # 2) Proposed interpretations awaiting approval (source-backed but NOT auto-approved)
        if proposed_rows:
            prows = [[esc(r.family.as_str()), esc(r.raw_code), esc(r.generation_id), esc(r.package),
                      esc("BASE" if r.is_base else "variant"), safe(_approve_variant_form(s, r))]
                     for r in proposed_rows]
            parts.append('<div class="card"><h2>Proposed interpretations</h2>'
                         '<p class="muted">Family + generation-segment + variant memberships derived from the '
                         'charts. Source-backed, but an interpretation is not truth until approved.</p>'
                         + table(["Commercial family", "Raw code", "Gen", "Package", "Role", ""], prows) + '</div>')

        # 3) Approved commercial families -> preferred order (only APPROVED interpretation drives this)
        frows = []
        for fk in approved_fams:
            family = FamilyKey.parse(fk)
            dec = st.resolve_order(family)
            if dec["status"] == "order":
                call = safe(f'{badge("ok", "ORDER")} <strong>{esc(dec["raw_code"])}</strong> · '
                            f'{esc(dec["package"])} · gen {esc(dec["generation"])}')
            else:
                call = safe(f'{badge("pending", "unresolved")} {esc(dec["message"])}')
            frows.append([esc(fk), esc(", ".join(st.segments(family, approved_only=True))), call])
        parts.append('<div class="card"><h2>Approved families &amp; preferred order</h2>'
                     + (table(["Commercial family", "Generation segments", "Preferred order version"], frows)
                        if frows else '<p class="muted">No family interpretations approved yet.</p>') + '</div>')

        # 4) Dictionary — every governed SAME_AS mapping with proof + approve/retire
        drows = []
        for m in sorted(mappings, key=lambda x: (x.semantic_type, x.raw_value, x.model_scope)):
            drows.append([esc(m.semantic_type), esc(m.raw_value), esc_text(m.display_name),
                          esc(m.model_scope or "any"),
                          safe(badge("completed" if m.approval == "approved" and m.active
                                     else "stale" if m.approval == "retired" else "pending", m.approval)),
                          esc(", ".join(m.proof_refs) or "—"), safe(_mapping_actions(s, m))])
        parts.append('<div class="card"><h2>Translation dictionary</h2>'
                     + (table(["Type", "Raw", "Canonical name", "Scope", "State", "Proof", ""], drows)
                        if drows else '<p class="muted">Nothing imported yet.</p>') + '</div>')

        # 5) Audit tail — who changed what, when (append-only; newest first)
        alog = st.audit_log()[-12:][::-1]
        arows = [[esc(a.get("at", "")), esc(a.get("actor", "")), esc(a.get("action", "")),
                  esc(a.get("target", ""))] for a in alog]
        parts.append('<div class="card"><h2>Change history</h2>'
                     + (table(["When", "Who", "Action", "Target"], arows) if arows
                        else '<p class="muted">No changes recorded yet.</p>') + '</div>')

        return Response(page("Translation & Identity", "".join(parts), ctx=app.ctx(s),
                             active_path="/admin/translation", flash=_flash(s), wide=True, hide_title=True))

    @app.post("/admin/translation/import-reviewed-charts")
    def translation_import(app, req):
        s = req.session
        app.require(s, GOVERN)
        st = _store(app, s.scope)
        counts = SEED.seed(st, actor=s.principal_id, as_of=_now(app)[:10])
        _gov_event(app, s, "import_reviewed_charts", "QX60/QX65/QX80@2026-08-19")
        s.flash = (f"Import complete — {counts['observations']} observations, "
                   f"{counts['approved_mappings']} SAME-AS mappings approved, "
                   f"{counts['proposed_interpretations']} interpretations proposed for approval.")
        return Response.redirect("/admin/translation")

    @app.post("/admin/translation/approve")
    def translation_approve(app, req):
        s = req.session
        app.require(s, GOVERN)
        st = _store(app, s.scope)
        st.approve_semantic(req.f("source", ""), req.f("stype", ""), req.f("raw", ""), req.f("scope", ""),
                            actor=s.principal_id, at=_now(app))
        _gov_event(app, s, "approve_semantic", f'{req.f("stype", "")}/{req.f("raw", "")}')
        s.flash = "Mapping approved."
        return Response.redirect("/admin/translation")

    @app.post("/admin/translation/retire")
    def translation_retire(app, req):
        s = req.session
        app.require(s, GOVERN)
        st = _store(app, s.scope)
        st.retire_semantic(req.f("source", ""), req.f("stype", ""), req.f("raw", ""), req.f("scope", ""),
                           actor=s.principal_id, at=_now(app))
        _gov_event(app, s, "retire_semantic", f'{req.f("stype", "")}/{req.f("raw", "")}')
        s.flash = "Mapping retired (history preserved)."
        return Response.redirect("/admin/translation")

    @app.post("/admin/translation/approve-variant")
    def translation_approve_variant(app, req):
        s = req.session
        app.require(s, GOVERN)
        st = _store(app, s.scope)
        st.approve_variant(FamilyKey.parse(req.f("family", "")), req.f("raw", ""), req.f("gen", ""),
                           req.f("package", ""), actor=s.principal_id, at=_now(app))
        _gov_event(app, s, "approve_variant", f'{req.f("family", "")}/{req.f("raw", "")}/{req.f("package", "")}')
        s.flash = "Interpretation approved."
        return Response.redirect("/admin/translation")

    @app.post("/admin/translation/resolve")
    def translation_resolve(app, req):
        s = req.session
        app.require(s, GOVERN)
        st = _store(app, s.scope)
        raw, name = req.f("raw", "").strip(), req.f("name", "").strip()
        if raw and name:
            st.upsert_semantic(SemanticMapping(req.f("source", ""), req.f("stype", ""), raw, raw, name,
                                               req.f("scope", "").strip(), "approved", ("operator-resolved",)),
                               actor=s.principal_id, at=_now(app))
            _gov_event(app, s, "resolve_semantic", f'{req.f("stype", "")}/{raw}')
            s.flash = f"Resolved {raw} → {name}."
        return Response.redirect("/admin/translation")


def _flash(s):
    f = s.flash
    s.flash = None
    return f


def _resolve_form(s, o):
    return (f'<form class="mut" method="post" action="/admin/translation/resolve">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=source value="{esc(o["source_system"])}">'
            f'<input type=hidden name=stype value="{esc(o["semantic_type"])}">'
            f'<input type=hidden name=raw value="{esc(o["raw_value"])}">'
            f'<input name=name placeholder="canonical name" style="max-width:190px" required> '
            f'<input name=scope placeholder="model scope (optional)" style="max-width:140px"> '
            f'<button type=submit style="padding:4px 10px">Approve mapping</button></form>')


def _approve_variant_form(s, r):
    return (f'<form class="mut" method="post" action="/admin/translation/approve-variant">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=family value="{esc(r.family.as_str())}">'
            f'<input type=hidden name=raw value="{esc(r.raw_code)}">'
            f'<input type=hidden name=gen value="{esc(r.generation_id)}">'
            f'<input type=hidden name=package value="{esc(r.package)}">'
            f'<button type=submit style="padding:3px 9px">Approve</button></form>')


def _mapping_actions(s, m):
    if m.approval != "approved":
        act, label = "approve", "Approve"
    elif m.active:
        act, label = "retire", "Retire"
    else:
        return ""
    return (f'<form class="mut" method="post" action="/admin/translation/{act}">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=source value="{esc(m.source_system)}">'
            f'<input type=hidden name=stype value="{esc(m.semantic_type)}">'
            f'<input type=hidden name=raw value="{esc(m.raw_value)}">'
            f'<input type=hidden name=scope value="{esc(m.model_scope)}">'
            f'<button type=submit style="padding:3px 9px">{esc(label)}</button></form>')
