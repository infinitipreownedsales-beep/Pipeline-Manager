# ADR-0038 — Raw History presentation

- **Status:** Accepted (Phase 10)
- **Owning segments:** 10 (User Experience)

## Decision
Every recommendation exposes a consistent Call / Why / Proof / Raw History pattern. Raw History is an
evidence-ORIENTED timeline — item opened, recommendation revisions, Decisions, approvals, executions,
reconciliations, with actor and time — not a raw database dump. Missing explanation is shown as
*unknown*, never invented. Corrected and superseded records remain visible; current and historical, and
official and Scenario, are labeled distinctly.

## Why
An operator must be able to move from the summary Call to the underlying evidence without losing context
and without being shown either fabricated reasoning or an unreadable table dump. An evidence timeline
built from the authoritative records makes the "why" auditable and honest.

## Consequences
- The detail reads authoritative records and recomputes nothing (ADR-0036).
- A revised recommendation shows both the current ref and the prior revision in the timeline (test 18).
- Absent reasoning renders "unknown" (test 17).
