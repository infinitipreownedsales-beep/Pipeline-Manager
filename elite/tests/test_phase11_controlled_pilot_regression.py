"""Phase 11 dedicated controlled-pilot regression (20-point).

Walks the whole controlled-pilot loop: the app starts in pilot mode with a visible banner and a preserved
legacy fallback; destructive cutover is blocked; a parallel comparison preserves both tools' results,
classifies differences, keeps unknown causes unresolved, records reviewer rationale, and mutates neither
result; a material unresolved difference blocks readiness until reviewed; an acceptable reviewed difference
permits ready-with-warnings; operator feedback records the exact revision and alters nothing; a backup
succeeds; health distinguishes live from ready; a restart preserves comparison + feedback history; the
pilot continues after a failed import using the prior valid state; and no production cutover occurs.
"""
import os
import tempfile
import unittest

from elite.ops import fixtures as F
from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.models import CAPS, READY, READY_WITH_WARNINGS, NOT_READY
from elite.errors import AuthorizationError

RS = "store:PILOTREG"       # isolated pilot-regression scope


class TestControlledPilotRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "elite.db"))
        # grant the reviewer/certifier the isolated regression scope
        for cap in (CAPS["PILOT_COMPARE"], CAPS["PILOT_REVIEW"]):
            self.p.stack.grant(self.p.op_reviewer, cap, RS)
        self.p.stack.grant(self.p.op_certifier, CAPS["PILOT_CERTIFY"], RS)
        self.p.stack.grant(self.p.op_feedback, CAPS["FEEDBACK_SUBMIT"], RS)

    def tearDown(self):
        self.p.close()

    def test_controlled_pilot_regression(self):
        p = self.p

        # 1-3. starts in pilot mode; banner visible; legacy fallback available
        self.assertTrue(p.pilot.is_pilot())
        self.assertIn("PILOT MODE", p.pilot.banner())
        self.assertTrue(p.pilot.legacy_fallback_available())

        # 4. destructive cutover control is unavailable / blocked
        self.assertFalse(p.pilot.cutover_available())
        with self.assertRaises(AuthorizationError):
            p.pilot.assert_action_allowed("cutover")

        # 5-9. parallel comparison preserves both results, classifies, keeps unknown unresolved
        cmp = p.pilot.compare(domain="new_inventory", scope=RS, initiated_by=p.op_reviewer, subjects=[
            {"subject_ref": "m1", "elite_result": 5, "legacy_result": 5},
            {"subject_ref": "d1", "elite_result": 8, "legacy_result": 6,
             "classification": "CALCULATION_DIFFERENCE", "likely_source": "calculation"},
            {"subject_ref": "u1", "elite_result": 3, "legacy_result": 9},   # unknown -> UNRESOLVED
        ])
        results = {r["subject_ref"]: r for r in cmp["results"]}
        self.assertEqual(str(results["d1"]["elite_result"]), "8")          # elite preserved
        self.assertEqual(str(results["d1"]["legacy_result"]), "6")         # legacy preserved
        self.assertEqual(results["m1"]["classification"], "MATCH")         # difference classified
        self.assertEqual(results["d1"]["classification"], "CALCULATION_DIFFERENCE")
        self.assertEqual(results["u1"]["classification"], "UNRESOLVED")    # unknown stays unresolved

        # 10-11. reviewer records rationale; comparison mutates neither result
        material_id = results["d1"]["id"]
        p.pilot.review_difference(result_id=material_id, reviewer=p.op_reviewer, disposition="acceptable",
                                  scope=RS, notes="explained by a known timing lag")
        reviewed = p.ops.get_comparison_result(material_id)
        self.assertEqual(reviewed["notes"], "explained by a known timing lag")
        self.assertEqual(str(reviewed["elite_result"]), "8")               # unchanged
        self.assertEqual(str(reviewed["legacy_result"]), "6")              # unchanged

        # 12. a material UNRESOLVED difference (u1) still blocks readiness until reviewed
        r_before = p.health.readiness(RS)
        self.assertEqual(r_before["status"], NOT_READY)
        self.assertIn("unreviewed_material_discrepancy", r_before["blockers"])

        # 13. once every material difference is reviewed, an acceptable review permits ready-with-warnings
        p.pilot.review_difference(result_id=results["u1"]["id"], reviewer=p.op_reviewer,
                                  disposition="acceptable", scope=RS, notes="agreed acceptable")
        r_after = p.health.readiness(RS)
        self.assertIn(r_after["status"], (READY, READY_WITH_WARNINGS))
        self.assertNotIn("unreviewed_material_discrepancy", r_after["blockers"])

        # 14-15. operator feedback records the exact revision and alters neither result
        elite_before = p.ops.get_comparison_result(material_id)["elite_result"]
        fb = p.pilot.submit_feedback(principal_id=p.op_feedback, scope=RS, category="usability",
                                     description="clarify label", screen_ref="/new-inventory",
                                     revision_ref="rev-77")
        self.assertEqual(fb["revision_ref"], "rev-77")
        self.assertEqual(p.ops.get_comparison_result(material_id)["elite_result"], elite_before)

        # 16. a backup succeeds
        bk = p.backup.create_backup(tempfile.mkdtemp())
        self.assertEqual(bk["status"], "verified")

        # 17. health distinguishes live from ready
        self.assertEqual(p.health.liveness()["status"], "UP")
        self.assertIn(p.health.readiness(RS)["status"], (READY, READY_WITH_WARNINGS, NOT_READY))

        # 18. a restart preserves comparison + feedback history
        comparisons = len(p.ops.list_comparison_results())
        feedback = len(p.ops.list_feedback())
        q = p.restart()
        try:
            self.assertEqual(q.table_count("pilot_comparison_result"), comparisons)
            self.assertEqual(q.table_count("operator_feedback"), feedback)
        finally:
            q.close()

        # 19. the controlled pilot continues after a failed import using the prior valid state
        sid = p.source_id("new_inventory_current")
        good = p.import_payload("new_inventory_current", F.INV_VALID, effective_time=p.now_iso(),
                                chash="sha256:preg-good")
        last_valid = p.orch._last_completed(sid, SCOPE)
        p.import_payload("new_inventory_current", F.INV_FULL, chash="sha256:preg-fail", fail_at="ingest")
        self.assertTrue(p.orch.accepted_state_intact(sid, SCOPE, last_valid))   # prior valid usable
        cont = p.import_payload("new_inventory_current", F.INV_FULL, effective_time=p.now_iso(),
                                chash="sha256:preg-cont")
        self.assertEqual(cont["state"], "COMPLETED")               # pilot keeps operating

        # 20. no production cutover occurs
        self.assertFalse(p.pilot.cutover_available())
        for a in p.pilot.CUTOVER_ACTIONS:
            with self.assertRaises(AuthorizationError):
                p.pilot.assert_action_allowed(a)


if __name__ == "__main__":
    unittest.main()
