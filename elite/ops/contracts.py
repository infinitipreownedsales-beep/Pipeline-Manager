"""Source-contract registry for the controlled pilot.

Documents the ACTUAL source families required for a controlled dealership pilot. Each contract declares
its owner, system, access method, file/interface type, cadence, snapshot capability, identity keys,
effective- and update-time semantics, schema version, required/optional fields, units, blank/zero/missing
behavior, duplicate/correction/absence semantics, quality thresholds, blocking vs nonblocking validation,
raw-retention requirement, and expected reconciliation.

This registry does NOT invent source access. Where no automated source exists for the pilot, the contract
is marked `access="manual_governed"` — a governed operator input, not a fabricated feed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceContract:
    key: str
    owner: str                       # who owns the data at the dealership
    source_system: str               # the system it comes from
    access: str                      # file_drop | operator_upload | api | manual_governed
    file_kind: str                   # csv | tsv | json | spreadsheet_export | manual
    cadence: str                     # daily | intraday | weekly | on_change | ad_hoc | manual
    snapshot_capability: str         # full | partial | full_or_partial | none
    identity_keys: tuple             # keys that establish identity
    effective_time: str              # how business-effective time is derived (NOT file import time)
    update_time: str                 # how "as of" / update time is derived
    schema_version: int
    required_fields: tuple
    optional_fields: tuple = ()
    units: dict = field(default_factory=dict)
    blank_zero_missing: str = "blank != zero != missing (distinct sentinels; never coerced)"
    duplicate_behavior: str = "within-file duplicate collapses; conflicting duplicate flagged"
    correction_behavior: str = "correction preserves prior; supersession recorded, never overwrite"
    absence_behavior: str = "absence is a scoped signal only; never a deletion unless Full-Snapshot contract permits"
    quality_thresholds: str = "reject-rate threshold blocks acceptance; below-threshold warns"
    blocking_validation: tuple = ()      # failures that BLOCK acceptance
    nonblocking_validation: tuple = ()   # failures that WARN but do not block
    raw_retention: str = "raw source rows preserved as Source Observations (Phase 2); required"
    expected_reconciliation: str = "row -> accepted fact -> identity -> domain projection"
    domain: str = ""
    fact_type: str = ""
    entity_kind: str = "vehicle"
    header_aliases: dict = field(default_factory=dict)   # real source header -> canonical field name
    sheet: str = ""                                      # worksheet name for workbook sources ("" = first sheet)
    stock_number_is_identity: bool = True                # False: stock_number is NOT an identity/dedup key
    serial_lifecycle: bool = False                       # True: Serial is lifecycle-dependent; classify UNKNOWN
    # Snapshot idempotency policy. "content_hash" (default): a prior COMPLETED run with the same content is a
    # replay (legacy behavior, unchanged for every existing source). "content_hash_per_business_date": for a
    # recurring longitudinal-memory source, dedup identity is (source, scope, local business date, content
    # hash) — a byte-identical export on a LATER business day is a NEW legitimate snapshot (inventory
    # unchanged into another day), while a same-day identical re-upload is still a replay.
    snapshot_idempotency: str = "content_hash"


# The minimum source families required for the controlled pilot.
SOURCE_CONTRACTS = {
    "new_inventory_current": SourceContract(
        key="new_inventory_current", owner="Inventory Manager", source_system="DMS",
        access="file_drop", file_kind="csv", cadence="daily", snapshot_capability="full_or_partial",
        identity_keys=("vin", "stock_number"), effective_time="as-of date column, else snapshot business date",
        update_time="DMS export timestamp column", schema_version=1,
        required_fields=("stock_number", "model"), optional_fields=("vin", "production_month", "mileage", "status"),
        units={"mileage": "miles"}, blocking_validation=("missing_required_field", "malformed_row"),
        nonblocking_validation=("invalid_vin", "extra_unknown_column"),
        domain="new_inventory", fact_type="vehicle_present", entity_kind="vehicle"),
    "production_orders": SourceContract(
        key="production_orders", owner="New Car Manager", source_system="OEM order portal",
        access="operator_upload", file_kind="csv", cadence="weekly", snapshot_capability="partial",
        identity_keys=("manufacturer_order_id", "vin"), effective_time="order/allocation date column",
        update_time="portal export date", schema_version=1,
        required_fields=("manufacturer_order_id", "model"), optional_fields=("vin", "eta_month", "status"),
        domain="production", fact_type="production_order_present", entity_kind="order"),
    "retail_history": SourceContract(
        key="retail_history", owner="Sales Manager", source_system="DMS sales ledger",
        access="file_drop", file_kind="csv", cadence="daily", snapshot_capability="partial",
        identity_keys=("vin", "deal_number"), effective_time="delivery/sold date column",
        update_time="ledger export date", schema_version=1,
        required_fields=("vin", "sold_date", "model"), optional_fields=("deal_number", "price"),
        domain="new_inventory", fact_type="retail_sale", entity_kind="vehicle"),
    "vehicle_identity": SourceContract(
        key="vehicle_identity", owner="Inventory Manager", source_system="DMS vehicle master",
        access="file_drop", file_kind="csv", cadence="daily", snapshot_capability="full",
        identity_keys=("vin",), effective_time="in-stock date column", update_time="master export date",
        schema_version=1, required_fields=("vin",), optional_fields=("stock_number", "model", "year"),
        domain="new_inventory", fact_type="vehicle_present", entity_kind="vehicle"),
    "arrival_availability": SourceContract(
        key="arrival_availability", owner="New Car Manager", source_system="OEM logistics feed",
        access="operator_upload", file_kind="csv", cadence="intraday", snapshot_capability="partial",
        identity_keys=("vin", "manufacturer_order_id"), effective_time="ETA / arrival window column",
        update_time="feed timestamp", schema_version=1,
        required_fields=("manufacturer_order_id",), optional_fields=("vin", "eta_date", "arrival_status"),
        domain="production", fact_type="production_order_present", entity_kind="order"),
    "service_loaner_fleet": SourceContract(
        key="service_loaner_fleet", owner="Service Director", source_system="Loaner fleet system",
        access="file_drop", file_kind="csv", cadence="daily", snapshot_capability="full",
        identity_keys=("vin",), effective_time="in-service date column (verified, not import date)",
        update_time="fleet export date", schema_version=1,
        required_fields=("vin",), optional_fields=("stock_number", "status", "in_service_date", "last_checkout_mileage"),
        absence_behavior="Full-Snapshot absence flags membership review; never auto-retires a unit",
        domain="service_loaner", fact_type="loaner_fleet_present", entity_kind="vehicle"),
    "service_loaner_status": SourceContract(
        key="service_loaner_status", owner="Service Director", source_system="Loaner fleet system",
        access="operator_upload", file_kind="csv", cadence="intraday", snapshot_capability="partial",
        identity_keys=("vin",), effective_time="status-change timestamp", update_time="export timestamp",
        schema_version=1, required_fields=("vin", "status"), optional_fields=("rented", "location"),
        domain="service_loaner", fact_type="loaner_status", entity_kind="vehicle"),
    "service_loaner_in_service_date": SourceContract(
        key="service_loaner_in_service_date", owner="Service Director", source_system="Loaner fleet system",
        access="manual_governed", file_kind="manual", cadence="on_change", snapshot_capability="partial",
        identity_keys=("vin",), effective_time="verified in-service date (authoritative; import date never substitutes)",
        update_time="operator entry time", schema_version=1,
        required_fields=("vin", "in_service_date"),
        domain="service_loaner", fact_type="loaner_in_service_date", entity_kind="vehicle"),
    "service_loaner_last_checkout_mileage": SourceContract(
        key="service_loaner_last_checkout_mileage", owner="Service Advisor", source_system="Loaner fleet system",
        access="operator_upload", file_kind="csv", cadence="on_change", snapshot_capability="partial",
        identity_keys=("vin",), effective_time="checkout timestamp", update_time="export timestamp",
        schema_version=1, required_fields=("vin", "last_checkout_mileage"),
        units={"last_checkout_mileage": "miles"},
        blank_zero_missing="0 miles != blank != missing != invalid (zero is a real reading)",
        domain="service_loaner", fact_type="loaner_last_checkout_mileage", entity_kind="vehicle"),
    "executive_demo_state": SourceContract(
        key="executive_demo_state", owner="General Manager", source_system="Demo log (where a source exists)",
        access="manual_governed", file_kind="manual", cadence="on_change", snapshot_capability="partial",
        identity_keys=("vin",), effective_time="designation date", update_time="operator entry time",
        schema_version=1, required_fields=("vin",), optional_fields=("assigned_to", "designation_date"),
        domain="executive_demo", fact_type="executive_demo_state", entity_kind="vehicle"),
    "policy_incentive_inputs": SourceContract(
        key="policy_incentive_inputs", owner="General Sales Manager", source_system="OEM incentive bulletin",
        access="manual_governed", file_kind="manual", cadence="on_change", snapshot_capability="none",
        identity_keys=("policy_key",), effective_time="incentive effective date (Phase 3 effective dating)",
        update_time="bulletin date", schema_version=1, required_fields=("policy_key",),
        absence_behavior="policy resolves through Phase 3; absence never invents a default",
        domain="policy", fact_type="", entity_kind="policy"),
    "user_authority_config": SourceContract(
        key="user_authority_config", owner="Dealer Principal", source_system="Elite authority admin",
        access="manual_governed", file_kind="manual", cadence="on_change", snapshot_capability="none",
        identity_keys=("principal_id", "capability", "scope"),
        effective_time="grant time (Phase 1 authorization)", update_time="grant/revocation time",
        schema_version=1, required_fields=("principal_id", "capability", "scope"),
        domain="governance", fact_type="", entity_kind="principal"),
    "market_value_residual": SourceContract(
        key="market_value_residual", owner="Used Car Manager", source_system="Third-party valuation (where authorized)",
        access="operator_upload", file_kind="csv", cadence="weekly", snapshot_capability="partial",
        identity_keys=("vin",), effective_time="valuation date", update_time="feed date", schema_version=1,
        required_fields=("vin", "value"), optional_fields=("residual", "source"),
        raw_retention="raw preserved; optional + only where authorized", domain="new_inventory",
        fact_type="market_value", entity_kind="vehicle"),
    # A real DMS inventory/pipeline SUMMARY export (workbook). This captures incoming + current inventory
    # rows as retained Source Observations only: it is deliberately NOT authoritative vehicle_present data
    # and asserts NO physical (VIN) identity. Serial is lifecycle-dependent (order number before
    # serialization; VIN last-six after) and cannot be classified from this file alone, so every row is
    # preserved with serial_semantic left UNRESOLVED. stock_number is NOT an identity key here (real exports
    # reuse placeholders such as "75" across many distinct vehicles), so rows never collapse on Stock#.
    # entity_kind is a non-vehicle/non-order label whose no-VIN rows always resolve UNRESOLVED, so ingestion
    # creates neither ProductionOrder nor VehicleUnit — pure observation capture pending later enrichment.
    "new_inventory_pipeline_summary": SourceContract(
        key="new_inventory_pipeline_summary", owner="Inventory Manager", source_system="DMS",
        access="operator_upload", file_kind="xlsx", cadence="daily", snapshot_capability="partial",
        identity_keys=(), effective_time="production/ETA columns (not import date)",
        update_time="export date", schema_version=1,
        # stock_number is NOT required: the real DMS legitimately emits blank Stock# for both incoming (ONS)
        # and even some in-stock (DLR-INV) vehicles. Blank is a normal pipeline state, retained as-is, never
        # fabricated, never identity-bearing. model stays required.
        required_fields=("model",),
        optional_fields=("stock_number", "serial", "serial_semantic", "status", "model_year", "model_code",
                         "description", "trans", "ext", "int", "msrp", "inv", "location", "dis", "eta",
                         "production_month"),
        serial_lifecycle=True,
        blocking_validation=("missing_required_field", "malformed_row"),
        nonblocking_validation=("extra_unknown_column",),
        header_aliases={"Stock#": "stock_number", "Serial": "serial", "Status": "status", "MY": "model_year",
                        "Model Line": "model", "Model Code": "model_code", "Description": "description",
                        "Trans": "trans", "Ext": "ext", "Int": "int", "MSRP": "msrp", "Inv": "inv",
                        "Location": "location", "DIS": "dis", "ETA": "eta", "Production Month": "production_month"},
        sheet="vehicleInventorySummary0", stock_number_is_identity=False,
        # Recurring longitudinal-memory source: dedup by (source, scope, local business date, content hash)
        # so an identical export on a later business day is retained as a new snapshot, not swallowed as a
        # pure content replay (America/Chicago; observation time resolved as-of -> receipt -> import time).
        snapshot_idempotency="content_hash_per_business_date",
        raw_retention="original workbook retained via FileIntake; rows retained as Source Observations",
        domain="new_inventory", fact_type="", entity_kind="inventory_pipeline_record"),
}


def get_contract(key):
    return SOURCE_CONTRACTS.get(key)


def contract_summary():
    """Discovery view: one safe row per contract (no data, only the contract shape)."""
    out = []
    for c in SOURCE_CONTRACTS.values():
        out.append({
            "key": c.key, "owner": c.owner, "system": c.source_system, "access": c.access,
            "file_kind": c.file_kind, "cadence": c.cadence, "snapshot": c.snapshot_capability,
            "identity_keys": list(c.identity_keys), "domain": c.domain,
            "required_fields": list(c.required_fields), "schema_version": c.schema_version,
        })
    return out
