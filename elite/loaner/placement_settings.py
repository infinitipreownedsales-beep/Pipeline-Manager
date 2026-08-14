"""Temporary monthly Service-Loaner placement requirement (dealer / OEM objective).

A first-class, TEMPORARY operator input stored in the governed metadata store (no schema change). It carries
the effective month, the required placement count (and/or additional placements), an optional reason, and an
objective-driven flag. It EXPIRES: a requirement set for one month is never silently inherited by the next —
`resolve` returns None unless the stored requirement's effective month matches the month being planned. This
keeps an externally-required, month-scoped objective from contaminating later unconstrained economic learning.
"""
from __future__ import annotations

import json

_KEY = "loaner_placement_requirement"


def set_requirement(metadata_store, *, effective_month, required=None, additional=None, reason="",
                    objective_driven=True):
    """Set the month-scoped placement requirement. `effective_month` = 'YYYY-MM'."""
    payload = {"effective_month": effective_month,
               "required": (int(required) if required is not None else None),
               "additional": (int(additional) if additional is not None else None),
               "reason": reason or "", "objective_driven": bool(objective_driven)}
    metadata_store.put(_KEY, json.dumps(payload))
    return payload


def clear_requirement(metadata_store):
    metadata_store.put(_KEY, "")


def resolve(metadata_store, planning_month):
    """The requirement IN FORCE for `planning_month`, or None. Expires automatically: a stored requirement for
    a different month does not apply (it is not inherited)."""
    if metadata_store is None:
        return None
    try:
        raw = metadata_store.get(_KEY)
    except Exception:   # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        p = json.loads(raw)
    except Exception:   # noqa: BLE001
        return None
    if p.get("effective_month") != planning_month:
        return None                              # expired / not for this month -> never inherited
    return p
