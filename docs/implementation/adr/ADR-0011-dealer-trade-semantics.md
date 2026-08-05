# ADR-0011 — Dealer Trade semantics

- **Status:** Accepted (Phase 5)
- **Owning segments:** 07 (Supply/pipeline)

## Decision
A Dealer Trade progresses proposal → request sent → acceptance → completion, with terminal
rejected/expired/withdrawn/failed states. A proposed trade is not Supply; sending a request is not
Supply; **acceptance alone is not completed Supply unless the approved contract explicitly marks it a
firm unit-level commitment** (`firm_on_accept`, default off). Confirmed completion creates or
reconciles exactly one qualifying Supply effect (Current Supply for the received Vehicle Unit).
Rejected/expired/withdrawn/failed trades never count; unknown trade attempts are never invented (only
recorded actions exist). The received Vehicle Unit identity reconciles with the completed trade.
Dealer Trade consumes Phase 4 Need and never changes Demand.

## Why
Treating acceptance or a sent request as Supply would overstate availability and could inflate
apparent coverage. Making completion the default supply-bearing point — with an explicit firm-on-
accept contract flag — matches how real trades resolve and keeps qualifying Supply honest.

## Consequences
- Outbound-unit effects (a traded-away unit) are deliberately out of Phase 5 scope; incoming-unit
  reconciliation is implemented.
- A completed trade counts once (via the Phase 4 dedup); the status history preserves every step.
