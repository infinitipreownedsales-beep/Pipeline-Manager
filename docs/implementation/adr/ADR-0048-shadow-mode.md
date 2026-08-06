# ADR-0048 — Domain shadow mode

## Status
Accepted (Phase 12).

## Context
The pilot must advance domain-by-domain from data-only to execution without any domain advancing
automatically, and with execution blocked until explicitly enabled.

## Decision
Add `domain_shadow_mode` as a governed, immutable event log (latest row = current mode) with states
DATA_ONLY / CALCULATE_ONLY / REVIEW_ONLY / DECISION_PILOT / EXECUTION_PILOT / CUTOVER_ELIGIBLE / BLOCKED.
Live execution is permitted only in EXECUTION_PILOT / CUTOVER_ELIGIBLE; every mode change is governed +
audited; history is preserved.

## Consequences
Mode is visible and domain-specific; no domain advances on its own; execution stays blocked until an
authorized, audited mode change enables it.
