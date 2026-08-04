"""Phase 2 acceptance — source, snapshot, values, reconciliation, durability
(items 1-16, 31, 32, 33, 34)."""
import os
import tempfile
import unittest

from elite.data.fixtures import GOOD_VIN, Phase2, source_cases
from elite.data.normalize import Special, normalize_scalar


class TestPhase2Data(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "elite.db")
        self.p = Phase2(self.path)
        self.cases = source_cases()

    def tearDown(self):
        self.p.close()

    def _facts(self):
        return self.p.store.conn.execute("SELECT COUNT(*) c FROM business_fact").fetchone()["c"]

    def test_1_source_registry_survives_restart(self):
        self.p.close()
        p2 = Phase2(self.path)
        try:
            self.assertIsNotNone(p2.store.get_source("src_dms"))
        finally:
            p2.close()

    def test_2_schema_profile_version_preserved(self):
        prof = self.p.store.get_profile("src_dms", 1)
        self.assertEqual(prof.version, 1)
        self.assertTrue(prof.snapshot_capable)

    def test_3_invalid_required_schema_rejected(self):
        rows, snap = self.cases["missing_required_field"]
        b = self.p.ingest_dms(rows, claimed_snapshot=snap)
        self.assertEqual(b.rejected_count, 1)
        self.assertEqual(b.accepted_count, 0)
        self.assertEqual(self._facts(), 0)

    def test_4_extra_harmless_field_does_not_invalidate(self):
        rows, snap = self.cases["harmless_extra_field"]
        b = self.p.ingest_dms(rows, claimed_snapshot=snap)
        self.assertEqual(b.accepted_count, 1)

    def test_5_raw_values_preserved(self):
        rows, snap = self.cases["harmless_extra_field"]
        b = self.p.ingest_dms(rows, claimed_snapshot=snap)
        obs = self.p.store.list_observations(b.id)[0]
        self.assertEqual(obs.raw_values, rows[0])            # raw kept verbatim (incl. extra field)
        self.assertIsNotNone(self.p.store.get_payload(b.payload_checksum))

    def test_6_normalized_separately_inspectable(self):
        b = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80")])
        obs = self.p.store.list_observations(b.id)[0]
        self.assertEqual(obs.raw_values["model"], "qx80")
        self.assertEqual(obs.normalized_values["model"], "QX80")   # normalized differs from raw

    def test_7_upload_or_parse_does_not_create_facts(self):
        # Non-authoritative source: rows parse into observations but never facts.
        raw = "x"
        b = self.p.ingestion.ingest(source_id="src_feed", profile_version=1,
                                    rows=[dict(stock_number="N1", vin=GOOD_VIN, model="qx80")],
                                    raw_text=raw, scope="store:HG", entity_kind="vehicle",
                                    fact_type="vehicle_present")
        self.assertTrue(self.p.store.list_observations(b.id))     # observation exists
        self.assertEqual(self._facts(), 0)                        # but no business fact

    def test_8_exact_replay_no_duplicate_effect(self):
        rows = [dict(stock_number="N1", vin=GOOD_VIN, model="qx80")]
        b1 = self.p.ingest_dms(rows)
        f1 = self._facts()
        b2 = self.p.ingest_dms(rows)                              # identical payload
        self.assertEqual(b1.id, b2.id)
        self.assertEqual(self._facts(), f1)
        n = self.p.store.conn.execute("SELECT COUNT(*) c FROM import_batch").fetchone()["c"]
        self.assertEqual(n, 1)

    def test_9_corrected_replay_preserves_history(self):
        rows = [dict(stock_number="N1", vin=GOOD_VIN, model="qx80", mileage="5")]
        b1 = self.p.ingest_dms(rows)
        obs1 = self.p.store.list_observations(b1.id)
        b2 = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80", mileage="9")],
                               correction_of=b1.id)
        self.assertNotEqual(b1.id, b2.id)
        self.assertEqual(self.p.store.get_batch(b2.id).replay_of, b1.id)
        self.assertTrue(self.p.store.list_observations(b1.id))    # original observations preserved
        self.assertEqual(len(obs1), 1)

    def test_10_full_snapshot_requires_contract_support(self):
        b = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80")], claimed_snapshot="full")
        self.assertEqual(b.validated_snapshot_type, "full")       # dms contract supports it
        b2 = self.p.ingestion.ingest(source_id="src_feed", profile_version=1,
                                     rows=[dict(stock_number="N2", vin=GOOD_VIN, model="qx80")],
                                     raw_text="y", scope="store:HG", entity_kind="vehicle",
                                     fact_type="vehicle_present", claimed_snapshot="full")
        self.assertEqual(b2.validated_snapshot_type, "partial")   # feed contract does not support full

    def test_11_partial_snapshot_absence_no_removal(self):
        va = "1GNSKBKC5FR00000A"; vb = "1GNSKBKC5FR00000B"
        self.p.ingest_dms([dict(stock_number="A", vin=va, model="qx80")], claimed_snapshot="partial")
        b2 = self.p.ingest_dms([dict(stock_number="B", vin=vb, model="qx80")], claimed_snapshot="partial")
        absent = [o for o, c in self.p.store.recon_for_batch(b2.id).items() if o == "absent_in_full_snapshot"]
        self.assertEqual(absent, [])
        # A's fact remains current (partial absence removes nothing)
        ua = self.p.store.find_vehicle_by_vin(va, "store:HG")
        self.assertTrue(self.p.store.facts_for("vehicle", ua.id, "vehicle_present", "store:HG", only_current=True))

    def test_12_full_snapshot_absence_only_signal(self):
        va = "1GNSKBKC5FR00000A"; vb = "1GNSKBKC5FR00000B"
        self.p.ingest_dms([dict(stock_number="A", vin=va, model="qx80")], claimed_snapshot="full")
        b2 = self.p.ingest_dms([dict(stock_number="B", vin=vb, model="qx80")], claimed_snapshot="full")
        outcomes = self.p.store.recon_for_batch(b2.id)
        self.assertIn("absent_in_full_snapshot", outcomes)        # A absent -> a signal
        ua = self.p.store.find_vehicle_by_vin(va, "store:HG")
        self.assertTrue(self.p.store.facts_for("vehicle", ua.id, "vehicle_present", "store:HG", only_current=True),
                        "absence must NOT remove or retire the prior fact")

    def test_13_explicit_zero_remains_zero(self):
        b = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80", mileage="0")])
        obs = self.p.store.list_observations(b.id)[0]
        self.assertEqual(obs.normalized_values["mileage"], 0)
        self.assertIsInstance(obs.normalized_values["mileage"], int)

    def test_14_blank_distinct_from_zero(self):
        b = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80", mileage="")])
        obs = self.p.store.list_observations(b.id)[0]
        self.assertIs(obs.normalized_values["mileage"], Special.BLANK)
        self.assertNotEqual(obs.normalized_values["mileage"], 0)

    def test_15_unknown_distinct_from_na(self):
        self.assertIs(normalize_scalar("UNKNOWN"), Special.UNKNOWN)
        self.assertIs(normalize_scalar("N/A"), Special.NA)
        self.assertNotEqual(Special.UNKNOWN, Special.NA)
        self.assertIsNot(normalize_scalar(None), normalize_scalar(""))  # MISSING vs BLANK distinct

    def test_16_invalid_value_cannot_become_authoritative_fact(self):
        b = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80", mileage="abc")])
        self.assertEqual(b.quarantined_count, 1)
        self.assertEqual(b.accepted_count, 0)
        self.assertEqual(self._facts(), 0)

    def test_31_every_row_has_reconciliation_outcome(self):
        rows, _ = self.cases["conflicting_duplicate"]
        b = self.p.ingest_dms(rows)
        # count only row-linked reconciliations (absence signals are not rows)
        n = self.p.store.conn.execute(
            "SELECT COUNT(*) c FROM reconciliation_result WHERE import_batch_id=? AND source_observation_id IS NOT NULL",
            (b.id,)).fetchone()["c"]
        self.assertEqual(n, b.row_count)

    def test_32_counts_balance_to_batch_totals(self):
        rows, _ = self.cases["conflicting_duplicate"]
        b = self.p.ingest_dms(rows)
        total = (b.accepted_count + b.rejected_count + b.quarantined_count +
                 b.duplicate_count + b.conflicting_count + b.unresolved_count)
        self.assertEqual(total, b.row_count)

    def test_33_persistence_survives_restart(self):
        b = self.p.ingest_dms([dict(stock_number="N1", vin=GOOD_VIN, model="qx80")])
        self.p.close()
        p2 = Phase2(self.path)
        try:
            self.assertIsNotNone(p2.store.get_batch(b.id))
            self.assertTrue(p2.store.list_observations(b.id))
        finally:
            p2.close()

    def test_34_migration_rerun_is_safe(self):
        v = self.p.stack.db.version()
        again = self.p.stack.db.migrate()          # rerun
        self.assertEqual(again, v)


if __name__ == "__main__":
    unittest.main()
