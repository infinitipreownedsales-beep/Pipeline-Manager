"""Phase 5 record types + workflow taxonomy + lifecycle constants.

Storage is JSON-in-SQLite (store.py). Governed action / transition / reconciliation / issued
records are append-preserving; projections may be superseded but prior-as-known is inspectable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---- taxonomy --------------------------------------------------------------
WORKFLOW_TYPES = ("cpo", "ppo", "dealer_trade", "ctp")

LIFECYCLE = ("DRAFT", "PROPOSED", "UNDER_REVIEW", "APPROVED", "COMMITTED", "IN_EXECUTION",
             "COMPLETED", "REJECTED", "WITHDRAWN", "CANCELLED", "FAILED", "SUPERSEDED",
             "EXPIRED", "UNRESOLVED")

# Per-workflow legal transitions (each domain restricts the common lifecycle).
_COMMON = {
    "DRAFT": {"PROPOSED", "WITHDRAWN"},
    "PROPOSED": {"UNDER_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED", "WITHDRAWN"},
    "APPROVED": {"COMMITTED", "CANCELLED", "SUPERSEDED"},
    "COMMITTED": {"IN_EXECUTION", "COMPLETED", "CANCELLED", "SUPERSEDED", "FAILED"},
    "IN_EXECUTION": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": set(), "REJECTED": set(), "WITHDRAWN": set(), "CANCELLED": set(),
    "FAILED": set(), "SUPERSEDED": set(), "EXPIRED": set(), "UNRESOLVED": set(),
}
# CPO/PPO: approval commits directly (an approved discrete allocation IS Committed Supply).
_ALLOC = {**{k: set(v) for k, v in _COMMON.items()}}
_ALLOC["PROPOSED"] = _ALLOC["PROPOSED"] | {"COMMITTED"}
_ALLOC["UNDER_REVIEW"] = _ALLOC["UNDER_REVIEW"] | {"COMMITTED"}

# Dealer Trade: an accepted (APPROVED) trade completes or fails directly, and an offer can lapse
# (EXPIRED) from any pre-completion state.
_DEALER = {**{k: set(v) for k, v in _COMMON.items()}}
_DEALER["PROPOSED"] = _DEALER["PROPOSED"] | {"EXPIRED"}
_DEALER["UNDER_REVIEW"] = _DEALER["UNDER_REVIEW"] | {"EXPIRED"}
_DEALER["APPROVED"] = _DEALER["APPROVED"] | {"EXPIRED", "COMPLETED", "FAILED"}

# CTP: an approved change is executed (accepted) to COMPLETED, or rejected/failed.
_CTP = {**{k: set(v) for k, v in _COMMON.items()}}
_CTP["APPROVED"] = _CTP["APPROVED"] | {"COMPLETED", "FAILED"}

TRANSITIONS = {"cpo": _ALLOC, "ppo": _ALLOC, "dealer_trade": _DEALER, "ctp": _CTP}

# A workflow that has reached one of these has (or had) a real qualifying-supply effect.
SUPPLY_BEARING = {"COMMITTED", "IN_EXECUTION", "COMPLETED"}
# Terminal states that never contribute prospective supply.
NON_CONTRIBUTING = {"REJECTED", "WITHDRAWN", "CANCELLED", "FAILED", "SUPERSEDED", "EXPIRED",
                    "DRAFT", "PROPOSED", "UNDER_REVIEW", "APPROVED", "UNRESOLVED"}

RECON_OUTCOMES = ("NO_SUPPLY_EFFECT", "COMMITMENT_CREATED", "ALREADY_REPRESENTED",
                  "COMMITMENT_UPDATED", "COMMITMENT_CANCELLED", "COMPLETED_TO_CURRENT",
                  "FAILED_NO_EFFECT", "UNRESOLVED_IDENTITY", "CONFLICTING", "DUPLICATE_REPLAY")

RISK_CLASSES = ("low", "elevated", "high", "unresolved")
ETA_PRECISION = ("exact", "range", "month", "unresolved", "conflicting", "stale")
EDITABILITY_STATES = ("editable", "conditionally_editable", "locked", "past_cutoff", "unknown",
                      "conflicting")


@dataclass
class ProductionPipeline:
    id: str
    store_scope: str
    production_order_id: Optional[str] = None
    combination_id: Optional[str] = None
    order_status: str = "open"
    production_status: str = "planned"
    allocation_status: Optional[str] = None
    vin_status: str = "pending"
    build_timing: Optional[str] = None
    shipment_timing: Optional[str] = None
    eta_start: Optional[str] = None
    eta_end: Optional[str] = None
    arrival_month: Optional[str] = None
    source_refs: list = field(default_factory=list)
    fact_refs: list = field(default_factory=list)
    identity_refs: dict = field(default_factory=dict)
    quality_status: str = "ok"
    confidence: str = "medium"
    status: str = "current"
    conflict: Optional[str] = None
    recorded_time: Optional[str] = None
    effective_time: Optional[str] = None


@dataclass
class EtaRecord:
    id: str
    precision: str
    production_order_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    eta_start: Optional[str] = None
    eta_end: Optional[str] = None
    arrival_month: Optional[str] = None
    confidence: str = "medium"
    stale: bool = False
    conflicting: bool = False
    supersedes: Optional[str] = None
    source_refs: list = field(default_factory=list)
    recorded_time: Optional[str] = None


@dataclass
class EditabilityResult:
    id: str
    editability_state: str
    production_order_id: Optional[str] = None
    store_scope: Optional[str] = None
    editable_dimensions: list = field(default_factory=list)
    cutoff: Optional[str] = None
    source_refs: list = field(default_factory=list)
    policy_refs: list = field(default_factory=list)
    confidence: str = "medium"
    unresolved_conditions: list = field(default_factory=list)
    recorded_time: Optional[str] = None


@dataclass
class ModelYearTransition:
    id: str
    store_scope: str
    model: str
    outgoing_model_year: Optional[str] = None
    incoming_model_year: Optional[str] = None
    overlap: Optional[str] = None
    lineage_status: str = "unspecified"
    transition_window: dict = field(default_factory=dict)
    arrival_risk: str = "unknown"
    constrained_incoming: bool = False
    evidence: dict = field(default_factory=dict)
    policy_refs: list = field(default_factory=list)
    confidence: str = "medium"
    recorded_time: Optional[str] = None


@dataclass
class IncomingRisk:
    id: str
    classification: str
    subject_kind: str = "future_supply"
    subject_ref: Optional[str] = None
    combination_id: Optional[str] = None
    store_scope: Optional[str] = None
    reasons: list = field(default_factory=list)      # component reasons — never one opaque score
    timing: dict = field(default_factory=dict)
    affected_need_window: dict = field(default_factory=dict)
    source_facts: list = field(default_factory=list)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    confidence: str = "medium"
    reproducibility_package: Optional[str] = None
    issued_time: Optional[str] = None


@dataclass
class SupplyWorkflow:
    id: str
    workflow_type: str
    store_scope: str
    subject_identity: Optional[str] = None
    subject_kind: str = "production_order"
    combination_id: Optional[str] = None
    target_month: Optional[str] = None
    quantity: int = 1
    originating_need_ref: Optional[str] = None
    qualifying_supply_at_propose: Optional[int] = None
    expected_resulting_supply: dict = field(default_factory=dict)
    proposal_reason: str = ""
    evidence: dict = field(default_factory=dict)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    approval_decision: Optional[str] = None
    execution_refs: list = field(default_factory=list)
    lifecycle_status: str = "DRAFT"
    idempotency_identity: Optional[str] = None
    audit_refs: list = field(default_factory=list)
    reproducibility_package: Optional[str] = None
    scenario_id: Optional[str] = None
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class ReconciliationResult:
    id: str
    outcome: str
    workflow_id: Optional[str] = None
    transition_ref: Optional[str] = None
    subject_identity: Optional[str] = None
    combination_id: Optional[str] = None
    supply_ref: Optional[str] = None
    prior_qualifying: Optional[int] = None
    new_qualifying: Optional[int] = None
    detail: str = ""
    recorded_at: Optional[str] = None
