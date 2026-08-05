"""Phase 6 Service Loaner record types + lifecycle constants. Storage is JSON-in-SQLite."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Service Loaner membership lifecycle (governed). Rental state is a SEPARATE operational fact.
LIFECYCLE = ("CANDIDATE", "ENTRY_PROPOSED", "ENTRY_APPROVED", "ENTRY_PENDING", "ACTIVE_AVAILABLE",
             "ACTIVE_RENTED", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE", "RETIREMENT_PROPOSED",
             "RETIREMENT_APPROVED", "PROVISIONAL_RETIREMENT", "AWAITING_RETURN", "RETURN_CONFIRMED",
             "RETIRED", "AWAITING_USED_CARS_RECEIPT", "USED_CARS_RECEIVED", "RETURNED_TO_NEW_RETAIL",
             "CANCELLED", "CORRECTED")

# Legal transitions. Cancellation of a retirement restores an ACTIVE_* state (history preserved).
TRANSITIONS = {
    "CANDIDATE": {"ENTRY_PROPOSED", "CANCELLED"},
    "ENTRY_PROPOSED": {"ENTRY_APPROVED", "CANCELLED"},
    "ENTRY_APPROVED": {"ENTRY_PENDING", "ACTIVE_AVAILABLE", "CANCELLED"},
    "ENTRY_PENDING": {"ACTIVE_AVAILABLE", "CANCELLED"},
    "ACTIVE_AVAILABLE": {"ACTIVE_RENTED", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE",
                         "RETIREMENT_PROPOSED", "CORRECTED"},
    "ACTIVE_RENTED": {"ACTIVE_AVAILABLE", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE",
                      "RETIREMENT_PROPOSED", "PROVISIONAL_RETIREMENT", "CORRECTED"},
    "ACTIVE_UNRESOLVED": {"ACTIVE_AVAILABLE", "ACTIVE_RENTED", "CORRECTED"},
    "RETIREMENT_ELIGIBLE": {"RETIREMENT_PROPOSED", "ACTIVE_AVAILABLE"},
    "RETIREMENT_PROPOSED": {"RETIREMENT_APPROVED", "CANCELLED", "ACTIVE_AVAILABLE"},
    "RETIREMENT_APPROVED": {"PROVISIONAL_RETIREMENT", "AWAITING_RETURN", "RETURN_CONFIRMED",
                            "ACTIVE_AVAILABLE", "ACTIVE_RENTED", "CANCELLED"},
    "PROVISIONAL_RETIREMENT": {"AWAITING_RETURN", "RETURN_CONFIRMED", "ACTIVE_AVAILABLE", "ACTIVE_RENTED",
                               "CANCELLED"},
    "AWAITING_RETURN": {"RETURN_CONFIRMED", "ACTIVE_AVAILABLE", "CANCELLED"},
    "RETURN_CONFIRMED": {"RETIRED"},
    "RETIRED": {"AWAITING_USED_CARS_RECEIPT", "RETURNED_TO_NEW_RETAIL"},
    "AWAITING_USED_CARS_RECEIPT": {"USED_CARS_RECEIVED"},
    "USED_CARS_RECEIVED": set(),
    "RETURNED_TO_NEW_RETAIL": set(),
    "CANCELLED": set(),
    "CORRECTED": set(),
}
# Membership states that count as actual active fleet membership.
ACTIVE_MEMBERSHIP = {"ACTIVE_AVAILABLE", "ACTIVE_RENTED", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE",
                     "RETIREMENT_PROPOSED", "RETIREMENT_APPROVED", "PROVISIONAL_RETIREMENT",
                     "AWAITING_RETURN"}

MILEAGE_KINDS = ("zero", "value", "blank", "missing", "invalid")

ECONOMIC_ALTERNATIVES = ("remain_in_fleet", "retire_now", "retire_later", "await_return",
                         "return_to_new_retail", "transfer_to_used_cars")

EXECUTION_STATES = ("READY", "BLOCKED_RENTED", "BLOCKED_RETURN_NOT_CONFIRMED", "BLOCKED_POLICY",
                    "BLOCKED_IDENTITY", "BLOCKED_DATA", "BLOCKED_OPERATIONAL", "AWAITING_APPROVAL",
                    "APPROVED_NOT_EXECUTED", "IN_EXECUTION", "COMPLETED", "FAILED", "UNRESOLVED")

SNAPSHOT_OUTCOMES = ("MEMBER_CONFIRMED", "MEMBER_ADDED", "ABSENT_REVIEW", "ABSENT_NO_CHANGE",
                     "INVALID_VIN_EXCLUDED", "DUPLICATE_VIN", "CONFLICTING_STATE", "UNRESOLVED_IDENTITY")

RECON_OUTCOMES = ("REMAINS_ACTIVE", "PROVISIONAL_ONLY", "RETURN_CONFIRMED", "RETIRED_AWAITING_HANDOFF",
                  "USED_CARS_RECEIVED", "RETURNED_TO_NEW_RETAIL", "ALREADY_RECONCILED",
                  "UNRESOLVED_IDENTITY", "CONFLICTING", "FAILED_NO_EFFECT")


@dataclass
class ServiceLoanerUnit:
    id: str
    store_scope: str
    vehicle_unit_id: Optional[str] = None
    vin: Optional[str] = None
    combination_id: Optional[str] = None
    membership_state: str = "CANDIDATE"
    accepted_in_service_date: Optional[str] = None
    in_service_date_authority: Optional[str] = None
    current_rental_state: Optional[str] = None
    last_checkout_mileage: Optional[str] = None       # JSON-encoded typed value ref
    last_accepted_snapshot: Optional[str] = None
    active_fleet_presence: bool = False
    entry_decision: Optional[str] = None
    entry_execution_event: Optional[str] = None
    retirement_decision: Optional[str] = None
    return_confirmation: Optional[str] = None
    retirement_event: Optional[str] = None
    used_cars_receipt: Optional[str] = None
    return_to_retail_ref: Optional[str] = None
    correction_of: Optional[str] = None
    superseded_by: Optional[str] = None
    quality_status: str = "ok"
    confidence: str = "medium"
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class CheckoutMileage:
    id: str
    service_loaner_unit_id: str
    value_kind: str                                    # zero|value|blank|missing|invalid
    value: Optional[int] = None
    snapshot_ref: Optional[str] = None
    source: str = ""
    provenance: dict = field(default_factory=dict)
    status: str = "current"
    supersedes: Optional[str] = None
    recorded_at: Optional[str] = None


@dataclass
class InServiceDateResolution:
    id: str
    service_loaner_unit_id: str
    candidate_values: list = field(default_factory=list)
    source: str = ""
    evidence: dict = field(default_factory=dict)
    authority_level: str = "unverified"                # verified|unverified|fallback
    effective_time: Optional[str] = None
    accepted_value: Optional[str] = None
    conflict_state: Optional[str] = None
    correction_of: Optional[str] = None
    recorded_at: Optional[str] = None


@dataclass
class MonitoringAlert:
    id: str
    service_loaner_unit_id: str
    rule: str
    prompt: str = ""
    status: str = "active"                             # active|cleared
    snapshot_ref: Optional[str] = None
    in_service_date: Optional[str] = None
    elapsed_days: Optional[int] = None
    threshold_days: Optional[int] = None
    policy_refs: list = field(default_factory=list)
    cleared_reason: Optional[str] = None
    created_at: Optional[str] = None
    cleared_at: Optional[str] = None


@dataclass
class EconomicResult:
    id: str
    service_loaner_unit_id: str
    store_scope: str
    resolution_status: str                             # resolved|unresolved|conflicting
    decision_point: Optional[str] = None
    alternatives: list = field(default_factory=list)   # [{alternative, value, basis}]
    economic_call: dict = field(default_factory=dict)  # {choice, value, rationale}
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
    service_loaner_unit_id: str
    store_scope: str
    lifecycle_status: str                              # proposed|approved|provisional|cancelled|completed
    economic_result_id: Optional[str] = None
    decision_ref: Optional[str] = None
    approval_time: Optional[str] = None
    provisional: bool = False
    cancellation_status: Optional[str] = None
    correction_of: Optional[str] = None
    created_at: Optional[str] = None
    version: int = 1
