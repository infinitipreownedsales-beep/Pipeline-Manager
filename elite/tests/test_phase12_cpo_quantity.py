"""CPO quantity workflow (Stage 5A/5C/5D adversarial). An ORDER-N > 1 must be impossible to miss, a partial
confirmation must leave the remainder as unresolved work, confirmation is idempotent, and confirming keeps
the operator's context (anchors back to the combination, not the top of the page)."""
import os
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


class TestCpoQuantity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.store = NewInvStore(self.conn, self.p.clock)
        self.cb = self._plan("8481", "QBE", "G", acquire=2)     # ORDER 2 VEHICLES
        self.full = self.p.login(self.p.op_full)
        self.combo = self.cb.id

    def tearDown(self):
        self.p.close()

    def _plan(self, code, ext, inte, *, acquire):
        cb = resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="t")
        mr = [InventoryPlanMonth(id=new_id("ipm"), plan_id="", month=M, expected_demand=2.0, cumulative_demand=2.0,
                                 cumulative_supply=0, shortage=2.0, excess=0.0, confidence="medium", seq=0)]
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 2.0}, need=2.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acquire, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": 2.0, "incoming_in_horizon": 0, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=mr))
        return cb

    def _body(self):
        return self.full.get("/ordering/cpo", month=M).body

    def _line(self, **form):
        form.setdefault("month", M)
        form.setdefault("combo", self.combo)
        return self.full.post("/ordering/cpo/line", form)

    def test_quantity_prominent(self):
        b = self._body()
        self.assertIn("ORDER 2 VEHICLES", b)             # impossible to miss
        self.assertIn("Confirm 2 ordered", b)            # action names the quantity

    def test_partial_leaves_remainder_unresolved(self):
        self._line(state="partial", qty="1", order="2")
        b = self._body()
        self.assertIn("1 OF 2 ORDERED", b)               # progress is explicit
        self.assertIn("1 left", b)
        self.assertNotIn("Worked — 1", b)                # NOT completed: remainder returns to the active queue
        self.assertIn("Confirm remaining 1", b)

    def test_full_confirm_resolves(self):
        self._line(state="confirmed", order="2")
        b = self._body()
        self.assertIn("Ordered 2 of 2", b)
        self.assertIn("Worked — 1", b)

    def test_partial_then_confirm_remaining(self):
        self._line(state="partial", qty="1", order="2")
        self._line(state="confirmed", order="2")
        b = self._body()
        self.assertIn("Ordered 2 of 2", b)
        self.assertIn("Worked — 1", b)

    def test_confirm_is_idempotent(self):
        self._line(state="confirmed", order="2")
        self._line(state="confirmed", order="2")         # double submit must not double-count
        b = self._body()
        self.assertEqual(b.count("Worked — 1"), 1)

    def test_partial_qty_at_or_above_order_is_full(self):
        self._line(state="partial", qty="2", order="2")  # k>=N is a full confirm, not a lingering partial
        b = self._body()
        self.assertIn("Ordered 2 of 2", b)

    def test_confirm_preserves_context_anchor(self):
        resp = self._line(state="confirmed", order="2")
        loc = dict(resp.headers).get("Location", "")
        self.assertIn(f"#combo-{self.combo}", loc)        # returns to the combination, not the page top

    def test_certified_unchanged(self):
        self._body()
        self.assertEqual(current_version(self.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
