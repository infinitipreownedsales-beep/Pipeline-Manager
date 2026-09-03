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
                      action_group, rec_row, work_group, restraint_note, coverage_lane,
                      horizon_strip)
from ..http import Response
from .domains import _readable, _readable_h, _resp, _conn


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


def _sl_relevant_models(app, scope):
    """Models the dealership actually operates as Service Loaners (active fleet), i.e. models whose future
    Service-Loaner requirement must be resolved before a Retail-only order can be called complete. Read from
    the certified/authoritative loaner intelligence composition; on any failure return empty (fail toward NOT
    inventing an unresolved warning for a model we cannot confirm is a loaner model)."""
    try:
        from ...loaner.intelligence import build_intelligence
        intel = build_intelligence(_conn(app), scope, app.prefs, app.stack.clock)
        return {(m or "").upper() for m, _ in intel.composition if m}
    except Exception:   # noqa: BLE001
        return set()


def _cpo_decomposition(app, scope, board, month):
    """Per-model cross-domain order-source decomposition for the CPO board: certified Retail acquire units +
    the Service-Loaner ORDER portion of any management directive (i.e. what remains AFTER placing safe units
    from existing surplus) + other governed commitments = total dealership acquisition requirement.

    Certified Retail demand is read, never mutated. A directive of N is NOT added blindly: economic sourcing
    decides how many can come from existing surplus (place) vs must be ordered specifically; only the ORDER
    portion reaches CPO. When economics can't assess the split, the full requirement is ordered conservatively
    and flagged (never under-ordered, never fabricated). Returns (deco_by_model, sourcing_by_model)."""
    from ...ordering.cross_domain import PlannedRequirementStore, decompose_orders
    from ...loaner.unit_econ import sourcing_plan
    retail_by_model = {}
    for b in board:
        m = (b["model"] or "").upper()
        retail_by_model[m] = retail_by_model.get(m, 0) + int(b["order"] or 0)
    store = PlannedRequirementStore(app.prefs, scope)
    directives = store.by_model()                          # {model: N} governed management directive
    order_by_model, sourcing = {}, {}
    if directives:
        try:
            sp = sourcing_plan(app, scope, month, directives)
            sourcing = sp["by_model"]
            for m, ms in sourcing.items():
                order_by_model[m] = ms.requested if ms.unresolved else ms.order_count
        except Exception:   # noqa: BLE001 — fail safe: order the full requirement rather than under-order Retail
            order_by_model = dict(directives)
    lines = decompose_orders(retail_by_model, order_by_model,
                             sl_relevant_models=set(), acknowledged_models=store.acknowledged_models())
    return {ln.model: ln for ln in lines}, sourcing


def _cpo_sl_program_banner(sb):
    """Program-level Service-Loaner self-balancing result for the CPO page. Replaces the old per-model red
    'unresolved' spam: a fleet at/above target resolves to zero automatically (no manual number required); a
    positive calculated need is stated and additive; only a missing target is a real prerequisite."""
    lb = (' <span class="muted">Exit timing is unresolved for '
          f'{sb.unresolved_timing_units} unit(s), so this is a lower bound.</span>'
          if sb.is_lower_bound and sb.unresolved_timing_units else "")
    if sb.resolution == "no_target":
        return ('<div class="err" role="alert"><strong>Service-Loaner target not set.</strong> Elite cannot '
                'calculate future loaner need until a desired fleet target exists. '
                '<a href="/service-loaner">Set the desired Service-Loaner fleet</a> — do not invent a number to '
                'clear this; the engine will calculate it.</div>')
    fleet = f'fleet {sb.current_active} / target {sb.desired}'
    if sb.resolution == "resolved_zero":
        return restraint_note(safe(
            f'<strong>Service-Loaner self-balancing: {esc(fleet)} → no additional loaner acquisition required.</strong> '
            f'The fleet is at or above target; Elite is not adding loaners and is preserving Retail supply.{lb}'))
    return ('<div class="callout"><strong>Service-Loaner self-balancing: '
            f'{esc(fleet)}, {sb.releasing_now} releasing → order {sb.calculated_need} more for Service Loaner.</strong> '
            'This is a separate dealership obligation, added to the total below (Retail demand is unchanged). '
            'Model/colour allocation stays open unless a management directive sets it. '
            f'<a href="/ordering/sl-requirements">Review the plan</a>.{lb}</div>')


def _cpo_replacement_block(nb, model, recs, stat, month):
    """Replacement search for a NOT-ORDERABLE recommendation. Reruns the CERTIFIED horizon (the issued plan
    already reflects on-ground + inbound + demand) for same-family combinations that are still orderable and
    carry their own certified order — never a nearest-code/trim/colour substitute. NO SUBSTITUTE is a valid,
    explicit result (the unmet demand is left unfilled rather than manufacturing an unjustified order)."""
    alts = [b for b in recs
            if b["combo"] != nb["combo"] and _int_or0(b.get("order")) > 0
            and stat[b["combo"]]["status"] == "open"]      # each alt has its OWN certified justification
    head = (f'<div class="callout"><strong>{esc(nb["identity"])} — not orderable.</strong> '
            'Replacement search re-ran the certified horizon for same-family orderable combinations '
            '(no nearest-code substitution). ')
    if not alts:
        return head + ('<strong>NO SUBSTITUTE — LEAVE UNFILLED.</strong> No other orderable '
                       f'{esc(model)} combination has a certified order to justify a replacement; the unmet '
                       'demand is left unfilled rather than manufacturing an unjustified order.</div>')
    opts = "".join(
        f'<div class="pos" style="padding:2px 0"><a href="/combination/{esc(b["pid"])}?month={esc(month)}">'
        f'{esc(b["identity"])}</a> — certified ORDER {esc(b["order"])} · Current {esc(b["current"])}</div>'
        for b in alts)
    return head + 'These orderable same-family combinations carry their own certified order:</div>' + opts


def _read_production_orders(app, scope):
    """Latest completed authoritative Production Orders snapshot rows, or [] — best effort, never breaks CPO."""
    try:
        from ...newinv.supply_bridge import read_latest_snapshot_rows
        from ...newinv.snapshots import SnapshotReader
        ops = _ops_stack(app)
        ops_store = getattr(ops, "ops", None) if ops else None
        if ops_store is None:
            return []
        reader = SnapshotReader(ops_store, ops.data)
        return list(read_latest_snapshot_rows(reader, ops.source_id("production_orders"), scope) or [])
    except Exception:   # noqa: BLE001
        return []


def _ppo_supply(app):
    """The EXISTING governed New-Inventory committed-supply rail (shared with CPO/planning) — NOT a PPO-only
    ledger. A PPO FIRM enters Committed Supply here and is counted once by `supply.qualifying_supply`."""
    from ...newinv.store import NewInvStore
    from ...newinv.supply import SupplyService
    store = NewInvStore(_conn(app), app.stack.clock)
    return store, SupplyService(store, app.stack.clock)


def _ppo_sync_commitments(app, scope, offer, combination_key):
    """Make the governed Committed Supply for ONE offer match Kyle's recorded decision — idempotently, by unit
    identity. A FIRM/PARTIAL of N units yields N committed SupplyCommitments (commitment_type='ppo'); DENY /
    unworked yields zero; re-recording never double-commits the same identity. Returns the current id map.

    This reuses the EXISTING SupplyCommitment rail (proposed -> committed), so the commitment affects subsequent
    PPO evaluation, CPO/ordering Need and every other consumer of qualifying committed Supply. It never creates
    an authoritative Vehicle Unit / Production Order and never invents a VIN/order number."""
    from ...ordering.ppo_commitments import commitment_units_for_offer
    from ...clock import to_utc_iso
    _store, supply = _ppo_supply(app)
    act = (offer.get("operator_action") or "").upper()
    qty = 0
    if act in ("FIRM", "PARTIAL"):
        try:
            qty = max(0, int(offer.get("operator_qty") or 0))
        except (TypeError, ValueError):
            qty = 0
    targets = {u["unit_or_order_id"]: u for u in commitment_units_for_offer(offer, combination_key, qty)}
    existing = dict(offer.get("commitments", {}) or {})       # {unit_or_order_id: commitment_id}
    at = to_utc_iso(app.stack.clock.now())
    # create any target identity not yet committed
    for uid, u in targets.items():
        if uid not in existing:
            c = supply.propose_commitment(combination_key, scope, commitment_type="ppo", unit_or_order_id=uid,
                                          unit_identity_kind=u["unit_identity_kind"],
                                          arrival_month=offer.get("production_month"), source="ppo_firm")
            supply.approve_commitment(c.id, decision_ref=f"ppo:{offer.get('id')}", approval_time=at)
            existing[uid] = c.id
    # cancel (explicit governed reversal) any prior commitment no longer wanted
    for uid in list(existing.keys()):
        if uid not in targets:
            try:
                supply.cancel_commitment(existing[uid], reason="ppo_decision_change")
            except Exception:   # noqa: BLE001
                pass
            existing.pop(uid, None)
    offer["commitments"] = existing
    return existing


def _ppo_release_commitments(app, scope, offer, *, reason):
    """Explicit governed reversal of an offer's committed Supply (used by Clear window). Cancels each governed
    commitment — never a silent delete of committed Supply."""
    _store, supply = _ppo_supply(app)
    released = 0
    for uid, cid in (offer.get("commitments", {}) or {}).items():
        try:
            supply.cancel_commitment(cid, reason=reason)
            released += 1
        except Exception:   # noqa: BLE001
            pass
    offer["commitments"] = {}
    return released


def _cpo_commitments_card(app, scope, month, board, lines, qty):
    """Session ORDER commitments (shadow future supply) and their reconciliation against authoritative
    Production Orders — counted once, ambiguity surfaced, never silently merged."""
    from ...ordering.commitment_ledger import commitments_from_lines, reconcile_commitments
    board_map = {b["combo"]: {"model": b["model"], "order": _int_or0(b.get("order"))} for b in board}
    commits = commitments_from_lines(lines, qty, board_map)
    total = sum(v["qty"] for v in commits.values())
    if not total:
        return ""
    prod = _read_production_orders(app, scope)
    head = ('<div class="card"><h2 style="margin-top:4px">Session order commitments</h2>'
            f'<p style="margin:2px 0"><strong>{total}</strong> unit(s) committed this session (shadow future '
            'supply — not yet an authoritative Production Order).</p>')
    if not prod:
        return head + ('<p class="muted" style="font-size:12px">No Production Orders snapshot loaded yet. When '
                       'it arrives, Elite reconciles these commitments so a confirmed order is never counted '
                       'twice.</p></div>')
    rec = reconcile_commitments(commits, prod)
    rows = kv([("Committed this session", total),
               ("Matched to authoritative Production Orders (counted once)", len(rec["matched"])),
               ("Still shadow (awaiting a Production Order)", sum(rec["remaining_shadow"].values())),
               ("Unmatched Production Orders (no session commitment)", len(rec["unmatched"])),
               ("Ambiguous — needs a deterministic identifier", len(rec["ambiguous"]))])
    amb = ''
    if rec["ambiguous"]:
        amb = ('<div class="err" role="alert"><strong>Ambiguous reconciliation.</strong> '
               + str(len(rec["ambiguous"])) + ' Production Order(s) could match more than one commitment and '
               'were NOT merged. Provide a deterministic identifier (VIN or combination) to reconcile.</div>')
    return head + rows + amb + '</div>'


def _cpo_dealership_total_card(deco, sb, sourcing=None):
    """The one reconciled dealership acquisition total: certified Retail + the Service-Loaner ORDER portion of
    any directive (after placing safe units from existing surplus) + calculated program need + other, counted
    once. Certified Retail demand is summed, never mutated."""
    sourcing = sourcing or {}
    retail = sum(ln.retail_certified for ln in deco.values())
    order_directive = sum(ln.sl_planned for ln in deco.values())     # already the ORDER portion (post-sourcing)
    other = sum(ln.other_committed for ln in deco.values())
    calc = sb.calculated_need if sb.resolution == "resolved_need" else 0
    total = retail + order_directive + calc + other
    placed = sum(ms.place_count for ms in sourcing.values())
    requested = sum(ms.requested for ms in sourcing.values())
    rows = [("Retail-certified acquisition requirement", retail),
            ("Service-Loaner calculated requirement (program)", calc),
            ("Service-Loaner directive — ORDER portion", order_directive),
            ("Other authoritative commitment", other),
            ("Total dealership acquisition requirement", total)]
    body = "".join(f'<dt>{esc(k)}</dt><dd><strong>{v}</strong></dd>' for k, v in rows)
    src = ''
    if requested:
        unresolved = any(ms.unresolved for ms in sourcing.values())
        src = ('<p class="muted" style="font-size:12px">Service-Loaner directive of <strong>' + str(requested)
               + '</strong>: <strong>' + str(placed) + '</strong> sourced from existing Retail surplus (placed, '
               'not ordered), <strong>' + str(order_directive) + '</strong> ordered specifically for Service '
               'Loaner. Elite does not order units it can safely place from surplus.'
               + (' <em>Sourcing split is pending economics — the full requirement is ordered conservatively.</em>'
                  if unresolved else '') + '</p>')
    note = ('' if sb.resolution != "no_target" else
            '<p class="muted" style="font-size:12px">Service-Loaner need is not yet counted — set the fleet '
            'target so the total is complete.</p>')
    return ('<div class="card"><h2 style="margin-top:4px">Dealership acquisition requirement</h2>'
            f'<dl class="kv">{body}</dl>' + src
            + '<p class="muted" style="font-size:12px">Certified Retail demand is read, never changed. '
            'Service-Loaner need is additive and, where only program-level, is not assigned to an exact '
            f'colour combination.</p>{note}</div>')


def _cpo_supply_integrity(app, scope):
    """One physical supply truth: committed VINs (Service Loaner + Demo) that ALSO appear as free New-Retail
    supply — a double-count risk. Best-effort and read-only; returns [] when inventory is unavailable."""
    try:
        from ...ordering.cross_domain import committed_vins, supply_double_count_audit
        from ...loaner.placement import read_new_retail_units, _authoritative_vin
        committed = set(committed_vins(_conn(app), scope, app.prefs).keys())
        if not committed:
            return []
        rows = read_new_retail_units(app, scope)

        def _vin(r):
            v, ok, _serial = _authoritative_vin(r)
            return v if ok else None
        return supply_double_count_audit(rows, committed, _vin)
    except Exception:   # noqa: BLE001 — supply integrity must never break the ordering page
        return []


def _decomposition_html(model, ln):
    """The order-source line for one model: certified Retail + any governed management-override Service-Loaner
    quantity for this model. The program-wide calculated SL requirement is resolved at page level, so no
    per-model 'unresolved' state is shown here."""
    src = [f'<div class="pos" style="margin:6px 0"><strong>Order sources — {esc(model)}</strong> · '
           f'Retail-certified <strong>{ln.retail_certified}</strong>']
    if ln.sl_planned:
        src.append(f' · Service&nbsp;Loaner directive <strong>+{ln.sl_planned}</strong>')
    if ln.other_committed:
        src.append(f' · Other commitment <strong>+{ln.other_committed}</strong>')
    src.append(f' · <strong>Model total {ln.total}</strong></div>')
    tail = ""
    if ln.sl_planned:
        tail = restraint_note(safe(
            f'Management directive: <strong>+{ln.sl_planned} additional {esc(model)}</strong> for Service&nbsp;Loaner '
            '— a governed <strong>model-level</strong> add. It is <strong>not</strong> assigned to an exact colour '
            'combination here. <a href="/ordering/sl-requirements">Manage</a>'))
    return "".join(src) + tail


def _planning_code4(identity):
    """The 4-digit planning model code carried in a dms_planning canonical identity, else ''."""
    import re
    m = re.search(r"model_code=(\d{3,5})", str(identity or ""))
    return (m.group(1)[:4] if m else "")


def _executable_order_identity(st, code4):
    """Governed EXECUTABLE order identity for a planning code, so an ACQUIRE never terminates on an obsolete
    (older-generation) code merely because historical demand lived there. Returns (state, order_code, family):
      * 'current'   — this code IS the current governed orderable version (single-generation family, or the code
                      is ungoverned → leave as-is); order it as shown;
      * 'supersede' — an older-generation display code whose family's NEWEST generation is positively governed
                      orderable; order that newer current code;
      * 'gated'     — a MULTI-generation family whose NEWEST generation is not positively governed orderable →
                      gate. The executable order is NEVER allowed to fall back to an older generation just because
                      an old chart row was priced; orderability of the current generation is its own governed fact.
    Demand-evidence identity (where the history lived) is thereby kept distinct from executable order identity."""
    if not (code4 and len(code4) >= 2 and code4.isdigit()):
        return ("current", None, "")
    try:
        fam = st.family_for_code(code4)
    except Exception:   # noqa: BLE001
        fam = None
    if fam is None:
        return ("current", None, "")                       # ungoverned code — leave the existing action as-is
    try:
        segs = {int(g) for g in st.segments(fam, approved_only=True) if str(g).isdigit()}
    except Exception:   # noqa: BLE001
        segs = set()
    if len(segs) <= 1:
        return ("current", None, fam.as_str())             # single-generation family — existing behaviour
    # MULTI-generation family: the executable order must be the NEWEST generation, and ONLY when that newest
    # generation is positively governed orderable. Never the older generation, even if its old BASE was priced.
    newest = max(segs)
    code_gen = int(code4[:2])
    try:
        order = st.resolve_order(fam)
    except Exception:   # noqa: BLE001
        order = None
    if (order and order.get("status") == "order" and str(order.get("generation") or "").isdigit()
            and int(order["generation"]) == newest):
        return (("supersede" if newest > code_gen else "current"), order.get("raw_code"), fam.as_str())
    return ("gated", None, fam.as_str())                   # newest generation not positively orderable → gate


def _plan_key_of(identity):
    """(model, code4, exterior, interior) parsed from a dms_planning canonical identity (∅ -> '')."""
    import re
    s = str(identity or "")

    def g(f):
        m = re.search(rf"{f}=([^|]*)", s)
        v = (m.group(1).strip() if m else "")
        return "" if v == "∅" else v
    return (g("model"), g("model_code")[:4], g("exterior"), g("interior"))


