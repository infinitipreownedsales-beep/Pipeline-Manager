# IMPLEMENTATION LEDGER

Append-only log of implementation-control actions. Newest phase at the bottom.

## Phase 0 — Preservation and Audit  (branch `elite-pipeline/phase-0`, from `3bf9162`)

Actions taken:
1. Confirmed legacy stable point `3bf9162` (build + 39/39 tests + headless render all green; clean working tree).
2. Preserved legacy:
   - annotated tag `legacy-inventory-tool-1.0` → `3bf9162`;
   - protected branch `legacy/inventory-tool` → `3bf9162` (frozen);
   - recorded artifact SHA-256 `bc8972b4187a6178…` and reproducible build.
3. Created clean restart branch `elite-pipeline/phase-0` from `3bf9162` (legacy line unaltered).
4. Added canonical specification + audit + kickoff prompt under `docs/specification/`.
   - Spec SHA-256 `18b76b9f…`; verified structure: 17 segments (00–16) + ToC, 18 H1 / 1085 H2, 4,523 unique requirement IDs (matches accepted audit).
5. Generated machine-readable `docs/implementation/requirement_index.json` (4,523 IDs, segment + family attribution) and human-readable `REQUIREMENT_INDEX.md`.
6. Authored durable control artifacts: `IMPLEMENTATION_CONTROL.md`, `REPOSITORY_AUDIT.md`,
   `LEGACY_PRESERVATION.md`, `KNOWN_BUG_REGISTRY.md`, `IMPLEMENTATION_LEDGER.md`.
7. Captured known-correct behaviors and confirmed fixes (CPO goalposts / Need
   monotonicity FIXED; C1 pairing, Last Checkout Mileage, snapshot-absence recorded
   with honest Phase-0 status).
8. Verified no secrets in tracked source; env config isolated to git-ignored `config.json`.

Not done (out of Phase 0 scope, by contract): Phase 1 work, redesign, framework
selection, business-logic rewrite, new UI, requirement-ID→code binding, migration
of official truth out of browser-local storage.

Result: **Phase 0 evidence complete → HOLD FOR REVIEW.**
Approved next work unit: **Phase 1 (Preservation-safe implementation start), only after review.**

## Phase 1 — Platform Foundation  (branch `elite-pipeline/phase-0`)

Control-record corrections first: reclassified BUG-CPO-002 from "specification
blocker" to "implementation defect / regression risk" and recorded the canonical
resolution (Demand independent of supply method; CPO a distinct supply workflow;
approved CPO creates a discrete unit-level Commitment counted once; continuous
replenishment must not impersonate a commitment; added qualifying Supply must not
raise Need under unchanged Demand inputs and window). Demand engine NOT redesigned.

Implemented the smallest authoritative platform seed as a NEW `elite/` package
(Python stdlib + SQLite; ADR-0001/0002), touching no legacy file:
- environment identity (explicit; no default), validated config with safe startup
  failure, secret hygiene (env-only, redacted);
- stable IDs, controlled UTC clock + dealership presentation;
- typed errors with correlation IDs;
- repository contracts + durable SQLite persistence; tracked migrations;
  idempotency; optimistic concurrency;
- authentication (identity only) separate from authorization
  (Principal/Capability/Authority/Scope/effective grant), enforced below the UI;
- append-only Audit Events (DB-trigger enforced), distinct from Business/Actual
  facts; governed actions binding business write + audit atomically (no success
  without audit);
- structured logging distinct from audit; deterministic test harness + fixtures.

Evidence executed: platform harness **26/26**; legacy suite **39/39**; legacy
application paths byte-unchanged vs `legacy/inventory-tool` @ `3bf9162`. All 22
mandatory acceptance items pass (see PHASE1_COMPLETION.md).

Docs: PHASE1_COMPLETION.md, PHASE1_TRACEABILITY.md, RUN_INSTRUCTIONS.md,
adr/ADR-0001, adr/ADR-0002; updated IMPLEMENTATION_CONTROL.md and KNOWN_BUG_REGISTRY.md.

Result: **Phase 1 complete → HOLD FOR REVIEW.** Next: Phase 2 only after review.

## Phase 2 — Data, Identity, and Accepted Facts  (branch `elite-pipeline/phase-0`)

Control records: Phase 1 recorded approved; Phase 2 set active then complete.
BUG-CPO-002 kept open only as a later-domain implementation/regression risk.

Implemented a NEW `elite/data/` package + migration v2 (appended; v1 unchanged),
touching no legacy file:
- Source Registry, Source Contract/Schema Profile (shape+meaning only), Import Batch;
- Source Observation with raw preservation + separate normalization; distinct value
  sentinels (missing/blank/zero/false/na/unknown/invalid/unresolved/conflicting);
- Full/Partial snapshot classification (contract-driven; absence = scoped signal only);
- Vehicle Unit + Production Order identity (VIN-only unit identity; order-id-only order
  identity; pre-VIN→single-unit link; scope isolation; corrections preserve prior);
- Identity Evidence + resolution outcomes;
- Business Facts under source authority (fact-type + scope), append-preserving with
  correction/supersession/reversal; deterministic current-state projection + conflict;
- Reconciliation (one outcome per row; counts balance; absence signals);
- deterministic fixtures (21 source cases, 14 identity cases) + tests.

Evidence executed: platform harness **61/61** (26 Phase 1 + 35 Phase 2); legacy suite
**39/39**; migration v2 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 38 mandatory acceptance items pass
(PHASE2_COMPLETION.md).

Docs: PHASE2_COMPLETION, PHASE2_TRACEABILITY, PHASE2_DATA_MODEL, adr/ADR-0003;
updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note).

