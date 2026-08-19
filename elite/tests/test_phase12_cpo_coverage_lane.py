"""CPO coverage lane — the compact horizontal time/coverage context on each model workspace. It renders the
previous / selected / next relevant months around the selected one, showing model-level expected need vs the
certified supply position and the resulting coverage state, so the operator can SEE the shortage story before
opening any Why. It is pure presentation: values are summed straight from certified inventory_plan_month
rows (no recompute, no schema change), and the selected month binding is unchanged."""
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

AUG, SEP, OCT = "2026-08", "2026-09", "2026-10"


class TestCoverageLane(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.store = NewInvStore(self.conn, self.p.clock)
        # Two QX60 combinations, each with the SAME three planning months, so the lane must SUM them to the
        # model: Sep model need = 1+1 = 2, Sep model supply = 0+0 = 0, Sep model shortage = 2+1 = 3.
        self._plan("XKJ", "K", {AUG: (0.0, 2, 0.0), SEP: (2.0, 0, 0.0), OCT: (1.0, 1, 0.0)})
        self._plan("QBE", "G", {AUG: (0.0, 1, 0.0), SEP: (1.0, 0, 0.0), OCT: (0.0, 2, 0.0)})
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _plan(self, ext, inte, months):
        cb = resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": "8481", "exterior": ext, "interior": inte},
            SCOPE, source_ref="t")
        # months maps month -> (shortage, supply_position, excess); expected demand is 1.0 per combo per month.
        mrows = []
        for i, (m, (short, sup, exc)) in enumerate(sorted(months.items())):
            mrows.append(InventoryPlanMonth(id=new_id("ipm"), plan_id="", month=m, expected_demand=1.0,
                                            cumulative_demand=1.0, cumulative_supply=sup, shortage=short,
                                            excess=exc, confidence="medium", seq=i))
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 1, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 9, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=mrows))
        return cb

    def _body(self, month=SEP):
        return self.full.get("/ordering/cpo", month=month).body

    def test_lane_renders_surrounding_months(self):
        b = self._body(SEP)
        self.assertIn('class="covlane"', b)                 # the compact horizontal lane exists
        # previous / selected / next relevant months are all visible for context
        for lbl in ("Aug '26", "Sep '26", "Oct '26"):
            self.assertIn(lbl, b)

    def test_selected_month_is_central_and_highlighted(self):
        b = self._body(SEP)
        # the selected (Sep) cell carries the highlighted 'sel' class and is NOT a link (it is the centre)
        self.assertRegex(b, r'<div class="covcell [a-z]+ sel">\s*<span class="cm">Sep')
        # a surrounding month is a server-backed month link (lane doubles as navigation)
        self.assertIn(f'href="/ordering/cpo?month={OCT}"', b)

    def test_model_level_aggregation_and_state(self):
        b = self._body(SEP)
        # isolate the selected Sep cell and prove the certified rows were SUMMED to the model
        cell = re.search(r'<div class="covcell short sel">(.*?)</div>\s*(?:<a|<div class="covcell|</div>)',
                         b, re.S)
        self.assertIsNotNone(cell)
        seg = cell.group(1)
        self.assertIn("need 2", seg)          # 1 + 1 expected demand
        self.assertIn("have 0", seg)          # 0 + 0 supply position
        self.assertIn("Short 3", seg)         # 2 + 1 certified shortage -> exposed month
        self.assertIn("▲", seg)               # shortage glyph (text, not colour-only)

    def test_covered_and_state_by_month(self):
        b = self._body(SEP)
        # August is covered (no shortage/excess), rendered as a coverage state, not a shortage
        aug = re.search(r'>\s*<span class="cm">Aug[^<]*</span>(.*?)</(?:a|div)>', b, re.S)
        self.assertIsNotNone(aug)
        self.assertIn("Covered", aug.group(1))

    def test_lane_follows_month_binding(self):
        # selecting October re-centres the lane on October without any recompute
        b = self._body(OCT)
        self.assertRegex(b, r'<div class="covcell [a-z]+ sel">\s*<span class="cm">Oct')
        self.assertIn(f'href="/ordering/cpo?month={SEP}"', b)   # Sep now a neighbour link

    def test_presentation_only_certified_unchanged(self):
        self._body(SEP)
        self.assertEqual(current_version(self.conn), 12)
        # the certified discrete ORDER-now is still 1 for every rich card regardless of the month shortage
        for m in re.findall(r'<div class="call">ORDER (\d+)</div>', self._body(SEP)):
            self.assertEqual(m, "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
