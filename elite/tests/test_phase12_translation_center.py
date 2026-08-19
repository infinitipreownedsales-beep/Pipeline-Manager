"""Translation & Identity Center (route-level) — the authorized maintenance surface and its Data-Health entry
point. An authorized user resolves unresolved language and approves mappings with no coding; the certified
plan and schema (v12) are untouched."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.identity.translation import TranslationStore, SemanticMapping


class TestTranslationCenter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_center_renders_seed_families_and_corrected_colors(self):
        b = self.full.get("/admin/translation").body
        self.assertEqual(self.full.get("/admin/translation").status, 200)
        self.assertIn("Translation &amp; Identity", b)
        self.assertIn("2T Dynamic Metal", b)                       # corrected XLF mapping, source-backed
        self.assertIn("2T Radiant White", b)                       # XKJ
        self.assertIn("QX80·LUXE·2WD", b)                          # commercial family key
        self.assertIn("QX80·PURE·2WD", b)
        self.assertIn("QX80·PURE·4WD", b)                          # distinct family (drivetrain)
        # QX80 LUXE 2WD preferred order is unresolved (pending BASE, priced package not substituted)
        self.assertIn("BASE preferred — orderability unresolved", b)

    def test_data_health_shows_unresolved_link(self):
        # seed first (via the center), then plant an unresolved raw value
        self.full.get("/admin/translation")
        TranslationStore(self.p.app.prefs, SCOPE).record_observation(
            "NNA_ORDER_PORTAL", "exterior", "ZZZ", as_of="2026-08-19", proof_ref="chart")
        d = self.full.get("/data").body
        self.assertIn("Translation &amp; Identity", d)
        self.assertIn("/admin/translation", d)
        self.assertIn("unresolved", d)

    def test_resolve_unknown_without_coding(self):
        self.full.get("/admin/translation")                         # seed
        TranslationStore(self.p.app.prefs, SCOPE).record_observation(
            "NNA_ORDER_PORTAL", "exterior", "ZZZ", as_of="2026-08-19", proof_ref="chart")
        self.assertIn("ZZZ", self.full.get("/admin/translation").body)   # surfaces in Needs attention
        r = self.full.post("/admin/translation/resolve",
                           {"source": "NNA_ORDER_PORTAL", "stype": "exterior", "raw": "ZZZ",
                            "name": "Midnight Blue", "scope": ""})
        self.assertEqual(r.status, 303)
        st = TranslationStore(self.p.app.prefs, SCOPE)
        self.assertEqual(st.translate("NNA_ORDER_PORTAL", "exterior", "ZZZ")[1], "Midnight Blue")  # reusable now
        self.assertFalse(any(o["raw_value"] == "ZZZ" for o in st.unresolved_translations()))

    def test_approve_proposed_mapping(self):
        self.full.get("/admin/translation")                         # seed
        TranslationStore(self.p.app.prefs, SCOPE).upsert_semantic(
            SemanticMapping("NNA_ORDER_PORTAL", "trim", "AUTOG", "AUTOGRAPH", "Autograph", "", "proposed",
                            ("chart",)))
        self.assertIsNone(TranslationStore(self.p.app.prefs, SCOPE).translate("NNA_ORDER_PORTAL", "trim", "AUTOG"))
        r = self.full.post("/admin/translation/approve",
                           {"source": "NNA_ORDER_PORTAL", "stype": "trim", "raw": "AUTOG", "scope": ""})
        self.assertEqual(r.status, 303)
        self.assertEqual(TranslationStore(self.p.app.prefs, SCOPE).translate(
            "NNA_ORDER_PORTAL", "trim", "AUTOG")[1], "Autograph")

    def test_admin_index_lists_translation_center(self):
        self.assertIn("/admin/translation", self.full.get("/admin").body)

    def test_certified_and_schema_unchanged(self):
        self.full.get("/admin/translation")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
