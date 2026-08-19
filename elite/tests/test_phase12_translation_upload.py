"""Slice A — the upload-resolution maintenance loop.

Proves: an ingested source file (1) auto-records raw observations, (2) resolves known vocabulary silently,
(3) preserves new raw values, (4) surfaces only genuinely-new meanings, (5) lets an authorized user resolve
them, and (6) reuses the approved mapping on the next upload with no code. Identity/family/segment are NOT
wired to certified CPO demand or ORDER here — this records observations only."""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE
from elite.identity.translation import TranslationStore, SemanticMapping
from elite.identity.ingest import observe_source_rows
from elite.tests.test_phase12_real_demand_planning_bridge import sts_workbook, _row
from elite.ops.intake import content_hash


class TestObserveRows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.store = TranslationStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_known_resolves_new_surfaces_and_reuses(self):
        # a known exterior colour is pre-approved; an unknown one is not
        self.store.upsert_semantic(SemanticMapping("speed_to_sell", "exterior", "KH3", "KH3", "Black Obsidian",
                                                   "", "approved", ("seed",)))
        rows = [{"model_code": "83316", "exterior": "KH3", "interior": "G"},
                {"model_code": "83316", "exterior": "ZZ9", "interior": "G"}]     # ZZ9 = new vocabulary
        summ = observe_source_rows(self.store, "speed_to_sell", rows, as_of="2026-08-19", proof_ref="f1")
        # every raw value preserved as an observation
        raws = {o["raw_value"] for o in self.store.observations()}
        self.assertTrue({"83316", "KH3", "ZZ9", "G"} <= raws)
        # only genuinely-new meanings surface (ZZ9 exterior; 83316 model_code not yet placed); KH3/G do not
        new = dict((t, r) for (t, r) in summ["new_unresolved"])
        self.assertEqual(new.get("exterior"), "ZZ9")
        self.assertNotIn(("exterior", "KH3"), summ["new_unresolved"])
        # authorized resolution, then a second upload reuses it automatically
        self.store.upsert_semantic(SemanticMapping("speed_to_sell", "exterior", "ZZ9", "ZZ9", "Midnight", "",
                                                   "approved", ("operator",)))
        summ2 = observe_source_rows(self.store, "speed_to_sell", rows, as_of="2026-08-20", proof_ref="f2")
        self.assertNotIn(("exterior", "ZZ9"), summ2["new_unresolved"])   # reused, no longer new


class TestUploadLoop(unittest.TestCase):
    """The real browser upload path (/data/import) drives the hook end to end."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["ELITE_UPLOAD_DIR"] = os.path.join(self.tmp, "uploads")
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.app = self.p.app
        self.app._p11 = self.p
        self.full = self.p.p10.login(self.p.p10.op_full)
        # a colour already resolved for THIS source on a prior upload — "known vocabulary" for speed_to_sell
        TranslationStore(self.app.prefs, SCOPE).upsert_semantic(
            SemanticMapping("speed_to_sell", "exterior", "KH3", "KH3", "Black Obsidian", "", "approved",
                            ("prior-upload",)))

    def tearDown(self):
        os.environ.pop("ELITE_UPLOAD_DIR", None)
        self.p.close()

    def _store(self):
        return TranslationStore(self.app.prefs, SCOPE)

    def _upload_sts(self, filename, extra_ext):
        rows = [_row("202608", "N1", "20", "83316", "KH3", "G", "QX80 LUXE 2WD"),      # KH3 = known colour
                _row("202608", "N2", "22", "83316", extra_ext, "G", "QX80 LUXE 2WD")]  # extra_ext may be new
        xlsx = sts_workbook(rows)
        return self.full.post("/data/import", form={"contract": "speed_to_sell"},
                              files={"file": (filename, xlsx)})

    def test_end_to_end_upload_resolution_loop(self):
        r = self._upload_sts("sts-aug.xlsx", "WZ7")            # WZ7 is a brand-new exterior code
        self.assertEqual(r.status, 303)
        st = self._store()
        # (2)+(3) known KH3 auto-resolves; new WZ7 preserved as an observation
        raws = {o["raw_value"] for o in st.observations()}
        self.assertIn("WZ7", raws)
        self.assertIn("KH3", raws)
        # (4) only the new meaning surfaces; KH3 (approved SAME_AS from seed) does not
        unresolved = {(o["semantic_type"], o["raw_value"]) for o in st.unresolved_translations()}
        self.assertIn(("exterior", "WZ7"), unresolved)
        self.assertNotIn(("exterior", "KH3"), unresolved)
        # Data Health surfaces the unresolved count with the resolution link
        d = self.full.get("/data").body
        self.assertIn("unresolved", d)
        self.assertIn("/admin/translation", d)
        # (5) authorized user resolves it in the Translation Center
        self.full.post("/admin/translation/resolve",
                       {"source": "speed_to_sell", "stype": "exterior", "raw": "WZ7", "name": "Storm Gray"})
        self.assertEqual(self._store().translate("speed_to_sell", "exterior", "WZ7")[1], "Storm Gray")
        # (6) a later upload of the same vocabulary reuses the mapping — no longer unresolved
        self._upload_sts("sts-sep.xlsx", "WZ7")
        st2 = self._store()
        self.assertNotIn(("exterior", "WZ7"),
                         {(o["semantic_type"], o["raw_value"]) for o in st2.unresolved_translations()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
