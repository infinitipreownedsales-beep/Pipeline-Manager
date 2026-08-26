"""Identity bridge: a governed 4-digit PLANNING model code resolves to its authoritative reviewed 5-digit
Infiniti order code (and commercial family), so a CTP CHANGE target rendered from a planning identity never
shows `[8421 (unmapped)]`. Deterministic reverse of the governed reduction (model-scoped normalize_code +
code4), single-family only — never a fuzzy prefix match, raw/source codes untouched.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.identity.translation import TranslationStore
from elite.identity.provision import bootstrap_reviewed_translation
from elite.operatorstd import description as D

SCOPE = "store:HG"


class TestPlanningCodeBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase10(os.path.join(cls.tmp, "e.db"))
        bootstrap_reviewed_translation(cls.p.app.prefs, SCOPE)
        cls.st = TranslationStore(cls.p.app.prefs, SCOPE)

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    def _fam(self, code):
        f = self.st.family_for_code(code)
        return f"{f.model} {f.trim} {f.drivetrain}" if f else None

    def test_8421_resolves_to_qx60_luxe_awd(self):
        self.assertEqual(self._fam("8421"), "QX60 LUXE AWD")
        self.assertEqual(self.st.order_code_for_code("8421"), "84217")

    def test_qx60_planning_forms(self):
        self.assertEqual(self._fam("8431"), "QX60 LUXE FWD")     # 84317
        self.assertEqual(self._fam("8441"), "QX60 SPORT AWD")    # 84417
        self.assertEqual(self._fam("8461"), "QX60 AUTOGRAPH AWD")  # 84617 (code4)
        self.assertEqual(self._fam("8481"), "QX60 AUTOGRAPH AWD")  # 84617 (normalize special case)
        self.assertEqual(self.st.order_code_for_code("8431"), "84317")
        self.assertEqual(self.st.order_code_for_code("8461"), "84617")
        self.assertEqual(self.st.order_code_for_code("8481"), "84617")

    def test_exact_five_digit_codes_untouched(self):
        for code in ("84217", "84317", "84417", "84617"):
            self.assertIsNotNone(self.st.family_for_code(code))
            self.assertEqual(self.st.order_code_for_code(code), code)   # raw/source code returned unchanged

    def test_qx80_regression_no_ambiguity(self):
        # every QX80 planning form resolves to a single family; nothing collides across families
        cases = {"8631": "QX80 LUXE 2WD", "8661": "QX80 AUTOGRAPH 4WD", "8621": "QX80 LUXE 4WD",
                 "8611": "QX80 PURE 2WD", "8601": "QX80 PURE 4WD"}
        for code, expect in cases.items():
            self.assertEqual(self._fam(code), expect)

    def test_unknown_code_fails_honestly(self):
        self.assertIsNone(self.st.family_for_code("9999"))
        self.assertIsNone(self.st.order_code_for_code("9999"))
        self.assertIsNone(self.st.family_for_code("84"))         # 2-digit is not a planning code -> no bridge

    def test_describe_renders_planning_code_without_unmapped(self):
        d = D.describe(self.st, model="QX60", model_code="8421", exterior_code="KAD", interior_code="K")
        self.assertEqual((d.trim, d.drivetrain), ("LUXE", "AWD"))
        self.assertEqual(d.unresolved, ())                       # nothing unmapped
        self.assertNotIn("unmapped", d.operator)


if __name__ == "__main__":
    unittest.main(verbosity=2)
