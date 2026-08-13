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


# For vehicleInventorySummary the inventory PIPELINE STAGE is carried by the Location column (aliased to
# `location`), NOT by Status. Status holds an operational deal state such as "Deal Opened" and must never be
# substituted for the pipeline stage. This is a source-specific rule; other contracts are unaffected.
#
# Two ratified levels are modelled (the exact source stage is always preserved verbatim; the planning state
# is a SEPARATE, coarser derivation):
#   SOURCE STAGE  (exact, distinct supply-stage evidence):
#     ONS      = on-order pipeline
#     SIT      = Sea In Transit (overseas / on the water)
#     NNA-INV  = in INFINITI/NNA U.S. inventory, awaiting shipment to dealer (already stateside)
#     DLR-INV  = arrived at the dealership
#     OTHER    = any Location not yet authoritatively defined
#   PLANNING STATE (derived planning bucket):
#     INCOMING = ONS + SIT + NNA-INV
#     ARRIVED  = DLR-INV
#     OTHER    = undefined stages only
# The distinction matters: SIT is a materially earlier supply signal than NNA-INV (still overseas vs already
# in the U.S.), and only DLR-INV is physically arrived (the sole bucket that drives dealer DIS aging).
INVENTORY_STATE_FIELD = "location"

SOURCE_STAGES = ("ONS", "SIT", "NNA-INV", "DLR-INV", "OTHER")
INCOMING_STAGES = ("ONS", "SIT", "NNA-INV")
ARRIVED_STAGES = ("DLR-INV",)
_DEFINED = ("ONS", "SIT", "NNA-INV", "DLR-INV")


def classify_source_stage(value):
    """Classify a raw Location value into its EXACT source stage (ONS / SIT / NNA-INV / DLR-INV / OTHER).
    Case/space-insensitive; unknown/blank/undefined -> OTHER. The exact stage is never collapsed."""
    if isinstance(value, Special):
        return "OTHER"
    s = (str(value).strip().upper() if value is not None else "")
    return s if s in _DEFINED else "OTHER"


def planning_state_of(stage):
    """Derive the coarser planning bucket from an exact source stage."""
    if stage in ARRIVED_STAGES:
        return "ARRIVED"
    if stage in INCOMING_STAGES:
        return "INCOMING"
    return "OTHER"


def dms_source_stage(row):
    """Exact preserved source stage for a vehicleInventorySummary row — read from Location, never Status."""
    return classify_source_stage(row.get(INVENTORY_STATE_FIELD))


def dms_planning_state(row):
    """Derived planning bucket (INCOMING / ARRIVED / OTHER) for a vehicleInventorySummary row."""
    return planning_state_of(dms_source_stage(row))


def dms_cohort_key(row):
    """Return the canonical DMS cohort key tuple for a source row (raw_values or normalized dict)."""
    return tuple(_norm(row.get(d)) for d in COHORT_DIMS)


def dms_cohort_label(row):
    """A stable human label for a cohort (display/corroboration only; not identity)."""
    m, my, mc, ex, it = (dms_cohort_key(row))
    return f"{m} MY{my} {mc} {ex}/{it}"
