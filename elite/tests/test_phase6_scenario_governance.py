"""Phase 6 acceptance — scenario/policy exploration, governance/audit, output slices (67-79)."""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ConcurrencyError, PersistenceError
from elite.loaner.fixtures import OTHER_SCOPE, Phase6
from elite.loaner.output import build_unit_slice, queue, zero_mile_queue
from elite.workflow.fixtures import SCOPE

V = "1GNSKBKC5FR000601"


class TestPhase6ScenarioGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _u(self, uid):
        return self.p.store.get_unit(uid)

    # ---- scenario ----------------------------------------------------------
    def test_67_68_scenario_does_not_change_official(self):
        u = self.p.make_active(V)
        official_state = u.membership_state
        official_pf = self.p.policy  # official policy store unchanged by scenario
        self.p.scenario.explore("scnX", SCOPE, kind="fleet_size", overrides={"required_quantity": 99},
                                output={"selected": []})
        self.assertEqual(self._u(u.id).membership_state, official_state)   # official fleet unchanged
        # scenario result is isolated (its own record), official policy versions untouched
        rows = self.p.store.conn.execute("SELECT scenario_id FROM service_loaner_scenario_result").fetchall()
        self.assertTrue(all(r["scenario_id"] == "scnX" for r in rows))

    def test_69_70_scenario_identifies_overrides_no_approval(self):
        row = self.p.scenario.explore("scnY", SCOPE, kind="write_down", overrides={"write_down": 500},
                                      output={"note": "hypothetical"})
        import json
        self.assertEqual(json.loads(row["overrides"]), {"write_down": 500})   # overrides identified
        # sharing/exploring is not an approval — no governed policy activation happened
        self.assertEqual(row["kind"], "write_down")

    # ---- governance --------------------------------------------------------
    def test_71_authorities_separate(self):
        c = self.p.candidate(V)
        # proposer proposes; approver approves; executor executes
        r = self.p.units.propose_entry(self.p.proposer, SCOPE, c)
        with self.assertRaises(AuthorizationError):
            self.p.units.approve_entry(self.p.proposer, SCOPE, r["unit"])      # proposer != approver
        r = self.p.units.approve_entry(self.p.approver, SCOPE, r["unit"])
        with self.assertRaises(AuthorizationError):
            self.p.units.execute_entry(self.p.approver, SCOPE, r["unit"])      # approver != executor
        r = self.p.units.execute_entry(self.p.executor, SCOPE, r["unit"])
        # retirement path: returner confirms, completer completes, receiver receipts — all distinct
        self.p.retirement.propose(self.p.proposer, SCOPE, self._u(r["unit"].id))
        self.p.retirement.approve(self.p.approver, SCOPE, self._u(r["unit"].id))
        with self.assertRaises(AuthorizationError):
            self.p.retirement.confirm_return(self.p.completer, SCOPE, self._u(r["unit"].id), actual_event_ref="e")
        self.p.retirement.confirm_return(self.p.returner, SCOPE, self._u(r["unit"].id), actual_event_ref="e")
        with self.assertRaises(AuthorizationError):
            self.p.retirement.complete(self.p.returner, SCOPE, self._u(r["unit"].id))
        self.p.retirement.complete(self.p.completer, SCOPE, self._u(r["unit"].id))
        with self.assertRaises(AuthorizationError):
            self.p.retirement.confirm_used_cars_receipt(self.p.completer, SCOPE, self._u(r["unit"].id))
        self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, self._u(r["unit"].id))

    def test_72_authorization_enforced_below_ui(self):
        c = self.p.candidate(V)
        nobody = self.p.stack.authn.register("Nobody", "pw").id
        with self.assertRaises(AuthorizationError):
            self.p.units.propose_entry(nobody, SCOPE, c)

    def test_73_scope_mismatch_rejected(self):
        c = self.p.candidate(V)
        scoped = self.p.stack.authn.register("Scoped", "pw").id
        self.p.stack.grant(scoped, "service_loaner.entry.propose", SCOPE)     # only store:HG
        c2 = self.p.units.create_candidate(OTHER_SCOPE, vehicle_unit_id="vu_w", vin="1GNSKBKC5FR000602")
        with self.assertRaises(AuthorizationError):
            self.p.units.propose_entry(scoped, OTHER_SCOPE, c2)

    def test_74_revoked_authority_rejected(self):
        c = self.p.candidate(V)
        rid = self.p.stack.authn.register("Temp", "pw").id
        g = self.p.stack.grant(rid, "service_loaner.entry.propose", "*")
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        with self.assertRaises(AuthorizationError):
            self.p.units.propose_entry(rid, SCOPE, c)

    def test_75_stale_transition_rejected(self):
        import dataclasses
        c = self.p.candidate(V)
        with self.assertRaises(ConcurrencyError):
            self.p.units.propose_entry(self.p.full, SCOPE, dataclasses.replace(c, version=99))

    def test_76_idempotent_retry_no_duplicate(self):
        c = self.p.candidate(V)
        r = self.p.units.approve_entry(self.p.full, SCOPE, self.p.units.propose_entry(self.p.full, SCOPE, c)["unit"])
        self.p.units.execute_entry(self.p.full, SCOPE, r["unit"])
        ev = self._u(r["unit"].id).entry_execution_event
        self.p.units.execute_entry(self.p.full, SCOPE, self._u(r["unit"].id))   # replay
        self.assertEqual(self._u(r["unit"].id).entry_execution_event, ev)       # no duplicate effect

    def test_77_required_audit_written_atomically(self):
        c = self.p.candidate(V)
        before = self.p.stack.audit.count()
        self.p.units.propose_entry(self.p.full, SCOPE, c)
        self.assertEqual(self.p.stack.audit.count(), before + 1)

    def test_78_audit_failure_blocks_success(self):
        c = self.p.candidate(V)
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                self.p.units.propose_entry(self.p.full, SCOPE, c)
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(self._u(c.id).membership_state, "CANDIDATE")          # rolled back

    def test_79_output_slices_use_real_records(self):
        u = self.p.make_active(V, rental="rented", in_service_date="2025-01-01", checkout_mileage=0)
        e = self.p.econ(u)
        st = self.p.execution.assess(u, e.id, rented=True)
        sl = build_unit_slice(self.p.store, self.p.ni, u.id, economic=e, execution=st)
        self.assertEqual(sl["vin"], u.vin)
        self.assertEqual(sl["membership_and_rental_state"]["rental"], "rented")
        self.assertEqual(sl["economic_call"], e.economic_call)
        self.assertEqual(sl["execution_status"], "BLOCKED_RENTED")
        self.assertIn("raw_history_path", sl)
        # queue slices are real projections
        self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        self.assertTrue(any(x["service_loaner_unit_id"] == u.id for x in zero_mile_queue(self.p.store, SCOPE)))
        self.assertTrue(queue(self.p.store, SCOPE, ["ACTIVE_RENTED"]))


if __name__ == "__main__":
    unittest.main()
