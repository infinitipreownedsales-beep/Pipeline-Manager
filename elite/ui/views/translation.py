"""Translation & Identity Center — the authorized, user-maintainable maintenance surface (`/admin/translation`).

An authorized person maintains source-language equivalence (SAME AS), commercial families + generation
segments (SAME FAMILY AS), factory-option variants (VARIANT OF BASE) and the preferred order version — WITHOUT
any Claude/GPT coding. New/unresolved language from an import surfaces here (and is counted in Data Health);
approving a mapping makes it reusable forever. Raw observations are immutable; nothing is deleted.
"""
from __future__ import annotations

from ..render import (page, esc, safe, table, kv, badge, metric, stat_row, workspace_header, esc_text)
from ..http import Response
from ...identity.translation import (TranslationStore, SemanticMapping, FamilyKey)
from ...identity import seed_infiniti as SEED


def _store(app, scope):
    st = TranslationStore(app.prefs, scope)
    if not st.semantic_mappings():                 # first visit on this store: install the source-backed seed
        SEED.seed(st)
    return st


def _resolve_form(app, s, o):
    """Inline resolution control for one unresolved raw observation: name it + approve, in place."""
    return (f'<form class="mut" method="post" action="/admin/translation/resolve">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=source value="{esc(o["source_system"])}">'
            f'<input type=hidden name=stype value="{esc(o["semantic_type"])}">'
            f'<input type=hidden name=raw value="{esc(o["raw_value"])}">'
            f'<input name=name placeholder="canonical name" style="max-width:200px" required> '
            f'<input name=scope placeholder="model scope (optional)" style="max-width:150px"> '
            f'<button type=submit style="padding:4px 10px">Approve mapping</button></form>')


def register(app):
    @app.get("/admin/translation")
    def translation_center(app, req):
        s = req.session
        app.require(s, "workspace.view")
        st = _store(app, s.scope)
        mappings = st.semantic_mappings()
        unresolved = st.unresolved_translations()
        rows = st.variant_rows()
        families = sorted({r.family.as_str() for r in rows})

        hero = stat_row([metric(sum(1 for m in mappings if m.approval == "approved"), "Approved mappings"),
                         metric(len(unresolved), "Unresolved", attn=bool(unresolved)),
                         metric(len(families), "Commercial families"),
                         metric(sum(1 for m in mappings if m.approval == "proposed"), "Proposed", attn=any(
                             m.approval == "proposed" for m in mappings))])
        parts = [workspace_header("Translation & Identity", safe(
            '<a href="/data">← Data Health</a>')), hero]

        # 1) Needs attention — new/unresolved language from imports
        if unresolved:
            urows = [[esc(o["source_system"]), esc(o["semantic_type"]), esc(o["raw_value"]),
                      esc(o.get("seen_state", "")), safe(_resolve_form(app, s, o))] for o in unresolved]
            parts.append('<div class="card"><h2>Needs attention — unresolved language</h2>'
                         '<p class="muted">New raw values seen on an import with no approved translation yet. '
                         'Name each one to make it reusable forever. Raw values are never changed or deleted.</p>'
                         + table(["Source", "Type", "Raw value", "Seen", "Resolve"], urows) + '</div>')
        else:
            parts.append('<div class="card"><h2>Needs attention</h2>'
                         '<p class="muted">Nothing unresolved — every observed value has an approved translation.</p></div>')

        # 2) Commercial families → generation segments → preferred order version
        frows = []
        for fk in families:
            family = FamilyKey.parse(fk)
            segs = st.segments(family)
            dec = st.resolve_order(family)
            if dec["status"] == "order":
                call = safe(f'{badge("ok", "ORDER")} <strong>{esc(dec["raw_code"])}</strong> · '
                            f'{esc(dec["package"])} · gen {esc(dec["generation"])}')
            else:
                call = safe(f'{badge("pending", "unresolved")} {esc(dec["message"])}')
            frows.append([esc(fk), esc(", ".join(segs)), call])
        parts.append('<div class="card"><h2>Commercial families &amp; preferred order</h2>'
                     '<p class="muted">Family = franchise + model + trim + drivetrain. Generation is a planning '
                     'segment underneath — demand may share as lineage, but supply is counted per segment and the '
                     'ORDER identity is the exact currently-orderable raw code. BASE is preferred; a pending BASE '
                     'is never auto-substituted by a priced package.</p>'
                     + table(["Commercial family", "Generation segments", "Preferred order version"], frows) + '</div>')

        # 3) Dictionary — every governed SAME AS mapping with proof + approval
        drows = []
        for m in sorted(mappings, key=lambda x: (x.semantic_type, x.raw_value, x.model_scope)):
            action = ("" if m.approval == "approved" else safe(
                f'<form class="mut" method="post" action="/admin/translation/approve">'
                f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                f'<input type=hidden name=source value="{esc(m.source_system)}">'
                f'<input type=hidden name=stype value="{esc(m.semantic_type)}">'
                f'<input type=hidden name=raw value="{esc(m.raw_value)}">'
                f'<input type=hidden name=scope value="{esc(m.model_scope)}">'
                f'<button type=submit style="padding:3px 9px">Approve</button></form>'))
            drows.append([esc(m.semantic_type), esc(m.raw_value), esc_text(m.display_name),
                          esc(m.model_scope or "any"), safe(badge("completed" if m.approval == "approved"
                                                                  else "pending", m.approval)),
                          esc(", ".join(m.proof_refs) or "—"), action])
        parts.append('<div class="card"><h2>Translation dictionary</h2>'
                     + table(["Type", "Raw", "Canonical name", "Scope", "State", "Proof", ""], drows) + '</div>')

        return Response(page("Translation & Identity", "".join(parts), ctx=app.ctx(s),
                             active_path="/admin/translation", wide=True, hide_title=True))

    @app.post("/admin/translation/approve")
    def translation_approve(app, req):
        s = req.session
        app.require(s, "workspace.view")
        st = _store(app, s.scope)
        st.approve_semantic(req.f("source", ""), req.f("stype", ""), req.f("raw", ""), req.f("scope", ""))
        s.flash = "Mapping approved."
        return Response.redirect("/admin/translation")

    @app.post("/admin/translation/resolve")
    def translation_resolve(app, req):
        s = req.session
        app.require(s, "workspace.view")
        st = _store(app, s.scope)
        raw = req.f("raw", "").strip()
        name = req.f("name", "").strip()
        if raw and name:
            st.upsert_semantic(SemanticMapping(req.f("source", ""), req.f("stype", ""), raw, raw, name,
                                               req.f("scope", "").strip(), "approved",
                                               ("operator-resolved",)))
            s.flash = f"Resolved {raw} → {name}."
        return Response.redirect("/admin/translation")
