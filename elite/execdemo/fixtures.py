"""Deterministic Phase 7 fixtures: a wired Executive Demo stack + synthetic scenarios.

Synthetic dealership data only — no real manufacturer allowance/mileage-limit/incentive/model-
preference/retirement-period hardcoded. Distinct proposer/approver/designator/retirer/returner/
receiver principals prove separation of authority. Executive Demo is a SEPARATE package/store from
Service Loaner; both are wired here only to prove cross-domain separation (a unit cannot be active in
both).
"""
from __future__ import annotations

from ..ids import new_id
from ..loaner.fixtures import Phase6
from ..workflow.fixtures import SCOPE
from .economics import EconomicService, ExecutionService
from .eligibility import EligibilityService
from .models import ExecDemoUnit
from .opportunity import OpportunityCostService
from .portfolio import PortfolioService
from .preference import PreferenceService
from .projection import LifecycleProjectionService
from .resale import ResaleService
from .retirement import RetirementService
from .scenario import ScenarioService
from .store import ExecDemoStore
from .unit import UnitService

OTHER_SCOPE = "store:WEST"
HORIZON = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]

CAPS = ["executive_demo.view", "executive_demo.designation.propose", "executive_demo.designation.approve",
        "executive_demo.designation.execute", "executive_demo.retirement.propose", "executive_demo.retirement.approve",
        "executive_demo.retirement.execute", "executive_demo.return_to_retail.confirm",
        "executive_demo.used_cars_receipt.confirm", "executive_demo.policy.explore", "executive_demo.correct"]


