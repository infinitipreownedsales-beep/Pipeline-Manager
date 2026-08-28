"""Service-Loaner USED-ledger VIN identity bridge (live acceptance 2026-08-28).

Live permanent-DB proof: the QX60 used-sales ledger carries BLANK / TRUCK in Model Number (740 BLANK + 17 TRUCK
of 757), so NO DMS model code ever reached _price_observations — exact code, raw code4, market-lineage, and
MSRP-retention all appeared empty. But the SAME FULL VIN exists in the dealership's New-Retail lifecycle with the
authoritative model code:

  5N1AL1HU6SC339383  2025 QX60 AUTOGRAPH  used $64,000  -> New Retail model number 84615 (raw 8461)
  5N1AL1HU2TC334313  2026 QX60 AUTOGRAPH  used $56,488  -> New Retail model number 84816 (raw 8481)
  5N1DL1HU8RC336427  2024 QX60 AUTOGRAPH  used $53,988  -> New Retail model number 84614 (raw 8461)

latest_retail_rows now bridges IDENTITY ONLY from the same-VIN New-Retail lifecycle record: it recovers the
authoritative model code (and original MSRP where the used row lacks it), leaving the used sale date, used
transaction price, used VIN and used model year exactly as the used ledger recorded them. Provenance is stamped
('original New Retail VIN lifecycle record'); a non-code sentinel never becomes identity; a VIN with no lifecycle
match stays unresolved (never inferred).
"""
import json
import os
import tempfile
import unittest

from elite.ids import new_id
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.preowned_evidence import latest_retail_rows, new_retail_identity_index, _is_real_code
from elite.loaner.sl_decision import _price_observations, _market_price, _code_norm, _code4
from elite.newinv.dms_identity import code4

# (used VIN, used model year, used price, used-ledger Model Number sentinel, New-Retail model code)
CASES = [
    ("5N1AL1HU6SC339383", "2025", 64000, "BLANK", "84615"),   # 2025 Autograph -> 8461
    ("5N1AL1HU2TC334313", "2026", 56488, "TRUCK", "84816"),   # 2026 Autograph -> 8481
    ("5N1DL1HU8RC336427", "2024", 53988, "BLANK", "84614"),   # 2024 Autograph -> 8461
]


def _batch(conn, source_id, received_at, obs, *, schema=None):
    bid = new_id("ib")
    conn.execute(
        "INSERT INTO import_batch(id,source_id,store_scope,lifecycle_status,received_at,payload_checksum,"
        "schema_profile_version) VALUES(?,?,?,?,?,?,?)",
        (bid, source_id, SCOPE, "completed", received_at, "sha256:" + bid, schema))
    for norm, raw in obs:
        conn.execute(
            "INSERT INTO source_observation(id,import_batch_id,source_scope,acceptance_status,raw_values,"
            "normalized_values,observed_time,recorded_time,validation_status,identity_status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (new_id("obs"), bid, SCOPE, "accepted", json.dumps(raw), json.dumps(norm),
             received_at, received_at, "valid", "resolved"))
    conn.commit()


def _used_row(vin, my, price, sentinel):
    """A used-ledger sale in the LIVE shape: real VIN + used facts, Model Number is a non-code sentinel."""
    r = {"vin": vin, "model": "QX60", "model_number": sentinel, "year": my,
         "sold_date": f"{my}-06-15", "price": float(price), "days_to_sell": 42}
    return (r, r)


def _pipe_row(vin, code, msrp, my):
    """A New-Retail lifecycle record carrying only the DMS Serial (last-8 of the VIN) + authoritative code/MSRP."""
    r = {"serial": vin[-8:], "stock_number": vin[-8:], "model": "QX60", "model_code": code,
         "model_year": my, "msrp": str(msrp)}
    return (r, r)


class TestVinIdentityBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.app.stack.db.conn
        # used ledger: every row has a real VIN but a BLANK/TRUCK Model Number
        used = [_used_row(vin, my, price, sent) for (vin, my, price, sent, _code) in CASES]
        used.append(_used_row("5N1XXORPHAN0000000", "2025", 61000, "BLANK"))   # no lifecycle match anywhere
        _batch(self.conn, "src_p11_retail_history", "2026-08-27T00:00:00Z", used, schema=3)
        # New-Retail lifecycle: the SAME VINs (by Serial last-8) with authoritative code + MSRP
        _batch(self.conn, "src_p11_new_inventory_pipeline_summary", "2025-01-01T00:00:00Z",
               [_pipe_row(vin, code, 70000, my) for (vin, my, _p, _s, code) in CASES])

    def tearDown(self):
        self.p.close()

    def _rows_by_vin(self):
        rows, _as_of = latest_retail_rows(self.conn, SCOPE)
        return {r.get("vin"): r for r in rows}

    def test_sentinel_never_becomes_identity_and_code_recovered(self):
        by = self._rows_by_vin()
        for vin, my, price, sentinel, code in CASES:
            r = by[vin]
            self.assertTrue(_is_real_code(r.get("model_number")))            # BLANK/TRUCK replaced by a real code
            self.assertEqual(r["model_number"], code)                        # same-VIN New-Retail code recovered
            self.assertNotIn(r["model_number"], ("BLANK", "TRUCK"))
            self.assertEqual(r["model_number_source"], "original New Retail VIN lifecycle record")  # provenance

    def test_specific_codes_and_raw_config(self):
        by = self._rows_by_vin()
        self.assertEqual(by["5N1AL1HU6SC339383"]["model_number"], "84615")   # 2025 Autograph
        self.assertEqual(code4("84615"), "8461")
        self.assertEqual(by["5N1AL1HU2TC334313"]["model_number"], "84816")   # 2026 Autograph
        self.assertEqual(code4("84816"), "8481")
        self.assertEqual(by["5N1DL1HU8RC336427"]["model_number"], "84614")   # 2024 Autograph
        self.assertEqual(code4("84614"), "8461")

    def test_used_transaction_facts_are_preserved(self):
        by = self._rows_by_vin()
        for vin, my, price, sentinel, code in CASES:
            r = by[vin]
            self.assertEqual(r["price"], float(price))                       # USED Vehicle Price unchanged
            self.assertEqual(r["sold_date"], f"{my}-06-15")                  # used sale date unchanged
            self.assertEqual(str(r["year"]), my)                            # used model year unchanged
            self.assertEqual(r["vin"], vin)                                 # used VIN unchanged

    def test_no_false_match_and_no_inference_without_lifecycle(self):
        by = self._rows_by_vin()
        orphan = by["5N1XXORPHAN0000000"]
        self.assertFalse(_is_real_code(orphan.get("model_number")))          # stays a sentinel -> no code
        self.assertEqual(orphan.get("model_number"), "BLANK")
        self.assertNotIn("model_number_source", orphan)                      # nothing inferred without a VIN match

    def test_price_observations_now_see_recovered_codes(self):
        rows, _as_of = latest_retail_rows(self.conn, SCOPE)
        obs = _price_observations(rows, "QX60")
        codes = [c for _am, _p, c in obs]
        self.assertIn("84615", codes)
        self.assertIn("84614", codes)
        self.assertIn("84816", codes)
        self.assertEqual(codes.count("BLANK"), 1)                            # only the unresolved orphan stays BLANK
        c4 = [_code4("QX60", c) for c in codes]
        self.assertIn("8461", c4)                                            # 2024/2025 Autograph -> raw 8461
        self.assertIn("8481", c4)                                            # 2026 Autograph -> raw 8481

    def test_index_is_identity_only_direct_lookup(self):
        idx = new_retail_identity_index(self.conn, SCOPE)
        # keyed by last-8 (the Serial form) so a full used VIN resolves
        self.assertIn("SC339383", idx)
        self.assertEqual(idx["SC339383"]["model_code"], "84615")
        self.assertEqual(idx["SC339383"]["source"], "original New Retail VIN lifecycle record")
        self.assertNotIn("5N1XXORPHAN0000000"[-8:], idx)                     # no phantom entries


if __name__ == "__main__":
    unittest.main(verbosity=2)
