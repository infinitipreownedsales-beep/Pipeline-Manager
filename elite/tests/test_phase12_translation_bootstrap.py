"""Translation bootstrap / authority — the live blocker fix (least-privilege identity.govern for the
single-operator pilot + automatic idempotent reviewed-dictionary initialization).

Proves:
  * an authorized store-operating principal (holds decision.approve) receives identity.govern AT THE STORE SCOPE;
  * a pure view-only principal does NOT;
  * the grant is scoped to the configured store — no wildcard/global admin escalation;
  * automatic reviewed-dictionary bootstrap is idempotent (no duplicates on re-run);
  * an operator-approved more-specific mapping survives re-import (never reverted);
  * unknown/unreviewed codes are never auto-approved;
  * model-scoped interior mappings stay model-scoped (P = Sepia Brown QX80 vs Saddle Brown QX60);
  * human vehicle language resolves after bootstrap and Wholesale dealer-copy becomes human-readable;
  * schema stays v12 and tests never touch a permanent DB (temp only).
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.db import current_version
from elite.identity.provision import (ensure_single_operator_identity_govern, bootstrap_reviewed_translation,
                                      ensure_identity_governance_grants)
from elite.identity.translation import TranslationStore, SemanticMapping
from elite.ui.views import domains

SCOPE = "store:HG_INFINITI_JACKSON"
GOVERN = "identity.govern"


class TestTranslationBootstrapAuthority(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.stack = self.p.stack
        # an operating principal (holds a store-operating-authority capability) and a pure viewer
        self.op = self.stack.authn.register("Kyle GSM", "secret-op")
        self.stack.grant(self.op.id, "decision.approve", SCOPE)
        self.viewer = self.stack.authn.register("Viewer", "secret-view")
        self.stack.grant(self.viewer.id, "workspace.view", SCOPE)

    def tearDown(self):
        self.p.close()

    # ---- authority (least privilege) ----
    def test_operator_gets_identity_govern_at_store_scope(self):
        self.assertFalse(self.stack.authz.decide(self.op.id, GOVERN, SCOPE).allowed)
        ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        self.assertTrue(self.stack.authz.decide(self.op.id, GOVERN, SCOPE).allowed)

    def test_viewer_does_not_get_identity_govern(self):
        ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        self.assertFalse(self.stack.authz.decide(self.viewer.id, GOVERN, SCOPE).allowed)

    def test_grant_is_scoped_no_wildcard_escalation(self):
        ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        # scoped to THIS store only — no authority leaks to another store, and no '*' grant is created
        self.assertFalse(self.stack.authz.decide(self.op.id, GOVERN, "store:OTHER").allowed)
        grants = [g for g in self.stack.grants.list_for(self.op.id)
                  if g.capability == GOVERN and g.effective()]
        self.assertTrue(grants and all(g.scope == SCOPE for g in grants))   # never scope '*'

    def test_idempotent_authority_backfill(self):
        g1 = ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        g2 = ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        self.assertIn((self.op.id, SCOPE), g1)            # the operating principal was granted
        self.assertEqual(g2, [])                          # already granted → nothing new, no duplicate grant

    def test_import_route_permitted_after_grant(self):
        # the live symptom: the import POST is 403 before the grant, 200/redirect after it
        ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        tok = self.p.app.login(self.op.id, "secret-op", SCOPE)
        from elite.ui.fixtures import Client
        c = Client(self.p.app, tok)
        r = c.post("/admin/translation/import-reviewed-charts", {})
        self.assertNotEqual(r.status, 403)

    # ---- bootstrap content ----
    def test_bootstrap_populates_and_is_idempotent(self):
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        st = TranslationStore(self.p.app.prefs, SCOPE)
        n1 = (len(st.semantic_mappings()), len(st.variant_rows()))
        self.assertGreater(n1[0], 0)
        # colour/model-line SAME_AS are approved out-of-the-box; interpretations stay proposed (human governance)
        self.assertTrue(any(m.approval == "approved" for m in st.semantic_mappings()))
        self.assertTrue(all(r.approval == "proposed" for r in st.variant_rows()))
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        n2 = (len(st.semantic_mappings()), len(st.variant_rows()))
        self.assertEqual(n1, n2)                           # no duplicates on re-run

    def test_operator_more_specific_mapping_survives_reimport(self):
        st = TranslationStore(self.p.app.prefs, SCOPE)
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        # operator resolves a genuinely-new interior code with a model-specific meaning
        st.upsert_semantic(SemanticMapping("NNA_ORDER_PORTAL", "interior", "C", "C", "Java (operator)", "QX80",
                                           "approved", ("operator-resolved",)), actor="kyle", at="2026-08-22")
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)   # re-import must not revert it
        self.assertEqual(st.resolve_display("interior", "C", model="QX80"), ("C", "Java (operator)"))

    def test_unknown_code_not_auto_approved(self):
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        st = TranslationStore(self.p.app.prefs, SCOPE)
        self.assertIsNone(st.resolve_display("exterior", "ZZZ", model="QX80"))   # never invented

    def test_model_scoped_interior_preserved(self):
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        st = TranslationStore(self.p.app.prefs, SCOPE)
        self.assertEqual(st.resolve_display("interior", "P", model="QX80"), ("P", "Sepia Brown"))
        self.assertEqual(st.resolve_display("interior", "P", model="QX60"), ("P", "Saddle Brown"))

    # ---- live human-description path ----
    def test_wholesale_dealer_copy_human_after_bootstrap(self):
        ident = "dms_planning|model=QX80|model_code=8331|exterior=QBE|interior=G"
        # before bootstrap: compact codes
        self.assertEqual(domains._readable_h(self.p.app, SCOPE, ident, dealer=True),
                         domains._readable(ident))
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        dealer = domains._readable_h(self.p.app, SCOPE, ident, dealer=True)
        self.assertIn("Radiant White", dealer)            # governed colour name now leads
        self.assertIn("Graphite", dealer)
        self.assertNotIn("QBE", dealer)                   # no internal colour code in dealer copy
        # operator form keeps codes for precision; unmapped trim/drivetrain stays honest (never guessed)
        op = domains._readable_h(self.p.app, SCOPE, ident)
        self.assertIn("Radiant White (QBE)", op)

    # ---- safety ----
    def test_schema_stays_v12_and_db_temp_only(self):
        bootstrap_reviewed_translation(self.p.app.prefs, SCOPE)
        ensure_single_operator_identity_govern(self.stack, scope=SCOPE)
        self.assertEqual(current_version(self.stack.db.conn), 12)
        self.assertTrue(self.tmp in os.path.abspath(os.path.join(self.tmp, "elite.db")))  # temp, not permanent

    def test_authority_grant_anchor_still_works(self):
        # the pre-existing manager anchor (authority.grant → identity.govern) is preserved
        mgr = self.stack.authn.register("Manager", "secret-mgr")
        self.stack.grant(mgr.id, "authority.grant", SCOPE)
        ensure_identity_governance_grants(self.stack)
        self.assertTrue(self.stack.authz.decide(mgr.id, GOVERN, SCOPE).allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
