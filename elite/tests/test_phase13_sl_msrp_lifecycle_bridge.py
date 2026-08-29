"""Service-Loaner MSRP source/provenance bridge (live acceptance 2026-08-27).

The live blocker was that neither the current unit's identity/MSRP nor the historical MSRP reached the decision,
so all 27 units gated on expected used price. Two governed provenance bridges — no new pricing math, no manual
values — restore the evidence from data ALREADY loaded. (The market rail itself prices from OBSERVED TRANSACTION
DOLLARS for the unit's trim as the primary path; MSRP-normalized retention is the secondary fallback. Bridge B
also recovers the unit's model_code, which the primary observed-dollar path needs to pick its trim cohort.)

  A. Historical original MSRP: the Reynolds retail-history export carries MSRP, but earlier schema profiles
     omitted it from normalization, so it survives only in the retained RAW observation. latest_retail_rows now
     surfaces it (never mutating raw), so the retention FALLBACK can normalize each historical sale by its OWN
     authoritative original MSRP when same-trim transaction evidence is insufficient.

  B. Current-unit MSRP + model code lifecycle: a Service Loaner has moved out of today's New-Retail snapshot, so
     it is absent from the latest inventory export — but its MSRP + model code were retained when it was new
     inventory (the pipeline summary is a per-business-date longitudinal-memory source). inventory_lifecycle_facts
     recovers them from any retained snapshot by the same governed VIN/Serial/Stock last-8 linkage used for MY.

Acceptance proof (TC348756): authoritative model code + MSRP -> observed transaction-price cohort/n/window ->
price now -> price future -> adjusted basis now/future (independent basis rail) -> KEEP/PULL/SWAP.
"""
import json
import os
import tempfile
import unittest

from elite.ids import new_id
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.preowned_evidence import (inventory_lifecycle_facts, latest_retail_rows, _retail_msrp)
from elite.loaner.sl_decision import build_unit_decision, _retention_observations
from elite.loaner.intelligence import UnitIntel
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore

FULLVIN = "5N1AL1HU8TC348756"          # last-8 = TC348756, the shortened id the DMS pipeline carries as Serial
CODE = "84616"


def _batch(conn, source_id, received_at, obs, *, schema=None):
    """Insert a completed batch + accepted observations. Each obs is (normalized_dict, raw_dict) so a legacy
    already-loaded shape (MSRP only in raw) can be reproduced exactly."""
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


def _pipe_row(serial, msrp, code=CODE, my="2026"):
    r = {"serial": serial, "stock_number": serial, "model": "QX60", "model_code": code,
         "model_year": my, "msrp": str(msrp)}
    return (r, r)


def _legacy_retail(code=CODE, ages=range(3, 16), per=5):
    """Historical QX60 sales in the LIVE already-loaded shape: normalized_values has NO msrp (earlier profile),
    the authoritative original MSRP lives only in the RAW row under the Reynolds 'MSRP' header. Retention
    (price / original MSRP) declines with lifecycle age."""
    msrp_by_my = {2024: 58000, 2025: 60000, 2026: 62000}
    obs = []
    for my in (2024, 2025, 2026):
        msrp = msrp_by_my[my]
        for a in ages:
            t = my * 12 + a
            y, m = t // 12, t % 12 + 1
            for k in range(per):
                price = msrp - 400 * a + (k - 2) * 100
                norm = {"model": "QX60", "model_number": code, "year": my,
                        "sold_date": f"{y:04d}-{m:02d}-15", "price": float(price), "days_to_sell": 40}
                raw = {**{"Model": "QX60", "Model Number": code, "Year": str(my),
                          "Sales Date": f"{y:04d}-{m:02d}-15", "Vehicle Price": str(price)},
                       "MSRP": str(msrp)}                      # authoritative original MSRP, raw only
                obs.append((norm, raw))
    return obs


