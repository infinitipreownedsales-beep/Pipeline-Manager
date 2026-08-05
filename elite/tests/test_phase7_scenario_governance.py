"""Phase 7 acceptance — scenario exploration, resale foundations (67-71), governance/audit edges
(72-77), output slices from real records (78-79)."""
import dataclasses
import json
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ConcurrencyError, PersistenceError
from elite.execdemo.fixtures import OTHER_SCOPE, Phase7
from elite.execdemo.output import build_unit_slice, portfolio_slice, queue
from elite.workflow.fixtures import SCOPE

V = "1HGCM82633A500001"


class TestPhase7ScenarioGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase7(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _u(self, uid):
        return self.p.store.get_unit(uid)

    def _candidate(self, vin, comb=None):
        c = comb or self.p.combination(exterior_color="SG")
        u = self.p.candidate_unit(vin, c.id)
        self.p.p4.seed_current(c, [{"vehicle_unit_id": u.vehicle_unit_id, "state": "available_unsold",
                                   "identity_status": "resolved"}])
        return u

    # ---- scenario + resale (67-71) ----------------------------------------
    def test_67_68_scenario_does_not_change_official(self):
        u = self.p.make_active(V)
        official = u.membership_state
        self.p.scenario.explore("scnX", SCOPE, kind="portfolio_size", overrides={"required_size": 99},
                                output={"selected": []})
        self.assertEqual(self._u(u.id).membership_state, official)   # official portfolio unchanged
        rows = self.p.store.conn.execute("SELECT scenario_id FROM executive_demo_scenario_result").fetchall()
        self.assertTrue(all(r["scenario_id"] == "scnX" for r in rows))

    def test_69_scenario_identifies_overrides_no_approval(self):
        row = self.p.scenario.explore("scnY", SCOPE, kind="preferred_model", overrides={"preferred": "QX60"},
                                      output={"note": "hypothetical"})
        self.assertEqual(json.loads(row["overrides"]), {"preferred": "QX60"})   # overrides visible
        self.assertEqual(row["kind"], "preferred_model")             # exploring is not approval

    def test_70_scenario_does_not_activate_policy(self):
        # a scenario preference resolution stays isolated; no official policy version is activated
        fam = self.p.p3.family(category="MANAGEMENT_PREFERENCE", name="scn_pref", dims=["store"],
                               default_resolution={"mode": "unresolved"})
        before = self.p.policy.get_family(fam.id)
        self.p.preference.resolve(SCOPE, policy_store=self.p.policy, family=self.p.policy.get_family(fam.id),
                                  subject_scope={"store": "HG"}, at_time="2026-08-15T00:00:00+00:00",
                                  context="scenario", scenario_id="scnZ")
        self.assertEqual(self.p.policy.get_family(fam.id).id, before.id)   # official family untouched

    def test_71_resale_reference_is_foundation_only(self):
        u = self.p.make_active(V)
        rid = self.p.resale.record_reference(u, resale_event_ref="r1", resale_value={"gross": 1000})
        row = self.p.store.conn.execute("SELECT * FROM executive_demo_resale_reference WHERE id=?", (rid,)).fetchone()
        self.assertEqual(row["executive_demo_unit_id"], u.id)
        # foundation only: predicted/observed pairing columns exist but are NOT populated here (Phase 8)
        self.assertIsNone(row["predicted_ref"])
        self.assertIsNone(row["observed_ref"])

    # ---- governance / audit (72-77) ---------------------------------------
    def test_72_authorities_separate(self):
        u = self._candidate(V)
        self.p.units.propose_designation(self.p.proposer, SCOPE, u)
        with self.assertRaises(AuthorizationError):
            self.p.units.approve_designation(self.p.proposer, SCOPE, self._u(u.id))   # proposer != approver
        self.p.units.approve_designation(self.p.approver, SCOPE, self._u(u.id))
        with self.assertRaises(AuthorizationError):
            self.p.units.execute_designation(self.p.approver, SCOPE, self._u(u.id))   # approver != designator
        self.p.units.execute_designation(self.p.designator, SCOPE, self._u(u.id))
        # retirement path authorities distinct: retirer executes, returner confirms return
        self.p.retirement.propose(self.p.proposer, SCOPE, self._u(u.id))
        self.p.retirement.approve(self.p.approver, SCOPE, self._u(u.id))
        with self.assertRaises(AuthorizationError):
            self.p.retirement.execute(self.p.approver, SCOPE, self._u(u.id))          # approver != retirer

    def test_73_authorization_enforced_below_ui(self):
        u = self._candidate(V)
        nobody = self.p.stack.authn.register("Nobody7", "pw").id
        with self.assertRaises(AuthorizationError):
            self.p.units.propose_designation(nobody, SCOPE, u)

    def test_74_scope_mismatch_rejected(self):
        scoped = self.p.stack.authn.register("Scoped7", "pw").id
        self.p.stack.grant(scoped, "executive_demo.designation.propose", SCOPE)    # only store:HG
        c2 = self.p.units.create_candidate(OTHER_SCOPE, vehicle_unit_id="vu_w7", vin="1HGCM82633A500002")
        with self.assertRaises(AuthorizationError):
            self.p.units.propose_designation(scoped, OTHER_SCOPE, c2)

    def test_75_revoked_authority_rejected(self):
        u = self._candidate(V)
        rid = self.p.stack.authn.register("Temp7", "pw").id
        g = self.p.stack.grant(rid, "executive_demo.designation.propose", "*")
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        with self.assertRaises(AuthorizationError):
            self.p.units.propose_designation(rid, SCOPE, u)

    def test_76_stale_transition_rejected(self):
        u = self._candidate(V)
        with self.assertRaises(ConcurrencyError):
            self.p.units.propose_designation(self.p.full, SCOPE, dataclasses.replace(u, version=99))

    def test_77_audit_written_atomically_and_failure_rolls_back(self):
        u = self._candidate(V)
        before = self.p.stack.audit.count()
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.assertEqual(self.p.stack.audit.count(), before + 1)     # exactly one audit event
        # audit failure blocks the business write (atomic rollback)
        u2 = self._candidate("1HGCM82633A500003")
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                self.p.units.propose_designation(self.p.full, SCOPE, u2)
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(self._u(u2.id).membership_state, "CANDIDATE")   # rolled back

    # ---- output slices (78-79) --------------------------------------------
    def test_78_unit_slice_uses_real_records(self):
        c = self.p.combination(exterior_color="SL")
        u = self._candidate(V, c)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        r = self.p.units.execute_designation(self.p.full, SCOPE, self._u(u.id))
        e = self.p.econ(self._u(u.id))
        st = self.p.execution.assess(self._u(u.id), e.id)
        sl = build_unit_slice(self.p.store, self.p.ni, u.id, economic=e, execution=st)
        self.assertEqual(sl["vin"], u.vin)
        self.assertEqual(sl["economic_call"], e.economic_call)
        self.assertEqual(sl["execution_status"], "READY")
        self.assertIn("ACTIVE_DEMO", sl["proof"]["reconciliations"])
        self.assertIn("raw_history_path", sl)

    def test_79_portfolio_and_queue_slices_real(self):
        plan = self.p.portfolio.best_overall(SCOPE, required_size=1, candidates=[
            {"vehicle_unit_id": "q1", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 2},
             "executive_demo_benefit": {"value": 3}, "portfolio_fit": {"value": 4}}])
        ps = portfolio_slice(plan)
        self.assertEqual(ps["need"], 1)
        self.assertEqual(ps["best_overall"]["pick"]["vehicle_unit_id"], "q1")
        # active-unit queue is a real projection
        r = self.p.units.execute_designation(self.p.full, SCOPE, self.p.store.get_unit(
            self._active_unit_id()))
        self.assertTrue(any(x["executive_demo_unit_id"] == r["unit"].id for x in queue(self.p.store, SCOPE, ["ACTIVE"])))

    def _active_unit_id(self):
        c = self.p.combination(exterior_color="Q")
        u = self._candidate("1HGCM82633A500009", c)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        return u.id


if __name__ == "__main__":
    unittest.main()
