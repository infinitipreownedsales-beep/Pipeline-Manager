"""Deterministic Phase 9 fixtures: a wired governance + operational-control stack + synthetic scenarios.

Synthetic dealership data only. Distinct reviewer / decider / approver / executor / acknowledger /
scenario-owner / scenario-reviewer / promoter / authority-admin / delegator / auditor / readiness
principals prove separation of authority. Phase 9 REFERENCES authoritative Phase 1-8 output and reuses
the Phase 1 Governor + Phase 8 Calibration governance; it never copies or redefines domain results.
"""
from __future__ import annotations

from ..learning.fixtures import Phase8, _to_approved, _to_validated
from ..workflow.fixtures import SCOPE
from .acknowledge import AcknowledgmentService
from .approval import ApprovalService
from .audit_admin import AuditAdminService
from .authority import AuthorityAdminService
from .calibration_workspace import CalibrationWorkspaceService
from .decision import DecisionService
from .execution import ExecutionService
from .expiration import ExpirationService
from .models import CAPS
from .queues import ExceptionQueueService
from .readiness import ReadinessService
from .scenario_admin import ScenarioAdminService
from .sod import SeparationOfDutiesService
from .store import GovernStore
from .summaries import OperationalControlService
from .workspace import WorkspaceService

OTHER_SCOPE = "store:WEST"


