"""Phase 8 learning + calibration record types + constants. Storage is JSON-in-SQLite.

Domain-aware: shared platform fields are common but each Prediction/Observation carries an explicit
domain payload contract — no universal payload that erases domain meaning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Foundational Prediction types (domain-aware; each declares its Observation contract).
PREDICTION_TYPES = (
    "new_inventory_monthly_demand", "combination_retail_expectation", "need_or_excess",
    "arrival_timing_or_incoming_risk", "workflow_outcome_expectation",
    "service_loaner_economic_call_expectation", "service_loaner_retirement_expectation",
    "executive_demo_opportunity_or_lifecycle_expectation", "executive_demo_retirement_expectation",
)
# Each Prediction type declares the Observation contract it expects.
OBSERVATION_CONTRACT = {
    "new_inventory_monthly_demand": "actual_monthly_retail",
    "combination_retail_expectation": "actual_unit_retail",
    "need_or_excess": "actual_availability",
    "arrival_timing_or_incoming_risk": "actual_arrival_timing",
    "workflow_outcome_expectation": "actual_workflow_completion",
    "service_loaner_economic_call_expectation": "actual_service_loaner_retirement",
    "service_loaner_retirement_expectation": "actual_service_loaner_retirement",
    "executive_demo_opportunity_or_lifecycle_expectation": "actual_executive_demo_activation",
    "executive_demo_retirement_expectation": "actual_executive_demo_retirement",
}
OBSERVATION_TYPES = (
    "actual_monthly_retail", "actual_unit_retail", "actual_availability", "actual_arrival_timing",
    "actual_workflow_completion", "actual_workflow_failure", "actual_service_loaner_retirement",
    "actual_used_cars_receipt", "actual_service_loaner_resale_reference", "actual_executive_demo_activation",
    "actual_executive_demo_retirement", "actual_return_path", "actual_resale_or_new_retail_outcome",
)

PAIRING_OUTCOMES = (
    "PAIRED", "PENDING_OBSERVATION", "PARTIAL", "LATE_PAIRED", "AMBIGUOUS", "CONFLICTING", "UNIT_MISMATCH",
    "SCOPE_MISMATCH", "IDENTITY_MISMATCH", "OUTSIDE_WINDOW", "UNRESOLVED", "CORRECTED", "SUPERSEDED",
)

ATTRIBUTION_CATEGORIES = (
    "availability_constraint", "stockout", "source_data_quality", "timing_shift", "eta_variance",
    "policy_change", "calculation_limitation", "model_year_transition", "unapproved_lineage",
    "operational_execution_failure", "cancelled_or_failed_workflow", "service_loaner_operational_block",
    "executive_demo_operational_block", "market_or_customer_factor", "unknown",
)
ATTRIBUTION_STATUSES = (
    "PROPOSED", "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "REJECTED", "UNRESOLVED",
    "CORRECTED", "SUPERSEDED",
)

SIGNAL_STATUSES = (
    "CANDIDATE", "MONITORING", "SUPPORTED", "INSUFFICIENT_EVIDENCE", "CONFLICTING", "REJECTED",
    "ESCALATED_TO_CALIBRATION", "CORRECTED", "SUPERSEDED",
)

CALIBRATION_TARGETS = (
    "calculation_version", "model_version", "calculation_parameter", "confidence_classification",
    "lineage_or_comparability_rule", "materiality_threshold", "monitoring_threshold",
    "policy_review_recommendation", "source_quality_rule_review", "comparison_specification_version",
)
CALIBRATION_STATES = (
    "DRAFT", "PROPOSED", "UNDER_REVIEW", "VALIDATION_REQUIRED", "VALIDATED", "APPROVED", "SCHEDULED",
    "ACTIVATED", "REJECTED", "WITHDRAWN", "ROLLED_BACK", "SUPERSEDED", "CORRECTED",
)
# Legal Calibration lifecycle transitions (governed).
CALIBRATION_TRANSITIONS = {
    "DRAFT": {"PROPOSED", "WITHDRAWN", "CORRECTED"},
    "PROPOSED": {"UNDER_REVIEW", "REJECTED", "WITHDRAWN", "CORRECTED"},
    "UNDER_REVIEW": {"VALIDATION_REQUIRED", "APPROVED", "REJECTED", "WITHDRAWN", "CORRECTED"},
    "VALIDATION_REQUIRED": {"VALIDATED", "REJECTED", "WITHDRAWN", "CORRECTED"},
    "VALIDATED": {"APPROVED", "REJECTED", "WITHDRAWN", "CORRECTED"},
    "APPROVED": {"SCHEDULED", "ACTIVATED", "REJECTED", "WITHDRAWN", "CORRECTED"},
    "SCHEDULED": {"ACTIVATED", "WITHDRAWN", "CORRECTED"},
    "ACTIVATED": {"ROLLED_BACK", "SUPERSEDED", "CORRECTED"},
    "REJECTED": set(),
    "WITHDRAWN": set(),
    "ROLLED_BACK": set(),
    "SUPERSEDED": set(),
    "CORRECTED": set(),
}
# Targets that change real behavior and therefore require validation before approval.
MATERIAL_TARGETS = {"calculation_version", "model_version", "calculation_parameter",
                    "comparison_specification_version"}


@dataclass
class Prediction:
    id: str
    prediction_type: str
    owning_domain: str
    store_scope: str
    subject_entity_type: Optional[str] = None
    subject_entity_id: Optional[str] = None
    org_scope: Optional[str] = None
    issue_time: Optional[str] = None
    effective_period: Optional[str] = None
    prediction_horizon: Optional[str] = None
    predicted_payload: dict = field(default_factory=dict)
    unit_contract: dict = field(default_factory=dict)
    confidence: Optional[str] = None
    uncertainty: dict = field(default_factory=dict)
    evidence_classification: Optional[str] = None
    fact_refs: list = field(default_factory=list)
    source_state_refs: list = field(default_factory=list)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    model_version: Optional[str] = None
    identity_rule_version: Optional[str] = None
    comparison_spec_version: Optional[str] = None
    comparison_spec_family: Optional[str] = None
    observation_contract: Optional[str] = None
    scenario_id: Optional[str] = None
    reproducibility_package: Optional[str] = None
    implementation_revision: str = "phase8"
    issuing_actor: Optional[str] = None
    resolution_status: str = "issued"
    status: str = "issued"
    correction_of: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class Observation:
    id: str
    observation_type: str
    owning_domain: str
    store_scope: str
    subject_entity_type: Optional[str] = None
    subject_entity_id: Optional[str] = None
    observed_period: Optional[str] = None
    observed_payload: Optional[dict] = None            # None => missing (NOT zero)
    unit_contract: dict = field(default_factory=dict)
    fact_refs: list = field(default_factory=list)
    source_observation_refs: list = field(default_factory=list)
    accepted_time: Optional[str] = None
    recorded_time: Optional[str] = None
    quality: Optional[str] = None
    confidence: Optional[str] = None
    completeness: Optional[str] = None
    resolution_status: str = "accepted"
    status: str = "accepted"
    provenance: dict = field(default_factory=dict)
    correction_of: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ComparisonSpecRuntime:
    id: str
    version: str
    prediction_type: str
    observation_type: str
    registry_ref: Optional[str] = None
    subject_entity_type: Optional[str] = None
    scope_rules: dict = field(default_factory=dict)
    matching_keys: list = field(default_factory=list)
    timing_rules: dict = field(default_factory=dict)
    observation_window: dict = field(default_factory=dict)
    lateness_tolerance: dict = field(default_factory=dict)
    unit_contract: dict = field(default_factory=dict)
    transformation_rules: dict = field(default_factory=dict)
    aggregation_rules: dict = field(default_factory=dict)
    partial_behavior: str = "partial_error"
    conflicting_behavior: str = "unresolved"
    missing_behavior: str = "pending"                  # NOT zero
    error_semantics: str = "signed_numeric"
    directionality: str = "over_under"
    materiality_threshold_ref: Optional[str] = None
    confidence_rules: dict = field(default_factory=dict)
    status: str = "registered"
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    approval_metadata: dict = field(default_factory=dict)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    impl_revision: str = "phase8"
    created_at: Optional[str] = None
    version_no: int = 1


@dataclass
class Pairing:
    id: str
    prediction_id: str
    comparison_spec_version: str
    pairing_status: str
    observation_id: Optional[str] = None
    subject_entity_type: Optional[str] = None
    subject_entity_id: Optional[str] = None
    store_scope: Optional[str] = None
    matching_evidence: dict = field(default_factory=dict)
    timing_relationship: Optional[str] = None
    unit_compatible: Optional[bool] = None
    completeness: Optional[str] = None
    confidence: Optional[str] = None
    paired_time: Optional[str] = None
    rule_or_principal: Optional[str] = None
    correction_of: Optional[str] = None
    superseded_by: Optional[str] = None
    reason: str = ""
    idempotency_key: Optional[str] = None
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class PredictionError:
    id: str
    pairing_id: str
    prediction_id: str
    comparison_spec_version: str
    observation_id: Optional[str] = None
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    signed_error: Optional[str] = None
    absolute_error: Optional[str] = None
    percentage_error: Optional[str] = None
    bounded_error: Optional[str] = None
    timing_error: Optional[str] = None
    classification: Optional[str] = None
    materiality: Optional[str] = None
    confidence: Optional[str] = None
    resolution_status: str = "calculated"
    calculation_time: Optional[str] = None
    calculation_version: Optional[str] = None
    reproducibility_package: Optional[str] = None
    correction_of: Optional[str] = None
    superseded_by: Optional[str] = None
    created_at: Optional[str] = None
