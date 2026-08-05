"""Phase 9 acceptance — domain readiness (93-99) + operational output slices (100)."""
import os
import tempfile
import unittest

from elite.govern import output
from elite.govern.fixtures import Phase9
from elite.workflow.fixtures import SCOPE


class TestPhase9ReadinessOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase9(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _assess(self, **kw):
        base = dict(owning_domain="new_inventory", required_policy_present=True, authority_coverage=True)
        base.update(kw)
        return self.p.readiness.assess(self.p.readiness_assessor, SCOPE, **base)

    # ---- readiness (93-99) ------------------------------------------------
    def test_93_readiness_evidence_based(self):
        r = self._assess(operational_owner="gm", test_evidence={"synthetic_pass": True, "operational_evidence": True})
        self.assertEqual(r["classification"], "READY")
        import json
        self.assertTrue(json.loads(r["evidence"])["required_policy_present"])

    def test_94_missing_policy_blocks(self):
        r = self._assess(required_policy_present=False)
        self.assertEqual(r["classification"], "NOT_READY")
        self.assertIn("missing required policy", " ".join(__import__("json").loads(r["blockers"])))

    def test_95_missing_authority_blocks(self):
        r = self._assess(authority_coverage=False)
        self.assertEqual(r["classification"], "NOT_READY")

    def test_96_critical_unresolved_identity_blocks(self):
        r = self._assess(unresolved_critical=2)
        self.assertEqual(r["classification"], "NOT_READY")

    def test_97_synthetic_tests_alone_insufficient(self):
        r = self._assess(test_evidence={"synthetic_pass": True})       # no operational evidence
        self.assertEqual(r["classification"], "READY_WITH_WARNINGS")
        self.assertTrue(any("synthetic" in w for w in __import__("json").loads(r["warnings"])))

    def test_98_readiness_does_not_deploy(self):
        cv_before = self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]
        self._assess()
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"],
                         cv_before)                                    # no activation / deployment
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"], 0)

    def test_99_prior_assessment_historical(self):
        r1 = self._assess()
        r2 = self._assess(required_policy_present=False)
        rows = self.p.store.readiness_for("new_inventory")
        self.assertEqual(len(rows), 2)                                 # both preserved
        self.assertEqual(rows[0]["id"], r1["id"])
        self.assertEqual(r2["revision"], 2)

    # ---- output slices (100) ----------------------------------------------
    def test_100_output_slices_use_real_records(self):
        it, d = self.p.decide(rec="rec_o")
        a = self.p.approvals.approve(self.p.approver, SCOPE, d)["approval"]
        e = self.p.execution.authorize(self.p.executor, SCOPE, d, a, execution_capability="x", expected_action="y",
                                       domain_execute_fn=lambda conn: "ref")["execution"]
        self.p.ack.acknowledge(self.p.acknowledger, SCOPE, decision_id=d["id"])
        sc = self.p.scenario(scenario_id="scn_o")
        self.p.queues.enqueue(queue="unresolved_identity", source_type="vehicle_unit", source_ref="vu",
                              owning_domain="new_inventory")
        self.p.store.add_sod_rule(rule_type="proposer_not_approver")
        self.p.sod.override(self.p.authority_admin, SCOPE, rule_type="proposer_not_approver", actor_a="x",
                            actor_b="x", reason="r")
        self._assess()
        s = self.p.store
        # 1 inbox, 3 decision, 4 approval-queue, 5 execution-queue, 6 ack-queue, 7 stale/expired
        self.assertTrue(any(x["workspace_item_id"] == it["id"] for x in output.decision_inbox(s)))
        self.assertEqual(output.decision_slice(s, d["id"])["decision_id"], d["id"])
        self.assertIsInstance(output.approval_queue(s), list)
        self.assertIsInstance(output.execution_queue(s), list)
        self.assertIsInstance(output.acknowledgment_queue(s), list)
        self.assertIsInstance(output.stale_expired_queue(s), list)
        # 2 recommendation detail
        self.assertEqual(output.recommendation_detail(s, it["id"])["domain"], "new_inventory")
        # 8 scenario admin, 9 comparison, 10 promotion queue
        self.assertTrue(any(x["scenario_admin_id"] == sc["id"] for x in output.scenario_admin_slice(s)))
        self.assertEqual(output.scenario_comparison(s, sc["id"])["official_baseline_ref"], "base_1")
        self.assertIsInstance(output.promotion_queue(s), list)
        # 12 authority admin, 13 sod exceptions
        self.p.authority.delegate(self.p.full, SCOPE, delegate=self.p.stack.authn.register("Dx", "pw").id,
                                  capability="decision.approve", delegate_scope="*")
        self.assertTrue(output.authority_admin_slice(s))
        self.assertTrue(output.sod_exceptions_slice(s))
        # 14 audit review, 15 exception queue, 17 readiness
        self.assertIsInstance(output.audit_review_slice(self.p.audit_admin, self.p.auditor, SCOPE), list)
        self.assertTrue(output.exception_queue_slice(s))
        self.assertEqual(output.readiness_slice(s, "new_inventory")["domain"], "new_inventory")
        # 16 operational-control summary
        self.assertIn("counts", self.p.summaries.summarize(scope=SCOPE))
        # every slice exposes a raw-history path where it references a stored record
        self.assertIn("raw_history_path", output.decision_slice(s, d["id"]))


if __name__ == "__main__":
    unittest.main()
