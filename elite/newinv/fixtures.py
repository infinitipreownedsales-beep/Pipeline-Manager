"""Deterministic Phase 4 fixtures: a wired New Inventory stack + dealership-representative
synthetic scenarios. Synthetic dealership data only — no confidential production data and no
real manufacturer incentives/allowances/windows.
"""
from __future__ import annotations

from ..data.fixtures import Phase2  # noqa: F401  (kept for symmetry / discoverability)
from ..policy.fixtures import Phase3
from .availability import AvailabilityService
from .combination import CombinationService
from .coverage import CoverageService, target_units
from .demand import DemandService
from .forecast import ForecastService
from .planning import PlanningService
from .retail import RetailService
from .store import NewInvStore
from .supply import SupplyService

SCOPE = "store:HG"
OTHER_SCOPE = "store:WEST"
TZ = "America/Chicago"
HORIZON = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]
AT = "2026-08-15T00:00:00+00:00"


class Phase4:
    """Phase 1-3 foundations + Phase 4 New Inventory domain services, deterministically wired."""

    def __init__(self, db_path, *, seed=True):
        self.p3 = Phase3(db_path, seed=seed)                    # migrates v1+v2+v3; +v4 below
        self.stack = self.p3.stack
        self.clock = self.stack.clock
        self.stack.db.migrate()                      # ensure migration v4 applied
        self.policy = self.p3.store                  # PolicyStore (reproducibility + resolution)
        self.gov = self.p3.gov
        self.owner = self.p3.owner
        self.store = NewInvStore(self.stack.db.conn, self.clock)
        self.combos = CombinationService(self.store, self.clock)
        self.supply = SupplyService(self.store, self.clock)
        self.retail = RetailService(self.store, self.clock)
        self.availability = AvailabilityService(self.store, self.clock)
        self.demand = DemandService(self.store, self.clock, self.policy)
        self.coverage = CoverageService(self.store, self.clock)
        self.forecasts = ForecastService(self.store, self.clock, self.policy)
        self.planning = PlanningService(self.store, self.clock, self.policy)
        # Calculation Versions (registered once; ids persisted in system_metadata for reopen).
        self.demand_cv = self._calc_version("new_inventory_demand", "demand_cv_id", "1.0.0")
        self.plan_cv = self._calc_version("new_inventory_plan", "plan_cv_id", "1.0.0")

    def _calc_version(self, family_name, meta_key, semver):
        cvid = self.stack.metadata.get(meta_key)
        if cvid is not None:
            return cvid
        cf = self.p3.calc_family(name=family_name)
        cv = self.p3.calc_version(cf.id, semver, lifecycle="active", change=family_name)
        self.stack.metadata.put_if_absent(meta_key, cv.id)
        return cv.id

    def reopen(self):
        return Phase4(self.stack.db.path)

    def close(self):
        self.stack.close()

    # ---- builders ---------------------------------------------------------
    def combination(self, *, scope=SCOPE, model="QX80", model_year="2026", trim="LUXE",
                    drivetrain="AWD", exterior_color="BLACK", interior_color="GRAPHITE",
                    franchise="INFINITI", model_year_material=True, source_ref="dms", **extra):
        attrs = dict(model=model, model_year=model_year, trim=trim, drivetrain=drivetrain,
                     exterior_color=exterior_color, interior_color=interior_color, franchise=franchise)
        attrs.update(extra)
        return self.combos.resolve_or_create(attrs, scope, model_year_material=model_year_material,
                                              source_ref=source_ref)

    def coverage_family(self, *, dims=None, default_resolution=None):
        return self.p3.family(category="OPERATIONAL_CONSTRAINT", name="desired_ending_coverage",
                              dims=dims if dims is not None else ["store", "model", "model_year"],
                              default_resolution=default_resolution or {"mode": "unresolved"})

    def coverage_version(self, family_id, *, months=None, units=None, scope=None, store_scope=SCOPE):
        value = {"mode": "months", "value": months} if months is not None else {"mode": "units", "value": units}
        return self.p3.version(family_id, value, scope=scope or {"store": "HG"}, lifecycle="ACTIVE",
                               effective_start="2020-01-01T00:00:00+00:00", store_scope=store_scope)

    def seed_retail(self, comb, month_counts, *, scope=SCOPE, model_year="2026"):
        events = []
        for month, n in month_counts.items():
            for j in range(n):
                uid = f"vu_{comb.id}_{month}_{j}"          # unique per month so re-seeding never collides
                events.append({"vehicle_unit_id": uid, "retail_event_ref": f"re_{uid}",
                               "retail_date": f"{month}-15", "model_year": model_year,
                               "fact_refs": [f"fact_{uid}"]})
        return self.retail.project(comb.id, scope, events)

    def seed_availability(self, comb, rows, *, scope=SCOPE):
        return self.availability.reconstruct(comb.id, scope, rows)

    def seed_current(self, comb, units, *, scope=SCOPE):
        return self.supply.project_current(comb.id, scope, units)

    def seed_future(self, comb, orders, *, scope=SCOPE):
        return self.supply.project_future(comb.id, scope, orders)

    def approved_commitment(self, comb, *, scope=SCOPE, unit_id, arrival_month, commitment_type="cpo_like"):
        c = self.supply.propose_commitment(comb.id, scope, commitment_type=commitment_type,
                                            unit_or_order_id=unit_id, arrival_month=arrival_month,
                                            source="synthetic")
        return self.supply.approve_commitment(c.id, decision_ref=f"dec_{unit_id}", approval_time=AT)

    def issue_demand(self, comb, *, scope=SCOPE, horizon=None, trend=1.0, trend_method="stable",
                     seasonality=None, inherited=None, inherit_allowed=False, policy_versions=None,
                     scenario_id=None):
        horizon = horizon or HORIZON
        rbm = self.retail.retail_by_month(comb.id, scope)
        exposure = self.availability.exposure_months(comb.id, scope)
        gaps = self.availability.has_gaps(comb.id, scope)
        return self.demand.issue(comb, scope, horizon, retail_by_month=rbm, exposure_months=exposure,
                                 sample_size=sum(rbm.values()), trend=trend, trend_method=trend_method,
                                 seasonality=seasonality, inherited=inherited, inherit_allowed=inherit_allowed,
                                 gaps=gaps, policy_versions=policy_versions,
                                 calculation_version=self.demand_cv, scenario_id=scenario_id)

    def issue_plan(self, comb, demand_result, *, scope=SCOPE, coverage_resolution=None,
                   coverage_target=None, horizon=None, scenario_id=None):
        horizon = horizon or HORIZON
        qualifying = self.supply.qualifying_supply(comb.id, scope)
        counts = self.supply.counts(comb.id, scope)
        if coverage_target is None and coverage_resolution is not None:
            rate = (sum(demand_result.monthly_expected.values()) / len(demand_result.monthly_expected)
                    if demand_result.monthly_expected else 0.0)
            coverage_target = target_units(coverage_resolution, rate)
        return self.planning.issue(demand_result, horizon=horizon, qualifying=qualifying,
                                   coverage_target=coverage_target, counts=counts,
                                   calculation_version=self.plan_cv, coverage_resolution=coverage_resolution,
                                   scenario_id=scenario_id)