Result: **Phase 2 complete → HOLD FOR REVIEW.** Next: Phase 3 only after review.

## Phase 3 — Policy, Configuration, Effective Dating, and Calculation Versioning  (branch `elite-pipeline/phase-0`)

Control records: Phase 2 recorded approved; Phase 3 set active then complete. BUG-CPO-002
kept open only as a later New-Inventory implementation/regression risk.

Implemented a NEW `elite/policy/` package + migration v3 (appended; v1/v2 unchanged),
touching no legacy file:
- Policy Family + immutable, effective-dated Policy Version (DB triggers enforce
  value-immutability + no-delete; optimistic concurrency on lifecycle);
- taxonomy (8 categories, technical config kept distinct from business policy);
- scope model with declared allowed dimensions (unsupported dimensions rejected);
- lifecycle state machine (DRAFT→PROPOSED→UNDER_REVIEW→APPROVED→SCHEDULED→ACTIVE plus
  EXPIRED/SUPERSEDED/REVOKED/REJECTED/WITHDRAWN/CORRECTED) with legal-transition enforcement;
  approval never auto-activates a future version; activation refused before effective time;
- supersession/revocation/rejection/withdrawal + correction lineage (append-preserving);
- deterministic resolution (scenario-vs-official → active lifecycle → effective time → scope
  → specificity → approved precedence → conflict); newest-recorded never auto-wins; explicit
  CONFLICTING; declared-only fallback (never invents a value);
- typed financial assumptions (unit/denominator; zero valid; blank ≠ zero);
- Calculation Family/Version + Model/Identity-Rule/Comparison-Spec version foundations
  (registered-until-activated; behavior change requires a distinct version);
- reproducibility package pinning all refs + replay (identical output); current recompute
  does not rewrite a prior issued result;
- governed Scenario-override isolation (`scenario.override`; resolves only in scenario; never
  changes official; never activates by existing/sharing; audited);
- version activation/rollback history (append-preserving; rollback marks prior `rolled_back`);
- deterministic fixtures + 59 acceptance tests.

Evidence executed: platform harness **120/120** (26 P1 + 35 P2 + 59 P3); legacy suite
**39/39**; migration v3 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 59 mandatory acceptance items pass
(PHASE3_COMPLETION.md).

Docs: PHASE3_COMPLETION, PHASE3_TRACEABILITY, PHASE3_POLICY_MODEL, adr/ADR-0004;
updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note).

Result: **Phase 3 complete → HOLD FOR REVIEW.** Next: Phase 4 only after review.

## Phase 3 review disposition — APPROVED

Phase 3 (policy/configuration/effective-dating/calculation-versioning; `elite/policy/` +
migration v3) reviewed and **approved**. Recorded here and in IMPLEMENTATION_CONTROL.md.
Legacy line preserved at `3bf9162`. BUG-CPO-002 carried forward as a Phase 4 implementation /
regression risk (New Inventory Need must not rise when qualifying Supply is added under
unchanged Demand inputs and window).

## Phase 4 — New Inventory Foundation  (branch `elite-pipeline/phase-0`)  [ACTIVE]

Control records: Phase 3 recorded approved; Phase 4 set active. Building the authoritative
New Inventory planning foundation in specification order on the Phase 1-3 platform/fact/
identity/policy/calculation-version/reproducibility foundations, appending migration v4
(v1-v3 unchanged), touching no legacy file. Objective: Sellable Combination → Current/Future/
Committed Supply → historical retail → availability reconstruction → Demand baseline
(independent of acquisition/supply method) → seasonality/trend → lineage → month-by-month
forecast → desired ending coverage (policy-resolved) → Need → Excess → portfolio reconciliation
→ confidence/evidence explanation → first operational output slice. Proves Demand-independence
and monotonic qualifying Supply, and carries a dedicated BUG-CPO-002 regression. No second
Demand calculation inside any supply workflow; no Phase-5 workflows / CPO / PPO / Dealer Trade /
CTP / Service Loaner / Executive Demo / Learning / full Governance / broad UX.

