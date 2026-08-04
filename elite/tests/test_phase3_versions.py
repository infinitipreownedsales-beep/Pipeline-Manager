"""Phase 3 acceptance — Calculation/Model/Identity-Rule/Comparison version foundation,
reproducibility, replay, activation + rollback history (items 32-43).

No domain formula is implemented here — only synthetic version-keyed behavior used to
prove that a behavior change requires a distinct version and that a preserved
reproducibility package replays identically.
"""
import os
import tempfile
import unittest

from elite.policy import calc, versions
from elite.policy.fixtures import Phase3


class TestPhase3Versions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase3(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_32_calc_family_survives_restart(self):
        cf = self.p.calc_family()
        self.p.close()
        p2 = Phase3(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_calc_family(cf.id))

    def test_33_calc_version_survives_restart(self):
        cf = self.p.calc_family()
        cv = self.p.calc_version(cf.id, "1.0.0")
        self.p.close()
        p2 = Phase3(self.dbp)
        self.addCleanup(p2.close)
        self.assertEqual(p2.store.get_calc_version(cv.id).semver, "1.0.0")

    def test_34_behavior_change_requires_distinct_version(self):
        cf = self.p.calc_family()
        v1 = self.p.calc_version(cf.id, "1.0.0")
        v2 = self.p.calc_version(cf.id, "2.0.0")
        inputs, pv = {"a": 10}, {"value": 5}
        out1 = calc.run(v1, inputs, pv)
        out2 = calc.run(v2, inputs, pv)
        self.assertNotEqual(out1, out2)                    # different behavior => different version
        self.assertEqual(calc.run(v1, inputs, pv), out1)   # same version => deterministic

    def test_35_activation_is_recorded_in_history(self):
        cf = self.p.calc_family()
        cv = self.p.calc_version(cf.id, "1.0.0")
        versions.activate_calc_version(self.p.store, cv.id, cv.version, actor=self.p.owner)
        hist = self.p.store.activation_history(cv.id)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["action"], "activate")
        self.assertEqual(self.p.store.get_calc_version(cv.id).lifecycle_status, "active")

    def test_36_rollback_preserves_versions_and_records_history(self):
        cf = self.p.calc_family()
        v1 = self.p.calc_version(cf.id, "1.0.0")
        v2 = self.p.calc_version(cf.id, "2.0.0")
        versions.activate_calc_version(self.p.store, v1.id, v1.version, actor=self.p.owner)
        v2 = self.p.store.get_calc_version(v2.id)
        versions.activate_calc_version(self.p.store, v2.id, v2.version, actor=self.p.owner)
        v2 = self.p.store.get_calc_version(v2.id)
        versions.rollback_calc_version(self.p.store, from_id=v2.id, from_expected=v2.version,
                                       to_id=v1.id, actor=self.p.owner, reason="synthetic regression")
        self.assertEqual(self.p.store.get_calc_version(v2.id).lifecycle_status, "rolled_back")  # preserved
        self.assertEqual(self.p.store.get_calc_version(v1.id).lifecycle_status, "active")       # restored
        rb = self.p.store.rollback_history("calculation_version")
        self.assertEqual(len(rb), 1)
        self.assertEqual((rb[0]["from_id"], rb[0]["to_id"]), (v2.id, v1.id))

    def test_37_model_version_registered_until_activated(self):
        mv = self.p.model_version(status="registered")
        self.assertEqual(self.p.store.get_model_version(mv.id).status, "registered")
        versions.activate_model_version(self.p.store, mv.id, actor=self.p.owner)
        self.assertEqual(self.p.store.get_model_version(mv.id).status, "active")
        self.assertEqual(len(self.p.store.activation_history(mv.id)), 1)

    def test_38_new_resolution_references_active_identity_rule(self):
        rule = self.p.identity_rule_version(status="active")
        active = self.p.store.active_identity_rule("vehicle_identity")
        self.assertEqual(active, rule.id)
        cf = self.p.calc_family()
        cv = self.p.calc_version(cf.id, "1.0.0")
        _out, pkg = calc.issue_result(self.p.store, clock=self.p.clock, calc_version=cv,
                                      inputs={"a": 1}, policy_versions=[], policy_value={"value": 1},
                                      identity_rule_version=active)
        self.assertEqual(pkg.refs["identity_rule_version"], rule.id)

    def test_39_prior_identity_rule_and_phase2_evidence_unchanged(self):
        first = self.p.identity_rule_version(version="1.0.0", status="active")
        second = self.p.identity_rule_version(version="2.0.0", status="registered")
        # both preserved (append), Phase 2 identity evidence untouched by version registration
        self.assertIsNotNone(self.p.store.active_identity_rule("vehicle_identity"))
        self.assertEqual(self.p.store.active_identity_rule("vehicle_identity"), first.id)
        rows = self.p.store.conn.execute(
            "SELECT id FROM identity_rule_version ORDER BY version").fetchall()
        self.assertEqual({r["id"] for r in rows}, {first.id, second.id})
        self.assertEqual(self.p.store.conn.execute(
            "SELECT COUNT(*) AS n FROM identity_evidence").fetchone()["n"], 0)

    def test_40_comparison_spec_persists_without_pairing(self):
        cs = self.p.comparison_spec()
        got = self.p.store.get_comparison_spec(cs.id)
        self.assertEqual(got.subject_entity_type, "vehicle")
        # foundation only: no prediction/observation pairing executed in Phase 3
        self.assertEqual(got.status, "registered")

    def test_41_reproducibility_package_pins_all_refs(self):
        cf = self.p.calc_family()
        cv = self.p.calc_version(cf.id, "1.0.0")
        mv = self.p.model_version()
        rule = self.p.identity_rule_version(status="active")
        cs = self.p.comparison_spec()
        _out, pkg = calc.issue_result(
            self.p.store, clock=self.p.clock, calc_version=cv, inputs={"a": 2},
            policy_versions=["pv_x"], policy_value={"value": 3}, identity_rule_version=rule.id,
            model_version=mv.id, comparison_spec=cs.id, scenario_id=None)
        for key in ("calculation_version", "policy_versions", "identity_rule_version",
                    "model_version", "comparison_specification_version", "inputs"):
            self.assertIn(key, pkg.refs)
        self.assertEqual(pkg.refs["calculation_version"], cv.id)
        self.assertEqual(pkg.refs["model_version"], mv.id)
        self.assertTrue(pkg.output_reference.startswith("sha256:"))

    def test_42_replay_reproduces_the_same_output(self):
        cf = self.p.calc_family()
        cv = self.p.calc_version(cf.id, "1.0.0")
        out, pkg = calc.issue_result(self.p.store, clock=self.p.clock, calc_version=cv,
                                     inputs={"a": 7}, policy_versions=[], policy_value={"value": 4})
        replayed, ok = calc.replay(self.p.store, pkg.id)
        self.assertTrue(ok)
        self.assertEqual(replayed, out)

    def test_43_version_change_is_traceable(self):
        cf = self.p.calc_family()
        v1 = self.p.calc_version(cf.id, "1.0.0")
        v2 = self.p.calc_version(cf.id, "2.0.0")
        versions.activate_calc_version(self.p.store, v1.id, v1.version, actor=self.p.owner)
        v2 = self.p.store.get_calc_version(v2.id)
        versions.activate_calc_version(self.p.store, v2.id, v2.version, actor=self.p.owner)
        v2 = self.p.store.get_calc_version(v2.id)
        versions.rollback_calc_version(self.p.store, from_id=v2.id, from_expected=v2.version,
                                       to_id=v1.id, actor=self.p.owner)
        # activation + rollback histories together reconstruct what was in force when
        acts = self.p.store.activation_history(v1.id) + self.p.store.activation_history(v2.id)
        self.assertGreaterEqual(len(acts), 2)
        self.assertEqual(len(self.p.store.rollback_history("calculation_version")), 1)


if __name__ == "__main__":
    unittest.main()
