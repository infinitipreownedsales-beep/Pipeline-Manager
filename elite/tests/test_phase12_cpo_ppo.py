"""CPO + PPO functional operator workflows + clickable combination detail. Persistence is governed prefs
(no schema change); PPO Firm never mutates authoritative inventory; certified board is read, not recomputed."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id


def _combo(store, clock, code, ext, inte):
    return resolve_or_create_planning_combination(
        store, clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="cpo-test")


def _persist(store, comb, *, current, acquire):
    store.add_plan(InventoryPlanResult(
        id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
        expected_demand=0.0, current_supply=current, future_supply=0, committed_supply=0,
        qualifying_supply=current, desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=0.0,
        confidence="medium",
        evidence={"model": "time_phased_order_up_to",
                  "decision": {"acquire_units": acquire, "arrived_excess": 0, "incoming_excess": 0,
                               "target_level": 1.6, "breadth": "represented_by_velocity",
                               "evidence_level": "model_code", "credibility": {"credibility_z": 0.1},
                               "dts_burden": 1.0, "incoming_in_horizon": 1, "pending_timing": 0,
                               "monitor_months": []}},
        policy_versions=[], calculation_version="cv", reproducibility_package="rep",
        demand_result_id=None, status="issued", months=[]))


class TestCpoPpo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        store = NewInvStore(self.conn, self.p.clock)
        self.c1 = _combo(store, self.p.clock, "8501", "QBE", "G")   # QX65
        self.c2 = _combo(store, self.p.clock, "8481", "XKJ", "K")   # QX60
        _persist(store, self.c1, current=0, acquire=2)
        _persist(store, self.c2, current=1, acquire=3)
        self.full = self.p.login(self.p.op_full)
        self.m = self._month()

    def tearDown(self):
        self.p.close()

    def _month(self):
        from elite.clock import to_utc_iso
        return to_utc_iso(self.p.clock.now())[:7]

    def _plan_id(self, code):
        combo = self.conn.execute("SELECT id FROM sellable_combination WHERE canonical_identity LIKE ?",
                                  (f"%model_code={code}|%",)).fetchone()
        return self.conn.execute("SELECT id FROM inventory_plan_result WHERE combination_id=?",
                                 (combo["id"],)).fetchone()["id"]

    def test_cpo_renders_ranked_board(self):
        b = self.full.get("/ordering/cpo").body
        self.assertIn("CPO", b)
        self.assertIn("QX65 8501 QBE/G", b)
        self.assertIn("Confirm", b)
        self.assertIn("Not ordering", b)

    def test_allocation_persists(self):
        r = self.full.post("/ordering/cpo/allocation", {"month": self.m, "alloc_QX60": "8", "alloc_QX65": "5"})
        self.assertEqual(r.status, 303)
        b = self.full.get("/ordering/cpo", month=self.m).body
        self.assertIn('value="8"', b)
        self.assertIn("Allocation ceiling", b)

    def test_line_confirm_persists_and_reverts(self):
        combo_id = self.conn.execute("SELECT id FROM sellable_combination WHERE canonical_identity LIKE ?",
                                     ("%model_code=8501|%",)).fetchone()["id"]
        self.full.post("/ordering/cpo/line", {"month": self.m, "combo": combo_id, "state": "confirmed"})
        self.assertIn("Ordered", self.full.get("/ordering/cpo", month=self.m).body)   # quantity-named confirm chip
        self.full.post("/ordering/cpo/line", {"month": self.m, "combo": combo_id, "state": "clear"})
        self.assertNotIn("Ordered", self.full.get("/ordering/cpo", month=self.m).body)

    def test_open_capacity_when_allocation_exceeds_justified(self):
        # QX65 has 1 justified combo; allocate 4 -> 3 intentionally open with a Why
        self.full.post("/ordering/cpo/allocation", {"month": self.m, "alloc_QX65": "4"})
        b = self.full.get("/ordering/cpo", month=self.m).body
        self.assertIn("open on purpose", b)
        self.assertIn("Why open", b)

    def test_combination_detail_clickable(self):
        pid = self._plan_id("8501")
        b = self.full.get(f"/combination/{pid}").body
        self.assertIn("Recommendation", b)
        self.assertIn("Why", b)
        self.assertIn("Proof", b)
        self.assertIn("QX65 8501 QBE/G", b)
        self.assertIn(pid, b)

    def test_ppo_firm_does_not_mutate_inventory(self):
        before = self.conn.execute("SELECT COUNT(*) FROM vehicle_unit").fetchone()[0]
        self.full.get("/ordering/ppo", window="August PPO")
        self.full.post("/ordering/ppo/offer", {"window": "August PPO", "combo": "QX60 LUXE QBE/G",
                                               "decision": "FIRM"})
        b = self.full.get("/ordering/ppo", window="August PPO").body
        self.assertIn("QX60 LUXE QBE/G", b)
        self.assertIn("FIRM", b)
        self.assertIn("1 firmed", b)
        after = self.conn.execute("SELECT COUNT(*) FROM vehicle_unit").fetchone()[0]
        self.assertEqual(before, after)                 # simulated only; no authoritative mutation
        self.assertEqual(current_version(self.conn), 12)

    def test_ppo_revert(self):
        self.full.post("/ordering/ppo/offer", {"window": "W", "combo": "X", "decision": "FIRM"})
        self.full.post("/ordering/ppo/revert", {"window": "W"})
        self.assertIn("0 firmed", self.full.get("/ordering/ppo", window="W").body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
