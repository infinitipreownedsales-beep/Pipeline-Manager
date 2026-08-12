"""Phase 11 operational record constants + lightweight record helpers.

These are OPERATIONAL descriptors — how data moved and was reviewed — never business truth.
"""
from __future__ import annotations

# ---- import-run state machine -------------------------------------------------
IMPORT_STATES = [
    "RECEIVED", "VALIDATING", "VALIDATED", "REJECTED", "INGESTING", "INGESTED",
    "RECONCILING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "CANCELLED", "SUPERSEDED",
]
# terminal states never transition further
IMPORT_TERMINAL = {"COMPLETED", "COMPLETED_WITH_WARNINGS", "REJECTED", "FAILED", "CANCELLED", "SUPERSEDED"}
# states that mean facts were accepted into the authoritative store
IMPORT_ACCEPTED = {"INGESTED", "RECONCILING", "COMPLETED", "COMPLETED_WITH_WARNINGS"}

# ---- freshness statuses -------------------------------------------------------
FRESHNESS_STATUSES = ["CURRENT", "AGING", "STALE", "MISSING", "FAILED", "CONFLICTING", "UNRESOLVED"]

# ---- operational reconciliation / drift outcomes ------------------------------
RECON_OUTCOMES = [
    "MATCHED", "NEW", "CHANGED", "MISSING_EXPECTED", "EXTRA", "DUPLICATE",
    "IDENTITY_UNRESOLVED", "CONFLICTING", "STALE", "LEGACY_DIFFERENCE", "UNRESOLVED",
]

# ---- parallel-run comparison classifications ----------------------------------
COMPARISON_CLASSES = [
    "MATCH", "DATA_DIFFERENCE", "TIMING_DIFFERENCE", "IDENTITY_DIFFERENCE", "POLICY_DIFFERENCE",
    "CALCULATION_DIFFERENCE", "LEGACY_LIMITATION", "ELITE_LIMITATION", "UNRESOLVED",
]
# unresolved / material differences that block readiness until reviewed
COMPARISON_MATERIAL = {"DATA_DIFFERENCE", "IDENTITY_DIFFERENCE", "POLICY_DIFFERENCE",
                       "CALCULATION_DIFFERENCE", "UNRESOLVED"}

# ---- health-check kinds -------------------------------------------------------
HEALTH_KINDS = ["liveness", "readiness", "operational"]

# ---- readiness classifications ------------------------------------------------
READY = "READY"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
NOT_READY = "NOT_READY"

# ---- scheduled-job kinds ------------------------------------------------------
JOB_KINDS = [
    "source_import", "freshness_check", "expiration_sweep", "stale_recommendation_check",
    "calibration_activation_check", "zero_mile_monitoring", "health_check", "backup", "pilot_comparison",
]

# ---- Phase 11 capabilities (below-UI authorization; no second permission store) ----
CAPS = {
    "IMPORT_RUN": "ops.import.run",
    "FILE_UPLOAD": "ops.file.upload",
    "SCHEDULE_MANAGE": "ops.schedule.manage",
    "BACKUP_RUN": "ops.backup.run",
    "PILOT_COMPARE": "ops.pilot.compare",
    "PILOT_REVIEW": "ops.pilot.review",
    "PILOT_CERTIFY": "ops.pilot.certify",
    "FEEDBACK_SUBMIT": "ops.feedback.submit",
    "FEEDBACK_TRIAGE": "ops.feedback.triage",
}

# ---- controlled file intake policy defaults -----------------------------------
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt", ".json", ".xlsx"}   # incl. native DMS workbook exports
DISALLOWED_EXTENSIONS = {".exe", ".sh", ".bat", ".dll", ".so", ".bin", ".py", ".js", ".php"}
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024                 # 25 MiB
