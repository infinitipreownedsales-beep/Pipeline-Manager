# PHASE 3 COMPLETION PACKET — Policy, Configuration, Effective Dating, and Calculation Versioning

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/policy/` (+ migration v3 in `elite/db.py`); no legacy file changed.

## Implemented
A governed, versioned, effective-dated, auditable policy + calculation foundation —
built **before** any domain calculation:

- **Policy Family / Policy Version** with an immutable value payload (DB triggers block
  value mutation and deletion) and optimistic concurrency on lifecycle updates.
- **Taxonomy** — Manufacturer / Dealership policy, Financial Assumption, Operational
  Constraint, Management Preference, Calculation Configuration (technical, *not* business
  policy), Scenario Override, Calibration Change — kept distinguishable.
- **Effective dating** (UTC internal; dealership-tz boundary conversion for presentation),
  inclusive/exclusive window boundaries.
- **Lifecycle** — DRAFT → PROPOSED → UNDER_REVIEW → APPROVED → SCHEDULED → ACTIVE, plus
  EXPIRED / SUPERSEDED / REVOKED / REJECTED / WITHDRAWN / CORRECTED, with legal-transition
  enforcement. Approval **never** auto-activates a future-effective version; activation is
  refused before the effective time.
- **Supersession, revocation, rejection/withdrawal, correction lineage** — all
  append-preserving; the original-as-known is never overwritten.
- **Deterministic resolution** — precedence by explicit rules
  (scenario-vs-official → active lifecycle → effective time → scope match → specificity →
  approved precedence → conflict). Newest-recorded **never** auto-wins; equally-applicable
  distinct authorities resolve to an explicit CONFLICTING; fallback is only what the family
  declares (the system never invents a value).
- **Typed financial assumptions** — unit/denominator validated; zero is valid; blank/missing
  never silently becomes zero; percentages must name a denominator.
- **Calculation Family / Version, Model Version, Identity-Rule Version, Comparison-Specification
  Version foundations** — registered-until-activated; behavior change requires a distinct
  version.
- **Reproducibility package** pinning all version + input references; **replay** reproduces the
  identical output; a current recalculation under a new version does not rewrite a prior issued
  result.
- **Scenario override isolation** — a what-if value resolves only inside its scenario, never
  changes official policy, and never activates merely by existing or being shared. Creating one
  is a governed action requiring `scenario.override`.
- **Version activation / rollback history** — append-preserving; rollback marks the prior
  version `rolled_back` (never deletes) and re-activates the restored version.
- Deterministic fixtures + tests.

**No** domain calculation, and **no** Demand / Need / forecasting / CPO / PPO / Dealer Trade /
CTP / Service Loaner / Executive Demo / Prediction pairing / Learning / broad UI. Synthetic
policy/calculation values only — no real incentives, allowances, write-downs, or windows.

## Acceptance evidence (59 mandatory tests, all executed)
| # | Requirement | Test |
|---|---|---|
| 1 | Policy Family survives restart | `test_phase3_policy.test_01` |
| 2 | Policy Version survives restart | `test_phase3_policy.test_02` |
| 3 | Version value is immutable (trigger) | `test_phase3_policy.test_03` |
| 4 | Version cannot be deleted (trigger) | `test_phase3_policy.test_04` |
| 5 | DRAFT does not resolve | `test_phase3_policy.test_05` |
| 6 | PROPOSED does not resolve | `test_phase3_policy.test_06` |
| 7 | Approval never auto-activates a future version | `test_phase3_policy.test_07` |
| 8 | Activation rejected before effective time | `test_phase3_policy.test_08` |
| 9 | EXPIRED has no current resolution | `test_phase3_policy.test_09` |
| 10 | EXPIRED still resolves historically | `test_phase3_policy.test_10` |
| 11 | SUPERSEDED version remains inspectable | `test_phase3_policy.test_11` |
| 12 | REVOKED does not resolve | `test_phase3_policy.test_12` |
| 13 | REJECTED never resolves | `test_phase3_policy.test_13` |
| 14 | WITHDRAWN never resolves | `test_phase3_policy.test_14` |
| 15 | Correction preserves original | `test_phase3_policy.test_15` |
| 16 | More-specific scope overrides broader | `test_phase3_policy.test_16` |
| 17 | Scope does not leak across stores | `test_phase3_policy.test_17` |
| 18 | Unsupported scope dimension rejected | `test_phase3_policy.test_18` |
| 19 | Latest-recorded does not auto-win | `test_phase3_policy.test_19` |
| 20 | Equally-applicable conflict is explicit | `test_phase3_policy.test_20` |
| 21 | Approved fallback only when declared | `test_phase3_policy.test_21` |
| 22 | No applicable + no fallback → unresolved | `test_phase3_policy.test_22` |
| 23 | Technical config is not business policy | `test_phase3_policy.test_23` |
| 24 | Assumption type/unit validated | `test_phase3_policy.test_24` |
| 25 | Zero is a valid assumption value | `test_phase3_policy.test_25` |
| 26 | Blank is not silently zero | `test_phase3_policy.test_26` |
| 27 | Percentage requires denominator | `test_phase3_policy.test_27` |
| 28 | Dealership-tz date boundary → UTC | `test_phase3_policy.test_28` |
| 29 | Historical retains the version in force then | `test_phase3_policy.test_29` |
| 30 | Current uses the newer effective version | `test_phase3_policy.test_30` |
| 31 | Current recompute does not rewrite history | `test_phase3_policy.test_31` |
| 32 | Calculation Family survives restart | `test_phase3_versions.test_32` |
| 33 | Calculation Version survives restart | `test_phase3_versions.test_33` |
| 34 | Behavior change requires distinct version | `test_phase3_versions.test_34` |
| 35 | Activation recorded in history | `test_phase3_versions.test_35` |
| 36 | Rollback preserves versions + records history | `test_phase3_versions.test_36` |
| 37 | Model Version registered-until-activated | `test_phase3_versions.test_37` |
| 38 | Resolution references active Identity-Rule Version | `test_phase3_versions.test_38` |
| 39 | Prior identity rule + Phase-2 evidence unchanged | `test_phase3_versions.test_39` |
| 40 | Comparison Spec persists without pairing | `test_phase3_versions.test_40` |
| 41 | Reproducibility package pins all refs | `test_phase3_versions.test_41` |
| 42 | Replay reproduces the same output | `test_phase3_versions.test_42` |
| 43 | Version change is traceable | `test_phase3_versions.test_43` |
| 44 | Scenario override resolves only in scenario | `test_phase3_scenario_gov.test_44` |
| 45 | Scenario override never changes official | `test_phase3_scenario_gov.test_45` |
| 46 | Override does not leak into other scenarios | `test_phase3_scenario_gov.test_46` |
| 47 | Unauthorized override rejected | `test_phase3_scenario_gov.test_47` |
| 48 | Transition authorization enforced below UI | `test_phase3_scenario_gov.test_48` |
| 49 | Stale transition raises concurrency | `test_phase3_scenario_gov.test_49` |
| 50 | Idempotent retry has no double effect | `test_phase3_scenario_gov.test_50` |
| 51 | Governed action writes audit | `test_phase3_scenario_gov.test_51` |
| 52 | Required audit failure rolls back write | `test_phase3_scenario_gov.test_52` |
| 53 | Migration v3 applied | `test_phase3_scenario_gov.test_53` |
| 54 | Migrations are rerun-safe | `test_phase3_scenario_gov.test_54` |
| 55 | No domain symbols in policy package | `test_phase3_scenario_gov.test_55` |
| 56 | Financial values are policy records, not constants | `test_phase3_scenario_gov.test_56` |
| 57 | Legacy line untouched by Phase 3 | `test_phase3_scenario_gov.test_57` |
| 58 | Scenario override flagged + isolated | `test_phase3_scenario_gov.test_58` |
| 59 | Override creation is audited | `test_phase3_scenario_gov.test_59` |

**Platform harness:** `120/120 passed` (26 Phase 1 + 35 Phase 2 + 59 Phase 3).
**Legacy:** `39/39` (29 engine + 10 loaner).

## 23-item completion report
1. New `elite/policy/` package + migration v3; no legacy file changed.
2. Policy Family + immutable Policy Version (DB triggers enforce value-immutability and no-delete).
3. Full policy taxonomy implemented and kept distinguishable (8 categories).
4. Scope model with declared allowed dimensions; unsupported dimensions rejected at creation.
5. Effective dating with inclusive/exclusive window boundaries; internal UTC; dealership-tz
   boundary conversion for presentation.
6. Lifecycle state machine with legal-transition enforcement (12 states).
7. Approval records approval metadata but never auto-activates a future-effective version.
8. Scheduling / activation; activation refused before the effective time.
9. Expiration: no current resolution, but still resolvable historically.
10. Supersession: append-preserving; original-as-known preserved and linked.
11. Revocation honored by resolution (revoked ⇒ not current).
12. Rejection / withdrawal: never resolve (current or historical).
13. Correction lineage: a new corrective version is created; the original is marked CORRECTED
    and preserved unchanged.
14. Deterministic resolution precedence; newest-recorded never auto-wins.
15. Equally-applicable distinct authorities resolve to explicit CONFLICTING (no silent pick).
16. Approved fallback used only when the family declares it; otherwise UNRESOLVED — never invented.
17. Typed financial assumptions (unit/denominator validated; zero valid; blank ≠ zero; percentage
    requires denominator). Technical configuration is a separate category, not business policy.
18. Calculation Family / Version; behavior change requires a distinct version.
19. Model Version, Identity-Rule Version, Comparison-Specification Version foundations
    (registered-until-activated; no pairing executed in Phase 3).
20. Reproducibility package pinning all version + input references; replay reproduces the identical
    output; current recompute under a new version does not rewrite a prior issued result.
21. Scenario override isolation — governed creation (`scenario.override`), resolves only inside its
    scenario, never changes official policy, never activates by existing/sharing, tagged + audited.
22. Version activation / rollback history (append-preserving; rollback marks prior `rolled_back`,
    never deletes).
23. Deterministic fixtures + 59 acceptance tests; platform `120/120`, legacy `39/39`; legacy
    application paths byte-unchanged vs `legacy/inventory-tool` @ `3bf9162`.

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- BUG-CPO-002 remains **open** only as a later New-Inventory implementation / regression risk
  (unaffected by Phase 3).
- The synthetic calculation behaviors exist solely to prove version resolution + reproducibility;
  no domain formula is implemented. Promotion of a scenario override to official policy is a
  distinct governed action, deliberately **not** provided in Phase 3.

## Status
**HOLD FOR REVIEW.** Phase 4 not started.
