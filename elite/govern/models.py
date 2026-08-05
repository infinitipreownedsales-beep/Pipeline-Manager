"""Phase 9 governance constants + record types. Storage is JSON-in-SQLite behind repositories.

Records reference authoritative domain output; the workspace state SUMMARIZES operational control and
never replaces a domain lifecycle.
"""
from __future__ import annotations

# Decision Workspace states — operational-control summary only.
WORKSPACE_STATES = (
    "OPEN", "READY_FOR_REVIEW", "UNDER_REVIEW", "AWAITING_INFORMATION", "UNRESOLVED", "RECOMMENDED",
    "DECISION_PENDING", "DECIDED", "APPROVED", "REJECTED", "DEFERRED", "AWAITING_EXECUTION",
    "IN_EXECUTION", "COMPLETED", "FAILED", "EXPIRED", "STALE", "SUPERSEDED", "CORRECTED", "CANCELLED",
)

# Decision dispositions.
DISPOSITIONS = ("ACCEPT", "REJECT", "DEFER", "REQUEST_INFORMATION", "NO_ACTION", "OVERRIDE", "CANCEL",
                "CORRECT", "SUPERSEDE")

# Decision-to-execution reconciliation outcomes.
RECONCILIATION_OUTCOMES = (
    "NO_EXECUTION_REQUIRED", "AWAITING_APPROVAL", "APPROVED_AWAITING_EXECUTION", "EXECUTION_AUTHORIZED",
    "EXECUTED", "COMPLETED", "FAILED", "CANCELLED", "EXPIRED", "STALE", "ALREADY_RECONCILED",
    "UNRESOLVED_IDENTITY", "CONFLICTING", "DOMAIN_REJECTED", "AUDIT_BLOCKED",
)

# Scenario administration states.
SCENARIO_STATES = (
    "DRAFT", "READY", "SHARED", "UNDER_REVIEW", "APPROVED_FOR_DISCUSSION", "PROMOTION_REQUESTED",
    "POLICY_REVIEW_REQUESTED", "REJECTED", "EXPIRED", "ARCHIVED", "SUPERSEDED", "CORRECTED",
)
SCENARIO_TRANSITIONS = {
    "DRAFT": {"READY", "SHARED", "REJECTED", "CORRECTED", "ARCHIVED"},
    "READY": {"SHARED", "UNDER_REVIEW", "REJECTED", "CORRECTED", "ARCHIVED", "EXPIRED"},
    "SHARED": {"UNDER_REVIEW", "APPROVED_FOR_DISCUSSION", "REJECTED", "CORRECTED", "ARCHIVED", "EXPIRED"},
    "UNDER_REVIEW": {"APPROVED_FOR_DISCUSSION", "REJECTED", "CORRECTED", "ARCHIVED", "EXPIRED"},
    "APPROVED_FOR_DISCUSSION": {"PROMOTION_REQUESTED", "POLICY_REVIEW_REQUESTED", "ARCHIVED", "EXPIRED",
                                "CORRECTED"},
    "PROMOTION_REQUESTED": {"REJECTED", "ARCHIVED", "SUPERSEDED", "CORRECTED"},
    "POLICY_REVIEW_REQUESTED": {"REJECTED", "ARCHIVED", "SUPERSEDED", "CORRECTED"},
    "REJECTED": set(), "EXPIRED": set(), "ARCHIVED": set(), "SUPERSEDED": set(), "CORRECTED": set(),
}

# Promotion-request targets → the governed review type they must route to.
PROMOTION_TARGETS = {
    "official_policy_review": "policy_review",
    "calculation_version_review": "calibration",
    "model_version_review": "calibration",
    "comparison_specification_review": "calibration",
    "operational_decision": "official_decision",
    "portfolio_requirement_review": "policy_review",
    "monitoring_threshold_review": "policy_review",
}

# Separation-of-duties rule types.
SOD_RULE_TYPES = (
    "proposer_not_approver", "approver_not_executor", "executor_not_completer",
    "calibration_proposer_not_activator", "policy_proposer_not_approver",
    "correction_actor_differs", "self_approval_prohibited_above_materiality",
)

READINESS_CLASSES = ("READY", "READY_WITH_WARNINGS", "NOT_READY", "UNRESOLVED", "CONFLICTING")

READINESS_DOMAINS = ("new_inventory", "production_workflows", "service_loaner", "executive_demo",
                     "learning_calibration", "governance_foundation")

# Governance capabilities.
CAPS = (
    "workspace.view", "workspace.review", "decision.issue", "decision.approve", "decision.reject",
    "decision.defer", "decision.override", "decision.correct", "decision.supersede", "decision.acknowledge",
    "execution.authorize", "execution.review", "scenario.create", "scenario.share", "scenario.review",
    "scenario.promote", "scenario.policy_review_request", "calibration.workspace.review", "authority.view",
    "authority.grant", "authority.delegate", "authority.revoke", "authority.override_separation",
    "audit.view", "audit.exception.review", "readiness.assess", "readiness.approve",
)

# Exception / unresolved queues.
EXCEPTION_QUEUES = (
    "unresolved_identity", "conflicting_facts", "missing_policy", "conflicting_policy",
    "stale_recommendation", "expired_approval", "failed_execution", "reconciliation_conflict",
    "audit_failure", "missing_observation", "ambiguous_pairing", "conflicting_learning_signal",
    "calibration_validation_regression", "scenario_promotion_awaiting_review", "authority_conflict",
    "service_loaner_operational_alert", "executive_demo_blocked_recommendation",
)