def _wholesale_on_ground(app, scope, plan_key):
    """ARRIVED (DLR-INV) physical units matching a combination's planning key, OLDEST first (by days-in-stock).
    Real DMS inventory only — never fabricates a VIN. Each: {vin, stock, dis}. Incoming stages are excluded
    (they belong to future redirect, never arrived wholesale disposition)."""
    try:
        from ...loaner.placement import read_new_retail_units, _authoritative_vin
        from ...newinv.dms_cohort import dms_source_stage
        from ...newinv.dms_identity import dms_planning_key
    except Exception:   # noqa: BLE001
        return []
    out = []
    for r in (read_new_retail_units(app, scope) or []):
        try:
            if dms_source_stage(r) != "DLR-INV" or dms_planning_key(r) != plan_key:
                continue
        except Exception:   # noqa: BLE001
            continue
        vin, ok, serial = _authoritative_vin(r)
        stock = str(r.get("stock_number") or r.get("stock") or r.get("Stock#") or "").strip()
        dis = None
        for k in ("dis", "days_in_stock", "DIS"):
            v = r.get(k)
            if str(v or "").strip():
                try:
                    dis = int(float(v))
                    break
                except (TypeError, ValueError):
                    pass
        out.append({"vin": (vin if ok else ""), "stock": stock, "serial": serial, "dis": dis})
    out.sort(key=lambda u: -(u["dis"] if u["dis"] is not None else -1))   # oldest (highest DIS) first
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
        from ...identity.translation import TranslationStore
        bench = _benched(app, s.scope)
        xlat = TranslationStore(app.prefs, s.scope)

        models = {}          # model -> list of (call_kind, label, readable, current, incoming, target, pid, acq, note)
        totals = {"acquire": 0, "gated": 0, "gated_combos": 0, "arrived_excess": 0, "incoming_excess": 0,
                  "combos": 0}
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
            acq = int(dec.get("acquire_units", 0) or 0)
            # EXECUTABLE-ORDER bridge: an ACQUIRE must never terminate on an obsolete older-generation order
            # code. Keep the demand-evidence identity, but point the action at the current governed orderable
            # version (or gate when none is established). The need count is unchanged (the 22 total reconciles).
            note = ""
            gated = False
            if kind == "ACQUIRE" and acq > 0:
                state, order_code, _fam = _executable_order_identity(xlat, _planning_code4(ident.get(r["combination_id"], "")))
                if state == "supersede" and order_code:
                    note = f"Order the current version {order_code} (this {label.split(' ')[0]} identity is a prior generation)."
                elif state == "gated":
                    kind = "GATED"
                    gated = True
                    label = "ORDER GATED · no current orderable version"
                    note = ("Demand is supported, but no current-generation orderable version is established for "
                            "this family yet — order is gated (never an obsolete code).")
            # ACCOUNTING: 'Vehicles to order now' counts only EXECUTABLE acquire units; gated demand is real
            # but not order-executable, so it is counted and shown separately (never in the order-now headline).
            if gated:
                totals["gated"] += acq
                totals["gated_combos"] += 1
            else:
                totals["acquire"] += acq
            totals["arrived_excess"] += int(dec.get("arrived_excess", 0) or 0)
            totals["incoming_excess"] += int(dec.get("incoming_excess", 0) or 0)
            totals["combos"] += 1
            models.setdefault(_model_of(readable), []).append(
                (kind, label, readable, r["current_supply"], incoming,
                 round(dec.get("target_level", 0) or 0, 1), r["id"], acq, note))

        if not models:
            body = ('<div class="card"><p class="muted">No certified inventory plan is loaded for this store yet. '
                    'Once the New-Inventory board is issued it appears here as the dealership pipeline.</p></div>')
            return _resp(app, s, "Pipeline", body, "/")

        headline_rows = [("Vehicles to order now", totals["acquire"])]
        if totals["gated"]:
            headline_rows.append(("Vehicles needed but order-gated", totals["gated"]))
        headline_rows += [("Combinations in the plan", totals["combos"]),
                          ("Arrived, over-stocked (review disposition)", totals["arrived_excess"]),
                          ("Incoming to redirect", totals["incoming_excess"])]
        headline = kv(headline_rows)
        parts = [f'<div class="card"><h2>Today across the whole dealership</h2>{headline}'
                 '<p class="muted">Expand a model to see its combinations. Numbers are read from the certified '
                 'plan — nothing is recomputed here.</p></div>']
        _tone = {"ACQUIRE": "attention", "EXCESS": "pending", "MONITOR": "healthy", "GATED": "unresolved"}
        _rank = {"ACQUIRE": 0, "GATED": 0, "EXCESS": 1, "MONITOR": 2}
        for model in sorted(models):
            combos = sorted(models[model], key=lambda c: (_rank.get(c[0], 3), c[2]))
            acq_combos = [c for c in combos if c[0] == "ACQUIRE"]
            gated_combos = [c for c in combos if c[0] == "GATED"]
            n_acq_combos, n_vehicles = len(acq_combos), sum(c[7] for c in acq_combos)   # executable acquire
            n_gated_combos, n_gated_veh = len(gated_combos), sum(c[7] for c in gated_combos)   # gated demand
            rows_html = table(
                ["Call", "Combination", "On ground now", "Incoming", "Target (60-day)"],
                [[safe(badge(_tone.get(c[0], "healthy"), c[1])),
                  safe(f'<a href="/combination/{esc(c[6])}">{esc(c[2])}</a>'
                       + (f'<div class="muted" style="font-size:12px">{esc(c[8])}</div>' if c[8] else "")),
                  esc(c[3]), esc(c[4]), esc(c[5])]
                 for c in combos])
            # distinguish EXECUTABLE acquire from GATED demand, and combinations from vehicles
            summary = (f'{esc(model)} · {len(combos)} combination(s)'
                       + (f' · <strong>{n_acq_combos} acquire combination(s) · {n_vehicles} vehicle(s) to acquire'
                          f'</strong>' if n_acq_combos else (' · steady' if not n_gated_combos else ''))
                       + (f' · <span class="muted">{n_gated_combos} gated combination(s) · {n_gated_veh} '
                          f'vehicle(s) order-gated</span>' if n_gated_combos else ''))
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
        qty = _ws_get(app, s.scope, f"cpo_line_qty::{month}", {}) or {}
        board = _acquire_board(app, s.scope, month)
        coverage = _model_coverage(app, s.scope, month)
        pmonths = _plan_months(app, s.scope)     # certified per-plan month rows (for the horizon sparkline)
        deco, sourcing = _cpo_decomposition(app, s.scope, board, month)   # order-source decomposition per model
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

        # Service-Loaner self-balancing (program-level, engine-calculated): a fleet at/above target resolves to
        # zero automatically — no invented number — so the old per-model red 'unresolved' spam is gone. The
        # dealership total reconciles certified Retail + calculated SL + management override + other.
        from ...loaner.self_balancing import build_requirement
        sb = build_requirement(_conn(app), s.scope, app.prefs)
        parts.append(_cpo_sl_program_banner(sb))
        directive_total = sum(ln.sl_planned for ln in deco.values())
        if directive_total and sb.resolution != "resolved_need":
            parts.append('<div class="callout"><strong>Management directive active.</strong> Elite\'s calculated '
                         f'need is {sb.calculated_need if sb.resolution != "no_target" else "pending"}, and '
                         f'management has directed <strong>+{directive_total}</strong> more to ORDER (after placing '
                         'any safe units from surplus) — additive to the dealership order below, with certified '
                         'Retail demand unchanged.</div>')
        parts.append(_cpo_dealership_total_card(deco, sb, sourcing))
        parts.append(_cpo_commitments_card(app, s.scope, month, board, lines, qty))

        # one physical supply truth: a committed SL/Demo VIN must never also count as free Retail supply
        dbl = _cpo_supply_integrity(app, s.scope)
        if dbl:
            tails = ", ".join("…" + v[-6:] for v in dbl[:8]) + ("…" if len(dbl) > 8 else "")
            parts.append('<div class="err" role="alert"><strong>Physical supply conflict.</strong> '
                         f'{len(dbl)} vehicle(s) committed to Service&nbsp;Loaner / Demo still appear in '
                         f'New-Retail supply ({esc(tails)}). One physical vehicle is one purpose — verify these are '
                         'not being counted as free Retail supply before ordering against them.</div>')

        if not models:
            parts.append('<div class="card"><p class="muted">No certified ACQUIRE recommendations are issued '
                         'for this store yet. Load or refresh the New-Inventory plan to populate CPO.</p></div>')
            return Response(page("CPO Ordering", "".join(parts), ctx=app.ctx(s), active_path="/ordering",
                                 flash=_flash(s), wide=True, hide_title=True))

        for mo in sorted(models):
            recs = models[mo]
            cap = int(alloc.get(mo, len(recs)) or 0)
            active, nextbest = recs[:cap], recs[cap:]
            stat = {b["combo"]: _cpo_status(lines, qty, b) for b in recs}
            not_ordered_active = sum(1 for b in active if stat[b["combo"]]["status"] == "not_ordered")
            promoted = nextbest[:not_ordered_active]
            shown = active + promoted
            worked = sum(1 for b in shown if _cpo_worked(stat[b["combo"]]["status"]))
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
            ln = deco.get((mo or "").upper())
            deco_html = _decomposition_html(mo, ln) if ln else ""
            block = [f'<div class="card"><h2 style="margin-top:4px">{esc(mo)}</h2>{hero}{deco_html}{lane}{edit}']

            # work queue: unresolved recommendations, in certified rank order. EVERY rank uses the same
            # information-complete row — rank sets the order, never whether the call, position, inline horizon,
            # human Why or actions are visible — so the whole allocation is scannable and #4..#N are not
            # subconsciously overlooked. Handled (worked) items collapse into a receded, still-undoable group.
            ranked = list(enumerate(shown, 1))     # (certified rank, rec)
            unresolved = [(r, b) for r, b in ranked if not _cpo_worked(stat[b["combo"]]["status"])]
            worked = [(r, b) for r, b in ranked if _cpo_worked(stat[b["combo"]]["status"])]
            queue = []
            for i, (r, b) in enumerate(unresolved):
                queue.append(_cpo_rec_row(s, b, r, stat[b["combo"]], month,
                                          promoted=b in promoted, horizon_html=_strip(b), ln=ln))
            if queue:
                block.append('<div class="queue">' + "".join(queue) + '</div>')
            elif worked:
                block.append('<p class="muted" style="margin:8px 0">Every recommendation for this model is '
                             'handled — see the worked items below.</p>')
            if worked:
                n_conf = sum(1 for _r, b in worked if stat[b["combo"]]["status"] == "confirmed")
                n_not = len(worked) - n_conf
                bits = ([f"{n_conf} confirmed"] if n_conf else []) + ([f"{n_not} not ordering"] if n_not else [])
                rows = "".join(_cpo_rec_row(s, b, r, stat[b["combo"]], month,
                                            promoted=b in promoted, horizon_html=_strip(b), ln=ln)
                               for r, b in worked)
                block.append(work_group(f"Worked — {len(worked)} · {' · '.join(bits)}", safe(rows)))

            # NOT ORDERABLE -> FIND REPLACEMENT: re-run the certified horizon for a same-family orderable
            # substitute; never substitute by nearest code/trim/colour, and allow NO SUBSTITUTE.
            for b in shown:
                if stat[b["combo"]]["status"] == "not_orderable":
                    block.append(_cpo_replacement_block(b, mo, recs, stat, month))

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
        order = _int_or0(req.form.get("order"))
        lines = _ws_get(app, s.scope, f"cpo_line::{month}", {}) or {}
        qty = _ws_get(app, s.scope, f"cpo_line_qty::{month}", {}) or {}
        if state == "confirmed":                          # full order secured (idempotent)
            lines[combo] = "confirmed"
            qty.pop(combo, None)
        elif state in ("not_ordered", "not_orderable"):   # not_orderable also triggers replacement search
            lines[combo] = state
            qty.pop(combo, None)
        elif state == "partial":                          # only k of N secured; remainder returns to unresolved
            k = _int_or0(req.form.get("qty"))
            lines.pop(combo, None)
            if k <= 0:
                qty.pop(combo, None)
            elif order and k >= order:                    # k>=N is a full confirm, not a partial
                lines[combo] = "confirmed"
                qty.pop(combo, None)
            else:
                qty[combo] = k
        elif state == "clear":
            lines.pop(combo, None)
            qty.pop(combo, None)
        _ws_put(app, s.scope, f"cpo_line::{month}", lines)
        _ws_put(app, s.scope, f"cpo_line_qty::{month}", qty)
        anchor = f"#combo-{combo}" if combo else ""       # keep the operator's context, not back to the top
        return Response.redirect(f"/ordering/cpo?month={month}{anchor}")

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
        windows = _ws_get(app, s.scope, "ppo_windows", []) or []
        pick = (f'<form method="get" action="/ordering/ppo" class="mut"><label>Open PPO window</label>'
                + _select("window", [(w, w) for w in windows] or [("", "— none yet —")], window, onchange=True)
                + '<noscript><button type=submit class=secondary>Open</button></noscript></form>') if windows else ""
        create = form("/ordering/ppo/new",
                      '<label>Create PPO window (month)</label>' + _month_select(app, "month", _default_month(app)),
                      csrf=s.csrf_token, submit="Create window")
        parts = [f'<div class="card"><h2>PPO — portfolio decision</h2>{pick}{create}'
                 '<p class="muted">Enter each manufacturer-<strong>offered</strong> unit (this is the offer, not '
                 'your decision). Elite evaluates the whole offered set against the certified position and '
                 'recommends <strong>FIRM / DENY / REVIEW</strong> for each — firming one recomputes the rest. You '
                 'then confirm or override. A confirmed <strong>FIRM becomes committed Supply</strong> that the '
                 'rest of Elite counts (once); it does not create an authoritative vehicle or invent a VIN.</p></div>']
        if window:
            from ...ordering.ppo_commitments import evaluate_window
            certs, label_to_key = _certified_positions(app, s.scope)
            key_for = lambda o: label_to_key.get(o.get("combo", ""), o.get("combo", ""))
            res = evaluate_window(offers, certs, key_for_offer=key_for)
            verdicts, worked = res["verdicts"], res["worked"]
            combos = [lbl for _cid, lbl in _known_combos(app, s.scope)]
            entry = form("/ordering/ppo/offer",
                         f'<input type=hidden name=window value="{esc(window)}">'
                         '<label>Offered combination (select a known combination; type only for a truly external one)</label>'
                         + _datalist_input("combo", "ppo_combos", combos, placeholder="select or type external")
                         + '<label>Quantity offered</label>'
                         '<input name=quantity type=number min=1 value=1 style="max-width:90px">'
                         '<label>VIN (optional — names the physical unit when known)</label>'
                         '<input name=vin placeholder="VIN" style="max-width:240px" autocomplete=off>'
                         '<label>Stock # (optional)</label><input name=stock placeholder="stock" style="max-width:140px">'
                         '<label class=mut><input type=checkbox name=external value=1> Truly external offer '
                         '(orderability unknown → REVIEW)</label>',
                         csrf=s.csrf_token, submit="Add offer (Elite will evaluate)")

            # top summary: Offered N · Firmed N · Denied N · Review N · Unworked N
            parts.append(f'<div class="card"><h3>{esc(window)}</h3>'
                         f'<p><strong>{esc(res["summary"])}</strong></p>'
                         '<p class="muted">Firmed decisions are already reflected in the remaining '
                         'recommendations.</p>' + entry + '</div>')

            # recommendation-first offer table: answer first, then physical/qty/timing/why, then operator action
            orows = []
            for o in offers:
                oid = str(o.get("id") or o.get("combo"))
                w = worked.get(oid)
                if w is not None:
                    # LOCKED worked decision — the machine recommendation is the PRESERVED audit, not a live recompute
                    if w["override"]:
                        decided = badge("stale", f'OVERRIDE: Elite said {w["recommendation"] or "—"} → Kyle '
                                        f'{w["action"]} {w["qty"]}')
                    elif w["action"] in ("FIRM", "PARTIAL"):
                        decided = badge("completed", f'FIRMED {w["qty"]} — counted in committed supply')
                    else:
                        decided = badge("skip", 'DENIED — contributes 0 supply')
                    phys = (f'{esc(o.get("vin"))}' if o.get("vin") else (f'stk {esc(o.get("stock"))}' if o.get("stock")
                            else '<span class="muted">combination-level (no VIN)</span>'))
                    rec_lbl = f'{w["recommendation"]}' + (f' {w["recommended_qty"]}' if w["recommendation"] == "FIRM" else '')
                    orows.append([esc(o.get("combo", "")), safe(phys), esc(w["qty"] or "—"), esc("—"),
                                  safe(badge("pending", rec_lbl or "—")), esc("recorded " + (w["at"] or "")),
                                  safe(decided)])
                    continue
                v = verdicts.get(oid)
                if v is None:
                    continue
                tone = {"FIRM": "completed", "DENY": "skip", "REVIEW": "pending"}.get(v.recommendation, "pending")
                phys = (f'{esc(v.vin)}' if v.vin else (f'stk {esc(v.stock)}' if v.stock else
                        '<span class="muted">combination-level (no VIN)</span>'))
                orows.append([esc(o.get("combo", "")), safe(phys),
                              esc(v.recommended_qty if v.recommendation == "FIRM" else "—"),
                              esc(v.availability or "—"), safe(badge(tone, v.recommendation)), esc(v.why),
                              safe(_ppo_action_form(s, window, o, v))])
            parts.append('<div class="card"><h3>Offers — Elite recommendation first</h3>'
                         + (table(["Offered", "Physical unit", "Firm qty", "Timing", "Recommendation", "Why",
                                   "Your action"], orows) if orows else '<p class="muted">No offers entered yet.</p>')
                         + form("/ordering/ppo/revert", f'<input type=hidden name=window value="{esc(window)}">',
                                csrf=s.csrf_token, submit="Clear window (cancels committed units)") + '</div>')
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
        from ...ids import new_id
        window = req.form.get("window") or ""
        combo = (req.form.get("combo") or "").strip()
        try:
            qty = max(1, int(req.form.get("quantity") or 1))
        except (TypeError, ValueError):
            qty = 1
        if window and combo:
            offers = _ws_get(app, s.scope, f"ppo_offers::{window}", []) or []
            offers.append({"id": new_id("ppo"), "combo": combo, "quantity": qty,
                           "vin": (req.form.get("vin") or "").strip().upper() or None,
                           "stock": (req.form.get("stock") or "").strip() or None,
                           "external": bool(req.form.get("external")),
                           "at": to_utc_iso(app.stack.clock.now())[:10]})
            _ws_put(app, s.scope, f"ppo_offers::{window}", offers)
            _ws_put(app, s.scope, "ppo_current_window", window)
            windows = _ws_get(app, s.scope, "ppo_windows", []) or []
            if window not in windows:
                windows.append(window)
                _ws_put(app, s.scope, "ppo_windows", windows)
        return Response.redirect(f"/ordering/ppo?window={window}")

    @app.post("/ordering/ppo/record")
    def ppo_record(app, req):
        """Record Kyle's ACTUAL execution. This (a) PRESERVES the machine recommendation at the moment he acted
        — computed against the disposable state of every other already-worked offer, so a later recomputation
        can never rewrite whether he followed or overrode Elite — and (b) makes a confirmed FIRM/PARTIAL enter
        the governed Committed Supply rail once (DENY / override-to-deny reverses it)."""
        from ...ordering.ppo_commitments import machine_recommendation_at
        from ...clock import to_utc_iso
        s = req.session
        app.require(s, "workspace.view")
        window = req.form.get("window") or ""
        oid = req.form.get("offer") or ""
        action = req.form.get("action") if req.form.get("action") in ("FIRM", "DENY", "PARTIAL") else "DENY"
        try:
            aqty = int(req.form.get("action_qty") or 0)
        except (TypeError, ValueError):
            aqty = 0
        offers = _ws_get(app, s.scope, f"ppo_offers::{window}", []) or []
        certs, label_to_key = _certified_positions(app, s.scope)
        key_for = lambda o: label_to_key.get(o.get("combo", ""), o.get("combo", ""))
        # preserve the machine recommendation AT THIS MOMENT (against the other worked offers' disposable state)
        rec = machine_recommendation_at(offers, certs, oid, key_for_offer=key_for) or {}
        for o in offers:
            if str(o.get("id")) == oid:
                act = "FIRM" if action == "PARTIAL" else action
                qty = aqty if action in ("FIRM", "PARTIAL") else 0
                o["operator_action"] = act
                o["operator_qty"] = qty
                # persisted audit — never rewritten by a later recomputation (item 3/5, acceptance 10)
                o["recommended_action"] = rec.get("recommendation", "")
                o["recommended_qty"] = rec.get("recommended_qty", 0)
                o["actual_action"] = act
                o["actual_qty"] = qty
                o["override"] = bool(rec.get("recommendation")) and (
                    rec.get("recommendation") != act or int(rec.get("recommended_qty") or 0) != qty)
                o["recorded_at"] = to_utc_iso(app.stack.clock.now())
                # governed Committed Supply — created once for a FIRM/PARTIAL, reversed for a DENY (idempotent)
                _ppo_sync_commitments(app, s.scope, o, key_for(o))
                break
        _ws_put(app, s.scope, f"ppo_offers::{window}", offers)
        return Response.redirect(f"/ordering/ppo?window={window}")

    @app.post("/ordering/ppo/revert")
    def ppo_revert(app, req):
        """Clear the window. Committed Supply is NOT silently destroyed: each firmed offer's governed commitment
        is explicitly cancelled (a reversal), and Kyle is told how many committed units were released."""
        s = req.session
        app.require(s, "workspace.view")
        window = req.form.get("window") or ""
        offers = _ws_get(app, s.scope, f"ppo_offers::{window}", []) or []
        released = sum(_ppo_release_commitments(app, s.scope, o, reason="ppo_window_cleared") for o in offers)
        _ws_put(app, s.scope, f"ppo_offers::{window}", [])
        s.flash = (f"PPO window cleared — {released} committed unit(s) cancelled." if released
                   else "PPO window cleared.")
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
        from .domains import _source_descriptions
        descs = _source_descriptions(app, s.scope)      # physical DMS Descriptions for human trim/drivetrain
        now, future = [], []
        for r in rows:
            try:
                dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
            except Exception:   # noqa: BLE001
                dec = {}
            arr, inc = int(dec.get("arrived_excess", 0) or 0), int(dec.get("incoming_excess", 0) or 0)
            canonical = ident.get(r["combination_id"], r["combination_id"])
            readable = _readable_h(app, s.scope, canonical, descriptions=descs)                 # operator: human + codes
            dealer_name = _readable_h(app, s.scope, canonical, dealer=True, descriptions=descs)  # dealer: names lead
            if arr > 0:
                now.append({"identity": readable, "dealer": dealer_name, "qty": arr, "pid": r["id"],
                            "dts": dec.get("dts_burden", "—"), "key": _plan_key_of(canonical)})
            if inc > 0:
                future.append({"identity": readable, "qty": inc, "pid": r["id"]})
        now.sort(key=lambda d: (-d["qty"], d["identity"]))
        future.sort(key=lambda d: (-d["qty"], d["identity"]))

        # PHYSICAL-UNIT COMPLETION: for each arrived-excess combination, name the exact N on-ground VINs to move
        # (oldest first) and, separately, the unit(s) being retained. Real inventory only; never a fabricated VIN.
        def _unit_cell(u):
            who = u["vin"] or u["stock"] or u["serial"] or "—"
            age = f' · {u["dis"]}d in stock' if u["dis"] is not None else ""
            return esc(who) + (f'<span class="muted" style="font-size:12px"> (stock {esc(u["stock"])}{age})</span>'
                               if u["stock"] and who != u["stock"] else esc(age))
        phys_html = ""
        for d in now:
            units = _wholesale_on_ground(app, s.scope, d["key"])
            if not units:
                continue
            n = min(d["qty"], len(units))
            move, keep = units[:n], units[n:]
            move_tbl = table(["Dispose (oldest first)", "Days in stock"],
                             [[safe(_unit_cell(u)), esc("—" if u["dis"] is None else u["dis"])] for u in move])
            keep_tbl = (table(["Retain on ground", "Days in stock"],
                              [[safe(_unit_cell(u)), esc("—" if u["dis"] is None else u["dis"])] for u in keep])
                        if keep else '<p class="muted">No units retained in this combination.</p>')
            short = "" if n >= d["qty"] else (f'<p class="muted">Only {n} on-ground VIN(s) found for a stated '
                                             f'excess of {d["qty"]} — showing the units that exist; none invented.</p>')
            phys_html += (f'<details class="card"><summary style="cursor:pointer;font-weight:600">'
                          f'{esc(d["identity"])} — move {n} of {len(units)} on ground</summary>'
                          f'<div style="margin-top:8px">{move_tbl}{short}<div style="margin-top:8px">{keep_tbl}</div>'
                          '</div></details>')

        nrows = [[esc(i + 1),
                  safe(f'<a href="/combination/{esc(d["pid"])}">{esc(d["identity"])}</a>'),
                  esc(d["qty"]), esc(d["dts"])] for i, d in enumerate(now)]
        dealer_text = "\n".join(f'{d["dealer"]} — {d["qty"]} available' for d in now)
        copy = ('<h3>Dealer list (safe to send)</h3>'
                f'<textarea id="dl" readonly rows="{max(2, len(now)+1)}" '
                'style="max-width:520px;font-family:monospace">' + esc(dealer_text) + '</textarea>'
                '<div style="margin-top:8px"><button type=button onclick="'
                "navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('dl').value);"
                'this.textContent=&quot;Copied&quot;">Copy dealer list</button></div>'
                '<p class="muted">Copied text is combination + quantity only — no rank, age, or internal reasoning.</p>')
        frows = [[safe(f'<a href="/combination/{esc(d["pid"])}">{esc(d["identity"])}</a>'), esc(d["qty"])]
                 for d in future]
        phys_section = ('<div class="card"><h2>Physical units to move (exact VINs, oldest first)</h2>'
                        '<p class="muted">For each arrived over-stock combination, the exact on-ground unit(s) to '
                        'dispose and the unit(s) to retain. Real inventory only — no VIN is invented, and incoming '
                        'units are never mixed in here.</p>' + phys_html + '</div>') if phys_html else ""
        body = ('<div class="card"><h2>What to move first</h2>'
                '<p class="muted">Ranked by disposition readiness (arrived over-stock). Click a combination for '
                'Recommendation → Why → Proof. Within a combination, dispose the oldest appropriate unit first.</p>'
                + table(["#", "Combination", "To move", "DTS burden"], nrows) + copy + '</div>'
                + phys_section
                + '<div class="card"><h2>Future changes (incoming to redirect)</h2>'
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
        # Unavailable marks are STABLE UNIT KEYS, so they survive a re-paste / reordered snapshot (they bind to
        # the unit/order, not a row position). Keys that no longer match any pasted unit are simply inert.
        prior = _ws_get(app, s.scope, "trade_their", {}) or {}
        _ws_put(app, s.scope, "trade_their", {
            "requested": (req.form.get("requested") or "").strip(),
            "inv_raw": inv_raw,
            # Keep legacy line storage for backward compatibility with old sessions.
            "inv": [ln.strip() for ln in inv_raw.splitlines() if ln.strip()],
            "unavail": sorted(str(x) for x in prior.get("unavail", []) if isinstance(x, str))})
        s.flash = "Their-trade session saved."
        return Response.redirect("/dealer-trade?tab=their")

    @app.post("/dealer-trade/their/unavailable")
    def their_unavail(app, req):
        # Exclude the exact unit/order by its STABLE identity key (dealer + stage + stock + serial/order), never
        # by row position — so a re-pasted / reordered snapshot keeps the same unit unavailable and no
        # configuration-wide blacklist ever occurs.
        s = req.session
        app.require(s, "workspace.view")
        st = _ws_get(app, s.scope, "trade_their", {}) or {}
        key = (req.form.get("key") or "").strip()
        if key:
            un = {str(x) for x in st.get("unavail", [])}   # keys only (legacy int-index marks are ignored)
            un.add(key)
            st["unavail"] = sorted(un)
            _ws_put(app, s.scope, "trade_their", st)
        return Response.redirect("/dealer-trade?tab=their")

    @app.post("/dealer-trade/our")
    def our_save(app, req):
        s = req.session
        app.require(s, "workspace.view")
        _ws_put(app, s.scope, "trade_our", {"needed": (req.form.get("needed") or "").strip(),
                                            "demanded": (req.form.get("demanded") or "").strip()})
        s.flash = "Our-trade session saved."
        return Response.redirect("/dealer-trade?tab=our")

    # ---- Demos — manager operating board (KEEP / PLAN SWAP / SWAP NOW / PULL) --------------------------
    @app.get("/demos")
    def demos(app, req):
        from ...operatorstd import demo_board as DB
        from ...clock import to_utc_iso
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        today = to_utc_iso(app.stack.clock.now())[:10]
        meta, alloc, pools = _demo_cockpit(app, s.scope, roster, today)
        _tone = {DB.KEEP: "completed", DB.PLAN_SWAP: "need", DB.SWAP_NOW: "need", DB.PULL: "pending",
                 DB.REVIEW: "unresolved"}
        n_active = len(meta)
        counts = {}
        for m in meta.values():
            counts[m["decision"].state] = counts.get(m["decision"].state, 0) + 1
        summary = " · ".join(f"{k} {v}" for k, v in counts.items()) or "no active demos"

        rows = []
        for u in roster:
            uid = u["id"]
            if uid not in meta:
                rows.append([safe(f'<a href="/demos/user/{esc(uid)}">{esc(u["name"])}</a>'),
                             '<span class="muted">no demo assigned</span>', "—", "—", "—", "—",
                             safe(badge("stale", "NO DEMO")), "—", "—"])
                continue
            m = meta[uid]
            cur = u.get("current") or {}
            dec, ms = m["decision"], m["ms"]
            # human build + ONE operational unit tag (no full VIN, no "Unit X · Unit X" duplication)
            build = _demo_current_build(app, s.scope, cur.get("vin")) or ""
            unit_tag = _mask_vin(cur.get("vin"))
            build_h = build if (build and (cur.get("vin", "") or "").upper() not in build.upper()) else ""
            demo_cell = safe(f'{esc(build_h)} <span class="muted">· {esc(unit_tag)}</span>' if build_h
                             else f'{esc(unit_tag)}')
            inv_age = _demo_inv_age(app, s.scope, cur.get("vin"))
            # forecast is never blank when an assignment date exists: cadence window (+ learned ETA when known)
            cwin = DB.cadence_window_date(cur.get("start"))
            if ms.velocity is not None and ms.estimated is not None:
                fore = esc(f"~{ms.estimated:,} mi est · {ms.velocity} mi/day ({ms.confidence})")
            elif cwin:
                fore = esc(f"cadence window ~{cwin} · mileage learning")
            else:
                fore = '<span class="muted">—</span>'
            a = alloc.get(uid, {})
            path, unit = a.get("path", "NONE"), a.get("unit")
            pool = pools.get(m["target"]) or {}
            if path == "USE NOW":
                rep = badge("completed", "USE NOW") + " " + esc(_demo_unit_label(app, s.scope, unit,
                                                                                 combination_id=m["target"]))
                if len(pool.get("current", [])) <= 1:
                    rep += ' <span class="badge" style="color:var(--timing)">LAST ONE — protect/reorder first</span>'
            elif path == "WAIT":
                rep = badge("need", "WAIT FOR INCOMING") + " " + esc(_demo_unit_label(app, s.scope, unit,
                                                                                     combination_id=m["target"]))
            elif path == "ORDER":
                # deterministic identity is NOT proof the factory accepts an order today (CTP discipline)
                if pool.get("orderable"):
                    rep = badge("pending", "ORDER FOR DEMO") + " " + esc(pool.get("label", ""))
                else:
                    rep = badge("unresolved", "ORDER PATH — REVIEW") + \
                        ' <span class="muted">current orderability unresolved</span>'
            else:
                rep = '<span class="muted">—</span>'
            secured = path in ("USE NOW", "WAIT")
            outgoing = _demo_outgoing(dec.state, replacement_secured=secured, sl_need=m.get("sl_need", False))
            out_cell = safe(badge("pending", outgoing)) if outgoing else '<span class="muted">—</span>'
            rows.append([safe(f'<a href="/demos/user/{esc(uid)}">{esc(u["name"])}</a>'),
                         demo_cell, esc(inv_age), esc(f'{dec.days}d' if dec.days is not None else "—"),
                         esc(ms.display()), safe(fore), safe(badge(_tone.get(dec.state, "stale"), dec.state)),
                         safe(rep), out_cell])

        add = form("/demos/user",
                   '<label>Name</label><input name=name required style="max-width:260px">'
                   '<label>Role / title</label><input name=role style="max-width:260px">'
                   '<label>Model preference</label>'
                   + _select("model_pref", [("", "— any —")] + [(m, m) for m in _known_models(app, s.scope)])
                   + '<label>Trim preference</label><input name=trim_pref style="max-width:200px">',
                   csrf=s.csrf_token, submit="Add user")
        headline = f"{n_active} active · " + " · ".join(
            f"{k} {counts[k]}" for k in (DB.KEEP, DB.PLAN_SWAP, DB.SWAP_NOW, DB.PULL, DB.REVIEW) if counts.get(k))
        # anticipated returns — a demo about to swap comes back to retail; represent once so Ordering can see it
        returning = DB.anticipated_returns([{"unit": (m["user"].get("current") or {}).get("vin"),
                                             "state": m["decision"].state} for m in meta.values()])
        ret_note = (f'<p class="muted">{len(returning)} demo(s) expected to return to retail — represented once '
                    f'in future supply so Ordering does not replace a vehicle that is about to come back.</p>'
                    if returning else "")
        _act_tone = {DB.USE_NOW: "completed", DB.WAIT_FOR_INCOMING: "need", DB.REORDER_BEFORE_PULLING: "pending",
                     DB.ORDER_FOR_DEMO: "pending", DB.ORDER_REVIEW: "unresolved", DB.NOT_SAFE: "unresolved"}
        best = _demo_best_candidates(app, s.scope)
        best_sections = ""
        for model in ("QX60", "QX65", "QX80"):
            crows = []
            for c in best.get(model, []):
                pf = c.get("proof") or {}
                proof_txt = (f'expected demand {pf.get("expected_demand")}, days-to-sell {pf.get("days_to_sell_burden")}, '
                             f'planning depth {pf.get("planning_depth")}, certified need {pf.get("certified_need")}, '
                             f'score {pf.get("score")}')
                why = (esc(c["why"]) + (f' <span class="muted">· {esc(c["note"])}</span>' if c["note"] else "")
                       + f'<details><summary style="cursor:pointer;color:var(--accent);font-size:12px">'
                         f'Technical Proof</summary><span class="muted" style="font-size:12px">{esc(proof_txt)}'
                         f'</span></details>')
                crows.append([esc(f'#{c["rank"]}'), esc(c["build"]), safe(why),
                              esc(f'{c["on_ground"]} on-ground'), esc(f'{c["incoming"]} incoming'),
                              esc(c["inv_age"]), safe(badge(_act_tone.get(c["action"], "stale"), c["action"]))])
            if crows:
                best_sections += (f'<h3 style="margin:14px 0 4px">{esc(model)}</h3>'
                                  + table(["#", "Build", "Why it's a good Demo", "On ground", "Incoming",
                                           "Inv age", "Action"], crows))
        best_card = ('<div class="card"><h2>Best Demo Candidates</h2>'
                     '<p class="muted">Proven fast movers ranked by Demo suitability (Speed-to-Sell velocity, '
                     'inventory depth, retail protection) — not the largest shortage. No VINs, no economics on '
                     'this surface.</p>' + (best_sections or '<p class="muted">No governed Demo candidates in '
                     'the current certified plan.</p>') + '</div>') if best else ""
        body = (f'<div class="card"><h2>Executive Demo board</h2><p><strong>{esc(headline)}</strong></p>'
                '<p class="muted">Firmed swap decisions are sequenced as one portfolio — a replacement unit is '
                'never assigned to two executives. Replacement paths protect the retail position first; '
                'replacements are ranked by Demo suitability (proven fast movers), not the largest shortage.</p>'
                + table(["Executive", "Current demo", "Inv age", "Demo days", "Mileage / learning", "Forecast",
                         "Decision", "Replacement", "Outgoing"], rows) + ret_note + '</div>'
                + best_card
                + '<div class="card"><h3>Add a demo user</h3>' + add + '</div>')
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
        from ...operatorstd import demo_board as DB
        cur = u.get("current") or {}
        from ...clock import to_utc_iso
        today = to_utc_iso(app.stack.clock.now())[:10]
        build = _demo_current_build(app, s.scope, cur.get("vin")) if cur else ""
        assignment_mi, obs, cycles = _demo_observations(u) if cur else (None, [], [])
        ms = (DB.mileage_state(cur.get("start"), assignment_mi, obs, today, completed_cycles=cycles)
              if cur else DB.MileageState())
        vel = ms.velocity
        info = kv([("Role", u.get("role", "")), ("Prefers", f'{u.get("model_pref","")} {u.get("trim_pref","")}'.strip()),
                   ("Current demo", (build or "—") if cur else "—"),
                   ("Current demo VIN", cur.get("vin", "—")), ("Start date", cur.get("start", "—")),
                   ("Mileage at assignment", f"{ms.assignment_mileage:,} mi (assignment fact, not current)"
                    if ms.assignment_mileage is not None else "—"),
                   ("Current actual odometer", f"{ms.actual:,} mi ({ms.actual_date})"
                    if ms.actual is not None else "not yet observed"),
                   ("Estimated today", f"~{ms.estimated:,} mi (estimate, not an odometer)"
                    if (ms.estimated is not None and ms.source != "unknown") else "—"),
                   ("Personal mileage velocity", f"{vel} mi/day ({ms.confidence})" if vel is not None else "—")])

        # ---- DECISION A — the operating call (KEEP / PLAN SWAP / SWAP NOW / PULL); never a dead-end on mileage ---
        decA = DB.decide(cur.get("start"), today, ms, pull_reason=u.get("pull_reason", "")) if cur else None
        _a_tone = {DB.KEEP: "completed", DB.PLAN_SWAP: "need", DB.SWAP_NOW: "need", DB.PULL: "pending",
                   DB.REVIEW: "unresolved"}
        _a_badge = badge(_a_tone.get(decA.state, "stale"), decA.state) if decA else badge("stale", "NO DEMO ASSIGNED")
        mileage_form = (form("/demos/user/" + u["id"] + "/mileage",
                             '<label>Current odometer reading</label>'
                             '<input name=mi type=number required style="max-width:160px">',
                             csrf=s.csrf_token, submit="Record current mileage") if cur else "")
        _odo_note = ('<p class="muted">An actual odometer is required before final swap execution.</p>'
                     if (decA and decA.needs_odometer) else "")
        _a_detail = decA.detail if decA else "No demo is currently assigned."
        decA_card = ('<div class="card"><h3>Decision A — Operating call</h3>'
                     f'<p>{safe(_a_badge)}</p>'
                     f'<p class="muted">{esc(_a_detail)}</p>'
                     + _odo_note + (mileage_form if cur else "") + '</div>')

        # ---- REPLACEMENT PLAN — the SAME governed portfolio decision the Executive Demo board produced ----
        # The detail page is a second PRESENTATION of the one decision rail: it reuses _demo_cockpit's output
        # for this executive (same portfolio sequencing, same suitability ranking, same selected unit, same
        # outgoing) and only adds deeper explanation. It never re-ranks by certified Need or runs a competing
        # Demo-economic selection.
        meta_all, alloc_all, pools_all = _demo_cockpit(app, s.scope, roster, today)
        m = meta_all.get(u["id"])
        if not cur or m is None:
            decB_card = ('<div class="card"><h3>Replacement plan</h3>'
                         + empty("No active demo — no replacement is planned.") + '</div>')
        else:
            a = alloc_all.get(u["id"], {})
            path, unit = a.get("path", "NONE"), a.get("unit")
            tgt = m["target"]
            pool = pools_all.get(tgt) or {}
            sut = pool.get("suitability")
            if path == "USE NOW":
                head = safe(badge("completed", "USE NOW") + " "
                            + esc(_demo_unit_label(app, s.scope, unit, combination_id=tgt)))
            elif path == "WAIT":
                head = safe(badge("need", "WAIT FOR INCOMING") + " "
                            + esc(_demo_unit_label(app, s.scope, unit, combination_id=tgt)))
            elif path == "ORDER":
                head = safe((badge("pending", "ORDER FOR DEMO") + " " + esc(pool.get("label", "")))
                            if pool.get("orderable") else
                            (badge("unresolved", "ORDER PATH — REVIEW")
                             + ' <span class="muted">current orderability unresolved</span>'))
            else:
                head = safe(badge("stale", "—") + ' <span class="muted">no eligible governed replacement</span>')
            secured = path in ("USE NOW", "WAIT")
            outgoing = _demo_outgoing(m["decision"].state, replacement_secured=secured,
                                      sl_need=m.get("sl_need", False))
            out_line = (f'<p>Outgoing demo: {safe(badge("pending", outgoing))}</p>' if outgoing else "")
            # deeper EXPLANATION of the same decision (business language; exact numbers in Technical Proof)
            og, inc = len(pool.get("current", [])), len(pool.get("incoming", []))
            expl = []
            if sut is not None and sut.reasons:
                expl.append("Why this build ranks as a good Demo: " + esc(" · ".join(sut.reasons))
                            + (f' <span class="muted">· {esc(sut.note)}</span>' if sut.note else ""))
            expl.append(f"Physical path: {og} on-ground · {inc} incoming.")
            if path == "WAIT":
                expl.append("No on-ground unit was selected — the incoming unit is the superior/retail-safe path.")
            if og <= 1 and path in ("USE NOW",):
                expl.append("Last retail unit of a desirable combination — protect / reorder before pulling.")
            if m["decision"].needs_odometer:
                expl.append("Current odometer is still required before final physical swap execution.")
            expl_html = "".join(f'<p class="muted">{x}</p>' for x in expl)
            proof = ""
            if sut is not None and sut.proof:
                pf = sut.proof
                proof = ('<details><summary style="cursor:pointer;color:var(--accent);font-size:12px">'
                         'Technical Proof (optional / Strategy)</summary><span class="muted" style="font-size:12px">'
                         f'expected demand {pf.get("expected_demand")}, days-to-sell {pf.get("days_to_sell_burden")}, '
                         f'planning depth {pf.get("planning_depth")}, certified need {pf.get("certified_need")}, '
                         f'suitability score {pf.get("score")}</span></details>')
            decB_card = ('<div class="card"><h3>Replacement plan '
                         '<span class="badge">from the Executive Demo board</span></h3>'
                         f'<p>{head}</p>' + out_line + expl_html + proof + '</div>')

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
        hrows = [[esc(h.get("vin", "")), esc(h.get("mi_in", "")), esc(h.get("mi_out", "")),
                  esc(h.get("miles", "")), esc(h.get("start", "")), esc(h.get("end", ""))] for h in u.get("history", [])]
        body = (f'<p><a href="/demos">← Roster</a></p><div class="card"><h2>{esc(u["name"])}</h2>{info}</div>'
                + decA_card + decB_card
                + '<div class="card"><h3>Assign / swap</h3>' + assign + ret + '</div>'
                '<div class="card"><h3>Demo history</h3>'
                + table(["VIN", "Miles in", "Miles out", "Driven", "Start", "End"], hrows) + '</div>')
        return _resp(app, s, u["name"], body, "/demos")

    @app.post("/demos/user/{uid}/mileage")
    def demos_mileage(app, req):
        from ...clock import to_utc_iso
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        today = to_utc_iso(app.stack.clock.now())[:10]
        for u in roster:
            if u["id"] == req.params["uid"] and u.get("current"):
                mi = _int_or0(req.form.get("mi"))
                u["current"]["mi_now"] = mi
                # store a DATED, observed odometer point (mileage learning uses only observed readings)
                u.setdefault("mileage_obs", []).append({"date": today, "miles": mi, "source": "manual_reading"})
                _ws_put(app, s.scope, "demo_roster", roster)
                s.flash = "Current mileage recorded."
                break
        return Response.redirect("/demos/user/" + req.params["uid"])

    @app.post("/demos/user/{uid}/assign")
    def demos_assign(app, req):
        s = req.session
        app.require(s, "workspace.view")
        roster = _ws_get(app, s.scope, "demo_roster", []) or []
        for u in roster:
            if u["id"] == req.params["uid"]:
                start = (req.form.get("start") or "").strip()
                mi_in = _int_or0(req.form.get("mi"))
                u["current"] = {"vin": (req.form.get("vin") or "").strip(), "start": start, "mi_in": mi_in}
                # the assignment reading is a dated observation, and the assignment itself is a history event
                if start:
                    u.setdefault("mileage_obs", []).append({"date": start, "miles": mi_in, "source": "assignment"})
                u.setdefault("events", []).append({"kind": "assignment", "date": start, "vin": u["current"]["vin"],
                                                   "mileage": mi_in})
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
                end = (req.form.get("date") or "").strip()
                cur["mi_out"] = mi_out
                cur["end"] = end
                cur["miles"] = max(0, mi_out - _int_or0(cur.get("mi_in")))
                if end:
                    u.setdefault("mileage_obs", []).append({"date": end, "miles": mi_out, "source": "return"})
                u.setdefault("events", []).append({"kind": "return", "date": end, "vin": cur.get("vin"),
                                                   "mileage": mi_out, "miles_driven": cur["miles"]})
                u.setdefault("history", []).append(cur)
                u["current"] = None
                _ws_put(app, s.scope, "demo_roster", roster)
                s.flash = "Return recorded; demo returned to retail pool."
                break
        return Response.redirect("/demos/user/" + req.params["uid"])

    # ---- CTP — live multi-file Change-The-Production session -------------------------------------------
    @app.get("/ctp")
    def ctp(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...workflow import ctp_intake as CTP
        from .domains import _source_descriptions
        from ...clock import to_utc_iso
        sess = _ws_get(app, s.scope, "ctp_session", {}) or {}
        files = sess.get("files", [])

        head = ('<div class="wshead"><h1>CTP — What Should I Change?</h1></div>'
                '<p class="muted">Upload the current Infiniti CTP files. Elite will tell you which production '
                'orders to leave alone and which ones to change.</p>')

        # SECTION A — upload + loaded-file chips
        add = ('<form method="post" action="/ctp/upload" enctype="multipart/form-data" class="mut">'
               f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
               '<input type=file name=file accept=".csv,.tsv,.txt,.xls,.xlsx" required> '
               '<button type=submit>Add CTP File</button>'
               '<span class="muted" style="margin-left:10px">Add QX60, QX65, QX80, or any other current Infiniti '
               'CTP file. You can add more than one.</span></form>')
        chips = ""
        for i, f in enumerate(files):
            chips += (f'<span class="chip">{esc(f.get("model") or "?")} — {len(f.get("candidates", []))} orders '
                      f'<form class="mut" method="post" action="/ctp/remove" style="display:inline">'
                      f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}"><input type=hidden name=idx value="{i}">'
                      f'<button type=submit title="Remove file" '
                      f'style="padding:0 4px;background:none;border:none;color:var(--muted);cursor:pointer">✕</button>'
                      f'</form></span> ')
        clear = ('<form class="mut" method="post" action="/ctp/clear" style="display:inline;margin-left:6px">'
                 f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                 '<button type=submit class=secondary>Clear session</button></form>') if files else ""
        upload_card = f'<div class="card"><h2>Add CTP File</h2>{add}<div style="margin-top:10px">{chips}{clear}</div></div>'

        if not files:
            return _resp(app, s, "CTP", head + upload_card + '<div class="card"><p>No CTP files loaded yet.</p></div>',
                         "/ctp")

        # parse session → reconcile → evaluate (state machine)
        candidates = [CTP.Candidate(**c) for f in files for c in f.get("candidates", [])]
        descs = _source_descriptions(app, s.scope)
        pipeline = _ctp_pipeline_rows(app, s.scope)
        reconciled = CTP.reconcile(candidates, pipeline)
        board = _ctp_board(app, s.scope, descriptions=descs)
        now = to_utc_iso(app.stack.clock.now())[:16].replace("T", " ")
        # STALE-BOARD PROTECTION: a KEEP/CHANGE must never be issued from a certified board older than the
        # Inventory/Pipeline snapshot it evaluates. When the board is not derived from the current Pipeline,
        # CTP gates every order to NEEDS ATTENTION instead of KEEP/CHANGE (it never recomputes planning itself).
        from ...newinv.board_recompute import board_status as _board_status
        try:
            _bstat = _board_status(app, s.scope)
        except Exception:   # noqa: BLE001
            _bstat = {"state": "unknown", "detail": "Board status unavailable."}
        confirmed = _ws_get(app, s.scope, "ctp_confirmed", {}) or {}
        if _bstat.get("state") != "current":
            recs = []
            for rc in reconciled:
                _line, _colors, _codes = CTP.human_build(rc.candidate) if rc.candidate else ("", "", "")
                recs.append(CTP.Recommendation(
                    decision_state=CTP.CANT_EVALUATE,
                    order_number=(rc.candidate.order_number if rc.candidate else ""),
                    vin=(rc.candidate.vin if rc.candidate else ""), reconciliation=rc.status,
                    current_line=_line, current_colors=_colors, current_codes=_codes,
                    blocking_reason="certified board not current",
                    reason_plain="Planning board must be recomputed from the current Pipeline.",
                    operator_action_plain="Open Data and press “Recompute current board”, then re-check.",
                    proof={"board_state": _bstat.get("state"), "detail": _bstat.get("detail", "")},
                    evaluation_timestamp=now, candidate=rc.candidate))
        else:
            infeasible = _ws_get(app, s.scope, "ctp_infeasible", {}) or {}
            session_rules = _ws_get(app, s.scope, "ctp_session_rules", {}) or {}
            recs = CTP.evaluate(reconciled, board, now=now, infeasible=infeasible, confirmed=confirmed,
                                session_rules=session_rules)
        summ = CTP.summarize(recs)
        pipe_age = _ctp_pipeline_age(app, s.scope)

        changes = [r for r in recs if r.decision_state == CTP.CHANGE]
        keeps = [r for r in recs if r.decision_state == CTP.KEEP]
        attention = [r for r in recs if r.decision_state == CTP.CANT_EVALUATE]

        # SECTION B — business summary
        model_label = ", ".join(sorted({(f.get("model") or "?") for f in files})) or "OEM"
        b_cards = stat_row([metric(summ["orders"], "Orders available"), metric(summ["ready"], "Ready"),
                            metric(summ["change"], "Change", attn=bool(summ["change"])),
                            metric(summ["keep"], "Keep"),
                            metric(summ["attention"], "Need Attention", attn=bool(summ["attention"]))])
        if summ["ready"] == 0 and summ["attention"]:
            msg = ('<p class="callout">Elite cannot make CTP recommendations until these orders are found in the '
                   'current Pipeline.</p>')
        elif summ["change"] and summ["attention"]:
            msg = (f'<p class="muted">{summ["change"]} change(s) recommended. {summ["keep"]} to keep. '
                   f'{summ["attention"]} order(s) need attention before Elite can decide.</p>')
        elif summ["change"]:
            msg = (f'<p class="muted">{summ["change"]} change(s) recommended. {summ["keep"]} order(s) should stay '
                   f'as they are.</p>')
        elif summ["attention"]:
            msg = f'<p class="muted">{summ["keep"]} ready to keep. {summ["attention"]} need attention.</p>'
        else:
            msg = f'<p class="muted">All {summ["keep"]} orders should stay as they are.</p>'
        summary_card = f'<div class="card"><h2>{summ["orders"]} {esc(model_label)} orders available</h2>{b_cards}{msg}</div>'

        # SECTION B2 — active LEARNED OEM production rules for this session (distinct from exact-config exclusions)
        session_rules = _ws_get(app, s.scope, "ctp_session_rules", {}) or {}
        rule_cards = ""
        _st = session_rules.get("same_trim_only") or {}
        if _st.get("active"):
            taught = _st.get("taught_by", "")
            note = f' — “{esc(_st.get("note"))}”' if _st.get("note") else ""
            when = esc((_st.get("at") or "")[:16].replace("T", " "))
            clear = ('<form method="post" action="/ctp/session-rule-clear" style="display:inline;margin-left:8px">'
                     f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                     '<input type=hidden name=rule value="same_trim_only">'
                     '<button type=submit class=secondary style="padding:2px 8px;font-size:12px">'
                     'Clear this OEM rule</button></form>')
            rule_cards = (
                '<div class="card" style="border-left:4px solid var(--attn,#c60)">'
                f'<h2>{safe(badge("need", "LEARNED OEM RULE"))} Same-trim changes only</h2>'
                '<p class="muted">Elite learned this session that the OEM is not allowing cross-trim CTP changes. '
                'Every remaining order may still be optimized within its own trim (model code / colour / interior); '
                'only cross-trim targets are removed.</p>'
                f'<p class="muted" style="font-size:12px">Taught by {esc(taught) or "an OEM rejection"}'
                f'{note}{(" · " + when) if when else ""}.{safe(clear)}</p></div>')

        parts = [head, upload_card, summary_card]
        if rule_cards:
            parts.append(rule_cards)

        def _build_html(line, colors, codes=""):
            return (f'<div><strong>{esc(line or "—")}</strong></div>'
                    + (f'<div>{esc(colors)}</div>' if colors else "")
                    + (f'<div class="muted" style="font-size:12px">{esc(codes)}</div>' if codes else ""))

        def _proof(r):
            rows_ = [(k, str(v)) for k, v in r.proof.items() if not isinstance(v, dict)]
            for k, v in r.proof.items():
                if isinstance(v, dict):
                    rows_.append((k, ", ".join(f"{kk}={vv}" for kk, vv in v.items())))
            return disclosure("Show proof", kv(rows_))

        _REASON_OPTS = [("production_restriction", "Production restriction"),
                        ("trim_swap_unavailable", "Trim swap not available"),
                        ("package_component_unavailable", "Package / component unavailable"),
                        ("above_maximum", "Above maximum"),
                        ("other_oem_rejection", "Other OEM rejection")]

        def _rejected_history(r):
            """The RECOMMENDED → OEM REJECTED / NOT AVAILABLE → NEXT BEST provenance trail for one order."""
            if not r.rejected_targets:
                return ""
            lbl = dict(_REASON_OPTS)
            items = ""
            for rec in r.rejected_targets:
                why = lbl.get(rec.get("reason", ""), rec.get("reason", "") or "OEM rejection")
                note = f' — “{esc(rec.get("note"))}”' if rec.get("note") else ""
                when = esc((rec.get("at") or "")[:16].replace("T", " "))
                items += (f'<li>{safe(badge("skip", "NOT AVAILABLE"))} '
                          f'{esc(rec.get("target_canonical") or rec.get("target") or "target")} '
                          f'<span class="muted">— {esc(why)}{note}{(" · " + when) if when else ""}</span></li>')
            okey = CTP.order_key(r.order_number, r.vin)
            reset = ('<form method="post" action="/ctp/available-reset" class="mut" style="display:inline">'
                     f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                     f'<input type=hidden name=order value="{esc(okey)}">'
                     '<button type=submit style="padding:0;background:none;border:none;color:var(--muted);'
                     'cursor:pointer;font-size:12px;text-decoration:underline">reset unavailable marks</button></form>')
            return ('<div class="muted" style="font-size:12px;margin-top:6px">'
                    'RECOMMENDED → OEM REJECTED / NOT AVAILABLE → NEXT BEST</div>'
                    f'<ul style="margin:4px 0 0;padding-left:18px">{items}</ul>'
                    f'<div style="margin-top:4px">{reset}</div>')

        def _not_available_form(r):
            """Operator feedback: mark this proposed configuration OEM-infeasible for the whole model's active
            CTP session (recorded under this order for provenance)."""
            opts = "".join(f'<option value="{esc(v)}">{esc(t)}</option>' for v, t in _REASON_OPTS)
            okey = CTP.order_key(r.order_number, r.vin)
            return ('<form method="post" action="/ctp/not-available" class="mut" '
                    'style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">'
                    f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                    f'<input type=hidden name=order value="{esc(okey)}">'
                    f'<input type=hidden name=target value="{esc(r.proposed_combination_id)}">'
                    f'<input type=hidden name=target_canonical value="{esc(r.proof.get("target_combination", ""))}">'
                    f'<select name=reason>{opts}</select>'
                    '<input type=text name=note placeholder="optional reason (as told by OEM)" '
                    'style="min-width:220px">'
                    '<button type=submit class=secondary>Not available configuration</button></form>')

        # SECTION C — actions first
        if changes:
            cc = ""
            for r in changes:
                okey = CTP.order_key(r.order_number, r.vin)
                conf = confirmed.get(okey) or r.confirmed
                state_badge = (badge("completed", "CONFIRMED CHANGED") if conf
                               else badge("need", "RECOMMENDED CHANGE"))
                if conf:
                    # correction path for a mistakenly confirmed execution (unlocks re-optimization)
                    confirm_ctl = ('<form method="post" action="/ctp/confirm-undo" class="mut" '
                                   'style="display:inline;margin-left:8px">'
                                   f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                                   f'<input type=hidden name=order value="{esc(okey)}">'
                                   '<button type=submit class=secondary '
                                   'style="padding:2px 8px;font-size:12px">Undo confirmation</button></form>')
                else:
                    confirm_ctl = ('<form method="post" action="/ctp/confirm-change" class="mut" '
                                   'style="display:inline;margin-left:8px">'
                                   f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
                                   f'<input type=hidden name=order value="{esc(okey)}">'
                                   f'<input type=hidden name=target value="{esc(r.proposed_combination_id)}">'
                                   '<button type=submit>Mark confirmed changed</button></form>')
                cc += ('<div class="card" style="border-left:3px solid var(--accent)">'
                       f'<h3>{safe(state_badge)} {esc(r.order_number or r.vin)}</h3>'
                       '<dl class="kv"><dt>Current</dt><dd>' + _build_html(r.current_line, r.current_colors, r.current_codes)
                       + '</dd><dt>Change to</dt><dd>' + _build_html(r.proposed_line, r.proposed_colors) + '</dd></dl>'
                       f'<p><strong>Why</strong> {esc(r.reason_plain)}</p>'
                       f'<p><strong>What to do</strong> {esc(r.operator_action_plain)}{safe(confirm_ctl)}</p>'
                       + _rejected_history(r)
                       + ("" if conf else _not_available_form(r))
                       + _proof(r) + '</div>')
            parts.append('<div class="card"><h2>What You Should Do</h2>' + cc + '</div>')

        if keeps:
            kc = ""
            for r in keeps:
                kc += ('<div class="card">'
                       f'<h3>{safe(badge("completed", "KEEP"))} {esc(r.order_number or r.vin)}</h3>'
                       + _build_html(r.current_line, r.current_colors, r.current_codes)
                       + f'<p>Leave this order exactly as it is. <span class="muted">{esc(r.reason_plain)}</span></p>'
                       + _rejected_history(r)
                       + _proof(r) + '</div>')
            parts.append('<div class="card"><h2>Keep — leave these as they are</h2>' + kc + '</div>')

        if attention:
            ac = ""
            for r in attention:
                det = kv([("CTP file", r.source_provenance.get("source_file", "")),
                          ("Parsed order #", r.proof.get("ctp_order", r.order_number)),
                          ("Parsed VIN", r.proof.get("ctp_vin", r.vin or "none")),
                          ("Pipeline updated", pipe_age or "not loaded"),
                          ("Order match count", r.proof.get("order_match_count", 0)),
                          ("VIN match count", r.proof.get("vin_match_count", 0))])
                ac += ('<div class="card" style="border-left:3px solid var(--timing)">'
                       f'<h3>{safe(badge("stale", "NEEDS ATTENTION"))} {esc(r.order_number or r.vin)}</h3>'
                       + _build_html(r.current_line, r.current_colors, r.current_codes)
                       + f'<p>{esc(r.reason_plain)}</p>'
                       + f'<p><strong>What to do</strong> {esc(r.operator_action_plain)}</p>'
                       + disclosure("Show matching details", det) + '</div>')
            parts.append('<div class="card"><h2>Orders Elite Can\'t Evaluate Yet</h2>' + ac + '</div>')

        # SECTION D — compact scan table
        trows = []
        for r in recs:
            says = {CTP.KEEP: badge("completed", "Keep"), CTP.CHANGE: badge("need", "Change"),
                    CTP.CANT_EVALUATE: badge("stale", "Needs attention")}[r.decision_state]
            change_to = (f'{esc(r.proposed_line)} {esc(r.proposed_colors)}'.strip()
                         if r.decision_state == CTP.CHANGE else '<span class="muted">—</span>')
            build = f'{esc(r.current_line)}' + (f' — {esc(r.current_colors)}' if r.current_colors else "")
            trows.append([esc(r.order_number or r.vin), safe(build), safe(says), safe(change_to),
                          esc(r.reason_plain)])
        parts.append('<div class="card"><h2>All orders</h2>'
                     + table(["Order", "Current Build", "Elite Says", "Change To", "Why"], trows) + '</div>')

        # SECTION G — quiet session status
        parts.append(f'<p class="muted" style="font-size:12px">CTP session: {len(files)} file(s) • '
                     f'{summ["orders"]} OEM orders • Pipeline updated {esc(pipe_age or "— not loaded —")}</p>')
        return _resp(app, s, "CTP", "".join(parts), "/ctp")

    @app.post("/ctp/upload")
    def ctp_upload(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...workflow import ctp_intake as CTP
        from ...ids import new_id
        upload = req.files.get("file")
        if not upload or not upload[1]:
            s.flash = "Choose a CTP file to add first; nothing was loaded."
            return Response.redirect("/ctp")
        filename, data = upload
        rows = CTP.parse_ctp_file(filename, data)
        candidates = [c for c in (CTP.to_candidate(r, source_file=filename) for r in rows) if c is not None]
        if not candidates:
            s.flash = (f"Elite couldn't find any orders in {filename}. If this is the OEM CTP export, it may be in "
                       f"a format Elite doesn't recognize yet — tell the team.")
            return Response.redirect("/ctp")
        from collections import Counter
        model = (Counter((c.model or "").upper() for c in candidates if c.model).most_common(1) or [("", 0)])[0][0]
        sess = _ws_get(app, s.scope, "ctp_session", {}) or {}
        files = sess.get("files", [])
        files.append({"id": new_id("ctpf"), "name": filename, "model": model,
                      "candidates": [vars(c) for c in candidates]})
        sess["files"] = files
        _ws_put(app, s.scope, "ctp_session", sess)
        s.flash = f"Loaded {len(candidates)} order(s) from {filename}."
        return Response.redirect("/ctp")

    @app.post("/ctp/remove")
    def ctp_remove(app, req):
        s = req.session
        app.require(s, "workspace.view")
        sess = _ws_get(app, s.scope, "ctp_session", {}) or {}
        files = sess.get("files", [])
        try:
            idx = int(req.form.get("idx"))
            if 0 <= idx < len(files):
                removed = files.pop(idx)
                sess["files"] = files
                _ws_put(app, s.scope, "ctp_session", sess)
                s.flash = f"Removed {removed.get('name', 'file')}."
        except (TypeError, ValueError):
            pass
        return Response.redirect("/ctp")

    @app.post("/ctp/clear")
    def ctp_clear(app, req):
        s = req.session
        app.require(s, "workspace.view")
        _ws_put(app, s.scope, "ctp_session", {})
        _ws_put(app, s.scope, "ctp_infeasible", {})
        _ws_put(app, s.scope, "ctp_confirmed", {})
        _ws_put(app, s.scope, "ctp_session_rules", {})
        s.flash = "CTP session cleared."
        return Response.redirect("/ctp")

    @app.post("/ctp/not-available")
    def ctp_not_available(app, req):
        """Operator feedback loop for an OEM rejection. TWO independent kinds are learned this session:
          * 'Trim swap not available' teaches a broader LEARNED production rule (same_trim_only = true) — a
            session/model constraint that removes only cross-trim targets from every remaining order (within-trim
            optimization is untouched). Provenance records which rejection taught it.
          * any other reason records an EXACT-configuration exclusion (governed model + model code + exterior +
            interior) that is removed from every remaining order of that model this session.
        Kept separate; either way the board is untouched (nothing executed) and CTP re-runs for all orders."""
        s = req.session
        app.require(s, "workspace.view")
        from ...clock import to_utc_iso
        okey = (req.form.get("order") or "").strip()
        target = (req.form.get("target") or "").strip()
        if not okey or not target:
            s.flash = "Couldn't record that — the order or target was missing."
            return Response.redirect("/ctp")
        reason = (req.form.get("reason") or "other_oem_rejection").strip()
        note = (req.form.get("note") or "").strip()
        target_canonical = (req.form.get("target_canonical") or "").strip()

        # (2) SESSION-LEARNED RULE: a trim-swap rejection teaches same-trim-only for this session/model.
        if reason == "trim_swap_unavailable":
            rules = _ws_get(app, s.scope, "ctp_session_rules", {}) or {}
            rules["same_trim_only"] = {"active": True, "taught_by": okey, "reason": reason, "note": note,
                                       "target_canonical": target_canonical,
                                       "at": to_utc_iso(app.stack.clock.now()),
                                       "actor": getattr(s, "principal_id", "") or ""}
            _ws_put(app, s.scope, "ctp_session_rules", rules)
            s.flash = ("Learned OEM rule for this session: same-trim changes only (cross-trim swaps removed). "
                       f"Taught by {okey}. Re-evaluating all remaining orders.")
            return Response.redirect("/ctp")

        # (1) EXACT-CONFIGURATION EXCLUSION: this governed build is unavailable for the whole session/model.
        infeasible = _ws_get(app, s.scope, "ctp_infeasible", {}) or {}
        marks = list(infeasible.get(okey, []) or [])
        if any(m.get("target") == target for m in marks):
            s.flash = "That configuration is already marked not available for this order."
            return Response.redirect("/ctp")
        marks.append({"target": target, "target_canonical": target_canonical, "reason": reason,
                      "note": note, "at": to_utc_iso(app.stack.clock.now()),
                      "actor": getattr(s, "principal_id", "") or ""})
        infeasible[okey] = marks
        _ws_put(app, s.scope, "ctp_infeasible", infeasible)
        s.flash = (f"Recorded — {target_canonical or target} marked not available for this model's CTP session "
                   f"(first rejected on {okey}). Re-evaluating all remaining orders.")
        return Response.redirect("/ctp")

    @app.post("/ctp/available-reset")
    def ctp_available_reset(app, req):
        """Operator correction: clear the session-level 'not available' exclusions recorded under this order (and
        any session rule this order taught), then recompute. Those configurations become eligible again for every
        order (unless another order independently marked the same configuration)."""
        s = req.session
        app.require(s, "workspace.view")
        okey = (req.form.get("order") or "").strip()
        infeasible = _ws_get(app, s.scope, "ctp_infeasible", {}) or {}
        changed = False
        if okey in infeasible:
            infeasible.pop(okey, None)
            _ws_put(app, s.scope, "ctp_infeasible", infeasible)
            changed = True
        rules = _ws_get(app, s.scope, "ctp_session_rules", {}) or {}
        if any((v or {}).get("taught_by") == okey for v in rules.values()):
            rules = {k: v for k, v in rules.items() if (v or {}).get("taught_by") != okey}
            _ws_put(app, s.scope, "ctp_session_rules", rules)
            changed = True
        if changed:
            s.flash = "Cleared those session exclusions/rules. Re-evaluating all remaining orders."
        return Response.redirect("/ctp")

    @app.post("/ctp/session-rule-clear")
    def ctp_session_rule_clear(app, req):
        """Clear one active learned OEM production rule (e.g. same_trim_only) for this session and recompute."""
        s = req.session
        app.require(s, "workspace.view")
        rule = (req.form.get("rule") or "").strip()
        rules = _ws_get(app, s.scope, "ctp_session_rules", {}) or {}
        if rule in rules:
            rules.pop(rule, None)
            _ws_put(app, s.scope, "ctp_session_rules", rules)
            s.flash = "Cleared the learned OEM rule for this session. Re-evaluating all remaining orders."
        return Response.redirect("/ctp")

    @app.post("/ctp/confirm-change")
    def ctp_confirm_change(app, req):
        """Record that the operator actually executed the recommended CHANGE in the OEM portal
        (RECOMMENDED → CONFIRMED CHANGED). Audit/state only; the confirmation UI can be refined later."""
        s = req.session
        app.require(s, "workspace.view")
        from ...clock import to_utc_iso
        okey = (req.form.get("order") or "").strip()
        target = (req.form.get("target") or "").strip()
        if not okey:
            s.flash = "Couldn't confirm — the order was missing."
            return Response.redirect("/ctp")
        confirmed = _ws_get(app, s.scope, "ctp_confirmed", {}) or {}
        confirmed[okey] = {"target": target, "at": to_utc_iso(app.stack.clock.now()),
                           "actor": getattr(s, "principal_id", "") or ""}
        _ws_put(app, s.scope, "ctp_confirmed", confirmed)
        s.flash = f"Marked {okey} as confirmed changed."
        return Response.redirect("/ctp")

    @app.post("/ctp/confirm-undo")
    def ctp_confirm_undo(app, req):
        """Correction path for a mistakenly confirmed execution: unlock the order so it re-optimizes normally.
        Its working-state consumption is released on the next evaluation; the certified board was never touched."""
        s = req.session
        app.require(s, "workspace.view")
        okey = (req.form.get("order") or "").strip()
        confirmed = _ws_get(app, s.scope, "ctp_confirmed", {}) or {}
        if okey in confirmed:
            confirmed.pop(okey, None)
            _ws_put(app, s.scope, "ctp_confirmed", confirmed)
            s.flash = f"Undid the confirmed change for {okey}; it will re-evaluate normally."
        return Response.redirect("/ctp")

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
                 + _board_recompute_card(app, s)
                + '<div class="card"><h2>Benched combinations</h2><p class="muted">A benched combination is no longer '
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

    @app.post("/data/recompute-board")
    def data_recompute_board(app, req):
        s = req.session
        app.require(s, "workspace.view")
        from ...newinv.board_recompute import recompute_board
        try:
            rb = recompute_board(app, s.scope, actor=s.principal_id)
            s.flash = rb.get("reason") or ("Recomputed." if rb.get("ok") else "Not recomputed.")
        except Exception as e:   # noqa: BLE001
            s.flash = f"Recompute failed; the last certified board was left unchanged: {e}"
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


def _cpo_human_why(b, month, ln):
    """A concise managerial narrative generated ONLY from certified/available state — not a receipt. It says
    what the position is, why the order quantity is what it is, names the approved Service-Loaner requirement
    when present, and always carries a watch/counter-evidence condition. Raw figures live in Proof."""
    ml = _month_label(month)
    order = b["order"]
    cur, fut = b.get("current"), b.get("future")
    sent = []
    if b.get("m_present"):
        short = b.get("m_shortage")
        dem = b.get("m_demand")
        empty_now = (cur == 0 or cur is None)
        arriving = (fut is not None and cur is not None and fut > cur)
        lead = ("You're empty now" if empty_now else f"You have {cur} on the lot now")
        arr = (f" and {fut} in position by {ml}" if arriving else
               (f" with no additional {ml} arrival" if not arriving else ""))
        gap = (f"the {ml} plan runs {_num(short)} short against {_num(dem)} expected demand"
               if (short or 0) > 0 else f"the {ml} position covers expected demand")
        sent.append(f"{lead}{arr}; {gap}.")
    else:
        sent.append(f"This is a certified acquire-now decision; {ml} is outside this combination's certified "
                    "planning horizon.")
    base = (f"Retail demand supports ordering {order}" if order else "Retail evidence does not yet support an order")
    if ln is not None and getattr(ln, "sl_planned", 0):
        sent.append(f"{base}, and an approved Service-Loaner requirement adds {ln.sl_planned} more "
                    f"{ln.model} to the dealership's need — a separate obligation, not Retail demand.")
    else:
        sent.append(f"{base} now.")
    # watch / counter-evidence — never fabricated; drawn from confidence or the restraint boundary
    conf = (b.get("m_confidence") or "").strip() if b.get("m_present") else ""
    if conf and conf.lower() not in ("high", "strong"):
        sent.append(f"Watch: {ml} confidence is {conf} — treat the projection as directional.")
    elif order:
        sent.append("A larger order would outrun current certified evidence.")
    return " ".join(sent)


def _cpo_rec_pieces(s, b, rank, st, month, promoted, ln=None):
    """Compute the shared parts of a CPO recommendation ONCE. Quantity-aware: the ORDER call names the number
    of VEHICLES so a >1 order cannot be missed, and a partial confirm shows 'k OF n ordered' with the remainder
    still open. `st` is the _cpo_status dict."""
    order = st["order"]
    ident = safe(f'<span id="combo-{esc(b["combo"])}"></span>'
                 f'<a href="/combination/{esc(b["pid"])}?month={esc(month)}">{esc(b["identity"])}</a>'
                 + (' ' + badge("completed", "promoted") if promoted else ''))
    call = f'ORDER {order} {"VEHICLES" if order != 1 else "VEHICLE"}'
    pos = safe(f'Current <strong>{esc(b["current"])}</strong> · By {esc(month)} <strong>{esc(b["future"])}</strong>')
    if b.get("m_present"):
        proof = kv([(f"Projected shortage — {month}", _num(b.get("m_shortage"))),
                    (f"Expected demand — {month}", _num(b.get("m_demand"))),
                    (f"Supply position by {month}", b.get("m_cum_supply")),
                    (f"Confidence — {month}", b.get("m_confidence") or "—"),
                    ("Order now (certified action)", order)])
    else:
        proof = kv([("Basis", "certified acquire-now decision for this combination"),
                    (f"Planning month {month}", "outside the certified planning horizon for this combination"),
                    ("Order now (certified action)", order)])
    why_body = safe(f'<p style="margin:2px 0 6px">{esc(_cpo_human_why(b, month, ln))}</p>'
                    + disclosure("Proof — certified figures", proof))
    common = dict(ident=ident, call=call, pos=pos, why_body=why_body, rank=rank)
    status = st["status"]
    if status == "confirmed":
        return dict(resolved=True, chip=chip("done", f"Ordered {order} of {order}"),
                    actions=action_group(_line_btn(s, b, "clear", "Undo", "secondary")), **common)
    if status == "not_ordered":
        return dict(resolved=True, chip=chip("skip", "Not ordering"),
                    actions=action_group(_line_btn(s, b, "clear", "Undo", "secondary")), **common)
    if status == "not_orderable":
        return dict(resolved=True, chip=chip("attention", "Not orderable · see replacement"),
                    actions=action_group(_line_btn(s, b, "clear", "Undo", "secondary")), **common)
    if status == "partial":
        acts = (_line_btn(s, b, "confirmed", f"Confirm remaining {st['remaining']}")
                + _partial_form(s, b, order, st["ordered"]) + _line_btn(s, b, "clear", "Undo", "secondary"))
        return dict(resolved=False, chip=chip("attention", f"{st['ordered']} OF {order} ORDERED · {st['remaining']} left"),
                    actions=action_group(acts), **common)
    confirm_text = f"Confirm {order} ordered" if order != 1 else "Confirm ordered"
    acts = _line_btn(s, b, "confirmed", confirm_text)
    if order > 1:
        acts += _partial_form(s, b, order)                 # only some secured -> remainder stays unresolved
    acts += (_line_btn(s, b, "not_ordered", "Not ordering", "secondary")
             + _line_btn(s, b, "not_orderable", "Not orderable", "secondary")
             + _bench_button(s, b["identity"], f"/ordering/cpo?month={month}"))
    return dict(resolved=False, chip=chip("need", f"Needs decision · order {order}"), actions=action_group(acts), **common)


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


def _cpo_rec_row(s, b, rank, st, month, *, promoted=False, horizon_html="", ln=None):
    """The ONE CPO recommendation row used at every rank. Compact but information-complete: the ORDER call,
    the position, the certified horizon sparkline shown INLINE (never buried), a human Why, and the full
    action set. Rank determines order only — it never determines how much of this is visible, so #4..#N carry
    exactly the same information as #1 and are not subconsciously overlooked."""
    p = _cpo_rec_pieces(s, b, rank, st, month, promoted, ln)
    pos = safe(p["pos"] + horizon_html) if horizon_html else p["pos"]
    why = disclosure(f"Why #{rank}", p["why_body"])
    return rec_row(rank, p["ident"], p["call"], pos, why, p["actions"],
                   resolved=p["resolved"], chip_html=p["chip"])


def _cpo_status(lines, qty, b):
    """The per-combination workflow status, quantity-aware. order = the certified ORDER-N. A partial confirm
    (0 < ordered < order) is NOT 'worked' — the remaining quantity returns to the active queue so an ORDER-2
    can never be silently completed as one."""
    combo = b["combo"]
    order = _int_or0(b.get("order"))
    st = lines.get(combo)
    if st == "not_orderable":
        return {"status": "not_orderable", "ordered": 0, "order": order, "remaining": 0}
    if st == "not_ordered":
        return {"status": "not_ordered", "ordered": 0, "order": order, "remaining": 0}
    if st == "confirmed":
        return {"status": "confirmed", "ordered": order, "order": order, "remaining": 0}
    k = _int_or0(qty.get(combo))
    if 0 < k < order:
        return {"status": "partial", "ordered": k, "order": order, "remaining": order - k}
    if k >= order and order > 0:
        return {"status": "confirmed", "ordered": order, "order": order, "remaining": 0}
    return {"status": "open", "ordered": 0, "order": order, "remaining": order}


def _cpo_worked(status):
    return status in ("confirmed", "not_ordered", "not_orderable")


def _line_btn(s, b, state, text, cls="primary", *, qty=None):
    return (f'<form class="mut" method="post" action="/ordering/cpo/line">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=month value="{esc(b.get("month", ""))}">'
            f'<input type=hidden name=combo value="{esc(b["combo"])}">'
            f'<input type=hidden name=order value="{esc(b.get("order", ""))}">'
            f'<input type=hidden name=state value="{esc(state)}">'
            + (f'<input type=hidden name=qty value="{esc(qty)}">' if qty is not None else '')
            + f'<button type=submit class="{esc(cls)}" style="padding:3px 9px">{esc(text)}</button></form>')


def _partial_form(s, b, order, ordered=0):
    """Record that only SOME of an ORDER-N were secured — the remainder returns to unresolved work."""
    return (f'<form class="mut" method="post" action="/ordering/cpo/line" '
            'style="display:inline-flex;gap:4px;align-items:center">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=month value="{esc(b.get("month", ""))}">'
            f'<input type=hidden name=combo value="{esc(b["combo"])}">'
            f'<input type=hidden name=order value="{esc(order)}">'
            f'<input type=hidden name=state value="partial">'
            f'<input name=qty type=number min=1 max="{esc(order)}" value="{esc(ordered or 1)}" '
            'style="width:64px;padding:2px 4px" aria-label="how many ordered">'
            f'<button type=submit class=secondary style="padding:3px 9px">of {esc(order)} ordered</button></form>')


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
        canonical = ident.get(r["combination_id"], r["combination_id"])
        readable = _readable(canonical)                     # COMPACT code form — machine-parseable (trade scorer)
        readable_h = _readable_h(app, scope, canonical)     # HUMAN vehicle language for display (item 2)
        model = _model_of(readable)
        acq = int(dec.get("acquire_units", 0) or 0)
        exc = int(dec.get("arrived_excess", 0) or 0)
        if acq > 0:
            short.append({"identity": readable, "identity_h": readable_h, "model": model, "qty": acq})
        if exc > 0:
            over.append({"identity": readable, "identity_h": readable_h, "model": model, "qty": exc})
    short.sort(key=lambda d: (-d["qty"], d["identity"]))
    over.sort(key=lambda d: (-d["qty"], d["identity"]))
    return short, over


def _ppo_action_form(s, window, o, v):
    """Operator execution control for one offer. Defaults to Elite's recommendation; anything else is an
    override the render layer flags. The machine recommendation is never overwritten (it is recomputed live)."""
    rec_qty = v.recommended_qty if v.recommendation == "FIRM" else 0
    return (f'<form class="mut" method="post" action="/ordering/ppo/record">'
            f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
            f'<input type=hidden name=window value="{esc(window)}">'
            f'<input type=hidden name=offer value="{esc(str(o.get("id","")))}">'
            f'<select name=action>'
            f'<option value=FIRM{" selected" if v.recommendation=="FIRM" else ""}>Firm</option>'
            f'<option value=PARTIAL>Partial</option>'
            f'<option value=DENY{" selected" if v.recommendation!="FIRM" else ""}>Deny</option>'
            f'</select> '
            f'<input name=action_qty type=number min=0 value="{esc(rec_qty)}" style="max-width:70px"> '
            f'<button type=submit style="padding:3px 9px">Record</button></form>')


def _certified_positions(app, scope):
    """Shared certified board for the incremental supply-opportunity evaluator (PPO / Supplemental / Dealer
    Trade all consume this one reader — item 6/17). Returns (certs, label_to_key). Each cert carries the
    whole-vehicle certified decision for one combination: acquire_units (actionable now-need), arrived_excess /
    incoming_excess (covered), and future_gap (post-horizon monitor gaps — a shortage that is NOT yet
    actionable). Read-only; no recompute of certified math."""
    conn = _conn(app)
    rows = conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                        (scope,)).fetchall()
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    certs, label_to_key = [], {}
    for r in rows:
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        cid = r["combination_id"]
        canonical = ident.get(cid, cid)
        human = _readable_h(app, scope, canonical)
        certs.append({"key": cid, "label": human,
                      "acquire_units": int(dec.get("acquire_units", 0) or 0),
                      "arrived_excess": int(dec.get("arrived_excess", 0) or 0),
                      "incoming_excess": int(dec.get("incoming_excess", 0) or 0),
                      # supply-only: real supply, no accepted demand basis -> Need/Excess NOT asserted (0 above)
                      "supply_only": bool(dec.get("supply_only")) or r["planning_state"] == "supply_only",
                      "future_gap": len(dec.get("monitor_months") or [])})
        label_to_key[human] = cid
        label_to_key[_readable(canonical)] = cid       # older offers stored the compact code label
    return certs, label_to_key


def _ctp_norm_key(v):
    """Order#/VIN dedup key — matches the CTP intake normalization (uppercase, strip, alnum+-_/ only)."""
    o = str(v or "").strip().lstrip("'").upper()
    return "".join(ch for ch in o if ch.isalnum() or ch in "-_/")


def _board_recompute_card(app, s):
    """Data-page card: certified planning-board vintage vs the loaded Pipeline, plus a recompute action. A
    recovery/admin control — it recomputes inventory_plan_result from the currently loaded certified sources
    (no re-upload) using the existing planning engine."""
    from ...newinv.board_recompute import board_status
    try:
        st = board_status(app, s.scope)
    except Exception:   # noqa: BLE001
        st = {"state": "unknown", "detail": "Board status unavailable.", "board_computed_at": None}
    tone = {"current": "healthy", "stale": "attention", "absent": "attention", "unknown": "attention"}.get(
        st["state"], "attention")
    word = {"current": "current", "stale": "stale — recompute", "absent": "not computed",
            "unknown": "unknown vintage"}.get(st["state"], st["state"])
    when = st.get("board_computed_at")
    meta = (f'<div class="muted" style="font-size:12px">Board computed {esc((when or "")[:16].replace("T", " "))}'
            f'; latest Pipeline snapshot {esc((st.get("snapshot_time") or "")[:16].replace("T", " ") or "—")}.</div>'
            if when else "")
    btn = (f'<form class="mut" method="post" action="/data/recompute-board">'
           f'<input type=hidden name=_csrf value="{esc(s.csrf_token)}">'
           f'<button type=submit>Recompute current board</button></form>')
    return ('<div class="card"><h2>Certified planning board</h2>'
            f'<p>{badge(tone, word)} {esc(st.get("detail", ""))}</p>' + meta
            + '<p class="muted" style="font-size:12px">Recomputes the certified board (Need / Excess per '
            'combination) from the currently loaded Inventory / Pipeline — no re-upload needed. CTP reads this '
            'board; it does not recompute it.</p>' + btn + '</div>')


def _ctp_pipeline_rows(app, scope):
    """Current Pipeline as CTP-reconcilable rows: one dict per incoming production order, with order_number,
    vin, combination_id, canonical, model, arrival_month. Read-only; no fabrication; no rows created FROM CTP.

    Reads the SAME authoritative incoming-order sources the rest of the app treats as the Pipeline, in order:
      1. the certified future-supply projection (`future_supply_projection` + `production_order`) — carries the
         combination_id / canonical board position, so a matched order is fully evaluable; then
      2. the authoritative Production Orders snapshot (`production_orders` source: manufacturer_order_id / vin /
         model / eta_month) for any order that is loaded but not yet projected onto the certified board.
    Without (2), an order the operator has loaded but Elite has not yet projected would read as 'not in the
    Pipeline' even though it is — the live disconnect. Matching stays EXACT (Order# or VIN); a snapshot-only
    match resolves reconciliation but has no board position, so the evaluator gates it honestly rather than
    fabricating one."""
    conn = _conn(app)
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    out, seen_orders, seen_vins = [], set(), set()

    def _emit(order_number, vin, cid, canonical, model, arrival_month):
        out.append({"order_number": order_number, "vin": vin, "combination_id": cid, "canonical": canonical,
                    "model": model, "arrival_month": arrival_month})
        if order_number:
            seen_orders.add(_ctp_norm_key(order_number))
        if vin:
            seen_vins.add(_ctp_norm_key(vin))

    # 1) certified future-supply projection (has the board combination)
    try:
        rows = conn.execute(
            "SELECT f.combination_id AS cid, f.arrival_month AS am, o.manufacturer_order_id AS onum, o.vin AS vin "
            "FROM future_supply_projection f JOIN production_order o ON f.production_order_id=o.id "
            "WHERE f.store_scope=? AND f.status='current'", (scope,)).fetchall()
    except Exception:   # noqa: BLE001
        rows = []
    for r in rows:
        canonical = ident.get(r["cid"], r["cid"])
        _emit((r["onum"] or ""), (r["vin"] or ""), r["cid"], canonical, _model_of(_readable(canonical)),
              (r["am"] or ""))

    # 2) authoritative Production Orders snapshot — loaded orders not (yet) projected onto the certified board
    for pr in _read_production_orders(app, scope):
        onum = str(pr.get("manufacturer_order_id") or "").strip()
        vin = str(pr.get("vin") or "").strip()
        if not onum and not vin:
            continue
        if (onum and _ctp_norm_key(onum) in seen_orders) or (vin and _ctp_norm_key(vin) in seen_vins):
            continue                                    # already covered by the certified projection
        _emit(onum, vin, None, None, str(pr.get("model") or "").strip(),
              str(pr.get("eta_month") or pr.get("eta") or "").strip())

    # 3) the LIVE DMS inventory / pipeline export the operator actually loads (new_inventory_pipeline_summary /
    #    new_inventory_current). There is no separate Production Orders import path, and the DMS pipeline carries
    #    on-order (ONS/SIT/NNA-INV) units whose factory ORDER number is the DMS `serial` (no VIN assigned yet).
    #    Elite matches the OEM CTP Order# against that serial (EXACT), resolving each to its certified board
    #    combination by the year-agnostic planning identity so a matched order is evaluable.
    for pr in _ctp_inventory_pipeline_rows(app, scope, ident):
        onum, vin = pr["order_number"], pr["vin"]
        if not onum and not vin:
            continue
        if (onum and _ctp_norm_key(onum) in seen_orders) or (vin and _ctp_norm_key(vin) in seen_vins):
            continue
        _emit(onum, vin, pr["combination_id"], pr["canonical"], pr["model"], pr["arrival_month"])
    return out


def _ctp_inventory_pipeline_rows(app, scope, ident_by_cid=None):
    """Incoming (on-order) units from the live DMS inventory / pipeline export, as CTP-reconcilable rows. The
    operator loads this source today (Data shows it current); Elite treats the on-order unit's DMS `serial` as
    its factory ORDER number and resolves each unit to its certified board combination by the year-agnostic
    planning identity (model_code / ext / int), so a matched order can be evaluated. Exact match only; nothing
    is fabricated. Only INCOMING stages (ONS / SIT / NNA-INV) contribute an order number — an in-stock unit's
    serial is never treated as an order."""
    try:
        from ...loaner.placement import read_new_retail_units, _authoritative_vin
        from ...newinv.dms_cohort import dms_source_stage, INCOMING_STAGES
        from ...newinv.dms_identity import dms_planning_identity
    except Exception:   # noqa: BLE001
        return []
    try:
        inv = read_new_retail_units(app, scope)
    except Exception:   # noqa: BLE001
        inv = []
    if not inv:
        return []
    conn = _conn(app)
    if ident_by_cid is None:
        ident_by_cid = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
            "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    cid_by_ident = {}
    for cid, canonical in ident_by_cid.items():
        cid_by_ident.setdefault(canonical, cid)
    # normalized (alnum only, lowercased) header names that denote an OEM/factory order number
    _ORDER_HEADERS = {"order", "orderno", "ordernumber", "manufacturerorderid", "factoryorder",
                      "vehicleorder", "oemorder", "oemorderno"}
    out = []
    for r in inv:
        try:
            stage = dms_source_stage(r)
        except Exception:   # noqa: BLE001
            stage = ""
        vin, ok, serial = _authoritative_vin(r)
        vin = vin if ok else ""
        # order number: an EXPLICIT order-like column if the export carries one, else the on-order serial
        order_number = ""
        for k, v in r.items():
            if _ctp_norm_key(k).lower() in _ORDER_HEADERS and v not in (None, ""):
                order_number = str(v).strip()
                break
        if not order_number and stage in INCOMING_STAGES and serial:
            order_number = str(serial).strip()
        if not order_number and not vin:
            continue
        try:
            canonical = dms_planning_identity(r)
        except Exception:   # noqa: BLE001
            canonical = None
        cid = cid_by_ident.get(canonical)
        model = str(r.get("model") or "").strip() or (_model_of(_readable(canonical)) if canonical else "")
        arrival = str(r.get("eta") or r.get("production_month") or "").strip()
        out.append({"order_number": order_number, "vin": vin, "combination_id": cid,
                    "canonical": (canonical if cid else None), "model": model, "arrival_month": arrival})
    return out


def _ctp_board(app, scope, descriptions=None):
    """Certified board keyed by combination_id → {canonical, line, colors, model, excess, short} for the CTP
    evaluator. Reuses the same issued certified decision every other engine reads (no recompute): `excess` =
    arrived + incoming over-supply, `short` = acquire-now need. line/colors are the clean human build so the
    CHANGE target reads in business language (exterior/interior names)."""
    from .domains import _describe
    from ...identity.translation import TranslationStore
    certs, _lk = _certified_positions(app, scope)
    conn = _conn(app)
    xlat = TranslationStore(app.prefs, scope)
    canon = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    board = {}
    for c in certs:
        cid = c["key"]
        canonical = canon.get(cid, cid)
        d = _describe(app, scope, canonical, descriptions=descriptions)
        line = d.vehicle if d else _model_of(_readable(canonical))
        # surface the authoritative reviewed ORDER code (e.g. 84217), so a CHANGE target is orderable with its
        # exact model code — the canonical identity carries only the 4-digit planning code (e.g. 8421).
        order_code = ""
        if d and getattr(d, "model_code", ""):
            order_code = xlat.order_code_for_code(d.model_code) or ""
            if order_code and order_code not in line:
                line = f"{order_code} {line}"
        # A CTP CHANGE must be a COMPLETE, actionable configuration: BOTH color dimensions shown with their codes
        # (never drop a dimension whose human name is unmapped — that produced the "— Graphite" one-colour target).
        # color_complete is False when either exterior or interior CODE is missing (identity, not just name):
        # such a target is gated in evaluate() rather than presented as an incomplete change.
        colors = d.colours(with_code=True, drop_unmapped=False) if d else ""
        ext_code = (getattr(d, "exterior_code", "") or "").strip() if d else ""
        int_code = (getattr(d, "interior_code", "") or "").strip() if d else ""
        ext_name = (getattr(d, "exterior_name", "") or "").strip() if d else ""
        int_name = (getattr(d, "interior_name", "") or "").strip() if d else ""
        drivetrain = (getattr(d, "drivetrain", "") or "").strip() if d else ""
        # GOVERNED TARGET CONTRACT: a CTP CHANGE target is EXECUTABLE only when its full production identity is
        # governed well enough to tell the operator exactly what to enter in Infiniti CTP — an orderable order
        # code, a recognized model family, and governed exterior AND interior (code + human name), with no
        # unresolved/`(unmapped)` component. This is computed from real translation governance; NO mapping is
        # fabricated (an ungoverned code/colour simply stays executable=False). The CTP evaluator excludes
        # non-executable positions from the candidate universe BEFORE final ranking, then reranks the remainder.
        executable = bool(d and order_code and getattr(d, "has_family", False)
                          and ext_code and ext_name and int_code and int_name
                          and not getattr(d, "unresolved", ()))
        board[cid] = {"canonical": canonical, "line": line, "colors": colors,
                      "model": _model_of(_readable(canonical)),
                      # AUTHORITATIVE governed trim from the model-code family / translation (clean 'AUTOGRAPH',
                      # drivetrain kept separate). '' when unresolved — the same-trim rule then gates, never
                      # guessing a trim from the free-text line ('QX60 AUTOGRAPH AWD SUV AUTO' -> not 'AUTO').
                      "trim": (getattr(d, "trim", "") or "").strip() if d else "",
                      # GOVERNED GENERATION / planning segment = first two digits of the governed order code
                      # (fallback: the planning model code). '86' current-gen QX80, '83' prior-gen. The CTP
                      # evaluator forbids a CHANGE from crossing generations without explicit supply-substitution
                      # authority (supply is generation-specific).
                      "generation": "".join(ch for ch in (order_code or (getattr(d, "model_code", "") if d else ""))
                                            if ch.isdigit())[:2],
                      "drivetrain": drivetrain, "order_code": order_code,
                      "exterior_code": ext_code, "interior_code": int_code,
                      "exterior_name": ext_name, "interior_name": int_name,
                      # executable == fully-governed, orderable identity (see GOVERNED TARGET CONTRACT above).
                      "executable": executable,
                      "color_complete": bool(ext_code and int_code),
                      # supply-only: the position is authoritative but asserts no Need/Excess (0/0); the flag lets
                      # the CTP evaluator use honest no-demand-basis language instead of "at/below needed supply".
                      "supply_only": bool(c.get("supply_only")),
                      "excess": int(c["arrived_excess"]) + int(c["incoming_excess"]), "short": int(c["acquire_units"])}
    return board


def _ctp_pipeline_age(app, scope):
    """Human 'Pipeline updated' timestamp — newest certified future-supply projection, else the authoritative
    Production Orders snapshot load time (so a loaded-but-not-yet-projected Pipeline is not reported as 'not
    loaded'). '' only when neither source has any incoming orders for this store."""
    try:
        r = _conn(app).execute("SELECT MAX(calculation_timestamp) AS t FROM future_supply_projection "
                               "WHERE store_scope=?", (scope,)).fetchone()
        if r and r["t"]:
            return (r["t"] or "")[:16].replace("T", " ")
    except Exception:   # noqa: BLE001
        pass
    # fall back to the newest load time of any authoritative incoming-order source the operator can load:
    # the Production Orders snapshot, or the live DMS inventory / pipeline export (which carries on-order units).
    try:
        from ...newinv.snapshots import SnapshotReader
        ops = _ops_stack(app)
        ops_store = getattr(ops, "ops", None) if ops else None
        if ops_store is not None:
            reader = SnapshotReader(ops_store, ops.data)
            best = ""
            for key in ("production_orders", "new_inventory_pipeline_summary", "new_inventory_current"):
                try:
                    snap = reader.latest_snapshot(ops.source_id(key), scope)
                except Exception:   # noqa: BLE001
                    snap = None
                if snap is not None:
                    t = getattr(snap, "observed_time", None) or getattr(snap, "received_at", None) or ""
                    if t and t > best:
                        best = t
            if best:
                return best[:16].replace("T", " ")
    except Exception:   # noqa: BLE001
        pass
    return ""


def _dms_dis(r):
    """Days-in-stock (inventory age) from a DMS row, or None. Never fabricated."""
    for k in ("dis", "days_in_stock", "DIS"):
        v = r.get(k) if isinstance(r, dict) else None
        if str(v or "").strip():
            try:
                return int(float(v))
            except (TypeError, ValueError):
                pass
    return None


def _demo_op_id(vin, serial, stock):
    """The operational unit identity for a physical unit: a real 17-char VIN, else serial, else stock. This is
    the count-once key AND the source of the masked 'Unit ######' tag — never a fabricated VIN."""
    for v in ((vin or "").strip().upper(), (serial or "").strip().upper(), (stock or "").strip().upper()):
        if v:
            return v
    return ""


def _demo_live_units(app, scope, plan_key):
    """(on_ground, incoming) LIVE physical units for a combination's planning key, straight from the DMS
    inventory snapshot the rest of Elite reads — because the certified board is recomputed from that snapshot and
    does NOT populate current_supply_projection rows. on_ground = DLR-INV (available now, youngest DIS first for
    Demo); incoming = ONS/SIT/NNA-INV. Each: {op_id, vin, stock, serial, dis, arrival_month}. Never fabricates."""
    try:
        from ...loaner.placement import read_new_retail_units, _authoritative_vin
        from ...newinv.dms_cohort import dms_source_stage
        from ...newinv.dms_identity import dms_planning_key
    except Exception:   # noqa: BLE001
        return [], []
    on_ground, incoming = [], []
    for r in (read_new_retail_units(app, scope) or []):
        try:
            if dms_planning_key(r) != plan_key:
                continue
            stage = dms_source_stage(r)
        except Exception:   # noqa: BLE001
            continue
        vin, ok, serial = _authoritative_vin(r)
        stock = str(r.get("stock_number") or r.get("stock") or "").strip()
        op_id = _demo_op_id(vin if ok else "", serial, stock)
        if not op_id:
            continue
        unit = {"op_id": op_id, "vin": (vin if ok else ""), "stock": stock, "serial": serial,
                "dis": _dms_dis(r), "arrival_month": str(r.get("production_month") or r.get("pm") or "").strip()}
        if stage == "DLR-INV":
            on_ground.append(unit)
        elif stage in ("ONS", "SIT", "NNA-INV"):
            incoming.append(unit)
    on_ground.sort(key=lambda u: (u["dis"] if u["dis"] is not None else 10 ** 9))   # youngest first for Demo
    return on_ground, incoming


def _demo_pools(app, scope, cid):
    """Physical Demo candidate pools for a combination (CORE LAW: physical, count-once). Returns
    (current, incoming, order_available). Reads the LIVE DMS inventory snapshot (the real source of on-ground /
    incoming physical units) AND any Phase-4 current/future supply projections, unioned + deduped by operational
    identity, committed units excluded. order_available is True when no eligible physical unit exists (so an
    ORDER / REVIEW fallback can always be produced)."""
    from ...newinv.store import NewInvStore
    from ...ordering.cross_domain import committed_vins
    from ...operatorstd import supply as _S
    conn = _conn(app)
    st = NewInvStore(conn, app.stack.clock)
    committed = set(committed_vins(conn, scope, app.prefs).keys())
    canonical = (conn.execute("SELECT canonical_identity FROM sellable_combination WHERE id=? AND store_scope=?",
                              (cid, scope)).fetchone() or {})
    canonical = canonical["canonical_identity"] if canonical else None
    plan_key = _plan_key_of(canonical) if canonical else None

    current, incoming, seen = [], [], set()

    def _add(bucket, op_id, *, age=None, arrival=None, stock=None):
        if not op_id or op_id in committed or op_id in seen:
            return
        seen.add(op_id)
        avail = (_S.classify_availability(_S.CURRENT_INVENTORY, production_month=arrival)
                 if arrival else (_S.ON_GROUND if bucket is current else _S.NEAR_IMMEDIATE))
        bucket.append(_S.NormalizedSupply(_S.CURRENT_INVENTORY, avail, combination_id=cid, vin=op_id,
                                          stock=stock, age_days=age, arrival_month=arrival))

    # LIVE DMS snapshot units (the real on-ground / incoming physical inventory)
    if plan_key:
        og, inc = _demo_live_units(app, scope, plan_key)
        for u in og:
            _add(current, u["op_id"], age=u["dis"], stock=u["stock"])
        for u in inc:
            _add(incoming, u["op_id"], arrival=(u["arrival_month"] or None), stock=u["stock"])

    # Phase-4 projections (present in tests / any environment that populates them) — unioned, deduped
    def _vin(table, key):
        try:
            r = conn.execute(f"SELECT vin FROM {table} WHERE id=? AND store_scope=?", (key, scope)).fetchone()
            return (r["vin"].strip().upper() if r and r["vin"] else None)
        except Exception:   # noqa: BLE001
            return None

    for cs in st.current_supply_for(cid, scope):
        _add(current, (_vin("vehicle_unit", cs.vehicle_unit_id) or ""), age=cs.age_days)
    unbuilt = False
    for fs in st.future_supply_for(cid, scope):
        vin = _vin("production_order", fs.production_order_id)
        if vin:
            _add(incoming, vin, arrival=fs.arrival_month)
        else:
            unbuilt = True
    order_available = unbuilt or not (current or incoming)
    return current, incoming, order_available


DEMO_SWAP_MILES = 2000        # preferred swap around ~2,000 mi (ideally 1,xxx) — policy guidance, not a hard rule
DEMO_CADENCE_DAYS = 90        # rough replacement cadence — planning guidance only, never a hard trigger


def _demo_replacement_due(cur, today):
    """Decision A — is the CURRENT demo due for replacement NOW? Uses the demo policy (miles first, ~90-day
    cadence as guidance). Honest about evidence: with no CURRENT mileage reading it never pretends 'due' — it
    reports exactly the missing evidence. Returns {state, detail, accumulated, days} where state is
    'unknown_mileage' | 'keep' | 'due' | 'no_demo'."""
    import datetime as _dt
    if not cur or not cur.get("vin"):
        return {"state": "no_demo", "detail": "No demo is currently assigned.", "accumulated": None, "days": None}
    days = None
    try:
        days = max(0, (_dt.date.fromisoformat(str(today)[:10])
                       - _dt.date.fromisoformat(str(cur.get("start"))[:10])).days)
    except Exception:   # noqa: BLE001
        days = None
    mi_now = cur.get("mi_now")
    if mi_now in (None, "") or str(mi_now).strip() == "":
        return {"state": "unknown_mileage", "days": days, "odometer": None,
                "detail": "Current odometer reading is needed to assess replacement — record the demo's current "
                          "mileage. Elite will not assume it is due."}
    # The swap point is the vehicle's CURRENT TOTAL ODOMETER (~2,000 mi, ideally still in the 1,xxx range), NOT
    # miles accumulated since assignment — assignment mileage informs velocity/history, it never raises the bar.
    odo = _int_or0(mi_now)
    cadence = f" (~{days}d in service; ~{DEMO_CADENCE_DAYS}d is typical guidance)" if days is not None else ""
    if odo >= DEMO_SWAP_MILES:
        return {"state": "due", "odometer": odo, "days": days,
                "detail": f"Current odometer ~{odo:,} mi — at or past the ~{DEMO_SWAP_MILES:,} mi swap point{cadence}."}
    return {"state": "keep", "odometer": odo, "days": days,
            "detail": f"Current odometer ~{odo:,} mi — below the ~{DEMO_SWAP_MILES:,} mi swap point"
                      f"{' (approaching the window)' if odo >= 1000 else ''}{cadence}."}


def _demo_current_row(app, scope, ident):
    """The DMS inventory row for an assigned demo, matched by VIN, serial, OR stock (a roster 'unit' may be any
    of these). Returns the row or None. Real snapshot only — never fabricated."""
    ident = (ident or "").strip().upper()
    if not ident:
        return None
    try:
        from ...loaner.placement import read_new_retail_units, _authoritative_vin
        for r in (read_new_retail_units(app, scope) or []):
            rv, ok, serial = _authoritative_vin(r)
            stock = str(r.get("stock_number") or r.get("stock") or "").strip().upper()
            if ident in {(rv if ok else "").strip().upper(), (serial or "").strip().upper(), stock} - {""}:
                return r
    except Exception:   # noqa: BLE001
        pass
    return None


def _demo_current_build(app, scope, vin):
    """Human build (model / trim / drivetrain / colours) for an assigned demo, from the governed DMS description
    — never the bare VIN or an '[code] (unmapped)' string. '' when the physical unit cannot be resolved (the
    caller then shows only the operational unit tag; nothing is fabricated)."""
    r = _demo_current_row(app, scope, vin)
    if r is None:
        return ""
    try:
        from ...newinv.dms_identity import dms_planning_identity
        from .domains import _describe
        d = _describe(app, scope, dms_planning_identity(r))
        if d:
            line = d.vehicle or ""
            colours = d.colours(with_code=False, drop_unmapped=True) if hasattr(d, "colours") else ""
            return " — ".join(x for x in (line, colours) if x)
    except Exception:   # noqa: BLE001
        pass
    return ""


def _mask_vin(v):
    """Manager execution views never show a full VIN — only a short unit tag (last 6). Full VINs remain in the
    collapsed Technical Proof / audit."""
    v = (v or "").strip().upper()
    return f"Unit {v[-6:]}" if len(v) >= 6 else (f"Unit {v}" if v else "—")


def _demo_combo_build(app, scope, cid):
    """The governed human build (model / trim / drivetrain / exterior · interior) for a combination, from its
    canonical identity — the SAME governed identity the Demo candidate/replacement engine already resolved. Used
    to label a selected physical unit whose own DMS inventory row is NOT in `read_new_retail_units` (e.g. an
    incoming Production-Order unit lives in the pipeline/production-orders source, not the inventory snapshot).
    '' when the combination cannot be described (never fabricated)."""
    if not cid:
        return ""
    try:
        row = _conn(app).execute("SELECT canonical_identity FROM sellable_combination WHERE id=? AND store_scope=?",
                                 (cid, scope)).fetchone()
        if not row:
            return ""
        from .domains import _describe
        d = _describe(app, scope, row["canonical_identity"] or cid)
        if d:
            line = d.vehicle or ""
            colours = d.colours(with_code=False, drop_unmapped=True) if hasattr(d, "colours") else ""
            return " — ".join(x for x in (line, colours) if x)
    except Exception:   # noqa: BLE001
        pass
    return ""


def _demo_unit_label(app, scope, op_id, *, combination_id=None):
    """Presentation for a physical unit on the manager surface: the governed human build (model / trim /
    drivetrain / exterior) + the operational unit tag. The build resolves from the unit's own DMS inventory row
    when present, ELSE from its already-governed COMBINATION identity — so an incoming Production-Order unit
    (which the candidate engine selected from the pipeline, not the inventory snapshot) still shows its human
    build. Falls back to the unit tag alone when neither resolves (never a fabricated build, never a VIN)."""
    op_id = (op_id or "").strip()
    if not op_id:
        return "—"
    build = _demo_current_build(app, scope, op_id) or _demo_combo_build(app, scope, combination_id)
    tag = _mask_vin(op_id)
    return f"{build} · {tag}" if build else tag


def _demo_inv_age(app, scope, vin):
    """Inventory age (days in stock) for a physical unit — a SEPARATE clock from Demo days. Sourced from the live
    DMS snapshot (days-in-stock), else a current-supply projection; '—/unknown' when it genuinely cannot be
    sourced (never fabricated)."""
    ident = (vin or "").strip().upper()
    if not ident:
        return "—"
    r = _demo_current_row(app, scope, ident)                 # live DMS row (days-in-stock)
    if r is not None:
        dis = _dms_dis(r)
        if dis is not None:
            return f"{dis}d"
    try:
        row = _conn(app).execute(
            "SELECT c.age_days AS a FROM current_supply_projection c JOIN vehicle_unit v ON v.id=c.vehicle_unit_id "
            "WHERE UPPER(v.vin)=? AND c.store_scope=? ORDER BY c.calculation_timestamp DESC LIMIT 1",
            (ident, scope)).fetchone()
        if row and row["a"] is not None:
            return f"{int(row['a'])}d"
    except Exception:   # noqa: BLE001
        pass
    return "unknown"


def _demo_governed_combos(app, scope):
    """Certified combination_ids whose PRODUCTION IDENTITY is fully governed (recognized family + governed
    exterior/interior names, no `(unmapped)` / phantom). A Demo replacement or ORDER target must be one of these
    — the phantom 8311/QBE/C class can never be offered (same discipline as the CTP executable gate)."""
    from .domains import _describe
    conn = _conn(app)
    canon = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    ok = set()
    for cid, canonical in canon.items():
        d = _describe(app, scope, canonical)
        if (d and getattr(d, "has_family", False)
                and (getattr(d, "exterior_name", "") or "").strip()
                and (getattr(d, "interior_name", "") or "").strip()
                and not getattr(d, "unresolved", ())):
            ok.add(cid)
    return ok


def _demo_observations(u):
    """(assignment_mileage, current_observations, completed_cycles) for the driver's CURRENT assignment.

    ASSIGNMENT mileage is its own fact (mileage at assignment), returned separately — it is NEVER a current
    odometer. current_observations are DATED post-assignment readings (a recorded reading, a return/swap, or an
    authoritative dated exact-VIN odometer). completed_cycles are prior whole Demo cycles for this driver, so
    learned velocity persists across Demo vehicles."""
    cur = u.get("current") or {}
    start = str(cur.get("start") or "")[:10]
    assignment_mi = _int_or0(cur.get("mi_in")) if cur.get("mi_in") is not None else None
    obs = []
    for o in (u.get("mileage_obs") or []):
        if not (o.get("date") and o.get("miles") is not None):
            continue
        if (o.get("source") == "assignment") or (start and str(o["date"])[:10] < start):
            continue                                               # the assignment reading is not a current obs
        obs.append({"date": str(o["date"])[:10], "miles": _int_or0(o["miles"]), "source": o.get("source", "")})
    obs.sort(key=lambda o: o["date"])
    cycles = []
    for h in u.get("history", []):
        try:
            import datetime as _dt
            d0 = _dt.date.fromisoformat(str(h.get("start"))[:10])
            d1 = _dt.date.fromisoformat(str(h.get("end"))[:10])
            cycles.append({"miles": _int_or0(h.get("miles")), "days": max(1, (d1 - d0).days)})
        except Exception:   # noqa: BLE001
            pass
    return assignment_mi, obs, cycles


def _demo_signals(app, scope):
    """Per-combination Demo-suitability signals from the certified plan evidence (real Speed-to-Sell velocity,
    days-to-sell burden, inventory depth) — so 'best Demo' means a proven fast mover, not the largest shortage."""
    conn = _conn(app)
    out = {}
    for r in conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                          (scope,)).fetchall():
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        dts = dec.get("dts_burden")
        out[r["combination_id"]] = {
            "need": int(dec.get("acquire_units", 0) or 0),
            "dts_burden": float(dts) if isinstance(dts, (int, float)) else 0.0,
            "expected_demand": float(r["expected_demand"] or 0.0),
            "depth": int(r["current_supply"] or 0) + int(r["future_supply"] or 0)}
    return out


