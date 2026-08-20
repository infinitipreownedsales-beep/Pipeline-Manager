"""Real Service-Loaner fleet export ingestion — reproduces the ACTUAL headers from vehicles_2026-08-20.csv
(`in_service_date`, `odometer_value`) end to end: adapter alias -> ingestion -> reconcile -> authoritative
in-service date + last-checkout mileage on the unit, with explicit odometer 0 preserved as a real value, and
an idempotent backfill that repopulates units created before dating reconciliation existed."""
import os
import tempfile
import unittest

from elite.loaner.fixtures import Phase6
from elite.workflow.fixtures import SCOPE
from elite.ops.adapters import run_adapter
from elite.ops.contracts import get_contract

# Real export column names, VINs, an explicit odometer 0, and a real nonzero mileage.
CSV = (
    "vin,in_service_date,odometer_value,status\n"
    "1GNSKBKC5FR000201,2025-12-01,11513,available\n"      # nonzero mileage
    "1GNSKBKC5FR000202,2025-11-15,0,available\n"          # explicit zero — a real reading, not missing
    "1GNSKBKC5FR000203,2025-10-20,4275,rented\n")


class TestRealFleetIngestion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _adapter_rows(self, csv=CSV):
        return run_adapter(get_contract("service_loaner_fleet"), csv, file_kind="csv").rows

    def test_adapter_aliases_odometer_value(self):
        rows = self._adapter_rows()
        self.assertIn("last_checkout_mileage", rows[0])          # odometer_value -> last_checkout_mileage
        self.assertNotIn("odometer_value", rows[0])
        self.assertEqual(str(rows[1]["last_checkout_mileage"]), "0")   # explicit zero preserved through parse

    def _ingest(self, csv=CSV):
        rows = self._adapter_rows(csv)
        b = self.p.snapshot.ingest_fleet(rows, snapshot_type="full")
        self.p.snapshot.reconcile(b, rows)
        return b

    def test_dates_and_mileage_reconcile_end_to_end(self):
        self._ingest()
        u1 = self.p.store.unit_for_vin("1GNSKBKC5FR000201", SCOPE)
        self.assertEqual(u1.accepted_in_service_date, "2025-12-01")
        self.assertEqual(u1.in_service_date_authority, "verified")
        self.assertEqual(str(u1.last_checkout_mileage), "11513")

    def test_explicit_zero_odometer_survives(self):
        self._ingest()
        u0 = self.p.store.unit_for_vin("1GNSKBKC5FR000202", SCOPE)
        self.assertEqual(u0.accepted_in_service_date, "2025-11-15")
        self.assertEqual(str(u0.last_checkout_mileage), "0")     # explicit 0 is a real value, not "missing"

    def test_intelligence_no_longer_reports_missing_dates(self):
        self._ingest()
        from elite.loaner.intelligence import build_intelligence
        intel = build_intelligence(self.p.store.conn, SCOPE, self._prefs(), self.p.clock)
        blocked = [u for u in intel.units if not u.in_service_date]
        self.assertEqual(blocked, [])                            # all active units now have a resolved date

    def test_backfill_repopulates_units_created_without_dating(self):
        # simulate the live state: units created by an OLDER build (membership only, NULL date/mileage)
        from elite.loaner.snapshot import _clean_in_service_date  # noqa: F401  (import sanity)
        rows = self._adapter_rows()
        b = self.p.snapshot.ingest_fleet(rows, snapshot_type="full")
        # create membership WITHOUT dating by blanking the dating-bearing columns for the first pass
        bare = [{"vin": r["vin"], "rental_status": r.get("status")} for r in rows]
        self.p.snapshot.reconcile(b, bare)
        self.assertIsNone(self.p.store.unit_for_vin("1GNSKBKC5FR000201", SCOPE).accepted_in_service_date)
        # now the operator re-uploads the SAME real file: backfill must populate without re-entry
        self.p.snapshot.backfill_dating(b, rows)
        u1 = self.p.store.unit_for_vin("1GNSKBKC5FR000201", SCOPE)
        self.assertEqual(u1.accepted_in_service_date, "2025-12-01")
        self.assertEqual(str(u1.last_checkout_mileage), "11513")
        self.assertEqual(str(self.p.store.unit_for_vin("1GNSKBKC5FR000202", SCOPE).last_checkout_mileage), "0")

    def test_raw_odometer_key_still_reconciles(self):
        # observations parsed BEFORE the alias existed carry the raw `odometer_value` key; reconcile tolerates it
        rows = [{"vin": "1GNSKBKC5FR000201", "in_service_date": "2025-12-01", "odometer_value": "9000",
                 "rental_status": "available"}]
        b = self.p.snapshot.ingest_fleet(rows, snapshot_type="full")
        self.p.snapshot.reconcile(b, rows)
        u = self.p.store.unit_for_vin("1GNSKBKC5FR000201", SCOPE)
        self.assertEqual(u.accepted_in_service_date, "2025-12-01")
        self.assertEqual(str(u.last_checkout_mileage), "9000")

    def _prefs(self):
        from elite.ui.prefs import PrefsService
        return PrefsService(self.p.store.conn, self.p.clock)

    def test_scoped_icv_needs_model_year_to_resolve(self):
        # The load-bearing fix: an MY-scoped ICV record resolves ONLY when the unit's model year is supplied.
        # Coverage sees the record at model/month level, but the unit resolver must carry the MY.
        from elite.loaner.program_inputs import ProgramInputsStore, resolve_for_unit
        pis = ProgramInputsStore(self._prefs(), SCOPE)
        pis.add("icv", effective_month="2026-02", model="QX60", model_year="2026", value=6500,
                actor="kyle", recorded_at="t")
        with_my = resolve_for_unit(pis, "icv", model="QX60", in_service_date="2026-02-10", model_year="2026")
        self.assertEqual(with_my["status"], "resolved")
        self.assertEqual(with_my["entry"].value, 6500)
        blank = resolve_for_unit(pis, "icv", model="QX60", in_service_date="2026-02-10", model_year="")
        self.assertEqual(blank["status"], "unresolved")      # the exact live bug when MY is missing


if __name__ == "__main__":
    unittest.main(verbosity=2)
