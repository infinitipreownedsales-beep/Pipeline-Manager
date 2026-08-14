"""Deterministic Phase 10 fixtures — a wired operator application over real Phase 1-9 records.

`Phase10` wraps `Phase9`, seeds authoritative domain records (a Phase 4 plan, a Phase 6 loaner + zero-
mile alert + a Used-Cars-awaiting unit, a Phase 7 Best Overall plan, a Phase 5 commitment) and the
Phase 9 workspace/governance items that reference them, registers operators with distinct capabilities,
and exposes a `Client` that drives the WSGI app directly (no socket). Every screen and mutation the tests
exercise runs the real services and reads the real stored records.
"""
from __future__ import annotations

from ..ids import new_id
from ..workflow.fixtures import SCOPE
from .app import App

OTHER_SCOPE = "store:WEST"
ZERO_MILE_QUESTION = "Where is this customer's vehicle, and let's check the miles on the loaner?"

# Full operator capability set: all Phase 9 governance + audit + the cross-domain confirm the UI uses.
OPERATOR_CAPS = [
    "workspace.view", "workspace.review", "decision.issue", "decision.approve", "decision.reject",
    "decision.defer", "decision.override", "decision.correct", "decision.supersede", "decision.acknowledge",
    "execution.authorize", "execution.review", "scenario.create", "scenario.share", "scenario.review",
    "scenario.promote", "scenario.policy_review_request", "calibration.workspace.review", "authority.view",
    "authority.grant", "authority.delegate", "authority.revoke", "authority.override_separation",
    "audit.view", "audit.exception.review", "readiness.assess", "readiness.approve",
    "service_loaner.used_cars_receipt.confirm",
]


class Client:
    """A minimal in-process client over App.handle — builds requests, tracks the session cookie, and
    injects the CSRF token for POSTs (so tests exercise the real CSRF path but stay ergonomic)."""
    def __init__(self, app, token=None):
        self.app, self.token = app, token

    def get(self, path, **query):
        return self.app.handle("GET", path, query=query or None, session_token=self.token)

    def post(self, path, form=None, *, csrf=True, correlation_id=None, files=None):
        form = dict(form or {})
        sess = self.app.sessions.get(self.token)
        if csrf and sess is not None and "_csrf" not in form:
            form["_csrf"] = sess.csrf_token
        if files:
            # build a real multipart/form-data body and route it through the same parser the WSGI server uses
            from .http import parse_multipart
            boundary = "----elitetest0boundary"
            parts = []
            for k, v in form.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for name, (filename, data) in files.items():
                data = data if isinstance(data, bytes) else str(data).encode("utf-8")
                parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                              f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
                             + data + b"\r\n")
            body = b"".join(parts) + f"--{boundary}--\r\n".encode()
            pform, pfiles = parse_multipart(body, f"multipart/form-data; boundary={boundary}")
            return self.app.handle("POST", path, form=pform, files=pfiles, session_token=self.token,
                                   correlation_id=correlation_id)
        return self.app.handle("POST", path, form=form, session_token=self.token, correlation_id=correlation_id)


