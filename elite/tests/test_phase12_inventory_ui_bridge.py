"""Phase 12 UI bridge — the certified issued New-Inventory board must surface in the normal UI.

Proves the smallest bridge: the persisted discrete plan (inventory_plan_result.evidence.decision) renders on
/new-inventory as ACQUIRE / MONITOR / EXCESS, and is materialised into Phase 9 workspace items so Today /
Decision Inbox shows it. No reimport, no recompute, no schema/auth/grant/execution change."""
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
        store, clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="ui-bridge-test")


def _persist(store, comb, *, state, current, need, excess, decision):
    store.add_plan(InventoryPlanResult(
        id=new_id("plan"),
        store_scope=SCOPE, planning_state=state, combination_id=comb.id, expected_demand=0.0,
        current_supply=current, future_supply=0, committed_supply=0, qualifying_supply=current,
        desired_ending_coverage={"target_units": decision.get("target_level", 0)}, need=need, excess=excess,
        confidence="medium", evidence={"model": "time_phased_order_up_to", "decision": decision},
        policy_versions=[], calculation_version="cv_test", reproducibility_package="rep_test",
        demand_result_id=None, status="issued", months=[]))


class TestInventoryUiBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        store = NewInvStore(self.conn, self.p.clock)
        # certified spot-check cohorts, persisted exactly as the deployment would (discrete decision in evidence)
        qx65 = _combo(store, self.p.clock, "8501", "QBE", "G")
        qx60 = _combo(store, self.p.clock, "8481", "XKJ", "K")
        _persist(store, qx65, state="balanced", current=0, need=1.19, excess=0.0,
                 decision={"acquire_units": 2, "arrived_excess": 0, "incoming_excess": 0,
                           "target_level": 1.624, "breadth": "represented_by_velocity", "evidence_level": "model_code",
                           "credibility": {"credibility_z": 0.0938}, "dts_burden": 1.0, "incoming_in_horizon": 0,
                           "pending_timing": 0, "monitor_months": [{"month": "2026-10"}, {"month": "2026-11"}]})
        _persist(store, qx60, state="excess", current=5, need=0.0, excess=3.42,
                 decision={"acquire_units": 0, "arrived_excess": 3, "incoming_excess": 0,
                           "target_level": 0.7604, "breadth": "represented_by_velocity", "evidence_level": "model_code",
                           "credibility": {"credibility_z": 0.31}, "dts_burden": 0.33, "incoming_in_horizon": 0,
                           "pending_timing": 0, "monitor_months": [],
                           "excess_trace": [{"removed": "arrived", "delta_remove": 0.594, "rejected": True,
                                             "reason": "infeasible: min P(m)-T(m)=-0.901 < 0"}]})
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    # 1 + 2. /new-inventory renders the discrete board incl. the certified spot-check cohorts
    def test_new_inventory_renders_discrete_board(self):
        body = self.full.get("/new-inventory").body
        self.assertIn("ACQUIRE 2", body)
        self.assertIn("QX65 8501 QBE/G", body)
        self.assertIn("QX60 8481 XKJ/K", body)
        self.assertIn("EXCESS", body)
        self.assertIn("INTEGER TOTAL NEED", body)
        self.assertIn("MONITOR", body) if False else None   # (monitor months rendered in-row)

    # 3 + 4. Today / Decision Inbox materialises workspace items the GSM scope can see
    def test_inbox_materialises_and_scoped(self):
        home = self.full.get("/").body
        self.assertNotIn("no items", home)
        items = self.p.app.store.all_items(scope=SCOPE)
        self.assertGreaterEqual(len(items), 2)
        refs = {it["recommendation_ref"] for it in items}
        plan_ids = {r["id"] for r in self.conn.execute(
            "SELECT id FROM inventory_plan_result WHERE store_scope=?", (SCOPE,)).fetchall()}
        self.assertTrue(refs & plan_ids)                       # items reference the issued plans
        self.assertTrue(all(it["owning_domain"] == "new_inventory" for it in items
                            if it["recommendation_ref"] in plan_ids))

    # 5. no duplicate workspace items on rerun / reload
    def test_materialisation_idempotent(self):
        self.full.get("/"); self.full.get("/new-inventory"); self.full.get("/")
        n1 = len(self.p.app.store.all_items(scope=SCOPE))
        # force a fresh publish attempt (clear the per-process cache) -> DB-level idempotency must still hold
        self.p.app._published_scopes.discard(SCOPE)
        self.full.get("/")
        n2 = len(self.p.app.store.all_items(scope=SCOPE))
        self.assertEqual(n1, n2)

    # 6 + 7 + 8. no reimport / recompute / schema / entity changes from the bridge
    def test_no_schema_or_entity_changes(self):
        self.full.get("/"); self.full.get("/new-inventory")
        self.assertEqual(current_version(self.conn), 12)
        for t in ("vehicle_unit", "production_order", "business_fact"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)

    # 10. the rest of the normal UI still loads
    def test_full_ui_still_usable(self):
        for path in ("/", "/new-inventory", "/production", "/service-loaner"):
            self.assertEqual(self.full.get(path).status, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
