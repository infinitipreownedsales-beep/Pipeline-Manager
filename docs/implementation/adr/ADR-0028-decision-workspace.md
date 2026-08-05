# ADR-0028 — Consolidated Decision Workspace

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance), 10 (Views)

## Decision
The Decision Workspace is a governed operational-control layer whose items REFERENCE authoritative domain
output (recommendation / Prediction / Economic Call / Execution Status / planning refs) by id — never a
copy of the domain calculations. A workspace item carries only control metadata (priority, unresolved
classification, assigned reviewer, required authority, evidence refs, Raw History refs, applicable facts +
versions) and a summary `workspace_state`. The workspace state summarizes operational control; it does
NOT replace the domain lifecycle. A changed current recommendation creates a new workspace revision (or a
superseding item); prior reviewed recommendations remain historical. Review exposes Call / Why / Proof
and resolves confidence/uncertainty from the referenced domain record, never inventing missing
explanation.

## Why
A single operational surface is needed to review and act on outputs from many independent domain engines
without becoming a second source of truth that could drift from, or silently rewrite, the authoritative
domain results. Referencing (not copying) keeps the domain engines authoritative and the workspace a thin,
auditable control view — the bridge to Phase 10.

## Consequences
- The workspace table has no domain-math columns (test 2); output slices resolve domain records live.
- A recommendation change is a new revision with the prior preserved (tests 3-4).
- Review with no resolver invents nothing (test 6).