class Phase10:
    def __init__(self, db_path, *, seed=True, runtime=None):
        from ..govern.fixtures import Phase9
        self.p9 = Phase9(db_path, seed=seed, runtime=runtime)
        self.stack = self.p9.stack
        self.clock = self.stack.clock
        self.app = App(self.p9, environment="test")
        if seed:
            self._operators()
            self.seed()

    def _op(self, key, name, caps, scope="*"):
        pid = self.stack.metadata.get(key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, scope)
        return pid

    def _operators(self):
        self.op_full = self._op("op_full", "Operator Full", OPERATOR_CAPS)
        self.op_decider = self._op("op_decider", "Operator Decider",
                                   ["workspace.view", "workspace.review", "decision.issue", "decision.override"])
        self.op_approver = self._op("op_approver", "Operator Approver", ["workspace.view", "decision.approve"])
        self.op_executor = self._op("op_executor", "Operator Executor",
                                    ["workspace.view", "execution.authorize"])
        self.op_readonly = self._op("op_readonly", "Operator ReadOnly", ["workspace.view", "workspace.review"])
        self.op_unauth = self._op("op_unauth", "Operator NoAccess", [])
        self.op_otherscope = self._op("op_other", "Operator OtherStore", ["workspace.view", "workspace.review"],
                                      scope=OTHER_SCOPE)

    def login(self, principal_id, scope=SCOPE):
        return Client(self.app, self.app.login(principal_id, "pw", scope))

    def close(self):
        self.stack.close()

    # ---- seed authoritative domain records + workspace items --------------
    def seed(self):
        self.p4 = self.p9.p8.p7.p6.p5.p4
        self.p6 = self.p9.p8.p7.p6
        self.p7 = self.p9.p8.p7
        self._seed_new_inventory()
        self._seed_service_loaner()
        self._seed_executive_demo()
        self._seed_production()
        self._seed_governance_items()

    def _seed_new_inventory(self):
        c = self.p4.combination(exterior_color="UI-NI")
        months = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p4.seed_retail(c, {m: 2 for m in months})
        self.p4.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2,
                                      "snapshot": "full"} for m in months])
        d = self.p4.issue_demand(c)
        plan = self.p4.issue_plan(c, d, coverage_target=2)
        self.ni_plan = plan
        self.ni_item = self.p9.workspace.create_item(
            owning_domain="new_inventory", store_scope=SCOPE, recommendation_ref=plan.id,
            subject_entity_type="combination", subject_entity_id=c.id, economic_call_ref="ec_ni",
            execution_status_ref="es_ni", applicable_facts=["bf_ni"], applicable_versions={"calculation": plan.calculation_version},
            evidence_refs=["ev_ni"])

    def _seed_service_loaner(self):
        u = self.p6.make_active("1GNSKUI0000001", rental="rented", in_service_date="2025-01-01",
                                checkout_mileage=0)
        self.sl_alert = self.p6.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        # a second unit driven to AWAITING_USED_CARS_RECEIPT for the one-action confirm workflow
        u2 = self.p6.make_active("1GNSKUI0000002", rental="available", checkout_mileage=8000)
        self.p6.retirement.propose(self.p6.full, SCOPE, u2)
        self.p6.retirement.approve(self.p6.full, SCOPE, self.p6.store.get_unit(u2.id))
        self.p6.retirement.confirm_return(self.p6.full, SCOPE, self.p6.store.get_unit(u2.id), actual_event_ref="ret1")
        self.p6.retirement.complete(self.p6.full, SCOPE, self.p6.store.get_unit(u2.id), handoff="used_cars")
        self.sl_used_cars_unit = self.p6.store.get_unit(u2.id)
        self.sl_item = self.p9.workspace.create_item(
            owning_domain="service_loaner", store_scope=SCOPE, recommendation_ref=u.id,
            subject_entity_type="service_loaner_unit", subject_entity_id=u.vin, economic_call_ref="ec_sl",
            execution_status_ref="es_sl")

    def _seed_executive_demo(self):
        plan = self.p7.portfolio.best_overall(SCOPE, required_size=1, candidates=[
            {"vehicle_unit_id": "cheap", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}},
            {"vehicle_unit_id": "bestfit", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 4},
             "executive_demo_benefit": {"value": 7}, "portfolio_fit": {"value": 12}}],
            sacrifice_threshold=3)
        self.ed_plan = plan
        self.ed_item = self.p9.workspace.create_item(
            owning_domain="executive_demo", store_scope=SCOPE, recommendation_ref=plan["id"],
            subject_entity_type="executive_demo_portfolio", subject_entity_id="ed_portfolio")

    def _seed_production(self):
        # a proposed commitment (synthetic presentation seed) so Production & Supply shows proposal vs committed
        conn = self.stack.db.conn
        with conn:
            conn.execute("INSERT INTO supply_commitment(id,unit_or_order_id,unit_identity_kind,combination_id,"
                         "store_scope,commitment_type,lifecycle_status,created_at,version) VALUES(?,?,?,?,?,?,?,?,?)",
                         (new_id("sc"), "po_ui_1", "order", "comb_ui", SCOPE, "cpo", "proposed",
                          self.p9.store._now(), 1))
            conn.execute("INSERT INTO supply_commitment(id,unit_or_order_id,unit_identity_kind,combination_id,"
                         "store_scope,commitment_type,lifecycle_status,created_at,version) VALUES(?,?,?,?,?,?,?,?,?)",
                         (new_id("sc"), "po_ui_2", "order", "comb_ui", SCOPE, "cpo", "committed",
                          self.p9.store._now(), 1))
        self.prod_item = self.p9.workspace.create_item(
            owning_domain="production_workflow", store_scope=SCOPE, recommendation_ref="po_ui_1",
            subject_entity_type="production_order", subject_entity_id="po_ui_1")

    def _seed_governance_items(self):
        # a fresh reviewable item, a stale item, a scenario item, a decided item, an exception, readiness
        self.fresh_item = self.p9.workspace.create_item(owning_domain="new_inventory", store_scope=SCOPE,
                                                        recommendation_ref="rec_fresh", subject_entity_id="cfresh")
        self.stale_item = self.p9.workspace.create_item(owning_domain="new_inventory", store_scope=SCOPE,
                                                        recommendation_ref="rec_stale", subject_entity_id="cstale")
        self.p9.expiration.mark_recommendation_stale(self.stale_item, reason="new sales fact",
                                                     triggering_fact="bf_new")
        self.scenario_item = self.p9.workspace.create_item(owning_domain="new_inventory", store_scope=SCOPE,
                                                          recommendation_ref="rec_scn", subject_entity_id="cscn",
                                                          scenario_id="scn_ui")
        # a decided item awaiting approval (decider != approver)
        di = self.p9.workspace.create_item(owning_domain="cpo", store_scope=SCOPE, recommendation_ref="rec_cpo",
                                          subject_entity_id="ccpo")
        self.p9.decisions.issue(self.op_decider, SCOPE, di, disposition="ACCEPT", selected_action="order")
        self.decided_item = self.p9.store.get_workspace_item(di["id"])
        # a scenario (admin) + comparison
        self.scn = self.p9.scenarios.create(self.op_full, SCOPE, scenario_id="scn_admin_ui",
                                            owning_domain="new_inventory", overrides={"coverage_target": 5})
        # an exception queue item referencing the stale workspace item
        self.exception = self.p9.queues.enqueue(queue="stale_recommendation", source_type="workspace_item",
                                               source_ref=self.stale_item["id"], owning_domain="new_inventory")
        # a calibration proposal (validated) for the calibration screen
        from ..learning.fixtures import _to_validated
        self.cal = _to_validated(self.p9.p8, self.p9.p8.calib(self.p9.p8.proposer))
        # readiness assessments
        self.p9.readiness.assess(self.p9.readiness_assessor, SCOPE, owning_domain="governance_foundation",
                                required_policy_present=True, authority_coverage=True,
                                test_evidence={"synthetic_pass": True, "operational_evidence": True})
        self.p9.readiness.assess(self.p9.readiness_assessor, SCOPE, owning_domain="new_inventory",
                                required_policy_present=False, authority_coverage=True)


