"""Governed, fail-closed model-year ingestion (Stage 1A/6 adversarial).

Model year comes ONLY from the explicit governed allowlist of authoritative fleet headers, must normalise to
exactly one 4-digit year, and fails closed on ambiguity/malformed. It is never inferred from a VIN or model
code, and an unrelated 'year'-like column never matches."""
import os
import tempfile
import unittest

from elite.loaner.preowned_evidence import active_fleet_model_years, _norm_model_year, MODEL_YEAR_SOURCE_HEADERS
from elite.loaner.fixtures import Phase6
from elite.workflow.fixtures import SCOPE
from elite.ids import new_id


class TestNormalise(unittest.TestCase):
    def test_valid_four_digit(self):
        self.assertEqual(_norm_model_year("2026"), "2026")
        self.assertEqual(_norm_model_year(" 2026 "), "2026")
        self.assertEqual(_norm_model_year("2026.0"), "2026")

    def test_malformed_fails_closed(self):
        for bad in ("", None, "26", "twenty-twenty-six", "2026-QX60", "20260", "FY2026Q1"):
            self.assertIsNone(_norm_model_year(bad), bad)

    def test_bare_year_not_in_allowlist(self):
        self.assertNotIn("year", MODEL_YEAR_SOURCE_HEADERS)   # unrelated 'year' column must never match


class TestActiveFleetModelYears(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.store.conn

    def tearDown(self):
        self.p.close()

    def _unit(self, vin):
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "created_at,version) VALUES(?,?,?,?,1,?,1)", (new_id("slu"), vin, SCOPE, "ACTIVE_AVAILABLE", "2026-01-01"))
        self.conn.commit()

    def _snapshot(self, rows):
        """Insert a completed service_loaner_fleet batch + accepted observations with the given raw_values."""
        import json
        bid = new_id("ib")
        self.conn.execute(
            "INSERT INTO import_batch(id,source_id,store_scope,lifecycle_status,received_at,payload_checksum) "
            "VALUES(?,?,?,?,?,?)", (bid, "src_p11_service_loaner_fleet", SCOPE, "completed",
                                    "2026-08-20T00:00:00Z", "sha256:" + bid))
        for r in rows:
            self.conn.execute(
                "INSERT INTO source_observation(id,import_batch_id,source_scope,acceptance_status,raw_values,"
                "normalized_values,observed_time,recorded_time,validation_status,identity_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (new_id("obs"), bid, SCOPE, "accepted", json.dumps(r), json.dumps(r),
                 "2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z", "valid", "resolved"))
        self.conn.commit()

    def test_accepts_governed_headers(self):
        cases = {"1GNSKBKC5FR900001": ("model_year", "2026"),
                 "1GNSKBKC5FR900002": ("Model Year", "2025"),
                 "1GNSKBKC5FR900003": ("MY", "2024")}
        rows = []
        for v, (header, val) in cases.items():
            self._unit(v)
            rows.append({"vin": v, header: val})
        self._snapshot(rows)                                  # ONE batch (only the latest is read)
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        for v, (header, val) in cases.items():
            self.assertEqual(resolved.get(v), val, header)
            self.assertNotIn(v, conflicts)

    def test_unrelated_year_column_does_not_match(self):
        v = "1GNSKBKC5FR900010"
        self._unit(v)
        self._snapshot([{"vin": v, "year": "2019"}])          # 'year' is NOT authoritative here
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(v, resolved)                          # never silently read as model year

    def test_conflicting_columns_fail_closed(self):
        v = "1GNSKBKC5FR900011"
        self._unit(v)
        self._snapshot([{"vin": v, "model_year": "2026", "MY": "2025"}])
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(v, resolved)                          # ambiguity never silently resolved
        self.assertIn(v, conflicts)

    def test_malformed_fails_closed(self):
        v = "1GNSKBKC5FR900012"
        self._unit(v)
        self._snapshot([{"vin": v, "model_year": "20xx"}])
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(v, resolved)
        self.assertIn(v, conflicts)

    def test_missing_my_is_silent_unknown(self):
        v = "1GNSKBKC5FR900013"
        self._unit(v)
        self._snapshot([{"vin": v, "model": "QX60"}])          # no MY column at all
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(v, resolved)
        self.assertNotIn(v, conflicts)                         # absent, not a conflict

    def test_agreeing_duplicate_columns_resolve(self):
        v = "1GNSKBKC5FR900014"
        self._unit(v)
        self._snapshot([{"vin": v, "model_year": "2026", "MY": "2026"}])
        resolved, conflicts = active_fleet_model_years(self.conn, SCOPE)
        self.assertEqual(resolved.get(v), "2026")              # same value in two columns is not a conflict


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestInventorySourceFallback(unittest.TestCase):
    """Source-connection fallback: when the loaner fleet export carries no model-year column, MY is resolved
    for a VIN from another already-loaded authoritative source that has a governed MY column keyed by VIN (the
    DMS inventory export). Still governed, fail-closed, never inferred from the VIN."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.store.conn

    def tearDown(self):
        self.p.close()

    def _unit(self, vin):
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "created_at,version) VALUES(?,?,?,?,1,?,1)", (new_id("slu"), vin, SCOPE, "ACTIVE_AVAILABLE", "2026-01-01"))
        self.conn.commit()

    def _inventory_snapshot(self, rows, source_id="src_p11_new_inventory_current"):
        import json
        bid = new_id("ib")
        self.conn.execute(
            "INSERT INTO import_batch(id,source_id,store_scope,lifecycle_status,received_at,payload_checksum) "
            "VALUES(?,?,?,?,?,?)", (bid, source_id, SCOPE, "completed", "2026-08-24T00:00:00Z", "sha256:" + bid))
        for r in rows:
            self.conn.execute(
                "INSERT INTO source_observation(id,import_batch_id,source_scope,acceptance_status,raw_values,"
                "normalized_values,observed_time,recorded_time,validation_status,identity_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (new_id("obs"), bid, SCOPE, "accepted", json.dumps(r), json.dumps(r),
                 "2026-08-24T00:00:00Z", "2026-08-24T00:00:00Z", "valid", "resolved"))
        self.conn.commit()

    def test_my_resolved_from_inventory_when_fleet_lacks_it(self):
        vin = "5N1AL1ER7TC348756"
        self._unit(vin)                                       # loaner fleet has no MY column at all
        resolved, _ = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(vin, resolved)                       # unknown before the fallback source is loaded
        self._inventory_snapshot([{"vin": vin, "MY": "2026", "model": "QX60"}])
        resolved, _ = active_fleet_model_years(self.conn, SCOPE)
        self.assertEqual(resolved.get(vin), "2026")           # resolved from the governed inventory MY column

    def test_inventory_fallback_still_fail_closed_on_malformed(self):
        vin = "5N1AL1ER2TC351709"
        self._unit(vin)
        self._inventory_snapshot([{"vin": vin, "MY": "20xx"}])   # malformed -> stays UNKNOWN, never guessed
        resolved, _ = active_fleet_model_years(self.conn, SCOPE)
        self.assertNotIn(vin, resolved)
