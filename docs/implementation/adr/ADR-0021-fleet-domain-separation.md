# ADR-0021 — Executive Demo and Service Loaner remain separate bounded domains

- **Status:** Accepted (Phase 7)
- **Owning segments:** 08 (Service Loaner), 09 (Executive Demo)

## Decision
Executive Demo (Phase 7) and Service Loaner (Phase 6) are implemented as **separate** bounded domains:
distinct packages (`elite/execdemo/` vs `elite/loaner/`), distinct SQLite stores and tables, distinct
migrations (v7 vs v6), distinct capability namespaces (`executive_demo.*` vs `service_loaner.*`), and
distinct lifecycles. They are **not** generalized into one shared fleet engine. A Vehicle Unit that is
an active Service Loaner is ineligible and blocked for Executive Demo designation, and the same
count-once identity rules keep a unit from being active in both simultaneously. Their Used Cars
handoffs are separate records (`executive_demo_used_cars_receipt` vs `used_cars_receipt`).

Reuse is limited to genuine platform-level primitives already valid for both domains — the Phase 1
Governor + audit, the governed-transition + raw-effect pattern, Phase 3 policy/calculation-version +
reproducibility, Phase 4 New Retail supply/plan contracts, and Phase 2 identity/facts. These are shared
foundations, not a merged fleet abstraction.

## Why
The two domains answer different business questions (executive demonstration portfolio vs service
loaner fleet) with different eligibility, economics, monitoring, and supply direction. The Phase 7
directive explicitly required preserving Service Loaner as a completed, separate domain and forbade a
shared fleet engine unless a specific platform-level primitive is already valid for both. Premature
generalization would couple two independently-evolving domains and risk cross-domain double-counting.

## Consequences
- `execdemo/portfolio.py` imports no Service Loaner package; the guard test (`test_phase7_migration_cross.test_89`)
  asserts the absence of a shared engine and of out-of-scope Pairing/Learning/Governance symbols.
- Cross-domain exclusivity is enforced at eligibility and at designation execution
  (`test_phase7_unit_portfolio.test_04_05`, `test_phase7_economics_designation_retirement.test_54`).
- If a future primitive is genuinely valid for both fleets, it can be extracted to the platform layer
  deliberately — this ADR governs that it must be a real shared primitive, not a merge of the domains.
