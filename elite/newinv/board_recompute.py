"""Recompute the certified New-Inventory board (`inventory_plan_result`) from the live loaded Inventory /
Pipeline snapshot — wiring the EXISTING governed planning engine (`plan_from_stores`) to production.

This changes NO supply/demand math, CTP logic, translation, or planning logic. It only invokes the already-
certified planning path against the exact latest imported snapshot and atomically swaps the issued board.

Guarantees:
  * derived from the exact successfully-imported snapshot (whichever Inventory contract holds the latest data);
  * ATOMIC swap — the prior board stays live until a new board is fully issued, then the prior board is
    superseded in one statement; a partial/failed run is rolled back and the last valid board is preserved;
  * a genuinely-missing required input (no Inventory snapshot, or planning issues nothing) NEVER overwrites the
    last valid board — it returns a clear blocker;
  * provenance is persisted (board computed_at + the exact inventory snapshot id/time it was derived from) so a
    consumer can detect a board older than the current Pipeline.
"""
from __future__ import annotations

from ..clock import to_utc_iso
from ..ids import new_id

INVENTORY_CONTRACTS = ("new_inventory_pipeline_summary", "new_inventory_current")
_PROV_KEY = "newinv_board_provenance"


def _ops_stack(app):
    for cand in (getattr(app, "_p11", None), getattr(getattr(app, "_pilot_stack", None), "p11", None),
                 getattr(app, "_pilot_stack", None)):
        if cand is not None and hasattr(cand, "orch") and hasattr(cand, "source_id"):
            return cand
    return None


def _snapshot_reader(app):
    ops = _ops_stack(app)
    ops_store = getattr(ops, "ops", None) if ops else None
    if ops is None or ops_store is None:
        return None, ops
    from .snapshots import SnapshotReader
    return SnapshotReader(ops_store, ops.data), ops


def latest_inventory_snapshot(app, scope):
    """(source_id, snapshot) for whichever Inventory contract holds the NEWEST completed snapshot, else
    (None, None). The same 'read whichever inventory contract has data' rule the rest of the app uses."""
    reader, ops = _snapshot_reader(app)
    if reader is None:
        return None, None
    best_src, best_snap, best_t = None, None, ""
    for key in INVENTORY_CONTRACTS:
        try:
            snap = reader.latest_snapshot(ops.source_id(key), scope)
        except Exception:   # noqa: BLE001
            snap = None
        if snap is not None:
            t = getattr(snap, "observed_time", None) or getattr(snap, "received_at", None) or ""
            if t >= best_t:
                best_src, best_snap, best_t = ops.source_id(key), snap, t
    return best_src, best_snap


def _snapshot_id_time(snap):
    # a snapshot's stable identity is its import run; observed_time is the safety comparator
    return (getattr(snap, "import_run_id", None) or getattr(snap, "id", None),
            getattr(snap, "observed_time", None) or getattr(snap, "received_at", None) or "")


def _calc_version(policy, metadata, family_name, meta_key):
    from ..policy.models import CalculationFamily, CalculationVersion
    cvid = metadata.get(meta_key)
    if cvid is not None:
        return cvid
    cf = policy.add_calc_family(CalculationFamily(id=new_id("cf"), name=family_name,
                                                  purpose="production new-inventory board recompute"))
    cv = policy.add_calc_version(CalculationVersion(id=new_id("cv"), family_id=cf.id, semver="1.0.0",
                                                    lifecycle_status="active", impl_revision="prod-1.0.0",
                                                    change_summary=family_name))
    metadata.put_if_absent(meta_key, cv.id)
    return cv.id


def build_planning_context(app, scope):
    """A PlanningContext over the app's shared connection — the SAME certified services Phase 4 wires, built
    on demand (they are stateless over the connection). No planning math is altered."""
    from ..policy.store import PolicyStore
    from .store import NewInvStore
    from .demand import DemandService
    from .forecast import ForecastService
    from .planning import PlanningService
    from .planning_runner import PlanningContext
    conn, clock, md = app.stack.db.conn, app.stack.clock, app.stack.metadata
    policy = PolicyStore(conn, clock)
    store = NewInvStore(conn, clock)
    return PlanningContext(
        scope=scope, store=store, clock=clock,
        demand=DemandService(store, clock, policy), forecast=ForecastService(store, clock, policy),
        planning=PlanningService(store, clock, policy),
        demand_cv=_calc_version(policy, md, "new_inventory_demand", "demand_cv_id"),
        plan_cv=_calc_version(policy, md, "new_inventory_plan", "plan_cv_id"), metadata=md)


def _issued_plan_ids(conn, scope):
    return {r["id"] for r in conn.execute(
        "SELECT id FROM inventory_plan_result WHERE store_scope=? AND status='issued'", (scope,)).fetchall()}


def _supersede(conn, ids):
    ids = list(ids)
    if not ids:
        return
    with conn:
        conn.execute("UPDATE inventory_plan_result SET status='superseded' WHERE id IN (%s)"
                     % ",".join("?" * len(ids)), ids)


