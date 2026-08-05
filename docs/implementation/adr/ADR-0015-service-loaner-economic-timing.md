# ADR-0015 — Service Loaner economic timing

- **Status:** Accepted (Phase 6)
- **Owning segments:** 08 (Service Loaner), 06 (Calculation/economics)

## Decision
The Service Loaner Economic Call is a versioned result (Calculation Version `service_loaner_economic`)
kept strictly SEPARATE from Execution Status. Placement economics and exit-timing economics are
distinct decision points. Exit timing uses INCREMENTAL future economics from the current decision
point; the sunk placement cost is never reapplied to the exit decision. Each result carries its
alternatives — each with its own explicit value and basis (never a single opaque score) — the chosen
call, assumptions, uncertainty, Policy Versions, Calculation Version, fact refs, and a reproducibility
package. Unsupported financial inputs produce unresolved or lower-confidence output. The Economic Call
is never rewritten merely because execution is currently blocked; operational infeasibility lives only
in Execution Status.

## Why
Conflating "what is financially best" with "what can be done right now" hides the strongest option and
distorts exit timing. Separating the two, and using incremental future economics without sunk cost,
is the smallest correct way to keep exit decisions financially honest and reproducible.

## Consequences
- Execution Status can block a financially preferred call without altering it.
- Actual market/residual/write-down values resolve through Phase 3; the fixtures pass synthetic values.
