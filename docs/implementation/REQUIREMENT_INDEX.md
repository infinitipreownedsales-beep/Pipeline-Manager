# REQUIREMENT INDEX — Elite Pipeline 1.0.0 (RC1)

Human-readable view. Machine-readable source of truth: `docs/implementation/requirement_index.json` (regenerate from the canonical DOCX).

- Unique requirement IDs: **4523** (occurrences 4532)
- Segments: **17** (00–16) + Table of Contents · Heading 1: 18 · Heading 2: 1085
- Requirement IDs are the specification's authority; this index is generated, not authored.

## Segments (owning families)

- SEGMENT 00 — SPECIFICATION CONTROL
- SEGMENT 01 — PRODUCT CONSTITUTION
- SEGMENT 02 — SYSTEM CONTEXT AND ARCHITECTURE RC1 CONTRACT
- SEGMENT 03 — CANONICAL DOMAIN MODEL AND LIFECYCLE STATE MACHINES
- SEGMENT 04 — DATA, IDENTITY, SOURCE AUTHORITY, RECONCILIATION, AND INGESTION
- SEGMENT 05 — POLICY, CONFIGURATION, EFFECTIVE DATING, AND CALCULATION VERSIONING
- SEGMENT 06 — NEW INVENTORY DEMAND, SUPPLY, FORECASTING, AND PORTFOLIO PLANNING
- SEGMENT 07 — PRODUCTION PIPELINE, MODEL-YEAR TRANSITION, INCOMING RISK, CPO, PPO, DEALER TRADE, AND CTP
- SEGMENT 08 — SERVICE LOANER DOMAIN
- SEGMENT 09 — EXECUTIVE DEMO DOMAIN
- SEGMENT 10 — PREDICTION, DECISION, OBSERVATION, ERROR, ATTRIBUTION, LEARNING SIGNAL, AND CALIBRATION
- SEGMENT 11 — GOVERNANCE, AUTHORIZATION, SCENARIOS, SHARING, AUDIT, AND ADMINISTRATION
- SEGMENT 12 — USER EXPERIENCE AND INTERACTION CONTRACT
- SEGMENT 13 — NONFUNCTIONAL REQUIREMENTS, SECURITY, RELIABILITY, PERFORMANCE, PORTABILITY, AND OPERATIONS
- SEGMENT 14 — VERIFICATION, FIXTURES, ACCEPTANCE, AND RELEASE GATES
- SEGMENT 15 — IMPLEMENTATION SEQUENCE, REPOSITORY RESTART, MIGRATION, DELIVERY, AND COMPLETION DIRECTIVE
- SEGMENT 16 — GLOSSARY AND REQUIREMENT INDEX

## Requirement families (prefix → count)

| Family | Count | | Family | Count | | Family | Count |
|---|--:|---|---|--:|---|---|--:|
| NFR | 422 | | UX | 417 | | TEST | 351 |
| DELIVERY | 297 | | DATA | 255 | | SL | 250 |
| GOV | 249 | | INV | 243 | | DM | 235 |
| DEMO | 189 | | POL | 187 | | ARCH | 176 |
| CONST | 153 | | REQ | 107 | | SEC | 106 |
| GLOSS | 82 | | PIPE | 78 | | LRN | 76 |
| CTP | 63 | | SPEC | 52 | | CAL | 49 |
| GATE | 47 | | CALC | 41 | | PAIR | 35 |
| SCN | 33 | | LSIG | 28 | | SUPPLY | 27 |
| AUDIT | 25 | | TRANS | 24 | | ERR | 24 |
| PRED | 21 | | ATTR | 21 | | DEC | 17 |
| RISK | 16 | | CPO | 14 | | DT | 13 |
| EXIT | 11 | | ENTRY | 9 | | POLICYEXP | 9 |
| PPO | 8 | | OBS | 8 | | DEMAND | 6 |
| HANDOFF | 6 | | MODEL | 5 | | RET | 5 |
| CONF | 5 | | IDRULE | 4 | | FCST | 4 |
| FLEET | 4 | | REMOVE | 4 | | NOACT | 4 |
| FIX | 4 | | BUG | 3 | | AUTH | 1 |

## Implemented-requirement coverage by phase
- Phase 1 (platform): `PHASE1_TRACEABILITY.md`.
- Phase 2 (data/identity/facts): `PHASE2_TRACEABILITY.md`.
- Phase 3 (policy/versioning): `PHASE3_TRACEABILITY.md`.
- Phase 4 (new inventory): `PHASE4_TRACEABILITY.md`.
- Phase 5 (production/supply workflows): `PHASE5_TRACEABILITY.md`.
- Phase 6 (service loaner domain): `PHASE6_TRACEABILITY.md`.
- Phase 7 (executive demo domain): `PHASE7_TRACEABILITY.md`.
- Phase 8 (prediction/observation/error/attribution/learning/calibration): `PHASE8_TRACEABILITY.md`.
- Phase 9 (governance/decision-workspace/scenario-admin/operational-control): `PHASE9_TRACEABILITY.md`.
The canonical DOCX is unchanged, so `requirement_index.json` is unchanged; phase
traceability maps implemented capabilities to owning segments/families (exact IDs
bound at review).

## Usage
- Phase 1 binds each material business rule to its owning segment and applicable requirement IDs (see REPOSITORY_AUDIT business-rule map).
- Do not renumber or remove IDs; the DOCX is canonical. Regenerate this file and `requirement_index.json` from the DOCX if the spec is reissued.
