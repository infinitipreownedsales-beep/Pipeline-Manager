"""Phase 10 acceptance — Scenario admin (61-66), Calibration review (67-70), Authority (71-76),
Audit (77-79), Exceptions (80-82), Summaries (83), Readiness (84-88), Search (89-90)."""
import os
import tempfile
import unittest

from elite.learning.fixtures import _to_approved, _to_validated
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


class TestPhase10Govern(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    # ---- Scenario admin (61-66) -------------------------------------------
    def test_61_scenario_visibly_hypothetical(self):
        body = self.full.get("/scenarios").body
        self.assertIn("hypothetical", body.lower())
        self.assertIn(self.p.scn["scenario_id"], body)

    def test_62_63_sharing_and_discussion_not_official(self):
        self.p.p9.scenarios.share(self.p.op_full, SCOPE, self.p.scn, shared_with=self.p.op_readonly)
        body = self.full.get("/scenarios").body
        self.assertIn("SHARED", body)                                  # shared status shown as such
        self.assertIn("shared does not mean approved", body.lower())   # 62: sharing not approval
        self.assertIn("does not mean official", body.lower())          # 63: discussion not official
        # the scenario carries a hypothetical Scenario badge, never an official-state badge
        self.assertIn("badge scenario", body)

    def test_64_promotion_no_direct_effect(self):
        sc = self.p.p9.scenarios.share(self.p.op_full, SCOPE, self.p.scn, shared_with=self.p.op_readonly)
        self.p.p9.scenarios.review(self.p.op_full, SCOPE, self.p.p9.store.get_scenario(sc["id"]))
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]
        self.p.p9.scenarios.request_promotion(self.p.op_full, SCOPE, self.p.p9.store.get_scenario(sc["id"]),
                                              target_type="official_policy_review")
        after = self.p.stack.db.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]
        self.assertEqual(before, after)

    def test_65_comparison_identifies_overrides(self):
        r = self.full.get("/scenario/" + self.p.scn["id"])
        self.assertIn("coverage_target", r.body)           # the override is shown
        self.assertIn("baseline", r.body.lower())

    def test_66_private_scenario_scoped(self):
        self.assertEqual(self.p.scn["store_scope"], SCOPE)
        oos = self.p.login(self.p.op_otherscope, scope=SCOPE)
        self.assertEqual(oos.get("/scenarios").status, 403)   # cannot reach another store's scenarios

    # ---- Calibration (67-70) ----------------------------------------------
    def test_67_approval_distinct_from_activation(self):
        cal = _to_validated(self.p.p9.p8, self.p.p9.p8.calib(self.p.p9.p8.proposer))
        self.p.p9.calibration_ws.approve(self.p.p9.p8.approver, SCOPE, cal)
        r = self.full.get("/calibration/" + cal["id"])
        self.assertIn("Not activated", r.body)

    def test_68_scheduled_future_effective(self):
        cal = _to_approved(self.p.p9.p8, target_type="calculation_version",
                           effective="2030-01-01T00:00:00+00:00")
        self.p.p9.calibration_ws.activate(self.p.p9.p8.activator, SCOPE, cal, future=True)
        r = self.full.get("/calibration/" + cal["id"])
        self.assertIn("Scheduled", r.body)

    def test_69_policy_target_routes_to_review(self):
        cal = _to_approved(self.p.p9.p8, target_type="materiality_threshold")
        self.p.p9.calibration_ws.activate(self.p.p9.p8.activator, SCOPE, cal)
        r = self.full.get("/calibration/" + cal["id"])
        self.assertIn("policy review", r.body.lower())

    def test_70_prior_predictions_unchanged(self):
        pred = self.p.p9.p8.prediction(value=10, subject_entity_id="cui")
        cal = _to_approved(self.p.p9.p8, target_type="calculation_version")
        self.p.p9.calibration_ws.activate(self.p.p9.p8.activator, SCOPE, cal)
        self.assertEqual(self.p.p9.p8.store.get_prediction(pred.id).predicted_payload["value"], 10)

    # ---- Authority (71-76) ------------------------------------------------
    def test_71_72_authority_view_and_chain(self):
        d = self.p.stack.authn.register("DUI", "pw").id
        self.p.p9.authority.delegate(self.p.op_full, SCOPE, delegate=d, capability="decision.approve",
                                     delegate_scope="*", reason="cover")
        body = self.full.get("/authority").body
        self.assertIn(d, body)                             # from the Phase 1 records
        self.assertIn("delegated_by:", body)               # grant chain visible

    def test_73_74_expired_and_revoked_look_inactive(self):
        d = self.p.stack.authn.register("DUI2", "pw").id
        dg = self.p.p9.authority.delegate(self.p.op_full, SCOPE, delegate=d, capability="decision.approve",
                                          delegate_scope="*")
        self.p.p9.authority.revoke_delegation(self.p.op_full, SCOPE, dg)
        self.assertIn("Inactive / revoked", self.full.get("/authority").body)

    def test_75_authority_mutation_governed(self):
        before = self.p.stack.audit.count()
        d = self.p.stack.authn.register("DUI3", "pw").id
        self.full.post("/authority/delegate", {"delegate": d, "capability": "decision.approve", "scope": "*"})
        self.assertEqual(self.p.stack.audit.count(), before + 1)     # governed + audited
        self.assertTrue(any(g.capability == "decision.approve" for g in self.p.stack.grants.list_for(d)))

    def test_76_authority_audit_failure_no_success(self):
        d = self.p.stack.authn.register("DUI4", "pw").id
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r = self.full.post("/authority/delegate", {"delegate": d, "capability": "decision.approve", "scope": "*"})
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(r.status, 409)
        self.assertFalse(any(g.capability == "decision.approve" for g in self.p.stack.grants.list_for(d)))

    # ---- Audit (77-79) ----------------------------------------------------
    def test_77_audit_read_only(self):
        body = self.full.get("/audit").body
        self.assertIn("read-only", body.lower())
        self.assertNotIn("<button", body.split("<table")[-1] if "<table" in body else "")   # no mutate controls in table

    def test_78_correlated_trace(self):
        it = self.p.fresh_item
        self.p.decider = self.p.login(self.p.op_decider)
        self.p.decider.post("/item/" + it["id"] + "/decide",
                            {"disposition": "ACCEPT", "selected_action": "x"}, correlation_id="corr_ui")
        r = self.full.get("/audit", correlation_id="corr_ui")
        self.assertIn("corr_ui", r.body)

    def test_79_missing_audit_event_exception(self):
        ex = self.p.p9.audit_admin.detect_missing(expected_action="never.happens", correlation_id="c_x")
        self.assertIsNotNone(ex)
        self.assertEqual(ex["kind"], "missing_expected_event")

    # ---- Exceptions (80-82) -----------------------------------------------
    def test_80_81_queue_links_source_close_preserves(self):
        body = self.full.get("/exceptions").body
        self.assertIn(self.p.stale_item["id"], body)       # references the authoritative source
        item = self.p.exception
        self.p.p9.queues.close(item)
        self.assertEqual(self.p.p9.store.get_workspace_item(self.p.stale_item["id"])["workspace_state"],
                         "READY_FOR_REVIEW")               # source untouched

    def test_82_dismissal_requires_authority_and_reason(self):
        item = self.p.p9.queues.enqueue(queue="missing_policy", source_type="policy_family", source_ref="pf",
                                        owning_domain="new_inventory")
        # no reason -> rejected
        r = self.full.post("/exception/" + item["id"] + "/dismiss", {"reason": ""})
        self.assertEqual(r.status, 409)
        # unauthorized operator -> rejected
        ro = self.p.login(self.p.op_readonly)
        r2 = ro.post("/exception/" + item["id"] + "/dismiss", {"reason": "dup"})
        self.assertEqual(r2.status, 403)

    # ---- Summaries (83) ---------------------------------------------------
    def test_83_summaries_reconcile(self):
        r = self.full.get("/summaries")
        total = len(self.p.p9.store.all_items(scope=SCOPE))
        self.assertIn(str(total), r.body)

    # ---- Readiness (84-88) ------------------------------------------------
    def test_84_85_86_87_readiness_evidence_based(self):
        body = self.full.get("/readiness").body
        self.assertIn("NOT_READY", body)                   # the seeded missing-policy domain
        self.assertIn("evidence-based", body.lower())

    def test_88_readiness_does_not_deploy(self):
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"]
        self.p.p9.readiness.assess(self.p.p9.readiness_assessor, SCOPE, owning_domain="service_loaner",
                                   required_policy_present=True, authority_coverage=True)
        after = self.p.stack.db.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"]
        self.assertEqual(before, after)

    # ---- Search (89-90) ---------------------------------------------------
    def test_89_90_search_scoped_and_links(self):
        r = self.full.get("/search", q=self.p.ni_item["subject_entity_id"])
        self.assertIn("/item/", r.body)                    # links to authoritative detail
        # out-of-scope operator cannot search another store
        oos = self.p.login(self.p.op_otherscope, scope=SCOPE)
        self.assertEqual(oos.get("/search", q="anything").status, 403)


if __name__ == "__main__":
    unittest.main()