def _demo_order_orderable(app, scope, cid):
    """Governed CURRENT orderability for a combination's family (reuses the CTP resolve_order discipline): a
    deterministic identity is NOT proof the factory will accept an order today. Returns True only when the
    family resolves to a currently-orderable order version, else False (-> honest REVIEW, never false ORDER)."""
    try:
        from ...identity.translation import TranslationStore
        from ...newinv.dms_identity import code4
        conn = _conn(app)
        row = conn.execute("SELECT canonical_identity FROM sellable_combination WHERE id=? AND store_scope=?",
                           (cid, scope)).fetchone()
        if not row:
            return False
        from .domains import _describe
        d = _describe(app, scope, row["canonical_identity"] or cid)
        code = code4(getattr(d, "model_code", "") or "") if d else ""
        xlat = TranslationStore(app.prefs, scope)
        fam = xlat.family_for_code(code) if code else None
        if fam is None:
            return False
        return xlat.resolve_order(fam).get("status") == "order"
    except Exception:   # noqa: BLE001
        return False


def _sl_has_add_need(app, scope):
    """Does the EXISTING Service-Loaner self-balancing engine actually require a unit right now? Reused, never
    duplicated — the Demo->SL bridge only surfaces SL REVIEW when SL genuinely needs a unit."""
    try:
        from ...loaner.self_balancing import build_requirement
        sb = build_requirement(_conn(app), scope, app.prefs)
        return bool(sb.desired is not None and int(sb.calculated_need) > 0)
    except Exception:   # noqa: BLE001
        return False


