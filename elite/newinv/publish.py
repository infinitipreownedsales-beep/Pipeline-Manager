"""Publish issued New-Inventory plans into the Phase 9 governance workspace (Today / Decision Inbox).

The planning runner persists Phase 4 ``inventory_plan_result`` rows (the certified board). The Decision Inbox
is driven by Phase 9 ``decision_workspace_item`` records created via the existing ``WorkspaceService``. This
module is the smallest bridge between the two: it reads the ALREADY-PERSISTED issued plans (never recomputes
or reimports) and materialises one workspace item per ACTIONABLE plan (ACQUIRE / EXCESS / MONITOR) using the
existing governance primitive, so the certified board enters the normal review / acknowledgement / approval
workflow. It is idempotent — a plan already represented by a workspace item is never published twice.
"""
from __future__ import annotations

import json


def _decision(row):
    """The persisted discrete decision bundle from a plan's evidence JSON (never recomputed)."""
    try:
        ev = json.loads(row["evidence"]) if row["evidence"] else {}
    except Exception:   # noqa: BLE001
        ev = {}
    return ev.get("decision") or {}


def plan_call(dec):
    """Dealer-facing call for an issued plan's persisted decision. WHOLE vehicles only."""
    acq = int(dec.get("acquire_units", 0) or 0)
    arr = int(dec.get("arrived_excess", 0) or 0)
    inc = int(dec.get("incoming_excess", 0) or 0)
    if acq > 0:
        return "ACQUIRE", acq, f"ACQUIRE {acq}"
    if arr > 0 or inc > 0:
        bits = []
        if arr:
            bits.append(f"{arr} arrived (disposition)")
        if inc:
            bits.append(f"{inc} incoming (redirect)")
        return "EXCESS", arr + inc, "EXCESS " + " + ".join(bits)
    if dec.get("monitor_months"):
        return "MONITOR", 0, "MONITOR — future coverage risk"
    return "NO_ACTION", 0, "NO ACTION"


def _existing_refs(conn, scope):
    return {r["recommendation_ref"] for r in conn.execute(
        "SELECT recommendation_ref FROM decision_workspace_item WHERE store_scope=?", (scope,)).fetchall()
        if r["recommendation_ref"]}


def publish_issued_inventory(conn, workspace, scope, *, domain="new_inventory"):
    """Materialise Phase 9 workspace items for every ACTIONABLE issued New-Inventory plan in `scope`.

    `conn` is the shared DB connection (reads inventory_plan_result); `workspace` is the Phase 9
    WorkspaceService (create_item). Idempotent: skips any plan already published. Returns a summary."""
    already = _existing_refs(conn, scope)
    rows = conn.execute(
        "SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued' ORDER BY issued_time,id",
        (scope,)).fetchall()
    created, skipped, by_call = 0, 0, {}
    for r in rows:
        dec = _decision(r)
        kind, qty, _label = plan_call(dec)
        if kind == "NO_ACTION":
            continue                                   # nothing to review; keep the inbox actionable
        if r["id"] in already:
            skipped += 1
            continue
        priority = "high" if kind in ("ACQUIRE", "EXCESS") else "normal"
        workspace.create_item(
            owning_domain=domain, store_scope=scope, recommendation_ref=r["id"],
            subject_entity_type="sellable_combination", subject_entity_id=r["combination_id"],
            planning_refs=[r["id"]],
            evidence_refs=[x for x in [r["id"], r["demand_result_id"], r["reproducibility_package"]] if x],
            priority=priority, workspace_state="READY_FOR_REVIEW")
        created += 1
        by_call[kind] = by_call.get(kind, 0) + 1
    return {"created": created, "skipped": skipped, "actionable": created + skipped,
            "total_issued": len(rows), "by_call": by_call}
