"""CPO workspace-state memory — the operator's last CPO working month is remembered per principal + store,
so leaving the page and returning restores the month instead of resetting to the default. This is presentation
state only: the resolved month is bound to the certified plan exactly as an explicit ?month always was, and no
certified calculation or ORDER-now quantity changes."""
import os
import re
import tempfile
import unittest

from elite.ui.fixtures import Phase10, OTHER_SCOPE
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult, InventoryPlanMonth
from elite.ids import new_id

# The Phase10 fixture clock is anchored in Jan 2026, so the default CPO month is January 2026 and the
# selector window is 2025-12 .. 2027-01.
DEFAULT_LABEL = "January 2026"
OCT, SEP = "2026-10", "2026-09"


def _cur(body):
    m = re.search(r'<span class="cur">([^<]+)</span>', body)
    return m.group(1) if m else None


class TestCpoMonthMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.full = self.p.login(self.p.op_full)                       # at SCOPE

    def tearDown(self):
        self.p.close()

    # 1. select October -> leave CPO -> return -> October is restored
    def test_select_month_is_remembered_across_navigation(self):
        self.full.get("/ordering/cpo", month=OCT)                      # select October
        self.full.get("/")                                             # navigate away
        b = self.full.get("/ordering/cpo").body                        # return with no ?month
        self.assertEqual(_cur(b), "October 2026")

    # 2. an explicit month overrides the remembered one and becomes the new remembered month
    def test_explicit_month_overrides_and_updates_memory(self):
        self.full.get("/ordering/cpo", month=OCT)                      # remembered = October
        b1 = self.full.get("/ordering/cpo", month=SEP).body            # explicit September overrides
        self.assertEqual(_cur(b1), "September 2026")
        b2 = self.full.get("/ordering/cpo").body                       # future return with no ?month
        self.assertEqual(_cur(b2), "September 2026")                   # now September, not October

    # 3. one store's remembered month cannot leak into another store
    def test_memory_is_store_scoped(self):
        self.full.get("/ordering/cpo", month=OCT)                      # SCOPE remembers October
        other = self.p.login(self.p.op_otherscope, OTHER_SCOPE)        # a different store
        b = other.get("/ordering/cpo").body
        # the selected (current) month is the default, NOT the other store's remembered October
        self.assertEqual(_cur(b), DEFAULT_LABEL)

    # 4. an invalid / out-of-window remembered month falls back safely to the default
    def test_invalid_remembered_month_falls_back(self):
        # plant a stale, out-of-window remembered month directly in the governed store
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", f"cpo_last_month::{self.p.op_full}", "2020-01")
        b = self.full.get("/ordering/cpo").body
        self.assertEqual(_cur(b), DEFAULT_LABEL)                       # safe fallback
        # an explicit out-of-window month also falls back rather than binding an impossible month
        b2 = self.full.get("/ordering/cpo", month="2099-05").body
        self.assertEqual(_cur(b2), DEFAULT_LABEL)

    # 5. certified month binding + ORDER-now math are unchanged by the memory layer
    def test_certified_binding_and_order_now_unchanged(self):
        store = NewInvStore(self.conn, self.p.clock)
        cb = resolve_or_create_planning_combination(
            store, self.p.clock, {"model_code": "8481", "exterior": "XKJ", "interior": "K"}, SCOPE, source_ref="t")
        mr = [InventoryPlanMonth(id=new_id("ipm"), plan_id="", month=OCT, expected_demand=1.0,
                                 cumulative_demand=1.0, cumulative_supply=0, shortage=3.0, excess=0.0,
                                 confidence="medium", seq=0)]
        store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 1, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 9, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=mr))
        # remembered-month render and explicit-month render bind the SAME certified board + ORDER-now
        self.full.get("/ordering/cpo", month=OCT)                      # remember October
        remembered = self.full.get("/ordering/cpo").body               # restored via memory
        explicit = self.full.get("/ordering/cpo", month=OCT).body      # bound via explicit ?month
        self.assertEqual(_cur(remembered), "October 2026")
        self.assertEqual(_cur(explicit), "October 2026")
        for body in (remembered, explicit):
            self.assertIn('<span class="rcall">ORDER 1</span>', body)  # certified discrete ORDER-now == 1
        self.assertEqual(current_version(self.conn), 12)               # schema untouched


if __name__ == "__main__":
    unittest.main(verbosity=2)