def _demo_outgoing(decision_state, *, replacement_secured, sl_need):
    """Operational disposition for the OUTGOING demo when a swap/pull is called. No economics, no full VIN. The
    returned demo becomes normal retail supply once unless a real governed current-use destination is superior;
    Demo->SL is never automatic — only SERVICE LOANER REVIEW when SL actually needs a unit."""
    from ...operatorstd import demo_board as DB
    if decision_state in (DB.KEEP, DB.REVIEW):
        return ""
    if not replacement_secured:
        return "HOLD UNTIL REPLACEMENT"
    if sl_need:
        return "SERVICE LOANER REVIEW"
    return "RETURN TO RETAIL"


def _demo_cockpit(app, scope, roster, today):
    """The manager operating board: for every active demo, the KEEP/PLAN SWAP/SWAP NOW/PULL/REVIEW decision, the
    correct mileage/learning state, a Demo-suitability-ranked + portfolio-allocated replacement path (one
    physical unit never assigned twice), and the outgoing disposition. Reuses the governed physical pools +
    demo_board engine + SL self-balancing; no economics, no full VINs."""
    from ...operatorstd import demo_board as DB
    certs, label_to_key = _certified_positions(app, scope)
    governed = _demo_governed_combos(app, scope)
    signals = _demo_signals(app, scope)
    label_of = {c["key"]: c["label"] for c in certs}
    model_of = {c["key"]: _model_of(c["label"]) for c in certs}

    def _candidates(pref):
        cands = []
        for c in certs:
            cid = c["key"]
            if cid not in governed or c["acquire_units"] <= 0:
                continue
            sig = signals.get(cid, {})
            depth = int(sig.get("depth", 0))
            cands.append({"cid": cid, "label": label_of.get(cid, ""), "model": model_of.get(cid, ""),
                          "need": c["acquire_units"], "dts_burden": sig.get("dts_burden", 0.0),
                          "expected_demand": sig.get("expected_demand", 0.0), "depth": depth,
                          "last_on_lot": depth <= 1, "has_incoming_or_order": True, "governed": True})
        ranked = DB.rank_demo_candidates(cands, preferred_model=(pref or None))
        # honor a stated preference as a filter when at least one preferred candidate is eligible
        if pref:
            pref_hits = [r for r in ranked if r.model == pref and r.eligible]
            if pref_hits:
                return pref_hits[0], ranked
        elig = [r for r in ranked if r.eligible]
        return (elig[0] if elig else (ranked[0] if ranked else None)), ranked

    sl_need = _sl_has_add_need(app, scope)
    entries, meta, pools = [], {}, {}
    for u in roster:
        cur = u.get("current") or {}
        if not cur.get("vin"):
            continue
        assignment_mi, obs, cycles = _demo_observations(u)
        ms = DB.mileage_state(cur.get("start"), assignment_mi, obs, today, completed_cycles=cycles)
        dec = DB.decide(cur.get("start"), today, ms, pull_reason=u.get("pull_reason", ""))
        best, ranked = _candidates((u.get("model_pref") or "").upper())
        tgt = best.cid if best else None
        if tgt is not None and tgt not in pools:
            c, i, order_ok = _demo_pools(app, scope, tgt)
            pools[tgt] = {"current": c, "incoming": i, "order": order_ok, "label": label_of.get(tgt, ""),
                          "orderable": _demo_order_orderable(app, scope, tgt), "suitability": best}
        entries.append({"id": u["id"], "decision": dec, "pool_key": tgt})
        meta[u["id"]] = {"user": u, "decision": dec, "ms": ms, "target": tgt, "ranked": ranked, "sl_need": sl_need}
    alloc = DB.allocate_replacements(entries, pools)
    return meta, alloc, pools


