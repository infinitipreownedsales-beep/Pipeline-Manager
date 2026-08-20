"""Service-Loaner placement must consume the SAME authoritative current inventory snapshot the rest of Elite
reads. Regression for the live defect where placement reported "No New-Retail inventory snapshot is loaded"
even though a current snapshot existed — caused by passing a bare DataStore (no latest_snapshot) where a
SnapshotReader was required, so the AttributeError was silently swallowed."""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11
from elite.workflow.fixtures import SCOPE
from elite.loaner.placement import read_new_retail_units, best_available_placement

# new_inventory_current with a Location column (extra, tolerated) marking physically on-lot DLR-INV units.
INV = ("stock_number,vin,model,production_month,mileage,location,status\n"
       "S001,1GNSKBKC5FR000401,QX60,2026-05,12,DLR-INV,available\n"
       "S002,1GNSKBKC5FR000402,QX60,2026-05,8,DLR-INV,available\n"
       "S003,1GNSKBKC5FR000403,QX80,2026-04,5,ONS,available\n")   # ONS = not yet on the lot


class TestPlacementSeesInventory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        self.app._p11 = self.p                       # wire the ops stack the way the live launcher does
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.stack.close()

    def _ingest(self):
        run = self.p.import_payload("new_inventory_current", INV, claimed_snapshot="full",
                                    effective_time="2026-08-20T12:00:00Z")
        self.assertIn(run["state"], ("COMPLETED", "COMPLETED_WITH_WARNINGS"))

    def test_placement_reads_the_live_snapshot(self):
        self._ingest()
        rows = read_new_retail_units(self.app, SCOPE)
        self.assertTrue(rows)                        # NOT empty — the snapshot is reachable now
        vins = {r.get("vin") for r in rows}
        self.assertIn("1GNSKBKC5FR000401", vins)

    def test_board_no_longer_falsely_reports_no_inventory(self):
        self._ingest()
        res = best_available_placement(self.app, self.conn, SCOPE, n=3)
        self.assertTrue(res["loaded"])               # the false "No inventory loaded" is gone
        self.assertGreaterEqual(res["eligible"], 2)  # the two DLR-INV QX60s are eligible on-lot units
        # the ONS unit (not on the lot) is not eligible
        self.assertEqual(res["eligible"], 2)

    def test_no_inventory_still_reports_not_loaded(self):
        res = best_available_placement(self.app, self.conn, SCOPE, n=3)   # nothing ingested
        self.assertFalse(res["loaded"])              # honest: genuinely no snapshot -> not loaded (no fabrication)

    def test_fleet_model_year_propagates_to_unit_intel(self):
        # Real production path (src_p11_service_loaner_fleet): a fleet export carrying model_year must reach
        # unit-level intelligence so the MY-scoped ICV/Velocity resolve (the TC348756 live defect).
        from elite.loaner.snapshot import SnapshotService
        from elite.loaner.store import LoanerStore
        from elite.ops.adapters import run_adapter
        from elite.ops.contracts import get_contract
        from elite.loaner.intelligence import build_intelligence
        fleet = ("vin,model,model_year,in_service_date,odometer_value,status\n"
                 "1GNSKBKC5FR000701,QX60,2026,2026-02-10,11513,available\n")
        run = self.p.import_payload("service_loaner_fleet", fleet, claimed_snapshot="full",
                                    effective_time="2026-08-20T12:00:00Z")
        batch = self.p.data.get_batch(run["import_batch_id"])
        rows = run_adapter(get_contract("service_loaner_fleet"), fleet, file_kind="csv").rows
        SnapshotService(LoanerStore(self.conn, self.p.clock), self.p.data, self.p.ingestion,
                        self.p.clock, SCOPE).reconcile(batch, rows)
        intel = build_intelligence(self.conn, SCOPE, self.app.prefs, self.p.clock)
        u = next((x for x in intel.units if x.vin == "1GNSKBKC5FR000701"), None)
        self.assertIsNotNone(u)
        self.assertEqual(u.model_year, "2026")       # authoritative MY reached the unit (never inferred)


if __name__ == "__main__":
    unittest.main(verbosity=2)
