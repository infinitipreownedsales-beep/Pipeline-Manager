"""Operator Intelligence — the system-wide standard layer.

Four reusable components every operator decision surface (New Retail, CPO/Ordering, PPO, Supplemental,
Dealer Trade, Service Loaner, Demo, Wholesale, CTP) is meant to consume instead of re-implementing:

  * description   — governed, code→human vehicle language ("QX80 LUXE 2WD — Radiant White (QBE) / Graphite (G)").
  * supply        — one normalized supply representation with SOURCE and AVAILABILITY as separate dimensions.
  * physical      — the physical-unit (VIN + stock) selector that fulfils a combination need whenever a real
                    vehicle exists — the CORE LAW: combination-level intelligence decides WHAT is needed,
                    VIN-level intelligence decides WHICH actual vehicle fulfils it.
  * opportunity   — the shared incremental supply-opportunity evaluator (PPO / Supplemental / Dealer Trade all
                    ask the same question: given everything already owned and committed, should we add THIS
                    specific unit?). Sequential, disposable-planning-state, actionability-timing-preserving.

Everything here is stdlib-only and pure/deterministic except where it reads an existing governed store; nothing
writes truth, migrates schema, or touches the permanent DB. No fake heuristics (no diversification, mileage or
Velocity staggering, executive weighting, oldest-wins, artificial Ground-Stock/Dealer-Trade bonus, or
nearest-code substitution) live in this layer — see CORE LAW in description/physical and the prohibitions the
evaluator enforces.
"""
