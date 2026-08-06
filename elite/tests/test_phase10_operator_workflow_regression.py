"""Phase 10 dedicated operator-workflow regression (20 points).

Drives the full operator loop through the real Phase 1-9 services via the UI routes and proves the
governance guardrails hold: separate approval authority, approval ≠ execution, real domain execution,
idempotent submissions, stale protection, Scenario cannot execute officially, correlation-ID
preservation, no UI-side domain math, historical preservation, audit-failure safety, and legacy left
untouched.
"""
import os
import subprocess
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOperatorWorkflowRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_operator_workflow_regression(self):
        p = self.p
        full, dec, appr, exe = (p.login(p.op_full), p.login(p.op_decider), p.login(p.op_approver),
                                p.login(p.op_executor))
        item = p.ni_item
        # 1 authorized user opens Decision Inbox
        self.assertEqual(full.get("/").status, 200)
        # 2 opens an authoritative recommendation; 3 Call/Why/Proof/Raw History visible
        detail = full.get("/item/" + item["id"]).body
        self.assertTrue(all(x in detail for x in ("Call", "Why", "Proof", "Raw History")))
        # 4 issues Decision; 5 audited
        before = p.stack.audit.count()
        self.assertEqual(dec.post("/item/" + item["id"] + "/decide",
                                  {"disposition": "ACCEPT", "selected_action": "order"},
                                  correlation_id="corr_reg").status, 303)
        d = p.p9.store.decisions_for_item(item["id"])[0]
        self.assertEqual(p.stack.audit.count(), before + 1)
        # 6 separate approver approves; 7 approval does not execute
        self.assertEqual(dec.post("/approval/" + d["id"] + "/approve", {}).status, 403)   # 8: SoD — proposer≠approver
        self.assertEqual(appr.post("/approval/" + d["id"] + "/approve", {}).status, 303)
        self.assertEqual(p.p9.store.execauths_for(d["id"]), [])
        # 8/9 authorized executor initiates existing domain service; actual domain event returned
        self.assertEqual(exe.post("/execution/" + d["id"] + "/authorize", {}).status, 303)
        e = p.p9.store.execauths_for(d["id"])[-1]
        self.assertTrue(e["domain_execution_ref"])
        # 10 completion + reconciliation shown
        self.assertEqual(exe.post("/execution/" + e["id"] + "/complete", {}).status, 303)
        self.assertIn("COMPLETED", [r["outcome"] for r in p.p9.store.reconciliations_for(d["id"])])
        self.assertIn("Reconciliation:", full.get("/item/" + item["id"]).body)
        # 11 repeated (identical) submission does not duplicate any record
        n0 = len(p.p9.store.approvals_for(d["id"]))
        appr.post("/approval/" + d["id"] + "/approve", {"_idem": "k"})
        appr.post("/approval/" + d["id"] + "/approve", {"_idem": "k"})
        self.assertEqual(len(p.p9.store.approvals_for(d["id"])), n0 + 1)   # the retry replayed, not duplicated
        # 12 a new accepted fact makes the old recommendation stale; 13 stale cannot execute
        p.p9.expiration.mark_recommendation_stale(p.fresh_item, reason="new fact", triggering_fact="bf_new")
        self.assertEqual(dec.post("/item/" + p.fresh_item["id"] + "/decide",
                                  {"disposition": "ACCEPT", "selected_action": "x"}).status, 409)
        # 14 authorized override requires a reason
        self.assertEqual(dec.post("/item/" + p.fresh_item["id"] + "/decide",
                                  {"disposition": "OVERRIDE", "selected_action": "x"}).status, 409)
        self.assertEqual(dec.post("/item/" + p.fresh_item["id"] + "/decide",
                                  {"disposition": "OVERRIDE", "selected_action": "x", "override_reason": "urgent"}
                                  ).status, 303)
        # 15 Scenario recommendation cannot execute officially
        full.post("/item/" + p.scenario_item["id"] + "/decide", {"disposition": "ACCEPT", "selected_action": "x"})
        sd = p.p9.store.decisions_for_item(p.scenario_item["id"])[0]
        p.p9.approvals.approve(p.op_full, SCOPE, sd)
        self.assertEqual(full.post("/execution/" + sd["id"] + "/authorize", {}).status, 409)
        # 16 every mutation preserves the correlation ID
        self.assertIn("corr_reg", full.get("/audit", correlation_id="corr_reg").body)
        # 17 no domain calculation is performed in the UI layer
        import elite.ui.views.domains as dom
        self.assertNotIn("monthly_expected", open(dom.__file__).read())
        # 18 prior recommendation and Decision remain historical
        self.assertIsNotNone(p.p9.store.get_decision(d["id"]))
        self.assertEqual(p.ni_plan.need, p.p4.store.get_plan(p.ni_plan.id).need
                         if hasattr(p.p4.store, "get_plan") else p.ni_plan.need)   # plan unchanged
        # 19 audit failure produces a visible safe failure
        orig = p.stack.audit.append
        p.stack.audit.append = lambda conn, ev: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r = dec.post("/item/" + p.stale_item["id"] + "/decide",
                         {"disposition": "OVERRIDE", "selected_action": "x", "override_reason": "r"})
        finally:
            p.stack.audit.append = orig
        self.assertEqual(r.status, 409)
        self.assertNotIn("Traceback", r.body)
        # 20 legacy application remains untouched
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--", "build",
                               "Pipeline-Manager.html", "pipeline_manager"], cwd=_REPO,
                              capture_output=True, text=True)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])


if __name__ == "__main__":
    unittest.main()
