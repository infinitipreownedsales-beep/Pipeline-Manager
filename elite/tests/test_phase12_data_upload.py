"""Browser file upload for the four daily sources: the operator chooses a file in the browser; Elite
parses multipart/form-data, sanitizes the filename, stages it in the uploads folder, and runs it through
the EXISTING ingestion orchestrator. Success updates freshness; failure never does; traversal is rejected;
no server-path text box remains."""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, INV_VALID, RETAIL_VALID, LOANER_FULL, INV_MALFORMED_DELIM
from elite.workflow.fixtures import SCOPE


class TestDataUpload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["ELITE_UPLOAD_DIR"] = os.path.join(self.tmp, "uploads")
        self.p = Phase11(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        self.app._p11 = self.p                       # expose the ops orchestrator to the operator app
        self.conn = self.p.stack.db.conn
        self.full = self.p.p10.login(self.p.p10.op_full)

    def tearDown(self):
        os.environ.pop("ELITE_UPLOAD_DIR", None)
        self.p.close()

    def _upload(self, contract, filename, content):
        return self.full.post("/data/import", form={"contract": contract},
                              files={"file": (filename, content)})

    def _runs(self, contract):
        return self.conn.execute("SELECT COUNT(*) FROM import_run WHERE source_contract=? AND store_scope=?",
                                 (contract, SCOPE)).fetchone()[0]

    def _accepted_runs(self, contract):
        return self.conn.execute(
            "SELECT COUNT(*) FROM import_run WHERE source_contract=? AND store_scope=? AND accepted_count>0",
            (contract, SCOPE)).fetchone()[0]

    # 1-4. each source's browser upload reaches its EXISTING importer (an import_run is recorded)
    def test_inventory_upload_reaches_importer(self):
        self._upload("new_inventory_current", "2026-08-14 Inventory.csv", INV_VALID)
        self.assertGreaterEqual(self._runs("new_inventory_current"), 1)

    def test_retail_history_upload_reaches_importer(self):
        self._upload("retail_history", "preowned.csv", RETAIL_VALID)
        self.assertGreaterEqual(self._runs("retail_history"), 1)

    def test_retail_history_accepts_native_dms_sales_export(self):
        native = (
            "Sales Date,Stock Number,Year,Make,Model,Exterior Color,Interior Color,Trim,"
            "VIN,Days to Sell,Model Number,Vehicle Cost,Vehicle Price,Gross Profit\n"
            '20210312,P10408,2014,LINCOLN,MKZ,GRAY,,4DR SDN FWD,'
            '3LN6L2GK3ER821746,-288,,"15,200.67","17,427.38","1,813.71"\n'
        )
        self._upload("retail_history", "10YEARSOFUSEDCARSALES.csv", native)

        run = self.conn.execute(
            "SELECT state, accepted_count, rejected_count FROM import_run "
            "WHERE source_contract=? AND store_scope=? "
            "ORDER BY created_at DESC LIMIT 1",
            ("retail_history", SCOPE),
        ).fetchone()

        self.assertIsNotNone(run)
        self.assertIn(run["state"], ("COMPLETED", "COMPLETED_WITH_WARNINGS"))
        self.assertGreaterEqual(run["accepted_count"], 1)
        self.assertEqual(run["rejected_count"], 0)

    def test_retail_history_preserves_repeat_vin_as_separate_sale_observations(self):
        native = (
            "Sales Date,Stock Number,Year,Make,Model,Exterior Color,Interior Color,Trim,"
            "VIN,Days to Sell,Model Number,Vehicle Cost,Vehicle Price,Gross Profit\n"
            '20200716,XP3774A,2015,JEEP,WRANGLER UNLIMI,,,SPORT,'
            '1C4BJWDG1FL754497,17,,,"23,499.76",0\n'
            '20240823,T47570B,2015,JEEP,WRANGLER UNLIMI,,,SPORT,'
            '1C4BJWDG1FL754497,29,,,"19,999.00",0\n'
        )
        self._upload("retail_history", "repeat-vin-history.csv", native)

        run = self.conn.execute(
            "SELECT import_batch_id, accepted_count, duplicate_count "
            "FROM import_run WHERE source_contract=? AND store_scope=? "
            "ORDER BY created_at DESC LIMIT 1",
            ("retail_history", SCOPE),
        ).fetchone()

        self.assertIsNotNone(run)
        self.assertEqual(run["accepted_count"], 2)
        self.assertEqual(run["duplicate_count"], 0)

        batch = self.conn.execute(
            "SELECT conflicting_count, quarantined_count FROM import_batch WHERE id=?",
            (run["import_batch_id"],),
        ).fetchone()
        self.assertEqual(batch["conflicting_count"], 0)
        self.assertEqual(batch["quarantined_count"], 0)

        obs = self.conn.execute(
            "SELECT COUNT(*) AS n FROM source_observation "
            "WHERE import_batch_id=? AND acceptance_status='accepted'",
            (run["import_batch_id"],),
        ).fetchone()["n"]
        self.assertEqual(obs, 2)

    def test_retail_history_v3_normalizes_preowned_dts_and_economics(self):
        native = (
            "Sales Date,Stock Number,Year,Make,Model,Exterior Color,Interior Color,Trim,"
            "VIN,Days to Sell,Model Number,Vehicle Cost,Vehicle Price,Gross Profit\n"
            '20210312,P10408,2014,LINCOLN,MKZ,GRAY,,4DR SDN FWD,'
            '3LN6L2GK3ER821746,-288,ABC123,"15,200.67","17,427.38","1,813.71"\n'
        )
        self._upload("retail_history", "retail-v3.csv", native)

        run = self.conn.execute(
            "SELECT import_batch_id FROM import_run "
            "WHERE source_contract=? AND store_scope=? "
            "ORDER BY created_at DESC LIMIT 1",
            ("retail_history", SCOPE),
        ).fetchone()
        self.assertIsNotNone(run)

        batch = self.conn.execute(
            "SELECT schema_profile_version, accepted_count, quarantined_count "
            "FROM import_batch WHERE id=?",
            (run["import_batch_id"],),
        ).fetchone()

        self.assertEqual(batch["schema_profile_version"], 3)
        self.assertEqual(batch["accepted_count"], 1)
        self.assertEqual(batch["quarantined_count"], 0)

        import json
        obs = self.conn.execute(
            "SELECT raw_values, normalized_values FROM source_observation "
            "WHERE import_batch_id=? LIMIT 1",
            (run["import_batch_id"],),
        ).fetchone()

        raw = json.loads(obs["raw_values"])
        norm = json.loads(obs["normalized_values"])

        self.assertEqual(raw["days_to_sell"], "-288")
        self.assertEqual(norm["sold_date"], "2021-03-12")
        self.assertEqual(norm["stock_number"], "P10408")
        self.assertEqual(norm["year"], 2014)
        self.assertEqual(norm["make"], "LINCOLN")
        self.assertEqual(norm["model"], "MKZ")
        self.assertEqual(norm["trim"], "4DR SDN FWD")
        self.assertEqual(norm["days_to_sell"], -288)
        self.assertEqual(norm["model_number"], "ABC123")
        self.assertEqual(norm["vehicle_cost"], 15200.67)
        self.assertEqual(norm["price"], 17427.38)
        self.assertEqual(norm["gross_profit"], 1813.71)

    def test_loaner_upload_reaches_importer(self):
        self._upload("service_loaner_fleet", "icv.csv", LOANER_FULL)
        self.assertGreaterEqual(self._runs("service_loaner_fleet"), 1)

    def test_loaner_upload_projects_to_requested_operator_scope(self):
        """Regression: accepted ICV rows project into the operator-requested scope,
        never the Phase-6 fixture construction scope."""
        from elite.ui.views.operator import _run_upload

        operator_scope = "store:HG_INFINITI_JACKSON"
        payload = LOANER_FULL.encode("utf-8") if isinstance(LOANER_FULL, str) else LOANER_FULL
        msg = _run_upload(self.app, operator_scope, "service_loaner_fleet", ("icv.csv", payload))
        self.assertIn("COMPLETED", msg)

        run = self.conn.execute(
            "SELECT import_batch_id FROM import_run WHERE source_contract=? AND store_scope=? "
            "ORDER BY created_at DESC LIMIT 1",
            ("service_loaner_fleet", operator_scope),
        ).fetchone()
        self.assertIsNotNone(run)
        batch_id = run["import_batch_id"]

        correct = self.conn.execute(
            "SELECT COUNT(*) FROM service_loaner_unit WHERE store_scope=? AND last_accepted_snapshot=?",
            (operator_scope, batch_id),
        ).fetchone()[0]
        wrong = self.conn.execute(
            "SELECT COUNT(*) FROM service_loaner_unit WHERE store_scope=? AND last_accepted_snapshot=?",
            (SCOPE, batch_id),
        ).fetchone()[0]

        self.assertGreater(correct, 0)
        self.assertEqual(wrong, 0)

    def test_speed_to_sell_upload_reaches_importer(self):
        self._upload("speed_to_sell", "sts.xlsx", b"PK\x03\x04 not-a-real-xlsx")
        self.assertGreaterEqual(self._runs("speed_to_sell"), 1)    # reached the importer even if it rejects

    # 5. a successful import updates freshness (source no longer "not loaded")
    def test_success_updates_freshness(self):
        from elite.ui.app import source_health
        before = dict((lbl, word) for (lbl, word, _t) in source_health(self.app, SCOPE))
        self.assertEqual(before["Inventory"], "not loaded")
        self._upload("new_inventory_current", "inv.csv", INV_VALID)
        self.assertGreaterEqual(self._accepted_runs("new_inventory_current"), 1)
        after = dict((lbl, word) for (lbl, word, _t) in source_health(self.app, SCOPE))
        self.assertNotEqual(after["Inventory"], "not loaded")       # freshness advanced on success

    # 6 + 7. a malformed/unsupported file returns a useful error and does NOT update freshness
    def test_failed_import_does_not_update_freshness(self):
        r = self._upload("new_inventory_current", "bad.csv", INV_MALFORMED_DELIM)
        # the flash carries an honest non-success message; freshness stays "not loaded"
        from elite.ui.app import source_health
        after = dict((lbl, word) for (lbl, word, _t) in source_health(self.app, SCOPE))
        self.assertEqual(self._accepted_runs("new_inventory_current"), 0)
        self.assertEqual(after["Inventory"], "not loaded")

    # 8. path-traversal filename is rejected safely (nothing staged outside the uploads dir)
    def test_traversal_filename_rejected(self):
        self.full.post("/data/import", form={"contract": "new_inventory_current"},
                       files={"file": ("../../etc/passwd", INV_VALID)})
        # nothing was written above the uploads dir
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "passwd")))
        self.assertFalse(os.path.exists("/etc/passwd_elite"))
        # a legitimate name stages inside the uploads dir
        self._upload("new_inventory_current", "clean.csv", INV_VALID)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "uploads", "clean.csv")))

    # 9. no user-facing server-path text box remains; browser file inputs are present
    def test_no_path_textbox(self):
        b = self.full.get("/data").body
        self.assertNotIn("C:\\ElitePipeline\\uploads", b)
        self.assertNotIn('name=path', b)
        self.assertIn('type=file', b)
        self.assertIn('enctype="multipart/form-data"', b)

    # 10. missing file is handled without a false success
    def test_missing_file_no_false_success(self):
        r = self.full.post("/data/import", form={"contract": "new_inventory_current"})
        self.assertEqual(self._accepted_runs("new_inventory_current"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
