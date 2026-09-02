"""Phase 4 canonical record types (dataclasses). Storage is JSON-in-SQLite (store.py).

These are New Inventory planning records: Sellable Combination + lineage; Current / Future /
Committed Supply projections; historical retail; availability reconstruction; issued Demand /
forecast / plan / portfolio results. Issued results are append-preserving.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- taxonomy constants -----------------------------------------------------
# Availability states an interval can distinguish.
AVAILABILITY_STATES = ("available_unsold", "available_sold", "unavailable", "constrained",
                       "stockout", "unknown", "conflicting", "partial")
# Evidence tiers, most direct first. Direct evidence outranks inherited.
EVIDENCE_TIERS = ("exact", "lineage", "family", "attribute", "estimate")
DIRECT_TIERS = {"exact"}
# Planning states (Need/Excess resolution outcomes).
# "supply_only": the cohort has real current/incoming SUPPLY but NO accepted demand basis (and no approved
# demand lineage), so Need and Excess are UNKNOWN / NOT ASSERTED — never fabricated to zero. The combination is
# still authoritative; demand basis is honestly unresolved. Distinct from "balanced" (which asserts demand==supply).
PLANNING_STATES = ("need", "excess", "balanced", "unresolved", "conflicting", "supply_only")
# Commitment lifecycle.
COMMITMENT_STATES = ("proposed", "committed", "superseded", "cancelled", "fulfilled")

# Seasonality index bounds — sparse data must not create exaggerated coefficients.
SEASON_MIN, SEASON_MAX = 0.5, 2.0
# Sample-size threshold below which confidence is reduced.
LOW_SAMPLE = 3


@dataclass
class SellableCombination:
    id: str
    store_scope: str
    model: str
    canonical_identity: str
    franchise: str = ""
    model_year: Optional[str] = None
    trim: Optional[str] = None
    drivetrain: Optional[str] = None
    exterior_color: Optional[str] = None
    interior_color: Optional[str] = None
    source_refs: list = field(default_factory=list)
    quality_status: str = "ok"
    status: str = "active"
    lineage_metadata: dict = field(default_factory=dict)
    correction_of: Optional[str] = None
    created_at: Optional[str] = None
    corrected_at: Optional[str] = None
    version: int = 1


@dataclass
class CombinationLineage:
    id: str
    from_combination_id: str
    to_combination_id: str
    relationship: str                 # new_model_year|generation_change|related_family|attribute
    comparability: str = "comparable"
    approved_rule_ref: Optional[str] = None
    evidence_refs: list = field(default_factory=list)
    status: str = "active"
    created_at: Optional[str] = None


@dataclass
class CurrentSupply:
    id: str
    store_scope: str
    availability_state: str
    vehicle_unit_id: Optional[str] = None
    combination_id: Optional[str] = None
    arrival_date: Optional[str] = None
    available_for_retail_date: Optional[str] = None
    age_days: Optional[int] = None
    source_state_refs: list = field(default_factory=list)
    fact_refs: list = field(default_factory=list)
    retail_eligible: bool = False
    exclusion_reason: Optional[str] = None
    quality_status: str = "ok"
    confidence: str = "medium"
    calculation_timestamp: Optional[str] = None
    status: str = "current"


@dataclass
class FutureSupply:
    id: str
    store_scope: str
    production_order_id: Optional[str] = None
    combination_id: Optional[str] = None
    production_state: str = "planned"
    eta_start: Optional[str] = None
    eta_end: Optional[str] = None
    arrival_month: Optional[str] = None
    timing_confidence: str = "medium"
    editability: Optional[str] = None
    cancellation_status: Optional[str] = None
    source_refs: list = field(default_factory=list)
    fact_refs: list = field(default_factory=list)
    identity_linkage: dict = field(default_factory=dict)
    quality_status: str = "ok"
    calculation_timestamp: Optional[str] = None
    status: str = "current"


@dataclass
class SupplyCommitment:
    id: str
    store_scope: str
    commitment_type: str
    unit_or_order_id: Optional[str] = None
    unit_identity_kind: str = "production_order"     # vehicle_unit|production_order
    combination_id: Optional[str] = None
    decision_ref: Optional[str] = None
    approval_time: Optional[str] = None
    expected_supply_timing: Optional[str] = None
    arrival_month: Optional[str] = None
    lifecycle_status: str = "proposed"
    commitment_source: str = ""
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    cancellation_status: Optional[str] = None
    fact_refs: list = field(default_factory=list)
    audit_refs: list = field(default_factory=list)
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class RetailHistory:
    id: str
    store_scope: str
    combination_id: Optional[str] = None
    vehicle_unit_id: Optional[str] = None
    retail_event_ref: Optional[str] = None
    retail_date: Optional[str] = None
    retail_month: Optional[str] = None
    arrival_refs: list = field(default_factory=list)
    availability_refs: list = field(default_factory=list)
    model_year: Optional[str] = None
    source_refs: list = field(default_factory=list)
    fact_refs: list = field(default_factory=list)
    quality_status: str = "ok"
    status: str = "current"
    correction_of: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class AvailabilityInterval:
    id: str
    store_scope: str
    available_state: str
    combination_id: Optional[str] = None
    bucket: str = "month"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    available_unit_days: float = 0.0
    opening_depth: int = 0
    closing_depth: int = 0
    arrivals: int = 0
    retail_events: int = 0
    stockout_periods: list = field(default_factory=list)
    source_refs: list = field(default_factory=list)
    fact_refs: list = field(default_factory=list)
    quality_status: str = "ok"
    confidence: str = "medium"
    unresolved_gaps: list = field(default_factory=list)
    created_at: Optional[str] = None


@dataclass
class DemandResult:
    id: str
    store_scope: str
    combination_id: Optional[str] = None
    horizon_start: Optional[str] = None
    horizon_end: Optional[str] = None
    monthly_expected: dict = field(default_factory=dict)     # {month: expected_retail}
    baseline_evidence: dict = field(default_factory=dict)
    evidence_tier: str = "estimate"
    direct_evidence: bool = False
    availability_adjustment: str = ""
    seasonality_ref: dict = field(default_factory=dict)
    trend_ref: dict = field(default_factory=dict)
    confidence: str = "low"
    uncertainty: dict = field(default_factory=dict)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    source_refs: list = field(default_factory=list)
    fact_refs: list = field(default_factory=list)
    reproducibility_package: Optional[str] = None
    scenario_id: Optional[str] = None
    issued_time: Optional[str] = None
    status: str = "issued"


@dataclass
class ForecastResult:
    id: str
    store_scope: str
    issue_date: str
    combination_id: Optional[str] = None
    horizon_start: Optional[str] = None
    horizon_end: Optional[str] = None
    total_expected: float = 0.0
    confidence: str = "low"
    input_state_refs: list = field(default_factory=list)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    lineage_refs: list = field(default_factory=list)
    scenario_id: Optional[str] = None
    reproducibility_package: Optional[str] = None
    demand_result_id: Optional[str] = None
    status: str = "issued"
    months: list = field(default_factory=list)               # list[ForecastMonth]


@dataclass
class ForecastMonth:
    id: str
    forecast_id: str
    month: str
    expected_retail: float = 0.0
    cumulative_expected: float = 0.0
    confidence: str = "low"
    seq: int = 0


@dataclass
class DesiredCoverageResolution:
    id: str
    store_scope: str
    resolution_status: str            # resolved|unresolved|conflicting
    combination_id: Optional[str] = None
    policy_version: Optional[str] = None
    scope: dict = field(default_factory=dict)
    effective_period: dict = field(default_factory=dict)
    unit_contract: str = ""
    resolved_value: dict = field(default_factory=dict)
    fallback_used: bool = False
    note: str = ""
    created_at: Optional[str] = None


@dataclass
class InventoryPlanResult:
    id: str
    store_scope: str
    planning_state: str
    combination_id: Optional[str] = None
    evaluated_start: Optional[str] = None
    evaluated_end: Optional[str] = None
    expected_demand: float = 0.0
    current_supply: int = 0
    future_supply: int = 0
    committed_supply: int = 0
    qualifying_supply: int = 0
    desired_ending_coverage: dict = field(default_factory=dict)
    need: float = 0.0
    excess: float = 0.0
    confidence: str = "low"
    evidence: dict = field(default_factory=dict)
    policy_versions: list = field(default_factory=list)
    calculation_version: Optional[str] = None
    reproducibility_package: Optional[str] = None
    demand_result_id: Optional[str] = None
    scenario_id: Optional[str] = None
    issued_time: Optional[str] = None
    status: str = "issued"
    months: list = field(default_factory=list)               # list[InventoryPlanMonth]


@dataclass
class InventoryPlanMonth:
    id: str
    plan_id: str
    month: str
    expected_demand: float = 0.0
    cumulative_demand: float = 0.0
    cumulative_supply: int = 0
    shortage: float = 0.0
    excess: float = 0.0
    confidence: str = "low"
    seq: int = 0


@dataclass
class PortfolioPlanResult:
    id: str
    store_scope: str
    level: str                        # model|model_year|portfolio
    evaluated_start: Optional[str] = None
    evaluated_end: Optional[str] = None
    grouping_key: Optional[str] = None
    summary: dict = field(default_factory=dict)
    plan_refs: list = field(default_factory=list)
    monthly_demand: dict = field(default_factory=dict)
    supply_by_state: dict = field(default_factory=dict)
    need: float = 0.0
    excess: float = 0.0
    unresolved_quantity: float = 0.0
    confidence: str = "low"
    timing_risk: str = "unknown"
    calculation_version: Optional[str] = None
    issued_time: Optional[str] = None
    status: str = "issued"
