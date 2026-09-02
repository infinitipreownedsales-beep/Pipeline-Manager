"""Service-Loaner economics safety (live acceptance round 2, 2026-08-26).

  1. Authoritative model year resolves for a loaner even though the DMS pipeline export carries no full-VIN
     column — it identifies units by Serial / Stock# (the last-8 form, e.g. VIN ...TC348756). The bridge now
     joins on any available identifier + last-8, never inferring MY from VIN structure.
  2. The Command Board's 'Releasing now' / 'Expected to remain' reconcile to the per-unit economic operating
     plan (PULL/SWAP exits), not a separate self-balancing rail.
  3. Current Fleet renders the SAME certified per-unit KEEP/PULL/SWAP call, not a hardcoded 'Pending Economics'.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ops.fixtures import Phase11, SCOPE
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE as UI_SCOPE
from elite.loaner.preowned_evidence import active_fleet_model_years
from elite.ui.views.domains import _fleet_unit_row, _fleet_position_card
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS

FULLVIN = "5N1AL1HU8TC348756"     # last-8 = TC348756 (the shortened id the live fleet displays)


def _pipe(rows):
    return make_xlsx([PIPE_HEADERS] + rows, sheet_name="vehicleInventorySummary0")


def _inv(stock, serial, my, code="84616"):
    # [Stock#, Serial, Status, MY, ModelLine, ModelCode, Desc, Trans, Ext, Int, MSRP, Inv, Location, DIS, ETA, PM]
    return [stock, serial, "", my, "QX60", code, "QX60", "AUTO", "XKJ", "K", "58900", "55000", "DLR-INV", "10", "", ""]


class TestModelYearResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _loaner(self, uid, vin):
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vehicle_unit_id,vin,store_scope,membership_state,"
            "active_fleet_presence,accepted_in_service_date,created_at,version) "
            "VALUES(?,?,?,?,'ACTIVE_AVAILABLE',1,'2026-02-10',?,1)", (uid, uid + "vu", vin, SCOPE, "2026-02-10T00:00:00Z"))
        self.conn.commit()

    def test_my_resolves_by_serial_last8_when_pipeline_has_no_vin(self):
        self._loaner("slu1", FULLVIN)
        xp = _pipe([_inv("TC348756", "TC348756", "2026")])   # Serial = last-8; no VIN column
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:a", effective_time=self.p.now_iso())
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertEqual(resolved.get(FULLVIN), "2026")      # joined by last-8 -> MY authoritative
        self.assertEqual(conflicts, {})

    def test_my_resolves_by_stock_number(self):
        self._loaner("slu1", FULLVIN)
        xp = _pipe([_inv("TC348756", "OTHERSER", "2026")])   # match on Stock# = last-8
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:b", effective_time=self.p.now_iso())
        resolved, _c = active_fleet_model_years(self.conn, SCOPE)
        self.assertEqual(resolved.get(FULLVIN), "2026")

    def test_conflicting_my_is_flagged_not_guessed(self):
        self._loaner("slu1", FULLVIN)
        xp = _pipe([_inv("TC348756", "TC348756", "2026"), _inv("X", "TC348756", "2025")])   # same id, two MYs
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:c", effective_time=self.p.now_iso())
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(FULLVIN, resolved)                  # ambiguous -> not guessed
        self.assertIn(FULLVIN, conflicts)


class _U:
    def __init__(self, uid):
        self.id = uid
        self.vin = "5N1AL1HU8TC34" + uid[-4:]
        self.model = "QX60"
        self.in_service_date = "2026-02-10"
        self.age_days = 180
        self.mileage = 8000
        self.mileage_available = True
        self.rental_state = None
        self.membership_state = "ACTIVE_AVAILABLE"


class TestSurfacesConsistent(unittest.TestCase):
    def test_current_fleet_row_shows_decision_not_pending(self):
        row = _fleet_unit_row(_U("u1"), "$6,500", {"action": "PULL"})
        self.assertIn("PULL", row[-1])
        self.assertNotIn("Pending Economics", row[-1])
        # no decision -> honest UNRESOLVED, still never a fabricated 'Pending Economics'
        self.assertIn("UNRESOLVED", _fleet_unit_row(_U("u2"), "Unknown", None)[-1])

    def test_command_board_releasing_reconciles_to_operating_plan(self):
        p = Phase10(os.path.join(tempfile.mkdtemp(), "e.db"))
        try:
            sb = type("SB", (), {"current_active": 27, "desired": 20, "releasing_now": 0, "remaining": 27,
                                 "resolution": "resolved_need", "calculated_need": 5, "is_lower_bound": False})()
            decisions = {"a": {"action": "PULL"}, "b": {"action": "SWAP"}, "c": {"action": "KEEP"}}
            with patch("elite.loaner.self_balancing.build_requirement", return_value=sb), \
                 patch("elite.loaner.self_balancing.human_why", return_value="why"), \
                 patch("elite.loaner.self_balancing.source_label", return_value="src"):
                html = _fleet_position_card(p.app, UI_SCOPE, decisions)
            flat = html.replace(" ", "").replace("\n", "")
            # A (execution invariant preserved): V8 renamed the "Releasing now" metric to "Pulling"; the
            # reconciliation itself is unchanged — 2 PULL/SWAP exits -> 25 expected to remain -> 0 add.
            self.assertIn('<divclass="v">2</div><divclass="l">Pulling</div>', flat)         # 2 PULL/SWAP exits
            self.assertIn('<divclass="v">25</div><divclass="l">Expectedtoremain</div>', flat)  # 27 - 2
            self.assertIn('<divclass="v">0</div><divclass="l">Add(calculated)</div>', flat)    # 20 - 25 -> 0
        finally:
            p.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
