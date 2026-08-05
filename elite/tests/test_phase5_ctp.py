"""Phase 5 acceptance — CTP workflow (items 37-44)."""
import inspect
import os
import tempfile
import unittest

from elite.errors import ValidationError
from elite.workflow.ctp import CtpService
from elite.workflow.fixtures import SCOPE, Phase5


class TestPhase5Ctp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))
        self.src, self.sd, _ = self.p.need_combo(exterior_color="SRC")
        self.dst, self.dd, _ = self.p.need_combo(exterior_color="DST")
        self.p.p4.seed_future(self.src, [{"production_order_id": "po_ctp", "arrival_month": "2026-10"}])
        self.ed = self.p.pipeline.assess_editability("po_ctp", SCOPE, "editable",
                                                     editable_dimensions=["exterior_color"])

    def tearDown(self):
        self.p.close()

    def _qual(self, comb):
        return len(self.p.supply.qualifying_supply(comb.id, SCOPE))

    def _propose(self, order="po_ctp"):
        return self.p.ctp.propose(self.p.full, SCOPE, production_order_id=order, original_combination_id=self.src.id,
                                  proposed_combination_id=self.dst.id, editability=self.ed,
                                  changes={"exterior_color": ("SRC", "DST")})

    def test_37_ctp_modifies_one_order_no_duplicate(self):
        w = self._propose()
        self.p.ctp.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.ctp.execute(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), proposed_combination_id=self.dst.id,
                           arrival_month="2026-10")
        # exactly one CURRENT future supply for the order, now under dst; original superseded (not a 2nd order)
        current = [fs for fs in self.p.ni.future_supply_for(self.dst.id, SCOPE) if fs.production_order_id == "po_ctp"]
        self.assertEqual(len(current), 1)
        allrows = self.p.wf.conn.execute("SELECT status FROM future_supply_projection WHERE production_order_id=?",
                                        ("po_ctp",)).fetchall()
        self.assertEqual(sorted(r["status"] for r in allrows), ["current", "superseded"])

    def test_38_unaccepted_ctp_does_not_replace_original_future_supply(self):
        w = self._propose()
        self.p.ctp.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))   # approved, NOT executed
        self.assertEqual(self._qual(self.src), 1)                  # original still authoritative
        self.assertEqual(self._qual(self.dst), 0)

    def test_39_accepted_ctp_preserves_original_order_history(self):
        w = self._propose()
        self.p.ctp.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.ctp.execute(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), proposed_combination_id=self.dst.id)
        superseded = self.p.wf.conn.execute("SELECT COUNT(*) n FROM future_supply_projection WHERE "
                                           "production_order_id=? AND status='superseded'", ("po_ctp",)).fetchone()["n"]
        self.assertEqual(superseded, 1)                            # prior-as-known preserved

    def test_40_rejected_ctp_leaves_order_unchanged(self):
        w = self._propose()
        self.p.ctp.reject(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.assertEqual(self._qual(self.src), 1)                  # original untouched
        self.assertEqual(self._qual(self.dst), 0)

    def test_41_non_editable_ctp_is_rejected(self):
        locked = self.p.pipeline.assess_editability("po_locked", SCOPE, "locked")
        with self.assertRaises(ValidationError):
            self.p.ctp.propose(self.p.full, SCOPE, production_order_id="po_locked", original_combination_id=self.src.id,
                               proposed_combination_id=self.dst.id, editability=locked)

    def test_42_ctp_consumes_need_excess_without_separate_demand(self):
        w = self.p.ctp.propose(self.p.full, SCOPE, production_order_id="po_ctp", original_combination_id=self.src.id,
                               proposed_combination_id=self.dst.id, editability=self.ed,
                               need_ref="need_dst", excess_ref="excess_src")
        self.assertEqual(w.originating_need_ref, "need_dst")
        self.assertEqual(w.evidence.get("excess_ref"), "excess_src")
        self.assertNotIn("monthly_expected", inspect.getsource(CtpService))   # no separate Demand

    def test_43_ctp_recomputes_both_combinations(self):
        before_src, before_dst = self._qual(self.src), self._qual(self.dst)
        w = self._propose()
        self.p.ctp.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.ctp.execute(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), proposed_combination_id=self.dst.id)
        self.assertEqual((before_src, before_dst), (1, 0))
        self.assertEqual((self._qual(self.src), self._qual(self.dst)), (0, 1))   # both change, counted once

    def test_44_replayed_accepted_ctp_does_not_apply_twice(self):
        w = self._propose()
        self.p.ctp.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.ctp.execute(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), proposed_combination_id=self.dst.id)
        r2 = self.p.ctp.execute(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), proposed_combination_id=self.dst.id)
        self.assertEqual(r2["outcome"], "DUPLICATE_REPLAY")
        self.assertEqual(self._qual(self.dst), 1)                  # still once


if __name__ == "__main__":
    unittest.main()
