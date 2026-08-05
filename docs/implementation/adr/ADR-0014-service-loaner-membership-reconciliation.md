# ADR-0014 — Service Loaner membership reconciliation

- **Status:** Accepted (Phase 6)
- **Owning segments:** 08 (Service Loaner), 04 (Data/ingestion)

## Decision
Active-fleet membership is reconciled by accepted VIN from an authoritative Full Snapshot ingested
through the Phase 2 pipeline (raw preserved). Only a valid, compatible Full Snapshot may support
absence reconciliation, and even then absence yields a review signal (`ABSENT_REVIEW`) — never a
removal or an invented retirement/return. A Partial Snapshot absence is `ABSENT_NO_CHANGE`; an invalid
Full claim (a non-snapshot-capable source) validates as partial and cannot remove membership.
Invalid/unresolved VINs never silently enter the fleet; duplicate VINs and conflicting operational
states are explicit outcomes. Rental state is a separate operational fact and never changes membership
by itself.

## Why
The active fleet is safety-critical operational truth. Treating snapshot absence as removal — or
letting a partial/invalid file drive membership — would fabricate retirements and corrupt planning.
Routing through Phase 2 preserves raw values and reuses the proven full/partial classification and
absence-signal rules.

## Consequences
- Membership can arise from an accepted snapshot (observed reality) or from a governed entry decision;
  both are distinct paths and both establish `active_fleet_presence` explicitly.
- Every VIN row yields an explicit reconciliation outcome; nothing enters or leaves the fleet silently.
