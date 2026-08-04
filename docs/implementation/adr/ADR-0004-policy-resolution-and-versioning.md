# ADR-0004 — Policy resolution and calculation versioning

- **Status:** Accepted (Phase 3)
- **Owning segments:** 05 (Policy/configuration/effective dating), 06 (Calculation
  versioning/reproducibility), 11 (Governance)

## Decisions
1. **Immutable, versioned, effective-dated policy.** A Policy Version's `value` is
   immutable (DB trigger blocks any value change) and undeletable (trigger blocks
   deletes). Change is expressed only by a new version + a lifecycle transition, so the
   original-as-known is always inspectable. Optimistic concurrency (`version` column)
   guards every lifecycle update.
2. **Lifecycle governs activation, not approval.** Approval records who/when but never
   activates a future-effective version; activation is refused before the effective time.
   Expiration removes a version from *current* resolution while leaving it resolvable
   *historically*. Revocation, rejection, and withdrawal remove a version from resolution;
   supersession and correction preserve and link the prior record.
3. **Deterministic resolution — never recency or insertion order.** Precedence is by
   explicit rules: scenario-vs-official → active lifecycle → effective time → scope match →
   subject specificity → approved precedence → conflict. A newer recorded time never
   automatically overrides a more appropriate effective-dated policy. Equally-applicable
   distinct authorities with no approved precedence yield an explicit `CONFLICTING`; the
   system never silently picks one.
4. **Fallback only when declared.** If no version applies, resolution returns the family's
   declared fallback (`broad_fallback` / `default_version`) or `UNRESOLVED`. The system
   never invents a value.
5. **Financial assumptions are typed policy records, not constants.** Each carries a typed,
   unit-validated value (percentage requires a denominator; currency requires a code). Zero
   is valid; blank/missing never silently becomes zero. Technical configuration
   (`CALCULATION_CONFIGURATION`) is a separate category and does not act as business policy.
6. **Behavior change requires a distinct calculation version.** Synthetic version-keyed
   behavior proves this; a reproducibility package pins every version + input reference so
   `replay` reproduces the identical output, and a current recalculation under a new version
   does not rewrite a prior issued result. Model, Identity-Rule, and Comparison-Specification
   versions are registered-until-activated foundations (no pairing executed in Phase 3).
7. **Scenario overrides are isolated and governed.** A scenario override resolves only inside
   its scenario, never changes official policy, and never becomes active official policy
   merely by existing or by being shared. Creating one is a governed action requiring the
   `scenario.override` capability; promotion to official policy would be a separate governed
   action, deliberately not provided in Phase 3.
8. **Every governed change is atomic with its audit.** Lifecycle transitions and override
   creation bind the business write to an Audit Event in one transaction (reusing the Phase 1
   Governor); a required audit failure rolls the whole action back. Activation and rollback
   are recorded in append-only history so a later change is always traceable.

## Why
Trustworthy calculations require a governed, versioned, effective-dated policy foundation
*before* any domain math. Modeling immutability, deterministic resolution, explicit
conflict, declared-only fallback, and reproducibility is the smallest correct way to make
later domain results explainable, reproducible, and auditable.

## Consequences
- Storage is JSON-in-SQLite behind repository methods (replaceable).
- No domain business rule is implemented; synthetic calculation behaviors exist only to
  prove version resolution + reproducibility.
- Migration v3 is appended and rerun-safe; v1/v2 are unchanged.
