# PHASE 5 REGISTRIES — Production and Supply Workflows

Living registries for the Phase 5 domain. Runtime records live in the authoritative SQLite store
(migration v5); this document indexes the contracts.

## Production-pipeline registry
`production_pipeline_projection` — one CURRENT projection per Production Order (prior superseded and
preserved). Fields: order/production/allocation/VIN status, build+shipment timing, ETA range,
arrival month, source+fact+identity references, conflict, confidence. Rules: identity stable through
status changes; pre-VIN→VIN linkage updates the same order (no duplicate); conflicting source states
are explicit; cancelled/invalid/superseded orders emit no qualifying Future Supply
(`PipelineService.emit_future_supply`).

## Workflow registry
`supply_workflow` (+ `supply_workflow_transition`, `supply_workflow_evidence`). Common lifecycle
across four workflow types. Every record preserves: workflow id/type, subject identity + kind,
combination, target month, quantity, originating Need ref, qualifying-supply-at-propose, expected
resulting supply, proposal reason, evidence, policy + calculation versions, approval decision,
execution refs, lifecycle history, idempotency identity, audit refs, reproducibility, scenario id.

| Workflow | Capabilities | Supply effect point | Distinctions |
|---|---|---|---|
| CPO | `cpo.propose`, `cpo.approve` | approval → one Committed Supply (discrete order) | discrete production-order commitment, not replenishment |
| PPO | `ppo.propose`, `ppo.approve` | approval → at most one Committed Supply | own path, distinguishable from CPO; synthetic allocation evidence |
| Dealer Trade | `dealer_trade.propose/approve/complete` | completion → one qualifying Supply (acceptance firm only by contract) | proposal/request/acceptance are not supply by default |
| CTP | `ctp.propose/approve/execute` | accepted execution → moves one future unit between combinations | modifies an existing order; no duplicate; respects editability |

Cross-cutting: `workflow.cancel`, `workflow.supersede`, `production.view/propose/approve/execute`.
Proposal, approval, and completion authorities are distinct capabilities (separation enforced).

## Commitment-reconciliation registry
Every governed transition produces or references a `commitment_reconciliation_result` with one of:
`NO_SUPPLY_EFFECT`, `COMMITMENT_CREATED`, `ALREADY_REPRESENTED`, `COMMITMENT_UPDATED`,
`COMMITMENT_CANCELLED`, `COMPLETED_TO_CURRENT`, `FAILED_NO_EFFECT`, `UNRESOLVED_IDENTITY`,
`CONFLICTING`, `DUPLICATE_REPLAY`. Prior/new qualifying-supply counts are recorded so the supply
effect is explicit and count-once is auditable.

## Transition / model-year registry
`model_year_transition_result` records outgoing/incoming model years, overlap, lineage status,
transition window, arrival risk, and constrained-incoming flag. Transition never auto-transfers
Demand between model years; approved Phase 4 lineage/comparability governs inherited evidence; late
outgoing-model-year supply stays visible; incoming uncertainty never becomes false precision;
model-year identity is preserved (distinct Sellable Combinations).

## CPO / PPO / Dealer Trade / CTP contract summary
- **CPO** — identify an eligible Production Order / accepted allocation → bind to one combination →
  show Need + Current/Future/Committed Supply + arrival timing + Incoming Risk → propose → authorized
  approval creates one Committed Supply → reconcile against existing supply (ALREADY_REPRESENTED if
  the order is already represented) → prevent duplicate (idempotent replay) → preserve execution +
  completion/cancellation. CPO never computes Demand and never increases it.
- **PPO** — its own governed path; discrete unit/order opportunity; no supply before approval;
  counts once; identity continuity; distinguishable from CPO; no separate Demand.
- **Dealer Trade** — proposal → request → acceptance → completion; only completion creates/reconciles
  one qualifying Supply (unless the contract marks acceptance firm); rejected/expired/withdrawn/failed
  do not count; received Vehicle Unit reconciles with the trade; consumes Need without changing Demand.
- **CTP** — governed modification of an existing Production Order (no duplicate order); approved
  intent leaves original Future Supply authoritative; accepted execution moves the one future unit to
  the proposed combination (counted once, original history preserved); respects editability; consumes
  Need + Excess; recomputes both source and destination combinations; replay does not apply twice.