Implemented a NEW `elite/newinv/` package + migration v4 (appended; v1-v3 unchanged), touching
no legacy file: Sellable Combination (canonical identity from demand-material dims; scope-isolated;
correction-preserving) + alias + lineage/comparability; Current/Future/Committed Supply projections
with count-once qualifying-supply dedup; historical retail (accepted facts only, dedup, correction/
reversal preserving); availability reconstruction (available≠unavailable, partial invents no
continuity, stockout fabricates no lost sales, gaps reduce confidence); one supply-blind Demand
contract (evidence hierarchy exact>inherited, bounded seasonality/trend, reproducibility+replay);
month-by-month forecast with combination→model→portfolio reconciliation; policy-resolved desired
ending coverage (unresolved when missing); deterministic month-aware Need/Excess (≥0, not both
positive, monotone in qualifying supply, later arrival can't satisfy earlier month); portfolio
aggregation that never recomputes Demand; first operational output slice (Call/Why/Proof/…);
40 dealership-representative fixtures.

Evidence executed: platform harness **185/185** (26 P1 + 35 P2 + 59 P3 + 65 P4); legacy suite
**39/39**; migration v4 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 63 mandatory acceptance items pass, plus the dedicated
10-point BUG-CPO-002 regression + monotonicity ladder (PHASE4_COMPLETION.md).

Docs: PHASE4_COMPLETION, PHASE4_TRACEABILITY, PHASE4_DOMAIN_MODEL, PHASE4_REGISTRIES,
adr/ADR-0005..0008; updated IMPLEMENTATION_CONTROL, KNOWN_BUG_REGISTRY, RUN_INSTRUCTIONS,
REQUIREMENT_INDEX (note).

Result: **Phase 4 complete → HOLD FOR REVIEW.** Next: Phase 5 only after review.

## Phase 4 review disposition — APPROVED

Phase 4 (New Inventory foundation; `elite/newinv/` + migration v4) reviewed and **approved**.
Recorded here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. BUG-CPO-002
carried forward **open** until the real CPO workflow (Phase 5) proves the Phase 4 Demand and
monotonic-Supply contracts end-to-end.

## Phase 5 — Production and Supply Workflows  (branch `elite-pipeline/phase-0`)  [ACTIVE]

Control records: Phase 4 recorded approved; Phase 5 set active. Building the governed production +
acquisition workflows (production pipeline, ETA/arrival windows, editability, model-year transition,
Incoming Risk, CPO, PPO, Dealer Trade, CTP, sequential recomputation, commitment reconciliation,
integrated forecast updates, execution/outcome foundations, operational workflow slices) on the
Phase 1 authz/audit, Phase 3 policy, and Phase 4 Demand/Supply/Need/Excess/forecast/commitment/
reproducibility contracts, appending migration v5 (v1-v4 unchanged), touching no legacy file. Every
workflow consumes the authoritative Phase 4 Need contract and defines no separate Demand; carries a
dedicated end-to-end BUG-CPO-002 regression. No Service Loaner / Executive Demo / Pairing / Learning
/ completed Phase-9 Governance / full UX / operational hardening / migration-cutover.

Implemented a NEW `elite/workflow/` package + migration v5 (appended; v1-v4 unchanged), touching
no legacy file: production-pipeline projection (order identity stable; pre-VIN→VIN one unit;
conflicts explicit; cancelled emits no qualifying future supply); ETA/arrival-window interpretation
(precision ≤ evidence; conservative cross-month; unknown/stale not confident supply; revisions
preserved); editability (unknown ≠ editable); model-year transition (preserves identity); Incoming
Risk (component-explained, never one opaque score); the common governed workflow lifecycle (Phase 1
Governor: authz + atomic audit + optimistic concurrency + idempotency); CPO, PPO, Dealer Trade, CTP
workflows (all consume Phase 4 Need, none compute Demand; discrete count-once commitments; CTP moves
one future unit between combinations without a duplicate order); commitment reconciliation (10
outcomes); sequential recomputation (recompute-after-each; suppress unnecessary; no double-select);
integrated forecast updates (new plan preserving prior, causing action identified); operational
workflow slices; 50 dealership-representative fixtures.

Supply effects flow through Phase 4 Supply/commitment records via raw inserts on the governed
connection, so count-once and monotonicity hold end-to-end. The dedicated 15-point end-to-end
BUG-CPO-002 regression (`test_phase5_bug_cpo_002_e2e.py`) passes together with the Phase 4 regression
→ BUG-CPO-002 recorded **FIXED_END_TO_END** (retained permanently in the regression registry).

Evidence executed: platform harness **266/266** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5); legacy
**39/39**; migration v5 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 78 mandatory acceptance items pass (PHASE5_COMPLETION.md).

Docs: PHASE5_COMPLETION, PHASE5_TRACEABILITY, PHASE5_DOMAIN_MODEL, PHASE5_REGISTRIES,
adr/ADR-0009..0013; updated IMPLEMENTATION_CONTROL, KNOWN_BUG_REGISTRY, RUN_INSTRUCTIONS,
REQUIREMENT_INDEX (note).

Result: **Phase 5 complete → HOLD FOR REVIEW.** Next: Phase 6 only after review.

## Phase 5 review disposition — APPROVED

Phase 5 (production/supply workflows; `elite/workflow/` + migration v5) reviewed and **approved**.
Recorded here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. BUG-CPO-002 is
**FIXED_END_TO_END** (Phase 4 synthetic + Phase 5 end-to-end regressions both green), retained
permanently in the regression registry.

## Phase 6 — Service Loaner Domain  (branch `elite-pipeline/phase-0`)  [ACTIVE]

Control records: Phase 5 recorded approved; Phase 6 set active. **Scope corrected: Phase 6 is
Service Loaner ONLY — Executive Demo is deferred to Phase 7 and is not built here.** Building the
complete Service Loaner bounded domain (active-fleet Full Snapshot + membership reconciliation;
Service Loaner Unit + lifecycle; in-service-date authority; Last Checkout Mileage; zero-mile-rented
monitoring; versioned Economic Call separate from Execution Status; entry portfolio optimization;
retirement/provisional/return/final; Used Cars idempotent-receipt handoff; return-to-retail
reconciliation; scenario exploration; resale/outcome foundations; operational output slices) on the
Phase 1-5 identity/facts/policy/supply/planning/commitment/workflow/governance/audit foundations,
appending migration v6 (v1-v5 unchanged), touching no legacy file. Strict domain separation from
Executive Demo, New Retail Demand, generic acquisition ranking, production workflow, CPO/PPO, and
Used Cars before confirmed handoff. Carries a dedicated 14-point zero-mile-rented monitoring
regression. No Executive Demo / Pairing / Learning / completed Phase-9 Governance / full UX /
operational hardening / migration-cutover.

