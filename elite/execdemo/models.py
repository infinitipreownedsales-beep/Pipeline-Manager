"""Phase 7 Executive Demo record types + lifecycle constants. Storage is JSON-in-SQLite."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

LIFECYCLE = ("CANDIDATE", "DESIGNATION_PROPOSED", "DESIGNATION_APPROVED", "DESIGNATION_PENDING",
             "ACTIVE", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE", "RETIREMENT_PROPOSED",
             "RETIREMENT_APPROVED", "RETIREMENT_PENDING", "RETIRED", "RETURNED_TO_NEW_RETAIL",
             "AWAITING_USED_CARS_RECEIPT", "USED_CARS_RECEIVED", "CANCELLED", "CORRECTED")

TRANSITIONS = {
    "CANDIDATE": {"DESIGNATION_PROPOSED", "CANCELLED"},
    "DESIGNATION_PROPOSED": {"DESIGNATION_APPROVED", "CANCELLED"},
    "DESIGNATION_APPROVED": {"DESIGNATION_PENDING", "ACTIVE", "CANCELLED"},
    "DESIGNATION_PENDING": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE", "RETIREMENT_PROPOSED", "CORRECTED"},
    "ACTIVE_UNRESOLVED": {"ACTIVE", "CORRECTED"},
    "RETIREMENT_ELIGIBLE": {"RETIREMENT_PROPOSED", "ACTIVE"},
    "RETIREMENT_PROPOSED": {"RETIREMENT_APPROVED", "CANCELLED", "ACTIVE"},
    "RETIREMENT_APPROVED": {"RETIREMENT_PENDING", "RETIRED", "ACTIVE", "CANCELLED"},
    "RETIREMENT_PENDING": {"RETIRED", "CANCELLED"},
    "RETIRED": {"RETURNED_TO_NEW_RETAIL", "AWAITING_USED_CARS_RECEIPT"},
    "RETURNED_TO_NEW_RETAIL": set(),
    "AWAITING_USED_CARS_RECEIPT": {"USED_CARS_RECEIVED"},
    "USED_CARS_RECEIVED": set(),
    "CANCELLED": set(),
    "CORRECTED": set(),
}
# A correction may be recorded from any non-terminal state (it preserves prior history).
_TERMINAL = {"RETURNED_TO_NEW_RETAIL", "USED_CARS_RECEIVED", "CANCELLED", "CORRECTED", "RETIRED",
             "AWAITING_USED_CARS_RECEIPT"}
for _s, _targets in TRANSITIONS.items():
    if _s not in _TERMINAL:
        _targets.add("CORRECTED")

# Membership states that count as an actual active Executive Demo unit.
ACTIVE_MEMBERSHIP = {"ACTIVE", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE", "RETIREMENT_PROPOSED",
                     "RETIREMENT_APPROVED", "RETIREMENT_PENDING"}
# States that make a Vehicle Unit unavailable as a fresh candidate.
UNAVAILABLE = ACTIVE_MEMBERSHIP | {"DESIGNATION_PROPOSED", "DESIGNATION_APPROVED", "DESIGNATION_PENDING",
                                   "RETIRED", "AWAITING_USED_CARS_RECEIPT", "USED_CARS_RECEIVED"}

ELIGIBILITY_OUTCOMES = ("ELIGIBLE", "INELIGIBLE_ACTIVE_SERVICE_LOANER", "INELIGIBLE_ALREADY_DEMO",
                        "INELIGIBLE_COMMITTED", "INELIGIBLE_SOLD", "INELIGIBLE_POLICY",
                        "INELIGIBLE_IDENTITY", "INELIGIBLE_DATA", "UNRESOLVED", "CONFLICTING")

ECONOMIC_ALTERNATIVES = ("designate_now", "designate_later", "choose_another", "maintain_portfolio",
                         "retire_now", "retire_later", "return_to_new_retail", "transfer_to_used_cars",
                         "unresolved")

EXECUTION_STATES = ("READY", "AWAITING_APPROVAL", "APPROVED_NOT_EXECUTED", "BLOCKED_POLICY",
                    "BLOCKED_IDENTITY", "BLOCKED_DATA", "BLOCKED_NEW_RETAIL_RISK", "BLOCKED_OPERATIONAL",
                    "IN_EXECUTION", "COMPLETED", "FAILED", "UNRESOLVED")

RECON_OUTCOMES = ("REMAINS_ACTIVE_DEMO", "DESIGNATION_COMMITTED", "ACTIVE_DEMO",
                  "RETIRED_AWAITING_DISPOSITION", "RETURNED_TO_NEW_RETAIL", "USED_CARS_RECEIVED",
                  "ALREADY_RECONCILED", "UNRESOLVED_IDENTITY", "CONFLICTING", "FAILED_NO_EFFECT")


@dataclass
class ExecDemoUnit:
    id: str
    store_scope: str
    vehicle_unit_id: Optional[str] = None
    vin: Optional[str] = None
    combination_id: Optional[str] = None
    membership_state: str = "CANDIDATE"
    designation_decision: Optional[str] = None
    designation_execution_event: Optional[str] = None
    active_date: Optional[str] = None
    in_service_or_activation_date: Optional[str] = None
    current_mileage: Optional[str] = None
    assigned_role: Optional[str] = None
    model_preference_evidence: Optional[str] = None
    portfolio_role: Optional[str] = None
    retirement_decision: Optional[str] = None
    retirement_event: Optional[str] = None
    return_to_retail_event: Optional[str] = None
    used_cars_receipt: Optional[str] = None
    current_economic_result: Optional[str] = None
    active_fleet_supply_ref: Optional[str] = None
    correction_of: Optional[str] = None
    superseded_by: Optional[str] = None
    quality_status: str = "ok"
    confidence: str = "medium"
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class EconomicResult:
    id: str
    executive_demo_unit_id: str
    store_scope: str
    resolution_status: str
    decision_point: Optional[str] = None
    candidate_id: Optional[str] = None
    alternatives: list = field(default_factory=list)
    economic_call: dict = field(default_factory=dict)
    opportunity_cost_ref: Optional[str] = None
    expected_benefit: dict = field(default_factory=dict)
    retirement_impact: dict = field(default_factory=dict)
    assumptions: dict = field(default_factory=dict)
    uncertainty: dict = field(default_factory=dict)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    fact_refs: list = field(default_factory=list)
    reproducibility_package: Optional[str] = None
    scenario_id: Optional[str] = None
    issued_time: Optional[str] = None
    status: str = "issued"


@dataclass
class RetirementAction:
    id: str
    executive_demo_unit_id: str
    store_scope: str
    lifecycle_status: str
    economic_result_id: Optional[str] = None
    decision_ref: Optional[str] = None
    approval_time: Optional[str] = None
    cancellation_status: Optional[str] = None
    correction_of: Optional[str] = None
    created_at: Optional[str] = None
    version: int = 1
