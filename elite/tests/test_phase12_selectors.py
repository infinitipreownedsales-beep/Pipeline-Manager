"""Selector-first usability: where Elite can enumerate valid values, forms present a selector/picker
(month picker, model/combination/VIN selector, searchable canonical datalist) rather than free text."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id


class TestSelectors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        st = NewInvStore(self.p.stack.db.conn, self.p.clock)
        for code, ext, inte, acq, exc in [("8501", "QBE", "G", 2, 0), ("8481", "XKJ", "K", 0, 3)]:
            cb = resolve_or_create_planning_combination(
                st, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="t")
            st.add_plan(InventoryPlanResult(
                id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
                expected_demand=0.0, current_supply=1, future_supply=0, committed_supply=0, qualifying_supply=1,
                desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=float(exc), confidence="medium",
                evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": exc,
                                                     "incoming_excess": 0, "target_level": 1.6,
                                                     "incoming_in_horizon": 0, "dts_burden": 1.0}},
                policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
                status="issued", months=[]))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_cpo_month_is_picker(self):
        b = self.full.get("/ordering/cpo").body
        self.assertIn('<select name="month"', b)
        self.assertIn("August 2026", b)                       # month/year labels, not YYYY-MM typing
        self.assertNotIn('name=month value="" placeholder="YYYY-MM"', b)   # old free-text field gone

    def test_ppo_window_and_combo_are_selectors(self):
        self.full.post("/ordering/ppo/new", {"month": "2026-08"})
        b = self.full.get("/ordering/ppo", window="August 2026 PPO").body
        self.assertIn('<select name="window"', b)              # existing windows selectable
        self.assertIn('list="ppo_combos"', b)                  # searchable canonical combination selector
        self.assertIn("QX65 8501 QBE/G", b)                    # canonical values enumerated as options

    def test_data_uses_selectors(self):
        b = self.full.get("/data").body
        self.assertIn('<select name="combo"', b)               # bench = combination selector
        self.assertIn('list="un_vins"', b)                     # unavailable VIN selector
        self.assertIn('<select name="eff"', b)                 # effective month picker
        self.assertIn('<select name="model"', b)               # ICV/Velocity model selector
        self.assertIn('type=date', b)                          # unavailable start = date control

    def test_dealer_trade_internal_is_selector(self):
        b = self.full.get("/dealer-trade").body
        self.assertIn('list="their_req_combos"', b)            # our-inventory request = canonical selector
        self.assertIn("QX65 8501 QBE/G", b)

    def test_demos_prefs_and_vin_selectors(self):
        b = self.full.get("/demos").body
        self.assertIn('<select name="model_pref"', b)          # model preference selector
        # create a user, open detail, assign VIN via selector
        self.full.post("/demos/user", {"name": "Sam", "model_pref": "QX60"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        d = self.full.get(f"/demos/user/{roster[0]['id']}").body
        self.assertIn('list="assign_vins"', d)                 # VIN selector on assignment

    def test_selector_posts_still_persist(self):
        # a month chosen from the picker still drives allocation persistence
        self.full.post("/ordering/cpo/allocation", {"month": "2026-08", "alloc_QX65": "3"})
        b = self.full.get("/ordering/cpo", month="2026-08").body
        # the CPO cockpit surfaces the saved ceiling as a metric and pre-fills the edit control with it
        self.assertIn("Allocation ceiling", b)
        self.assertIn('value="3"', b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
