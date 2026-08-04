"""Phase 2 canonical record types (dataclasses). Storage is JSON-in-SQLite (store.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldSpec:
    name: str
    required: bool = True
    kind: str = "text"          # text|upper|int|number|bool|date|vin
    meaning: str = ""
    normalize: str = ""         # informational; `kind` drives coercion


@dataclass
class SourceRegistry:
    id: str
    name: str
    owner: str = ""
    source_type: str = ""
    supported_profiles: list = field(default_factory=list)      # profile ids
    authoritative_fact_types: list = field(default_factory=list)
    scope: str = "*"
    status: str = "active"
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    registered_at: Optional[str] = None
    version: int = 1

    def is_authoritative(self, fact_type: str, scope: str) -> bool:
        if self.status != "active":
            return False
        if fact_type not in self.authoritative_fact_types:
            return False
        return self.scope == "*" or self.scope == scope


@dataclass
class SchemaProfile:
    id: str
    source_id: str
    version: int
    fields: list                         # list[FieldSpec]
    snapshot_capable: bool = False
    full_snapshot_requirements: dict = field(default_factory=dict)
    scope_rules: str = ""
    effective_time_rule: str = ""
    compatibility_status: str = "active"
    created_at: Optional[str] = None


@dataclass
class ImportBatch:
    id: str
    source_id: str
    schema_profile_version: Optional[int]
    payload_checksum: str
    received_at: str
    store_scope: str
    claimed_snapshot_type: str = "partial"
    validated_snapshot_type: str = "partial"
    lifecycle_status: str = "received"
    effective_time: Optional[str] = None
    row_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    quarantined_count: int = 0
    duplicate_count: int = 0
    conflicting_count: int = 0
    unresolved_count: int = 0
    detail: str = ""
    correlation_id: Optional[str] = None
    replay_of: Optional[str] = None


@dataclass
class SourceObservation:
    id: str
    import_batch_id: str
    raw_values: dict
    normalized_values: dict
    recorded_time: str
    validation_status: str              # valid|rejected|quarantined
    acceptance_status: str              # pending|accepted|rejected|duplicate|conflicting|unresolved|quarantined
    source_record_identity: Optional[str] = None
    observed_time: Optional[str] = None
    source_scope: Optional[str] = None
    identity_status: Optional[str] = None
    provenance: dict = field(default_factory=dict)
    supersedes_ref: Optional[str] = None
    correction_ref: Optional[str] = None


@dataclass
class VehicleUnit:
    id: str
    identity_status: str
    store_scope: str
    vin: Optional[str] = None
    created_at: Optional[str] = None
    corrected_at: Optional[str] = None
    version: int = 1


@dataclass
class ProductionOrder:
    id: str
    identity_status: str
    store_scope: str
    manufacturer_order_id: Optional[str] = None
    vin: Optional[str] = None
    linked_vehicle_unit_id: Optional[str] = None
    created_at: Optional[str] = None
    version: int = 1


@dataclass
class IdentityEvidence:
    id: str
    entity_type: str
    identifier_type: str
    identifier_value: str
    resolution_status: str              # matched|created|distinct|unresolved|conflicting|corrected|superseded
    recorded_at: str
    source_ref: Optional[str] = None
    record_ref: Optional[str] = None
    candidate_entities: list = field(default_factory=list)
    resolution_rule_version: str = "1.0.0"
    confidence: Optional[float] = None
    resolver: str = "auto"
    reason: str = ""
    correction_ref: Optional[str] = None
    store_scope: Optional[str] = None


@dataclass
class BusinessFact:
    id: str
    fact_type: str
    subject_entity_type: str
    subject_entity_id: str
    payload: dict
    recorded_time: str
    status: str = "current"             # current|superseded|reversed
    effective_time: Optional[str] = None
    observation_refs: list = field(default_factory=list)
    source_authority: Optional[str] = None
    quality_status: str = "ok"
    correction_of: Optional[str] = None
    superseded_by: Optional[str] = None
    reversal_of: Optional[str] = None
    store_scope: Optional[str] = None
    provenance: dict = field(default_factory=dict)
    version: int = 1


@dataclass
class ReconciliationResult:
    id: str
    import_batch_id: str
    outcome: str                        # matched|created|rejected|duplicate|conflicting|unresolved|quarantined|absent_in_full_snapshot
    recorded_at: str
    source_observation_id: Optional[str] = None
    candidate_entities: list = field(default_factory=list)
    reason: str = ""
    resulting_fact_refs: list = field(default_factory=list)
    conflict_refs: list = field(default_factory=list)
    reviewer: Optional[str] = None
