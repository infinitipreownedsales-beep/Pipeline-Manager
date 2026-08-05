"""Phase 5 acceptance — integrated forecast updates, governance/audit, output slices (56-69)."""
import os
import sqlite3
import tempfile
import unittest

from elite.errors import AuthorizationError, ConcurrencyError, PersistenceError
from elite.workflow.fixtures import OTHER_SCOPE, SCOPE, Phase5
from elite.workflow.output import build_workflow_slice


class TestPhase5IntegrateGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _committed(self, color="BLACK", scenario_id=None):
        c, d, plan = self.p.need_combo(exterior_color=color)
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id=f"po_{color}", combination_id=c.id,
                               arrival_month="2026-09", scenario_id=scenario_id)
        self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        return c, d, plan, self.p.wf.get_workflow(w.id)

    def test_56_workflow_change_issues_new_planning_result(self):
        c, d, plan, w = self._committed("N")
        new_plan = self.p.integrate.reissue_plan(d, SCOPE, coverage_target=2, workflow_id=w.id,
                                                 causing_action="cpo.approve")
        self.assertNotEqual(new_plan.id, plan.id)
        self.assertLess(new_plan.need, plan.need)             # updated supply -> lower need

    def test_57_prior_issued_planning_result_immutable(self):
        c, d, plan, w = self._committed("I")
        before = plan.need
        self.p.integrate.reissue_plan(d, SCOPE, coverage_target=2, workflow_id=w.id, causing_action="cpo.approve")
        self.assertEqual(self.p.ni.get_plan(plan.id).need, before)   # unchanged
        with self.assertRaises(sqlite3.Error):
            with self.p.ni.conn:
                self.p.ni.conn.execute("DELETE FROM inventory_plan_result WHERE id=?", (plan.id,))

    def test_58_workflow_output_identifies_causing_action(self):
        c, d, plan, w = self._committed("A")
        new_plan = self.p.integrate.reissue_plan(d, SCOPE, coverage_target=2, workflow_id=w.id,
                                                 causing_action="cpo.approve")
        rows = self.p.wf.workflow_issued_outputs(w.id)
        self.assertTrue(any(r["output_id"] == new_plan.id and r["causing_action"] == "cpo.approve" for r in rows))

    def test_59_official_and_scenario_workflows_isolated(self):
        c, d, plan, wo = self._committed("O")                 # official
        cs, ds, plans, ws = self._committed("S", scenario_id="scn1")
        self.assertIsNone(wo.scenario_id)
        self.assertEqual(ws.scenario_id, "scn1")
        sp = self.p.integrate.reissue_plan(ds, SCOPE, coverage_target=2, workflow_id=ws.id,
                                           causing_action="cpo.approve", scenario_id="scn1")
        self.assertEqual(sp.scenario_id, "scn1")

    def test_60_proposal_and_approval_authorities_separate(self):
        c, d, _ = self.p.need_combo(exterior_color="P")
        w = self.p.cpo.propose(self.p.proposer, SCOPE, production_order_id="po", combination_id=c.id,
                               arrival_month="2026-10")   # proposer may propose
        with self.assertRaises(AuthorizationError):
            self.p.cpo.approve(self.p.proposer, SCOPE, w)  # but not approve
        self.p.cpo.approve(self.p.approver, SCOPE, w)      # approver may approve

    def test_61_approval_and_completion_authorities_separate(self):
        c, d, _ = self.p.need_combo(exterior_color="Q")
        w = self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu", combination_id=c.id, arrival_month="2026-10")
        self.p.dt.send_request(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.dt.accept(self.p.approver, SCOPE, self.p.wf.get_workflow(w.id))   # approver accepts
        with self.assertRaises(AuthorizationError):
            self.p.dt.complete(self.p.approver, SCOPE, self.p.wf.get_workflow(w.id), received_unit_id="vu")
        self.p.dt.complete(self.p.completer, SCOPE, self.p.wf.get_workflow(w.id), received_unit_id="vu")

    def test_62_authorization_enforced_below_ui(self):
        c, d, _ = self.p.need_combo(exterior_color="B")
        # a principal with no workflow grants cannot propose
        nobody = self.p.stack.authn.register("Nobody", "pw").id
        with self.assertRaises(AuthorizationError):
            self.p.cpo.propose(nobody, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")

    def test_63_scope_mismatch_rejected(self):
        c, d, _ = self.p.need_combo(exterior_color="C")
        scoped = self.p.stack.authn.register("Scoped", "pw").id
        self.p.stack.grant(scoped, "cpo.propose", SCOPE)      # only store:HG
        with self.assertRaises(AuthorizationError):
            self.p.cpo.propose(scoped, OTHER_SCOPE, production_order_id="po", combination_id=c.id,
                               arrival_month="2026-10")       # store:WEST -> denied

    def test_64_revoked_authority_rejected(self):
        c, d, _ = self.p.need_combo(exterior_color="R")
        rid = self.p.stack.authn.register("Temp", "pw").id
        g = self.p.stack.grant(rid, "cpo.propose", "*")
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        with self.assertRaises(AuthorizationError):
            self.p.cpo.propose(rid, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")

    def test_65_stale_transition_rejected(self):
        import dataclasses
        c, d, _ = self.p.need_combo(exterior_color="S")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        with self.assertRaises(ConcurrencyError):
            self.p.cpo.approve(self.p.full, SCOPE, dataclasses.replace(w, version=99))

    def test_66_idempotent_retry_no_duplicate_effect(self):
        c, d, _ = self.p.need_combo(exterior_color="D")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.assertEqual(len(self.p.supply.qualifying_supply(c.id, SCOPE)), 1)   # not two

    def test_67_required_audit_written_atomically(self):
        c, d, _ = self.p.need_combo(exterior_color="AU")
        before = self.p.stack.audit.count()
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        self.assertEqual(self.p.stack.audit.count(), before + 1)   # propose audited
        self.p.cpo.approve(self.p.full, SCOPE, w)
        self.assertEqual(self.p.stack.audit.count(), before + 2)   # approve audited

    def test_68_audit_failure_prevents_unsafe_success(self):
        c, d, _ = self.p.need_combo(exterior_color="AF")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                self.p.cpo.approve(self.p.full, SCOPE, w)
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(self.p.wf.get_workflow(w.id).lifecycle_status, "PROPOSED")   # rolled back
        self.assertEqual(len(self.p.supply.qualifying_supply(c.id, SCOPE)), 0)

    def test_69_output_slice_uses_real_domain_output(self):
        c, d, plan, w = self._committed("SL")
        new_plan = self.p.integrate.reissue_plan(d, SCOPE, coverage_target=2, workflow_id=w.id,
                                                 causing_action="cpo.approve")
        sl = build_workflow_slice(self.p.wf, self.p.ni, w.id, plan=new_plan, demand=d)
        self.assertEqual(sl["need"], new_plan.need)
        self.assertEqual(sl["demand"], d.monthly_expected)
        self.assertEqual(sl["workflow_state"], "COMMITTED")
        self.assertIn("COMMITMENT_CREATED", sl["why"]["reconciliation_outcomes"])
        for key in ("call", "why", "proof", "identity", "timing", "versions", "evidence_references"):
            self.assertIn(key, sl)


if __name__ == "__main__":
    unittest.main()
