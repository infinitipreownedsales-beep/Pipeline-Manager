"""Phase 5 — Production and Supply Workflows (L4/L5 governed workflows over the L3 New
Inventory domain).

Governed workflows (CPO, PPO, Dealer Trade, CTP) that convert supply opportunities into
proposed/approved/committed/executed/cancelled/superseded/failed supply actions. Every workflow
CONSUMES the authoritative Phase 4 Need contract and defines NO separate Demand; supply effects
flow through the Phase 4 Supply/commitment records so count-once and monotonicity hold. Governed
transitions reuse the Phase 1 Governor (authz + atomic audit).
"""
