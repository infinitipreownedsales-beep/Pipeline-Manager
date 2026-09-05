"""PPO live blocker — a governed manufacturer-offered identity (86417 QX80 SPORT 4WD, 8641) can be ENTERED and
evaluated even when no sellable_combination / planning row exists yet.

Covers the required contract:
  * PPO entry resolves/creates the governed combination identity on demand (no Supply / Production Order /
    Vehicle Unit / demand);
  * a governed manufacturer offer needs no "Truly external" marking;
  * FIRM / DENY when a certified position exists; honest REVIEW (never a false "already covered" DENY) when the
    governed combination has no certified demand evidence;
  * the shared opportunity evaluator treats a missing certified position as UNKNOWN demand (REVIEW), never zero;
  * committed-supply count-once and existing PPO workstate are preserved.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.supply import SupplyService
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.identity.translation import TranslationStore
from elite.identity import seed_infiniti as SEED
from elite.ids import new_id
from elite.ui.views import operator as OP
from elite.operatorstd import opportunity as OPP


# ---- shared opportunity evaluator: missing position is UNKNOWN demand -> REVIEW, never a false DENY -------
class TestOpportunityUnknownDemand(unittest.TestCase):
    def test_offer_with_no_position_is_review_not_deny(self):
        offer = OPP.Offer(id="o1", combination_key="8641|GAT|G", quantity=1, orderable=True, label="QX80 SPORT")
        res = OPP.evaluate_portfolio([offer], {})                 # no positions at all
        v = res.verdicts[0]
        self.assertEqual(v.recommendation, OPP.REVIEW)            # unknown demand -> REVIEW
        self.assertNotIn("already covered", v.why)

    def test_offer_with_covered_position_is_a_real_deny(self):
        pos = OPP.Position("8641|GAT|G", demand=0.0, owned=0.0, demand_known=True, label="QX80 SPORT")
        res = OPP.evaluate_portfolio([OPP.Offer(id="o1", combination_key="8641|GAT|G", quantity=1, orderable=True)],
                                     {pos.combination_key: pos})
        self.assertEqual(res.verdicts[0].recommendation, OPP.DENY)   # a real certified-covered DENY still holds


def _combo(store, clock, code, ext, inte):
    return resolve_or_create_planning_combination(
        store, clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="ppo-test")


def _persist(store, comb, *, acquire):
    store.add_plan(InventoryPlanResult(
        id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
        expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
        desired_ending_coverage={"target_units": 1.6}, need=float(acquire), excess=0.0, confidence="medium",
        evidence={"model": "m", "decision": {"acquire_units": acquire, "arrived_excess": 0, "incoming_excess": 0,
                                              "monitor_months": []}},
        policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
        status="issued", months=[]))


class TestPpoGoverned8641(unittest.TestCase):
    OFFERS = ("86417 GAT/G", "86417 KCN/G", "86417 QBE/G", "86417 XKJ/G")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        self.store = NewInvStore(self.conn, self.p.clock)
        self.full = self.p.login(self.p.op_full)
        self.full.post("/ordering/ppo/new", {"month": "2026-09"})
        self.win = OP._ws_get(self.p.app, SCOPE, "ppo_current_window", "")

    def tearDown(self):
        self.p.close()

    def _offer(self, combo, *, qty=1, external=False):
        form = {"window": self.win, "combo": combo, "quantity": str(qty)}
        if external:
            form["external"] = "1"
        self.full.post("/ordering/ppo/offer", form)
        return (OP._ws_get(self.p.app, SCOPE, f"ppo_offers::{self.win}", []) or [])[-1]

    def _combos_in_db(self, code4):
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM sellable_combination WHERE store_scope=? AND canonical_identity LIKE ?",
            (SCOPE, f"%model_code={code4}|%")).fetchone()["n"]

    # 1/2/3: all four governed 86417 offers enter WITHOUT external, resolve to QX80 SPORT 4WD, and (no certified
    # position) evaluate to an honest REVIEW — never disappearing and never a false DENY.
    def test_governed_8641_offers_enter_and_review(self):
        for combo in self.OFFERS:
            o = self._offer(combo)
            self.assertTrue(o["governed"])                        # resolved to a governed identity
            self.assertFalse(o["external"])                       # no "truly external" marking required
            self.assertTrue(o["combination_id"])                  # combination identity resolved/created
            self.assertIn("QX80 SPORT 4WD", o["combo"])           # governed human build
        b = self.full.get("/ordering/ppo", window=self.win).body
        self.assertNotIn("already covered", b)                    # never a false DENY
        self.assertGreaterEqual(b.count("REVIEW"), 4)             # each governed-but-uncertified offer -> REVIEW
        for ext in ("GAT", "KCN", "QBE", "XKJ"):
            self.assertIn(ext, b)                                 # no valid 8641 offer disappears

    # 3: resolving the identity creates the combination row ONLY — no NEW supply / production order / vehicle
    # unit / demand is fabricated by entering the offer (measured as a delta against the fixture baseline)
    def test_resolution_creates_identity_only_no_supply(self):
        def counts():
            return {t: self.conn.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE store_scope=?",
                                         (SCOPE,)).fetchone()["n"]
                    for t in ("current_supply_projection", "production_order", "vehicle_unit",
                              "inventory_plan_result", "sellable_combination")}
        before = counts()
        self._offer("86417 GAT/G")
        after = counts()
        self.assertGreaterEqual(self._combos_in_db("8641"), 1)    # the combination identity now exists
        self.assertEqual(after["sellable_combination"], before["sellable_combination"] + 1)  # exactly one identity
        for t in ("current_supply_projection", "production_order", "vehicle_unit", "inventory_plan_result"):
            self.assertEqual(after[t], before[t], f"{t} must be unchanged by a PPO offer")

    # 5: when a certified position exists for the governed combination, evaluate normally (FIRM on a real shortage)
    def test_certified_shortage_firms(self):
        c = _combo(self.store, self.p.clock, "86417", "GAT", "G")
        _persist(self.store, c, acquire=2)
        o = self._offer("86417 GAT/G")
        self.assertEqual(o["combination_id"], c.id)               # keyed to the SAME certified combination
        b = self.full.get("/ordering/ppo", window=self.win).body
        self.assertIn("FIRM", b)
        self.assertNotIn("already covered", b)

    # 5: a certified position that is already covered is a REAL DENY (distinct from the no-evidence REVIEW)
    def test_certified_covered_denies(self):
        c = _combo(self.store, self.p.clock, "86417", "KCN", "G")
        _persist(self.store, c, acquire=0)                        # certified, but no shortage
        self._offer("86417 KCN/G")
        b = self.full.get("/ordering/ppo", window=self.win).body
        self.assertIn("already covered", b)                      # a real certified DENY, evidence-based

    # 7: a FIRM on a governed 8641 offer enters committed supply exactly once (existing count-once rail)
    def test_firm_commits_supply_once(self):
        c = _combo(self.store, self.p.clock, "86417", "GAT", "G")
        _persist(self.store, c, acquire=2)
        o = self._offer("86417 GAT/G", qty=1)
        self.full.post("/ordering/ppo/record",
                       {"window": self.win, "offer": o["id"], "action": "FIRM", "action_qty": "1"})
        supply = SupplyService(NewInvStore(self.conn, self.p.clock), self.p.clock)
        committed = [x for x in supply.qualifying_supply(c.id, SCOPE) if x["kind"] == "committed"]
        self.assertEqual(len(committed), 1)
        # re-record the same FIRM — still counted once (idempotent by identity)
        self.full.post("/ordering/ppo/record",
                       {"window": self.win, "offer": o["id"], "action": "FIRM", "action_qty": "1"})
        committed = [x for x in supply.qualifying_supply(c.id, SCOPE) if x["kind"] == "committed"]
        self.assertEqual(len(committed), 1)

    # 8: entering a new 8641 offer never clears/rebuilds an existing window or its worked FIRM
    def test_existing_workstate_survives(self):
        c = _combo(self.store, self.p.clock, "86417", "GAT", "G")
        _persist(self.store, c, acquire=2)
        first = self._offer("86417 GAT/G")
        self.full.post("/ordering/ppo/record",
                       {"window": self.win, "offer": first["id"], "action": "FIRM", "action_qty": "1"})
        self._offer("86417 QBE/G")                                # add another offer afterward
        offers = OP._ws_get(self.p.app, SCOPE, f"ppo_offers::{self.win}", []) or []
        self.assertEqual(len(offers), 2)                          # both offers present — nothing rebuilt
        kept = next(o for o in offers if o["id"] == first["id"])
        self.assertEqual(kept.get("operator_action"), "FIRM")    # the existing FIRM survives unchanged


if __name__ == "__main__":
    unittest.main(verbosity=2)