Implemented a NEW `elite/loaner/` package + migration v6 (appended; v1-v5 unchanged), touching no
legacy file: authoritative active-fleet Full Snapshot + membership reconciliation by VIN (via Phase 2
ingestion, raw preserved; only a valid Full Snapshot supports absence, and absence is a review signal
only); Service Loaner Unit + governed lifecycle (Vehicle Unit identity never replaced; approval ≠
execution; execution establishes membership once; rental separate from membership); in-service-date
authority (verified controls tenure; import date never substitutes; conflicts unresolved; corrections
preserved); Last Checkout Mileage (zero≠blank≠missing≠invalid; supersede preserves history);
zero-mile-rented monitoring (approved prompt; idempotent; clears on not-rented/nonzero; no invented
location/mileage); versioned Economic Call separate from Execution Status (incremental exit economics,
no sunk-cost reapplication); entry portfolio optimization (need resolved separately; explainable;
opportunity cost an input; no double-select); retirement/provisional/return/final; Used Cars single
idempotent immutable receipt (auto Principal+time; no checklist; cannot precede retirement; creates no
New Retail supply); return-to-retail reconciliation (restores Current Supply once; existing prevents
duplication); scenario exploration (isolated; identifies overrides; no official change);
resale/outcome foundations; operational output slices; 60 dealership-representative fixtures.

Evidence executed: platform harness **345/345** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6);
legacy **39/39**; migration v6 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 89 mandatory acceptance items pass, plus the dedicated
14-point zero-mile-rented monitoring regression (PHASE6_COMPLETION.md).

Docs: PHASE6_COMPLETION, PHASE6_TRACEABILITY, PHASE6_DOMAIN_MODEL, PHASE6_REGISTRIES,
adr/ADR-0014..0017; updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note).

Result: **Phase 6 complete → HOLD FOR REVIEW.** Next: Phase 7 (Executive Demo) only after review.

## Phase 6 review disposition — APPROVED

Phase 6 (Service Loaner domain; `elite/loaner/` + migration v6) reviewed and **approved**. Recorded
here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. Service Loaner is a
completed, separate bounded domain and is not modified by later phases. BUG-CPO-002 remains
FIXED_END_TO_END (permanent regression coverage).

## Phase 7 — Executive Demo Domain  (branch `elite-pipeline/phase-0`)  [COMPLETE — HOLD FOR REVIEW]

Control records: Phase 6 recorded approved; Phase 7 set active. Building the complete Executive Demo
bounded domain (current portfolio + need; eligibility + candidate construction; Best Overall
portfolio-selection; model preference via Phase 3; versioned New Retail opportunity cost consuming
Phase 4 planning; expected lifecycle; designation propose/approve/execute; versioned Economic Call
separate from Execution Status; retirement/return-to-retail/Used-Cars handoff; committed portfolio
updates; scenario exploration; resale foundations; output slices) on the Phase 1-6 foundations,
appending migration v7 (v1-v6 unchanged), touching no legacy file. **Executive Demo is a SEPARATE
package (`elite/execdemo/`) — the two fleet domains are NOT generalized into one shared engine;
Service Loaner records are untouched.** Carries a dedicated 14-point Best Overall regression. No
Prediction/Observation Pairing / Learning / completed Phase-9 Governance / full UX / operational
hardening / migration-cutover.

Evidence executed: platform harness **424/424** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 +
79 P7); legacy **39/39**; migration v7 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 90 mandatory acceptance items pass, plus the dedicated
14-point Best Overall regression (PHASE7_COMPLETION.md). Best Overall proven to select the strongest
full-objective candidate — not the cheapest and not the highest-benefit; designation execution removes
New Retail Current Supply once and return-to-New-Retail restores it once; Used Cars receipt is a
separate, idempotent, immutable record; a unit cannot be active in both fleet domains.

Docs: PHASE7_COMPLETION, PHASE7_TRACEABILITY, PHASE7_DOMAIN_MODEL, PHASE7_REGISTRIES,
adr/ADR-0018..0021; updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note),
KNOWN_BUG_REGISTRY (note). Phase 6 migration-durability tests made version-agnostic (assert v6 present
and total ≥ 6) so appending v7 keeps them green — no Service Loaner behavior changed.

Result: **Phase 7 complete → HOLD FOR REVIEW.** Executive Demo and Service Loaner remain separate
bounded domains (no shared fleet engine). Next: Phase 8 only after review.

## Phase 7 review disposition — APPROVED

Phase 7 (Executive Demo domain; `elite/execdemo/` + migration v7) reviewed and **approved**. Recorded
here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. Executive Demo and Service
Loaner remain completed, separate bounded domains (no shared fleet engine) and are not modified by
later phases. BUG-CPO-002 remains FIXED_END_TO_END (permanent regression coverage).

## Phase 8 — Prediction, Observation, Error, Attribution, Learning, Calibration  (branch `elite-pipeline/phase-0`)  [COMPLETE — HOLD FOR REVIEW]

Control records: Phase 7 recorded approved; Phase 8 set active. Building the institutional-memory and
learning foundation (`elite/learning/`) that preserves and connects Prediction; Decision learning
context; Observation; an executable versioned Comparison Specification extending the Phase 3 registry;
Prediction-to-Observation Pairing; Error; Attribution; Learning Signal; Calibration Proposal +
review/approval/activation/rollback; versioned activation references; historical reproducibility;
confidence + uncertainty; cross-domain learning without domain collapse; and operational output slices.
Appends migration v8 (v1-v7 unchanged), touching no legacy file. All Phase 1-7 issued Predictions,
Decisions, economic/planning/workflow/Service-Loaner/Executive-Demo results are preserved as immutable
historical inputs. Comparison rules are versioned (Phase 3 foundation, not ad hoc). **Learning may
propose change but must NEVER activate it — no approved Calibration means no operational change;**
Learning/Calibration never automatically mutate active policy, calculations, thresholds, valuation,
permissions, or business behavior. Learning stays domain-aware (New Inventory / CPO / Service Loaner /
Executive Demo / Dealer Trade / CTP not collapsed into one universal scorer). Carries a dedicated
20-point learning-governance regression. No completed Phase-9 Governance / full Decision workspace /
broad Scenario administration / Phase-10 UX / operational hardening / migration-cutover.

