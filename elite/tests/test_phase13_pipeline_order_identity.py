"""Pipeline repair (live acceptance 2026-08-26): summary language + current-order identity.

(1) Model headers distinguish COMBINATIONS from VEHICLES ("3 acquire combination(s) · 6 vehicle(s) to acquire")
    so "3 combinations x 2 = 6" reads truthfully. Acquisition math is unchanged; the total reconciles.
(2) An ACQUIRE must never terminate on an obsolete older-generation order code merely because historical demand
    lived there. Demand-evidence identity (where the history lived) stays distinct from executable order
    identity: an older-generation code whose family has a newer orderable version is re-pointed to it; one with
    NO current orderable version is GATED (never guessed). Governed via the existing Translation/Identity layer;
    83xx and 86xx stay distinct — no global normalization, no rewritten history.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id
from elite.identity.translation import (TranslationStore, FamilyKey, VariantRow, derive_orderability)
from elite.identity import seed_infiniti as SEED
from elite.ui.views.operator import _executable_order_identity


class TestExecutableOrderBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "e.db"))
        self.st = TranslationStore(self.p.app.prefs, "store:HG")
        SEED.seed(self.st)

    def tearDown(self):
        self.p.close()

    def test_obsolete_gen_with_no_current_orderable_is_gated(self):
        # LUXE 2WD and AUTOGRAPH 4WD: 86-gen exists but is pending ($0) and 83-gen is pending too -> no current
        # orderable version -> the 83-gen ACQUIRE is GATED, never an obsolete executable order.
        self.assertEqual(_executable_order_identity(self.st, "8331")[0], "gated")
        self.assertEqual(_executable_order_identity(self.st, "8361")[0], "gated")

    def test_current_generation_gates_when_orderability_unresolved(self):
        # 86-gen codes exist but are pending ($0) -> current-generation orderability unresolved -> GATE
        for code in ("8631", "8661"):
            self.assertEqual(_executable_order_identity(self.st, code)[0], "gated")

    def test_single_generation_family_stays_current(self):
        # PURE 2WD is single-generation in the seed (only 86117) -> the multi-gen rule does not apply
        self.assertEqual(_executable_order_identity(self.st, "8611")[0], "current")

    def test_older_gen_never_current_when_newer_exists_even_if_old_base_priced(self):
        # SPORT 4WD (83417 priced) and PURE 4WD (83017 priced): a NEWER 86-gen exists but is not orderable, so
        # the older priced BASE must NEVER become the executable order -> GATE, never 'current' on 83417/83017.
        self.assertEqual(_executable_order_identity(self.st, "8381")[0], "gated")
        self.assertEqual(_executable_order_identity(self.st, "8301")[0], "gated")

    def test_supersede_only_when_newest_generation_positively_orderable(self):
        # positively govern LUXE 2WD 86317 as orderable -> the older 8331 supersedes to it; the 86 code is current
        fam = FamilyKey("INFINITI", "QX80", "LUXE", "2WD")
        r = VariantRow(fam, "86317", "86", "BASE", True, "seen_latest", True,
                       derive_orderability("seen_latest", True), ("chart",))
        self.st.add_variant_row(r, actor="k", at="t")
        self.st.approve_variant(fam, "86317", "86", "BASE", actor="k", at="t")
        self.assertEqual(_executable_order_identity(self.st, "8331"), ("supersede", "86317", fam.as_str()))
        self.assertEqual(_executable_order_identity(self.st, "8631"), ("current", "86317", fam.as_str()))

    def test_ungoverned_code_left_as_is(self):
        self.assertEqual(_executable_order_identity(self.st, "8131")[0], "current")   # QX50 not seeded -> as-is


class TestPipelineHomeRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "e.db"))
        self.conn = self.p.stack.db.conn
        self.st = TranslationStore(self.p.app.prefs, "store:HG")
        SEED.seed(self.st)
        self.store = NewInvStore(self.conn, self.p.clock)
        # QX65: 3 acquire combinations x 2 vehicles = 6
        for e, i in (("QBE", "G"), ("DAT", "K"), ("GAT", "G")):
            self._plan("8501", e, i, acq=2)
        # QX80: two multi-generation acquires that must GATE (86-gen not orderable) — a prior-gen LUXE 2WD
        # demand cohort (8331) and a current 86-gen SPORT (8641). QX65 8501 is single-generation -> executable.
        self._plan("8331", "QBE", "G", acq=1)
        self._plan("8641", "GAT", "G", acq=1)
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _plan(self, code, e, i, *, acq):
        cb = resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": e, "interior": i}, SCOPE, source_ref="t")
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": float(acq)}, need=float(acq), excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": 0, "incoming_excess": 0,
                                                 "target_level": float(acq), "incoming_in_horizon": 0,
                                                 "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def test_order_now_excludes_gated_and_shows_them_separately(self):
        # 6 executable (QX65: 3 combos x 2) + 2 gated (QX80 8331, 8641) -> order-now = 6, NOT 8; gated shown = 2
        b = self.full.get("/").body
        self.assertIn("3 acquire combination(s) · 6 vehicle(s) to acquire", b)     # QX65 executable
        flat = b.replace(" ", "")
        self.assertIn("Vehiclestoordernow</dt><dd>6</dd>".replace(" ", ""), flat)  # order-now = 6, not 8
        self.assertIn("Vehiclesneededbutorder-gated</dt><dd>2</dd>".replace(" ", ""), flat)  # gated shown = 2

    def test_obsolete_qx80_acquire_is_gated_not_ordered(self):
        b = self.full.get("/").body
        self.assertIn("ORDER GATED", b)                   # the obsolete/unresolved QX80 acquires are gated
        self.assertIn("no current orderable version", b)
        self.assertIn("gated combination(s)", b)          # model header distinguishes gated combos/vehicles


if __name__ == "__main__":
    unittest.main(verbosity=2)