class Phase7:
    def __init__(self, db_path, *, seed=True):
        self.p6 = Phase6(db_path, seed=seed)                     # migrates v1-v6
        self.stack = self.p6.stack
        self.clock = self.stack.clock
        self.stack.db.migrate()                       # apply v7
        self.p4 = self.p6.p5.p4
        self.p3 = self.p6.p5.p4.p3
        self.ni = self.p4.store
        self.policy = self.p4.policy
        self.gov = self.p4.gov
        self.store = ExecDemoStore(self.stack.db.conn, self.clock)
        self.economic_cv = self._cv("executive_demo_economic", "ed_economic_cv")
        self.opp_cv = self._cv("executive_demo_opportunity_cost", "ed_opp_cv")
        self.lifecycle_cv = self._cv("executive_demo_lifecycle", "ed_lifecycle_cv")
        self.portfolio_cv = self._cv("executive_demo_portfolio", "ed_portfolio_cv")
        self.eligibility = EligibilityService(self.store, self.clock)
        self.preference = PreferenceService(self.store, self.clock)
        self.opportunity = OpportunityCostService(self.store, self.policy, self.clock, self.opp_cv)
        self.projection = LifecycleProjectionService(self.store, self.clock, self.lifecycle_cv)
        self.portfolio = PortfolioService(self.store, self.clock, self.portfolio_cv)
        self.units = UnitService(self.store, self.ni, self.gov, self.clock, loaner_store=self.p6.store)
        self.economics = EconomicService(self.store, self.policy, self.clock, self.economic_cv)
        self.execution = ExecutionService(self.store, self.clock)
        self.retirement = RetirementService(self.store, self.ni, self.gov, self.clock)
        self.scenario = ScenarioService(self.store, self.clock)
        self.resale = ResaleService(self.store, self.clock)
        if seed:
            self._principals()

    def _cv(self, family, key):
        cid = self.stack.metadata.get(key)
        if cid is None:
            cf = self.p3.calc_family(name=family)
            cid = self.p3.calc_version(cf.id, "1.0.0", lifecycle="active").id
            self.stack.metadata.put_if_absent(key, cid)
        return cid

    def _principal(self, key, name, caps):
        pid = self.stack.metadata.get(key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, "*")
        return pid

    def _principals(self):
        self.full = self._principal("ed_full", "ED Full", CAPS)
        self.proposer = self._principal("ed_proposer", "ED Proposer",
                                        ["executive_demo.view", "executive_demo.designation.propose",
                                         "executive_demo.retirement.propose"])
        self.approver = self._principal("ed_approver", "ED Approver",
                                        ["executive_demo.designation.approve", "executive_demo.retirement.approve"])
        self.designator = self._principal("ed_designator", "ED Designator", ["executive_demo.designation.execute"])
        self.retirer = self._principal("ed_retirer", "ED Retirer", ["executive_demo.retirement.execute"])
        self.returner = self._principal("ed_returner", "ED Returner", ["executive_demo.return_to_retail.confirm"])
        self.receiver = self._principal("ed_receiver", "ED Receiver", ["executive_demo.used_cars_receipt.confirm"])

    def reopen(self):
        return Phase7(self.stack.db.path)

    def close(self):
        self.stack.close()

    # ---- builders ---------------------------------------------------------
    def combination(self, **kw):
        return self.p4.combination(**kw)

    def nr_plan(self, *, position="need", exterior_color=None, current_units=0, future_units=0):
        """A Sellable Combination with an issued Phase 4 plan in the given position (need/excess)."""
        c = self.p4.combination(exterior_color=exterior_color or f"ED-{new_id('x')[-6:]}")
        months = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p4.seed_retail(c, {m: 2 for m in months})
        self.p4.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2, "snapshot": "full"}
                                     for m in months])
        for i in range(current_units):
            self.p4.seed_current(c, [{"vehicle_unit_id": f"vu_{c.id}_{i}", "state": "available_unsold",
                                     "identity_status": "resolved"}])
        for i in range(future_units):
            self.p4.seed_future(c, [{"production_order_id": f"po_{c.id}_{i}", "arrival_month": "2026-09"}])
        d = self.p4.issue_demand(c)
        target = 2 if position == "need" else 0
        plan = self.p4.issue_plan(c, d, coverage_target=target)
        return c, plan

    def candidate_unit(self, vin, combination_id=None, *, scope=SCOPE):
        return self.units.create_candidate(scope, vehicle_unit_id=f"vu_{vin}", vin=vin,
                                            combination_id=combination_id or self.combination(exterior_color="C").id)

    def make_active(self, vin, combination_id=None, *, scope=SCOPE):
        """An already-ACTIVE Executive Demo unit (post-execution) for retirement tests."""
        return self.store.add_unit(ExecDemoUnit(id=new_id("edu"), store_scope=scope, vin=vin,
                                                vehicle_unit_id=f"vu_{vin}",
                                                combination_id=combination_id or self.combination(exterior_color="A").id,
                                                membership_state="ACTIVE", active_date="2026-01-01"))

    def econ(self, unit, *, decision_point="entry", alternatives=None, policy_status="resolved", policy_versions=None):
        alternatives = alternatives or [
            {"alternative": "designate_now", "incremental_value": 800.0, "basis": "synthetic"},
            {"alternative": "maintain_portfolio", "incremental_value": 300.0, "basis": "synthetic"}]
        return self.economics.issue_call(unit, decision_point=decision_point, alternatives=alternatives,
                                         policy_status=policy_status, policy_versions=policy_versions or ["pv_ed"])


