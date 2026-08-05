"""Phase 4 acceptance — Sellable Combination identity + lineage (items 1-6)."""
import os
import sqlite3
import tempfile
import unittest

from elite.newinv.fixtures import OTHER_SCOPE, SCOPE, Phase4


class TestPhase4Combination(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase4(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_01_combination_survives_restart(self):
        c = self.p.combination(exterior_color="BLACK")
        self.p.close()
        p2 = Phase4(self.dbp)
        self.addCleanup(p2.close)
        again = p2.store.get_combination(c.id)
        self.assertIsNotNone(again)
        self.assertEqual(again.canonical_identity, c.canonical_identity)

    def test_02_exact_combinations_distinguish_exterior_and_interior(self):
        base = self.p.combination(exterior_color="BLACK", interior_color="GRAPHITE")
        diff_int = self.p.combination(exterior_color="BLACK", interior_color="WHEAT")
        diff_ext = self.p.combination(exterior_color="WHITE", interior_color="GRAPHITE")
        self.assertNotEqual(base.id, diff_int.id)          # interior is a real dimension
        self.assertNotEqual(base.id, diff_ext.id)
        self.assertNotEqual(base.canonical_identity, diff_int.canonical_identity)

    def test_03_drivetrain_distinct_where_variable(self):
        awd = self.p.combination(drivetrain="AWD")
        rwd = self.p.combination(drivetrain="RWD")
        self.assertNotEqual(awd.id, rwd.id)

    def test_04_standard_trim_content_does_not_create_identity(self):
        # Extra, non-independently-selectable content must not split identity.
        plain = self.p.combination(trim="LUXE")
        with_content = self.p.combination(trim="LUXE", sunroof="yes", floor_mats="premium")
        self.assertEqual(plain.id, with_content.id)        # same canonical combination
        # but a genuinely different trim IS distinct
        sport = self.p.combination(trim="SPORT")
        self.assertNotEqual(plain.id, sport.id)

    def test_05_correction_preserves_prior_identity_history(self):
        orig = self.p.combination(exterior_color="BLAK")     # typo to be corrected
        corrected = self.p.combos.correct(orig.id, dict(
            model="QX80", model_year="2026", trim="LUXE", drivetrain="AWD", exterior_color="BLACK",
            interior_color="GRAPHITE", franchise="INFINITI"), SCOPE)
        self.assertEqual(corrected.correction_of, orig.id)
        preserved = self.p.store.get_combination(orig.id)
        self.assertEqual(preserved.status, "corrected")      # original preserved, not deleted
        self.assertEqual(preserved.exterior_color, "BLAK")   # original-as-known intact

    def test_06_cross_store_combinations_remain_scoped(self):
        hg = self.p.combination(scope=SCOPE, exterior_color="BLACK")
        west = self.p.combination(scope=OTHER_SCOPE, exterior_color="BLACK")
        self.assertNotEqual(hg.id, west.id)                  # no cross-store merge
        self.assertEqual(hg.canonical_identity, west.canonical_identity)  # same config, different scope

    def test_06b_combination_history_is_append_preserving(self):
        c = self.p.combination(exterior_color="BLACK")
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("DELETE FROM sellable_combination WHERE id=?", (c.id,))


if __name__ == "__main__":
    unittest.main()
