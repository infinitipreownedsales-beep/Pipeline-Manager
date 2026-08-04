"""Source Contract / Schema Profile evaluation.

Contracts describe *shape and meaning of source data only* — never downstream
business calculations. A row is validated against the active profile: required
fields present, values coerced/normalized, raw preserved. Snapshot capability is
a property of the contract, not of the payload's size.
"""
from __future__ import annotations

from .normalize import Special, normalize_scalar


def validate_row(profile, raw: dict):
    """Return (validation_status, normalized_dict).

    - required field missing/blank  -> 'rejected'
    - any field invalid (bad type)  -> 'quarantined' (kept, but not fact-eligible)
    - otherwise                     -> 'valid'
    Extra fields in `raw` are harmless: preserved in raw, ignored by normalization.
    Renamed required field == the required name absent -> rejected.
    """
    normalized = {}
    status = "valid"
    for fs in profile.fields:
        cell = raw.get(fs.name)                       # None when column absent
        val = normalize_scalar(cell, fs.kind)
        normalized[fs.name] = val
        if fs.required and val in (Special.MISSING, Special.BLANK):
            status = "rejected"
        elif val is Special.INVALID:
            if status != "rejected":
                status = "quarantined"
    return status, normalized


def classify_snapshot(profile, claimed: str, row_count: int) -> tuple[str, str]:
    """Return (validated_snapshot_type, note).

    A payload is only a Full Snapshot when the ACTIVE contract supports it and its
    full-snapshot requirements are declared — never merely because it has many rows.
    """
    claimed = (claimed or "partial").lower()
    if claimed == "full":
        if not profile.snapshot_capable:
            return "partial", "full-snapshot claim downgraded: source contract does not support full snapshots"
        reqs = profile.full_snapshot_requirements or {}
        if reqs.get("requires_scope") and not reqs.get("scope_declared", True):
            return "partial", "full-snapshot claim downgraded: required scope not declared"
        return "full", ""
    return "partial", ""
