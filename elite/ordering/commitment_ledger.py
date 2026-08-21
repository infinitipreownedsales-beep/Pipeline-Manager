"""CPO session commitments ↔ authoritative Production Order reconciliation.

When Kyle confirms an ORDER during a CPO session, that is a SHADOW future-supply commitment (planning only —
no source mutation). Later, the authoritative Production Orders arrive by upload. This module reconciles the
two so a confirmed order is never counted twice, using the strongest deterministic identifier available and
NEVER silently merging ambiguous records.

States:
  * MATCHED    — a production order deterministically covers a session commitment; it counts ONCE.
  * UNMATCHED  — a production order with no prior session commitment (authoritative supply on its own).
  * AMBIGUOUS  — a production order that could cover more than one commitment; surfaced, never merged.

Reconciliation is a pure function keyed by manufacturer_order_id, so re-importing the same orders is
idempotent. No certified state is changed; no schema change.
"""
from __future__ import annotations

from ..newinv.dms_identity import dms_planning_identity


def commitments_from_lines(lines, qty, board):
    """Derive session commitments {combo: {'model':..., 'qty':...}} from the CPO line state. A fully-confirmed
    combo commits its certified ORDER quantity; a partial commits exactly the k recorded. `board` maps
    combo -> {'model','order'}."""
    out = {}
    for combo, meta in board.items():
        order = int(meta.get("order", 0) or 0)
        st = lines.get(combo)
        if st == "confirmed":
            n = order
        elif st == "not_ordered":
            n = 0
        else:
            k = int((qty or {}).get(combo, 0) or 0)
            n = k if 0 < k < order else 0
        if n > 0:
            out[combo] = {"model": (meta.get("model") or "").upper(), "qty": n}
    return out


def _row_combo(row):
    """A production-order row's planning combo identity when it carries model_code + colors, else None (only a
    model-level match is possible, which is treated as ambiguous when it spans multiple commitments)."""
    mc = row.get("model_code") if isinstance(row, dict) else None
    ext = row.get("exterior") or row.get("exterior_code") if isinstance(row, dict) else None
    inte = row.get("interior") or row.get("interior_code") if isinstance(row, dict) else None
    if mc and ext and inte:
        return dms_planning_identity({"model_code": mc, "exterior": ext, "interior": inte})
    return None


def reconcile_commitments(commitments, production_rows):
    """Pure reconciliation. `commitments`: {combo: {'model','qty'}}. Returns matched/unmatched/ambiguous lists
    and the remaining uncovered shadow quantity per combo. Idempotent: keyed by manufacturer_order_id, each
    order processed once; the same input always yields the same result."""
    remaining = {c: int(v.get("qty", 0) or 0) for c, v in commitments.items()}
    model_of = {c: (v.get("model") or "").upper() for c, v in commitments.items()}
    matched, unmatched, ambiguous, seen = [], [], [], set()
    for row in production_rows or []:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("manufacturer_order_id") or row.get("vin") or "").strip()
        if oid and oid in seen:
            continue                                    # idempotent: an order id reconciles at most once
        if oid:
            seen.add(oid)
        model = str(row.get("model") or "").strip().upper()
        combo = _row_combo(row)
        if combo is not None and combo in remaining and remaining[combo] > 0:
            remaining[combo] -= 1                       # deterministic combo match -> counts once
            matched.append({"order_id": oid, "combo": combo, "model": model, "basis": "combination"})
            continue
        # no exact-combo match: a model-only signal is AMBIGUOUS when >1 open commitment shares the model
        model_combos = [c for c, m in model_of.items() if m == model and remaining.get(c, 0) > 0]
        if len(model_combos) == 1:
            c = model_combos[0]
            remaining[c] -= 1
            matched.append({"order_id": oid, "combo": c, "model": model, "basis": "model (sole open commitment)"})
        elif len(model_combos) > 1:
            ambiguous.append({"order_id": oid, "model": model, "candidates": list(model_combos)})
        else:
            unmatched.append({"order_id": oid, "model": model, "combo": combo})
    return {"matched": matched, "unmatched": unmatched, "ambiguous": ambiguous,
            "remaining_shadow": {c: n for c, n in remaining.items() if n > 0},
            "shadow_covered": sum(int(v.get("qty", 0) or 0) for v in commitments.values())
                              - sum(remaining.values())}
