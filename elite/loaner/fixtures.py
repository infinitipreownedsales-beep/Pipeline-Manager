"""Deterministic Phase 6 fixtures: a wired Service Loaner stack + synthetic scenarios.

Synthetic dealership data only — no real manufacturer/dealership incentives, write-downs, eligibility
windows, or thresholds (all resolve through Phase 3 in real use; fixtures pass synthetic values).
Distinct proposer/approver/executor/returner/completer/receiver principals prove separation of
authority.
"""
from __future__ import annotations

from ..data.models import FieldSpec, SchemaProfile, SourceRegistry
from ..ids import new_id
from ..workflow.fixtures import SCOPE, Phase5
from .dating import DatingService
from .economics import EconomicService
from .execution import ExecutionService
from .monitoring import MonitoringService
from .models import ServiceLoanerUnit
from .portfolio import PortfolioService
from .resale import ResaleService
from .retirement import RetirementService
from .scenario import ScenarioService
from .snapshot import SnapshotService
from .store import LoanerStore
from .unit import UnitService

OTHER_SCOPE = "store:WEST"
GOOD_VINS = [f"1GNSKBKC5FR{n:06d}" for n in range(1, 400)]

CAPS = ["service_loaner.view", "service_loaner.entry.propose", "service_loaner.entry.approve",
        "service_loaner.entry.execute", "service_loaner.retirement.propose", "service_loaner.retirement.approve",
        "service_loaner.return.confirm", "service_loaner.retirement.complete",
        "service_loaner.used_cars_receipt.confirm", "service_loaner.policy.explore", "service_loaner.correct"]

LOANER_FIELDS = [
    FieldSpec("vin", required=True, kind="vin", meaning="VIN"),
    FieldSpec("rental_status", required=False, kind="text", meaning="rented/available"),
    FieldSpec("in_service_date", required=False, kind="date", meaning="in-service date"),
    FieldSpec("checkout_mileage", required=False, kind="int", meaning="last checkout mileage"),
]


class Phase6:
    def __init__(self, db_path, *, seed=True):
        self.p5 = Phase5(db_path, seed=seed)                       # migrates v1-v5
        self.stack = self.p5.stack
        self.clock = self.stack.clock
        self.stack.db.migrate()                         # apply v6
        self.p3 = self.p5.p4.p3
        self.data = self.p5.p4.p3.p2.store              # Phase 2 DataStore
        self.ingestion = self.p5.p4.p3.p2.ingestion
        self.ni = self.p5.ni
        self.policy = self.p5.policy
        self.gov = self.p5.gov
        self.store = LoanerStore(self.stack.db.conn, self.clock)
        self._sources()
        self.economic_cv = self._cv("service_loaner_economic", "sl_economic_cv")
        self.portfolio_cv = self._cv("service_loaner_portfolio", "sl_portfolio_cv")
        self.units = UnitService(self.store, self.gov, self.clock)
        self.snapshot = SnapshotService(self.store, self.data, self.ingestion, self.clock, SCOPE)
        self.dating = DatingService(self.store, self.clock)
        self.monitoring = MonitoringService(self.store, self.clock)
        self.economics = EconomicService(self.store, self.policy, self.clock, self.economic_cv)
        self.execution = ExecutionService(self.store, self.clock)
        self.portfolio = PortfolioService(self.store, self.clock, self.portfolio_cv)
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

    def _sources(self):
        if self.data.get_source("src_loaner") is None:
            self.data.add_source(SourceRegistry(id="src_loaner", name="Loaner Fleet Snapshot", owner="dealership",
                                                source_type="dms", supported_profiles=["prof_loaner_v1"],
                                                authoritative_fact_types=["loaner_present"], scope=SCOPE))
            self.data.add_profile(SchemaProfile(id="prof_loaner_v1", source_id="src_loaner", version=1,
                                                fields=LOANER_FIELDS, snapshot_capable=True))
        if self.data.get_source("src_loaner_feed") is None:
            self.data.add_source(SourceRegistry(id="src_loaner_feed", name="Loaner Feed (non-authoritative)",
                                                owner="third_party", source_type="feed",
                                                supported_profiles=["prof_loaner_feed_v1"], scope=SCOPE))
            self.data.add_profile(SchemaProfile(id="prof_loaner_feed_v1", source_id="src_loaner_feed", version=1,
                                                fields=LOANER_FIELDS, snapshot_capable=False))

    def _principal(self, key, name, caps):
        pid = self.stack.metadata.get(key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, "*")
        return pid

    def _principals(self):
        self.full = self._principal("sl_full", "SL Full", CAPS)
        self.proposer = self._principal("sl_proposer", "SL Proposer",
                                        ["service_loaner.view", "service_loaner.entry.propose",
                                         "service_loaner.retirement.propose"])
        self.approver = self._principal("sl_approver", "SL Approver",
                                        ["service_loaner.entry.approve", "service_loaner.retirement.approve"])
        self.executor = self._principal("sl_executor", "SL Executor", ["service_loaner.entry.execute"])
        self.returner = self._principal("sl_returner", "SL Returner", ["service_loaner.return.confirm"])
        self.completer = self._principal("sl_completer", "SL Completer", ["service_loaner.retirement.complete"])
        self.receiver = self._principal("sl_receiver", "SL Receiver", ["service_loaner.used_cars_receipt.confirm"])

    def reopen(self):
        return Phase6(self.stack.db.path)

    def close(self):
        self.stack.close()

    # ---- builders ---------------------------------------------------------
    def combination(self, **kw):
        return self.p5.p4.combination(**kw)

    def make_active(self, vin, *, rental="available", in_service_date="2025-01-15", checkout_mileage=1200,
                    combination_id=None, scope=SCOPE):
        """Create an ACTIVE Service Loaner unit directly (post-entry), with in-service date + mileage.
        Each unit gets its OWN combination (keyed by VIN) so supply tests never cross-contaminate."""
        comb = combination_id or self.combination(exterior_color=f"SL-{vin[-6:]}", scope=scope).id
        u = self.store.add_unit(ServiceLoanerUnit(
            id=new_id("slu"), store_scope=scope, vin=vin,
            vehicle_unit_id=f"vu_{vin}", combination_id=comb,
            membership_state=("ACTIVE_RENTED" if rental == "rented" else "ACTIVE_AVAILABLE"),
            current_rental_state=rental, active_fleet_presence=True,
            accepted_in_service_date=in_service_date, in_service_date_authority="verified"))
        self.dating.record_mileage(u, checkout_mileage)
        return self.store.get_unit(u.id)

    def candidate(self, vin, *, combination_id=None, scope=SCOPE):
        comb = combination_id or self.combination(exterior_color="CAND").id
        return self.units.create_candidate(scope, vehicle_unit_id=f"vu_{vin}", vin=vin, combination_id=comb)

    def econ(self, unit, *, decision_point="exit", alternatives=None, policy_status="resolved", policy_versions=None):
        alternatives = alternatives or [
            {"alternative": "retire_now", "incremental_value": 500.0, "basis": "synthetic"},
            {"alternative": "remain_in_fleet", "incremental_value": 300.0, "basis": "synthetic"}]
        return self.economics.issue_call(unit, decision_point=decision_point, alternatives=alternatives,
                                         policy_status=policy_status, policy_versions=policy_versions or ["pv_synth"])


