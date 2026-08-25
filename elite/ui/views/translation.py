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
from ...identity.lineage import (LineageStore, ensure_lineage_proposals, root_issues,
                                CAT_CONFLICT, CAT_DEMAND_LINEAGE, CAT_UNKNOWN)
from ...audit import make_event

GOVERN = "identity.govern"


def _store(app, scope):
    return TranslationStore(app.prefs, scope)          # READ-ONLY construction — never seeds


def _lineage(app, scope):
    return LineageStore(app.prefs, scope)


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
        ln = _lineage(app, s.scope)
        mappings = st.semantic_mappings()
        approved_fams = st.families(approved_only=True)
        ri = root_issues(st, ln)
        lineage_items = [i for i in ri["issues"] if i["category"] == CAT_DEMAND_LINEAGE]
        unknown_items = [i for i in ri["issues"] if i["category"] == CAT_UNKNOWN]
        conflict_items = [i for i in ri["issues"] if i["category"] == CAT_CONFLICT]

        # Headline: ROOT issues needing judgment — not the raw observation count (which is audit detail).
        hero = stat_row([metric(ri["count"], "Root issues to review", attn=bool(ri["count"])),
                         metric(len(lineage_items), "Demand-lineage", attn=bool(lineage_items)),
                         metric(len(unknown_items), "Unknown", attn=bool(unknown_items)),
                         metric(sum(1 for m in mappings if m.approval == "approved" and m.active),
                                "Auto-resolved mappings"),
                         metric(len(st.observations()), "Observations (audit)")])
        parts = [workspace_header("Translation & Identity", safe('<a href="/data">← Data Health</a>')), hero]
        parts.append('<div class="card"><p class="muted">Deterministic identity — colour / model-line / interior '
                     'and the family of an exact order code the reviewed chart states — <strong>auto-resolves</strong> '
                     '(recorded in Change history below, no action needed). Only relationships that change how '
                     'demand evidence is shared, source conflicts, and genuinely-unknown codes appear here as root '
                     'issues. Fix one root once; it propagates everywhere.</p></div>')

        # governed initialization / reconcile — idempotent, capability-gated
        init = form("/admin/translation/import-reviewed-charts", "", csrf=s.csrf_token,
                    submit="Re-run reviewed-chart import / reconcile")
        parts.append('<div class="card"><h2>Reviewed dictionary</h2>'
                     '<p class="muted">The reviewed QX60/QX65/QX80 dictionary initializes automatically at startup. '
                     'This re-runs the import to reconcile any new observations. Idempotent — it never reverts an '
                     'approval, a rejection, or a more-specific operator mapping.</p>' + init + '</div>')

        # A) Demand-lineage — approval CHANGES how demand evidence is shared (review-gated; never auto-activated)
        if lineage_items:
            cards = ""
            for i in lineage_items:
                cards += ('<div class="card" style="border-left:3px solid var(--accent)">'
                          f'<h3>{esc(i["title"])}</h3>'
                          '<p class="muted"><strong>Why you\'re seeing this:</strong> ' + esc(i["why"]) + '</p>'
                          + safe(_lineage_actions(s, i.get("proposal_id", ""))) + '</div>')
            parts.append('<div class="card"><h2>Needs review — demand lineage '
                         + badge("attention", f"{len(lineage_items)}") + '</h2>'
                         '<p class="muted">The identity is already known and resolved. Approving one of these lets '
                         'real historical demand evidence be shared through a governed relationship — it never '
                         'merges or averages the raw histories, which stay distinct.</p>' + cards + '</div>')

        # B) Conflicts — authoritative sources disagree (one root each)
        if conflict_items:
            crows = [[esc(i["title"]), esc(i["why"]), esc(i["affected"]), esc(", ".join(i["sources"]))]
                     for i in conflict_items]
            parts.append('<div class="card"><h2>Needs review — source conflict '
                         + badge("blocked", f"{len(conflict_items)}") + '</h2>'
                         + table(["Root", "Why automation stopped", "Affected", "Sources"], crows) + '</div>')

        # C) Genuinely unknown — one root per (type, raw value), cross-source deduped, with affected count
        if unknown_items:
            urows = [[esc(i["semantic_type"]), esc(i["raw_value"]), esc(i["affected"]),
                      esc(", ".join(i["sources"])), safe(_resolve_form_root(s, i))] for i in unknown_items]
            parts.append('<div class="card"><h2>Needs review — unknown language '
                         + badge("attention", f"{len(unknown_items)}") + '</h2>'
                         '<p class="muted">Observed raw values with no authoritative mapping. Each row is ONE root '
                         'issue across all sources/VINs it affects — name it once and every observation resolves. '
                         'Elite never guesses.</p>'
                         + table(["Type", "Raw value", "Affected", "Sources", "Resolve once"], urows) + '</div>')

        if not ri["count"]:
            parts.append('<div class="card">' + badge("ok", "All clear")
                         + ' <span class="muted">No root issues require human judgment. Deterministic identity is '
                         'auto-resolved; see Change history.</span></div>')

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

        # 5) Change history — deterministic auto-resolutions, approvals, rejections, deferrals, reopens (newest
        #    first). Auto-resolved facts live HERE, not in the active review queue.
        merged = [(a, "identity") for a in st.audit_log()] + [(a, "lineage") for a in ln.audit_log()]
        merged.sort(key=lambda t: t[0].get("at", ""))
        arows = [[esc(a.get("at", "")), esc(a.get("actor", "")), esc(a.get("action", "")), esc(a.get("target", ""))]
                 for a, _src in merged[-16:][::-1]]
        parts.append('<div class="card"><h2>Change history</h2>'
                     '<p class="muted">Every deterministic auto-resolution, approval, rejection, deferral and '
                     'reopen — append-only, nothing hidden.</p>'
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
        proposed = ensure_lineage_proposals(st, _lineage(app, s.scope), actor=s.principal_id, at=_now(app))
        _gov_event(app, s, "import_reviewed_charts", "QX60/QX65/QX80@2026-08-19")
        s.flash = (f"Reconciled — {counts['approved_mappings']} colour/model-line mappings, "
                   f"{counts['auto_approved_identities']} deterministic identities auto-resolved, "
                   f"{proposed} demand-lineage relationship(s) proposed for review.")
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

    @app.post("/admin/translation/lineage")
    def translation_lineage(app, req):
        """Approve / reject / defer a demand-lineage relationship. Rejections/deferrals are remembered and never
        re-prompted (LineageStore.propose is insert-if-absent); a rejected relationship reopens only when
        materially new evidence appears (LineageStore.reopen)."""
        s = req.session
        app.require(s, GOVERN)
        ln = _lineage(app, s.scope)
        pid, action = req.f("proposal", ""), req.f("action", "")
        reason = req.f("reason", "").strip()
        if action == "approve":
            ln.approve(pid, actor=s.principal_id, at=_now(app))
        elif action == "reject":
            ln.reject(pid, actor=s.principal_id, at=_now(app), reason=reason)
        elif action == "defer":
            ln.defer(pid, actor=s.principal_id, at=_now(app), reason=reason)
        _gov_event(app, s, f"lineage_{action}", pid)
        s.flash = f"Demand-lineage relationship {action}d."
        return Response.redirect("/admin/translation")


def _flash(s):
    f = s.flash
    s.flash = None
    return f


def _lineage_actions(s, proposal_id):
    """Approve / Reject / Defer controls for one demand-lineage review (item 8/9). Reject/Defer accept a reason;
    a rejection is remembered and never re-prompted unless materially new evidence appears."""
    def btn(action, label, style=""):
        return (f'<form class="mut" method="post" action="/admin/translation/lineage" style="display:inline">'
                f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                f'<input type=hidden name=proposal value="{esc(proposal_id)}">'
                f'<input type=hidden name=action value="{esc(action)}">'
                f'<button type=submit style="padding:5px 12px;{style}">{esc(label)}</button></form> ')
    return btn("approve", "Approve") + btn("reject", "Reject", "background:var(--card);color:var(--danger)") \
        + btn("defer", "Defer", "background:var(--card);color:var(--muted)")


def _resolve_form_root(s, i):
    """Resolve ONE root unknown code across all sources it affects (item 11). Submits the first affected source;
    the governed display resolver's any-source fallback then applies the name everywhere the code appears."""
    src = (i.get("sources") or [""])[0]
    return (f'<form class="mut" method="post" action="/admin/translation/resolve">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=source value="{esc(src)}">'
            f'<input type=hidden name=stype value="{esc(i.get("semantic_type", ""))}">'
            f'<input type=hidden name=raw value="{esc(i.get("raw_value", ""))}">'
            f'<input name=name placeholder="canonical name" style="max-width:180px" required> '
            f'<input name=scope placeholder="model scope (optional)" style="max-width:130px"> '
            f'<button type=submit style="padding:4px 10px">Approve mapping</button></form>')


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