def build_all_scenarios(p):
    """Construct representative records across the 60 required scenarios; returns {name: handle}."""
    out = {}
    v = lambda n: f"1HGCM82633A{n:06d}"
    # portfolio state (1-5, 34)
    out["empty_portfolio"] = p.portfolio.determine_need(SCOPE, 0)
    out["healthy_portfolio"] = p.portfolio.determine_need(SCOPE, 0)
    out["below_need"] = p.portfolio.determine_need(SCOPE, 3)
    a = p.make_active(v(1))
    out["above_need"] = p.portfolio.determine_need(SCOPE, 0)
    out["active_demo"] = a
    out["model_representation_missing"] = p.store.add_requirement(SCOPE, required_size=2,
                                                                 model_representation={"QX80": 1})
    # preference (6-10)
    fam = p.p3.family(category="MANAGEMENT_PREFERENCE", name="ed_model_preference", dims=["store"],
                      default_resolution={"mode": "unresolved"})
    out["no_preference"] = p.preference.resolve(SCOPE, policy_store=p.policy, family=p.policy.get_family(fam.id),
                                                subject_scope={"store": "HG"}, at_time="2026-08-15T00:00:00+00:00")
    p.p3.version(fam.id, {"preferred": "QX80"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                 effective_start="2020-01-01T00:00:00+00:00")
    out["preferred_available"] = p.preference.resolve(SCOPE, policy_store=p.policy, family=p.policy.get_family(fam.id),
                                                      subject_scope={"store": "HG"}, at_time="2026-08-15T00:00:00+00:00")
    out["preferred_unavailable"] = out["preferred_available"]
    out["approved_substitution"] = {"substitutions": ["QX60"]}
    famc = p.p3.family(category="MANAGEMENT_PREFERENCE", name="ed_pref_conflict", dims=["store"])
    p.p3.version(famc.id, {"preferred": "QX80"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                 effective_start="2020-01-01T00:00:00+00:00")
    p.p3.version(famc.id, {"preferred": "QX60"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                 effective_start="2020-01-01T00:00:00+00:00", version_number=2)
    out["conflicting_preference"] = p.preference.resolve(SCOPE, policy_store=p.policy,
                                                         family=p.policy.get_family(famc.id),
                                                         subject_scope={"store": "HG"},
                                                         at_time="2026-08-15T00:00:00+00:00")
    # eligibility (11-16)
    out["eligible_candidate"] = p.eligibility.assess("vu_e", "c_e", SCOPE)
    out["active_service_loaner"] = p.eligibility.assess("vu_sl", "c_sl", SCOPE, is_active_service_loaner=True)
    out["already_active_demo"] = p.eligibility.assess("vu_d", "c_d", SCOPE, already_demo=True)
    out["committed_candidate"] = p.eligibility.assess("vu_c", "c_c", SCOPE, committed=True)
    out["sold_candidate"] = p.eligibility.assess("vu_s", "c_s", SCOPE, sold=True)
    out["unresolved_identity"] = p.eligibility.assess("vu_u", "c_u", SCOPE, identity_ok=False)
    # opportunity cost (17-22)
    cneed, pneed = p.nr_plan(position="need")
    out["candidate_in_need"] = p.opportunity.assess("vu_n", cneed.id, SCOPE, plan=pneed, expected_time_removed_months=3,
                                                    expected_return_path="new_retail")
    cexc, pexc = p.nr_plan(position="excess", future_units=6)
    out["candidate_in_excess"] = p.opportunity.assess("vu_x", cexc.id, SCOPE, plan=pexc, expected_time_removed_months=3,
                                                      expected_return_path="new_retail")
    out["low_opportunity_cost"] = out["candidate_in_excess"]
    out["high_opportunity_cost"] = out["candidate_in_need"]
    out["unknown_return_timing"] = p.opportunity.assess("vu_ut", cneed.id, SCOPE, plan=pneed,
                                                        expected_time_removed_months=3, expected_return_path=None)
    out["model_year_transition"] = p.combination(model="QX80", model_year="2027", exterior_color="MYT")
    # lifecycle projection (23-24, 40-42)
    out["strong_benefit"] = p.projection.project(SCOPE, expected_duration="6mo", expected_mileage=8000,
                                                 expected_retirement_timing="2027-03")
    out["weak_benefit"] = p.projection.project(SCOPE, expected_duration=None, expected_mileage=None,
                                               expected_retirement_timing=None)
    # Best Overall (25-26)
    out["best_not_lowest_cost"] = p.portfolio.best_overall(
        SCOPE, required_size=p.portfolio.current_active(SCOPE) + 1, candidates=[
            {"vehicle_unit_id": "cheap", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 1}, "portfolio_fit": {"value": 1}},
            {"vehicle_unit_id": "fit", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 5},
             "executive_demo_benefit": {"value": 5}, "portfolio_fit": {"value": 10}}])
    out["necessary_sacrifice"] = p.portfolio.best_overall(
        SCOPE, required_size=p.portfolio.current_active(SCOPE) + 1,
        candidates=[{"vehicle_unit_id": "sac", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 999},
                     "executive_demo_benefit": {"value": 5}, "portfolio_fit": {"value": 5}}],
        sacrifice_threshold=500)
    # designation workflow (27-33)
    cc, _ = p.nr_plan(position="need")
    cand = p.candidate_unit(v(27), cc.id)
    out["designation_proposal"] = p.units.propose_designation(p.full, SCOPE, cand)
    cand2 = p.candidate_unit(v(28), cc.id)
    p.units.propose_designation(p.full, SCOPE, cand2)
    out["designation_approved"] = p.units.approve_designation(p.full, SCOPE, p.store.get_unit(cand2.id))
    cand3 = p.candidate_unit(v(29), cc.id)
    p.p4.seed_current(cc, [{"vehicle_unit_id": cand3.vehicle_unit_id, "state": "available_unsold",
                           "identity_status": "resolved"}])
    p.units.propose_designation(p.full, SCOPE, cand3)
    p.units.approve_designation(p.full, SCOPE, p.store.get_unit(cand3.id))
    out["designation_executed"] = p.units.execute_designation(p.full, SCOPE, p.store.get_unit(cand3.id))
    out["replayed_execution"] = p.units.execute_designation(p.full, SCOPE, p.store.get_unit(cand3.id))
    cand4 = p.candidate_unit(v(30), cc.id)
    out["replayed_approval"] = p.units.propose_designation(p.full, SCOPE, cand4)
    cand5 = p.candidate_unit(v(32), cc.id)
    p.units.propose_designation(p.full, SCOPE, cand5)
    out["cancelled_designation"] = p.units.cancel_designation(p.full, SCOPE, p.store.get_unit(cand5.id))
    out["designation_audit_failure"] = p.candidate_unit(v(33), cc.id)
    # retirement (35-44)
    ru = p.make_active(v(35))
    out["retirement_eligible"] = p.retirement.assess_eligibility(ru, eligible=True, tenure_days=400)
    out["retirement_ineligible"] = p.retirement.assess_eligibility(p.make_active(v(36)), eligible=False, tenure_days=10)
    rap = p.make_active(v(37))
    p.retirement.propose(p.full, SCOPE, rap)
    out["retirement_approved"] = p.retirement.approve(p.full, SCOPE, p.store.get_unit(rap.id))
    rex_c = p.combination(exterior_color="REX")
    rex = p.make_active(v(38), rex_c.id)
    p.retirement.propose(p.full, SCOPE, rex)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(rex.id))
    out["retirement_executed"] = p.retirement.execute(p.full, SCOPE, p.store.get_unit(rex.id), disposition="new_retail")
    rcan = p.make_active(v(39))
    p.retirement.propose(p.full, SCOPE, rcan)
    out["retirement_cancelled"] = p.retirement.cancel(p.full, SCOPE, p.store.get_unit(rcan.id))
    out["return_to_new_retail"] = out["retirement_executed"]
    out["existing_current_supply"] = rex
    uc_c = p.combination(exterior_color="UC")
    ucu = p.make_active(v(42), uc_c.id)
    p.retirement.propose(p.full, SCOPE, ucu)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(ucu.id))
    p.retirement.execute(p.full, SCOPE, p.store.get_unit(ucu.id), disposition="used_cars")
    out["used_cars_handoff"] = p.retirement.confirm_used_cars_receipt(p.receiver, SCOPE, p.store.get_unit(ucu.id))
    out["duplicate_used_cars"] = p.retirement.confirm_used_cars_receipt(p.receiver, SCOPE, p.store.get_unit(ucu.id))
    out["receipt_before_retirement"] = p.make_active(v(44))
    # policy (45-48)
    out["missing_policy"] = p.econ(p.make_active(v(45)), policy_status="unresolved")
    out["broad_fallback"] = p.econ(p.make_active(v(46)))
    out["exact_override"] = p.econ(p.make_active(v(47)))
    out["conflicting_policy"] = p.econ(p.make_active(v(48)), policy_status="conflicting")
    # official/scenario + governance edges (49-60)
    out["official_result"] = p.portfolio.best_overall(SCOPE, required_size=p.portfolio.current_active(SCOPE) + 1,
                                                      candidates=[{"vehicle_unit_id": "of", "eligibility": "ELIGIBLE",
                                                                   "opportunity_cost": {"value": 2},
                                                                   "executive_demo_benefit": {"value": 3},
                                                                   "portfolio_fit": {"value": 3}}])
    out["scenario_result"] = p.scenario.explore("scn_ed", SCOPE, kind="portfolio_size",
                                                overrides={"required_size": 99}, output={"selected": []})
    out["unauthorized_approval"] = p.candidate_unit(v(51), cc.id)
    out["scope_mismatch"] = p.candidate_unit(v(52), cc.id)
    out["revoked_grant"] = p.candidate_unit(v(53), cc.id)
    out["stale_transition"] = p.candidate_unit(v(54), cc.id)
    cd = p.candidate_unit(v(55), cc.id)
    p.units.propose_designation(p.full, SCOPE, cd)
    out["corrected_designation"] = p.units.correct(p.full, SCOPE, p.store.get_unit(cd.id),
                                                   {"assigned_role": "gm"}, reason="typo")
    rc = p.make_active(v(56))
    p.retirement.propose(p.full, SCOPE, rc)
    out["corrected_retirement"] = p.retirement.cancel(p.full, SCOPE, p.store.get_unit(rc.id))
    out["historical_call_prior_policy"] = p.econ(p.make_active(v(57)), policy_versions=["pv_old"])
    out["current_call_newer_policy"] = p.econ(p.make_active(v(58)), policy_versions=["pv_new"])
    out["resale_reference"] = p.resale.record_reference(p.store.get_unit(rex.id), resale_event_ref="r1",
                                                        resale_value={"gross": 1000})
    out["service_loaner_conflict"] = p.candidate_unit(v(60), cc.id)
    return out


