"""Phase 12 constants for live integration, migration, validation, and release."""
from __future__ import annotations

# ---- live-source classifications ---------------------------------------------
SOURCE_CLASSES = ["MANUAL_GOVERNED", "FILE_EXPORT", "API_AVAILABLE", "ACCESS_PENDING",
                  "UNAVAILABLE", "OUT_OF_SCOPE"]
# classes that can actually feed a real import
SOURCE_INGESTIBLE = {"MANUAL_GOVERNED", "FILE_EXPORT", "API_AVAILABLE"}

# ---- identity-migration outcomes ---------------------------------------------
IDENTITY_OUTCOMES = ["MATCHED_EXISTING", "CREATED_CANONICAL", "ALIAS_LINKED", "PREVIN_LINKED_TO_VIN",
                     "DUPLICATE_RECONCILED", "CONFLICTING_IDENTITY", "UNRESOLVED_IDENTITY",
                     "EXCLUDED_INVALID", "CORRECTION_REQUIRED"]
IDENTITY_BLOCKING = {"CONFLICTING_IDENTITY", "UNRESOLVED_IDENTITY", "CORRECTION_REQUIRED"}

# ---- shadow-mode domain states -----------------------------------------------
SHADOW_MODES = ["DATA_ONLY", "CALCULATE_ONLY", "REVIEW_ONLY", "DECISION_PILOT",
                "EXECUTION_PILOT", "CUTOVER_ELIGIBLE", "BLOCKED"]
# only these permit real execution behind pilot actions
SHADOW_EXECUTION_ENABLED = {"EXECUTION_PILOT", "CUTOVER_ELIGIBLE"}

# ---- discrepancy statuses ----------------------------------------------------
DISCREPANCY_STATUSES = ["OPEN", "TRIAGED", "DATA_CORRECTION_REQUIRED", "IDENTITY_CORRECTION_REQUIRED",
                        "POLICY_REVIEW_REQUIRED", "ELITE_DEFECT_CONFIRMED", "LEGACY_LIMITATION_CONFIRMED",
                        "EXPECTED_DIFFERENCE", "ACCEPTED_WITH_WARNING", "RESOLVED", "BLOCKING", "CLOSED"]
# statuses that block affected-domain readiness while open
DISCREPANCY_BLOCKING = {"OPEN", "TRIAGED", "DATA_CORRECTION_REQUIRED", "IDENTITY_CORRECTION_REQUIRED",
                        "POLICY_REVIEW_REQUIRED", "ELITE_DEFECT_CONFIRMED", "BLOCKING"}
DISCREPANCY_CLOSED = {"EXPECTED_DIFFERENCE", "ACCEPTED_WITH_WARNING", "RESOLVED",
                      "LEGACY_LIMITATION_CONFIRMED", "CLOSED"}

# ---- parallel-comparison classifications (reuse Phase 11 vocabulary) ---------
PARALLEL_CLASSES = ["MATCH", "DATA_DIFFERENCE", "TIMING_DIFFERENCE", "IDENTITY_DIFFERENCE",
                    "POLICY_DIFFERENCE", "CALCULATION_DIFFERENCE", "ELITE_DEFECT", "LEGACY_LIMITATION",
                    "EXPECTED_DIFFERENCE", "UNRESOLVED"]
PARALLEL_MATERIAL = {"DATA_DIFFERENCE", "IDENTITY_DIFFERENCE", "POLICY_DIFFERENCE",
                     "CALCULATION_DIFFERENCE", "ELITE_DEFECT", "UNRESOLVED"}

# ---- UAT outcomes ------------------------------------------------------------
UAT_OUTCOMES = ["pass", "fail", "block"]

# ---- final-readiness dimensions + statuses -----------------------------------
DIMENSIONS = ["ENGINEERING_READY", "DATA_READY", "POLICY_READY", "AUTHORITY_READY", "OPERATOR_READY",
              "MIGRATION_READY", "ROLLBACK_READY", "SECURITY_READY", "OPERATIONALLY_READY",
              "GO_LIVE_AUTHORIZED"]
DIMENSION_STATUSES = ["PASS", "PASS_WITH_WARNINGS", "FAIL", "UNRESOLVED", "NOT_APPLICABLE"]
DIMENSION_OK = {"PASS", "PASS_WITH_WARNINGS", "NOT_APPLICABLE"}
# prior dimensions that OPERATIONALLY_READY depends on
OPERATIONAL_PREREQS = ["ENGINEERING_READY", "DATA_READY", "POLICY_READY", "AUTHORITY_READY",
                       "OPERATOR_READY", "MIGRATION_READY", "ROLLBACK_READY", "SECURITY_READY"]

# ---- release-authorization dispositions --------------------------------------
AUTH_DISPOSITIONS = ["AUTHORIZE_GO_LIVE", "AUTHORIZE_LIMITED_DOMAIN_GO_LIVE", "CONTINUE_PARALLEL_RUN",
                     "DEFER", "REJECT", "ROLLBACK_REQUIRED"]

# ---- final release recommendations -------------------------------------------
RELEASE_RECOMMENDATIONS = ["READY_FOR_EXPLICIT_GO_LIVE_AUTHORIZATION",
                           "READY_FOR_LIMITED_DOMAIN_AUTHORIZATION", "CONTINUE_PARALLEL_PILOT", "NOT_READY"]

# ---- Phase 12 capabilities (below-UI authorization; no second permission store) ----
CAPS = {
    "MIGRATE_RUN": "release.migrate.run",
    "IDENTITY_RESOLVE": "release.identity.resolve",
    "POLICY_MIGRATE": "release.policy.migrate",
    "AUTHORITY_MIGRATE": "release.authority.migrate",
    "SHADOW_SET": "release.shadow.set",
    "EXECUTE_LIVE": "release.execute.live",
    "PARALLEL_RUN": "release.parallel.run",
    "DISCREPANCY_REVIEW": "release.discrepancy.review",
    "UAT_RECORD": "release.uat.record",
    "REHEARSE": "release.rehearse",
    "PACKAGE_ISSUE": "release.package.issue",
    "CERTIFY": "release.certify",
    "AUTHORIZE_RELEASE": "release.authorize",
}
