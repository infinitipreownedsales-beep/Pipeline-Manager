# ADR-0036 — Authoritative-read discipline (no domain math in the UI)

- **Status:** Accepted (Phase 10)
- **Owning segments:** 10 (User Experience), 07-09 (domains)

## Decision
The presentation layer READS authoritative Phase 1-9 records and never recomputes domain logic. It
defines no alternative Demand / Need / Economic-Call / Best-Overall formula; it renders the stored
results as-is. Browser and local presentation state (saved filters, sort, column visibility) can never
alter an authoritative value. A refresh reproduces the same authoritative display; historical vs current
and official vs Scenario remain separately identifiable; a Scenario result can never replace an official
one.

## Why
Introducing any business logic into the interface would create a second, divergent source of truth and
could silently contradict — or appear to rewrite — the authoritative domain results. Keeping the UI a
faithful window preserves the integrity the previous phases established (one authoritative Demand, count-
once supply, governed Decisions) all the way to the operator's eyes.

## Consequences
- The presentation-integrity regression asserts displayed values equal stored values and that the UI
  source has no domain formula (`test_phase10_presentation_integrity_regression`).
- Domain workspaces read the Phase 4-7 stores directly and show stored Need/Demand/Best-Overall.