def recompute_board(app, scope, *, actor="system"):
    """Recompute + atomically re-issue the certified board from the latest Inventory/Pipeline snapshot.

    Returns a dict: {ok, reason, issued_count, inventory_source_id, inventory_snapshot_id, computed_at}. On a
    blocker (no snapshot, or planning issues nothing) `ok` is False and the last valid board is left untouched."""
    now = to_utc_iso(app.stack.clock.now())
    reader, ops = _snapshot_reader(app)
    if reader is None:
        return {"ok": False, "reason": "The import service is not available in this runtime.", "issued_count": 0}
    inv_src, inv_snap = latest_inventory_snapshot(app, scope)
    if inv_snap is None:
        return {"ok": False, "reason": "No Inventory / Pipeline snapshot is loaded — import Inventory first; the "
                "last certified board was left unchanged.", "issued_count": 0}
    snap_id, snap_time = _snapshot_id_time(inv_snap)

    conn = app.stack.db.conn
    old_ids = _issued_plan_ids(conn, scope)
    try:
        from .planning_runner import plan_from_stores
        ctx = build_planning_context(app, scope)
        sts_src = ops.source_id("speed_to_sell")
        res = plan_from_stores(ctx, reader, dms_source_id=inv_src, sts_source_id=sts_src, current_month=now[:7])
        issued_count = int(res.get("issued_count", 0) or 0)
    except Exception as e:   # noqa: BLE001 — a failed recompute must never destroy the last valid board
        new_ids = _issued_plan_ids(conn, scope) - old_ids
        _supersede(conn, new_ids)
        return {"ok": False, "reason": f"Planning could not complete ({e}); the last certified board was left "
                "unchanged.", "issued_count": 0}

    new_ids = _issued_plan_ids(conn, scope) - old_ids
    if issued_count <= 0:
        _supersede(conn, new_ids)                      # roll back any partial issue; keep the last valid board
        return {"ok": False, "reason": "Planning produced no certified positions from the current snapshot "
                "(check Inventory carries model codes and Speed-to-Sell demand is loaded). The last certified "
                "board was left unchanged.", "issued_count": 0}

    _supersede(conn, old_ids)                          # atomic swap: retire the prior board now that the new one is live
    prov = {"computed_at": now, "actor": actor, "inventory_source_id": inv_src,
            "inventory_snapshot_id": snap_id, "inventory_observed_time": snap_time, "issued_count": issued_count}
    app.prefs.set_pref(f"scope::{scope}", _PROV_KEY, prov)
    return {"ok": True, "reason": f"Certified board recomputed from the current Pipeline ({issued_count} "
            "position(s)).", "issued_count": issued_count, "inventory_source_id": inv_src,
            "inventory_snapshot_id": snap_id, "computed_at": now}


def board_provenance(app, scope):
    return app.prefs.get_pref(f"scope::{scope}", _PROV_KEY, default=None)


def board_status(app, scope):
    """Compare the issued board against the current Inventory/Pipeline snapshot.

    Returns {state, detail, board_computed_at, snapshot_time}. state is:
      * 'absent'  — no issued board at all;
      * 'unknown' — an issued board exists but was not produced by this recompute path (unknown vintage);
      * 'stale'   — a newer Inventory/Pipeline snapshot exists than the one the board was derived from;
      * 'current' — the board was derived from the latest Inventory/Pipeline snapshot."""
    conn = app.stack.db.conn
    has_board = conn.execute("SELECT 1 FROM inventory_plan_result WHERE store_scope=? AND status='issued' LIMIT 1",
                             (scope,)).fetchone() is not None
    _src, snap = latest_inventory_snapshot(app, scope)
    snap_id, snap_time = _snapshot_id_time(snap) if snap is not None else (None, "")
    prov = board_provenance(app, scope)
    if not has_board:
        return {"state": "absent", "detail": "No certified planning board has been computed yet.",
                "board_computed_at": None, "snapshot_time": snap_time}
    if not prov:
        return {"state": "unknown", "detail": "The certified board's vintage is unknown — recompute it from the "
                "current Pipeline.", "board_computed_at": None, "snapshot_time": snap_time}
    board_snap_id = prov.get("inventory_snapshot_id")
    # Stale when the current latest Inventory/Pipeline snapshot is not the exact one the board was derived from:
    # a different snapshot id means a newer Pipeline has been imported since the board was computed.
    if snap is not None and snap_id != board_snap_id:
        return {"state": "stale", "detail": "The loaded Pipeline is newer than the certified board — recompute "
                "the board from the current Pipeline.", "board_computed_at": prov.get("computed_at"),
                "snapshot_time": snap_time}
    return {"state": "current", "detail": "The certified board is derived from the current Pipeline.",
            "board_computed_at": prov.get("computed_at"), "snapshot_time": snap_time}