class Phase9:
    def __init__(self, db_path, *, seed=True):
        self.p8 = Phase8(db_path, seed=seed)                     # migrates v1-v8
        self.stack = self.p8.stack
        self.clock = self.stack.clock
        self.stack.db.migrate()                       # apply v9
        self.gov = self.p8.gov
        self.store = GovernStore(self.stack.db.conn, self.clock)
        self.workspace = WorkspaceService(self.store, self.clock)
        self.decisions = DecisionService(self.store, self.gov, self.clock)
        self.approvals = ApprovalService(self.store, self.gov, self.clock)
        self.execution = ExecutionService(self.store, self.gov, self.clock)
        self.ack = AcknowledgmentService(self.store, self.gov, self.clock)
        self.expiration = ExpirationService(self.store, self.clock)
        self.scenarios = ScenarioAdminService(self.store, self.gov, self.clock)
        self.calibration_ws = CalibrationWorkspaceService(self.p8.store, self.p8.calibration, self.clock)
        self.authority = AuthorityAdminService(self.store, self.stack, self.gov, self.clock)
        self.sod = SeparationOfDutiesService(self.store, self.gov, self.clock)
        self.audit_admin = AuditAdminService(self.store, self.stack.authz, self.clock)
        self.queues = ExceptionQueueService(self.store, self.gov, self.clock)
        self.summaries = OperationalControlService(self.store, self.clock)
        self.readiness = ReadinessService(self.store, self.gov, self.clock)
        if seed:
            self._principals()

    def _principal(self, key, name, caps):
        pid = self.stack.metadata.get(key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, "*")
        return pid

    def _principals(self):
        self.full = self._principal("g_full", "G Full", list(CAPS))
        self.reviewer = self._principal("g_reviewer", "G Reviewer", ["workspace.view", "workspace.review"])
        self.decider = self._principal("g_decider", "G Decider", ["decision.issue", "decision.override",
                                       "decision.correct", "decision.supersede", "decision.defer", "decision.reject"])
        self.approver = self._principal("g_approver", "G Approver", ["decision.approve"])
        self.executor = self._principal("g_executor", "G Executor", ["execution.authorize", "execution.review"])
        self.acknowledger = self._principal("g_ack", "G Acknowledger", ["decision.acknowledge"])
        self.scenario_owner = self._principal("g_scowner", "G Scenario Owner",
                                              ["scenario.create", "scenario.share", "scenario.promote",
                                               "scenario.policy_review_request"])
        self.scenario_reviewer = self._principal("g_screv", "G Scenario Reviewer", ["scenario.review"])
        self.authority_admin = self._principal("g_authadm", "G Authority Admin",
                                               ["authority.view", "authority.grant", "authority.delegate",
                                                "authority.revoke", "authority.override_separation"])
        self.auditor = self._principal("g_auditor", "G Auditor", ["audit.view", "audit.exception.review"])
        self.readiness_assessor = self._principal("g_ready", "G Readiness", ["readiness.assess", "readiness.approve"])

    def reopen(self):
        return Phase9(self.stack.db.path)

    def close(self):
        self.stack.close()

    # ---- builders ---------------------------------------------------------
    def item(self, *, domain="new_inventory", rec="rec_1", scope=SCOPE, workspace_state="READY_FOR_REVIEW", **kw):
        return self.workspace.create_item(owning_domain=domain, store_scope=scope, recommendation_ref=rec,
                                          subject_entity_type="combination", subject_entity_id="c1",
                                          economic_call_ref="ec_1", execution_status_ref="es_1",
                                          workspace_state=workspace_state, applicable_facts=["bf_1"],
                                          applicable_versions={"calculation": "cv_1"}, evidence_refs=["ev_1"],
                                          raw_history_refs=["rh_1"], **kw)

    def decide(self, *, disposition="ACCEPT", domain="new_inventory", rec="rec_1", scope=SCOPE, principal=None,
               scenario_id=None, presented_alternatives=None, **kw):
        it = self.item(domain=domain, rec=rec, scope=scope, scenario_id=scenario_id)
        r = self.decisions.issue(principal or self.decider, scope, it, disposition=disposition,
                                 selected_action="act", presented_alternatives=presented_alternatives or ["A", "B"],
                                 **kw)
        return it, r["decision"]

    def approved(self, *, domain="new_inventory", scope=SCOPE, quantity=None, decision_quantity=None):
        it, d = self.decide(domain=domain, disposition="ACCEPT", scope=scope)
        a = self.approvals.approve(self.approver, scope, d, quantity=quantity, decision_quantity=decision_quantity)
        return it, d, a["approval"]

    def executed(self, *, domain="new_inventory", scope=SCOPE, domain_ref="dom_exec_1"):
        it, d, a = self.approved(domain=domain, scope=scope)
        e = self.execution.authorize(self.executor, scope, d, a, execution_capability="domain.execute",
                                     expected_action="execute", domain_execute_fn=lambda conn: domain_ref)
        return it, d, a, e["execution"]

    def completed(self, *, domain="new_inventory", scope=SCOPE):
        it, d, a, e = self.executed(domain=domain, scope=scope)
        self.execution.complete(self.executor, scope, e, domain_completion_ref="dom_done_1")
        outcome = self.execution.reconcile(d)
        return it, d, a, e, outcome

    def scenario(self, *, scenario_id="scn_1", domain="new_inventory", scope=SCOPE, overrides=None):
        return self.scenarios.create(self.scenario_owner, scope, scenario_id=scenario_id, owning_domain=domain,
                                     overrides=overrides or {"coverage_target": 5}, official_baseline_ref="base_1")

    def calibration_proposal(self):
        return _to_approved(self.p8, target_type="calculation_version")


