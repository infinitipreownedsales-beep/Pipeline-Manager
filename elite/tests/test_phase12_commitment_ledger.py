"""CPO shadow-supply → Production Order reconciliation (Stage 12B/13 adversarial): counts exactly once,
ambiguous fails visibly, re-import is idempotent, and session commitments derive from the line state."""
import unittest

from elite.ordering.commitment_ledger import reconcile_commitments, commitments_from_lines
from elite.newinv.dms_identity import dms_planning_identity


def _combo(mc, ext, inte):
    return dms_planning_identity({"model_code": mc, "exterior": ext, "interior": inte})


C60 = _combo("8481", "QBE", "G")
C60B = _combo("8481", "XKJ", "K")


class TestReconcile(unittest.TestCase):
    def test_combo_match_counts_once(self):
        commits = {C60: {"model": "QX60", "qty": 2}}
        rows = [{"manufacturer_order_id": "PO1", "model": "QX60", "model_code": "8481", "exterior": "QBE",
                 "interior": "G"}]
        r = reconcile_commitments(commits, rows)
        self.assertEqual(len(r["matched"]), 1)
        self.assertEqual(r["remaining_shadow"], {C60: 1})     # one covered, one still shadow
        self.assertEqual(r["shadow_covered"], 1)

    def test_reimport_is_idempotent(self):
        commits = {C60: {"model": "QX60", "qty": 2}}
        rows = [{"manufacturer_order_id": "PO1", "model": "QX60", "model_code": "8481", "exterior": "QBE",
                 "interior": "G"}]
        r1 = reconcile_commitments(commits, rows + rows)      # same order id twice
        self.assertEqual(len(r1["matched"]), 1)               # counted once, not twice
        self.assertEqual(r1["remaining_shadow"], {C60: 1})

    def test_unmatched_production_order(self):
        commits = {C60: {"model": "QX60", "qty": 1}}
        rows = [{"manufacturer_order_id": "PO9", "model": "QX80", "model_code": "8383", "exterior": "KAD",
                 "interior": "A"}]
        r = reconcile_commitments(commits, rows)
        self.assertEqual(len(r["unmatched"]), 1)              # no prior commitment -> authoritative on its own
        self.assertEqual(r["remaining_shadow"], {C60: 1})     # commitment untouched

    def test_model_only_sole_commitment_matches(self):
        commits = {C60: {"model": "QX60", "qty": 1}}
        rows = [{"manufacturer_order_id": "PO2", "model": "QX60"}]   # no combo detail, but sole open QX60
        r = reconcile_commitments(commits, rows)
        self.assertEqual(len(r["matched"]), 1)
        self.assertEqual(r["matched"][0]["basis"], "model (sole open commitment)")

    def test_model_only_ambiguous_fails_visibly(self):
        commits = {C60: {"model": "QX60", "qty": 1}, C60B: {"model": "QX60", "qty": 1}}
        rows = [{"manufacturer_order_id": "PO3", "model": "QX60"}]   # could be either QX60 combo
        r = reconcile_commitments(commits, rows)
        self.assertEqual(len(r["matched"]), 0)                # never silently merged
        self.assertEqual(len(r["ambiguous"]), 1)
        self.assertEqual(set(r["ambiguous"][0]["candidates"]), {C60, C60B})
        self.assertEqual(r["remaining_shadow"], {C60: 1, C60B: 1})   # both still open


class TestCommitmentsFromLines(unittest.TestCase):
    def test_confirmed_commits_order_partial_commits_k(self):
        board = {C60: {"model": "QX60", "order": 2}, C60B: {"model": "QX60", "order": 3}}
        lines = {C60: "confirmed"}
        qty = {C60B: 1}                                       # partial 1 of 3
        commits = commitments_from_lines(lines, qty, board)
        self.assertEqual(commits[C60]["qty"], 2)             # full order
        self.assertEqual(commits[C60B]["qty"], 1)           # partial

    def test_not_ordered_and_open_commit_nothing(self):
        board = {C60: {"model": "QX60", "order": 2}, C60B: {"model": "QX60", "order": 2}}
        lines = {C60: "not_ordered"}                          # C60B is open
        commits = commitments_from_lines(lines, {}, board)
        self.assertEqual(commits, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