class TestMsrpProvenanceBridges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        self.conn = self.app.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _loaner(self, vin, in_service="2026-02-10"):
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "accepted_in_service_date,created_at,version) VALUES(?,?,?,?,1,?,?,1)",
            (new_id("slu"), vin, SCOPE, "ACTIVE_AVAILABLE", in_service, in_service + "T00:00:00Z"))
        self.conn.commit()

    # --- Bridge B: current-unit MSRP from the inventory lifecycle, not just the latest snapshot ---
    def test_lifecycle_recovers_msrp_after_unit_leaves_latest_snapshot(self):
        # earlier snapshot carried TC348756 as new inventory; the LATER (current) snapshot no longer has it
        _batch(self.conn, "src_p11_new_inventory_pipeline_summary", "2026-03-01T00:00:00Z",
               [_pipe_row("TC348756", 62000)])
        _batch(self.conn, "src_p11_new_inventory_pipeline_summary", "2026-08-20T00:00:00Z",
               [_pipe_row("ZZ999999", 55000)])               # today's snapshot: unit has departed to loaner
        msrp, code = inventory_lifecycle_facts(self.conn, SCOPE, FULLVIN)
        self.assertEqual(msrp, 62000.0)                       # recovered from the retained earlier snapshot
        self.assertEqual(code, "84616")

    def test_lifecycle_gates_when_never_in_any_snapshot(self):
        _batch(self.conn, "src_p11_new_inventory_pipeline_summary", "2026-08-20T00:00:00Z",
               [_pipe_row("ZZ999999", 55000)])
        self.assertEqual(inventory_lifecycle_facts(self.conn, SCOPE, FULLVIN), (None, None))  # never fabricated

    # --- Bridge A: historical original MSRP surfaced from the retained raw retail observation ---
    def test_retail_msrp_reads_legacy_header_spellings(self):
        self.assertEqual(_retail_msrp({"MSRP": "62,000"}), 62000.0)
        self.assertEqual(_retail_msrp({"msrp": "$58900"}), 58900.0)
        self.assertIsNone(_retail_msrp({"model": "QX60"}))    # absent -> None, never fabricated

    def test_latest_retail_rows_surface_raw_msrp(self):
        _batch(self.conn, "src_p11_retail_history", "2026-08-26T00:00:00Z", _legacy_retail(), schema=3)
        rows, _as_of = latest_retail_rows(self.conn, SCOPE)
        self.assertTrue(rows)
        self.assertTrue(all(r.get("msrp") for r in rows))     # raw MSRP still surfaced for display
        # retention denominator uses the governed (model_code, model_year) inventory MSRP anchors — NEVER the
        # used row's own MSRP field (unreliable in the combined Reynolds ledger).
        by_code_my = {(CODE, my): float(v) for my, v in {2024: 58000, 2025: 60000, 2026: 62000}.items()}
        by_code = {CODE: 60000.0}
        obs = _retention_observations(rows, by_code_my, by_code, "QX60")
        self.assertGreaterEqual(len(obs), 60)
        self.assertEqual(len(_retention_observations(rows, {}, {}, "QX60")), 0)   # no authoritative MSRP -> drop

    # --- Full acceptance proof for TC348756 ---
    def test_tc348756_prices_and_decides_end_to_end(self):
        self._loaner(FULLVIN)
        # inventory lifecycle: TC348756 (code 84616 / $62,000) captured when new, then gone from today's snapshot
        _batch(self.conn, "src_p11_new_inventory_pipeline_summary", "2026-03-01T00:00:00Z",
               [_pipe_row("TC348756", 62000)])
        _batch(self.conn, "src_p11_new_inventory_pipeline_summary", "2026-08-20T00:00:00Z",
               [_pipe_row("ZZ999999", 55000)])
        # historical QX60 retention evidence (legacy shape: MSRP in raw only)
        _batch(self.conn, "src_p11_retail_history", "2026-08-26T00:00:00Z", _legacy_retail(), schema=3)
        # basis + program rails
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_invoice(FULLVIN, 60000, actor="k", at="t")
        pol.set_protection_buffer_days(20, actor="k", at="t")
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        pis.add("icv", effective_month="2026-01", model="QX60", model_year="2026", value=6500, actor="k",
                recorded_at="t")
        pis.add("velocity", effective_month="2026-01", model="QX60", model_year="2026", value=2500,
                day_cap=240, mile_cap=10000, actor="k", recorded_at="t")

        unit = UnitIntel(id="u1", vin=FULLVIN, model="QX60", in_service_date="2026-02-10", age_days=180,
                         mileage=8000, mileage_available=True, membership_state="ACTIVE_AVAILABLE",
                         rental_state=None, quality_flags=(), model_year="2026")
        d = build_unit_decision(self.app, SCOPE, unit, None, today="2026-08-26", keep_horizon_days=90)
        f, c = d["facts"], d["components"]

        # authoritative current-unit MSRP (from the inventory lifecycle, not a manual entry)
        self.assertEqual(f["unit_msrp"], 62000.0)
        self.assertEqual(f["unit_model_code"], "84616")
        # observed transaction-price cohort (same model code) -> price now / future, both resolved (not gated)
        self.assertNotIn("expected used price now", d["gated"])
        self.assertNotIn("expected future used price (KEEP)", d["gated"])
        self.assertIsNotNone(f["price_now"])
        self.assertIsNotNone(f["price_future"])
        self.assertIn("observed used transaction price", f["price_now_basis"])   # primary rail, observed dollars
        self.assertIn("same model code 84616", f["price_now_basis"])
        self.assertLess(f["price_future"], f["price_now"])                    # later sale date -> older age
        # basis rail is independent (invoice + write-down), never the MSRP market number
        self.assertEqual(f["invoice"], 60000)
        self.assertGreater(c["adjusted_basis_now"], 0)
        self.assertLess(c["adjusted_basis_future"], c["adjusted_basis_now"])  # write-down accrues over the hold
        self.assertIn(d["action"], ("KEEP", "PULL", "SWAP"))                  # a real decision, not UNRESOLVED


if __name__ == "__main__":
    unittest.main(verbosity=2)