def _demo_best_candidates(app, scope, *, per_model=3):
    """The 'Best Demo Candidates' management section — separate governed QX60 / QX65 / QX80 lists, top-N each,
    ranked by Demo SUITABILITY (proven fast movers, not the largest shortage), each carrying the physical action
    (USE NOW / WAIT FOR INCOMING / REORDER BEFORE PULLING / ORDER FOR DEMO — REVIEW). Reuses the certified plan,
    suitability engine, governed physical pools and orderability. No VINs, no economics."""
    from ...operatorstd import demo_board as DB
    certs, _lk = _certified_positions(app, scope)
    governed = _demo_governed_combos(app, scope)
    signals = _demo_signals(app, scope)
    label_of = {c["key"]: c["label"] for c in certs}
    by_model = {}
    for c in certs:
        cid = c["key"]
        if cid not in governed or c["acquire_units"] <= 0:
            continue
        model = _model_of(c["label"])
        sig = signals.get(cid, {})
        depth = int(sig.get("depth", 0))
        by_model.setdefault(model, []).append({
            "cid": cid, "label": label_of.get(cid, ""), "model": model, "need": c["acquire_units"],
            "dts_burden": sig.get("dts_burden", 0.0), "expected_demand": sig.get("expected_demand", 0.0),
            "depth": depth, "last_on_lot": depth <= 1, "has_incoming_or_order": True, "governed": True})
    out = {}
    for model in ("QX60", "QX65", "QX80"):
        cands = by_model.get(model) or []
        if not cands:
            continue
        ranked = [r for r in DB.rank_demo_candidates(cands) if r.eligible][:per_model]
        rows = []
        for rank, s in enumerate(ranked, start=1):
            cur, inc, order_ok = _demo_pools(app, scope, s.cid)
            cc = len(cur)
            orderable = _demo_order_orderable(app, scope, s.cid)
            action = DB.candidate_action(cc, bool(inc), orderable=orderable, order_available=order_ok)
            inv_age = "—"
            if cur:
                ages = [getattr(u, "age_days", None) for u in cur if getattr(u, "age_days", None) is not None]
                inv_age = f"{min(ages)}d (best)" if ages else "—"
            rows.append({"rank": rank, "build": s.label, "why": " · ".join(s.reasons[:3]), "note": s.note,
                         "on_ground": cc, "incoming": len(inc), "inv_age": inv_age, "action": action,
                         "proof": s.proof or {}})
        if rows:
            out[model] = rows
    return out


