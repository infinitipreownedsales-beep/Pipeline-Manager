# PHASE 2 — Data Model, Source Contracts, and Migration

## Migration v2 (`data_identity_facts`)
Appended after v1 (v1 unchanged, so Phase 1 data stays valid). Rerun-safe (tracked
in `migration_record`; applies only pending versions). Tables:

- `source_registry`, `schema_profile` — sources and their contracts.
- `import_payload` — raw payload text keyed by checksum (raw preservation + replay identity).
- `import_batch` — batch lifecycle + reconciliation counts.
- `source_observation` — raw + normalized values, validation/identity/acceptance status, provenance.
- `vehicle_unit`, `production_order`, `entity_alias` — canonical identity + aliases.
- `identity_evidence` — evidence + resolution outcome (matched/created/distinct/unresolved/conflicting/corrected/superseded).
- `business_fact` (+ `business_fact_no_delete` trigger) — append-preserving facts with correction/supersession/reversal links.
- `reconciliation_result` — one outcome per source row (+ absence signals).

## Source Contract / Schema Profile model
A `schema_profile` declares **shape and meaning only** (never downstream business
calculations): `fields` (name / required / kind / meaning), `snapshot_capable`,
`full_snapshot_requirements`, `scope_rules`, `effective_time_rule`,
`compatibility_status`. Value kinds: `text | upper | int | number | bool | date |
month | vin`. The runtime **source-contract registry** is the `source_registry` +
`schema_profile` tables. Example profiles registered by the Phase 2 fixtures:

| Source | Authoritative fact types | Snapshot-capable | Profile |
|---|---|---|---|
| `src_dms` (DMS Vehicle Export) | `vehicle_present` | yes | `prof_dms_v1` (stock_number*, vin, model*, production_month, mileage) |
| `src_feed` (Ad-hoc Feed) | — (none) | no | `prof_feed_v1` (same fields) |

(*required. These are synthetic fixtures; real sources are registered at runtime.)

## Canonical entity registry (introduced in Phase 2)
| Entity | Identity basis | Notes |
|---|---|---|
| Source Observation | internal id | raw + normalized; not a fact |
| Vehicle Unit | valid accepted VIN, store-scoped | stock/config never establish identity |
| Production Order | manufacturer order id, store-scoped | distinct per order id; pre-VIN → later single-unit link |
| Business Fact | internal id | append-preserving; current/superseded/reversed |
| Identity Evidence | internal id | resolution outcome + lineage |
| Reconciliation Result | internal id | one per row (+ absence signals) |

All internal ids are opaque and separate from VIN / stock / order / source-row id.

## Raw preservation
`source_observation.raw_values` holds the received row verbatim; the full payload
text is stored once in `import_payload` (checksummed) and reused for idempotent
replay. Normalized values are computed alongside and remain separately inspectable.
