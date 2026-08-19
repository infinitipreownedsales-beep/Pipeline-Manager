"""Effective-dated Service-Loaner program inputs (ICV / Velocity) — the corrections required before live
acceptance: historical effective months are representable, values are effective-dated and append-only,
recorded_at is separate from effective_month, UNKNOWN never becomes $0, and coverage is reported honestly.
No Phase-4 calculation semantics change here."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.loaner.program_inputs import (ProgramInputsStore, parse_value, entry_status, coverage, valid_month)


class TestProgramInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.store = ProgramInputsStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    # 1. earlier historical effective months can be selected and stored (no artificial window)
    def test_historical_months_can_be_stored(self):
        for m in ("2026-02", "2026-03", "2026-04"):
            self.assertTrue(valid_month(m))
            self.store.add("icv", effective_month=m, model="QX80", value=1000, actor="kyle",
                           recorded_at="2026-08-19T10:00:00Z")
        months = {e.effective_month for e in self.store.entries("icv")}
        self.assertTrue({"2026-02", "2026-03", "2026-04"} <= months)

    # 2. historical and newer values coexist; 3. effective_month is separate from recorded_at
    def test_values_coexist_and_dates_are_separate(self):
        self.store.add("icv", effective_month="2026-03", model="QX80", value=1000, actor="k",
                       recorded_at="2026-08-19T10:00:00Z")
        self.store.add("icv", effective_month="2026-05", model="QX80", value=1500, actor="k",
                       recorded_at="2026-08-19T10:05:00Z")
        self.store.add("icv", effective_month="2026-08", model="QX80", value=2000, actor="k",
                       recorded_at="2026-08-19T10:10:00Z")
        vals = {e.effective_month: e.value for e in self.store.entries("icv")}
        self.assertEqual(vals, {"2026-03": 1000, "2026-05": 1500, "2026-08": 2000})   # all three preserved
        e = self.store.entries("icv")[0]
        self.assertNotEqual(e.effective_month, e.recorded_at[:7])                      # distinct fields
        # applicable value is the one effective at-or-before the period
        self.assertEqual(self.store.applicable("icv", "QX80", "2026-04").value, 1000)  # March value applies in April
        self.assertEqual(self.store.applicable("icv", "QX80", "2026-07").value, 1500)  # May value applies in July
        self.assertEqual(self.store.applicable("icv", "QX80", "2026-09").value, 2000)
        self.assertIsNone(self.store.applicable("icv", "QX80", "2026-01"))             # before any value -> None

    # 4. adding a later value does not rewrite prior history (append-only supersession)
    def test_later_value_is_prospective_only(self):
        self.store.add("icv", effective_month="2026-03", model="QX80", value=1000, actor="k", recorded_at="t1")
        self.store.add("icv", effective_month="2026-08", model="QX80", value=2000, actor="k", recorded_at="t2")
        self.assertEqual(self.store.applicable("icv", "QX80", "2026-04").value, 1000)  # March untouched
        self.assertEqual(len(self.store.entries("icv")), 2)                            # both retained

    # 5. explicit $0 is preserved as a real authoritative value
    def test_explicit_zero_preserved(self):
        self.assertEqual(parse_value("0"), 0)
        self.store.add("icv", effective_month="2026-06", model="QX55", value=parse_value("0"), actor="k",
                       recorded_at="t")
        e = self.store.applicable("icv", "QX55", "2026-07")
        self.assertIsNotNone(e)
        self.assertEqual(e.value, 0)                                                   # explicit zero applies

    # 6. missing / unset does NOT render or resolve as $0
    def test_unknown_is_not_zero(self):
        self.assertIsNone(parse_value(""))
        self.assertIsNone(parse_value(None))
        self.store.add("icv", effective_month="2026-06", model="QX65", value=parse_value(""), actor="k",
                       recorded_at="t")
        self.assertIsNone(self.store.applicable("icv", "QX65", "2026-07"))             # unresolved, not 0
        self.assertEqual(entry_status(self.store.entries("icv")[0], "2026-08"), "unresolved")

    # 7. coverage status identifies missing historical periods
    def test_coverage_reports_missing_periods(self):
        # active fleet in service since March; ICV history only starts in June -> March–May missing
        self.store.add("icv", effective_month="2026-06", model="QX80", value=1500, actor="k", recorded_at="t")
        cov = coverage(self.store, "icv", "2026-03", "2026-08", models=("QX80",))
        self.assertEqual(cov["status"], "incomplete")
        self.assertEqual(cov["earliest"], "2026-03")
        self.assertEqual(cov["missing"], ["2026-03", "2026-05"])
        # once a value covers March, it is complete
        self.store.add("icv", effective_month="2026-03", model="QX80", value=1200, actor="k", recorded_at="t")
        self.assertEqual(coverage(self.store, "icv", "2026-03", "2026-08", models=("QX80",))["status"], "complete")

    def test_legacy_ambiguous_zero_migrates_to_unresolved(self):
        # a legacy row whose blank amount was materialized as 0 must NOT survive as an authoritative $0
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "icv_program",
                                  [{"eff": "2026-07", "model": "QX80", "trim": "", "amount": 0},
                                   {"eff": "2026-07", "model": "QX60", "trim": "", "amount": 1800}])
        entries = {e.model: e for e in self.store.entries("icv")}
        self.assertIsNone(entries["QX80"].value)                       # ambiguous legacy 0 -> unresolved
        self.assertIn("re-enter", entries["QX80"].provenance)
        self.assertEqual(entries["QX60"].value, 1800)                  # positive legacy value preserved

    def test_schema_unchanged(self):
        self.store.add("icv", effective_month="2026-03", model="QX80", value=1000, actor="k", recorded_at="t")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


class TestProgramInputsPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _store(self):
        return ProgramInputsStore(self.p.app.prefs, SCOPE)

    def test_page_uses_durable_month_picker_and_columns(self):
        self.assertEqual(self.full.get("/program-inputs").status, 200)
        self.assertIn("type=month", self.full.get("/program-inputs").body)   # durable month picker, not a window
        self.full.post("/program-inputs/icv", {"effective_month": "2026-03", "model": "QX80", "value": "1200"})
        b = self.full.get("/program-inputs").body
        for col in ("Effective month", "Trim / scope", "Recorded by", "Recorded at"):
            self.assertIn(col, b)

    def test_historical_month_and_unknown_not_zero_via_route(self):
        # a historical month far outside any old dropdown window stores fine
        self.full.post("/program-inputs/icv", {"effective_month": "2026-02", "model": "QX80", "value": ""})
        e = self._store().entries("icv")[0]
        self.assertEqual(e.effective_month, "2026-02")
        self.assertIsNone(e.value)                              # blank -> UNRESOLVED, never $0
        self.assertNotEqual(e.effective_month, (e.recorded_at or "")[:7])   # recorded_at != effective_month
        b = self.full.get("/program-inputs").body
        self.assertIn("unresolved", b)
        # explicit zero is a real value and renders as $0
        self.full.post("/program-inputs/icv", {"effective_month": "2026-03", "model": "QX55", "value": "0"})
        self.assertEqual(self._store().applicable("icv", "QX55", "2026-04").value, 0)
        self.assertIn("$0", self.full.get("/program-inputs").body)

    def test_board_shows_coverage_and_stays_gated(self):
        b = self.full.get("/service-loaner").body
        self.assertIn("Program coverage", b)                    # coverage summary on the command board
        self.assertIn("/program-inputs", b)                     # reachable from Service Loaners
        self.assertIn("Undetermined", b)                        # still Phase-4 gated
        self.assertIn("Pending Economics", b)

    def test_reachable_from_data(self):
        self.assertIn("/program-inputs", self.full.get("/data").body)

    def test_certified_unchanged(self):
        self.full.get("/program-inputs")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
