"""CTP cross-generation eligibility (scoped fix, live acceptance 2026-09-02).

Live defect: an existing generation-86 QX80 production order was allowed to target a generation-83 shortage
(86117 gen86 PURE 2WD -> 83317 gen83 LUXE 2WD; 86217 gen86 LUXE 4WD -> 83317 gen83 LUXE 2WD) with no governed
cross-generation supply-substitution authority. Supply is counted per generation segment (code4 8631 vs 8331);
the SAME_FAMILY_CROSS_GEN demand-lineage relationship governs DEMAND EVIDENCE sharing, never physical/order
supply substitution. So a CHANGE target is eligible only when its governed generation equals the source order's
generation (or an explicit governed supply-substitution authority permits the transition — none exists today, so
crossing generations fails closed). Exclusion happens BEFORE ranking; the existing ranking reruns over the
same-generation remainder; KEEP honestly if no same-generation shortage improves the position.

This is scoped strictly to generation eligibility. It does NOT gate same-generation targets on the Aug-19
priced/resolve_order seed, does NOT merge 8331/8631, does NOT transfer demand, and fabricates no substitution.
"""
import unittest

from elite.workflow import ctp_intake as CTP
from elite.workflow.ctp_intake import Candidate, Reconciled, MATCHED, order_key


def _mk(order, cid, code, trim, dt):
    c = Candidate(order_number=order, vin="", model="QX80", model_code=code, trim=trim, drivetrain=dt)
    return Reconciled(c, MATCHED, {"combination_id": cid, "canonical": "src" + cid, "arrival_month": "2026-11"},
                      "matched by order #", "order#", {"order_match_count": 1, "vin_match_count": 0})


def _pos(gen, trim, dt, code, **kw):
    """A governed, executable board position. `gen`/`code` set the generation segment."""
    b = {"canonical": f"c{code}", "line": f"{code} QX80 {trim} {dt}", "colors": f"White ({code}) / Graphite (G)",
         "model": "QX80", "trim": trim, "drivetrain": dt, "generation": gen, "order_code": code,
         "executable": True, "color_complete": True, "excess": 0, "short": 0}
    b.update(kw)
    return b


# a gen-86 (current) QX80 order — the source that live CTP tried to redirect across generations
SRC_86 = ("TK79127", "cid_src", "86117", "PURE", "2WD")


class TestCrossGenerationEligibility(unittest.TestCase):
    def _eval(self, board, order=SRC_86, **kw):
        return CTP.evaluate([_mk(*order)], board, now="2026-09", **kw)[0]

    # LIVE CASE 1: a gen-86 order may NOT target the gen-83 83317 shortage — even as the top short — and the
    # existing ranking reruns over the remaining gen-86 target.
    def test_gen86_order_excludes_gen83_target_and_reranks_to_gen86(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=1),
                 "cid_83": _pos("83", "LUXE", "2WD", "83317", short=9),        # prior-gen — top short, must NOT win
                 "cid_86": _pos("86", "LUXE", "2WD", "86317", short=2)}        # current-gen — the eligible target
        r = self._eval(board)
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "cid_86")                 # reranked to the same-generation target
        self.assertNotIn("83317", r.reason_plain)                             # never directs Kyle across generations

    # the excluded gen-83 shortage is left completely untouched (no consumption, no mutation).
    def test_gen83_shortage_remains_separate_and_unchanged(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=1),
                 "cid_83": _pos("83", "LUXE", "2WD", "83317", short=9),
                 "cid_86": _pos("86", "LUXE", "2WD", "86317", short=2)}
        before83 = board["cid_83"]["short"]
        self._eval(board)
        self.assertEqual(board["cid_83"]["short"], before83)                  # evaluate copies the board; 8331 untouched
        self.assertEqual(before83, 9)

    # LIVE CASE (both orders): 86117 PURE 2WD and 86217 LUXE 4WD both refuse the gen-83 83317 target.
    def test_both_live_gen86_orders_cannot_target_gen83(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=2),
                 "cid_83": _pos("83", "LUXE", "2WD", "83317", short=9)}       # only superior target is cross-gen
        r1 = self._eval(board, order=("TK79127", "cid_src", "86117", "PURE", "2WD"))
        r2 = self._eval(board, order=("TK79128", "cid_src", "86217", "LUXE", "4WD"))
        for r in (r1, r2):
            self.assertEqual(r.decision_state, CTP.KEEP)                      # no eligible same-gen shortage
            self.assertNotIn("83317", r.reason_plain)
            self.assertIn("generation", r.reason_plain.lower())              # honest cross-generation wording
            self.assertFalse(r.proof.get("cross_generation_blocked") is False)  # flagged in proof

    # fail closed: when the ONLY superior target is a different generation, KEEP honestly (never cross).
    def test_only_cross_gen_target_keeps_honestly(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=1),
                 "cid_83": _pos("83", "LUXE", "2WD", "83317", short=9)}
        r = self._eval(board)
        self.assertEqual(r.decision_state, CTP.KEEP)
        self.assertTrue(r.proof.get("cross_generation_blocked"))
        self.assertEqual(r.proof.get("source_generation"), "86")

    # same-generation governed CTP changes still work (the gate is scoped to generation crossings only).
    def test_same_generation_change_still_works(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=1),
                 "cid_86": _pos("86", "LUXE", "2WD", "86317", short=2)}
        r = self._eval(board)
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "cid_86")

    # ranking math is unchanged among same-generation targets (highest governed short wins).
    def test_ranking_math_unchanged_within_generation(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=1),
                 "cid_strong": _pos("86", "LUXE", "2WD", "86317", short=6),
                 "cid_weak": _pos("86", "AUTOGRAPH", "4WD", "86617", short=3)}
        r = self._eval(board)
        self.assertEqual(r.proposed_combination_id, "cid_strong")            # larger same-gen shortage wins

    # manual NOT AVAILABLE / session reranking still works, and stays within the source generation.
    def test_manual_not_available_reranks_within_generation(self):
        board = {"cid_src": _pos("86", "PURE", "2WD", "86117", excess=1),
                 "cid_g1": _pos("86", "LUXE", "2WD", "86317", short=5),
                 "cid_g2": _pos("86", "AUTOGRAPH", "4WD", "86617", short=3),
                 "cid_83": _pos("83", "LUXE", "2WD", "83317", short=9)}       # cross-gen, always excluded
        rc = _mk(*SRC_86)
        okey = order_key(rc.candidate.order_number, rc.candidate.vin)
        infeasible = {okey: [{"target": "cid_g1", "target_canonical": "c86317"}]}
        r = CTP.evaluate([rc], board, now="2026-09", infeasible=infeasible)[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "cid_g2")                # reranked past the marked-unavailable
        self.assertNotEqual(r.proposed_combination_id, "cid_83")             # never crosses to the gen-83 top short

    # governance boundary: the gate never consults demand lineage, and there is no supply-substitution authority.
    def test_no_supply_substitution_authority_exists(self):
        self.assertFalse(CTP._cross_gen_substitution_authorized("86", "83"))
        self.assertFalse(CTP._cross_gen_substitution_authorized("83", "86"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
