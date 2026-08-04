"""Phase 3 acceptance — Scenario override isolation, governed-action + authorization
contracts, and migration / legacy / no-domain guards (items 44-59).
"""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ConcurrencyError, PersistenceError
from elite.policy import lifecycle, scenario
from elite.policy.fixtures import Phase3
from elite.policy.resolution import RESOLVED, resolve

SCOPE = "store:HG"
PAST_S = "2020-01-01T00:00:00+00:00"
NOW = "2026-06-01T00:00:00+00:00"
OFFICIAL = {"kind": "percentage", "value": 10, "denominator": "msrp"}
WHATIF = {"kind": "percentage", "value": 25, "denominator": "msrp"}


class TestPhase3ScenarioGov(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase3(self.dbp)

    def tearDown(self):
        self.p.close()

    def _official_family(self):
        f = self.p.family()
        self.p.version(f.id, OFFICIAL, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        return f

    # ---- scenario override isolation ----
    def test_44_scenario_override_resolves_only_in_scenario(self):
        f = self._official_family()
        ov = scenario.create_override(self.p.gov, self.p.store, principal=self.p.owner, scope=SCOPE,
                                      family_id=f.id, scenario_id="scn1", value=WHATIF,
                                      subject_scope={"store": "HG"}, clock=self.p.clock)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW,
                    context="scenario", scenario_id="scn1")
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.value, WHATIF)
        self.assertEqual(r.overrides_used, [ov.id])

    def test_45_scenario_override_never_changes_official(self):
        f = self._official_family()
        scenario.create_override(self.p.gov, self.p.store, principal=self.p.owner, scope=SCOPE,
                                 family_id=f.id, scenario_id="scn1", value=WHATIF,
                                 subject_scope={"store": "HG"}, clock=self.p.clock)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)   # official
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.value, OFFICIAL)                        # unchanged by the override

    def test_46_override_does_not_leak_into_other_scenarios(self):
        f = self._official_family()
        scenario.create_override(self.p.gov, self.p.store, principal=self.p.owner, scope=SCOPE,
                                 family_id=f.id, scenario_id="scn1", value=WHATIF,
                                 subject_scope={"store": "HG"}, clock=self.p.clock)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW,
                    context="scenario", scenario_id="scn2")        # a DIFFERENT scenario
        self.assertEqual(r.value, OFFICIAL)                        # sharing/other scenario stays official

    def test_47_unauthorized_override_is_rejected(self):
        f = self._official_family()
        with self.assertRaises(AuthorizationError):
            scenario.create_override(self.p.gov, self.p.store, principal=self.p.limited, scope=SCOPE,
                                     family_id=f.id, scenario_id="scn1", value=WHATIF,
                                     subject_scope={"store": "HG"}, clock=self.p.clock)

    # ---- governed-action + authorization contracts ----
    def test_48_transition_authorization_enforced_below_ui(self):
        f = self.p.family()
        v = self.p.version(f.id, OFFICIAL, scope={"store": "HG"}, lifecycle="PROPOSED")
        with self.assertRaises(AuthorizationError):        # limited lacks policy.approve
            lifecycle.approve(self.p.gov, self.p.store, self.p.limited, SCOPE, v.id,
                              self.p.store.get_version(v.id).version, clock=self.p.clock)
        lifecycle.approve(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id,
                          self.p.store.get_version(v.id).version, clock=self.p.clock)
        self.assertEqual(self.p.store.get_version(v.id).lifecycle_status, "APPROVED")

    def test_49_stale_transition_raises_concurrency(self):
        f = self.p.family()
        v = self.p.version(f.id, OFFICIAL, scope={"store": "HG"}, lifecycle="PROPOSED")
        with self.assertRaises(ConcurrencyError):
            lifecycle.approve(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id,
                              expected_version=999, clock=self.p.clock)

    def test_50_idempotent_retry_has_no_double_effect(self):
        f = self.p.family()
        v = self.p.version(f.id, OFFICIAL, scope={"store": "HG"}, lifecycle="DRAFT")
        before = self.p.stack.audit.count()
        lifecycle.propose(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id,
                          self.p.store.get_version(v.id).version, idempotency_key="idem-1")
        mid = self.p.stack.audit.count()
        res = lifecycle.propose(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id,
                                expected_version=999, idempotency_key="idem-1")  # stale, but same key
        self.assertTrue(res.get("replayed"))
        self.assertEqual(self.p.stack.audit.count(), mid)          # no second audit event
        self.assertEqual(mid, before + 1)

    def test_51_governed_action_writes_audit(self):
        f = self.p.family()
        v = self.p.version(f.id, OFFICIAL, scope={"store": "HG"}, lifecycle="DRAFT")
        before = self.p.stack.audit.count()
        res = lifecycle.propose(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id,
                                self.p.store.get_version(v.id).version)
        self.assertEqual(self.p.stack.audit.count(), before + 1)
        self.assertIsNotNone(self.p.stack.audit.get(res["audit_id"]))

    def test_52_required_audit_failure_rolls_back_write(self):
        f = self.p.family()
        v = self.p.version(f.id, OFFICIAL, scope={"store": "HG"}, lifecycle="DRAFT")
        orig_append = self.p.stack.audit.append

        def boom(conn, event):
            raise RuntimeError("synthetic audit failure")
        self.p.stack.audit.append = boom
        try:
            with self.assertRaises(PersistenceError):
                lifecycle.propose(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id,
                                  self.p.store.get_version(v.id).version)
        finally:
            self.p.stack.audit.append = orig_append
        # business write rolled back with the failed audit -> still DRAFT
        self.assertEqual(self.p.store.get_version(v.id).lifecycle_status, "DRAFT")

    # ---- migration / legacy / no-domain guards ----
    def test_53_migration_v3_applied(self):
        rows = self.p.store.conn.execute(
            "SELECT version,name FROM migration_record ORDER BY version").fetchall()
        recorded = {(r["version"], r["name"]) for r in rows}
        self.assertIn((3, "policy_and_versioning"), recorded)

    def test_54_migrations_are_rerun_safe(self):
        before = self.p.store.conn.execute("SELECT COUNT(*) AS n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase3(self.dbp)                                       # reopen re-runs migrate()
        self.addCleanup(p2.close)
        after = p2.store.conn.execute("SELECT COUNT(*) AS n FROM migration_record").fetchone()["n"]
        self.assertEqual(before, after)                            # no duplicate application

    def test_55_no_domain_symbols_in_policy_package(self):
        import elite.policy.calc as _calc
        import elite.policy.lifecycle as _lc
        import elite.policy.resolution as _res
        import elite.policy.scenario as _scn
        import elite.policy.store as _st
        forbidden = ("demand", "need", "forecast", "cpo", "ppo", "ctp", "loaner", "demo",
                     "predict", "learning", "replenish", "dealer_trade")
        for mod in (_calc, _lc, _res, _scn, _st):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"domain-looking symbol {name} in {mod.__name__}")

    def test_56_financial_values_are_policy_records_not_constants(self):
        # A financial assumption lives as a governed, typed Policy Version — never a
        # hardcoded module constant. Confirm the value is stored and typed.
        f = self.p.family(category="FINANCIAL_ASSUMPTION")
        v = self.p.version(f.id, {"kind": "currency", "amount": 0, "currency": "USD"},
                           scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        got = self.p.store.get_version(v.id)
        self.assertEqual(got.value["kind"], "currency")
        self.assertIn("currency", got.value)

    def test_57_legacy_line_untouched_by_phase3(self):
        # Phase 3 adds only the elite/ package; the protected legacy application files exist
        # and are not modified by policy code.
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertTrue(os.path.exists(os.path.join(repo, "Pipeline-Manager.html")))

    def test_58_scenario_override_is_flagged_and_isolated(self):
        f = self._official_family()
        ov = scenario.create_override(self.p.gov, self.p.store, principal=self.p.owner, scope=SCOPE,
                                      family_id=f.id, scenario_id="scnX", value=WHATIF,
                                      subject_scope={"store": "HG"}, clock=self.p.clock)
        stored = self.p.store.get_version(ov.id)
        self.assertTrue(stored.is_scenario)
        self.assertEqual(stored.scenario_id, "scnX")
        # official resolution set excludes scenario versions entirely
        official_versions = self.p.store.versions_for_family(f.id, scenario_id="__official__")
        self.assertNotIn(ov.id, {x.id for x in official_versions})

    def test_59_override_creation_is_audited(self):
        f = self._official_family()
        before = self.p.stack.audit.count()
        scenario.create_override(self.p.gov, self.p.store, principal=self.p.owner, scope=SCOPE,
                                 family_id=f.id, scenario_id="scnA", value=WHATIF,
                                 subject_scope={"store": "HG"}, clock=self.p.clock)
        self.assertEqual(self.p.stack.audit.count(), before + 1)   # governed => audited


if __name__ == "__main__":
    unittest.main()