def build_all_scenarios(p):
    """Construct representative records across the 60 required scenarios; returns {name: handle}."""
    out = {}
    vi = iter(GOOD_VINS)
    v = lambda: next(vi)
    # snapshot family (1-8)
    out["valid_full_snapshot"] = p.snapshot.ingest_fleet([{"vin": v(), "rental_status": "available"}],
                                                         snapshot_type="full")
    out["invalid_full_claim"] = p.snapshot.ingest_fleet([{"vin": v(), "rental_status": "available"}],
                                                        snapshot_type="full", authoritative=False)
    out["partial_snapshot"] = p.snapshot.ingest_fleet([{"vin": v()}], snapshot_type="partial")
    a_vin = v()
    b = p.snapshot.ingest_fleet([{"vin": a_vin, "rental_status": "available"}], snapshot_type="full")
    p.snapshot.reconcile(b, [{"vin": a_vin, "rental_status": "available"}])
    out["active_present"] = a_vin
    out["active_absent_full"] = "absent_signal"
    out["invalid_vin"] = p.snapshot.ingest_fleet([{"vin": "XYZ"}], snapshot_type="full")
    out["duplicate_vin"] = v()
    out["conflicting_rental"] = v()
    # dating + mileage (9-15)
    u = p.make_active(v(), in_service_date="2025-01-15")
    out["verified_in_service"] = p.dating.resolve_in_service_date(
        u, [{"value": "2025-01-15", "source": "dms", "authority": "verified"}])
    u2 = p.make_active(v())
    out["conflicting_in_service"] = p.dating.resolve_in_service_date(
        u2, [{"value": "2025-01-15", "source": "a", "authority": "verified"},
             {"value": "2025-03-01", "source": "b", "authority": "verified"}])
    u3 = p.make_active(v())
    out["missing_in_service"] = p.dating.resolve_in_service_date(u3, [{"source": "import", "authority": "import",
                                                                       "value": "2025-06-01"}])
    out["zero_mileage"] = p.dating.record_mileage(p.make_active(v()), "0")
    out["blank_mileage"] = p.dating.record_mileage(p.make_active(v()), "")
    out["missing_mileage"] = p.dating.record_mileage(p.make_active(v()), None)
    out["invalid_mileage"] = p.dating.record_mileage(p.make_active(v()), "abc")
    # monitoring (16-19)
    ur = p.make_active(v(), rental="rented", in_service_date="2026-06-01", checkout_mileage=0)
    out["zero_rented_recent"] = p.monitoring.evaluate(ur, at_date="2026-06-05", threshold_days=30)
    ur2 = p.make_active(v(), rental="rented", in_service_date="2025-01-01", checkout_mileage=0)
    out["zero_rented_over_threshold"] = p.monitoring.evaluate(ur2, at_date="2026-06-01", threshold_days=30)
    ur3 = p.make_active(v(), rental="rented", in_service_date="2025-01-01", checkout_mileage=800)
    out["rented_nonzero"] = p.monitoring.evaluate(ur3, at_date="2026-06-01", threshold_days=30)
    out["no_longer_rented"] = ur2
    # entry candidates + portfolio (20-25)
    out["eligible_candidate"] = {"vehicle_unit_id": "vu_e", "eligible": True, "available": True,
                                 "opportunity_cost": {"value": 100}}
    out["ineligible_candidate"] = {"vehicle_unit_id": "vu_i", "eligible": False}
    active_u = p.make_active(v())
    out["already_active_candidate"] = {"vehicle_unit_id": active_u.vehicle_unit_id, "eligible": True,
                                       "actual_state": "ACTIVE_AVAILABLE"}
    out["approved_pending_entry"] = p.candidate(v())
    out["portfolio_multi"] = p.portfolio.plan_entries(
        SCOPE, required_quantity=p.portfolio.current_active(SCOPE) + 2,
        candidates=[{"vehicle_unit_id": "vu_a", "eligible": True, "available": True, "opportunity_cost": {"value": 50}},
                    {"vehicle_unit_id": "vu_b", "eligible": True, "available": True, "opportunity_cost": {"value": 90}}])
    out["necessary_sacrifice"] = p.portfolio.plan_entries(
        SCOPE, required_quantity=p.portfolio.current_active(SCOPE) + 1,
        candidates=[{"vehicle_unit_id": "vu_s", "eligible": True, "available": True, "opportunity_cost": {"value": 999}}],
        sacrifice_threshold=500)
    # retirement family (26-34)
    re_u = p.make_active(v())
    out["retirement_eligible"] = p.retirement.assess_eligibility(re_u, eligible=True, tenure_days=400)
    out["retirement_ineligible"] = p.retirement.assess_eligibility(p.make_active(v()), eligible=False, tenure_days=30)
    av_u = p.make_active(v())
    p.retirement.propose(p.full, SCOPE, av_u)
    out["approved_retire_available"] = p.retirement.approve(p.full, SCOPE, p.store.get_unit(av_u.id))
    rr_u = p.make_active(v(), rental="rented")
    p.retirement.propose(p.full, SCOPE, rr_u)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(rr_u.id))
    out["approved_retire_rented"] = p.store.get_unit(rr_u.id)
    pv_u = p.make_active(v(), rental="rented")
    p.retirement.propose(p.full, SCOPE, pv_u)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(pv_u.id))
    out["provisional_retirement"] = p.retirement.provisional(p.full, SCOPE, p.store.get_unit(pv_u.id))
    out["returned_after_provisional"] = p.retirement.confirm_return(p.full, SCOPE, p.store.get_unit(pv_u.id),
                                                                    actual_event_ref="ret_evt")
    out["return_unconfirmed"] = p.make_active(v(), rental="rented")
    comp_u = p.make_active(v())
    p.retirement.propose(p.full, SCOPE, comp_u)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(comp_u.id))
    p.retirement.confirm_return(p.full, SCOPE, p.store.get_unit(comp_u.id), actual_event_ref="e")
    out["retirement_completed"] = p.retirement.complete(p.full, SCOPE, p.store.get_unit(comp_u.id))
    can_u = p.make_active(v())
    p.retirement.propose(p.full, SCOPE, can_u)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(can_u.id))
    out["retirement_cancelled"] = p.retirement.cancel(p.full, SCOPE, p.store.get_unit(can_u.id))
    # used cars (35-38)
    out["awaiting_used_cars"] = p.store.get_unit(comp_u.id)
    out["used_cars_confirmed"] = p.retirement.confirm_used_cars_receipt(p.receiver, SCOPE, p.store.get_unit(comp_u.id))
    out["duplicate_used_cars"] = p.retirement.confirm_used_cars_receipt(p.receiver, SCOPE, p.store.get_unit(comp_u.id))
    out["receipt_before_retirement"] = p.make_active(v())
    # return to retail (39-40)
    r2r = p.make_active(v())
    p.retirement.propose(p.full, SCOPE, r2r)
    p.retirement.approve(p.full, SCOPE, p.store.get_unit(r2r.id))
    p.retirement.confirm_return(p.full, SCOPE, p.store.get_unit(r2r.id), actual_event_ref="e")
    out["return_to_new_retail"] = p.retirement.complete(p.full, SCOPE, p.store.get_unit(r2r.id), handoff="new_retail")
    out["existing_current_supply"] = r2r
    # economics/policy (41-46)
    ec_u = p.make_active(v())
    out["missing_economic_policy"] = p.econ(ec_u, policy_status="unresolved")
    out["broad_economic_fallback"] = p.econ(p.make_active(v()))
    out["exact_policy_override"] = p.econ(p.make_active(v()))
    out["conflicting_policy"] = p.econ(p.make_active(v()), policy_status="conflicting")
    out["retire_now_call"] = p.econ(p.make_active(v()))
    out["remain_call"] = p.econ(p.make_active(v()), alternatives=[
        {"alternative": "remain_in_fleet", "incremental_value": 900.0, "basis": "s"},
        {"alternative": "retire_now", "incremental_value": 200.0, "basis": "s"}])
    # execution (47-48)
    ex_u = p.make_active(v(), rental="rented")
    e1 = p.econ(ex_u)
    out["blocked_by_rental"] = p.execution.assess(ex_u, e1.id, rented=True)
    out["blocked_by_data"] = p.execution.assess(p.make_active(v()), e1.id, data_ok=False)
    # official vs scenario (49-50)
    out["official_fleet"] = p.portfolio.plan_entries(SCOPE, required_quantity=p.portfolio.current_active(SCOPE) + 1,
                                                     candidates=[{"vehicle_unit_id": "vu_of", "eligible": True,
                                                                  "available": True, "opportunity_cost": {"value": 10}}])
    out["scenario_fleet"] = p.scenario.explore("scn_sl", SCOPE, kind="fleet_size",
                                               overrides={"required_quantity": 99}, output={"selected": []})
    # resale + corrections + edges (51-60)
    out["resale_reference"] = p.resale.record_reference(p.store.get_unit(comp_u.id), resale_event_ref="resale1",
                                                        resale_value={"gross": 1000})
    cr_u = p.make_active(v())
    p.retirement.propose(p.full, SCOPE, cr_u)
    out["corrected_retirement"] = p.retirement.cancel(p.full, SCOPE, p.store.get_unit(cr_u.id))
    out["stale_snapshot"] = p.make_active(v())
    out["unresolved_identity"] = p.snapshot.ingest_fleet([{"vin": "PENDING"}], snapshot_type="full")
    out["audit_failure"] = p.make_active(v())
    out["unauthorized_approval"] = p.candidate(v())
    out["scope_mismatch"] = p.candidate(v())
    out["revoked_grant"] = p.candidate(v())
    out["stale_transition"] = p.candidate(v())
    cid_u = p.make_active(v(), in_service_date="2025-01-01")
    out["corrected_in_service_changing_eligibility"] = p.dating.correct_in_service_date(cid_u, "2024-01-01")
    return out


