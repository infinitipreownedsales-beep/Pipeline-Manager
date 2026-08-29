"""Service-Loaner USED-ledger VIN identity bridge (live acceptance 2026-08-28).

Live permanent-DB proof: the QX60 used-sales ledger carries BLANK / TRUCK in Model Number (738 BLANK/special +
17 TRUCK of 757; only 2 coded), so NO DMS model code reaches _price_observations — exact code, raw code4,
market-lineage, and MSRP-retention all appear empty for the WHOLE model. But the dealership's HISTORICAL NEW-CAR
SALES (the DMS sales ledger's own coded rows — the ORIGINAL new sale of each VIN) carry the authoritative Model
Number for the SAME full VIN:

  5N1AL1HU6SC339383  used 2025 QX60 AUTOGRAPH $64,000  <- New-Car sale model number 84615 (raw 8461)
  5N1AL1HU2TC334313  used 2026 QX60 AUTOGRAPH $56,488  <- New-Car sale model number 84816 (raw 8481)
  5N1DL1HU8RC336427  used 2024 QX60 AUTOGRAPH $53,988  <- New-Car sale model number 84614 (raw 8461)

latest_retail_rows now bridges IDENTITY ONLY by EXACT FULL VIN from the historical New-Car sales record: it
recovers the authoritative model code (and original MSRP where the used row lacks it) while leaving the used sale
date, used transaction price, used VIN and used model year exactly as the used ledger recorded them. A non-code
sentinel never becomes identity; a VIN with no New-Car match stays unresolved (never inferred); a New-Car model
that disagrees with the used row is surfaced as a conflict and NOT bridged. Raw import history is never mutated.
"""
import json
import os
import tempfile
import unittest

from elite.ids import new_id
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.preowned_evidence import latest_retail_rows, new_retail_identity_index, _is_real_code
from elite.loaner.sl_decision import _price_observations, _code_norm, _code4
from elite.newinv.dms_identity import code4

# (used VIN, used model year, used price, used-ledger Model Number sentinel, New-Car model code)
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


def _used_row(vin, my, price, sentinel, model="QX60"):
    """A used-ledger sale in the LIVE shape: real full VIN + used facts; Model Number is a non-code sentinel."""
    r = {"vin": vin, "model": model, "model_number": sentinel, "year": my,
         "sold_date": f"{my}-06-15", "price": float(price), "days_to_sell": 42}
    return (r, r)


def _newcar_sale(vin, code, my, msrp, model="QX60"):
    """A HISTORICAL NEW-CAR SALE (earlier retail_history batch): full VIN + authoritative Model Number + model
    line + its own new-sale price (which the bridge must NEVER borrow)."""
    norm = {"vin": vin, "model": model, "model_number": code, "year": str(int(my) - 1),
            "sold_date": f"{int(my) - 1}-09-01", "price": 71000.0}
    raw = {**norm, "MSRP": str(msrp)}
    return (norm, raw)


class TestVinIdentityBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.app.stack.db.conn
        # HISTORICAL NEW-CAR SALES (earlier batch): same full VINs, authoritative Model Number
        _batch(self.conn, "src_p11_retail_history", "2024-01-01T00:00:00Z",
               [_newcar_sale(vin, code, my, 70000) for (vin, my, _p, _s, code) in CASES], schema=3)
        # USED sales ledger (latest batch): real VIN, BLANK/TRUCK Model Number, + an orphan with no New-Car match
        used = [_used_row(vin, my, price, sent) for (vin, my, price, sent, _c) in CASES]
        used.append(_used_row("5N1XXORPHAN0000000", "2025", 61000, "BLANK"))
        _batch(self.conn, "src_p11_retail_history", "2026-08-27T00:00:00Z", used, schema=3)

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
            self.assertEqual(r["model_number"], code)                        # same-VIN New-Car code recovered
            self.assertNotIn(r["model_number"], ("BLANK", "TRUCK"))
            self.assertIn("authoritative New-Car history", r["model_number_source"])   # exact provenance wording

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
            self.assertEqual(r["sold_date"], f"{my}-06-15")                  # used sale date unchanged (not the new sale)
            self.assertEqual(str(r["year"]), my)                            # used model year unchanged
            self.assertEqual(r["vin"], vin)                                 # used VIN unchanged

    def test_no_false_match_and_no_inference_without_newcar(self):
        by = self._rows_by_vin()
        orphan = by["5N1XXORPHAN0000000"]
        self.assertFalse(_is_real_code(orphan.get("model_number")))          # stays a sentinel -> no code
        self.assertEqual(orphan.get("model_number"), "BLANK")
        self.assertNotIn("model_number_source", orphan)                      # nothing inferred without a VIN match

    def test_free_text_model_still_bridges_same_commercial_line(self):
        # New-Car identity carries trim/description text ('QX60 2.0T AWD SEN'); it is still commercially QX60 and
        # MUST bridge a used 'QX60' row (the false-conflict bug from live acceptance).
        _batch(self.conn, "src_p11_retail_history", "2023-02-01T00:00:00Z",
               [_newcar_sale("5N1FREETEXT0000001", "84615", "2025", 70000, model="QX60 2.0T AWD SEN")], schema=3)
        _batch(self.conn, "src_p11_retail_history", "2026-09-02T00:00:00Z",
               [_used_row("5N1FREETEXT0000001", "2025", 62000, "BLANK", model="QX60")], schema=3)
        rows, _ = latest_retail_rows(self.conn, SCOPE)
        r = next(x for x in rows if x.get("vin") == "5N1FREETEXT0000001")
        self.assertEqual(r.get("model_number"), "84615")                     # bridged: same commercial model line
        self.assertNotIn("model_number_conflict", r)

    def test_model_conflict_is_surfaced_not_bridged(self):
        # a used QX80 row whose New-Car history VIN is a QX60 code must NOT bridge — conflict surfaced
        _batch(self.conn, "src_p11_retail_history", "2023-01-01T00:00:00Z",
               [_newcar_sale("5N1QX80CONFLICT0001", "84615", "2024", 70000, model="QX60")], schema=3)
        _batch(self.conn, "src_p11_retail_history", "2026-09-01T00:00:00Z",
               [_used_row("5N1QX80CONFLICT0001", "2025", 70000, "BLANK", model="QX80")], schema=3)
        rows, _ = latest_retail_rows(self.conn, SCOPE)
        r = next(x for x in rows if x.get("vin") == "5N1QX80CONFLICT0001")
        self.assertFalse(_is_real_code(r.get("model_number")))               # NOT bridged across a model conflict
        self.assertIn("model_number_conflict", r)

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

    def test_index_exact_full_vin_only(self):
        idx = new_retail_identity_index(self.conn, SCOPE)
        self.assertIn("5N1AL1HU6SC339383", idx)                              # keyed by the exact full VIN
        self.assertEqual(idx["5N1AL1HU6SC339383"]["model_code"], "84615")
        self.assertEqual(idx["5N1AL1HU6SC339383"]["source"], "authoritative New-Car sales history")
        self.assertNotIn("5N1XXORPHAN0000000", idx)                          # no phantom entries


if __name__ == "__main__":
    unittest.main(verbosity=2)
