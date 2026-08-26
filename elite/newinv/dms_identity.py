"""DMS planning identity — the year-agnostic, model_code-preserving cohort used to JOIN real Speed-to-Sell
demand to DMS-snapshot supply, without decoding trim/drivetrain and without semantic lying.

Two identity granularities exist deliberately:
  * SUPPLY (snapshot longitudinal memory, `dms_cohort.py`): (model, model_year, model_code, ext, int) — keeps
    MY so MY2026 vs MY2027 supply is tracked distinctly.
  * PLANNING (here): (model, model_code[4-digit], ext, int) — YEAR-AGNOSTIC, because a configuration's sell
    rate is not a property of model year: historical demand for a config must carry forward into whichever MY
    is currently orderable. Model year is a supply/plan attribute, never a demand-cohort dimension.

The planning key is the dealership-proven legacy config key `Model|Code|Ext|Int`. The small code/interior
normalizations below are ported verbatim (in meaning) from the legacy Speed-to-Sell engine
(`pipeline_manager/keys.py`) so real supply and real demand resolve to identical keys:
  * inventory codes are 5-digit (5th digit = model year) and reduce to their 4-digit matching form;
  * QX80 Sport 834x consolidates to 8381; QX60 8461 (Autograph FWD, discontinued) folds into 8481;
  * QX80 Sport (8381) consolidates the G and D interiors into a single D key.
model is DERIVED from the code prefix (not free-text Model), so a "QX60 SPORT" vs "QX60 SPORT AWD" text
discrepancy on the same code never fragments the cohort. model_code is preserved literally in the identity
string AND in truthful `lineage_metadata`; trim and drivetrain remain genuinely unknown (never fabricated).
"""
from __future__ import annotations

from ..ids import new_id
from .models import SellableCombination

# Model line from the first two digits of the (4- or 5-digit) model code (legacy _PREFIX_TO_MODEL).
# QX80 spans two code generations: the prior 83xxx and the CURRENT 86xxx generation. Both are truthfully
# QX80 the model LINE; they remain DISTINCT planning codes (8611/8621/8631/8661 vs 8331/8381) — recognizing
# 86 as QX80 does NOT merge current 86-gen demand into historical 83-gen demand (see normalize_code, which
# only consolidates 834x within the 83 generation and never crosses 83↔86). Cross-generation demand sharing,
# if ever wanted, stays a governed lineage decision, never this silent prefix map.
_PREFIX_TO_MODEL = {"81": "QX50", "82": "QX55", "83": "QX80", "84": "QX60", "85": "QX65", "86": "QX80"}


def digits_only(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        value = int(value)
    return "".join(ch for ch in str(value).strip() if ch.isdigit())


def model_from_code(code) -> str:
    d = digits_only(code)
    return _PREFIX_TO_MODEL.get(d[:2], "") if len(d) >= 2 else ""


def code4(code) -> str:
    """Reduce a raw model code to its 4-digit matching form (drops the 5th model-year digit on inventory)."""
    d = digits_only(code)
    return d[:4] if len(d) >= 4 else d


def normalize_code(model: str, raw_code) -> str:
    d = digits_only(raw_code)
    if model == "QX80" and d[:3] == "834":
        return "8381"
    if model == "QX60" and d[:4] == "8461":
        return "8481"
    return code4(raw_code)


def normalize_int(model: str, code: str, interior) -> str:
    interior = (str(interior).strip() if interior is not None else "")
    if model == "QX80" and code == "8381" and interior in ("G", "D"):
        return "D"
    return interior


def dms_planning_components(row) -> dict:
    """Derive the year-agnostic planning components from a row carrying model_code + exterior + interior.

    Returns model (from code), model_code (normalized 4-digit), exterior, interior (normalized), plus the raw
    model_code for provenance. model_code is the discriminator; model is determined by it. Unknowns stay ''."""
    raw_code = row.get("model_code")
    model = model_from_code(raw_code)
    code = normalize_code(model, raw_code)
    ext = (str(row.get("exterior") if row.get("exterior") is not None else row.get("ext") or "").strip())
    interior = normalize_int(model, code, row.get("interior") if row.get("interior") is not None else row.get("int"))
    return {"model": model, "model_code": code, "exterior": ext.upper(), "interior": interior.upper(),
            "raw_model_code": digits_only(raw_code)}


def dms_planning_key(row) -> tuple:
    """Canonical year-agnostic planning key tuple: (model, model_code[4], exterior, interior)."""
    c = dms_planning_components(row)
    return (c["model"], c["model_code"], c["exterior"], c["interior"])


def dms_planning_identity(row) -> str:
    """A source-grounded, explicitly-labeled canonical identity string. model_code appears as itself — never
    as trim. Resolvable, deterministic, and identical for supply and demand rows of the same cohort."""
    m, code, ext, interior = dms_planning_key(row)
    return f"dms_planning|model={m or '∅'}|model_code={code or '∅'}|exterior={ext or '∅'}|interior={interior or '∅'}"


def resolve_or_create_planning_combination(store, clock, row, scope, *, source_ref=None):
    """Return the SellableCombination for this row's year-agnostic planning cohort in `scope`, creating it if
    new. model_code is preserved literally in the identity + lineage_metadata; trim/drivetrain stay unknown;
    model_year is None (year-agnostic). Distinct model_codes never collapse."""
    c = dms_planning_components(row)
    if not c["model_code"]:
        return None                                   # cannot place a row with no usable model code
    ident = dms_planning_identity(row)
    existing = store.find_combination_by_identity(ident, scope)
    if existing is not None:
        return existing
    comb = SellableCombination(
        id=new_id("comb"), store_scope=scope, model=c["model"] or "UNKNOWN",
        canonical_identity=ident, franchise="INFINITI",
        model_year=None,                              # year-agnostic planning cohort
        trim=None, drivetrain=None,                   # genuinely unknown — never fabricated / decoded
        exterior_color=c["exterior"] or None, interior_color=c["interior"] or None,
        source_refs=[source_ref] if source_ref else [], quality_status="ok",
        lineage_metadata={"identity_kind": "dms_planning_year_agnostic", "model_code": c["model_code"],
                          "raw_model_code": c["raw_model_code"], "trim": "unknown", "drivetrain": "unknown"})
    store.add_combination(comb)
    return comb
