"""Upload-resolution hook — the ongoing maintenance loop (Slice A).

When any source file is ingested, its identity-bearing tokens (model/order code, exterior, interior, and any
trim/drivetrain/package columns) are recorded as immutable raw observations. Vocabulary already approved in the
Translation Center resolves automatically and silently; genuinely-new raw values are preserved and surface as
`unresolved` for an authorized person to name once — after which every future upload reuses that mapping with
no code. This does NOT interpret family / generation / preferred-order (that stays governed and is not wired to
CPO here); it only records observations and computes what still needs human resolution.
"""
from __future__ import annotations

# semantic type -> the raw_values keys a source might use for it (franchise/source-agnostic aliases).
IDENTITY_COLUMNS = {
    "model_code": ("model_code",),
    "exterior": ("exterior", "exterior_code", "ext", "exterior_color"),
    "interior": ("interior", "interior_code", "int", "interior_color"),
    "trim": ("trim", "trim_level", "trim_desc"),
    "drivetrain": ("drivetrain", "drive"),
    "package": ("package", "factory_option", "factory_options"),
}


def _val(row, aliases):
    for a in aliases:
        v = row.get(a)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def observe_source_rows(store, source_system, rows, *, as_of, proof_ref, actor="system"):
    """Record identity observations from ingested rows. Returns a summary distinguishing what resolved
    automatically from what is genuinely new:
        {"recorded": <unique tokens seen>, "auto_resolved": <count>, "new_unresolved": [(type, raw), ...]}.
    Idempotent at the observation layer (record_observation refreshes rather than duplicates)."""
    recorded = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for stype, aliases in IDENTITY_COLUMNS.items():
            raw = _val(row, aliases)
            if not raw:
                continue
            key = (source_system, stype, raw)
            if key in recorded:
                continue
            recorded.add(key)
            store.record_observation(source_system, stype, raw, as_of=as_of, proof_ref=proof_ref, actor=actor)
    # what of THIS batch still has no interpretation (authoritative queue, same rule as Data Health)
    unresolved = {(o["source_system"], o["semantic_type"], o["raw_value"]) for o in store.unresolved_translations()}
    new = sorted((stype, raw) for (src, stype, raw) in recorded if (src, stype, raw) in unresolved)
    return {"recorded": len(recorded), "auto_resolved": len(recorded) - len(new), "new_unresolved": new}
