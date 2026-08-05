# ADR-0034 — Domain launch-readiness assessment

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance), 15 (Delivery)

## Decision
A domain readiness assessment is an evidence-based, versioned, immutable record classifying a domain as
`READY / READY_WITH_WARNINGS / NOT_READY / UNRESOLVED / CONFLICTING` from concrete evidence (required
policy present, calculation versions active, source contracts available, unresolved/critical identities,
stale imports, authority + separation-of-duties coverage, audit health, operational owner, test evidence).
Missing required policy or required authority blocks readiness; a critical unresolved identity may block
it; a passing synthetic test suite ALONE is never sufficient (it is a warning without operational
evidence). Readiness does NOT deploy or activate a domain; prior assessments remain historical.

## Why
"The tests pass" is not "the dealership can run this domain." Grounding readiness in operational evidence —
and explicitly refusing to let a green synthetic suite stand in for real policy, authority, identity, and
ownership — keeps the go/no-go decision honest, and keeping it inert (assessment, not deployment) keeps it
safe.

## Consequences
- Missing policy/authority or critical unresolved identity yields NOT_READY (tests 94-96).
- Synthetic-only evidence yields READY_WITH_WARNINGS (test 97); an assessment activates nothing (test 98).
- Assessments are immutable and accumulate as history (test 99).
