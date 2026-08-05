"""Phase 9 acceptance — Decision Workspace + recommendation review (1-6), Decision issuance +
dispositions (7-26)."""
import os
import tempfile
import unittest

from elite.errors import PersistenceError, ValidationError
from elite.govern.fixtures import Phase9
from elite.workflow.fixtures import SCOPE


class TestPhase9WorkspaceDecision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase9(self.dbp)

    def tearDown(self):
        self.p.close()

    # ---- workspace + review (1-6) -----------------------------------------
    def test_01_item_survives_restart(self):
        it = self.p.item(rec="rec_a")
        self.p.close()
        p2 = Phase9(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_workspace_item(it["id"]))

    def test_02_references_not_copies_domain_output(self):
        it = self.p.item(rec="rec_ref")
        self.assertEqual(it["recommendation_ref"], "rec_ref")            # a reference, not a copy
        cols = [d[0] for d in self.p.store.conn.execute("SELECT * FROM decision_workspace_item").description]
        for domain_math in ("predicted_payload", "need", "excess", "monthly_expected", "economic_call"):
            self.assertNotIn(domain_math, cols)                         # no second source of truth

    def test_03_04_new_recommendation_new_revision(self):
        it = self.p.item(rec="rec_v1")
        revised = self.p.workspace.revise(it, new_recommendation_ref="rec_v2", reason="new forecast")
        self.assertEqual(revised["recommendation_ref"], "rec_v2")
        revs = self.p.store.workspace_revisions(it["id"])
        self.assertTrue(revs and revs[0]["recommendation_ref"] == "rec_v1")   # prior remains historical

    def test_05_review_exposes_facts_versions_confidence_rawhistory(self):
        it = self.p.item(rec="rec_r")
        review = self.p.workspace.review(it, resolvers={"confidence": lambda i: "high",
                                                        "uncertainty": lambda i: {"band": "±2"}})
        self.assertEqual(review["applicable_facts"], ["bf_1"])
        self.assertIn("calculation", review["applicable_versions"])
        self.assertEqual(review["why"]["confidence"], "high")          # resolved from the domain record
        self.assertEqual(review["why"]["uncertainty"], {"band": "±2"})
        self.assertIn("raw_history_path", review)

    def test_06_missing_explanation_not_invented(self):
        it = self.p.item(rec="rec_x")
        review = self.p.workspace.review(it)                            # no resolvers
        self.assertEqual(review["why"], {})                            # nothing invented
        self.assertFalse(review["explanation_present"])

    # ---- Decision issuance (7-17) -----------------------------------------
    def test_07_08_decision_references_exact_recommendation(self):
        it = self.p.item(rec="rec_exact")
        r = self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="order")
        d = r["decision"]
        self.assertEqual(d["source_recommendation_ref"], "rec_exact")  # exact recommendation
        self.assertEqual(d["recommendation_revision"], str(it["version"]))   # state known at Decision time

    def test_09_missing_rationale_unknown(self):
        _, d = self.p.decide(rec="rec_nr")
        self.assertIsNone(d["rationale"])                              # unknown, not invented

    def test_10_unpresented_alternatives_not_invented(self):
        it = self.p.item(rec="rec_alt")
        self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a",
                               presented_alternatives=["A"])
        d = self.p.store.decisions_for_item(it["id"])[0]
        alts = self.p.store.alternatives_for(d["id"])
        self.assertEqual([a["alternative"] for a in alts], ["A"])      # only what was presented

    def test_11_replayed_issuance_idempotent(self):
        it = self.p.item(rec="rec_idem")
        a = self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a",
                                   idempotency_key="k1")
        b = self.p.decisions.issue(self.p.decider, SCOPE, self.p.store.get_workspace_item(it["id"]),
                                   disposition="ACCEPT", selected_action="a", idempotency_key="k1")
        self.assertTrue(b["replayed"])
        self.assertEqual(a["decision"]["id"], b["decision"]["id"])
        self.assertEqual(len(self.p.store.decisions_for_item(it["id"])), 1)

    def test_12_audit_written_atomically(self):
        it = self.p.item(rec="rec_au")
        before = self.p.stack.audit.count()
        self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a")
        self.assertEqual(self.p.stack.audit.count(), before + 1)

    def test_13_audit_failure_rolls_back(self):
        it = self.p.item(rec="rec_af")
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a")
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(self.p.store.decisions_for_item(it["id"]), [])          # rolled back
        self.assertEqual(self.p.store.get_workspace_item(it["id"])["workspace_state"], "READY_FOR_REVIEW")

    def test_14_stale_recommendation_rejects_issuance(self):
        it = self.p.item(rec="rec_st")
        self.p.expiration.mark_recommendation_stale(it, reason="new fact")
        with self.assertRaises(ValidationError):
            self.p.decisions.issue(self.p.decider, SCOPE, self.p.store.get_workspace_item(it["id"]),
                                   disposition="ACCEPT", selected_action="a")

    def test_15_authorized_stale_override_requires_reason(self):
        it = self.p.item(rec="rec_ov")
        self.p.expiration.mark_recommendation_stale(it, reason="new fact")
        fresh = self.p.store.get_workspace_item(it["id"])
        with self.assertRaises(ValidationError):                        # override without reason
            self.p.decisions.issue(self.p.decider, SCOPE, fresh, disposition="OVERRIDE", selected_action="a")
        r = self.p.decisions.issue(self.p.decider, SCOPE, fresh, disposition="OVERRIDE", selected_action="a",
                                   override_reason="urgent")
        self.assertTrue(r["decision"]["override"])
        self.assertEqual(r["decision"]["override_reason"], "urgent")

    def test_16_17_scenario_decision_scenario_only(self):
        it = self.p.item(rec="rec_scn", scenario_id="scn_1")
        d = self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a")["decision"]
        self.assertEqual(d["scenario_id"], "scn_1")                     # remains scenario-only
        it2 = self.p.item(rec="rec_scn2", scenario_id="scn_2")
        with self.assertRaises(ValidationError):                        # cannot become official truth
            self.p.decisions.issue(self.p.decider, SCOPE, it2, disposition="ACCEPT", selected_action="a",
                                   as_official=True)

    # ---- dispositions (18-26) ---------------------------------------------
    def test_18_19_accept_reject_preserve_recommendation(self):
        it = self.p.item(rec="rec_keep")
        self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a")
        self.assertEqual(self.p.store.get_workspace_item(it["id"])["recommendation_ref"], "rec_keep")
        it2 = self.p.item(rec="rec_keep2")
        self.p.decisions.issue(self.p.decider, SCOPE, it2, disposition="REJECT")
        self.assertEqual(self.p.store.get_workspace_item(it2["id"])["recommendation_ref"], "rec_keep2")

    def test_20_defer_not_rejection(self):
        it, d = self.p.decide(disposition="DEFER", rec="rec_def")
        self.assertEqual(d["disposition"], "DEFER")
        self.assertEqual(self.p.store.get_workspace_item(it["id"])["workspace_state"], "DEFERRED")

    def test_21_request_information_no_execution(self):
        it, d = self.p.decide(disposition="REQUEST_INFORMATION", rec="rec_ri")
        self.assertEqual(self.p.store.execauths_for(d["id"]), [])       # no execution effect

    def test_22_no_action_valid(self):
        it, d = self.p.decide(disposition="NO_ACTION", rec="rec_na")
        self.assertEqual(d["disposition"], "NO_ACTION")

    def test_23_override_audited(self):
        before = self.p.stack.audit.count()
        it = self.p.item(rec="rec_ova")
        self.p.expiration.mark_recommendation_stale(it, reason="x")
        self.p.decisions.issue(self.p.decider, SCOPE, self.p.store.get_workspace_item(it["id"]),
                               disposition="OVERRIDE", selected_action="a", override_reason="r")
        self.assertEqual(self.p.stack.audit.count(), before + 1)       # explicit + audited

    def test_24_correction_preserves_original(self):
        it, d = self.p.decide(rec="rec_corr")
        corrected = self.p.decisions.correct(self.p.decider, SCOPE, d, reason="typo")
        self.assertEqual(corrected["correction_of"], d["id"])
        self.assertIsNotNone(self.p.store.get_decision(d["id"]))       # original preserved

    def test_25_supersession_links_both(self):
        it, d = self.p.decide(rec="rec_sup")
        newer = self.p.decisions.supersede(self.p.decider, SCOPE, d, reason="new")
        self.assertEqual(newer["supersedes"], d["id"])
        self.assertIsNotNone(self.p.store.get_decision(d["id"]))

    def test_26_cancellation_preserves_history(self):
        it, d = self.p.decide(disposition="CANCEL", rec="rec_can")
        self.assertEqual(d["disposition"], "CANCEL")
        self.assertIsNotNone(self.p.store.get_decision(d["id"]))       # not erased


if __name__ == "__main__":
    unittest.main()
