"""Native in-context Bench: bench a combination from Pipeline combination detail or a CPO row; benched =
no longer orderable -> removed from ordering feasibility (CPO + Pipeline) while history is preserved; a
benched combination with incoming supply stays visible (labelled) until that supply is managed; Restore
returns it to orderable. Certified plan is read-only."""
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


class TestBenchContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        st = NewInvStore(self.conn, self.p.clock)
        self._mk(st, "8501", "QBE", "G", acq=2, inc=0)      # QX65 — no incoming
        self._mk(st, "8481", "XKJ", "K", acq=1, inc=1)      # QX60 — has incoming
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _mk(self, st, code, ext, inte, *, acq, inc):
        cb = resolve_or_create_planning_combination(
            st, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="t")
        st.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": inc, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _cpo_rows(self):
        # count ordering rows for QX65 by the order-line action presence, ignoring flash text
        b = self.full.get("/ordering/cpo", month="2099-01").body   # a month with no flash
        return b

    def test_bench_button_present_in_context(self):
        self.assertIn("Bench", self.full.get("/ordering/cpo").body)
        pid = self.conn.execute("SELECT id FROM inventory_plan_result").fetchone()["id"]
        self.assertIn("Bench", self.full.get(f"/combination/{pid}").body)

    def test_bench_removes_from_ordering_and_pipeline(self):
        self.assertIn("QX65 8501 QBE/G", self.full.get("/").body)
        r = self.full.post("/bench", {"combo": "QX65 8501 QBE/G", "back": "/ordering/cpo"})
        self.assertEqual(r.status, 303)
        self.full.get("/ordering/cpo")                     # consume the flash
        self.assertNotIn("QX65 8501 QBE/G", self.full.get("/ordering/cpo").body)   # gone from ordering
        self.assertNotIn("QX65 8501 QBE/G", self.full.get("/").body)               # gone from pipeline (no incoming)

    def test_benched_with_incoming_stays_labelled(self):
        self.full.post("/bench", {"combo": "QX60 8481 XKJ/K", "back": "/"})
        self.full.get("/")                                 # consume flash
        home = self.full.get("/").body
        self.assertIn("QX60 8481 XKJ/K", home)             # kept while incoming needs management
        self.assertIn("No longer orderable", home)

    def test_restore_makes_orderable_again(self):
        self.full.post("/bench", {"combo": "QX65 8501 QBE/G", "back": "/ordering/cpo"})
        self.full.get("/")
        self.assertNotIn("QX65 8501 QBE/G", self.full.get("/ordering/cpo", month="2099-02").body)
        self.full.post("/data/bench/restore", {"combo": "QX65 8501 QBE/G"})
        self.full.get("/")
        self.assertIn("QX65 8501 QBE/G", self.full.get("/ordering/cpo", month="2099-03").body)

    def test_history_and_schema_preserved(self):
        before = self.conn.execute("SELECT COUNT(*) FROM inventory_plan_result WHERE store_scope=?",
                                   (SCOPE,)).fetchone()[0]
        self.full.post("/bench", {"combo": "QX65 8501 QBE/G", "back": "/"})
        # bench never mutates the certified plan records (history preserved) or the schema
        after = self.conn.execute("SELECT COUNT(*) FROM inventory_plan_result WHERE store_scope=?",
                                  (SCOPE,)).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(current_version(self.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