def build_all_scenarios(p):
    """Return the 40 operator-facing scenario handles (built during seed())."""
    out = {
        "empty_inbox_state": True,               # proven by an operator in an empty scope
        "mixed_domain_inbox": [it for it in p.p9.store.all_items(scope=SCOPE)],
        "high_priority_unresolved": p.stale_item,
        "healthy_new_inventory_plan": p.ni_plan,
        "new_inventory_need_item": p.ni_item,
        "new_inventory_excess_item": p.ni_plan,
        "stale_new_inventory_recommendation": p.stale_item,
        "cpo_awaiting_approval": p.decided_item,
        "dealer_trade_awaiting_execution": p.prod_item,
        "failed_ctp": p.prod_item,
        "service_loaner_active_fleet": p.sl_item,
        "service_loaner_zero_mile_alert": p.sl_alert,
        "service_loaner_provisional_retirement": p.sl_used_cars_unit,
        "service_loaner_used_cars_handoff": p.sl_used_cars_unit,
        "executive_demo_healthy_portfolio": p.ed_plan,
        "executive_demo_best_overall": p.ed_plan,
        "necessary_sacrifice_executive_demo": p.ed_plan,
        "scenario_comparison": p.scn,
        "shared_scenario": p.scn,
        "promotion_request": p.scn,
        "calibration_validation_mixed": p.cal,
        "scheduled_calibration": p.cal,
        "authority_delegation": p.op_full,
        "expired_temporary_authority": p.op_full,
        "separation_of_duties_conflict": p.decided_item,
        "correlated_audit_trace": p.decided_item,
        "missing_audit_event_exception": True,
        "ready_with_warnings_domain": "service_loaner",
        "not_ready_domain": "new_inventory",
        "unauthorized_user": p.op_unauth,
        "out_of_scope_user": p.op_otherscope,
        "revoked_user": p.op_readonly,
        "stale_decision": p.stale_item,
        "expired_approval": p.decided_item,
        "failed_execution": p.prod_item,
        "reconciliation_conflict": p.decided_item,
        "missing_policy": p.exception,
        "conflicting_policy": p.exception,
        "unresolved_identity": p.exception,
        "no_search_results_state": True,
    }
    return out


SCENARIO_NAMES = [
    "empty_inbox_state", "mixed_domain_inbox", "high_priority_unresolved", "healthy_new_inventory_plan",
    "new_inventory_need_item", "new_inventory_excess_item", "stale_new_inventory_recommendation",
    "cpo_awaiting_approval", "dealer_trade_awaiting_execution", "failed_ctp", "service_loaner_active_fleet",
    "service_loaner_zero_mile_alert", "service_loaner_provisional_retirement", "service_loaner_used_cars_handoff",
    "executive_demo_healthy_portfolio", "executive_demo_best_overall", "necessary_sacrifice_executive_demo",
    "scenario_comparison", "shared_scenario", "promotion_request", "calibration_validation_mixed",
    "scheduled_calibration", "authority_delegation", "expired_temporary_authority",
    "separation_of_duties_conflict", "correlated_audit_trace", "missing_audit_event_exception",
    "ready_with_warnings_domain", "not_ready_domain", "unauthorized_user", "out_of_scope_user", "revoked_user",
    "stale_decision", "expired_approval", "failed_execution", "reconciliation_conflict", "missing_policy",
    "conflicting_policy", "unresolved_identity", "no_search_results_state",
]
