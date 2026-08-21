"""Sequential Service-Loaner placement optimizer (Stage 2/6). Proves placement recomputes Retail coverage
after each pick (sequential != static top-N), never places into a Retail shortage, returns the remaining
unmet requirement to ORDER, and keeps economics PROVISIONAL until the write-down treatment is governed."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_optimizer import (optimize_sl_placement, OPS_SAFE, DO_NOT_PLACE, ECON_RECOMMENDED,
                                       WRITEDOWN_TREATMENT_CERTIFIED)


def _row(stock, model_code, model, ext="QBE", inte="G", dis=120, status="in stock", year="2026"):
    return {"stock_number": stock, "model_code": model_code, "model": model, "exterior": ext, "interior": inte,
            "dis": dis, "status": status, "source_stage": "DLR-INV", "year": year}


class TestSequential(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app

    def tearDown(self):
        self.p.close()

    def _harm(self, excess):
        # one combination, `excess` surplus units certified
        from elite.newinv.dms_identity import dms_planning_identity
        combo = dms_planning_identity({"model_code": "84A", "exterior": "QBE", "interior": "G"})
        return {combo: {"state": "EXCESS" if excess > 0 else "COVERED", "excess": excess, "acquire": 0}}

    def _run(self, rows, harm, n):
        with patch("elite.loaner.sl_optimizer.read_new_retail_units", return_value=rows), \
             patch("elite.loaner.sl_optimizer.certified_harm_index", return_value=harm), \
             patch("elite.loaner.sl_optimizer._eligible", return_value=True), \
             patch("elite.loaner.sl_optimizer._gross_by_model", return_value={}):
            return optimize_sl_placement(self.app, SCOPE, "2026-01", n)

    def test_sequential_caps_at_surplus_not_request(self):
        # 3 physical units in ONE combo with only 2 surplus; ask for 3 -> place 2, 3rd is DO NOT PLACE
        rows = [_row("A", "84A", "QX60"), _row("B", "84A", "QX60"), _row("C", "84A", "QX60")]
        res = self._run(rows, self._harm(2), n=3)
        self.assertEqual(res["placed"], 2)                    # sequential recompute stops at real surplus
        self.assertEqual(res["remaining_to_order"], 1)        # the shortfall becomes an ORDER obligation
        self.assertTrue(res["sequential_diverges_from_static"])   # a naive top-3 would have over-placed
        dnp = [x for x in res["rejected"] if x["outcome"] == DO_NOT_PLACE]
        self.assertEqual(len(dnp), 1)

    def test_all_placeable_when_surplus_covers(self):
        rows = [_row("A", "84A", "QX60"), _row("B", "84A", "QX60")]
        res = self._run(rows, self._harm(3), n=2)
        self.assertEqual(res["placed"], 2)
        self.assertEqual(res["remaining_to_order"], 0)
        self.assertFalse(res["sequential_diverges_from_static"])

    def test_second_step_retail_after_reflects_recompute(self):
        rows = [_row("A", "84A", "QX60"), _row("B", "84A", "QX60")]
        res = self._run(rows, self._harm(2), n=2)
        self.assertEqual([s.retail_after for s in res["steps"]], ["EXCESS", "COVERED"])  # coverage drops as we pull

    def test_economics_stay_provisional_never_certified(self):
        rows = [_row("A", "84A", "QX60")]
        res = self._run(rows, self._harm(1), n=1)
        self.assertFalse(WRITEDOWN_TREATMENT_CERTIFIED)       # write-down treatment governance-required
        self.assertFalse(res["economics_certifiable"])
        self.assertTrue(all(s.provisional for s in res["steps"]))
        self.assertTrue(all(s.outcome != ECON_RECOMMENDED for s in res["steps"]))  # certified outcome unreachable
        self.assertTrue(all(s.outcome == OPS_SAFE for s in res["steps"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
