# ADR-0018 — Executive Demo Best Overall portfolio selection

- **Status:** Accepted (Phase 7)
- **Owning segments:** 09 (Executive Demo)

## Decision
Executive Demo candidate selection is a **portfolio optimization over the full business objective**,
not a single-field sort. Portfolio need is resolved first (from required size minus active minus
committed Executive Demo units — Service Loaner need never enters, New Retail Demand is never
recomputed). Among ELIGIBLE candidates (eligibility is a hard pre-filter, deduplicated, excluding
already-active/committed/retired units) each is scored:

`objective = W_BENEFIT·benefit − W_OPP_COST·new_retail_opportunity_cost + W_FIT·portfolio_fit + preference_bonus`

with recorded weights `W_BENEFIT=1.0, W_OPP_COST=1.0, W_FIT=2.0, W_PREFERENCE=1.5`. The top `need`
candidates are selected. Every plan records the per-candidate tradeoff breakdown (benefit, New Retail
opportunity cost, portfolio fit, preference bonus), the objective weights, the need basis, and labels
necessary sacrifices (opportunity cost above a threshold). Model preference contributes only through
an approved Phase 3 resolution, never overriding eligibility or silently overriding opportunity cost.

## Why
The dealership question is "which units make the best **overall** Executive Demo portfolio", not "which
is cheapest" or "which scores highest on one axis". The lowest New Retail opportunity cost must not
automatically win, nor the highest Executive Demo benefit if the New Retail sacrifice is excessive. A
weighted, fully-recorded objective makes the choice explainable and auditable — the proof is the
tradeoff breakdown, never an opaque composite number.

## Consequences
- A strong complete portfolio fit can outrank both the cheapest and the highest-benefit candidate
  (proven by `test_phase7_preference_bestoverall` items 33-36 and the 14-point regression).
- Weights are data recorded in each plan; re-tuning them is a versioned change, not a code-behavior
  surprise.
- Selection excludes duplicates and unavailable units, so one Vehicle Unit is never selected twice.
