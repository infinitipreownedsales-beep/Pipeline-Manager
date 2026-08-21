"""CPO workflow-first cockpit UX: recommendation cards (call is the hero), a per-model work summary,
resolved (confirmed / not-ordering) items visibly recede and sort below unresolved ones, and intentionally-
open capacity reads as a positive Elite restraint judgment. Presentation only — the certified board,
ranking, ORDER-now, endpoints and schema are unchanged."""
import os
import re
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult, InventoryPlanMonth
from elite.ids import new_id

M = "2026-09"


class TestCpoCockpit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.store = NewInvStore(self.conn, self.p.clock)
        self.a = self._plan("8481", "XKJ", "K", 3.0)   # ranks #1 (higher Sep shortage)
        self.b = self._plan("8481", "QBE", "G", 1.0)   # ranks #2
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _plan(self, code, ext, inte, sep_short):
        cb = resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="t")
        mr = [InventoryPlanMonth(id=new_id("ipm"), plan_id="", month=M, expected_demand=1.0, cumulative_demand=1.0,
                                 cumulative_supply=0, shortage=sep_short, excess=0.0, confidence="medium", seq=0)]
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 1, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 9, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=mr))
        return cb

    def _body(self):
        return self.full.get("/ordering/cpo", month=M).body

    def test_hero_work_summary_present(self):
        b = self._body()
        self.assertIn('class="metric', b)
        for label in ("Recommended", "Worked", "Remaining", "Allocation ceiling"):
            self.assertIn(label, b)
        self.assertIn("reviewed", b)                       # work-progress indicator
        self.assertIn('class="recrow', b)                  # uniform recommendation rows, not a table
        self.assertIn('<span class="rcall">ORDER 1 VEHICLE</span>', b)  # the call names the quantity at every rank

    def test_resolved_cards_recede_and_sort_below_unresolved(self):
        # confirm the #1 (QX60 8481 XKJ/K) -> it leaves the active queue and collapses into the receded,
        # still-undoable Worked group, below the unresolved #2
        combo_a = self.conn.execute("SELECT id FROM sellable_combination WHERE canonical_identity LIKE ?",
                                    ("%model_code=8481|exterior=XKJ|interior=K",)).fetchone()["id"]
        self.full.post("/ordering/cpo/line", {"month": M, "combo": combo_a, "state": "confirmed"})
        b = self._body()
        self.assertIn("Ordered 1 of 1", b)                 # status chip names the quantity ordered
        self.assertIn("Worked —", b)                       # handled items collapse into a receded group
        self.assertIn("recrow resolved", b)                # the worked item recedes (compact, receded row)
        self.assertIn("Undo", b)                           # completed item remains undoable
        # unresolved QBE/G (active queue) appears before the resolved XKJ/K (Worked group)
        self.assertLess(b.index("QX60 8481 QBE/G"), b.index("QX60 8481 XKJ/K"))

    def test_intentionally_open_reads_as_restraint(self):
        self.full.post("/ordering/cpo/allocation", {"month": M, "alloc_QX60": "5"})   # ceiling 5, only 2 justified
        b = self._body()
        self.assertIn("restraint", b)                      # positive Elite judgment styling/label
        self.assertIn("open on purpose", b)
        self.assertIn("Why open", b)
        self.assertIn("not unfinished work", b)   # explicitly framed as intentional, not incomplete

    def test_presentation_only_certified_unchanged(self):
        self._body()
        self.assertEqual(current_version(self.conn), 12)
        # ORDER-now stays certified 1 for every uniform row regardless of month shortage
        calls = re.findall(r'<span class="rcall">ORDER (\d+) VEHICLE', self._body())
        self.assertTrue(calls)
        for m in calls:
            self.assertEqual(m, "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
