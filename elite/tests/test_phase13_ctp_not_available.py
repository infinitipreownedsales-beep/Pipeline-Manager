"""CTP 'Not available configuration' operator feedback loop (session-scope correction 2026-08-27).

When Infiniti accepts a CTP evaluation but rejects the desired specification (production restriction / restricted
item above max / package unavailable / other), the operator marks that configuration NOT AVAILABLE. That mark is
a SESSION/MODEL/CONFIGURATION exclusion, not an order-specific one: the rejected configuration (by governed
canonical build identity — the board combination_id and its canonical) is removed from the candidate pool of
EVERY remaining unconfirmed order of that model in the active CTP session, so the operator never has to repeat
the same OEM rejection cycle on the next order. Elite records the OEM rejection as provenance (which order first
hit it — kept for the history trail, but it does not narrow applicability), re-runs the sequential CTP decision
on the unchanged supply/demand board, and returns the next genuinely eligible certified-short target — repeatable
— stopping at a feasible superior configuration or KEEP (best available outcome) once every superior alternative
is session-excluded. Confirmed-change locks and their working-board supply effects are preserved. The board is
never mutated (nothing was executed). 'Reset unavailable marks' clears the session exclusions and recomputes;
Clear session clears them; they never persist across future CTP production cycles. State: RECOMMENDED CHANGE ->
OEM REJECTED/NOT AVAILABLE -> NEXT BEST, and RECOMMENDED -> CONFIRMED CHANGED.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.workflow import ctp_intake as CTP
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.identity.translation import TranslationStore
from elite.identity import seed_infiniti as SEED
from elite.ids import new_id


# ---- A. engine-level proof (pure evaluate, the exact loop) ------------------------------------------------
class TestNotAvailableEngine(unittest.TestCase):
    def _board(self):
        # one over-supplied QX65 source (the current TK65797 SPORT AWD slot) and two certified-short QX65 LUXE
        # AWD targets. QBE/G ranks first (short 2 > DAT/K short 1), so it is the initial recommendation.
        return {
            "src": {"canonical": "85117 SPORT AWD GAT/G", "line": "QX65 SPORT AWD",
                    "colors": "Grey / Graphite", "model": "QX65", "excess": 2, "short": 0},
            "t_qbe": {"canonical": "85017 LUXE AWD QBE/G", "line": "QX65 LUXE AWD",
                      "colors": "Radiant White / Graphite", "model": "QX65", "excess": 0, "short": 2},
            "t_dat": {"canonical": "85017 LUXE AWD DAT/K", "line": "QX65 LUXE AWD",
                      "colors": "Deep Emerald / Stone Gray", "model": "QX65", "excess": 0, "short": 1},
        }

    def _order(self, num="TK65797"):
        c = CTP.Candidate(order_number=num, model="QX65", arrival_month="2026-11")
        return CTP.Reconciled(c, CTP.MATCHED, {"combination_id": "src", "model": "QX65", "arrival_month": "2026-11"},
                              "matched by order #", "order#")

    def test_initial_recommendation_is_highest_short_target(self):
        r = CTP.evaluate([self._order()], self._board())[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "t_qbe")     # QBE/G (short 2) first

    def test_not_available_returns_next_best_then_keep(self):
        board = self._board()
        okey = CTP.order_key("TK65797", "")
        # round 1: QBE/G marked NOT AVAILABLE for this order -> next-best DAT/K
        infeasible = {okey: [{"target": "t_qbe", "target_canonical": "85017 LUXE AWD QBE/G",
                              "reason": "above_maximum", "note": "restricted item above max", "at": "2026-08-26T00:00"}]}
        r1 = CTP.evaluate([self._order()], board, infeasible=infeasible)[0]
        self.assertEqual(r1.decision_state, CTP.CHANGE)
        self.assertEqual(r1.proposed_combination_id, "t_dat")    # next-best certified-short target
        self.assertEqual(len(r1.rejected_targets), 1)            # OEM rejection preserved as provenance
        # round 2: DAT/K also NOT AVAILABLE -> every superior alternative exhausted -> KEEP (best available)
        infeasible[okey].append({"target": "t_dat", "target_canonical": "85017 LUXE AWD DAT/K",
                                 "reason": "package_component_unavailable", "note": "", "at": "2026-08-26T00:05"})
        r2 = CTP.evaluate([self._order()], board, infeasible=infeasible)[0]
        self.assertEqual(r2.decision_state, CTP.KEEP)
        self.assertTrue(r2.proof.get("best_available_after_exhaustion"))
        self.assertIn("best available outcome", r2.reason_plain)
        self.assertEqual(len(r2.rejected_targets), 2)

    def test_mark_is_session_wide_not_per_order(self):
        # CORRECTED SCOPE: two orders on the same over-supplied source; order A rejects QBE/G. That production
        # restriction now excludes QBE/G for the WHOLE session, so order B must NOT be re-offered QBE/G — it
        # continues straight to the next eligible target (DAT/K). This is the fix for the live QX60 TK76339/40
        # loop. (DAT/K short=2 here so both orders can take it, isolating the scope change from supply exhaustion.)
        board = self._board()
        board["t_dat"]["short"] = 2
        a, b = self._order("TKAAA"), self._order("TKBBB")
        infeasible = {CTP.order_key("TKAAA", ""): [{"target": "t_qbe", "target_canonical": "85017 LUXE AWD QBE/G",
                                                    "reason": "production_restriction"}]}
        recs = CTP.evaluate([a, b], board, infeasible=infeasible)
        by_order = {r.order_number: r for r in recs}
        self.assertEqual(by_order["TKAAA"].proposed_combination_id, "t_dat")     # A skipped QBE/G
        self.assertNotEqual(by_order["TKBBB"].proposed_combination_id, "t_qbe")  # B is NOT re-offered QBE/G
        self.assertEqual(by_order["TKBBB"].proposed_combination_id, "t_dat")     # B continues to next eligible

    def test_board_not_mutated_by_marks(self):
        # a mark alone (order that does NOT reconcile to an excess source) must not consume board excess/short
        board = self._board()
        before = {k: (v["excess"], v["short"]) for k, v in board.items()}
        infeasible = {CTP.order_key("TK65797", ""): [{"target": "t_qbe", "reason": "above_maximum"}]}
        CTP.evaluate([self._order()], board, infeasible=infeasible)
        after = {k: (v["excess"], v["short"]) for k, v in board.items()}
        self.assertEqual(before, after)                          # evaluate copies the board; source unchanged


# ---- A2. SESSION-scope regression: a Production Restriction excludes the config for the whole session --------
class TestSessionWideExclusionRegression(unittest.TestCase):
    """The live QX60 loop: TK76339 cycled through OEM-rejected configs and was KEEP'd; TK76340 must not be
    re-offered those same rejected configs. Proves the exclusion is session/model/configuration scoped."""

    def _board(self):
        # one over-supplied QX60 source and two certified-short QX60 targets: A (top short, the one rejected) and
        # C (the next genuinely eligible configuration). Ample excess/short so scope is isolated from exhaustion.
        return {
            "src": {"canonical": "84117 SPORT FWD SRC/G", "line": "QX60 SPORT FWD", "colors": "",
                    "model": "QX60", "excess": 4, "short": 0},
            "A":   {"canonical": "84617 LUXE FWD AAA/K", "line": "QX60 LUXE FWD", "colors": "",
                    "model": "QX60", "excess": 0, "short": 20},  # stays the top short target through all orders
            "C":   {"canonical": "84517 PURE FWD CCC/G", "line": "QX60 PURE FWD", "colors": "",
                    "model": "QX60", "excess": 0, "short": 10},  # enough supply to absorb every order once A is banned
        }

    def _orders(self, *nums):
        out = []
        for n in nums:
            c = CTP.Candidate(order_number=n, model="QX60", arrival_month="2026-11")
            out.append(CTP.Reconciled(c, CTP.MATCHED,
                       {"combination_id": "src", "model": "QX60", "arrival_month": "2026-11"}, "matched", "order#"))
        return out

    def test_reject_on_order1_excludes_config_for_orders_2_to_N(self):
        orders = self._orders("TK76339", "TK76340", "TK76341", "TK76342")
        # baseline: with no marks every order is recommended the top short target A
        base = CTP.evaluate(orders, self._board())
        self.assertTrue(all(r.proposed_combination_id == "A" for r in base))
        # reject configuration A on order 1 (production restriction) — session-wide exclusion
        infeasible = {CTP.order_key("TK76339", ""): [{"target": "A", "target_canonical": "84617 LUXE FWD AAA/K",
                                                      "reason": "production_restriction", "at": "2026-08-27T00:00"}]}
        recs = CTP.evaluate(orders, self._board(), infeasible=infeasible)
        self.assertTrue(all(r.proposed_combination_id != "A" for r in recs))     # A never recommended again
        # every order continues to the next genuinely eligible configuration (C), not KEEP and not A
        self.assertTrue(all(r.decision_state == CTP.CHANGE and r.proposed_combination_id == "C" for r in recs))
        # provenance: only order 1 carries the rejection record; it does not scope applicability
        by = {r.order_number: r for r in recs}
        self.assertEqual(len(by["TK76339"].rejected_targets), 1)
        self.assertEqual(by["TK76340"].rejected_targets, [])

    def test_all_superior_configs_session_excluded_then_keep(self):
        orders = self._orders("TK76339", "TK76340")
        okey = CTP.order_key("TK76339", "")
        infeasible = {okey: [{"target": "A", "reason": "production_restriction"},
                             {"target": "C", "reason": "production_restriction"}]}
        recs = CTP.evaluate(orders, self._board(), infeasible=infeasible)
        self.assertTrue(all(r.decision_state == CTP.KEEP for r in recs))
        self.assertTrue(all(r.proof.get("best_available_after_exhaustion") for r in recs))

    def test_confirmed_change_stays_locked_through_session_exclusion(self):
        # order 1 confirmed onto A; order 2 then rejects A (session ban). The lock and its board effect survive.
        orders = self._orders("TK76339", "TK76340")
        confirmed = {CTP.order_key("TK76339", ""): {"target": "A"}}
        infeasible = {CTP.order_key("TK76340", ""): [{"target": "A", "reason": "production_restriction"}]}
        recs = CTP.evaluate(orders, self._board(), confirmed=confirmed, infeasible=infeasible)
        by = {r.order_number: r for r in recs}
        self.assertTrue(by["TK76339"].confirmed)
        self.assertEqual(by["TK76339"].proposed_combination_id, "A")            # lock survives A's session ban
        self.assertNotEqual(by["TK76340"].proposed_combination_id, "A")         # order 2 still excluded from A
        self.assertEqual(by["TK76340"].proposed_combination_id, "C")            # evaluated against post-lock state

    def test_reset_restores_eligibility_and_new_session_is_clean(self):
        orders = self._orders("TK76339", "TK76340")
        okey = CTP.order_key("TK76339", "")
        infeasible = {okey: [{"target": "A", "reason": "production_restriction"}]}
        banned = CTP.evaluate(orders, self._board(), infeasible=infeasible)
        self.assertTrue(all(r.proposed_combination_id != "A" for r in banned))
        # 'Reset unavailable marks' clears the session exclusions -> A eligible again for every order
        infeasible.pop(okey)
        after_reset = CTP.evaluate(orders, self._board(), infeasible=infeasible)
        self.assertTrue(all(r.proposed_combination_id == "A" for r in after_reset))
        # a brand-new CTP session carries no marks -> clean from the start
        fresh = CTP.evaluate(orders, self._board(), infeasible={})
        self.assertTrue(all(r.proposed_combination_id == "A" for r in fresh))


# ---- A3. SESSION-LEARNED production rule: same-trim-only (a SEPARATE, broader restriction) ------------------
class TestSameTrimSessionRule(unittest.TestCase):
    """A trim-swap OEM rejection teaches a broader session rule (same_trim_only): CHANGE targets must share the
    order's AUTHORITATIVE governed trim. Within-trim optimization and the exact-config rejection loop are
    untouched; only cross-trim targets are removed. Trim comes from the governed model-code identity carried on
    the board — NEVER positionally sliced from the free-text line (the live TK76338 bug read 'AUTO' out of
    'QX60 AUTOGRAPH AWD SUV AUTO' and dropped every real AUTOGRAPH alternative)."""

    def _board(self):
        # The live shape: the source DISPLAY line is 'QX60 AUTOGRAPH AWD SUV AUTO' (which a positional parser
        # mis-reads), but each board row carries the AUTHORITATIVE governed trim from its model-code family.
        # Targets: three AUTOGRAPH configs (the within-trim rejection loop) and one LUXE (cross-trim, top short).
        return {
            "src":    {"canonical": "84617 AUTOGRAPH AWD SRC/K", "line": "QX60 AUTOGRAPH AWD SUV AUTO",
                       "colors": "", "model": "QX60", "trim": "AUTOGRAPH", "excess": 3, "short": 0},
            "auto_a": {"canonical": "84617 AUTOGRAPH AWD AAA/K", "line": "QX60 AUTOGRAPH AWD SUV AUTO",
                       "colors": "", "model": "QX60", "trim": "AUTOGRAPH", "excess": 0, "short": 3},
            "auto_b": {"canonical": "84617 AUTOGRAPH AWD BBB/G", "line": "QX60 AUTOGRAPH AWD SUV AUTO",
                       "colors": "", "model": "QX60", "trim": "AUTOGRAPH", "excess": 0, "short": 2},
            "auto_c": {"canonical": "84617 AUTOGRAPH AWD CCC/P", "line": "QX60 AUTOGRAPH AWD SUV AUTO",
                       "colors": "", "model": "QX60", "trim": "AUTOGRAPH", "excess": 0, "short": 1},
            "luxe":   {"canonical": "84017 LUXE AWD LLL/K", "line": "QX60 LUXE AWD SUV AUTO",
                       "colors": "", "model": "QX60", "trim": "LUXE", "excess": 0, "short": 9},
        }

    def _order(self, num="TK76338"):
        c = CTP.Candidate(order_number=num, model="QX60", arrival_month="2026-11")
        return CTP.Reconciled(c, CTP.MATCHED, {"combination_id": "src", "model": "QX60", "arrival_month": "2026-11"},
                              "matched by order #", "order#")

    _RULE = {"same_trim_only": {"active": True, "taught_by": "TK76338", "reason": "trim_swap_unavailable"}}

    def test_source_trim_resolves_governed_autograph_never_auto(self):
        r = CTP.evaluate([self._order()], self._board(), session_rules=self._RULE)[0]
        # the governed trim is AUTOGRAPH — never 'AUTO' and never the whole 'AUTOGRAPH AWD SUV AUTO' line slice
        self.assertEqual(r.proof.get("source_trim"), "AUTOGRAPH")
        self.assertNotEqual(r.proof.get("source_trim"), "AUTO")

    def test_default_allows_cross_trim_top_short(self):
        r = CTP.evaluate([self._order()], self._board())[0]
        self.assertEqual(r.proposed_combination_id, "luxe")      # top short, cross-trim allowed when no rule

    def test_same_trim_removes_cross_trim_keeps_autograph_alternates(self):
        r = CTP.evaluate([self._order()], self._board(), session_rules=self._RULE)[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "auto_a")    # LUXE removed; best AUTOGRAPH alternative chosen
        self.assertEqual(r.proof.get("source_trim"), "AUTOGRAPH")

    def test_rejection_loop_advances_within_trim_then_keeps(self):
        # THE LIVE FIX: reject AUTOGRAPH config A -> next AUTOGRAPH B -> reject B -> AUTOGRAPH C -> reject C ->
        # only THEN KEEP. Cross-trim LUXE is never offered at any step; exact-config exclusions drive the loop.
        board = self._board()
        okey = CTP.order_key("TK76338", "")
        inf = {okey: [{"target": "auto_a", "target_canonical": "84617 AUTOGRAPH AWD AAA/K",
                       "reason": "production_restriction"}]}
        r1 = CTP.evaluate([self._order()], board, infeasible=inf, session_rules=self._RULE)[0]
        self.assertEqual(r1.proposed_combination_id, "auto_b")   # A rejected -> next AUTOGRAPH
        inf[okey].append({"target": "auto_b", "reason": "production_restriction"})
        r2 = CTP.evaluate([self._order()], board, infeasible=inf, session_rules=self._RULE)[0]
        self.assertEqual(r2.proposed_combination_id, "auto_c")   # B rejected -> next AUTOGRAPH
        inf[okey].append({"target": "auto_c", "reason": "production_restriction"})
        r3 = CTP.evaluate([self._order()], board, infeasible=inf, session_rules=self._RULE)[0]
        self.assertEqual(r3.decision_state, CTP.KEEP)            # all same-trim alternatives exhausted -> KEEP
        self.assertIn("same-trim only", r3.reason_plain)
        for r in (r1, r2, r3):
            self.assertNotEqual(r.proposed_combination_id, "luxe")   # cross-trim never offered

    def test_keep_when_only_cross_trim_short(self):
        board = {"src": self._board()["src"], "luxe": self._board()["luxe"]}   # only a cross-trim target short
        r = CTP.evaluate([self._order()], board, session_rules=self._RULE)[0]
        self.assertEqual(r.decision_state, CTP.KEEP)
        self.assertIn("same-trim only", r.reason_plain)
        self.assertTrue(r.proof.get("same_trim_only"))

    def test_gate_when_governed_trim_unresolved_never_guesses_auto(self):
        # if the authoritative trim can't be established (no governed model-code family), the rule GATES rather
        # than positionally guessing 'AUTO' from the line — and it does NOT collapse the order to KEEP.
        board = self._board()
        board["src"]["trim"] = ""                                # governed trim unresolved for the source
        r = CTP.evaluate([self._order()], board, session_rules=self._RULE)[0]
        self.assertEqual(r.decision_state, CTP.CANT_EVALUATE)
        self.assertIn("governed trim", r.reason_plain)
        self.assertEqual(r.proof.get("source_trim"), "")

    def test_two_levels_compose(self):
        # exact-config exclusion of auto_a AND same-trim-only together: LUXE removed by the rule, auto_a removed
        # by the exact exclusion -> the remaining same-trim auto_b is chosen.
        okey = CTP.order_key("TK76338", "")
        infeasible = {okey: [{"target": "auto_a", "target_canonical": "84617 AUTOGRAPH AWD AAA/K",
                              "reason": "production_restriction"}]}
        r = CTP.evaluate([self._order()], self._board(), infeasible=infeasible, session_rules=self._RULE)[0]
        self.assertEqual(r.proposed_combination_id, "auto_b")
        self.assertTrue(r.proof.get("same_trim_only"))

    def test_confirmed_cross_trim_change_survives_same_trim_rule(self):
        # an already-confirmed cross-trim change stays locked even after the same-trim rule is learned
        confirmed = {CTP.order_key("TK76338", ""): {"target": "luxe"}}
        r = CTP.evaluate([self._order()], self._board(), confirmed=confirmed, session_rules=self._RULE)[0]
        self.assertTrue(r.confirmed)
        self.assertEqual(r.proposed_combination_id, "luxe")      # lock unaffected by the learned rule


# ---- A4. COMPLETE-CONFIGURATION REQUIRED: a CTP CHANGE must carry both colour dimensions -------------------
class TestCtpCompleteConfiguration(unittest.TestCase):
    """Every recommended CTP CHANGE must be a COMPLETE governed target — model code, trim/drivetrain, and BOTH
    exterior and interior. A target missing a colour dimension's identity is gated, never presented as a
    one-colour change."""

    def _board(self, *, target_complete=True, target_colors="Mineral Black (GAT) / Graphite (G)"):
        return {
            "src": {"canonical": "84317 QX60 LUXE FWD KAD/K", "line": "84317 QX60 LUXE FWD",
                    "colors": "Graphite Shadow (KAD) / Stone Gray (K)", "model": "QX60", "trim": "LUXE",
                    "color_complete": True, "excess": 2, "short": 0},
            "tgt": {"canonical": "84617 QX60 AUTOGRAPH AWD GAT/G", "line": "84617 QX60 AUTOGRAPH AWD",
                    "colors": target_colors, "model": "QX60", "trim": "AUTOGRAPH",
                    "color_complete": target_complete, "excess": 0, "short": 3},
        }

    def _order(self):
        c = CTP.Candidate(order_number="TK1", model="QX60", arrival_month="2026-11")
        return CTP.Reconciled(c, CTP.MATCHED, {"combination_id": "src", "model": "QX60", "arrival_month": "2026-11"},
                              "matched", "order#")

    def test_complete_target_change_shows_both_colours(self):
        r = CTP.evaluate([self._order()], self._board())[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "tgt")
        self.assertIn("(GAT)", r.proposed_colors)             # exterior dimension present with its code
        self.assertIn("(G)", r.proposed_colors)               # interior dimension present with its code
        self.assertIn("/", r.proposed_colors)                 # both dimensions, not one

    def test_incomplete_colour_target_is_gated_not_recommended(self):
        # target missing a colour dimension's identity -> gated (never a one-colour "— Graphite" change)
        r = CTP.evaluate([self._order()],
                         self._board(target_complete=False, target_colors="Graphite (G)"))[0]
        self.assertEqual(r.decision_state, CTP.KEEP)
        self.assertNotEqual(r.proposed_combination_id, "tgt")


# ---- C. CONFIRMED CHANGED is a fixed execution constraint (engine-level) ----------------------------------
class TestConfirmedChangedEngine(unittest.TestCase):
    def _board(self):
        return {
            "src": {"canonical": "src", "line": "QX65 SPORT AWD", "colors": "", "model": "QX65",
                    "excess": 2, "short": 0},
            "t_qbe": {"canonical": "t_qbe", "line": "QX65 LUXE AWD", "colors": "QBE/G", "model": "QX65",
                      "excess": 0, "short": 1},
            "t_dat": {"canonical": "t_dat", "line": "QX65 LUXE AWD", "colors": "DAT/K", "model": "QX65",
                      "excess": 0, "short": 1},
        }

    def _order(self, num):
        c = CTP.Candidate(order_number=num, model="QX65", arrival_month="2026-11")
        return CTP.Reconciled(c, CTP.MATCHED, {"combination_id": "src", "model": "QX65", "arrival_month": "2026-11"},
                              "matched by order #", "order#")

    def test_confirmed_locks_consumes_and_downstream_recomputes(self):
        board = self._board()
        before = {k: (v["excess"], v["short"]) for k, v in board.items()}
        A, B = self._order("TKA"), self._order("TKB")
        # A is confirmed onto t_qbe; B subsequently rejects t_dat
        confirmed = {CTP.order_key("TKA", ""): {"target": "t_qbe"}}
        infeasible = {CTP.order_key("TKB", ""): [{"target": "t_dat", "reason": "above_maximum"}]}
        recs = CTP.evaluate([A, B], board, confirmed=confirmed, infeasible=infeasible)
        by = {r.order_number: r for r in recs}
        # (1)+(3) A is a fixed, confirmed CHANGE to its committed target — never re-optimized
        self.assertEqual(by["TKA"].decision_state, CTP.CHANGE)
        self.assertTrue(by["TKA"].confirmed)
        self.assertEqual(by["TKA"].proposed_combination_id, "t_qbe")
        # (4) A's source excess (2→1) and target shortage (t_qbe 1→0) stay consumed, so...
        # (5) B recomputes from the confirmed state: t_qbe is gone (A took it), B rejected t_dat -> KEEP
        self.assertEqual(by["TKB"].decision_state, CTP.KEEP)
        # (6) the certified board rows (the input dict) are never mutated
        self.assertEqual({k: (v["excess"], v["short"]) for k, v in board.items()}, before)

    def test_confirmed_consumption_cascades_to_next_order(self):
        # A confirmed onto t_qbe consumes one of src's two excess and t_qbe's shortage; a following order C then
        # sees only t_dat available and one remaining excess -> C changes to t_dat (not t_qbe).
        board = self._board()
        A, C = self._order("TKA"), self._order("TKC")
        recs = CTP.evaluate([A, C], board, confirmed={CTP.order_key("TKA", ""): {"target": "t_qbe"}})
        by = {r.order_number: r for r in recs}
        self.assertEqual(by["TKA"].proposed_combination_id, "t_qbe")       # confirmed
        self.assertEqual(by["TKC"].decision_state, CTP.CHANGE)
        self.assertEqual(by["TKC"].proposed_combination_id, "t_dat")       # t_qbe already consumed by A

    def test_later_rejection_cannot_undo_confirmed(self):
        # even if a later order rejects the confirmed target, A stays confirmed on it
        board = self._board()
        A, B = self._order("TKA"), self._order("TKB")
        confirmed = {CTP.order_key("TKA", ""): {"target": "t_qbe"}}
        infeasible = {CTP.order_key("TKB", ""): [{"target": "t_qbe", "reason": "above_maximum"}]}
        recs = CTP.evaluate([A, B], board, confirmed=confirmed, infeasible=infeasible)
        by = {r.order_number: r for r in recs}
        self.assertTrue(by["TKA"].confirmed)
        self.assertEqual(by["TKA"].proposed_combination_id, "t_qbe")       # unchanged by B's rejection


# ---- B. operator route loop (persistence + re-evaluation through the page) --------------------------------
class TestNotAvailableRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))    # governed identity (as the live system always is)
        st = NewInvStore(self.conn, self.p.clock)
        self.src = self._combo(st, "8511", "GAT", "G")          # QX65 SPORT AWD — over-supplied
        self.qbe = self._combo(st, "8501", "QBE", "G")          # QX65 LUXE AWD — short 2
        self.dat = self._combo(st, "8501", "DAT", "K")          # QX65 LUXE AWD — short 1
        self._persist(st, self.src, acq=0, exc=2)
        self._persist(st, self.qbe, acq=2, exc=0)
        self._persist(st, self.dat, acq=1, exc=0)
        # pipeline: TK65797 -> src (certified projection carries the board position)
        self.conn.execute("INSERT INTO production_order(id, manufacturer_order_id, vin, store_scope, "
                          "identity_status, created_at, version) "
                          "VALUES('po1','TK65797','', ?, 'resolved','2026-08-26T10:00:00Z', 1)", (SCOPE,))
        self.conn.execute("INSERT INTO future_supply_projection(id, store_scope, combination_id, arrival_month, "
                          "production_order_id, status, calculation_timestamp) "
                          "VALUES('fs1', ?, ?, '2026-11','po1','current','2026-08-26T10:00:00Z')",
                          (SCOPE, self.src.id))
        self.conn.commit()
        cand = vars(CTP.Candidate(order_number="TK65797", model="QX65", arrival_month="2026-11"))
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "ctp_session",
                                  {"files": [{"id": "f1", "name": "qx65.csv", "model": "QX65",
                                              "candidates": [cand]}]})
        self.full = self.p.login(self.p.op_full)
        self.okey = CTP.order_key("TK65797", "")

    def tearDown(self):
        self.p.close()

    def _combo(self, st, c, e, i):
        return resolve_or_create_planning_combination(
            st, self.p.clock, {"model_code": c, "exterior": e, "interior": i}, SCOPE, source_ref="t")

    def _persist(self, st, cb, *, acq, exc):
        st.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=1, future_supply=0, committed_supply=0, qualifying_supply=1,
            desired_ending_coverage={"target_units": 1.6}, need=float(acq), excess=float(exc), confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": exc, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 0, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _infeasible(self):
        return self.p.app.prefs.get_pref(f"scope::{SCOPE}", "ctp_infeasible", default={})

    def test_full_loop_qbe_then_dat_then_keep_and_confirm(self):
        # governed identity is seeded (live-realistic); assert on combination identity for stability.
        def _change_target(body):
            """The proposed target combination id from the CHANGE card's not-available form."""
            import re
            m = re.search(r'action="/ctp/not-available".*?name=target value="([^"]+)"', body, re.S)
            return m.group(1) if m else None

        with patch("elite.newinv.board_recompute.board_status", return_value={"state": "current"}):
            # round 0 — CHANGE to the QBE/G LUXE AWD target (short 2, ranks first)
            b0 = self.full.get("/ctp").body
            self.assertIn("RECOMMENDED CHANGE", b0)
            self.assertIn("Not available configuration", b0)     # the operator feedback control exists
            self.assertEqual(_change_target(b0), self.qbe.id)    # QBE/G first

            # mark QBE/G NOT AVAILABLE for this order (above max)
            self.full.post("/ctp/not-available", {"order": self.okey, "target": self.qbe.id,
                                                   "target_canonical": "QX65 LUXE AWD QBE/G",
                                                   "reason": "above_maximum", "note": "restricted item above max"})
            marks = self._infeasible().get(self.okey, [])
            self.assertEqual([m["target"] for m in marks], [self.qbe.id])   # recorded, per-order

            # round 1 — re-evaluated NEXT BEST: DAT/K
            b1 = self.full.get("/ctp").body
            self.assertEqual(_change_target(b1), self.dat.id)    # DAT/K now recommended
            self.assertIn("NOT AVAILABLE", b1)                   # provenance trail rendered
            self.assertIn("QX65 LUXE AWD QBE/G", b1)             # the rejected target is shown in the trail

            # mark DAT/K NOT AVAILABLE too -> exhausted -> KEEP best available
            self.full.post("/ctp/not-available", {"order": self.okey, "target": self.dat.id,
                                                   "target_canonical": "QX65 LUXE AWD DAT/K",
                                                   "reason": "package_component_unavailable", "note": ""})
            b2 = self.full.get("/ctp").body
            self.assertIn("best available outcome", b2)
            self.assertIn("KEEP", b2)
            self.assertIsNone(_change_target(b2))                # no CHANGE card remains

            # board untouched: certified excess on the source is still 2 (nothing executed)
            row = self.conn.execute("SELECT excess FROM inventory_plan_result WHERE combination_id=?",
                                    (self.src.id,)).fetchone()
            self.assertEqual(int(row["excess"]), 2)

            # reset marks -> QBE/G recommendation returns; confirm-change records CONFIRMED CHANGED
            self.full.post("/ctp/available-reset", {"order": self.okey})
            self.assertEqual(self._infeasible().get(self.okey, []), [])
            b3 = self.full.get("/ctp").body
            self.assertEqual(_change_target(b3), self.qbe.id)
            self.full.post("/ctp/confirm-change", {"order": self.okey, "target": self.qbe.id})
            b4 = self.full.get("/ctp").body
            self.assertIn("CONFIRMED CHANGED", b4)

    def _rules(self):
        return self.p.app.prefs.get_pref(f"scope::{SCOPE}", "ctp_session_rules", default={})

    def test_trim_swap_reason_sets_session_rule_banner_and_clears(self):
        # A 'Trim swap not available' rejection is the SEPARATE broader rule (same_trim_only), not an exact-config
        # exclusion: it must set a visible learned-rule banner, leave the exact-config store untouched, and be
        # independently clearable — restoring the prior recommendation.
        with patch("elite.newinv.board_recompute.board_status", return_value={"state": "current"}):
            b0 = self.full.get("/ctp").body
            self.assertIn("RECOMMENDED CHANGE", b0)
            self.assertIn("Trim swap not available", b0)         # the new reason option is offered
            self.full.post("/ctp/not-available", {"order": self.okey, "target": self.qbe.id,
                                                  "target_canonical": "QX65 LUXE AWD QBE/G",
                                                  "reason": "trim_swap_unavailable", "note": "OEM: no cross-trim"})
            self.assertTrue(self._rules().get("same_trim_only", {}).get("active"))   # rule learned + provenance
            self.assertEqual(self._rules()["same_trim_only"]["taught_by"], self.okey)
            self.assertEqual(self._infeasible(), {})             # separation: exact-config store untouched
            b1 = self.full.get("/ctp").body
            self.assertIn("LEARNED OEM RULE", b1)                # visible active constraint
            self.assertIn("Same-trim changes only", b1)
            # clear the learned rule -> gone, and CTP recomputes
            self.full.post("/ctp/session-rule-clear", {"rule": "same_trim_only"})
            self.assertEqual(self._rules().get("same_trim_only"), None)
            b2 = self.full.get("/ctp").body
            self.assertNotIn("LEARNED OEM RULE", b2)

    def test_clear_session_wipes_learned_rules_and_exclusions(self):
        with patch("elite.newinv.board_recompute.board_status", return_value={"state": "current"}):
            self.full.get("/ctp")
            self.full.post("/ctp/not-available", {"order": self.okey, "target": self.qbe.id,
                                                  "target_canonical": "QX65 LUXE AWD QBE/G",
                                                  "reason": "trim_swap_unavailable", "note": ""})
            self.assertTrue(self._rules().get("same_trim_only", {}).get("active"))
            self.full.post("/ctp/clear")
            self.assertEqual(self._rules(), {})                  # new CTP session starts clean
            self.assertEqual(self._infeasible(), {})


