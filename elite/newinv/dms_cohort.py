"""Source-grounded DMS cohort key for longitudinal inventory memory (ratified initial key).

Groups `vehicleInventorySummary` observations into planning cohorts using ONLY stable source configuration
dimensions — model, model year, model code, exterior, interior. This deliberately does NOT depend on a
Model Code -> trim/drivetrain decoder (none is invented); the raw source configuration IS the cohort
identity for now, and it can later map into the newinv canonical combination system without a decode table.

Volatile / temporal / economic attributes (Stock#, Serial, Status, Location, DIS, ETA, Production Month,
MSRP, Invoice) are excluded from identity — they are exactly what the snapshot delta engine measures across
time, never what defines the cohort. Description and Transmission are retained on the row for
display/corroboration only. Unknown/blank values are preserved DISTINCTLY (a blank never collapses into a
real value), matching the canonical-combination normalization convention (`elite/newinv/combination.py`).
"""
from __future__ import annotations

from ..data.normalize import Special

# Canonical DMS cohort identity dimensions, in order. These are the header-aliased canonical field names
# produced by the new_inventory_pipeline_summary adapter (MY->model_year, Ext->ext, Int->int, ...).
COHORT_DIMS = ("model", "model_year", "model_code", "ext", "int")

# Explicitly NON-identity attributes (observation / temporal / economic). Retained on the row, never keyed.
NON_COHORT_FIELDS = ("stock_number", "serial", "serial_semantic", "status", "location",
                     "dis", "eta", "production_month", "msrp", "inv", "description", "trans")


def _norm(v):
    """Normalize a cohort dimension value. Unknown/blank stay distinct (never blank==a known value)."""
    if v is None:
        return "∅"                       # ∅ : absent
    if isinstance(v, Special):
        return f"«{v.name.lower()}»"  # «unknown»/«blank»/«na» stay distinct, never a value
    s = str(v).strip()
    return s.upper() if s else "∅"


# For vehicleInventorySummary the inventory PIPELINE STATE (incoming vs arrived) is carried by the
# Location column (aliased to `location`), NOT by Status. Status holds an operational deal state such as
# "Deal Opened" and must never be substituted for the pipeline state. This is a source-specific rule; other
# contracts are unaffected (this classifier is only applied to vehicleInventorySummary snapshots).
INVENTORY_STATE_FIELD = "location"


def classify_inventory_state(value):
    """Classify a raw pipeline-state value into ONS (incoming) / DLR-INV (arrived dealer inventory) / OTHER.
    Case/space-insensitive; unknown/blank -> OTHER."""
    if isinstance(value, Special):
        return "OTHER"
    s = (str(value).strip().upper() if value is not None else "")
    if s == "ONS":
        return "ONS"
    if s == "DLR-INV":
        return "DLR-INV"
    return "OTHER"


def dms_inventory_state(row):
    """Inventory pipeline state for a vehicleInventorySummary row — read from Location, never Status."""
    return classify_inventory_state(row.get(INVENTORY_STATE_FIELD))


def dms_cohort_key(row):
    """Return the canonical DMS cohort key tuple for a source row (raw_values or normalized dict)."""
    return tuple(_norm(row.get(d)) for d in COHORT_DIMS)


def dms_cohort_label(row):
    """A stable human label for a cohort (display/corroboration only; not identity)."""
    m, my, mc, ex, it = (dms_cohort_key(row))
    return f"{m} MY{my} {mc} {ex}/{it}"