def _demo_call_card(app, scope, cid, label):
    """Render the three-pool Demo decision (USE NOW / WAIT FOR INCOMING / ORDER FOR DEMO) for one combination,
    with the actual physical VINs. Demo economics are not governed, so Elite enumerates the physically-eligible
    pools and states the exact economic gap rather than fabricating a pick or importing SL rules (item 9)."""
    from ...operatorstd import demo_engine as _DE, physical as _P
    cur, inc, order_ok = _demo_pools(app, scope, cid)
    d = _DE.decide(_P.Need(combination_id=cid, label=label), current=cur, incoming=inc, order_available=order_ok)
    if d.call == _DE.USE_NOW and d.unit:
        head = safe(badge("completed", "USE NOW") + f' <strong>{esc(d.unit.vin)}</strong>')
    elif d.call == _DE.WAIT_FOR_INCOMING and d.unit:
        head = safe(badge("need", "WAIT FOR INCOMING") + f' <strong>{esc(d.unit.vin)}</strong> · '
                    + esc(d.unit.arrival_month or d.unit.availability))
    elif d.call == _DE.ORDER_FOR_DEMO:
        head = safe(badge("pending", "ORDER FOR DEMO") + f' {esc(d.order_combination or label)}')
    else:
        head = safe(badge("stale", "PENDING DEMO ECONOMICS"))
    poolA = ", ".join(u.vin for u in d.current_pool) or "—"
    poolB = ", ".join(f'{u.vin} ({u.arrival_month or u.availability})' for u in d.incoming_pool) or "—"
    gap = ""
    if d.economics_gap:
        gap = ('<p class="muted">Elite will not fabricate an economic Demo pick. Governed Demo economics are '
               'required to rank these physical candidates — the exact missing inputs are:</p><ul>'
               + "".join(f"<li>{esc(x)}</li>" for x in d.economics_gap) + "</ul>")
    return ('<div class="card"><h3>Demo decision — ' + esc(label) + '</h3>'
            f'<p>{head}</p>'
            + kv([("A · Current on-ground VINs", poolA), ("B · Known incoming VINs", poolB),
                  ("C · Order path", "available" if d.order_available else "—")])
            + f'<p class="muted">{esc(d.why)}</p>' + gap + '</div>')


