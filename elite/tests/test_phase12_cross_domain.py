"""Cross-domain ordering integrity — committed-VIN protection (one vehicle / one purpose / count once) and the
governed additive planned Service-Loaner requirement (non-economic; never mutates certified Retail demand)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.ordering.cross_domain import (committed_vins, PlannedRequirementStore, decompose_orders,
                                          supply_double_count_audit)


class TestCommittedVins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _sl(self, vin, state="ACTIVE_AVAILABLE"):
        from elite.ids import new_id
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "created_at,version) VALUES(?,?,?,?,1,?,1)", (new_id("slu"), vin, SCOPE, state, "2026-01-01"))
        self.conn.commit()

    def test_active_loaner_vins_are_committed(self):
        self._sl("5N1AZ2CS0PC900001")
        self._sl("5N1AZ2CS0PC900002", state="AWAITING_USED_CARS_RECEIPT")
        c = committed_vins(self.conn, SCOPE)
        self.assertEqual(c.get("5N1AZ2CS0PC900001"), "service_loaner")
        self.assertEqual(c.get("5N1AZ2CS0PC900002"), "service_loaner")

    def test_demo_roster_vins_are_committed(self):
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "demo_roster",
                                  [{"id": "d1", "name": "GM", "current": {"vin": "5N1AZ2CS0PC900050"}}])
        c = committed_vins(self.conn, SCOPE, self.p.app.prefs)
        self.assertEqual(c.get("5N1AZ2CS0PC900050"), "demo")

    def test_count_once_sl_wins(self):
        vin = "5N1AZ2CS0PC900099"
        self._sl(vin)
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "demo_roster",
                                  [{"id": "d", "name": "x", "current": {"vin": vin}}])
        c = committed_vins(self.conn, SCOPE, self.p.app.prefs)
        self.assertEqual(c[vin], "service_loaner")            # a VIN is counted once, not in both purposes
        self.assertEqual(len([v for v in c.keys() if v == vin]), 1)   # exactly one committed entry


class TestPlannedRequirement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.store = PlannedRequirementStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_add_and_by_model(self):
        self.store.add(model="QX60", quantity=3, actor="kyle", recorded_at="t", required_by="2026-10",
                       reason="management directive")
        self.store.add(model="QX60", quantity=1, actor="kyle", recorded_at="t")
        self.store.add(model="QX80", quantity=2, actor="kyle", recorded_at="t")
        self.assertEqual(self.store.by_model(), {"QX60": 4, "QX80": 2})

    def test_positive_quantity_required(self):
        with self.assertRaises(ValueError):
            self.store.add(model="QX60", quantity=0, actor="k", recorded_at="t")

    def test_retire_removes_from_active(self):
        e = self.store.add(model="QX60", quantity=3, actor="k", recorded_at="t")
        self.store.retire(e.id, actor="k", at="2026-08-19")
        self.assertEqual(self.store.by_model(), {})           # retired need no longer participates
        self.assertEqual(len(self.store.entries()), 1)        # preserved for audit

    def test_schema_unchanged(self):
        self.store.add(model="QX60", quantity=1, actor="k", recorded_at="t")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)

    def test_acknowledge_no_need_resolves_to_zero(self):
        self.store.acknowledge_no_need("qx60", actor="kyle", at="2026-08-19")
        self.assertIn("QX60", self.store.acknowledged_models())          # normalized + recorded
        self.assertEqual(self.store.by_model(), {})                      # acknowledgement adds no quantity

    def test_planned_need_supersedes_acknowledgement(self):
        self.store.acknowledge_no_need("QX60", actor="k", at="2026-08-19")
        self.store.add(model="QX60", quantity=2, actor="k", recorded_at="t")
        # an explicit planned quantity wins: the model is no longer 'acknowledged none'
        self.assertNotIn("QX60", self.store.acknowledged_models())

    def test_clear_acknowledgement_reopens(self):
        self.store.acknowledge_no_need("QX60", actor="k", at="2026-08-19")
        self.assertTrue(self.store.clear_acknowledgement("qx60"))
        self.assertEqual(self.store.acknowledged_models(), set())


class TestDecomposeOrders(unittest.TestCase):
    """Pure cross-domain order-source combiner — Retail is read (never mutated); SL is additive, model-level;
    the unresolved state is the fail-safe trigger."""

    def _by_model(self, lines):
        return {l.model: l for l in lines}

    def test_additive_planned_is_added_not_merged(self):
        d = self._by_model(decompose_orders({"QX60": 4}, {"QX60": 2}, sl_relevant_models={"QX60"}))
        ln = d["QX60"]
        self.assertEqual((ln.retail_certified, ln.sl_planned, ln.total), (4, 2, 6))
        self.assertEqual(ln.sl_state, "additive")
        self.assertTrue(ln.complete)
        self.assertFalse(ln.sl_combo_resolved)          # SL need stays model-level, not assigned to a color

    def test_sl_relevant_without_resolution_is_unresolved(self):
        d = self._by_model(decompose_orders({"QX60": 3}, {}, sl_relevant_models={"QX60"}))
        self.assertEqual(d["QX60"].sl_state, "unresolved")
        self.assertFalse(d["QX60"].complete)            # Retail-only must NOT be called complete
        self.assertEqual(d["QX60"].total, 3)            # certified Retail is not mutated

    def test_acknowledged_none_is_complete(self):
        d = self._by_model(decompose_orders({"QX60": 3}, {}, sl_relevant_models={"QX60"},
                                            acknowledged_models={"QX60"}))
        self.assertEqual(d["QX60"].sl_state, "acknowledged_none")
        self.assertTrue(d["QX60"].complete)

    def test_non_loaner_model_is_not_applicable(self):
        d = self._by_model(decompose_orders({"Q50": 2}, {}, sl_relevant_models=set()))
        self.assertEqual(d["Q50"].sl_state, "not_applicable")
        self.assertTrue(d["Q50"].complete)

    def test_planned_only_model_absent_from_retail_still_appears(self):
        # a model with SL need but no Retail order must still surface (its need would otherwise be invisible)
        d = self._by_model(decompose_orders({}, {"QX80": 1}, sl_relevant_models=set()))
        self.assertEqual((d["QX80"].retail_certified, d["QX80"].sl_planned, d["QX80"].total), (0, 1, 1))
        self.assertEqual(d["QX80"].sl_state, "additive")

    def test_case_insensitive_model_keys(self):
        d = self._by_model(decompose_orders({"qx60": 1}, {"QX60": 1}, sl_relevant_models={"Qx60"}))
        self.assertEqual(set(d), {"QX60"})
        self.assertEqual(d["QX60"].total, 2)


class TestSupplyDoubleCount(unittest.TestCase):
    """One physical supply truth — a committed SL/Demo VIN that also shows up as free Retail supply is flagged."""

    def _vin(self, r):
        return r.get("vin")

    def test_overlap_detected(self):
        rows = [{"vin": "5N1AZ2CS0PC900001"}, {"vin": "5N1AZ2CS0PC900002"}]
        committed = {"5N1AZ2CS0PC900001"}                               # committed to SL AND in retail supply
        self.assertEqual(supply_double_count_audit(rows, committed, self._vin), ["5N1AZ2CS0PC900001"])

    def test_no_overlap_is_clean(self):
        rows = [{"vin": "5N1AZ2CS0PC900002"}]
        self.assertEqual(supply_double_count_audit(rows, {"5N1AZ2CS0PC900001"}, self._vin), [])

    def test_serial_only_rows_never_match(self):
        # a serial-only supply row (no authoritative vin) can never create a false double-count
        rows = [{"vin": None, "serial": "TC348756"}]
        self.assertEqual(supply_double_count_audit(rows, {"5N1AZ2CS0PC900001"}, self._vin), [])


def _board_row(model="QX60", order=2, pid="p1"):
    return {"pid": pid, "combo": pid + "c", "identity": f"{model} LUXE", "model": model, "order": order,
            "current": 0, "future": 0, "certified_future": 0, "m_present": False, "m_shortage": None,
            "m_demand": None, "m_cum_demand": None, "m_cum_supply": None, "m_excess": None, "m_confidence": None}


class TestPlannedRequirementPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_record_and_list_planned_requirement(self):
        self.assertIn("No planned Service-Loaner requirements", self.full.get("/ordering/sl-requirements").body)
        self.full.post("/ordering/sl-requirements/add",
                       {"model": "QX60", "quantity": "3", "required_by": "2026-10", "reason": "GM directive"})
        b = self.full.get("/ordering/sl-requirements").body
        self.assertIn("QX60", b)
        self.assertIn("GM directive", b)
        self.assertIn("2026-10", b)
        self.assertEqual(PlannedRequirementStore(self.p.app.prefs, SCOPE).by_model(), {"QX60": 3})

    def test_zero_quantity_rejected(self):
        self.full.post("/ordering/sl-requirements/add", {"model": "QX60", "quantity": "0"})
        self.assertEqual(PlannedRequirementStore(self.p.app.prefs, SCOPE).by_model(), {})   # never stored

    def test_acknowledge_no_need_round_trip(self):
        self.full.post("/ordering/sl-requirements/ack", {"model": "QX60"})
        self.assertIn("QX60", PlannedRequirementStore(self.p.app.prefs, SCOPE).acknowledged_models())
        b = self.full.get("/ordering/sl-requirements").body
        self.assertIn("Reopen QX60", b)
        self.full.post("/ordering/sl-requirements/ack-clear", {"model": "QX60"})
        self.assertEqual(PlannedRequirementStore(self.p.app.prefs, SCOPE).acknowledged_models(), set())

    def test_schema_unchanged(self):
        self.full.post("/ordering/sl-requirements/add", {"model": "QX60", "quantity": "1"})
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


class TestCpoDecompositionView(unittest.TestCase):
    """The CPO board shows the dealership decomposition and consumes the self-balancing Service-Loaner result:
    a fleet at/above target resolves to zero automatically (no invented number); a missing target is the only
    real prerequisite; a management directive is separate and additive."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _set_target(self, n):
        from elite.loaner.loaner_cockpit import MetaPrefs, set_desired_fleet
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), n)

    def _cpo(self):
        with patch("elite.ui.views.operator._acquire_board", return_value=[_board_row("QX60", 2)]):
            return self.full.get("/ordering/cpo").body

    def test_no_target_is_the_only_prerequisite(self):
        b = self._cpo()                                                 # no desired fleet set
        self.assertIn("Order sources — QX60", b)
        self.assertIn("Service-Loaner target not set", b)              # the one real prerequisite
        self.assertIn("do not invent a number", b)

    def test_fleet_at_target_auto_resolves_to_zero(self):
        self._set_target(0)                                            # 0 active units, target 0 -> need 0
        b = self._cpo()
        self.assertIn("no additional loaner acquisition required", b)  # auto-resolved, no manual entry
        self.assertNotIn("Service-Loaner target not set", b)
        self.assertIn("Total dealership acquisition requirement", b)

    def test_management_directive_is_added(self):
        self._set_target(0)
        PlannedRequirementStore(self.p.app.prefs, SCOPE).add(model="QX60", quantity=2, actor="k", recorded_at="t")
        b = self._cpo()
        self.assertIn("Management directive", b)                       # separate, additive, model-level
        self.assertIn("Model total 4", b)                             # 2 retail + 2 directive for QX60

    def test_certified_retail_not_mutated(self):
        self._set_target(0)
        self._cpo()
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