# ---------------------------------------------------------------------------
# 40 dealership-representative synthetic scenarios (builders). Each returns a
# handle dict; `build_all_scenarios` proves every one constructs valid records.
# ---------------------------------------------------------------------------
STABLE_HISTORY = {"2025-09": 2, "2025-10": 2, "2025-11": 2, "2025-12": 2, "2026-01": 2, "2026-02": 2,
                  "2026-03": 2, "2026-04": 2}
AVAIL_STABLE = [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2, "snapshot": "full"}
                for m in ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]]


def _stable(p4, **kw):
    c = p4.combination(**kw)
    p4.seed_retail(c, STABLE_HISTORY)
    p4.seed_availability(c, AVAIL_STABLE)
    return c


SCENARIO_NAMES = [
    "exact_stable", "exact_no_sales_available", "unavailable_full_period", "partial_availability",
    "stockout_after_strong", "low_sample", "new_model_year_lineage", "changed_generation_no_lineage",
    "exterior_match_diff_interior", "same_trim_diff_drivetrain", "current_inventory_unit",
    "future_production_unit", "pre_vin_later_vin", "approved_commitment", "proposed_unapproved",
    "cancelled_commitment", "duplicate_observation", "corrected_retail", "reversed_retail",
    "arrival_after_forecast_month", "eta_range_crossing_months", "unresolved_eta", "unresolved_identity",
    "model_year_transition", "seasonal_history", "sparse_seasonal", "rising_trend", "declining_trend",
    "stable_trend", "missing_coverage_policy", "broad_coverage_fallback", "exact_coverage_override",
    "conflicting_coverage_policy", "official_calculation", "hypothetical_scenario", "added_qualifying_supply",
    "removed_qualifying_supply", "changed_acquisition_path", "repeat_reproducible", "changed_forecast_new_facts",
]


