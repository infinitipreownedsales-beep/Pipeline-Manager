# ADR-0022 — Prediction-to-Observation Pairing

- **Status:** Accepted (Phase 8)
- **Owning segments:** 12 (Learning / Institutional Memory)

## Decision
A Prediction and an Observation are connected only through a deterministic Pairing that runs under an
ACTIVE, applicable Comparison Specification. Pairing verifies, in order: the spec is active and its
Prediction type matches (hard reject); the Observation type matches (hard reject); subject identity,
store/scope, and unit compatibility match; timing/window and lateness. It records one of thirteen
outcomes (`PAIRED, PENDING_OBSERVATION, PARTIAL, LATE_PAIRED, AMBIGUOUS, CONFLICTING, UNIT_MISMATCH,
SCOPE_MISMATCH, IDENTITY_MISMATCH, OUTSIDE_WINDOW, UNRESOLVED, CORRECTED, SUPERSEDED`). Pairing is
idempotent under `{prediction}:{observation}:{comparison_version}`, never mutates the Prediction or
Observation, may remain pending until the observation window closes, follows the late contract
afterward, and permits one-Prediction-to-many-Observations only when the spec explicitly allows
aggregation. An identity correction creates a NEW Pairing while preserving the prior one.

## Why
Comparing a prediction to an outcome is only valid under an explicit, versioned rule about what counts
as "the same thing observed in the right window in compatible units." Making the match deterministic,
idempotent, and non-mutating keeps the historical record trustworthy and lets an Error be computed only
when a genuinely valid correspondence exists — absence before the window closes is pending, not
failure, and ambiguity stays unresolved rather than being forced.

## Consequences
- An Error can be derived only from a valid Pairing (ADR-0023); pending/mismatched pairings never yield
  a fabricated numeric error.
- Replaying the same inputs never duplicates a Pairing; corrections are new rows with lineage.