def _callup_board(short):
    cards = ""
    for model in ("QX60", "QX65", "QX80"):
        picks = [b for b in short if b["model"] == model]
        best = picks[0].get("identity_h", picks[0]["identity"]) if picks else "none available in the current plan"
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
            reason = f"Exact shortage: {need.get('identity_h', need['identity'])} (need {qty})"
        elif code and code == need_code and ext and ext == need_ext:
            score = 700 + qty * 50
            reason = f"Same model code + exterior as shortage: {need.get('identity_h', need['identity'])}"
        elif code and code == need_code and interior and interior == need_int:
            score = 650 + qty * 50
            reason = f"Same model code + interior as shortage: {need.get('identity_h', need['identity'])}"
        elif code and code == need_code:
            score = 500 + qty * 40
            reason = f"Same model code as shortage: {need.get('identity_h', need['identity'])}"
        else:
            score = 100 + qty * 10
            reason = f"Model-level shortage relief: {need_model}"

        if score > best_score:
            best_score = score
            best_reason = reason
            best_qty = qty

    return best_score, best_reason, best_qty


_TRADE_TIER_LABEL = {1: "AVAILABLE NOW", 2: "IN TRANSIT", 3: "FUTURE / ORDER"}
_TRADE_BEST_HEAD = {1: "BEST AVAILABLE-NOW ASK", 2: "BEST IN-TRANSIT ASK", 3: "BEST FUTURE / ORDER OPPORTUNITY"}


