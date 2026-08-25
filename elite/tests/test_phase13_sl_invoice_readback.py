"""Service-Loaner per-unit invoice — readback, retire, and bulk import (live unblock 2026-08-25).

The live defect: a saved per-VIN invoice persisted but the Program Inputs page never showed it back (no list,
no retire), so the operator's $50k test value appeared to vanish. These tests lock the fix: the governed
SLPolicyStore now exposes a readback + retire + idempotent bulk import, the page lists stored invoices, and a
current fleet unit's KEEP/PULL/SWAP gate for 'authoritative invoice' clears once its invoice is on file
(write-down accrues from ACTUAL in-service tenure, not a projected-tenure gate).
"""
import os
import tempfile
import unittest


class _Prefs:
    def __init__(self):
        self.d = {}

    def get_pref(self, pk, k, default=None):
        return self.d.get((pk, k), default)

    def set_pref(self, pk, k, v):
        self.d[(pk, k)] = v


class TestPolicyInvoiceStore(unittest.TestCase):
    def setUp(self):
        from elite.loaner.sl_policy import SLPolicyStore
        self.pol = SLPolicyStore(_Prefs(), "store:HG")

    def test_set_then_readback_visible(self):
        self.pol.set_invoice("5n1al1er7tc348756", 52516, actor="op", at="2026-08-25T00:00:00Z")
        recs = self.pol.invoice_records()
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["vin"], recs[0]["amount"], recs[0]["actor"]),
                         ("5N1AL1ER7TC348756", 52516, "op"))

    def test_retire_removes_from_active(self):
        self.pol.set_invoice("VIN1", 52516, actor="op", at="2026-08-25T00:00:00Z")
        self.assertTrue(self.pol.remove_invoice("vin1", actor="op", at="2026-08-25T01:00:00Z"))
        self.assertIsNone(self.pol.invoice_for_vin("VIN1"))
        self.assertEqual(self.pol.invoice_records(), [])
        # audit kept
        self.assertTrue(any(h.get("kind") == "invoice_retired" for h in self.pol.history()))

    def test_resave_corrects(self):
        self.pol.set_invoice("VIN1", 50000, actor="op", at="2026-08-25T00:00:00Z")   # the $50k test value
        self.pol.set_invoice("VIN1", 52516, actor="op", at="2026-08-25T01:00:00Z")
        self.assertEqual(self.pol.invoice_for_vin("VIN1"), 52516)

    def test_bulk_import_idempotent(self):
        rows = [{"vin": "A1", "amount": "52516"}, {"vin": "A2", "amount": "51652"},
                {"vin": "", "amount": "1"}, {"vin": "A3", "amount": "0"}]   # 2 valid, 2 invalid
        r = self.pol.bulk_set_invoices(rows, actor="op", at="2026-08-25T00:00:00Z")
        self.assertEqual((r["applied"], r["skipped_invalid"]), (2, 2))
        r2 = self.pol.bulk_set_invoices(rows, actor="op", at="2026-08-25T00:10:00Z")
        self.assertEqual((r2["applied"], r2["skipped_existing"]), (0, 2))


class TestChecklistCsv(unittest.TestCase):
    def test_parses_full_vin_and_original_invoice(self):
        from elite.loaner.sl_policy import parse_invoice_csv
        csv = (b"Current Fleet ID,Full VIN,RDR Rental Month,In Service Date,Last Checkout Miles,"
               b"Original Invoice,Entered in Elite,Notes\n"
               b"TC348756,5N1AL1ER7TC348756,202602,2/10/2026,11513,52516,,\n")
        rows = parse_invoice_csv(csv)
        self.assertEqual(rows[0]["vin"], "5N1AL1ER7TC348756")
        self.assertEqual(rows[0]["amount"], "52516")

    def test_missing_columns_returns_empty(self):
        from elite.loaner.sl_policy import parse_invoice_csv
        self.assertEqual(parse_invoice_csv(b"foo,bar\n1,2\n"), [])


class TestInvoiceUIAndDecision(unittest.TestCase):
    def setUp(self):
        from elite.ui.fixtures import Phase10
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "e.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_saved_invoice_is_visible_after_save(self):
        self.full.post("/program-inputs/invoice", {"vin": "1GNSKUI0000001", "amount": "52516"})
        b = self.full.get("/program-inputs").body
        self.assertIn("1GNSKUI0000001", b)          # readback — no longer vanishes
        self.assertIn("52,516", b)
        self.assertIn("Invoices on file", b)
        self.assertIn("/program-inputs/invoice/retire", b)

    def test_bulk_import_route(self):
        csv = b"Current Fleet ID,Full VIN,Original Invoice\nTC1,1GNSKUI0000001,52516\nTC2,1GNSKUI0000002,51652\n"
        self.full.post("/program-inputs/invoice/import", {}, files={"file": ("c.csv", csv)})
        b = self.full.get("/program-inputs").body
        self.assertIn("1GNSKUI0000001", b)
        self.assertIn("1GNSKUI0000002", b)

    def test_retire_route(self):
        self.full.post("/program-inputs/invoice", {"vin": "1GNSKUI0000001", "amount": "52516"})
        self.full.post("/program-inputs/invoice/retire", {"vin": "1GNSKUI0000001"})
        b = self.full.get("/program-inputs").body
        self.assertEqual(b.count("1GNSKUI0000001"), 0)

    def test_invoice_clears_unit_decision_gate(self):
        # the current-unit KEEP/PULL/SWAP gate for the invoice clears once the invoice is on file; the
        # write-down accrues from ACTUAL in-service tenure (no projected-tenure gate for current units)
        from elite.loaner.intelligence import build_intelligence
        from elite.loaner.sl_decision import build_unit_decision
        intel = build_intelligence(self.p.app.stack.db.conn, "store:HG", self.p.app.prefs, self.p.app.stack.clock)
        u = intel.units[0]
        d0 = build_unit_decision(self.p.app, "store:HG", u, None)
        self.assertIn("authoritative invoice", d0["gated"])
        self.full.post("/program-inputs/invoice", {"vin": u.vin, "amount": "52516"})
        d1 = build_unit_decision(self.p.app, "store:HG", u, None)
        self.assertNotIn("authoritative invoice", d1["gated"])
        self.assertIsNotNone(d1["components"]["adjusted_basis_now"])

    def test_readiness_message_separates_unit_from_program(self):
        b = self.full.get("/program-inputs").body
        self.assertIn("Per-unit KEEP/PULL/SWAP economics are separate", b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
