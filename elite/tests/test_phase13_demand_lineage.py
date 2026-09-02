"""Certified planner consumes APPROVED cross-generation demand lineage (live unblock 2026-08-26).

Current 86-generation QX80 supply cohorts have no exact same-code Speed-to-Sell history, so `run_planning`
refused them (`no_accepted_demand_history`) and they never reached the certified board — CTP showed "no supply/
demand position". This wires the certified planner to the ALREADY-APPROVED Translation/Identity + Lineage
governance: when an approved SAME_FAMILY_CROSS_GEN relationship governs a predecessor generation, its REAL
history is borrowed as `lineage` supporting evidence (never `exact`), the current 86xx cohort keeps its 86xx
identity, and codes/histories stay distinct. With no approved relationship, the honest refusal remains and the
exact missing review is named. No forecasting math changes; no global normalization; QX65 colour-sharing is not
implemented here.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.intake import content_hash
from elite.newinv import board_recompute as BR
from elite.newinv import demand_bridge as DB
from elite.newinv.demand_lineage import LineageDemandResolver
from elite.newinv.planning_runner import plan_from_stores
from elite.ui.views import operator as OP
from elite.workflow import ctp_intake as CTP
from elite.identity.translation import TranslationStore
from elite.identity.lineage import LineageStore, ensure_lineage_proposals
from elite.identity import seed_infiniti as SEED
from elite.tests.test_phase12_real_demand_planning_bridge import sts_workbook, _row, D
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS

LUXE2WD_ROOT = "cross_gen:INFINITI·QX80·LUXE·2WD"


def _pipe(rows):
    return make_xlsx([PIPE_HEADERS] + rows, sheet_name="vehicleInventorySummary0")


def _q80(stock, serial, dis, code, ext, inte, loc, pm=""):
    return [stock, serial, "", "2026", "QX80", code, "QX80", "AUTO", ext, inte, "78900", "74000", loc, dis, "", pm]


# ---- A. resolver + borrow constructor (governance reads only; no fabrication) ----------------------------
class TestLineageResolver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "e.db"))
        self.tx = TranslationStore(self.p.app.prefs, "store:HG")
        SEED.seed(self.tx)
        self.ln = LineageStore(self.p.app.prefs, "store:HG")
        ensure_lineage_proposals(self.tx, self.ln)
        self.r = LineageDemandResolver(self.tx, self.ln)

    def tearDown(self):
        self.p.close()

    def test_family_governance_states(self):
        # data-driven per family: PURE 2WD and LUXE 4WD have NO 83xx predecessor; LUXE 2WD and AUTOGRAPH 4WD do.
        def status(code4):
            return self.r.resolve(("QX80", code4, "QBE", "G"), {})[1]["status"]
        self.assertEqual(status("8611"), "no_relationship")          # 86117 PURE 2WD — no prior-gen PURE 2WD
        self.assertEqual(status("8621"), "no_relationship")          # 86217 LUXE 4WD — no prior-gen LUXE 4WD
        self.assertEqual(status("8631"), "not_approved")             # 86317 LUXE 2WD — relationship exists, pending
        self.assertEqual(status("8661"), "not_approved")             # 86617 AUTOGRAPH 4WD — relationship exists, pending

    def test_not_approved_blocks_then_approved_borrows(self):
        # a real predecessor cohort (8331/QBE/G) present in demand_by_key
        pred = DB.build_demand([D(f"2026{m:02d}", f"H{m}", "25", "83317", "QBE", "G", "QX80 LUXE 2WD")
                                for m in range(1, 6)], latest_midx=DB.midx_of("202605"),
                               current_midx=DB.midx_of("202608"))["cohorts"]
        key = ("QX80", "8631", "QBE", "G")
        preds, note = self.r.resolve(key, pred)
        self.assertEqual(note["status"], "not_approved")             # pending review -> no borrow
        self.assertEqual(preds, [])
        prop = self.ln.latest_for(LUXE2WD_ROOT, "SAME_FAMILY_CROSS_GEN")
        self.ln.approve(prop.id, actor="kyle", at="2026-08-26")
        preds, note = self.r.resolve(key, pred)
        self.assertEqual(note["status"], "approved_lineage")
        self.assertEqual([p.key for p in preds], [("QX80", "8331", "QBE", "G")])   # OLDER gen, same colour

    def test_borrow_cohort_does_not_duplicate_or_relabel(self):
        pred = DB.build_demand([D(f"2026{m:02d}", f"H{m}", "25", "83317", "QBE", "G", "QX80 LUXE 2WD")
                                for m in range(1, 6)], latest_midx=DB.midx_of("202605"),
                               current_midx=DB.midx_of("202608"))["cohorts"][("QX80", "8331", "QBE", "G")]
        cur_key = ("QX80", "8631", "QBE", "G")
        rep = {"model_code": "86317", "exterior": "QBE", "interior": "G"}
        borrowed = DB.borrow_cohort(cur_key, rep, [pred])
        self.assertEqual(borrowed.sales_total, pred.sales_total)      # summed ONCE, not duplicated
        self.assertEqual(borrowed.retail_by_month, pred.retail_by_month)
        self.assertEqual(borrowed.key, cur_key)                       # carries CURRENT identity, not 8331
        self.assertIn("model_code=8631", borrowed.identity)
        self.assertNotIn("8331", borrowed.identity)

    def test_qx65_kcg_k_is_not_a_cross_gen_case(self):
        # READ-ONLY DIAGNOSTIC (no implementation): QX65 LUXE AWD is single-generation, so the cross-gen wiring
        # does not apply; KCG/K stays NEEDS ATTENTION — it is an intra-generation colour question, not this fix.
        preds, note = self.r.resolve(("QX65", "8501", "KCG", "K"), {})
        self.assertEqual(preds, [])
        self.assertEqual(note["status"], "no_relationship")
        self.assertEqual(note["family"], "INFINITI·QX65·LUXE·AWD")


# ---- B. end-to-end through the real board recompute + CTP ------------------------------------------------
class TestLineageEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        self.tx = TranslationStore(self.p.app.prefs, SCOPE)
        SEED.seed(self.tx)
        self.ln = LineageStore(self.p.app.prefs, SCOPE)
        ensure_lineage_proposals(self.tx, self.ln)
        # predecessor 83317 LUXE 2WD real STS history (QBE/G); NO current 86317 history exists
        drows = [_row(f"2026{m:02d}", f"H{m}", "25", "83317", "QBE", "G", "QX80 LUXE 2WD") for m in range(1, 6)]
        x = sts_workbook(drows)
        self.p.import_payload("speed_to_sell", x, chash=content_hash(x))
        # current 86317 supply (QBE/G): 1 arrived + 1 incoming, the incoming carries OEM order TK79123
        xp = _pipe([_q80("S1", "900001", 10, "86317", "QBE", "G", "DLR-INV"),
                    _q80("", "TK79123", 0, "86317", "QBE", "G", "ONS", "2026-11")])
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:q", effective_time=self.p.now_iso())
        self.key = ("QX80", "8631", "QBE", "G")

    def tearDown(self):
        self.p.close()

    def _approve_luxe2wd(self):
        prop = self.ln.latest_for(LUXE2WD_ROOT, "SAME_FAMILY_CROSS_GEN")
        self.ln.approve(prop.id, actor="kyle", at="2026-08-26")

    def _plan_outcome(self):
        ctx = BR.build_planning_context(self.p.app, SCOPE)
        reader, ops = BR._snapshot_reader(self.p.app)
        inv, _s = BR.latest_inventory_snapshot(self.p.app, SCOPE)
        res = plan_from_stores(ctx, reader, dms_source_id=inv, sts_source_id=ops.source_id("speed_to_sell"),
                               current_month="2026-08")
        return next((o for o in res["outcomes"] if o.key == self.key), None)

    def _issued_row(self):
        return self.conn.execute(
            "SELECT r.status, c.canonical_identity FROM inventory_plan_result r "
            "JOIN sellable_combination c ON r.combination_id=c.id "
            "WHERE r.store_scope=? AND r.status='issued' AND c.canonical_identity LIKE '%model_code=8631%'",
            (SCOPE,)).fetchone()

    def test_not_approved_supply_present_issues_supply_only(self):
        # NEW CONTRACT: with the lineage relationship pending (NOT approved) there is still no ACCEPTED demand
        # basis, but this cohort has real current/incoming supply — so it is no longer refused into invisibility.
        # It receives an HONEST supply-only position (no demand borrowed, Need/Excess NOT asserted). Approving
        # the lineage later upgrades it to a demand-backed position (test_approved_... below).
        o = self._plan_outcome()
        self.assertTrue(o.issued)
        self.assertTrue(o.supply_only)
        self.assertEqual(o.planning_state, "supply_only")
        self.assertIsNone(o.refused_reason)
        self.assertIsNone(o.need)                                    # Need NOT asserted (unknown, not zero)
        self.assertIsNone(o.excess)                                  # Excess NOT asserted
        self.assertNotEqual(o.evidence_tier, "lineage")             # nothing borrowed while pending

    def test_approved_issues_lineage_tier_and_persists_current_identity(self):
        self._approve_luxe2wd()
        o = self._plan_outcome()
        self.assertTrue(o.issued)
        self.assertEqual(o.evidence_tier, "lineage")                 # borrowed, NEVER exact
        self.assertEqual((o.current_supply, o.future_supply), (1, 1))  # current 86xx supply, under 8631 identity
        self.assertIn("model_code=8631", o.identity)
        self.assertNotIn("8331", o.identity)
        # certified board persists the lineage-supported CURRENT cohort
        self.assertTrue(BR.recompute_board(self.p.app, SCOPE)["ok"])
        self.assertIsNotNone(self._issued_row())

    def test_ctp_can_evaluate_after_lineage(self):
        self._approve_luxe2wd()
        self.assertTrue(BR.recompute_board(self.p.app, SCOPE)["ok"])
        board = OP._ctp_board(self.p.app, SCOPE)
        pipeline = OP._ctp_pipeline_rows(self.p.app, SCOPE)
        cand = CTP.to_candidate({"order": "TK79123", "model": "QX80", "arrival": "2026-11", "model_code": "86317"})
        out = CTP.evaluate(CTP.reconcile([cand], pipeline), board, now="2026-08")[0]
        self.assertNotEqual(out.decision_state, CTP.CANT_EVALUATE)    # now evaluable (was NEEDS ATTENTION)

    def test_raw_observations_unchanged_by_borrow(self):
        before = self.tx.observations()
        self._approve_luxe2wd()
        BR.recompute_board(self.p.app, SCOPE)
        self.assertEqual(self.tx.observations(), before)             # borrowing reads; never rewrites history

    def test_reject_restores_supply_only_not_borrowed_demand(self):
        self._approve_luxe2wd()
        approved = self._plan_outcome()
        self.assertTrue(approved.issued)                                  # borrowing works while approved …
        self.assertEqual(approved.evidence_tier, "lineage")              # … as a demand-backed lineage position
        prop = self.ln.latest_for(LUXE2WD_ROOT, "SAME_FAMILY_CROSS_GEN")
        self.ln.reject(prop.id, actor="kyle", at="2026-08-27", reason="hold generations separate")
        o = self._plan_outcome()
        # revoking the lineage removes the BORROWED demand: the cohort falls back to an honest supply-only
        # position (supply present, demand unknown) — never a fabricated demand-backed Need/Excess.
        self.assertTrue(o.issued)
        self.assertTrue(o.supply_only)
        self.assertEqual(o.planning_state, "supply_only")
        self.assertNotEqual(o.evidence_tier, "lineage")                 # the borrow is gone
        self.assertIsNone(o.need)
        self.assertIsNone(o.excess)

    def test_codes_stay_distinct_and_exact_still_exact(self):
        # add REAL exact 86317 history -> that cohort issues EXACT (not lineage), proving 86xx keeps its own code
        drows = [_row(f"2026{m:02d}", f"N{m}", "22", "86317", "QBE", "G", "QX80 LUXE 2WD") for m in range(3, 7)]
        x = sts_workbook(drows)
        self.p.import_payload("speed_to_sell", x, chash=content_hash(x))
        o = self._plan_outcome()
        self.assertTrue(o.issued)
        self.assertEqual(o.evidence_tier, "exact")                   # its own history is exact, no borrow needed
        # 83xx predecessor stays a distinct cohort/key, never merged into 86xx
        self.assertNotEqual(DB.dms_planning_key({"model_code": "83317", "exterior": "QBE", "interior": "G"}),
                            DB.dms_planning_key({"model_code": "86317", "exterior": "QBE", "interior": "G"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
