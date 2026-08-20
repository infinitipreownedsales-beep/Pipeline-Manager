"""CPO month-binding at the REAL browser/route level (not only direct helper calls).

Reproduces the actual operator path: render /ordering/cpo, read the month <form> exactly as a browser would
(its action, method, <select name="month"> options, and a usable/visible submit control), then issue the GET
the browser builds from choosing an option — and prove the selected month rebinds the header, the
Relevant-Future column, the ranking inputs, and that ORDER-now stays the certified action. This guards the
live regression where the selector displayed a month but the board stayed on the default month.
"""
import os
import re
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult, InventoryPlanMonth
from elite.ids import new_id

NEAR = "2026-09"
FAR = "2027-01"     # farthest month inside the selector's option window for the fixture clock (Jan 2026)


class TestCpoMonthRoute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.store = NewInvStore(self.conn, self.p.clock)
        # Two QX60 combos whose month-phased shortage ordering flips between NEAR and FAR.
        self._plan("8481", "XKJ", "K", {NEAR: (3.0, 0), "2026-10": (2.0, 1), FAR: (1.0, 2)})
        self._plan("8481", "QBE", "G", {NEAR: (0.0, 5), "2026-10": (1.0, 5), FAR: (9.0, 5)})
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _plan(self, code, ext, inte, months):
        cb = resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="t")
        mrows = [InventoryPlanMonth(id=new_id("ipm"), plan_id="", month=m, expected_demand=1.0,
                                    cumulative_demand=1.0, cumulative_supply=sup, shortage=short, excess=0.0,
                                    confidence="medium", seq=i)
                 for i, (m, (short, sup)) in enumerate(sorted(months.items()))]
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 1, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 9, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=mrows))

    def _month_form(self, body):
        """Extract the month <form> exactly as a browser sees it: (action, method, {option_value},
        has_visible_submit)."""
        m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', body, re.S)
        # find the specific form that owns <select name="month">
        for fm in re.finditer(r'<form([^>]*)>(.*?)</form>', body, re.S):
            attrs, inner = fm.group(1), fm.group(2)
            if 'name="month"' in inner and "/ordering/cpo" in attrs:
                action = re.search(r'action="([^"]*)"', attrs).group(1)
                method = (re.search(r'method="([^"]*)"', attrs) or [None, "get"])[1]
                opts = set(re.findall(r'<option value="([^"]*)"', inner))
                # a submit button that is NOT hidden inside <noscript>
                inner_no_noscript = re.sub(r'<noscript>.*?</noscript>', '', inner, flags=re.S)
                has_visible_submit = bool(re.search(r'<button[^>]*type=submit', inner_no_noscript))
                return action, method.lower(), opts, has_visible_submit
        return None

    def _select_month(self, month):
        """Simulate the browser submitting the month form with `month` chosen from its own options."""
        body = self.full.get("/ordering/cpo").body
        form = self._month_form(body)
        self.assertIsNotNone(form, "month form not found")
        action, method, opts, has_visible_submit = form
        self.assertEqual(action, "/ordering/cpo")
        self.assertEqual(method, "get")
        self.assertTrue(has_visible_submit, "month form has no visible submit control (Remote Desktop dead-end)")
        self.assertIn(month, opts, f"{month} is not a selectable option")
        return self.full.get(action.lstrip("/") and action or "/ordering/cpo", month=month).body

    # 1 + 2. selecting a near and a far month yields that operative month in the rendered page
    def _mlabel(self, ym):
        from elite.ui.views.operator import _month_label
        return _month_label(ym)

    def test_selection_binds_operative_month(self):
        near = self._select_month(NEAR)
        self.assertIn(f'<span class="cur">{self._mlabel(NEAR)}</span>', near)   # current-month context chip
        far = self._select_month(FAR)
        self.assertIn(f'<span class="cur">{self._mlabel(FAR)}</span>', far)
        self.assertNotIn(f'<span class="cur">{self._mlabel("2026-01")}</span>', far)  # not stuck on default month

    # 3. the selected canonical month drives the per-recommendation Relevant-Future ("By <month>")
    def test_relevant_future_tracks_month(self):
        self.assertIn(f"By {NEAR}", self._select_month(NEAR))
        self.assertIn(f"By {FAR}", self._select_month(FAR))

    # 4. underlying month-plan inputs change the board when source rows differ (ranking flips)
    def test_board_inputs_change_with_month(self):
        def first_combo(body):
            return re.search(r'/combination/[^"?]+\?month=[^"]*">([^<]+)</a>', body).group(1)
        self.assertEqual(first_combo(self._select_month(NEAR)), "QX60 8481 XKJ/K")   # short 3.0 in Sep
        self.assertEqual(first_combo(self._select_month(FAR)), "QX60 8481 QBE/G")     # short 9.0 by Jan

    # 5. switching back is deterministic
    def test_round_trip_deterministic(self):
        a = self._select_month(NEAR)
        self._select_month(FAR)
        b = self._select_month(NEAR)
        self.assertEqual(a, b)

    # 6. ORDER-now stays the certified discrete action; later shortage is not converted to an order quantity
    def test_order_now_is_certified(self):
        far = self._select_month(FAR)
        # locate the QBE/G uniform row and read its ORDER call (worst month shortage is 9). In the recrow the
        # call precedes the identity, and both live in the SAME row (no intervening 'recrow').
        card = re.search(r'<span class="rcall">ORDER (\d+)</span>(?:(?!recrow).)*?QX60 8481 QBE/G', far, re.S)
        self.assertIsNotNone(card)
        self.assertEqual(card.group(1), "1")               # certified acquire_units, not the month shortage

    # 7. the primary month navigation is deterministic server-backed prev/next LINKS carrying ?month=
    def test_month_nav_links_are_server_backed(self):
        body = self.full.get("/ordering/cpo", month="2026-10").body
        self.assertIn('href="/ordering/cpo?month=2026-09"', body)   # prev
        self.assertIn('href="/ordering/cpo?month=2026-11"', body)   # next
        # following the next link binds that month (no JS / form submit needed)
        self.assertIn(self._mlabel("2026-11"), self.full.get("/ordering/cpo", month="2026-11").body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