Evidence executed: platform harness **515/515** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 +
79 P7 + 91 P8); legacy **39/39**; migration v8 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 90 mandatory acceptance items pass, plus the dedicated 20-point
learning-governance regression (PHASE8_COMPLETION.md). The end-to-end loop is proven: Prediction ->
Observation -> versioned Comparison Specification -> Pairing -> Error -> evidence-based Attribution ->
domain-aware Learning Signal -> Calibration Proposal -> validation -> approval -> authorized activation
of a new version -> optional rollback — with Learning able only to PROPOSE, historical Predictions never
rewritten, and no operational change without an approved, activated Calibration.

Docs: PHASE8_COMPLETION, PHASE8_TRACEABILITY, PHASE8_DOMAIN_MODEL, PHASE8_REGISTRIES,
adr/ADR-0022..0027; updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note),
requirement_index.json (note), KNOWN_BUG_REGISTRY (note). Added raw `insert_calc_version` /
`insert_model_version` helpers to the Phase 3 policy store so a governed Calibration activation creates
a new version atomically (the wrapped `add_*` methods are unchanged; no Phase 1-7 behavior changed).

Result: **Phase 8 complete → HOLD FOR REVIEW.** All Phase 1-7 domains remain separate, complete, and
unmodified; their issued results are immutable historical learning inputs. Next: Phase 9 only after
review.

## Phase 8 review disposition — APPROVED

Phase 8 (learning + calibration foundation; `elite/learning/` + migration v8) reviewed and **approved**.
Recorded here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. Learning remains a
propose-only layer (no operational change without an approved, activated Calibration); historical
Predictions/Decisions immutable; learning domain-aware. BUG-CPO-002 remains FIXED_END_TO_END.

## Phase 9 — Governance, Decision Workspace, Scenario Administration, Operational Control  (branch `elite-pipeline/phase-0`)  [COMPLETE — HOLD FOR REVIEW]

Control records: Phase 8 recorded approved; Phase 9 set active. Building the completed governed
operational-control surface over Phases 1-8 (`elite/govern/`): consolidated Decision Workspace (references,
never duplicates, authoritative domain output); recommendation review; governed Decision issuance + 9
dispositions; approval; execution authorization referencing Phase 5-7 domain execution (never duplicating
it) + Decision-to-execution reconciliation (15 outcomes); acknowledgment; expiration + staleness; broad
Scenario administration + sharing/review + promotion + policy-review requests; Calibration review
workspace over Phase 8 records/services; consolidated authority administration over Phase 1 grants +
delegation + temporary authority + revocation; separation-of-duties rules/exceptions/override;
consolidated Audit review; exception + unresolved queues; operational-control summaries; domain
launch-readiness views; and the smallest real governance output slices. Appends migration v9 (v1-v8
unchanged), touching no legacy file. All Phase 1-8 issued records, Decisions, Predictions, Observations,
economic/planning/workflow results, and Audit Events are preserved as immutable historical evidence. Uses
the Phase 1 Governor/authorization/scope/audit and Phase 8 Calibration governance — **no competing
governance framework, no second activation process; Phase 4-8 domain mathematics are not redefined.**
Executive Demo / Service Loaner / New Inventory / production workflow / learning-calibration remain
separate governed domains; no universal operational ranker replaces domain truth. Carries a dedicated
20-point governed-decision regression and a 14-point authority-administration regression. No full Phase-10
UX / broad visual design / operational hardening / live deployment / migration / cutover.

Evidence executed: platform harness **619/619** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 + 79 P7 +
91 P8 + 104 P9); legacy **39/39**; migration v9 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 113 mandatory acceptance items pass, plus the dedicated 20-point
governed-decision regression and the 14-point authority-administration regression (PHASE9_COMPLETION.md).
The governed loop is proven end to end: a domain recommendation → a workspace item that REFERENCES it →
review → governed Decision (idempotent, atomically audited, stale-guarded) → distinct-authority approval
under an enforced separation-of-duties rule → execution authorization referencing the actual Phase 5-7
domain execution → completion referencing the actual event → reconciliation COMPLETED → with stale/expiry
protection, Scenario isolation, authority delegation/temporary/revocation over the Phase 1 grants, and no
governance action rewriting any issued recommendation, Prediction, Observation, result, or historical
Decision.

Docs: PHASE9_COMPLETION, PHASE9_TRACEABILITY, PHASE9_DOMAIN_MODEL, PHASE9_REGISTRIES,
adr/ADR-0028..0034; updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note),
requirement_index.json (note), KNOWN_BUG_REGISTRY (note). Phase 9 added `elite/govern/` as a package
(the Phase 1 Governor remains `elite/governance.py`, unchanged and reused — no competing framework).

Result: **Phase 9 complete → HOLD FOR REVIEW.** Phases 1-8 remain complete, approved, and unmodified;
their issued records are immutable historical evidence. Next: Phase 10 only after review.

## Phase 9 review disposition — APPROVED

Phase 9 (governance + operational control; `elite/govern/` + migration v9) reviewed and **approved**.
Recorded here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. The governed
operational surface references authoritative domain output and reuses the Phase 1 Governor + Phase 8
Calibration governance (no competing framework, no second activation path, no redefinition of Phase 4-8
domain mathematics). BUG-CPO-002 remains FIXED_END_TO_END.