def _trade_availability(unit):
    """Governed availability class for a counterparty candidate, preserving its real source state (never
    flattened). Returns (stage, tier): stage in DLR-INV / SIT / NNA-INV / ONS / OTHER; tier 1 = on a dealer lot
    now (DLR-INV), 2 = positively-identified inbound (SIT / NNA-INV), 3 = future order (ONS), 4 = unknown. The
    exact source Location token wins; only when absent is the class inferred conservatively from the preserved
    stock / DIS / ETA fields. A future ONS row must never silently occupy the immediate-availability slot."""
    hay = " ".join(str(unit.get(k) or "") for k in
                   ("location", "stage", "status", "availability", "body_style", "raw")).upper()
    stage = "OTHER"
    for tok in ("DLR-INV", "NNA-INV", "SIT", "ONS"):
        if tok in hay:
            stage = tok
            break
    if stage == "OTHER":                                   # infer only when the source carried no explicit stage
        try:
            dis = int(unit.get("dis") or 0)
        except (TypeError, ValueError):
            dis = 0
        eta = str(unit.get("eta") or "").strip()
        has_stock = bool(str(unit.get("stock_number") or "").strip())
        if dis > 0:
            stage = "DLR-INV"          # physically on a lot now: days-in-stock have accrued
        elif eta:                      # not in stock yet, but a future arrival/ETA is known -> INBOUND, not now
            stage = "SIT" if has_stock else "ONS"   # a stock# identified inbound = SIT; an order-only row = ONS
        # else: ambiguous (e.g. a stock# with DIS 0 and NO ETA) -> stays OTHER, never guessed AVAILABLE NOW
    tier = {"DLR-INV": 1, "SIT": 2, "NNA-INV": 2, "ONS": 3}.get(stage, 4)
    return stage, tier


def _trade_identity(unit, stage):
    """The COMPLETE external-source identity for one candidate — never an anonymous combination when the source
    row named a specific unit/order. dealer · Stock / Serial-or-Order · stage · model[/code] ext/int · DIS/ETA."""
    parts = []
    if unit.get("dealer"):
        parts.append(str(unit["dealer"]))
    ids = []
    if str(unit.get("stock_number") or "").strip():
        ids.append(f"Stock {unit['stock_number']}")
    if str(unit.get("serial") or "").strip():
        ids.append(f"Serial/Order {unit['serial']}")       # ONS orders keep their real order/serial identifier
    if ids:
        parts.append(" · ".join(ids))
    if stage and stage != "OTHER":
        parts.append(stage)
    label = unit.get("identity") or unit.get("description") or ""
    if label:
        parts.append(str(label))
    tail = []
    if stage == "DLR-INV" and unit.get("dis"):
        tail.append(f"DIS {unit['dis']}")
    if str(unit.get("eta") or "").strip() and stage in ("ONS", "SIT", "NNA-INV"):
        tail.append(f"ETA {unit['eta']}")
    if tail:
        parts.append(" · ".join(tail))
    return " — ".join(parts)


def _trade_has_identity(unit):
    """True when the source row named a SPECIFIC unit/order (stock or serial/order#). We never ask the operator
    to mark an anonymous candidate unavailable, and never present one as an actionable Best ask."""
    return bool(str(unit.get("stock_number") or "").strip() or str(unit.get("serial") or "").strip())


def _trade_unit_key(unit):
    """A STABLE external-candidate identity key for the Unavailable mark — bound to the unit/order, NOT the row
    position. A re-pasted or reordered snapshot keeps the same unit unavailable, and never blacklists a whole
    configuration. Physical unit: dealer + stage + stock + serial (dealer+stock+serial is sufficient identity).
    ONS/order: dealer + stage + serial/order. A deliberate free-text combination (no unit/order) keys by dealer
    + stage + what was entered — still specific to that entry, never a configuration-wide ban."""
    def _n(v):
        return " ".join(str(v or "").split()).upper()
    dealer = _n(unit.get("dealer"))
    stock = _n(unit.get("stock_number"))
    serial = _n(unit.get("serial"))
    stage, _tier = _trade_availability(unit)
    if stock or serial:
        return "|".join(("U", dealer, stage, stock, serial))
    return "|".join(("C", dealer, stage, _n(unit.get("identity") or unit.get("description"))))


def _trade_eta_month(unit, stage):
    """The month a candidate would realistically become OUR supply: DLR-INV -> None (now); SIT/ONS -> its
    specific ETA / production month, parsed conservatively to 'YYYY-MM' (or 'MONTH-NN' when only a month name is
    given, resolved against the horizon), or '' when no usable timing is present."""
    if stage == "DLR-INV":
        return None
    import re
    e = str(unit.get("eta") or "").strip()
    if not e:
        return ""
    m = re.match(r"^(\d{4})-(\d{1,2})", e)                   # YYYY-MM(-DD)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", e)         # MM/DD/YYYY
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{1,2})/(\d{4})$", e)                  # MM/YYYY
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    names = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
             "november", "december"]
    tok = e.split()[0].lower() if e.split() else ""
    if tok in names:
        return f"MONTH-{names.index(tok) + 1:02d}"           # year-agnostic month; resolved against the horizon
    return ""


def _trade_combo_key(model, code, ext, intr):
    return (str(model or "").upper(), str(code or "").upper(), str(ext or "").upper(), str(intr or "").upper())


def _trade_shortage_series(app, scope):
    """Per-configuration certified time-phased SHORTAGE series (no recompute), keyed by governed build identity
    (model, model_code, exterior, interior) -> {'months': [(YYYY-MM, shortage)], 'acquire_now': n}. Read straight
    from the issued inventory_plan_result + inventory_plan_month — the SAME certified projection every other
    engine reads. Nothing is fabricated and no shortage math is changed."""
    conn = _conn(app)
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    pmonths = _plan_months(app, scope)
    series = {}
    for r in conn.execute("SELECT id, combination_id, evidence FROM inventory_plan_result "
                          "WHERE store_scope=? AND status='issued'", (scope,)).fetchall():
        readable = _readable(ident.get(r["combination_id"], r["combination_id"]))
        parts = readable.split()
        code = parts[1] if len(parts) > 1 else ""
        colors = parts[2] if len(parts) > 2 else ""
        ext, intr = (colors.split("/", 1) + [""])[:2] if "/" in colors else ("", "")
        key = _trade_combo_key(_model_of(readable), code, ext, intr)
        months = pmonths.get(r["id"]) or {}
        ms = sorted(((m, float(row["shortage"] or 0.0)) for m, row in months.items()), key=lambda t: t[0])
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        series[key] = {"months": ms, "acquire_now": int(dec.get("acquire_units", 0) or 0)}
    return series


def _trade_overall_benefit(unit, stage, series):
    """The horizon-aware inventory-position benefit of trading FOR this candidate: the certified projected
    shortage of the candidate's EXACT configuration that this ONE unit would relieve, measured from the month it
    would actually become our supply through the end of the certified horizon (one unit relieves at most one unit
    of shortage per month). Uses only the governed projection — no invented weights, no availability bonuses.
    Returns a dict, or None when the candidate's exact configuration is not a certified plan/shortage."""
    key = _trade_combo_key(unit.get("model"), unit.get("model_code"), unit.get("ext"), unit.get("int"))
    s = series.get(key)
    if not s or not s["months"]:
        return None
    months = s["months"]
    avail = _trade_eta_month(unit, stage)
    if avail is None:
        start = 0                                            # available now -> the whole horizon
    elif avail == "":
        start = len(months)                                 # no usable timing -> credit no early relief
    elif avail.startswith("MONTH-"):
        mm = avail.split("-")[1]
        start = next((i for i, (ym, _sh) in enumerate(months) if ym.split("-")[1] == mm), len(months))
    else:
        start = next((i for i, (ym, _sh) in enumerate(months) if ym >= avail), len(months))
    relieved = sum(min(1.0, max(0.0, sh)) for _ym, sh in months[start:])
    horizon = sum(min(1.0, max(0.0, sh)) for _ym, sh in months)
    return {"benefit": round(relieved, 3), "horizon_short": round(horizon, 3),
            "avail_month": (months[start][0] if start < len(months) else (avail or "beyond horizon")),
            "months_relieved": len(months) - start,
            "shortage_at_avail": (round(months[start][1], 2) if start < len(months) else 0.0)}


def _trade_overall_why(t, ov, harmful, alt):
    """Plain-business explanation of why this candidate is the best OVERALL trade: fit, timing, projected need
    when it would arrive, effect on our future inventory position, and outgoing-unit harm."""
    when = "available now on a dealer lot" if t["stage"] == "DLR-INV" else \
        f"arriving {ov['avail_month'] if ov else 'later'} ({t['stage']})"
    if ov and ov["benefit"] > 0:
        need = (f"our certified board still projects this exact configuration short by "
                f"{ov['shortage_at_avail']} when it would arrive, and one unit relieves about "
                f"{ov['benefit']} shortage-month(s) across the horizon — the largest projected relief of any "
                f"available candidate")
    elif ov:
        need = ("our certified board does not project this configuration short by the time it would arrive, so it "
                "adds flexibility rather than filling a proven gap")
    else:
        need = ("this configuration is not a certified shortage, so it is a model-level flexibility play rather "
                "than a proven-need fill")
    harm = (f" Rather than releasing the requested unit (a build we are short on), offer “{alt}” instead — we "
            f"are over-stocked there, so the outgoing harm is lower.") if (harmful and alt) else ""
    return f"{t['reason']}, {when}; {need}.{harm}"


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
    harmful, alt = False, None
    if req:
        # is what they asked for something WE are short on? then propose a lower-harm alternative from our over-stock
        harmful = any(b["model"] in req.upper() or b["identity"] in req for b in short)
        alt = over[0].get("identity_h", over[0]["identity"]) if over else None
        rec = (f'Releasing “{esc(req)}” is costly — it is a combination we are short on. '
               + (f'Lower-harm alternative to offer instead: <strong>{esc(alt)}</strong> (we are over-stocked there).'
                  if alt else 'No over-stocked alternative is available to offer instead.')) if harmful \
            else f'Releasing “{esc(req)}” is reasonable — it is not a combination we are short on.'
        out += f'<div class="card"><h3>Should we release what they asked for?</h3><p>{rec}</p></div>'
    # Parse the counterparty snapshot into actual external vehicles, then rank each
    # against the certified combination-level shortage board.
    raw_inventory = st.get("inv_raw", "\n".join(st.get("inv", [])))
    candidates = _parse_external_trade_inventory(raw_inventory)
    unavail = {str(x) for x in st.get("unavail", [])}       # stable unit keys (legacy int-index marks ignored)

    scored = []
    for i, unit in enumerate(candidates):
        score, reason, shortage_qty = _score_external_trade_candidate(unit, short)
        stage, tier = _trade_availability(unit)
        scored.append({"idx": i, "unit": unit, "score": score, "reason": reason, "qty": shortage_qty,
                       "stage": stage, "tier": tier, "key": _trade_unit_key(unit)})

    # rank WITHIN each availability tier by the existing certified shortage FIT (age only as a tie-breaker). We
    # never mix tiers into one flat rank, so an anonymous/future ONS row cannot silently outrank an equivalent
    # exact physical DLR-INV unit. The Unavailable filter is by STABLE UNIT KEY, never row position.
    def _fit_key(t):
        u = t["unit"]
        return (-t["score"], -int(u.get("dis", 0) or 0), str(u.get("stock_number", "")),
                str(u.get("serial", "")), str(u.get("identity", "")))
    available = sorted((t for t in scored if t["key"] not in unavail), key=lambda t: (t["tier"], *_fit_key(t)))
    by_tier = {}
    for t in available:
        by_tier.setdefault(t["tier"], []).append(t)

    # ---- DECISION LAYER: the single BEST OVERALL trade across ALL availability states. Each candidate's value
    #      is measured at the month it would actually become our supply, against the certified projected shortage
    #      of its EXACT configuration over the horizon (governed inventory_plan_month). Availability tiers are NOT
    #      hardwired — timing is captured only through when the relief starts. Fit is the tie-break; sooner is the
    #      final tie-break, never an override. ----
    series = _trade_shortage_series(app, s.scope)
    for t in scored:
        t["overall"] = _trade_overall_benefit(t["unit"], t["stage"], series)

    def _overall_key(t):
        ben = t["overall"]["benefit"] if t["overall"] else -1.0
        return (-ben, -t["score"], t["tier"], str(t["unit"].get("identity", "")))
    best_overall = min(available, key=_overall_key) if available else None

    overall_card = ""
    if best_overall is not None:
        bo, ov = best_overall, best_overall["overall"]
        why = _trade_overall_why(bo, ov, harmful, alt)
        offer_line = (f'<p><strong>Offer instead:</strong> {esc(alt)} '
                      '<span class="muted">(we are over-stocked there — lower outgoing harm than releasing the '
                      'requested unit)</span></p>') if (harmful and alt) else ""
        # comparison proof: best-of-each-tier by the same horizon-aware benefit, so the operator sees why A beat B/C
        cmp_rows = []
        for tier in (1, 2, 3):
            picks = by_tier.get(tier, [])
            if not picks:
                continue
            bt = min(picks, key=_overall_key)
            btov = bt["overall"]
            cmp_rows.append((_TRADE_TIER_LABEL[tier],
                             f'{_trade_identity(bt["unit"], bt["stage"])} — fit {bt["score"]} '
                             f'({bt["reason"]}); projected shortage relieved '
                             f'{btov["benefit"] if btov else 0} over {btov["months_relieved"] if btov else 0} mo '
                             f'from {btov["avail_month"] if btov else "n/a"}'))
        overall_card = (
            '<div class="card" style="border-left:4px solid var(--accent,#2f6fed)">'
            '<h3>Best overall trade opportunity</h3>'
            f'<div style="font-weight:600">{esc(_trade_identity(bo["unit"], bo["stage"]))}</div>'
            f'<div class="muted">{esc(_TRADE_TIER_LABEL.get(bo["tier"], "UNKNOWN"))}'
            + (f' · would become our supply {esc(ov["avail_month"])}' if ov else '') + '</div>'
            f'<p><strong>Ask for this unit / order back.</strong></p>'
            + offer_line
            + f'<p><strong>Why this is best:</strong> {esc(why)}</p>'
            + disclosure("Show best-overall comparison (why this beat the alternatives)", kv(cmp_rows))
            + '</div>')

    # ---- best-per-tier summary (SUPPORTING ALTERNATIVES, not decisions the operator must make) ----
    best_items = ""
    for tier in (1, 2, 3):
        picks = by_tier.get(tier, [])
        if not picks:
            continue
        best = picks[0]
        tag = safe(badge("stale", "FUTURE")) if tier == 3 else (
              safe(badge("completed", "AVAILABLE NOW")) if tier == 1 else safe(badge("need", "IN TRANSIT")))
        best_items += (f'<li><strong>{esc(_TRADE_BEST_HEAD[tier])}:</strong> {tag} '
                       f'{esc(_trade_identity(best["unit"], best["stage"]))} '
                       f'<span class="muted">— {esc(best["reason"])}</span></li>')
    best_card = (f'<div class="card"><h3>Best ask by availability</h3>'
                 f'<ul style="margin:4px 0;padding-left:18px">{best_items}</ul>'
                 '<p class="muted">Supporting alternatives by availability. Elite\'s single overall recommendation '
                 'is above — these are the best in each timing bucket for reference, not decisions to weigh.</p>'
                 '</div>') if best_items else ""

    # ---- full ranked table, grouped by availability tier, EVERY row carrying its complete source identity ----
    rows = []
    for tier in (1, 2, 3, 4):
        picks = by_tier.get(tier, [])
        if not picks:
            continue
        label = _TRADE_TIER_LABEL.get(tier, "UNKNOWN")
        for rank, t in enumerate(picks, 1):
            unit, stage = t["unit"], t["stage"]
            tier_badge = badge("completed" if tier == 1 else "need" if tier == 2 else "stale", label)
            # A STRUCTURED source row that lost its unit identity is never actionable (we never ask the operator
            # to mark an anonymous unit unavailable). A deliberate free-text combination entry stays actionable —
            # it is a combination-level ask by design, not a specific unit whose identity was dropped.
            actionable = _trade_has_identity(unit) or not unit.get("structured", False)
            display = _trade_identity(unit, stage) if actionable else (
                (unit.get("identity") or unit.get("description") or "") + " · combination only (no specific unit)")
            unavail_btn = safe(_ws_btn(s, "/dealer-trade/their/unavailable", "key", t["key"], "Unavailable")) \
                if actionable else safe('<span class="muted">—</span>')
            rows.append([safe(tier_badge) + (f' #{rank}' if rank > 1 else ' Best'),
                         esc(display), esc(f"{t['score']} | {t['reason']}"), unavail_btn])

    # ---- units the operator marked unavailable (identity preserved; the mark is bound to the exact unit/order
    #      by STABLE KEY, so it survives a re-paste/reorder and never blacklists a whole configuration) ----
    for t in scored:
        if t["key"] not in unavail:
            continue
        rows.append([safe(badge("stale", "unavailable")),
                     esc(_trade_identity(t["unit"], t["stage"])), esc("—"), safe("")])

    if candidates:
        parsed_note = (
            f'<p class="muted">{len(candidates)} external candidate'
            f'{"s" if len(candidates) != 1 else ""} parsed. Availability is tiered — physical DLR-INV units are '
            'immediate; SIT/NNA-INV are inbound; ONS are future orders (their order/serial and ETA are kept). '
            'Within each tier, exact certified combination shortages rank ahead of model-level matches. External '
            'units do not become our supply until a trade is committed.</p>')
        out += overall_card
        out += best_card
        out += ('<div class="card"><h3>What we should ask for back (by availability, ranked)</h3>'
                + parsed_note
                + table(["Availability", "Their unit / order (full identity)", "Fit", ""], rows)
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
        alt = over[0].get("identity_h", over[0]["identity"]) if over else None
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
                    if batch:
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
                        # Membership projection runs once per batch. Dating (in-service date + mileage) is
                        # backfilled on EVERY upload — idempotently and even for an already-projected batch —
                        # so re-uploading the fleet CSV populates the authoritative dates/mileage on units that
                        # were created before dating reconciliation existed, without manual re-entry.
                        if not already_projected:
                            projector.reconcile(batch, accepted_rows)
                        else:
                            projector.backfill_dating(batch, accepted_rows)
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
            board_note = ""
            if contract_key in ("new_inventory_current", "new_inventory_pipeline_summary"):
                # a successful certified Inventory/Pipeline import recomputes the certified board from THIS
                # snapshot (the existing planning engine); a blocker never overwrites the last valid board.
                try:
                    from ...newinv.board_recompute import recompute_board
                    rb = recompute_board(app, scope, actor="import:" + contract_key)
                    board_note = (f" Certified board recomputed ({rb.get('issued_count', 0)} position(s))."
                                  if rb.get("ok") else f" Board NOT recomputed — {rb.get('reason', '')}")
                except Exception:   # noqa: BLE001 — recompute must never fail the accepted import
                    board_note = ""
            return f"Imported {safe} into {contract_key} - {state}.{id_note}{board_note}"
        return (f"Import of {safe} did not complete ({state}); previous data is unchanged and freshness "
                "was not updated.")
    except Exception as e:   # noqa: BLE001
        return f"Import failed and nothing was changed: {e}"
