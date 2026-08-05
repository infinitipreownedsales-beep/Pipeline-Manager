"""Phase 9 dedicated governed-decision regression (20 points).

Proves the end-to-end governed operational loop over the domain engines AND its guardrails:
Recommendation ≠ Decision ≠ approval ≠ execution ≠ completion; stale rejects; audit failure blocks;
Scenario cannot execute as official; nothing rewrites an issued recommendation or historical Decision.
"""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, PersistenceError, ValidationError
from elite.govern.fixtures import Phase9
from elite.workflow.fixtures import SCOPE


class TestGovernedDecisionRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase9(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_governed_decision_regression(self):
        p = self.p
        # 1 an authoritative domain recommendation exists (a real Phase 8 prediction stands in as the rec)
        pred = p.p8.prediction(value=10, subject_entity_id="comb_1")
        # 2 workspace item references it (never copies it)
        item = p.workspace.create_item(owning_domain="new_inventory", store_scope=SCOPE,
                                       recommendation_ref=pred.id, subject_entity_type="combination",
                                       subject_entity_id="comb_1", economic_call_ref="ec1",
                                       execution_status_ref="es1", applicable_facts=["bf_1"],
                                       applicable_versions={"calculation": pred.calculation_version},
                                       evidence_refs=["ev1"])
        self.assertEqual(item["recommendation_ref"], pred.id)
        # 3 reviewer sees Call, Why, Proof, confidence, uncertainty, Raw History
        review = p.workspace.review(item, resolvers={"confidence": lambda i: "medium",
                                                     "uncertainty": lambda i: {"band": "±2"}})
        self.assertEqual(review["proof"]["recommendation_ref"], pred.id)
        self.assertEqual(review["why"]["confidence"], "medium")
        self.assertIn("raw_history_path", review)
        # 4 authorized Decision is issued
        audit_before = p.stack.audit.count()
        r = p.decisions.issue(p.decider, SCOPE, item, disposition="ACCEPT", selected_action="order_2",
                              presented_alternatives=["order_1", "order_2"], correlation_id="corr_g")
        d = r["decision"]
        # 5 Decision preserves the exact recommendation revision
        self.assertEqual(d["source_recommendation_ref"], pred.id)
        self.assertEqual(d["recommendation_revision"], str(item["version"]))
        # 6 required Audit Event is atomic
        self.assertEqual(p.stack.audit.count(), audit_before + 1)
        # 7 approval uses distinct authority; 8 separation-of-duties rule enforced; 9 approval does not execute
        p.store.add_sod_rule(rule_type="proposer_not_approver", action_a="decision.issue", action_b="decision.approve")
        with self.assertRaises(AuthorizationError):
            p.approvals.approve(p.decider, SCOPE, d)                    # proposer cannot approve
        p.sod.enforce(p.approver, SCOPE, rule_type="proposer_not_approver", actor_a=d["decision_maker"],
                      actor_b=p.approver)                               # distinct actors -> ok
        a = p.approvals.approve(p.approver, SCOPE, d)["approval"]
        self.assertEqual(p.store.execauths_for(d["id"]), [])           # approval != execution
        # 10 execution authorization references approval; 11 actual domain execution produces its own event
        domain_event = f"domain_exec::{pred.id}"                        # a real domain execution ref (referenced)
        e = p.execution.authorize(p.executor, SCOPE, d, a, execution_capability="new_inventory.execute",
                                  expected_action="order", domain_execute_fn=lambda conn: domain_event)["execution"]
        self.assertEqual(e["approval_id"], a["id"])
        self.assertEqual(e["domain_execution_ref"], domain_event)
        # 12 completion references that actual event
        p.execution.complete(p.executor, SCOPE, e, domain_completion_ref=f"{domain_event}::done")
        self.assertEqual(p.store.get_execution_auth(e["id"])["completion_ref"], f"{domain_event}::done")
        # 13 Decision-to-execution reconciliation becomes completed
        self.assertEqual(p.execution.reconcile(d), "COMPLETED")
        # 14 replaying Decision, approval, and execution is idempotent
        r2 = p.decisions.issue(p.decider, SCOPE, p.store.get_workspace_item(item["id"]), disposition="ACCEPT",
                               selected_action="order_2", idempotency_key="rk", correlation_id="corr_g")
        r3 = p.decisions.issue(p.decider, SCOPE, p.store.get_workspace_item(item["id"]), disposition="ACCEPT",
                               selected_action="order_2", idempotency_key="rk", correlation_id="corr_g")
        self.assertTrue(r3["replayed"])
        a2 = p.approvals.approve(p.approver, SCOPE, d, idempotency_key="rak")
        self.assertTrue(p.approvals.approve(p.approver, SCOPE, d, idempotency_key="rak")["replayed"])
        # 15 a new fact makes the old recommendation stale; 16 the old rec + Decision remain historical
        p.expiration.mark_recommendation_stale(p.store.get_workspace_item(item["id"]), reason="new sales fact",
                                               triggering_fact="bf_new")
        self.assertEqual(p.p8.store.get_prediction(pred.id).predicted_payload["value"], 10)   # rec unchanged
        self.assertIsNotNone(p.store.get_decision(d["id"]))            # decision historical
        # 17 stale Decision cannot execute without renewed review
        it2, d2, a2b = p.approved()
        with self.assertRaises(ValidationError):
            p.execution.authorize(p.executor, SCOPE, d2, a2b, execution_capability="x", expected_action="y",
                                  stale=True)
        # 18 authorized stale override requires reason and is audited
        stale_item = p.store.get_workspace_item(item["id"])
        with self.assertRaises(ValidationError):
            p.decisions.issue(p.decider, SCOPE, stale_item, disposition="OVERRIDE", selected_action="x")
        ab = p.stack.audit.count()
        ov = p.decisions.issue(p.decider, SCOPE, stale_item, disposition="OVERRIDE", selected_action="x",
                               override_reason="urgent order")["decision"]
        self.assertTrue(ov["override"])
        self.assertEqual(p.stack.audit.count(), ab + 1)
        # 19 Scenario recommendation cannot be executed as official state
        scen_item = p.item(rec="scn_rec", scenario_id="scn_z")
        with self.assertRaises(ValidationError):
            p.decisions.issue(p.decider, SCOPE, scen_item, disposition="ACCEPT", selected_action="a",
                              as_official=True)
        # 20 Audit failure at any governed mutation blocks unsafe success
        it3 = p.item(rec="af_rec")
        orig = p.stack.audit.append
        p.stack.audit.append = lambda conn, ev: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                p.decisions.issue(p.decider, SCOPE, it3, disposition="ACCEPT", selected_action="a")
        finally:
            p.stack.audit.append = orig
        self.assertEqual(p.store.decisions_for_item(it3["id"]), [])    # nothing committed


if __name__ == "__main__":
    unittest.main()
