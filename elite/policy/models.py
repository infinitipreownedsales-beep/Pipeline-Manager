"""Phase 3 record types + taxonomy + lifecycle constants."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Policy taxonomy — categories must remain distinguishable.
CATEGORIES = ("MANUFACTURER_POLICY", "DEALERSHIP_POLICY", "FINANCIAL_ASSUMPTION",
              "OPERATIONAL_CONSTRAINT", "MANAGEMENT_PREFERENCE", "CALCULATION_CONFIGURATION",
              "SCENARIO_OVERRIDE", "CALIBRATION_CHANGE")

# Policy lifecycle states.
LIFECYCLE = ("DRAFT", "PROPOSED", "UNDER_REVIEW", "APPROVED", "SCHEDULED", "ACTIVE",
             "EXPIRED", "SUPERSEDED", "REVOKED", "REJECTED", "WITHDRAWN", "CORRECTED")

# Legal transitions (source -> allowed targets). Approval never auto-activates a
# future-effective version (see lifecycle.approve).
TRANSITIONS = {
    "DRAFT": {"PROPOSED", "WITHDRAWN", "CORRECTED"},
    "PROPOSED": {"UNDER_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED", "WITHDRAWN"},
    "APPROVED": {"SCHEDULED", "ACTIVE"},
    "SCHEDULED": {"ACTIVE", "REVOKED", "SUPERSEDED"},
    "ACTIVE": {"EXPIRED", "SUPERSEDED", "REVOKED"},
    "EXPIRED": set(), "SUPERSEDED": set(), "REVOKED": set(),
    "REJECTED": set(), "WITHDRAWN": set(), "CORRECTED": set(),
}
# States that never resolve as active official policy.
NON_RESOLVING = {"DRAFT", "PROPOSED", "UNDER_REVIEW", "REJECTED", "WITHDRAWN"}


@dataclass
class PolicyFamily:
    id: str
    name: str
    category: str
    owning_domain: str = "platform"
    value_schema: dict = field(default_factory=dict)
    allowed_scope_dimensions: list = field(default_factory=list)
    default_resolution: dict = field(default_factory=lambda: {"mode": "unresolved"})
    approval_required: bool = True
    correction_rules: dict = field(default_factory=dict)
    status: str = "active"
    created_at: Optional[str] = None


@dataclass
class PolicyVersion:
    id: str
    family_id: str
    version_number: int
    value: dict
    lifecycle_status: str
    recorded_time: str
    source: str = ""
    evidence_refs: list = field(default_factory=list)
    scope: dict = field(default_factory=dict)
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    start_inclusive: bool = True
    end_inclusive: bool = False
    approval_state: str = "unapproved"
    approving_principal: Optional[str] = None
    approved_time: Optional[str] = None
    scheduled_activation: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    correction_of: Optional[str] = None
    revocation: dict = field(default_factory=dict)
    reason: str = ""
    provenance: dict = field(default_factory=dict)
    store_scope: str = "*"
    is_scenario: bool = False
    scenario_id: Optional[str] = None
    version: int = 1


@dataclass
class CalculationFamily:
    id: str
    name: str
    owning_domain: str = "platform"
    purpose: str = ""
    input_contract_version: str = "1.0.0"
    output_contract_version: str = "1.0.0"
    determinism: str = "deterministic"
    required_policy_families: list = field(default_factory=list)
    status: str = "active"
    created_at: Optional[str] = None


@dataclass
class CalculationVersion:
    id: str
    family_id: str
    semver: str
    lifecycle_status: str = "registered"
    impl_revision: str = ""
    input_contract_version: str = "1.0.0"
    output_contract_version: str = "1.0.0"
    required_policy_families: list = field(default_factory=list)
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    approval_metadata: dict = field(default_factory=dict)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    rollback_of: Optional[str] = None
    change_summary: str = ""
    reproducibility_metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class ModelVersion:
    id: str
    model_family: str
    version: str
    status: str = "registered"
    scope: dict = field(default_factory=dict)
    purpose: str = ""
    activation: Optional[str] = None
    supersedes: Optional[str] = None
    evidence_refs: list = field(default_factory=list)
    calibration_proposal: Optional[str] = None
    validation_status: str = "unvalidated"
    rollback_ref: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class IdentityRuleVersion:
    id: str
    rule_family: str
    version: str
    status: str = "registered"
    entity_types: list = field(default_factory=list)
    rule_summary: str = ""
    impl_revision: str = ""
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    approval_metadata: dict = field(default_factory=dict)
    supersedes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ComparisonSpecificationVersion:
    id: str
    version: str
    status: str = "registered"
    prediction_type: str = ""
    observation_type: str = ""
    subject_entity_type: str = ""
    timing_rules: dict = field(default_factory=dict)
    matching_rules: dict = field(default_factory=dict)
    unit_contract: dict = field(default_factory=dict)
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    approval_metadata: dict = field(default_factory=dict)
    supersedes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ReproducibilityPackage:
    id: str
    refs: dict                       # all version + input references
    dealership_tz: str = "America/Chicago"
    calculation_timestamp: Optional[str] = None
    implementation_revision: str = ""
    output_reference: Optional[str] = None
    created_at: Optional[str] = None
