# PHASE 3 POLICY / VERSIONING MODEL (migration v3)

New tables added by migration v3 `policy_and_versioning` (appended; v1/v2 unchanged).
All payloads are JSON-in-SQLite behind repository methods (`policy/store.py`). Records are
append-preserving; DB triggers enforce value-immutability and no-delete on policy versions.

## Records
| Table | Purpose | Key invariants |
|---|---|---|
| `policy_family` | Governs a class of policy values | Category (taxonomy), declared `allowed_scope_dimensions`, `default_resolution`, `approval_required` |
| `policy_version` | An immutable, effective-dated policy value | `value` immutable (trigger); no delete (trigger); `version` column for optimistic concurrency; lifecycle status; effective window (inclusive/exclusive); `is_scenario`/`scenario_id`; supersedes/superseded_by/correction_of/revocation |
| `calculation_family` | Governs a class of calculations | purpose; input/output contract versions; determinism; required policy families |
| `calculation_version` | A versioned calculation behavior | semver; impl_revision; lifecycle; supersedes/superseded_by/rollback_of; `version` column |
| `model_version` | Model foundation | registered-until-activated; scope; activation; supersedes; validation status; rollback_ref |
| `identity_rule_version` | Identity-rule foundation | rule_family; entity_types; effective window; status |
| `comparison_specification_version` | Prediction↔observation comparison spec | prediction/observation/subject types; timing + matching rules; unit contract; status (no pairing executed in Phase 3) |
| `reproducibility_package` | Pins every version + input for a calculation result | refs (calc/policy/identity/model/comparison/scenario/inputs); dealership_tz; timestamp; implementation_revision; output_reference (checksum) |
| `version_activation_history` | Append-only activation record | target_type/id, action, actor, at, detail |
| `version_rollback_history` | Append-only rollback record | target_type, from_id, to_id, actor, at, reason |

## Taxonomy (`policy_family.category`)
`MANUFACTURER_POLICY`, `DEALERSHIP_POLICY`, `FINANCIAL_ASSUMPTION`,
`OPERATIONAL_CONSTRAINT`, `MANAGEMENT_PREFERENCE`, `CALCULATION_CONFIGURATION` (technical,
not business policy), `SCENARIO_OVERRIDE`, `CALIBRATION_CHANGE`.

## Lifecycle (`policy_version.lifecycle_status`)
`DRAFT → PROPOSED → UNDER_REVIEW → APPROVED → SCHEDULED → ACTIVE`, plus terminal
`EXPIRED`, `SUPERSEDED`, `REVOKED`, `REJECTED`, `WITHDRAWN`, `CORRECTED`. Only legal
transitions are permitted (`models.TRANSITIONS`). Non-resolving states:
`DRAFT/PROPOSED/UNDER_REVIEW/REJECTED/WITHDRAWN`.

## Resolution precedence (deterministic, `resolution.resolve`)
1. **Scenario vs official context** — scenario overrides apply only inside their scenario.
2. **Active lifecycle** — current resolution requires APPROVED/SCHEDULED/ACTIVE (and not
   revoked); historical resolution excludes only never-resolving states.
3. **Effective time** — the version's window must contain the query time.
4. **Scope match** — every declared scope dimension of the version must match the subject.
5. **Subject specificity** — more matched scope dimensions win.
6. **Approved precedence** — an explicit approved ordering breaks equal-specificity ties.
7. **Conflict** — equally-applicable distinct authorities with no approved precedence →
   explicit `CONFLICTING`. Newest-recorded never auto-wins.

Fallback is only what the family declares (`broad_fallback` / `default_version`); otherwise
`UNRESOLVED`. The system never invents a value.

## Governance
Lifecycle transitions and scenario-override creation are **governed actions**: authorized
below the UI (`authz`), executed atomically with their Audit Event (`governance.Governor`),
optimistic-concurrency checked (stale ⇒ `ConcurrencyError`), and idempotent under a retry
key. A required audit-write failure rolls back the business write.
