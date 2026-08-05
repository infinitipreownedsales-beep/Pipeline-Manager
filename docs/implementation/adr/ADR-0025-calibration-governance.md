# ADR-0025 — Calibration governance (propose ≠ activate)

- **Status:** Accepted (Phase 8)
- **Owning segments:** 12 (Learning), 11 (Governance/Audit), 06 (Versioning)

## Decision
Learning may PROPOSE a versioned change but never activates it. A Calibration Proposal moves through a
governed lifecycle (`DRAFT → PROPOSED → UNDER_REVIEW → (VALIDATION_REQUIRED → VALIDATED) → APPROVED →
{SCHEDULED →} ACTIVATED`, plus `REJECTED / WITHDRAWN / ROLLED_BACK / SUPERSEDED / CORRECTED`), each
transition authorized below the UI and bound to an Audit Event atomically, with optimistic concurrency
and idempotent activation. Material targets (calculation/model/parameter/comparison-spec versions)
require validation before approval. Approval is distinct from activation; future-effective Calibration
stays SCHEDULED. Activation is the ONLY step that creates operational change: it creates or references
a new approved version, or — for policy-adjacent targets — a policy-REVIEW recommendation, never a
direct mutation of active manufacturer/dealership policy, permissions, or source facts. Activation
never rewrites prior Predictions; rollback restores an approved prior version prospectively and
preserves history. Rejected/withdrawn proposals have no operational effect. **No approved Calibration
means no operational change.**

## Why
Automated learning that could silently change live behavior would be unsafe and unauditable. Separating
proposal, validation, approval, and activation — with distinct authorities and an atomic audit trail —
keeps every change a deliberate, reviewable, reversible act, and guarantees the system's behavior only
ever changes through an approved, activated, versioned decision.

## Consequences
- A Learning Signal or Proposal alone creates no version and no activation (tests 50, 54, 69).
- Activation is idempotent and immutable; audit failure rolls the activation back entirely (tests 75, 77).
- Policy targets never mutate policy; they emit a review recommendation (test 68).
