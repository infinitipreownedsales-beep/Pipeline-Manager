"""Best Available Placement Candidates — an explicitly NON-economic operational shortlist.

It answers one operational question: if management requires Kyle to place N additional Service Loaners today,
which physical eligible New-Retail units are the SAFEST available candidates on currently-certified evidence?

It is NOT the economic Ideal (that stays Undetermined until Phase-4 economics exist). It ranks real physical
units using only authoritative evidence already available:
  * physical current New-Retail inventory (on-lot units, with full identity);
  * eligibility / lifecycle exclusions (already a loaner, not on-lot, being sold);
  * certified New-Retail coverage/harm from Segment 06 (a unit whose combination is over-stocked is safe to
    place; a unit whose combination is short would reduce retail coverage and is protected);
  * aging (DIS) as a secondary tiebreak.
No ICV / Velocity / write-down / lifecycle economics are invented; nothing here claims economic optimality.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..newinv.dms_identity import dms_planning_identity
from ..newinv.dms_cohort import dms_source_stage

# a unit's retail-coverage state for its combination (from the certified issued plan)
EXCESS, COVERED, SHORTAGE, UNKNOWN = "EXCESS", "COVERED", "SHORTAGE", "UNKNOWN"
_HARM_LABEL = {
    EXCESS: "over-stocked — safest to place",
    COVERED: "coverage balanced — safe to place",
    SHORTAGE: "would reduce New-Retail coverage — protected",
    UNKNOWN: "New-Retail coverage unresolved",
}
_STATE_RANK = {EXCESS: 0, COVERED: 1, UNKNOWN: 2, SHORTAGE: 3}


@dataclass(frozen=True)
class PlacementCandidate:
    stock: str
    vin: str                 # authoritative VIN only ("" when the source does not provide one)
    vin_authoritative: bool  # False -> the board must NOT present serial/stock as a VIN
    serial: str              # source Serial (lifecycle-dependent; UNKNOWN semantics — never a VIN)
    year: str
    model: str
    trim: str
    drivetrain: str
    exterior: str
    interior: str
    dis: int | None
    new_retail_state: str
    harm_label: str
    rank_reason: str
    safe: bool


def _s(v):
    return "" if v is None else str(v).strip()


def _first(row, *keys):
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _as_int(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def certified_harm_index(conn, scope):
    """combination canonical_identity -> {'state','excess','acquire'} from the certified issued plan. Read-only,
    no recompute."""
    import json
    idx = {}
    ident = {c["id"]: (c["canonical_identity"] or c["id"]) for c in conn.execute(
        "SELECT id, canonical_identity FROM sellable_combination WHERE store_scope=?", (scope,)).fetchall()}
    for r in conn.execute("SELECT * FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                          (scope,)).fetchall():
        try:
            dec = (json.loads(r["evidence"]) if r["evidence"] else {}).get("decision") or {}
        except Exception:   # noqa: BLE001
            dec = {}
        excess = int(dec.get("arrived_excess", 0) or 0)
        acquire = int(dec.get("acquire_units", 0) or 0)
        state = EXCESS if excess > 0 else (SHORTAGE if acquire > 0 else COVERED)
        idx[ident.get(r["combination_id"], r["combination_id"])] = {"state": state, "excess": excess,
                                                                    "acquire": acquire}
    return idx


# the DMS inventory can arrive under EITHER contract: the CSV `new_inventory_current`, or the xlsx
# `new_inventory_pipeline_summary` (which _run_upload maps .xlsx uploads to). The placement board must read
# whichever actually has the latest snapshot — otherwise it reports "no snapshot" while Data shows inventory
# loaded (the 4A defect).
INVENTORY_CONTRACTS = ("new_inventory_current", "new_inventory_pipeline_summary")


def read_new_retail_units(app, scope):
    """Raw per-unit rows of the latest completed New-Retail inventory snapshot, from whichever inventory
    contract has data, or [] when none / no ops orchestrator. Never fabricates units."""
    try:
        from ..ui.views.operator import _ops_stack
        from ..newinv.supply_bridge import read_latest_snapshot_rows
        ops = _ops_stack(app)
        if ops is None:
            return []
        for key in INVENTORY_CONTRACTS:
            try:
                rows = list(read_latest_snapshot_rows(ops.data, ops.source_id(key), scope) or [])
            except Exception:   # noqa: BLE001
                rows = []
            if rows:
                return rows
        return []
    except Exception:   # noqa: BLE001 — inventory availability must never break the page
        return []


def _authoritative_vin(row):
    """A VIN only when the source truly provides one. Serial is lifecycle-dependent (serial_lifecycle) and its
    semantics are UNKNOWN — it is NEVER promoted to a VIN. Returns (vin, is_authoritative, serial)."""
    vin = _first(row, "vin")
    serial = _first(row, "serial")
    stock = _first(row, "stock_number", "stock")
    # a real VIN is 17 chars and distinct from stock/serial; anything else is not trustworthy as a VIN
    ok = bool(vin) and len(vin) == 17 and vin not in (serial, stock)
    return (vin if ok else "", ok, serial)


def _to_candidate(row, harm_index):
    model_code = _first(row, "model_code")
    ext = _first(row, "exterior", "exterior_code", "ext")
    inte = _first(row, "interior", "interior_code", "int")
    combo = dms_planning_identity({"model_code": model_code, "exterior": ext, "interior": inte})
    harm = harm_index.get(combo)
    state = harm["state"] if harm else UNKNOWN
    dis = _as_int(_first(row, "dis", "days_in_stock"))
    reason = _HARM_LABEL[state] + (f" · {dis}d in stock" if dis is not None else "")
    vin, vin_ok, serial = _authoritative_vin(row)
    return PlacementCandidate(
        stock=_first(row, "stock_number", "stock"), vin=vin, vin_authoritative=vin_ok, serial=serial,
        year=_first(row, "year", "model_year", "my"), model=_first(row, "model", "model_line") or model_code,
        trim=_first(row, "trim", "trim_desc", "description"), drivetrain=_first(row, "drivetrain", "drive"),
        exterior=ext, interior=inte, dis=dis, new_retail_state=state, harm_label=_HARM_LABEL[state],
        rank_reason=reason, safe=(state in (EXCESS, COVERED)))


def _eligible(row, loaner_vins):
    stage = dms_source_stage(row)                       # DLR-INV = physically on the lot now
    if stage != "DLR-INV":
        return False
    status = _first(row, "status").lower()
    if "sold" in status or "delivered" in status:       # already leaving retail — not eligible
        return False
    vin, ok, _serial = _authoritative_vin(row)
    return not (ok and vin in loaner_vins)               # exclude committed loaners by AUTHORITATIVE VIN only


def best_available_placement(app, conn, scope, *, n, loaner_vins=frozenset()):
    """Return the operational placement shortlist:
        {"candidates": [best N safe], "next_best": [2-3 more], "protected": <#shortage excluded>,
         "unresolved": <# coverage-unresolved>, "eligible": <# eligible on-lot>, "loaded": bool}.
    Safe candidates are ranked over-stocked-first, then oldest-aging-first; short-combination units are
    protected (never offered) to avoid harming certified New-Retail coverage."""
    rows = read_new_retail_units(app, scope)
    harm_index = certified_harm_index(conn, scope)
    cands = [_to_candidate(r, harm_index) for r in rows if _eligible(r, set(loaner_vins))]
    safe = [c for c in cands if c.safe]
    safe.sort(key=lambda c: (_STATE_RANK[c.new_retail_state], -(c.dis or 0), c.stock))
    protected = sum(1 for c in cands if c.new_retail_state == SHORTAGE)
    unresolved = sum(1 for c in cands if c.new_retail_state == UNKNOWN)
    n = max(0, int(n or 0))
    return {"candidates": safe[:n], "next_best": safe[n:n + 3], "protected": protected,
            "unresolved": unresolved, "eligible": len(cands), "loaded": bool(rows)}
