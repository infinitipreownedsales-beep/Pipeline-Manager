"""Translation & Identity Center (route-level) — the governance/mutation boundary.

Proves: opening the page creates NO identity truth; identity is created only through an explicit,
capability-gated, idempotent import (or human resolve/approve/retire); mutations require `identity.govern`,
are written to the audit trail (who/when) and never hard-delete; the live store surfaces only real observed
unresolved values; the certified plan and schema (v12) are untouched."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.identity.translation import TranslationStore, SemanticMapping, FamilyKey


class TestTranslationCenter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)                 # holds identity.govern
        self.viewer = self.p.login(self.p.op_readonly)           # workspace.view + review, NOT identity.govern

    def tearDown(self):
        self.p.close()

    def _store(self):
        return TranslationStore(self.p.app.prefs, SCOPE)

    # opening the center is read-only: it renders, but creates no observations/mappings
    def test_get_is_read_only(self):
        r = self.full.get("/admin/translation")
        self.assertEqual(r.status, 200)
        self.assertIn("Not initialized", r.body)
        self.assertFalse(self._store().is_initialized())          # GET did NOT seed anything
        self.full.get("/admin/translation")                       # a second view still creates nothing
        self.assertFalse(self._store().is_initialized())

    # import requires the identity.govern capability
    def test_import_requires_capability(self):
        r = self.viewer.post("/admin/translation/import-reviewed-charts", {})
        self.assertEqual(r.status, 403)                           # view-only operator is walled out
        self.assertFalse(self._store().is_initialized())         # nothing created

    # governed import initializes; distinguishes observations / approved mappings / proposed interpretations
    def test_governed_import_and_idempotent(self):
        r = self.full.post("/admin/translation/import-reviewed-charts", {})
        self.assertEqual(r.status, 303)
        st = self._store()
        self.assertTrue(st.is_initialized())
        self.assertGreater(len(st.observations()), 0)
        self.assertTrue(any(m.approval == "approved" for m in st.semantic_mappings()))   # SAME_AS approved
        self.assertTrue(all(r.approval == "proposed" for r in st.variant_rows()))        # interpretation proposed
        n_obs, n_map, n_rows = len(st.observations()), len(st.semantic_mappings()), len(st.variant_rows())
        self.full.post("/admin/translation/import-reviewed-charts", {})                  # re-run
        st2 = self._store()
        self.assertEqual((len(st2.observations()), len(st2.semantic_mappings()), len(st2.variant_rows())),
                         (n_obs, n_map, n_rows))                                          # idempotent, no dupes

    def test_corrected_colors_approved_families_proposed(self):
        self.full.post("/admin/translation/import-reviewed-charts", {})
        b = self.full.get("/admin/translation").body
        self.assertIn("2T Dynamic Metal", b)                     # XLF corrected, approved
        self.assertIn("2T Radiant White", b)                     # XKJ
        self.assertIn("QX80·LUXE·2WD", b)                        # appears as a PROPOSED interpretation
        self.assertIn("Proposed interpretations", b)

    # approving the interpretation moves the family into the approved preferred-order view (still unresolved order)
    def test_approve_interpretation_then_preferred_order(self):
        self.full.post("/admin/translation/import-reviewed-charts", {})
        fam = FamilyKey("INFINITI", "QX80", "LUXE", "2WD")
        for r in self._store().variant_rows(fam):
            self.full.post("/admin/translation/approve-variant",
                           {"family": fam.as_str(), "raw": r.raw_code, "gen": r.generation_id, "package": r.package})
        b = self.full.get("/admin/translation").body
        self.assertIn("Approved families", b)
        # pending BASE + priced package -> still surfaced, never auto-substituted
        self.assertIn("BASE preferred — orderability unresolved", b)
        self.assertEqual(self._store().resolve_order(fam)["status"], "unresolved")

    # a genuinely-unknown observed value resolves without coding, and reuses forever
    def test_resolve_unknown_governed(self):
        self.full.post("/admin/translation/import-reviewed-charts", {})
        self._store().record_observation("NNA_ORDER_PORTAL", "exterior", "ZZZ", as_of="2026-08-19", proof_ref="c")
        self.assertIn("ZZZ", self.full.get("/admin/translation").body)      # in Needs attention
        r = self.full.post("/admin/translation/resolve",
                           {"source": "NNA_ORDER_PORTAL", "stype": "exterior", "raw": "ZZZ", "name": "Midnight"})
        self.assertEqual(r.status, 303)
        self.assertEqual(self._store().translate("NNA_ORDER_PORTAL", "exterior", "ZZZ")[1], "Midnight")

    # retire is a soft, audited action — history preserved, never hard-deleted
    def test_retire_is_soft_and_audited(self):
        self.full.post("/admin/translation/import-reviewed-charts", {})
        r = self.full.post("/admin/translation/retire",
                           {"source": "NNA_ORDER_PORTAL", "stype": "exterior", "raw": "XLF", "scope": "QX80"})
        self.assertEqual(r.status, 303)
        st = self._store()
        m = [x for x in st.semantic_mappings() if x.raw_value == "XLF"][0]
        self.assertEqual((m.approval, m.active), ("retired", False))         # soft-retired, row preserved
        self.assertIsNone(st.translate("NNA_ORDER_PORTAL", "exterior", "XLF", model="QX80"))  # stops translating
        actions = {a["action"] for a in st.audit_log()}
        self.assertIn("semantic.retire", actions)                            # audited
        self.assertTrue(all(a["actor"] == self.p.op_full for a in st.audit_log() if a["action"] == "semantic.retire"))

    def test_audit_records_who_and_when(self):
        self.full.post("/admin/translation/import-reviewed-charts", {})
        log = self._store().audit_log()
        self.assertTrue(log)
        self.assertTrue(all(a.get("actor") and a.get("at") for a in log))    # who + when on every entry
        self.assertEqual({a["actor"] for a in log}, {self.p.op_full})

    # the live store shows only REAL observed unresolved values (no synthetic records)
    def test_no_synthetic_unresolved_after_import(self):
        self.full.post("/admin/translation/import-reviewed-charts", {})
        self.assertEqual(self._store().unresolved_translations(), [])        # every observed value is placed/mapped

    def test_data_health_shows_state(self):
        d0 = self.full.get("/data").body
        self.assertIn("not initialized", d0)                                 # before import
        self.full.post("/admin/translation/import-reviewed-charts", {})
        self.assertIn("/admin/translation", self.full.get("/data").body)

    def test_admin_index_and_schema(self):
        self.assertIn("/admin/translation", self.full.get("/admin").body)
        self.full.post("/admin/translation/import-reviewed-charts", {})
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
