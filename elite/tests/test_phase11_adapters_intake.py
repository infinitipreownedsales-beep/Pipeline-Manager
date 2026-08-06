"""Phase 11 acceptance — source adapters + import idempotency/retry (items 1-11) and controlled file
intake (items 65-68)."""
import os
import tempfile
import unittest

from elite.errors import ValidationError
from elite.ops import fixtures as F
from elite.ops.adapters import run_adapter
from elite.ops.contracts import get_contract
from elite.ops.intake import content_hash
from elite.ops.fixtures import Phase11, SCOPE


class TestPhase11AdaptersIntake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase11(os.path.join(cls.tmp, "elite.db"))

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    # ---- adapters (1-6) ---------------------------------------------------
    def test_001_adapter_produces_canonical_contract(self):
        contract = get_contract("new_inventory_current")
        res = run_adapter(contract, F.INV_VALID)
        kw = res.ingest_kwargs(source_id="s", scope=SCOPE, entity_kind="vehicle",
                               fact_type="vehicle_present", claimed_snapshot="partial")
        # canonical Phase 2 ingestion contract shape
        for key in ("source_id", "profile_version", "rows", "raw_text", "scope", "entity_kind",
                    "fact_type", "claimed_snapshot"):
            self.assertIn(key, kw)
        self.assertTrue(all(isinstance(r, dict) for r in kw["rows"]))
        self.assertEqual(kw["raw_text"], F.INV_VALID)          # raw preserved verbatim

    def test_002_adapter_does_not_write_domain_state(self):
        before = self._count("business_fact")
        run_adapter(get_contract("new_inventory_current"), F.INV_VALID)   # parse only
        self.assertEqual(self._count("business_fact"), before)            # no domain write

    def test_003_unsupported_schema_fails_safely(self):
        with self.assertRaises(ValidationError):
            run_adapter(get_contract("new_inventory_current"), F.UNSUPPORTED_SCHEMA)

    def test_004_original_source_row_traceable(self):
        res = run_adapter(get_contract("new_inventory_current"), F.INV_VALID)
        self.assertIn(0, res.row_locations)
        self.assertIn("line", res.row_locations[0])            # points back at the file line

    def test_005_adapter_version_recorded(self):
        run = self.p.import_payload("new_inventory_current", F.INV_VALID, effective_time=self.p.now_iso(),
                                    chash="sha256:av")
        self.assertEqual(run["adapter_version"], 1)
        av = self.p.ops.get_adapter_version("new_inventory_current.csv", 1)
        self.assertIsNotNone(av)

    def test_006_same_content_idempotent(self):
        a = self.p.import_payload("new_inventory_current", F.INV_VALID, effective_time=self.p.now_iso(),
                                  chash="sha256:idem6")
        b = self.p.import_payload("new_inventory_current", F.INV_VALID, effective_time=self.p.now_iso(),
                                  chash="sha256:idem6")
        self.assertEqual(a["id"], b["id"])

    # ---- import lifecycle (7-11) -----------------------------------------
    def test_007_duplicate_upload_no_duplicate_facts(self):
        self.p.import_payload("new_inventory_current", F.INV_VALID, effective_time=self.p.now_iso(),
                              chash="sha256:dup7")
        n1 = self._count("business_fact")
        self.p.import_payload("new_inventory_current", F.INV_VALID, effective_time=self.p.now_iso(),
                              chash="sha256:dup7")
        self.assertEqual(self._count("business_fact"), n1)

    def test_008_failed_import_preserves_prior_accepted(self):
        sid = self.p.source_id("new_inventory_current")
        good = self.p.import_payload("new_inventory_current", F.INV_FULL, effective_time=self.p.now_iso(),
                                     chash="sha256:good8")
        last = self.p.orch._last_completed(sid, SCOPE)
        self.assertEqual(last, good["id"])
        self.p.import_payload("new_inventory_current", F.INV_VALID, chash="sha256:fail8", fail_at="ingest")
        self.assertTrue(self.p.orch.accepted_state_intact(sid, SCOPE, last))   # prior state intact

    def test_009_partial_import_not_complete(self):
        run = self.p.import_payload("new_inventory_current", F.INV_VALID, chash="sha256:part9",
                                    fail_at="ingest")
        self.assertEqual(run["state"], "FAILED")
        self.assertNotIn(run["state"], ("COMPLETED", "COMPLETED_WITH_WARNINGS"))

    def test_010_retry_links_to_failed(self):
        bad = self.p.import_payload("new_inventory_current", F.INV_VALID, chash="sha256:r10",
                                    fail_at="ingest")
        rt = self.p.orch.retry(bad["id"], payload=F.INV_VALID, content_hash="sha256:r10b",
                               effective_time=self.p.now_iso())
        self.assertEqual(rt["retry_of"], bad["id"])
        self.assertEqual(rt["state"], "COMPLETED")

    def test_011_import_failure_visible_and_safe(self):
        bad = self.p.import_payload("new_inventory_current", F.INV_VALID, chash="sha256:vis11",
                                    fail_at="ingest")
        errs = self.p.ops.list_import_errors(bad["id"])
        self.assertTrue(errs)
        for e in errs:                                    # safe message only — no secret/raw row
            self.assertNotIn("pw", (e["safe_message"] or ""))
            self.assertNotIn("pepper", (e["safe_message"] or "").lower())

    # ---- controlled file intake (65-68) ----------------------------------
    def test_065_upload_allowlist_enforced(self):
        with self.assertRaises(ValidationError):
            self.p.intake.accept(filename="data.xml", payload="<x/>", scope=SCOPE)

    def test_066_file_size_limit_enforced(self):
        from elite.ops.intake import FileIntake
        tiny = FileIntake(self.p.ops, max_bytes=4)
        with self.assertRaises(ValidationError) as c:
            tiny.accept(filename="big.csv", payload="123456", scope=SCOPE)
        self.assertIn("file_too_large", c.exception.technical_detail)

    def test_067_filename_and_traversal_sanitized(self):
        with self.assertRaises(ValidationError) as c:
            self.p.intake.accept(filename="../../etc/passwd", payload="x", scope=SCOPE)
        self.assertIn("path_traversal", c.exception.technical_detail)

    def test_068_rejected_files_quarantined(self):
        try:
            self.p.intake.accept(filename="evil.exe", payload="MZ", scope=SCOPE)
        except ValidationError:
            pass
        q = self.p.ops.conn.execute(
            "SELECT * FROM source_file_receipt WHERE status='quarantined' AND media_type='.exe'").fetchall()
        self.assertTrue(q)

    def _count(self, table):
        return self.p.stack.db.conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]


if __name__ == "__main__":
    unittest.main()
