# ADR-0030 — Scenario promotion routing

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance), 05 (Policy)

## Decision
Scenario administration keeps a Scenario isolated from official state through its whole lifecycle. A
promotion request has NO direct operational effect; it routes to the correct governed review type: a
policy target → a policy-review request; a Calibration target (calculation/model/comparison-spec version)
→ the Phase 8 Calibration governance; an operational target → a NEW official Decision issued from official
facts (never a copy of Scenario state). Sharing a Scenario is not approval, and APPROVED_FOR_DISCUSSION is
not official. A rejected promotion has no official effect; a Scenario can never become an Observation, and
a Scenario Prediction is excluded from official learning unless explicitly permitted.

## Why
Scenarios must let management explore hypotheticals without any risk of a hypothesis leaking into official
policy, calculations, learning, or operational state. Routing promotion to the existing governed review
paths — rather than mutating official state directly — keeps every real change behind its proper approval
gate.

## Consequences
- A policy promotion creates a policy-review request, not a policy change (test 59).
- A Calibration promotion routes to Phase 8 governance; an operational promotion requires a fresh official
  Decision (tests 60, 61).
- Promotion creates no version and no Decision on its own (tests 58, 61).