## Phase 10 — Operator Experience and Presentation Layer  (branch `elite-pipeline/phase-0`)  [COMPLETE — HOLD FOR REVIEW]

Control records: Phase 9 recorded approved; Phase 10 set active. Building the first complete
operator-facing Elite Pipeline application (`elite/ui/`) — a server-rendered presentation layer (stdlib
WSGI; no new dependencies) built strictly on the Phase 9 output slices and Phase 1-8 authoritative read
models: application shell, navigation, unified Decision Inbox, recommendation detail (Call/Why/Proof/Raw
History), New Inventory / Production & Supply / Service Loaner / Executive Demo workspaces, the governed
Decision-issuance experience, approval/execution/acknowledgment queues, Scenario administration,
Calibration review, authority administration, Audit review, exception + unresolved queues,
operational-control summaries, domain readiness, operator search, and durable presentation preferences
(migration v10 — presentation-only, non-authoritative). The interface READS authoritative records and
never recomputes domain logic; introduces no second business-logic layer; browser/localStorage state is
never authoritative; every mutation routes through the Phase 1-9 services; below-UI authorization + scope
are never bypassed. Safe templating + output encoding, CSRF for state-changing browser actions, session
context, correlation-ID preservation, double-submission prevention, no stack traces/secrets to operators.
Carries a dedicated 20-point operator-workflow regression and a 15-point presentation-integrity
regression. No Phase-11 operational hardening / live-source deployment / broad real-data migration /
cutover / legacy replacement.

Implemented a NEW `elite/ui/` package + migration v10 (appended; v1-v9 unchanged), touching no legacy
file: a server-rendered operator application on the Python **stdlib only** (`wsgiref`, `html`,
`http.cookies`, `secrets`, `urllib.parse`) — no third-party web framework, no new dependency. It is a
thin window over Phase 1-9 services: it reads authoritative records and recomputes no domain logic,
routes every mutation through the governed services, and holds no authoritative state in the browser.
Delivered: the application shell (name/environment, authenticated Principal, current store scope,
primary navigation, attention count, freshness + data-quality + current-revision indicators, help, a
safe error boundary, and unauthorized/out-of-scope/revoked states); a unified Decision Inbox over the
Phase 9 workspace records (counts reconcile to source; domain/status/priority filters; Scenario-only
and stale items visually distinct); a consistent recommendation-detail pattern (Call / Why / Proof /
Raw History evidence timeline; missing explanation stays *unknown*; official vs Scenario and current
vs historical distinguishable; no recompute); New Inventory / Production & Supply / Service Loaner /
Executive Demo workspaces (every number read from the Phase 4-7 stores — proposal vs committed,
membership vs rental, Economic Call vs Execution Status distinct; the zero-mile question verbatim;
Used Cars confirmed in one action; Best Overall shows why it wins with visible tradeoffs and a labeled
sacrifice; one physical unit counted once); the governed Decision-issuance experience (9 dispositions,
exact recommendation revision, presented alternatives, optional rationale, override-with-reason, stale
guard, per-render idempotency nonce → double-submit safe, Scenario-only); approval / execution /
acknowledgment queues (separate approval authority + visible separation-of-duties, approval ≠
execution, the real domain service invoked, a failed run never shown as completed, Scenario Decisions
cannot execute officially, idempotent replays, approval-expiry guard); Scenario administration;
Calibration review over Phase 8 records (approval ≠ activation); authority administration over the
Phase 1 grants (governed + audited, immediate revocation); read-only Audit review; exception +
unresolved queues (dismissal needs authority + reason; closing never resolves source); operational-
control summaries (reconcile to source); domain readiness (evidence-based; synthetic-only
insufficient; never deploys); operator search (scope-filtered, links to authoritative detail); and
durable presentation preferences (migration v10 — presentation-only, non-authoritative, freely
deletable, no immutability triggers; deleting them changes no Decision/approval/execution/policy/
identity/supply/Demand/Need/Economic-Call/governance state). Safe templating with output encoding
everywhere, a strict CSP + `X-Frame-Options: DENY`, `HttpOnly`/`SameSite=Strict` server-side sessions,
a `_csrf` token on every non-public state-changing action, correlation-ID preservation across the
governed call chain, and a safe error boundary that never leaks a stack trace or secret.

Evidence executed: platform harness **717/717** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 +
79 P7 + 91 P8 + 104 P9 + 98 P10); legacy **39/39** (29 engine + 10 loaner); migration v10 rerun-safe
(presentation-only, re-application leaves the applied-count at 10 and every table freely deletable);
legacy application paths byte-unchanged vs `legacy/inventory-tool` @ `3bf9162`. All 121 mandatory
acceptance items pass, plus the dedicated 20-point operator-workflow regression and the 15-point
presentation-integrity regression (PHASE10_COMPLETION.md). The full operator loop is proven through
the real routes and services: open inbox → open an authoritative recommendation → Call/Why/Proof/Raw
History → issue an audited Decision → a separate approver approves under an enforced separation-of-
duties rule → approval does not execute → an authorized executor drives the real domain service
returning an actual event → completion + reconciliation shown → repeated submission does not duplicate
→ a new fact makes the recommendation stale → stale cannot execute → an authorized override requires a
reason → a Scenario recommendation cannot execute officially → the correlation ID is preserved → the
UI performs no domain calculation → prior recommendation + Decision remain historical → an audit
failure produces a visible safe failure → the legacy application remains untouched.