def build_all_scenarios(p):
    """Construct representative records across the 80 required scenarios; returns {name: handle}."""
    out = {}
    out["ni_recommendation_item"] = p.item(domain="new_inventory", rec="rec_ni")
    out["cpo_approval_item"] = p.approved(domain="cpo")[0]
    out["ppo_approval_item"] = p.approved(domain="ppo")[0]
    out["dealer_trade_execution_item"] = p.executed(domain="dealer_trade")[0]
    out["ctp_review_item"] = p.item(domain="ctp", rec="rec_ctp", workspace_state="UNDER_REVIEW")
    out["service_loaner_entry_item"] = p.item(domain="service_loaner", rec="rec_sl_entry")
    out["service_loaner_retirement_item"] = p.item(domain="service_loaner", rec="rec_sl_ret")
    out["executive_demo_designation_item"] = p.item(domain="executive_demo", rec="rec_ed_desig")
    out["executive_demo_retirement_item"] = p.item(domain="executive_demo", rec="rec_ed_ret")
    out["learning_signal_review_item"] = p.item(domain="learning_calibration", rec="rec_ls")
    out["calibration_review_item"] = p.item(domain="learning_calibration", rec="rec_cal")
    out["unresolved_policy_item"] = p.item(rec="rec_up", unresolved="policy")
    out["conflicting_fact_item"] = p.item(rec="rec_cf", unresolved="conflicting_facts")
    out["fresh_recommendation"] = p.item(rec="rec_fresh")
    stale_it = p.item(rec="rec_stale")
    p.expiration.mark_recommendation_stale(stale_it, reason="new fact", triggering_fact="bf_new")
    out["stale_recommendation"] = p.store.get_workspace_item(stale_it["id"])
    it16, d16 = p.decide(rec="rec_exp")
    eid = p.expiration.set_expiration("decision", d16["id"], expires_at="2000-01-01T00:00:00Z")
    p.expiration.expire(eid)
    out["expired_decision"] = d16
    out["decision_accepted"] = p.decide(disposition="ACCEPT", rec="r17")[1]
    out["decision_rejected"] = p.decide(disposition="REJECT", rec="r18")[1]
    out["decision_deferred"] = p.decide(disposition="DEFER", rec="r19")[1]
    out["decision_requests_information"] = p.decide(disposition="REQUEST_INFORMATION", rec="r20")[1]
    out["deliberate_no_action"] = p.decide(disposition="NO_ACTION", rec="r21")[1]
    stale22 = p.item(rec="r22")
    p.expiration.mark_recommendation_stale(stale22, reason="stale")
    out["authorized_override"] = p.decisions.issue(p.decider, SCOPE, p.store.get_workspace_item(stale22["id"]),
                                                   disposition="OVERRIDE", override_reason="urgent",
                                                   selected_action="act")["decision"]
    out["unauthorized_override"] = p.item(rec="r23")                 # test performs the raise
    it24, d24 = p.decide(rec="r24")
    out["correction"] = p.decisions.correct(p.decider, SCOPE, d24, reason="typo")
    it25, d25 = p.decide(rec="r25")
    out["supersession"] = p.decisions.supersede(p.decider, SCOPE, d25, reason="new info")
    it26 = p.item(rec="r26")
    r26a = p.decisions.issue(p.decider, SCOPE, it26, disposition="ACCEPT", selected_action="a", idempotency_key="idem26")
    r26b = p.decisions.issue(p.decider, SCOPE, p.store.get_workspace_item(it26["id"]), disposition="ACCEPT",
                             selected_action="a", idempotency_key="idem26")
    out["idempotent_decision_retry"] = r26b["replayed"]
    out["audit_failed_decision"] = p.item(rec="r27")                # test monkeypatches audit
    out["approval"] = p.approved()[2]
    out["stale_approval"] = p.decide(rec="r29")[1]                  # test approves with stale=True
    it30, d30, a30 = p.approved()
    p.expiration.expire(p.expiration.set_expiration("approval", a30["id"], expires_at="2000-01-01T00:00:00Z"))
    out["expired_approval"] = a30
    it31, d31 = p.decide(rec="r31")
    p.approvals.approve(p.approver, SCOPE, d31, idempotency_key="idemA31")
    out["idempotent_approval"] = p.approvals.approve(p.approver, SCOPE, d31, idempotency_key="idemA31")["replayed"]
    out["approval_beyond_quantity"] = p.decide(rec="r32")[1]        # test approves quantity>decision_quantity
    out["execution_authorization"] = p.executed()[3]
    it34, d34, a34, e34, outcome34 = p.completed()
    out["execution_completion"] = p.store.get_execution_auth(e34["id"])
    it35, d35, a35, e35 = p.executed()
    p.execution.complete(p.executor, SCOPE, e35, failed=True)
    out["domain_execution_failure"] = p.execution.reconcile(d35)
    it36, d36, a36, e36 = p.executed()
    out["reconciliation_conflict"] = p.execution.reconcile(d36, conflict=True)
    it37, d37 = p.decide(rec="r37")
    out["acknowledgment"] = p.ack.acknowledge(p.acknowledger, SCOPE, decision_id=d37["id"])["acknowledgment"]
    it38, d38 = p.decide(rec="r38")
    p.ack.acknowledge(p.acknowledger, SCOPE, decision_id=d38["id"])
    out["duplicate_acknowledgment"] = p.ack.acknowledge(p.acknowledger, SCOPE, decision_id=d38["id"])["replayed"]
    it39, d39 = p.decide(rec="r39")
    out["unacknowledged_required_item"] = p.ack.outstanding(d39["id"])
    out["private_scenario"] = p.scenario(scenario_id="scn_priv")
    sc41 = p.scenario(scenario_id="scn_shared")
    out["shared_scenario"] = p.scenarios.share(p.scenario_owner, SCOPE, sc41, shared_with=p.reviewer)
    sc42 = p.scenarios.share(p.scenario_owner, SCOPE, p.scenario(scenario_id="scn_rev"), shared_with=p.reviewer)
    out["scenario_under_review"] = p.scenarios.begin_review(p.scenario_reviewer, SCOPE, sc42)
    sc43 = p.scenarios.share(p.scenario_owner, SCOPE, p.scenario(scenario_id="scn_exp"), shared_with=p.reviewer)
    out["expired_scenario"] = p.scenarios.expire(p.scenario_reviewer, SCOPE, sc43)
    sc44 = p.scenario(scenario_id="scn_prom")
    p.scenarios.share(p.scenario_owner, SCOPE, sc44, shared_with=p.reviewer)
    p.scenarios.review(p.scenario_reviewer, SCOPE, p.store.get_scenario(sc44["id"]))
    out["scenario_promotion_request"] = p.scenarios.request_promotion(
        p.scenario_owner, SCOPE, p.store.get_scenario(sc44["id"]), target_type="operational_decision")
    sc45 = p.scenario(scenario_id="scn_pol")
    p.scenarios.share(p.scenario_owner, SCOPE, sc45, shared_with=p.reviewer)
    p.scenarios.review(p.scenario_reviewer, SCOPE, p.store.get_scenario(sc45["id"]))
    out["policy_review_request"] = p.scenarios.request_promotion(
        p.scenario_owner, SCOPE, p.store.get_scenario(sc45["id"]), target_type="official_policy_review")
    sc46 = p.scenario(scenario_id="scn_rej")
    p.scenarios.share(p.scenario_owner, SCOPE, sc46, shared_with=p.reviewer)
    p.scenarios.review(p.scenario_reviewer, SCOPE, p.store.get_scenario(sc46["id"]))
    prom46 = p.scenarios.request_promotion(p.scenario_owner, SCOPE, p.store.get_scenario(sc46["id"]),
                                           target_type="operational_decision")
    out["rejected_promotion"] = p.scenarios.reject_promotion(p.scenario_owner, SCOPE, prom46, reason="insufficient")
    cal = p.calibration_proposal()
    out["calibration_workspace_review"] = p.calibration_ws.review(cal["id"])
    cal48 = _to_approved(p.p8, target_type="calculation_version", effective="2030-01-01T00:00:00+00:00")
    out["scheduled_calibration"] = p.calibration_ws.activate(p.p8.activator, SCOPE, cal48, future=True)["calibration"]
    cal49 = _to_approved(p.p8, target_type="calculation_version", current_version="cv_prior")
    p.calibration_ws.activate(p.p8.activator, SCOPE, cal49)
    out["calibration_rollback"] = p.calibration_ws.rollback(p.p8.rollbacker, SCOPE, cal49,
                                                            restored_version_ref="cv_prior", reason="regressed")["calibration"]
    tmp_p = p.stack.authn.register("TmpHolder", "pw").id
    out["temporary_authority"] = p.authority.grant_temporary(p.authority_admin, SCOPE, to_principal=tmp_p,
                                                            capability="workspace.view", grant_scope="*",
                                                            expiration="2030-01-01T00:00:00Z")[0]
    exp_p = p.stack.authn.register("ExpHolder", "pw").id
    p.authority.grant_temporary(p.authority_admin, SCOPE, to_principal=exp_p, capability="workspace.view",
                                grant_scope="*", expiration="2000-01-01T00:00:00Z")
    p.authority.enforce_temporary_expiry()
    out["expired_temporary_authority"] = exp_p
    del_p = p.stack.authn.register("Delegate1", "pw").id
    out["delegated_authority"] = p.authority.delegate(p.full, SCOPE, delegate=del_p, capability="decision.approve",
                                                     delegate_scope="*", reason="coverage")
    out["over_broad_delegation_attempt"] = True                     # test performs the raise
    del54 = p.stack.authn.register("Delegate2", "pw").id
    dg54 = p.authority.delegate(p.full, SCOPE, delegate=del54, capability="decision.approve", delegate_scope="*")
    out["revoked_delegated_authority"] = p.authority.revoke_delegation(p.authority_admin, SCOPE, dg54)
    p.store.add_sod_rule(rule_type="proposer_not_approver", action_a="decision.issue", action_b="decision.approve")
    p.store.add_sod_rule(rule_type="approver_not_executor", action_a="decision.approve", action_b="execution.authorize")
    p.store.add_sod_rule(rule_type="self_approval_prohibited_above_materiality", materiality_threshold="1000")
    out["proposer_approver_conflict"] = True                        # test performs the raise
    out["approver_executor_conflict"] = True
    out["authorized_separation_override"] = p.sod.override(p.authority_admin, SCOPE,
                                                          rule_type="proposer_not_approver", actor_a="x", actor_b="x",
                                                          reason="single-staff store")
    out["unauthorized_separation_override"] = True                  # test performs the raise
    out["missing_audit_event"] = p.audit_admin.detect_missing(expected_action="nonexistent.action",
                                                             correlation_id="corr_missing")
    out["failed_atomic_audit_action"] = p.store.add_audit_exception(kind="failed_atomic", expected_action="x",
                                                                   detail="atomic action failed")
    out["unresolved_identity_queue"] = p.queues.enqueue(queue="unresolved_identity", source_type="vehicle_unit",
                                                        source_ref="vu_x", owning_domain="new_inventory")
    out["missing_policy_queue"] = p.queues.enqueue(queue="missing_policy", source_type="policy_family",
                                                  source_ref="pf_x", owning_domain="new_inventory")
    out["stale_recommendation_queue"] = p.queues.enqueue(queue="stale_recommendation", source_type="workspace_item",
                                                        source_ref=stale_it["id"], owning_domain="new_inventory")
    out["failed_execution_queue"] = p.queues.enqueue(queue="failed_execution", source_type="execution_authorization",
                                                    source_ref=e35["id"], owning_domain="dealer_trade")
    out["ambiguous_pairing_queue"] = p.queues.enqueue(queue="ambiguous_pairing", source_type="pairing",
                                                      source_ref="pair_x", owning_domain="learning_calibration")
    out["conflicting_learning_signal_queue"] = p.queues.enqueue(queue="conflicting_learning_signal",
                                                               source_type="learning_signal", source_ref="ls_x",
                                                               owning_domain="learning_calibration")
    out["blocked_service_loaner_queue"] = p.queues.enqueue(queue="service_loaner_operational_alert",
                                                          source_type="service_loaner_unit", source_ref="slu_x",
                                                          owning_domain="service_loaner")
    out["blocked_executive_demo_queue"] = p.queues.enqueue(queue="executive_demo_blocked_recommendation",
                                                          source_type="executive_demo_unit", source_ref="edu_x",
                                                          owning_domain="executive_demo")
    out["ready_domain"] = p.readiness.assess(p.readiness_assessor, SCOPE, owning_domain="governance_foundation",
                                            required_policy_present=True, authority_coverage=True,
                                            test_evidence={"synthetic_pass": True, "operational_evidence": True},
                                            operational_owner="gm")
    out["ready_with_warnings_domain"] = p.readiness.assess(p.readiness_assessor, SCOPE, owning_domain="service_loaner",
                                                          required_policy_present=True, authority_coverage=True,
                                                          stale_imports=2)
    out["not_ready_domain"] = p.readiness.assess(p.readiness_assessor, SCOPE, owning_domain="new_inventory",
                                                required_policy_present=False, authority_coverage=True)
    out["missing_authority_blocker"] = p.readiness.assess(p.readiness_assessor, SCOPE, owning_domain="executive_demo",
                                                         required_policy_present=True, authority_coverage=False)
    out["missing_policy_blocker"] = p.readiness.assess(p.readiness_assessor, SCOPE, owning_domain="production_workflows",
                                                      required_policy_present=False, authority_coverage=True)
    out["stale_source_blocker"] = p.readiness.assess(p.readiness_assessor, SCOPE, owning_domain="learning_calibration",
                                                    required_policy_present=True, authority_coverage=True,
                                                    stale_imports=5,
                                                    test_evidence={"synthetic_pass": True})
    out["official_decision"] = p.decide(rec="r75", disposition="ACCEPT")[1]
    it76 = p.item(rec="r76", scenario_id="scn_only")
    out["scenario_only_decision"] = p.decisions.issue(p.decider, SCOPE, it76, disposition="ACCEPT",
                                                     selected_action="a")["decision"]
    out["scenario_decision_attempted_as_official"] = p.item(rec="r77", scenario_id="scn_off")  # test raises
    it78, d78 = p.decide(rec="r78")
    p.decisions.correct(p.decider, SCOPE, d78, reason="fix")
    out["correction_preserving_original_decision"] = d78
    it79 = p.item(rec="r79_old")
    out["old_recommendation_preserved_after_supersession"] = p.workspace.revise(
        it79, new_recommendation_ref="r79_new", reason="updated forecast")
    out["restart_durability"] = p.item(rec="r80")
    return out