# ---- D. CONFIRMED CHANGED through the operator routes (persistence + board untouched + correction) --------
class TestConfirmedChangedRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))    # governed identity (as the live system always is)
        st = NewInvStore(self.conn, self.p.clock)
        self.src = self._combo(st, "8511", "GAT", "G")          # QX65 SPORT AWD — excess 2
        self.qbe = self._combo(st, "8501", "QBE", "G")          # QX65 LUXE AWD — short 1
        self.dat = self._combo(st, "8501", "DAT", "K")          # QX65 LUXE AWD — short 1
        self._persist(st, self.src, acq=0, exc=2)
        self._persist(st, self.qbe, acq=1, exc=0)
        self._persist(st, self.dat, acq=1, exc=0)
        for i, onum in enumerate(("TKA", "TKB")):
            self.conn.execute("INSERT INTO production_order(id, manufacturer_order_id, vin, store_scope, "
                              "identity_status, created_at, version) VALUES(?,?,'',?,'resolved',?,1)",
                              (f"po{i}", onum, SCOPE, "2026-08-26T10:00:00Z"))
            self.conn.execute("INSERT INTO future_supply_projection(id, store_scope, combination_id, arrival_month,"
                              " production_order_id, status, calculation_timestamp) "
                              "VALUES(?,?,?,'2026-11',?,'current','2026-08-26T10:00:00Z')",
                              (f"fs{i}", SCOPE, self.src.id, f"po{i}"))
        self.conn.commit()
        cands = [vars(CTP.Candidate(order_number=o, model="QX65", arrival_month="2026-11")) for o in ("TKA", "TKB")]
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "ctp_session",
                                  {"files": [{"id": "f1", "name": "qx65.csv", "model": "QX65", "candidates": cands}]})
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _combo(self, st, c, e, i):
        return resolve_or_create_planning_combination(
            st, self.p.clock, {"model_code": c, "exterior": e, "interior": i}, SCOPE, source_ref="t")

    def _persist(self, st, cb, *, acq, exc):
        st.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=1, future_supply=0, committed_supply=0, qualifying_supply=1,
            desired_ending_coverage={"target_units": 1.6}, need=float(acq), excess=float(exc), confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": exc, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 0, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _target_of(self, body, okey):
        import re
        m = re.search(r'action="/ctp/confirm-change".*?name=order value="%s".*?name=target value="([^"]+)"'
                      % re.escape(okey), body, re.S)
        return m.group(1) if m else None

    def _src_excess_db(self):
        return int(self.conn.execute("SELECT excess FROM inventory_plan_result WHERE combination_id=?",
                                     (self.src.id,)).fetchone()["excess"])

    def test_confirmed_change_constrains_session_and_board_untouched(self):
        with patch("elite.newinv.board_recompute.board_status", return_value={"state": "current"}):
            b0 = self.full.get("/ctp").body
            a_target = self._target_of(b0, "TKA")
            self.assertIsNotNone(a_target)                       # A has a recommended CHANGE target

            # (1) Order A confirms its change
            self.full.post("/ctp/confirm-change", {"order": "TKA", "target": a_target})
            b1 = self.full.get("/ctp").body
            self.assertIn("CONFIRMED CHANGED", b1)
            # (2) Order B subsequently rejects a target
            b_target = self._target_of(b1, "TKB")
            if b_target:                                         # B still has a change target to reject
                self.full.post("/ctp/not-available", {"order": "TKB", "target": b_target,
                                                       "target_canonical": "t", "reason": "above_maximum"})
            b2 = self.full.get("/ctp").body
            # (3) A remains fixed/confirmed after B's rejection
            self.assertIn("CONFIRMED CHANGED", b2)
            self.assertEqual(self.p.app.prefs.get_pref(f"scope::{SCOPE}", "ctp_confirmed", default={})["TKA"]
                             ["target"], a_target)
            # (6) certified board rows are unchanged (source excess still 2 in inventory_plan_result)
            self.assertEqual(self._src_excess_db(), 2)

            # resetting B's unavailable marks does NOT erase A's confirmed execution
            self.full.post("/ctp/available-reset", {"order": "TKB"})
            b3 = self.full.get("/ctp").body
            self.assertIn("CONFIRMED CHANGED", b3)

            # explicit correction path: undo A's confirmation -> A re-optimizes (RECOMMENDED CHANGE returns)
            self.full.post("/ctp/confirm-undo", {"order": "TKA"})
            self.assertNotIn("TKA", self.p.app.prefs.get_pref(f"scope::{SCOPE}", "ctp_confirmed", default={}))
            b4 = self.full.get("/ctp").body
            self.assertIsNotNone(self._target_of(b4, "TKA"))     # A recommended again (no longer locked)
            self.assertEqual(self._src_excess_db(), 2)           # board still untouched throughout


if __name__ == "__main__":
    unittest.main(verbosity=2)
