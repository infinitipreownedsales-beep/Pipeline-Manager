# ADR-0016 — Provisional retirement

- **Status:** Accepted (Phase 6)
- **Owning segments:** 08 (Service Loaner)

## Decision
Entry, active service, provisional retirement, actual return, retirement, and Used Cars receipt are
SEPARATE states and events. Eligibility is not retirement; retirement approval is not an actual
return. A currently rented unit may receive a provisional retirement Decision but remains
active/rented until an actual return is confirmed — its `membership_state` becomes
`PROVISIONAL_RETIREMENT` while its `current_rental_state` stays `rented`. Provisional retirement is
visible in portfolio state and prevents a duplicate retirement recommendation for the same unit.
Return confirmation is a distinct actual operational event; final retirement reconciles fleet
membership only at the defined event. Cancellation restores the appropriate current state without
deleting history; corrections preserve prior records.

## Why
A retirement recommendation being approved does not put the car back on the lot. Modeling provisional
retirement as a distinct membership state (orthogonal to rental) is the smallest correct way to
reflect "decided to retire, physically still out on rent" without double-recommending or prematurely
counting the unit as returned.

## Consequences
- Provisional units are excluded from re-recommendation (an illegal re-propose transition).
- Membership history is append-preserving across the entire retirement path; nothing is overwritten.
