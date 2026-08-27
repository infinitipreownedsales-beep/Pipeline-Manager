"""Translation/Identity closure + governed demand-lineage — adversarial coverage (item 24).

Deterministic identity auto-resolves; relationships that change demand sharing are review-gated; one root =
one decision; rejections are remembered and reopen only on materially new evidence; real data only; the model
number stays king and the DMS Description supplies human trim/drivetrain only on agreement.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.db import current_version
from elite.identity.translation import TranslationStore, FamilyKey, SemanticMapping
from elite.identity import seed_infiniti as SEED
from elite.identity.lineage import (LineageStore, ensure_lineage_proposals, root_issues,
                                    detect_cross_generation_candidates, CAT_UNKNOWN, CAT_DEMAND_LINEAGE)
from elite.operatorstd import description as D


class TestClosure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.scope = "store:HG_INFINITI_JACKSON"
        self.st = TranslationStore(self.p.app.prefs, self.scope)
        SEED.seed(self.st)
        self.ln = LineageStore(self.p.app.prefs, self.scope)
        ensure_lineage_proposals(self.st, self.ln)

    def tearDown(self):
        self.p.close()

    # ---- reviewed mappings resolve (QX60 / QX65 / QX80) ----
    def test_qx60_reviewed_mappings(self):
        self.assertEqual(self.st.family_for_code("84317").drivetrain, "FWD")   # QX60 LUXE FWD
        self.assertEqual(self.st.family_for_code("84617").trim, "AUTOGRAPH")
        self.assertEqual(self.st.resolve_display("exterior", "DAT", model="QX60"), ("DAT", "Deep Emerald"))
        self.assertEqual(self.st.resolve_display("exterior", "QBE", model="QX60"), ("QBE", "Radiant White"))

    def test_qx65_reviewed_mappings(self):
        self.assertEqual(self.st.family_for_code("85217"), FamilyKey("INFINITI", "QX65", "AUTOGRAPH", "AWD"))
        self.assertEqual(self.st.resolve_display("exterior", "XHQ", model="QX65"), ("XHQ", "2T Grand Blue"))
        self.assertEqual(self.st.resolve_display("interior", "N", model="QX65"), ("N", "Vermilion Red"))

    def test_qx80_reviewed_mappings(self):
        self.assertEqual(self.st.family_for_code("86617"), FamilyKey("INFINITI", "QX80", "AUTOGRAPH", "4WD"))
        self.assertEqual(self.st.family_for_code("86317").trim, "LUXE")
        self.assertEqual(self.st.resolve_display("exterior", "KCN", model="QX80"), ("KCN", "Dynamic Metal"))

    def test_model_scoped_interior_P(self):
        self.assertEqual(self.st.resolve_display("interior", "P", model="QX60"), ("P", "Saddle Brown"))
        self.assertEqual(self.st.resolve_display("interior", "P", model="QX80"), ("P", "Sepia Brown"))

    # ---- deterministic identity auto-resolves + audit ----
    def test_identity_auto_resolves_with_audit(self):
        self.assertTrue(self.st.variant_rows() and all(r.approval == "approved" for r in self.st.variant_rows()))
        self.assertTrue(any(a.get("action") == "variant.approve" and ":auto-resolve-identity" in a.get("actor", "")
                            for a in self.st.audit_log()))

    def test_unknown_stays_unresolved_never_guessed(self):
        self.assertIsNone(self.st.resolve_display("exterior", "ZZZ", model="QX80"))
        self.assertIsNone(self.st.family_for_code("99999"))

    # ---- MODEL NUMBER remains king; DMS Description supplies trim/drivetrain only on agreement ----
    def test_dms_description_supplies_trim_drivetrain_on_agreement(self):
        d = D.describe(self.st, model="QX80", model_code="8331", exterior_code="QBE", interior_code="G",
                       source_description="QX80 LUXE 2WD")
        self.assertEqual((d.trim, d.drivetrain), ("LUXE", "2WD"))
        self.assertEqual(d.model_code, "8331")                 # raw model code preserved, never overwritten
        self.assertFalse(d.description_conflict)
        self.assertEqual(d.operator, "QX80 LUXE 2WD — Radiant White (QBE) / Graphite (G)")

    def test_dms_description_disagreement_flags_conflict(self):
        # 8331 is a GOVERNED family (QX80 LUXE 2WD via the reviewed chart / planning-code reverse), so its trim /
        # drivetrain resolve from that authoritative family; a DMS Description whose MODEL disagrees is flagged for
        # review but never overrides the governed trim (model number stays king).
        d = D.describe(self.st, model="QX80", model_code="8331", exterior_code="QBE", interior_code="G",
                       source_description="QX60 AUTOGRAPH AWD")
        self.assertTrue(d.description_conflict)                 # sources disagree → one review, never silently chosen
        self.assertEqual((d.trim, d.drivetrain), ("LUXE", "2WD"))   # governed family stands, not the disagreeing desc

    def test_ungoverned_code_with_disagreeing_description_stays_unresolved(self):
        # for a code with NO governed family, a model-disagreeing DMS Description is refused and trim stays
        # unresolved (fail-closed) — never guessed from the disagreeing description.
        d = D.describe(self.st, model="QX80", model_code="99999", exterior_code="QBE", interior_code="G",
                       source_description="QX60 AUTOGRAPH AWD")
        self.assertTrue(d.description_conflict)
        self.assertIn("trim", d.unresolved)

    def test_governed_family_authoritative_over_messy_dms_description(self):
        # THE LIVE TK76338/76339 BUG: the DMS Description carries body/transmission tokens ("SUV AUTO"). The
        # governed model-code family (84617 -> QX60 AUTOGRAPH AWD) is authoritative, so trim resolves to AUTOGRAPH
        # and drivetrain to AWD — never "AUTO" and never the whole "AUTOGRAPH AWD SUV AUTO" description slice.
        d = D.describe(self.st, model="QX60", model_code="84617", exterior_code="GAT", interior_code="K",
                       source_description="QX60 AUTOGRAPH AWD SUV AUTO")
        self.assertEqual(d.trim, "AUTOGRAPH")
        self.assertNotEqual(d.trim, "AUTO")
        self.assertEqual(d.drivetrain, "AWD")
        self.assertNotIn("AUTO", d.trim.split())               # no transmission token leaks into trim

    def test_current_qx60_codes_resolve_governed_trims_separately(self):
        # every GOVERNED current QX60 order code resolves to the correct trim, with drivetrain as a SEPARATE
        # field. Ungoverned codes fail closed (unresolved) — they never mis-resolve to a body/transmission token.
        expected = {"84317": ("LUXE", "FWD"), "84217": ("LUXE", "AWD"),
                    "84417": ("SPORT", "AWD"), "84617": ("AUTOGRAPH", "AWD")}
        for code, (trim, drive) in expected.items():
            fam = self.st.family_for_code(code)
            self.assertIsNotNone(fam, code)
            self.assertEqual((fam.trim, fam.drivetrain), (trim, drive), code)
        for ungoverned in ("84117", "84017"):
            self.assertIsNone(self.st.family_for_code(ungoverned))   # honest None, never guessed as a trim

    def test_description_never_overwrites_model_code(self):
        d = D.describe(self.st, model="QX80", model_code="86317", source_description="QX80 SPORT 4WD")
        self.assertEqual(d.model_code, "86317")                # model code is canonical identity, untouched

    # ---- one root = one review, regardless of affected VINs; cross-source deduped ----
    def test_one_root_issue_across_many_sources(self):
        # the SAME unknown code observed across 3 different source systems → ONE root issue (cross-source dedup),
        # not one-per-source and not one-per-VIN. The translation layer counts source-observations (it dedupes by
        # source+type+raw); the physical-VIN count lives in inventory downstream.
        for src in ("speed_to_sell", "new_inventory_pipeline_summary", "dms_inventory"):
            for _ in range(40):
                self.st.record_observation(src, "exterior", "WZZ", as_of="2026-08-19", proof_ref="live")
        ri = root_issues(self.st, self.ln)
        wzz = [i for i in ri["issues"] if i.get("raw_value") == "WZZ"]
        self.assertEqual(len(wzz), 1)                          # one governance decision across all sources
        self.assertEqual(set(wzz[0]["sources"]), {"speed_to_sell", "new_inventory_pipeline_summary", "dms_inventory"})
        self.assertEqual(wzz[0]["affected"], 3)               # deduped per source (never 120 duplicate decisions)
        self.assertEqual(wzz[0]["category"], CAT_UNKNOWN)
        # resolving the one root resolves it for EVERY source (any-source display fallback)
        self.st.upsert_semantic(SemanticMapping("speed_to_sell", "exterior", "WZZ", "WZZ", "Test White", "",
                                                "approved", ("operator-resolved",)), actor="kyle", at="2026-08-22")
        self.assertEqual(self.st.resolve_display("exterior", "WZZ", model="QX80"), ("WZZ", "Test White"))
        self.assertEqual([i for i in root_issues(self.st, self.ln)["issues"] if i.get("raw_value") == "WZZ"], [])

    def test_headline_is_root_issues_not_raw_count(self):
        ri = root_issues(self.st, self.ln)
        # all root issues here are review-gated demand-lineage (identity already auto-resolved)
        self.assertTrue(all(i["category"] == CAT_DEMAND_LINEAGE for i in ri["issues"]))
        self.assertGreater(ri["count"], 0)

    # ---- cross-generation: identity auto-resolves; demand sharing review-gated ----
    def test_cross_generation_identity_auto_resolves(self):
        luxe = FamilyKey("INFINITI", "QX80", "LUXE", "2WD")
        self.assertEqual(self.st.segments(luxe, approved_only=True), ["83", "86"])   # both gens, approved

    def test_cross_generation_demand_sharing_is_review_gated(self):
        cands = detect_cross_generation_candidates(self.st)
        self.assertTrue(any(c["family"].endswith("QX80·LUXE·2WD") for c in cands))
        openr = [p for p in self.ln.open_reviews() if p.kind == "SAME_FAMILY_CROSS_GEN"]
        self.assertTrue(openr)                                 # surfaced as review, NOT auto-activated

    # ---- package identity auto-resolves; package demand-sharing review-gated; raw histories separate ----
    def test_package_identity_and_sharing_gated(self):
        sport = self.st.variant_rows(FamilyKey("INFINITI", "QX80", "SPORT", "4WD"), approved_only=True)
        self.assertEqual(len({r.family.as_str() for r in sport}), 1)     # one family
        self.assertGreaterEqual(len({r.package for r in sport}), 5)      # raw variants distinct
        self.assertTrue(any(p.kind == "PACKAGE_SHARING" for p in self.ln.open_reviews()))

    # ---- rejection memory + reopen on materially-new evidence ----
    def test_rejection_remembered_and_reopen_on_new_evidence(self):
        p = [x for x in self.ln.open_reviews() if x.kind == "SAME_FAMILY_CROSS_GEN"][0]
        self.ln.reject(p.id, actor="kyle", at="2026-08-22", reason="keep generations separate")
        # not re-prompted: ensure_lineage_proposals adds nothing new for that root
        self.assertEqual(ensure_lineage_proposals(self.st, self.ln), 0)
        self.assertNotIn(p.id, [o.id for o in self.ln.open_reviews()])
        # identical evidence does NOT reopen
        self.assertIsNone(self.ln.reopen(p.root_key, p.kind, new_evidence=p.evidence, why="same", at="x"))
        # materially-new evidence reopens, referencing the prior rejection
        reopened = self.ln.reopen(p.root_key, p.kind, new_evidence={"new": "AWD history accrued"},
                                  why="new real history", actor="system", at="2026-09-01")
        self.assertIsNotNone(reopened)
        self.assertEqual(reopened.supersedes, p.id)
        self.assertIn(reopened.id, [o.id for o in self.ln.open_reviews()])

    # ---- 4→5 digit: not inferred from similarity ----
    def test_unsupported_4to5_not_inferred(self):
        self.assertIsNone(self.st.family_for_code("8631"))     # 8631 != 86317; no similarity inference

    # ---- real data only: no synthetic demand introduced anywhere in this layer ----
    def test_no_synthetic_demand(self):
        for p in self.ln.all():
            self.assertNotIn("demand", {k.lower() for k in p.evidence.keys()})
            self.assertNotIn("sales", {k.lower() for k in p.evidence.keys()})

    # ---- safety ----
    def test_schema_v12_and_temp_db(self):
        self.assertEqual(current_version(self.p.stack.db.conn), 12)
        self.assertTrue(self.tmp in os.path.abspath(os.path.join(self.tmp, "elite.db")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
