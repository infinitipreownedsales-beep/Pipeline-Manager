# PHASE 4 REGISTRIES — New Inventory

Living registries for the Phase 4 domain. Exact runtime records live in the authoritative
SQLite store (migration v4); this document is the human-readable index of the contracts and the
calculation/lineage/forecast families they issue.

## New Inventory Calculation Registry
| Calculation Family | Version | Determinism | Inputs (never supply for Demand) | Output | Reproducibility |
|---|---|---|---|---|---|
| `new_inventory_demand` | 1.0.0 | deterministic | accepted retail, availability exposure, bounded seasonality, trend, lineage/inheritance, approved policy | monthly expected retail + evidence tier + confidence/uncertainty | package pins inputs + versions; `DemandService.replay` reproduces identical output |
| `new_inventory_plan` | 1.0.0 | deterministic | Demand result (input), qualifying supply (deduped), policy-resolved coverage | Need, Excess, per-month cumulative shortage, planning state | package pins inputs + versions; `PlanningService.replay` reproduces identical output |

Registered via the Phase 3 Calculation Family/Version foundation (`calculation_family` /
`calculation_version`); ids persisted in `system_metadata` (`demand_cv_id`, `plan_cv_id`) so a
restart reuses the same versions. A behavior change requires a new Calculation Version.

## Sellable Combination Registry
Canonical identity is built from demand-material, independently-selectable dimensions only:
`franchise, model, model_year, trim, drivetrain, exterior_color, interior_color`
(`newinv/combination.IDENTITY_DIMS`). Rules:
- Standard trim *content* that is not independently selectable never enters identity (extra
  attributes are ignored by `canonical_identity`).
- Model year is included by default; it may be dropped **only** under an approved immateriality
  rule (`model_year_material=False`).
- Interior color remains a distinguishing dimension when reliable evidence exists; unknown values
  stay distinct sentinels (never collapsed to a known value).
- Identity dedups **within a store scope only** — the same configuration in another store is a
  distinct combination (no silent cross-store merge).
- Corrections create a new combination (`correction_of`) and mark the original `corrected`; prior
  identity history is preserved (no-delete trigger).

## Lineage / Comparability Registry
`combination_lineage` records explicit, versioned relationships between combinations:
| Relationship | Default comparability | Inheritance rule |
|---|---|---|
| `new_model_year` | comparable | inheritable, labeled; reduced confidence |
| `related_family` | comparable | inheritable, labeled family-tier evidence |
| `attribute` | comparable | attribute-tier evidence |
| `generation_change` | requires approval | **not** inheritable as comparable without an `approved_rule_ref` |

Direct exact-combination evidence always outranks inherited evidence; inherited evidence is
labeled in the Demand result's `baseline_evidence.source` and carries a non-`exact` evidence tier.

## Issued Forecast Registry
Every issued Demand, forecast, inventory plan, and portfolio plan is indexed in
`issued_planning_output` with its `output_type`, `calculation_version`, `reproducibility_package`,
and `scenario_id`. Issued results are append-preserving (no-delete triggers): a changed current
forecast is a **new** issued record, never a rewrite of the historical one. Official
(`scenario_id = NULL`) and hypothetical (scenario) results remain distinct and isolated.