SCENARIO_NAMES = [
    "valid_full_snapshot", "invalid_full_claim", "partial_snapshot", "active_present", "active_absent_full",
    "invalid_vin", "duplicate_vin", "conflicting_rental", "verified_in_service", "conflicting_in_service",
    "missing_in_service", "zero_mileage", "blank_mileage", "missing_mileage", "invalid_mileage",
    "zero_rented_recent", "zero_rented_over_threshold", "rented_nonzero", "no_longer_rented", "eligible_candidate",
    "ineligible_candidate", "already_active_candidate", "approved_pending_entry", "portfolio_multi",
    "necessary_sacrifice", "retirement_eligible", "retirement_ineligible", "approved_retire_available",
    "approved_retire_rented", "provisional_retirement", "returned_after_provisional", "return_unconfirmed",
    "retirement_completed", "retirement_cancelled", "awaiting_used_cars", "used_cars_confirmed",
    "duplicate_used_cars", "receipt_before_retirement", "return_to_new_retail", "existing_current_supply",
    "missing_economic_policy", "broad_economic_fallback", "exact_policy_override", "conflicting_policy",
    "retire_now_call", "remain_call", "blocked_by_rental", "blocked_by_data", "official_fleet", "scenario_fleet",
    "resale_reference", "corrected_retirement", "stale_snapshot", "unresolved_identity", "audit_failure",
    "unauthorized_approval", "scope_mismatch", "revoked_grant", "stale_transition",
    "corrected_in_service_changing_eligibility",
]
