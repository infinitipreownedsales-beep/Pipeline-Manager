"""Translation & Identity core — the governed, source-backed mapping layer approved after the QX60/QX65/QX80
Order-Preference audit. Proves the corrected relations and the Preferred-Order policy:
  * SAME_AS is context-scoped (interior `P` differs by model line) and only APPROVED mappings translate;
  * SAME_FAMILY_AS may NOT cross drivetrain (PURE 2WD != PURE 4WD);
  * Commercial Family = franchise+model+trim+drivetrain, with generation as a Planning Segment underneath;
  * demand may inherit across a family as lineage, NEVER automatically exact;
  * Preferred Order resolves Family -> BASE -> authoritative orderability -> exact raw ORDER identity, and a
    `$0`/pending BASE never auto-substitutes a priced package (surfaces "BASE preferred — orderability
    unresolved" instead);
  * raw observations are immutable and absence from a later chart is NOT discontinuation;
  * the store is franchise/source-agnostic and needs no schema change (schema stays v12)."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.errors import ValidationError
from elite.identity.translation import (
    FamilyKey, SemanticMapping, VariantRow, PreferredOrderPolicy, TranslationStore,
    derive_orderability, check_same_family_drivetrain, demand_evidence_tier, resolve_preferred_order)
from elite.identity import seed_infiniti as SEED

QX80 = "Order_Preference_Details__QX80.pdf@2026-08-19"


def _row(model, trim, drive, code, gen, pkg, base, priced, seen="seen_latest"):
    fam = FamilyKey("INFINITI", model, trim, drive)
    return VariantRow(fam, code, gen, pkg, base, seen, priced, derive_orderability(seen, priced), (QX80,))


class TestPurePolicy(unittest.TestCase):
    # BASE, confirmed orderable -> order that exact raw identity + BASE
    def test_base_orderable_is_ordered(self):
        rows = [_row("QX60", "AUTOGRAPH", "AWD", "84617", "84", "BASE", True, True),
                _row("QX60", "AUTOGRAPH", "AWD", "84617", "84", "TPA", False, True)]
        d = resolve_preferred_order(rows, PreferredOrderPolicy(FamilyKey("INFINITI", "QX60", "AUTOGRAPH", "AWD")))
        self.assertEqual(d["status"], "order")
        self.assertEqual((d["raw_code"], d["package"]), ("84617", "BASE"))   # TPA never auto-preferred

    # QX80 LUXE 2WD: 86317 BASE is $0/pending (unresolved); 83317 is priced but only PA1 -> NO order, surfaced
    def test_pending_base_does_not_substitute_priced_package(self):
        rows = [_row("QX80", "LUXE", "2WD", "86317", "86", "BASE", True, False),   # $0 pending -> unresolved
                _row("QX80", "LUXE", "2WD", "83317", "83", "PA1", False, True)]    # priced package, not BASE
        d = resolve_preferred_order(rows, PreferredOrderPolicy(FamilyKey("INFINITI", "QX80", "LUXE", "2WD")))
        self.assertEqual(d["status"], "unresolved")
        self.assertIn("BASE preferred — orderability unresolved", d["message"])
        # both identities + generations are preserved in the honest candidate list
        gens = {(c["raw_code"], c["generation"]) for c in d["candidates"]}
        self.assertEqual(gens, {("86317", "86"), ("83317", "83")})

    # $0 / Pending-Changes is orderability `unresolved`, never `discontinued`
    def test_pending_is_unresolved_not_discontinued(self):
        self.assertEqual(derive_orderability("seen_latest", False), "unresolved")
        self.assertEqual(derive_orderability("seen_latest", True), "orderable")
        self.assertEqual(derive_orderability("not_seen_latest", True), "unresolved")   # absence != discontinued
        self.assertEqual(derive_orderability("seen_latest", False, explicit="discontinued"), "discontinued")

    # an explicitly authorized (evidence-backed) package substitution is honored
    def test_authorized_substitution(self):
        rows = [_row("QX80", "SPORT", "4WD", "86417", "86", "BASE", True, False),
                _row("QX80", "SPORT", "4WD", "86417", "86", "SEA", False, True)]
        pol = PreferredOrderPolicy(FamilyKey("INFINITI", "QX80", "SPORT", "4WD"),
                                   accepted_substitution=("86417", "SEA"))
        d = resolve_preferred_order(rows, pol)
        self.assertEqual((d["status"], d["raw_code"], d["package"]), ("order", "86417", "SEA"))
        self.assertEqual(d["reason"], "authorized_substitution")

    # older-generation BASE may remain eligible when explicitly orderable, but stays a SEPARATE segment
    def test_older_gen_base_eligible_separate_segment(self):
        rows = [_row("QX80", "LUXE", "2WD", "86317", "86", "BASE", True, False),           # new gen pending
                _row("QX80", "LUXE", "2WD", "8331", "83", "BASE", True, True)]              # old gen orderable
        d = resolve_preferred_order(rows, PreferredOrderPolicy(FamilyKey("INFINITI", "QX80", "LUXE", "2WD")))
        self.assertEqual(d["status"], "order")
        self.assertEqual((d["raw_code"], d["generation"]), ("8331", "83"))   # older gen, generation retained

    def test_no_orderable_base_surfaces_unresolved(self):
        rows = [_row("QX80", "PURE", "2WD", "86117", "86", "BASE", True, False),
                _row("QX80", "PURE", "2WD", "8311", "83", "BASE", True, False, seen="seen_previously")]
        d = resolve_preferred_order(rows, PreferredOrderPolicy(FamilyKey("INFINITI", "QX80", "PURE", "2WD")))
        self.assertEqual(d["status"], "unresolved")


class TestRelationsGuards(unittest.TestCase):
    def test_same_family_cannot_cross_drivetrain(self):
        fam = FamilyKey("INFINITI", "QX80", "PURE", "2WD")
        check_same_family_drivetrain(fam, "2WD")                       # same drivetrain ok
        with self.assertRaises(ValidationError):
            check_same_family_drivetrain(fam, "4WD")                   # 83017 PURE 4WD is a DIFFERENT family

    def test_demand_inheritance_is_lineage_never_exact(self):
        self.assertEqual(demand_evidence_tier("8331", "8331", True), "exact")       # own history
        self.assertEqual(demand_evidence_tier("8331", "86317", True), "lineage")    # cross-gen same family
        self.assertEqual(demand_evidence_tier("8331", "83017", False), "none")      # different family


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.store = TranslationStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_same_as_is_context_scoped_and_requires_approval(self):
        self.store.upsert_semantic(SemanticMapping("NNA_ORDER_PORTAL", "interior", "P", "P", "Sepia Brown",
                                                   "QX80", "approved", (QX80,)))
        self.store.upsert_semantic(SemanticMapping("NNA_ORDER_PORTAL", "interior", "P", "P", "Saddle Brown",
                                                   "QX60", "approved", (QX80,)))
        self.store.upsert_semantic(SemanticMapping("NNA_ORDER_PORTAL", "interior", "X", "X", "Proposed Name",
                                                   "", "proposed", (QX80,)))
        self.assertEqual(self.store.translate("NNA_ORDER_PORTAL", "interior", "P", model="QX80")[1], "Sepia Brown")
        self.assertEqual(self.store.translate("NNA_ORDER_PORTAL", "interior", "P", model="QX60")[1], "Saddle Brown")
        self.assertIsNone(self.store.translate("NNA_ORDER_PORTAL", "interior", "X"))   # proposed does not translate
        self.store.approve_semantic("NNA_ORDER_PORTAL", "interior", "X", "")
        self.assertEqual(self.store.translate("NNA_ORDER_PORTAL", "interior", "X")[1], "Proposed Name")

    def test_observations_immutable_and_absence_not_discontinued(self):
        self.store.record_observation("NNA_ORDER_PORTAL", "model_code", "83317", as_of="2026-07-01", proof_ref=QX80)
        self.store.record_observation("NNA_ORDER_PORTAL", "model_code", "83317", as_of="2026-08-19", proof_ref=QX80)
        obs = [o for o in self.store.observations() if o["raw_value"] == "83317"]
        self.assertEqual(len(obs), 1)                                  # not duplicated
        self.assertEqual(obs[0]["first_seen"], "2026-07-01")           # first-seen preserved
        self.assertEqual(obs[0]["last_seen"], "2026-08-19")
        # a value absent from the latest chart becomes not_seen_latest, NEVER discontinued
        self.store.record_observation("NNA_ORDER_PORTAL", "model_code", "8311", as_of="2026-07-01")
        self.store.mark_not_seen_latest({("NNA_ORDER_PORTAL", "model_code", "83317")})
        gone = [o for o in self.store.observations() if o["raw_value"] == "8311"][0]
        self.assertEqual(gone["seen_state"], "not_seen_latest")
        self.assertNotEqual(gone["seen_state"], "discontinued")

    def test_unresolved_queue_and_resolution_reuse(self):
        self.store.record_observation("NNA_ORDER_PORTAL", "exterior", "ZZZ", as_of="2026-08-19", proof_ref=QX80)
        self.assertTrue(any(o["raw_value"] == "ZZZ" for o in self.store.unresolved_translations()))
        self.store.upsert_semantic(SemanticMapping("NNA_ORDER_PORTAL", "exterior", "ZZZ", "ZZZ", "New Color",
                                                   "", "approved", (QX80,)))
        self.assertFalse(any(o["raw_value"] == "ZZZ" for o in self.store.unresolved_translations()))  # reused

    def test_franchise_source_agnostic(self):
        # a different source system + franchise resolves through the same API with no code change
        self.store.upsert_semantic(SemanticMapping("DEALER_DMS", "exterior", "040", "040", "Super White",
                                                   "", "approved", ("dms_export@2026-08-19",)))
        self.assertEqual(self.store.translate("DEALER_DMS", "exterior", "040")[1], "Super White")

    def test_seed_is_source_backed_and_families_segmented(self):
        SEED.seed(self.store)
        # corrected colors, verified from the chart
        self.assertEqual(self.store.translate("NNA_ORDER_PORTAL", "exterior", "XLF", model="QX80")[1],
                         "2T Dynamic Metal")
        self.assertEqual(self.store.translate("NNA_ORDER_PORTAL", "exterior", "XKJ", model="QX80")[1],
                         "2T Radiant White")
        # every seeded mapping carries a source proof
        self.assertTrue(all(m.proof_refs for m in self.store.semantic_mappings()))
        # QX80 LUXE 2WD is ONE family with TWO generation segments (83 + 86)
        luxe = FamilyKey("INFINITI", "QX80", "LUXE", "2WD")
        self.assertEqual(self.store.segments(luxe), ["83", "86"])
        # PURE 2WD and PURE 4WD are DIFFERENT families (drivetrain), never merged
        self.assertNotEqual(FamilyKey("INFINITI", "QX80", "PURE", "2WD").as_str(),
                            FamilyKey("INFINITI", "QX80", "PURE", "4WD").as_str())
        self.assertEqual(self.store.resolve_order(luxe)["status"], "unresolved")   # pending BASE, no substitution
        # SPORT 4WD packages collapse to ONE family (VARIANT OF BASE), not eight demand families
        sport = self.store.variant_rows(FamilyKey("INFINITI", "QX80", "SPORT", "4WD"))
        self.assertEqual(len({r.family.as_str() for r in sport}), 1)
        self.assertGreaterEqual(len(sport), 6)                        # BASE + several package variants
        self.assertEqual(current_version(self.p.stack.db.conn), 12)   # no schema change


if __name__ == "__main__":
    unittest.main(verbosity=2)