def build_all_scenarios(p4):
    """Construct all 40 scenarios; returns {name: handle}. Used to prove fixture completeness."""
    out = {}
    # 1 exact stable
    out["exact_stable"] = _stable(p4, exterior_color="BLACK")
    # 2 available but no sales
    c = p4.combination(exterior_color="WHITE")
    p4.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 0, "retail": 0, "snapshot": "full"}
                             for m in ["2026-01", "2026-02", "2026-03"]])
    out["exact_no_sales_available"] = c
    # 3 unavailable the whole period
    c = p4.combination(exterior_color="SILVER")
    p4.seed_availability(c, [{"month": m, "opening_depth": 0, "arrivals": 0, "retail": 0, "snapshot": "full"}
                             for m in ["2026-01", "2026-02", "2026-03"]])
    out["unavailable_full_period"] = c
    # 4 partial availability (partial snapshot)
    c = p4.combination(exterior_color="BLUE")
    p4.seed_availability(c, [{"month": "2026-01", "opening_depth": 2, "arrivals": 0, "retail": 1, "snapshot": "partial",
                              "depth_known": False}])
    out["partial_availability"] = c
    # 5 stockout after strong sales
    c = p4.combination(exterior_color="RED")
    p4.seed_retail(c, {"2026-01": 4, "2026-02": 4})
    p4.seed_availability(c, [{"month": "2026-01", "opening_depth": 4, "arrivals": 0, "retail": 4, "snapshot": "full"},
                             {"month": "2026-02", "opening_depth": 0, "arrivals": 0, "retail": 0, "stockout": True,
                              "snapshot": "full"}])
    out["stockout_after_strong"] = c
    # 6 low sample
    c = p4.combination(exterior_color="GREEN")
    p4.seed_retail(c, {"2026-02": 1})
    p4.seed_availability(c, [{"month": "2026-02", "opening_depth": 1, "arrivals": 0, "retail": 1, "snapshot": "full"}])
    out["low_sample"] = c
    # 7 new model-year lineage
    prior = _stable(p4, model_year="2025", exterior_color="BLACK")
    cur = p4.combination(model_year="2026", exterior_color="BLACK", trim="LUXE", drivetrain="AWD",
                         interior_color="GRAPHITE")
    p4.combos.link_lineage(prior.id, cur.id, "new_model_year")
    out["new_model_year_lineage"] = {"prior": prior, "current": cur}
    # 8 changed generation, no approved lineage
    old = _stable(p4, model="QX55", model_year="2023")
    newgen = p4.combination(model="QX55", model_year="2026")
    out["changed_generation_no_lineage"] = {"old": old, "new": newgen}
    # 9 exterior match, different interior
    a = p4.combination(exterior_color="BLACK", interior_color="GRAPHITE")
    b = p4.combination(exterior_color="BLACK", interior_color="WHEAT")
    out["exterior_match_diff_interior"] = {"a": a, "b": b}
    # 10 same trim, different drivetrain
    a = p4.combination(drivetrain="AWD")
    b = p4.combination(drivetrain="RWD")
    out["same_trim_diff_drivetrain"] = {"a": a, "b": b}
    # 11 current inventory unit
    c = p4.combination(exterior_color="MOON")
    out["current_inventory_unit"] = (c, p4.seed_current(c, [{"vehicle_unit_id": "vu_cur_1",
                                     "state": "available_unsold", "identity_status": "resolved"}]))
    # 12 future production unit
    c = p4.combination(exterior_color="SLATE")
    out["future_production_unit"] = (c, p4.seed_future(c, [{"production_order_id": "po_1",
                                     "arrival_month": "2026-10"}]))
    # 13 pre-VIN then VIN (same order)
    c = p4.combination(exterior_color="DUNE")
    out["pre_vin_later_vin"] = (c, p4.seed_future(c, [
        {"production_order_id": "po_2", "arrival_month": "2026-10"},
        {"production_order_id": "po_2", "vehicle_unit_id": "vu_late", "arrival_month": "2026-10"}]))
    # 14 approved commitment
    c = p4.combination(exterior_color="ONYX")
    out["approved_commitment"] = (c, p4.approved_commitment(c, unit_id="cpo_unit_1", arrival_month="2026-10"))
    # 15 proposed but unapproved
    c = p4.combination(exterior_color="PEARL")
    out["proposed_unapproved"] = (c, p4.supply.propose_commitment(
        c.id, SCOPE, commitment_type="cpo_like", unit_or_order_id="prop_1", arrival_month="2026-10"))
    # 16 cancelled commitment
    c = p4.combination(exterior_color="STORM")
    cm = p4.approved_commitment(c, unit_id="cancel_1", arrival_month="2026-10")
    out["cancelled_commitment"] = (c, p4.supply.cancel_commitment(cm.id, reason="synthetic_cancel"))
    # 17 duplicate observation
    c = p4.combination(exterior_color="SAND")
    out["duplicate_observation"] = (c, p4.retail.project(c.id, SCOPE, [
        {"vehicle_unit_id": "dup_1", "retail_date": "2026-02-10"},
        {"vehicle_unit_id": "dup_1", "retail_date": "2026-02-10"}]))
    # 18 corrected retail
    c = p4.combination(exterior_color="FROST")
    rs = p4.retail.project(c.id, SCOPE, [{"vehicle_unit_id": "cr_1", "retail_date": "2026-02-10"}])
    corrected = p4.retail.correct(rs[0].id, {"combination_id": c.id, "vehicle_unit_id": "cr_1",
                                             "retail_date": "2026-03-10"}, SCOPE)
    out["corrected_retail"] = (c, corrected)
    # 19 reversed retail
    c = p4.combination(exterior_color="EMBER")
    rs = p4.retail.project(c.id, SCOPE, [{"vehicle_unit_id": "rv_1", "retail_date": "2026-02-10"}])
    out["reversed_retail"] = (c, p4.retail.reverse(rs[0].id, c.id, SCOPE, reason="unwound"))
    # 20 arrival after forecast horizon
    c = p4.combination(exterior_color="COBALT")
    out["arrival_after_forecast_month"] = (c, p4.seed_future(c, [{"production_order_id": "late_po",
                                           "arrival_month": "2027-09"}]))
    # 21 ETA range crossing months
    c = p4.combination(exterior_color="JADE")
    out["eta_range_crossing_months"] = (c, p4.seed_future(c, [{"production_order_id": "cross_po",
                                        "eta_start": "2026-10-20", "eta_end": "2026-11-10", "arrival_month": "2026-11"}]))
    # 22 unresolved ETA
    c = p4.combination(exterior_color="RUST")
    out["unresolved_eta"] = (c, p4.seed_future(c, [{"production_order_id": "noeta_po", "arrival_month": None,
                                                    "timing_confidence": "unknown"}]))
    # 23 unresolved identity current unit
    c = p4.combination(exterior_color="CLAY")
    out["unresolved_identity"] = (c, p4.seed_current(c, [{"vehicle_unit_id": None, "state": "available_unsold",
                                                          "identity_status": "unresolved"}]))
    # 24 model-year transition (both years present)
    y25 = _stable(p4, model="Q50", model_year="2025")
    y26 = _stable(p4, model="Q50", model_year="2026")
    out["model_year_transition"] = {"2025": y25, "2026": y26}
    # 25 seasonal history (12 months, clear seasonality)
    c = p4.combination(model="QX60", exterior_color="BLACK")
    seasonal = {f"2025-{mm:02d}": (5 if mm in (3, 4, 5) else 1) for mm in range(1, 13)}
    p4.seed_retail(c, seasonal)
    p4.seed_availability(c, [{"month": f"2025-{mm:02d}", "opening_depth": 5, "arrivals": 2,
                              "retail": (5 if mm in (3, 4, 5) else 1), "snapshot": "full"} for mm in range(1, 13)])
    out["seasonal_history"] = c
    # 26 sparse seasonal (few months)
    c = p4.combination(model="QX60", exterior_color="WHITE")
    p4.seed_retail(c, {"2026-03": 5})
    p4.seed_availability(c, [{"month": "2026-03", "opening_depth": 5, "arrivals": 0, "retail": 5, "snapshot": "full"}])
    out["sparse_seasonal"] = c
    # 27/28/29 trend variants
    out["rising_trend"] = _stable(p4, model="QX80", exterior_color="RISE")
    out["declining_trend"] = _stable(p4, model="QX80", exterior_color="FALL")
    out["stable_trend"] = _stable(p4, model="QX80", exterior_color="EVEN")
    # 30 missing coverage policy
    fam = p4.coverage_family()
    out["missing_coverage_policy"] = {"family": fam}
    # 31 broad coverage fallback
    fam2 = p4.coverage_family(default_resolution={"mode": "unresolved"})
    broad = p4.coverage_version(fam2.id, months=2, scope={"store": "HG"})  # store-level broad coverage
    out["broad_coverage_fallback"] = {"family": fam2, "broad": broad}
    # 32 exact-combination coverage override (more specific)
    fam3 = p4.coverage_family()
    broad3 = p4.coverage_version(fam3.id, months=2, scope={"store": "HG"})
    exact3 = p4.coverage_version(fam3.id, units=10, scope={"store": "HG", "model": "QX80", "model_year": "2026"})
    out["exact_coverage_override"] = {"family": fam3, "broad": broad3, "exact": exact3}
    # 33 conflicting coverage policy (two equally-specific different values)
    fam4 = p4.coverage_family()
    a4 = p4.coverage_version(fam4.id, units=5, scope={"store": "HG"})
    b4 = p4.coverage_version(fam4.id, units=9, scope={"store": "HG"})
    out["conflicting_coverage_policy"] = {"family": fam4, "a": a4, "b": b4}
    # 34 official calculation
    c = _stable(p4, exterior_color="OFFCL")
    d = p4.issue_demand(c)
    out["official_calculation"] = (c, d)
    # 35 hypothetical scenario calculation
    c = _stable(p4, exterior_color="SCEN")
    d = p4.issue_demand(c, scenario_id="scenario_A")
    out["hypothetical_scenario"] = (c, d)
    # 36 added qualifying supply
    c = _stable(p4, exterior_color="ADD")
    p4.seed_future(c, [{"production_order_id": "add_po", "arrival_month": "2026-10"}])
    out["added_qualifying_supply"] = c
    # 37 removed qualifying supply
    c = _stable(p4, exterior_color="RMV")
    p4.seed_future(c, [{"production_order_id": "rmv_po", "arrival_month": "2026-10",
                        "cancellation_status": "cancelled"}])
    out["removed_qualifying_supply"] = c
    # 38 changed acquisition path (label change only)
    c = _stable(p4, exterior_color="PATH")
    out["changed_acquisition_path"] = (c, p4.approved_commitment(c, unit_id="path_1", arrival_month="2026-10",
                                                                 commitment_type="dealer_trade_like"))
    # 39 repeat reproducible
    c = _stable(p4, exterior_color="REPRO")
    out["repeat_reproducible"] = (c, p4.issue_demand(c))
    # 40 changed forecast from new facts
    c = _stable(p4, exterior_color="NEWFCT")
    out["changed_forecast_new_facts"] = c
    return out