Docs: PHASE10_COMPLETION, PHASE10_ARCHITECTURE, PHASE10_TRACEABILITY, adr/ADR-0035..0040; updated
IMPLEMENTATION_CONTROL, IMPLEMENTATION_LEDGER, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note),
KNOWN_BUG_REGISTRY (note). Migration v10 adds five presentation-only tables
(`operator_view_preference`, `saved_filter`, `saved_workspace_view`, `instructional_hint_state`,
`recent_operator_context`) with NO immutability triggers — proving presentation state is
non-authoritative. No Phase 1-9 behavior changed; every prior domain remains separate and unmodified.

Result: **Phase 10 complete → HOLD FOR REVIEW.** The operator application is a faithful window over the
authoritative Phase 1-9 platform — no second business-logic layer, no authoritative browser state, no
bypass of below-UI authorization or scope. Next: Phase 11 only after review.

## Phase 10 review disposition — APPROVED

Phase 10 (operator experience + presentation layer; `elite/ui/` + migration v10) reviewed and **approved**.
Recorded here and in IMPLEMENTATION_CONTROL.md. Legacy line preserved at `3bf9162`. Phase 10 is preserved
at commit `05ba436` as the first complete working application baseline. The operator application is a
faithful read-only window over the authoritative Phase 1-9 platform (no second business-logic layer, no
authoritative browser state, no bypass of below-UI authorization or scope). BUG-CPO-002 remains
FIXED_END_TO_END.

## Phase 11 — Operational Hardening, Real-Source Integration, and Controlled Pilot Readiness  (branch `elite-pipeline/phase-0`)  [COMPLETE — HOLD FOR REVIEW]

Control records: Phase 10 recorded approved; Phase 11 set active. Hardening the working Elite Pipeline
application (`elite/ops/`) for realistic dealership operation, appending migration v11 (operational
records — append-preserving; no earlier migration modified; no business truth moved into the operational
layer), touching no legacy file and preserving Phase 10 at `05ba436` as the first complete working
application baseline. Scope: real-source adapter contracts; controlled file ingestion; source
discovery/validation; operational scheduling; import orchestration; data freshness; reconciliation/drift;
restart recovery; failure recovery; concurrency hardening; transaction durability; backup + restore;
observability; structured logging; health checks; performance baselines; security hardening; configuration
management; secret handling; pilot environment setup; controlled parallel-run comparison; operator feedback
capture; release packaging; deployment documentation; and pilot-readiness certification — resulting in a
tool ready for a controlled dealership pilot alongside the legacy tool.

Binding operational principles (verbatim intent): source data is evidence, not automatically truth; raw
source must remain preserved; import success is not acceptance; acceptance is not reconciliation;
reconciliation is not automatic business action; Partial Snapshot must never act like Full Snapshot;
missing rows must not become deletions unless the source contract permits absence reconciliation; file
import time must not replace business effective time; real-source irregularities must not be fixed through
hidden UI logic; invalid or conflicting source data must remain visible; restart must not duplicate
imports, facts, Decisions, commitments, or workflow actions; failed import must not corrupt the last valid
operational state; the application must recover safely after interruption; operational diagnostics must not
expose customer data, secrets, or unnecessary VIN-level detail; logging must be useful without becoming an
ungoverned data copy; pilot mode must run alongside the legacy system; pilot comparison must not silently
mutate Elite Pipeline results to match the legacy tool; legacy disagreement is evidence for review, not
proof Elite Pipeline is wrong; Elite Pipeline disagreement is not automatically proof the legacy tool is
wrong; **no cutover occurs in Phase 11.** All Phase 1-10 domain mathematics, identity, policy, governance,
workflows, and presentation contracts are preserved unchanged; the platform architecture is not redesigned;
no new business rule is added merely to accommodate malformed live data; no final cutover / legacy
replacement / destructive migration / production go-live. Carries a dedicated 15-point import-recovery
regression and a dedicated 20-point controlled-pilot regression.