SCENARIO_NAMES = [
    "ni_recommendation_item", "cpo_approval_item", "ppo_approval_item", "dealer_trade_execution_item",
    "ctp_review_item", "service_loaner_entry_item", "service_loaner_retirement_item",
    "executive_demo_designation_item", "executive_demo_retirement_item", "learning_signal_review_item",
    "calibration_review_item", "unresolved_policy_item", "conflicting_fact_item", "fresh_recommendation",
    "stale_recommendation", "expired_decision", "decision_accepted", "decision_rejected", "decision_deferred",
    "decision_requests_information", "deliberate_no_action", "authorized_override", "unauthorized_override",
    "correction", "supersession", "idempotent_decision_retry", "audit_failed_decision", "approval",
    "stale_approval", "expired_approval", "idempotent_approval", "approval_beyond_quantity",
    "execution_authorization", "execution_completion", "domain_execution_failure", "reconciliation_conflict",
    "acknowledgment", "duplicate_acknowledgment", "unacknowledged_required_item", "private_scenario",
    "shared_scenario", "scenario_under_review", "expired_scenario", "scenario_promotion_request",
    "policy_review_request", "rejected_promotion", "calibration_workspace_review", "scheduled_calibration",
    "calibration_rollback", "temporary_authority", "expired_temporary_authority", "delegated_authority",
    "over_broad_delegation_attempt", "revoked_delegated_authority", "proposer_approver_conflict",
    "approver_executor_conflict", "authorized_separation_override", "unauthorized_separation_override",
    "missing_audit_event", "failed_atomic_audit_action", "unresolved_identity_queue", "missing_policy_queue",
    "stale_recommendation_queue", "failed_execution_queue", "ambiguous_pairing_queue",
    "conflicting_learning_signal_queue", "blocked_service_loaner_queue", "blocked_executive_demo_queue",
    "ready_domain", "ready_with_warnings_domain", "not_ready_domain", "missing_authority_blocker",
    "missing_policy_blocker", "stale_source_blocker", "official_decision", "scenario_only_decision",
    "scenario_decision_attempted_as_official", "correction_preserving_original_decision",
    "old_recommendation_preserved_after_supersession", "restart_durability",
]
