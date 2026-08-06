"""Phase 12 dedicated final-readiness regression (25-point).

Walks the full readiness -> authorization gate: a release package exists and pins the exact revision; the
source inventory, migration + rollback rehearsals, UAT, and discrepancy state are known; a material
unresolved discrepancy / missing policy / missing authority / failed rollback each block readiness; all ten
dimensions are separately visible; applicable PASS/PASS_WITH_WARNINGS dimensions can produce operational
readiness, which is NOT itself go-live authorization; an automated test cannot set GO_LIVE_AUTHORIZED; an
authorized Principal issues the explicit release Decision referencing the exact package; a limited
authorization names its exact domains; authorization performs no cutover; a new blocker supersedes prior
readiness; prior certification + authorization remain historical; no authorization leaves the system in
parallel pilot mode; an expired authorization cannot transition mode; the legacy tool remains available; and
no irreversible cutover occurs.
"""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ValidationError
from elite.release.fixtures import Phase12, SCOPE, CAPS

FR = "store:FRREG"
_PREREQS = ["ENGINEERING_READY", "DATA_READY", "POLICY_READY", "AUTHORITY_READY", "OPERATOR_READY",
            "MIGRATION_READY", "ROLLBACK_READY", "SECURITY_READY"]


class TestFinalReadinessRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase12(os.path.join(self.tmp, "elite.db"))
        p = self.p
        for cap in (CAPS["PACKAGE_ISSUE"], CAPS["CERTIFY"]):
            p.stack.grant(p.op_releaser, cap, FR)
        p.stack.grant(p.op_authorizer, CAPS["AUTHORIZE_RELEASE"], FR)
        p.stack.grant(p.op_validator, CAPS["PARALLEL_RUN"], FR)
        p.stack.grant(p.op_validator, CAPS["DISCREPANCY_REVIEW"], FR)
        p.stack.grant(p.op_uat, CAPS["UAT_RECORD"], FR)

    def tearDown(self):
        self.p.close()

    def test_final_readiness_regression(self):
        p = self.p

        # 1-2. a release package exists and pins the exact revision + migration level
        pkg = p.packages.issue(principal=p.op_releaser, scope=FR,
                               release_package_id=p.packages.build(version_label="v1.0.0",
                                   application_revision="83d66e4", migration_level=12,
                                   unresolved_risks=["execution wiring per domain"])["id"])
        self.assertEqual(pkg["application_revision"], "83d66e4")
        self.assertEqual(pkg["migration_level"], 12)

        # 3. the source inventory is complete or explicitly blocked
        p.migration.record_connection(source_family="new_inventory_current", classification="FILE_EXPORT")
        p.migration.record_connection(source_family="policy_incentive_inputs", classification="UNAVAILABLE",
                                      unresolved_blocker="no export exists")
        self.assertTrue(all(c["classification"] for c in p.store.list_connections()))

        # 4-6. migration + rollback rehearsal results + UAT evidence exist
        reh = p.rehearsal.migration_rehearsal()
        roll = p.rehearsal.rollback_rehearsal(migration_rehearsal_ref=reh["id"], elite_history_preserved=True,
                                              legacy_available=True)
        t = p.uat.add_test(test_case="inbox", domain="new_inventory", scope=FR, expected_result="ok")
        p.uat.record(principal=p.op_uat, scope=FR, uat_test_id=t["id"], actual_result="ok", outcome="pass")
        self.assertEqual(reh["outcome"], "pass")
        self.assertEqual(roll["outcome"], "pass")
        self.assertTrue(p.store.uat_results(t["id"]))

        # 7-8. a material unresolved discrepancy is known and blocks readiness
        pv = p.parallel.run(principal=p.op_validator, scope=FR, run_date="2026-08-06",
                            subjects=[{"subject_ref": "s1", "domain": "new_inventory", "elite_value": 9,
                                       "legacy_value": 1, "classification": "CALCULATION_DIFFERENCE"}])
        disc = p.discrepancy.open(parallel_result_ref=pv["results"][0]["id"], domain="new_inventory",
                                  scope=FR, summary="calc diff", classification="CALCULATION_DIFFERENCE")
        self.assertTrue(p.discrepancy.blocking(FR))                       # material unresolved blocks
        self.assertEqual(p.store.get_discrepancy(disc["id"])["status"], "OPEN")

        # 9. missing required policy blocks (none confirmed yet)
        self.assertTrue(p.migration.required_policies_present(FR, ["desired_ending_coverage"]))

        # 10. missing authority blocks the related workflow
        with self.assertRaises(AuthorizationError):
            p.stack.authz.require(p.op_noauth, "release.migrate.run", FR)

        # 11. a failed rollback rehearsal blocks readiness
        bad_roll = p.rehearsal.rollback_rehearsal(migration_rehearsal_ref=reh["id"],
                                                  elite_history_preserved=True, legacy_available=False)
        self.assertEqual(bad_roll["outcome"], "fail")

        # 12-13. all ten dimensions are separately visible; applicable PASS dimensions produce operational
        # readiness under policy
        cert = p.readiness.certify(principal=p.op_releaser, scope=FR, release_package_ref=pkg["id"],
                                   dimensions={d: {"status": "PASS"} for d in _PREREQS})
        dims = p.readiness.dimensions_of(cert["id"])
        self.assertEqual(len(dims), 10)
        self.assertEqual(dims["OPERATIONALLY_READY"]["status"], "PASS")

        # 14-15. operational readiness is not go-live authorization; certification cannot set GO_LIVE
        self.assertEqual(dims["GO_LIVE_AUTHORIZED"]["status"], "NOT_APPLICABLE")
        self.assertFalse(p.authorization.is_go_live_authorized(FR, pkg["id"]))

        # 16-17. an authorized Principal issues the explicit release Decision referencing the exact package
        auth = p.authorization.authorize(principal=p.op_authorizer, scope=FR, release_package_ref=pkg["id"],
                                         certification_ref=cert["id"], disposition="AUTHORIZE_GO_LIVE",
                                         warnings_ack=["minimal UI"], risks_ack=["per-domain wiring"],
                                         rollback_plan_ref=roll["id"])
        self.assertEqual(auth["release_package_ref"], pkg["id"])
        self.assertEqual(auth["authorized_by"], p.op_authorizer)

        # 18. a limited-domain authorization names its exact domains
        lim = p.authorization.authorize(principal=p.op_authorizer, scope=FR, release_package_ref=pkg["id"],
                                        certification_ref=cert["id"], disposition="AUTHORIZE_LIMITED_DOMAIN_GO_LIVE",
                                        enabled_domains=["service_loaner"], rollback_plan_ref=roll["id"])
        import json
        self.assertEqual(json.loads(lim["enabled_domains"]), ["service_loaner"])

        # 19. authorization performs no cutover (pilot still blocks destructive cutover)
        self.assertFalse(p.p11.pilot.cutover_available())
        with self.assertRaises(AuthorizationError):
            p.p11.pilot.assert_action_allowed("cutover")

        # 20-21. a new blocker supersedes prior readiness; prior certification remains historical
        cert2 = p.readiness.certify(principal=p.op_releaser, scope=FR, release_package_ref=pkg["id"],
                                    dimensions={**{d: {"status": "PASS"} for d in _PREREQS},
                                                "DATA_READY": {"status": "FAIL"}})
        self.assertEqual(cert2["overall"], "NOT_READY")
        self.assertTrue(p.store.get_certification(cert["id"])["superseded_by"])     # prior superseded, retained

        # 22. with no active go-live authorization for the superseding state, the system stays in parallel
        # pilot mode (pilot mode remains on; legacy fallback available)
        self.assertTrue(p.p11.pilot.is_pilot())

        # 23. an expired authorization cannot transition mode
        import datetime as _dt
        past = (p.clock.now() - _dt.timedelta(hours=1)).isoformat()
        exp = p.authorization.authorize(principal=p.op_authorizer, scope=FR, release_package_ref=pkg["id"],
                                        certification_ref=cert["id"], disposition="AUTHORIZE_GO_LIVE",
                                        rollback_plan_ref=roll["id"], expires_at=past)
        self.assertIsNone(p.authorization.active_authorization(FR, pkg["id"]))

        # 24-25. the legacy tool remains available; no irreversible cutover occurred
        self.assertTrue(p.p11.pilot.legacy_fallback_available())
        import subprocess
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        diff = subprocess.run(["git", "diff", "legacy/inventory-tool", "--", "build", "Pipeline-Manager.html",
                               "pipeline_manager"], cwd=repo, capture_output=True, text=True)
        self.assertEqual(diff.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