Implemented a NEW `elite/ops/` package + migration v11 (appended; v1-v10 unchanged), touching no legacy
file and preserving Phase 10 at `05ba436`: a Python **stdlib-only** operational + controlled-pilot layer
over the Phase 10 application. Real-source adapters over Phase 2 ingestion (produce the Phase 2 canonical
contract; never write domain state; explicit schema detection; deterministic encoding/delimiter/date/
decimal/currency/blank handling; original-row traceability; recorded adapter version); a source-contract
registry documenting the pilot source families (owner/system/access/file-kind/cadence/snapshot-capability/
identity-keys/effective+update-time/schema-version/required+optional fields/units/blank-zero-missing/
duplicate/correction/absence/quality-thresholds/blocking-vs-nonblocking/raw-retention/expected-
reconciliation; manual-governed where no automated source exists — never a fabricated feed); controlled
file intake (extension allowlist, bounded size, filename + path-traversal sanitization, content hash,
duplicate detection, quarantine, upload authorization + scope, no executable handling, no silent
overwrite); an authoritative import-run orchestrator (RECEIVED→VALIDATING→VALIDATED→INGESTING→INGESTED→
RECONCILING→COMPLETED/COMPLETED_WITH_WARNINGS with REJECTED/FAILED/CANCELLED/SUPERSEDED; same content
idempotent; failed import preserves the prior accepted state; partial never masquerades as complete; retry
links to the failed run; safe, operator-visible failure detail); domain-aware freshness (effective-time +
cadence — never file import time; a fresh upload with a stale effective date stays STALE; stale/missing
blocks readiness and reduces confidence; append-preserving history a restored-current reading never
erases); operational reconciliation/drift referencing the exact source + domain records (MATCHED..UNRESOLVED
incl LEGACY_DIFFERENCE; a difference never auto-corrects; Full/Partial snapshot semantics preserved — a
Full-Snapshot absence is MISSING_EXPECTED, never a deletion; one physical unit never duplicated; unknown
cause stays UNRESOLVED); controlled scheduling (stable job identity; idempotent fire; missed-run visible;
overlap-safe; explicit timezone; manual vs scheduled distinguishable; scheduler failure corrupts nothing);
restart/crash recovery (in-flight runs → failed/reviewable; committed stays committed; rolled-back leaves no
partial state; nothing replayed; no evidence deleted); concurrency hardening (optimistic concurrency +
idempotency → exactly-once effects; stale browser submission rejected; no silent lost update, no duplicate
commitment/receipt/activation/Current-Supply); SQLite durability (foreign keys, WAL, synchronous, busy
timeout, integrity check, startup validation); transactionally-consistent backup (online backup API;
timestamped, content-hashed, integrity-verified, metadata-recorded) + non-destructive restore validation
(reproduces authoritative counts + migration version; failed-backup alert; retention preserves the record
and the raw source-file evidence; NO automated destructive production restore); three-way health checks
(liveness / readiness / operational — a live application may be operationally NOT ready); safe operational
logging (correlation IDs; NO secret/token/session-ID/customer-PII; VIN masking; raw rows never logged; a
logging failure never corrupts a governed action); performance baselines (immutable metrics with
environment + dataset size + cold/warm; slow-query evidence; optimization changes no authoritative result;
no stale-risk caching); security hardening (session expiry + invalidation; environment-aware cookie flags;
CSRF; scope isolation; authority revocation; a runnable deployment-posture checklist — no default
credential, secrets externalized, debug off outside dev/test, safe host binding, pilot not labeled
production); configuration management (safe defaults; startup validation; secret hygiene; a non-loopback
bind requires explicit opt-in; invalid config fails clearly; safe diagnostics expose no secret; environment-
specific config never changes domain logic); a visible, enforceable controlled pilot mode ALONGSIDE the
legacy tool (banner + environment; legacy fallback preserved; destructive cutover / legacy-replacement /
destructive-migration / production-go-live BLOCKED); a non-authoritative parallel-run comparison (captures
the Elite and legacy results, classifies the difference, MUTATES NEITHER result — only governed review
fields — keeps an unknown cause UNRESOLVED, stores reviewer rationale only as supplied, and blocks readiness
on a material unresolved difference until reviewed); structured operator feedback (references the exact
screen + revision; never mutates authoritative data; an incorrect-result claim opens a review, not an
automatic correction; governed + audit-referenced); evidence-based pilot-readiness certification
(READY/READY_WITH_WARNINGS/NOT_READY); and a pilot packaging CLI (`elite.ops.cli`:
diagnostics/health/import/backup/restore-validate/scheduler/serve). Migration v11 adds seventeen operational
records (import_run + import_run_error, source_adapter_version, source_file_receipt, source_freshness_result,
source_reconciliation_result, scheduled_job + scheduled_job_run, health_check_result, backup_record +
restore_validation, pilot_comparison_run + pilot_comparison_result, operator_feedback,
pilot_readiness_certification, operational_metric, operational_log_reference): point-in-time evidence is
immutable (no-update + no-delete), lifecycle/registry rows are append-preserving (no-delete); NO business
truth is moved into the operational layer and raw source references are retained.

Evidence executed: platform harness **826/826** (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 + 79 P7 +
91 P8 + 104 P9 + 98 P10 + 109 P11); legacy **39/39** (29 engine + 10 loaner); migration v11 rerun-safe;
legacy application paths byte-unchanged vs `legacy/inventory-tool` @ `3bf9162`. All 106 mandatory acceptance
items pass, plus the dedicated 15-point import-recovery regression and the 20-point controlled-pilot
regression (PHASE11_COMPLETION.md). The import-recovery loop is proven end to end (prior valid state → new
import → interruption before acceptance → rollback → prior state intact → failed/reviewable run → linked
retry → corrected retry succeeds → facts exactly once → restart no replay → freshness updates → traceable
audit/correlation → no raw/secret in logs). The controlled-pilot loop is proven end to end (pilot banner +
legacy fallback → cutover blocked → comparison preserves both results + classifies + keeps unknown
unresolved + records rationale + mutates neither → material unresolved blocks readiness → acceptable review
permits ready-with-warnings → feedback references exact revision + alters nothing → backup succeeds → health
distinguishes live from ready → restart preserves comparison + feedback history → pilot continues after a
failed import using the prior valid state → no production cutover).

Docs: PHASE11_COMPLETION, PHASE11_ARCHITECTURE, PHASE11_RUNBOOKS, PHASE11_TRACEABILITY, adr/ADR-0041..0046;
updated IMPLEMENTATION_CONTROL, IMPLEMENTATION_LEDGER, KNOWN_BUG_REGISTRY, REQUIREMENT_INDEX (note),
requirement_index.json (note), RUN_INSTRUCTIONS. No Phase 1-10 behavior changed; every prior domain +
presentation contract remains unmodified.

Result: **Phase 11 complete → HOLD FOR REVIEW.** The application is hardened for a controlled dealership
pilot alongside the legacy tool — source data is evidence not truth, raw source preserved, import success
not acceptance, and no cutover / legacy replacement / destructive migration / production go-live occurred.
BUG-CPO-002 remains FIXED_END_TO_END. Next: Phase 12 only after review.