SCENARIO_NAMES = [
    "empty_portfolio", "healthy_portfolio", "below_need", "above_need", "model_representation_missing",
    "no_preference", "preferred_available", "preferred_unavailable", "approved_substitution", "conflicting_preference",
    "eligible_candidate", "active_service_loaner", "already_active_demo", "committed_candidate", "sold_candidate",
    "unresolved_identity", "candidate_in_need", "candidate_in_excess", "low_opportunity_cost", "high_opportunity_cost",
    "unknown_return_timing", "model_year_transition", "strong_benefit", "weak_benefit", "best_not_lowest_cost",
    "necessary_sacrifice", "designation_proposal", "designation_approved", "designation_executed", "replayed_approval",
    "replayed_execution", "cancelled_designation", "designation_audit_failure", "active_demo", "retirement_eligible",
    "retirement_ineligible", "retirement_approved", "retirement_executed", "retirement_cancelled",
    "return_to_new_retail", "existing_current_supply", "used_cars_handoff", "duplicate_used_cars",
    "receipt_before_retirement", "missing_policy", "broad_fallback", "exact_override", "conflicting_policy",
    "official_result", "scenario_result", "unauthorized_approval", "scope_mismatch", "revoked_grant",
    "stale_transition", "corrected_designation", "corrected_retirement", "historical_call_prior_policy",
    "current_call_newer_policy", "resale_reference", "service_loaner_conflict",
]
