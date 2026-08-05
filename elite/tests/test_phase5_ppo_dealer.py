"""Phase 5 acceptance — PPO + Dealer Trade workflows (items 26-36)."""
import os
import tempfile
import unittest

from elite.workflow.fixtures import SCOPE, Phase5


class TestPhase5PpoDealer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))
        self.c, self.d, self.plan = self.p.need_combo(exterior_color="BLACK")

    def tearDown(self):
        self.p.close()

    def _qual(self):
        return len(self.p.supply.qualifying_supply(self.c.id, SCOPE))

    # ---- PPO ---------------------------------------------------------------
    def test_26_ppo_distinct_from_cpo(self):
        w = self.p.ppo.propose(self.p.full, SCOPE, order_or_unit_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        self.assertEqual(w.workflow_type, "ppo")                   # distinguishable type

    def test_27_ppo_proposal_has_no_supply_effect(self):
        self.p.ppo.propose(self.p.full, SCOPE, order_or_unit_id="po", combination_id=self.c.id,
                           arrival_month="2026-10")
        self.assertEqual(self._qual(), 0)

    def test_28_approved_ppo_creates_at_most_one_commitment(self):
        w = self.p.ppo.propose(self.p.full, SCOPE, order_or_unit_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        self.p.ppo.approve(self.p.full, SCOPE, w)
        self.assertEqual(self._qual(), 1)
        # a replayed approval does not add a second unit
        self.p.ppo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.assertEqual(self._qual(), 1)

    def test_29_rejected_ppo_has_no_supply_effect(self):
        w = self.p.ppo.propose(self.p.full, SCOPE, order_or_unit_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        self.p.ppo.reject(self.p.full, SCOPE, w)
        self.assertEqual(self._qual(), 0)

    # ---- Dealer Trade ------------------------------------------------------
    def test_30_dealer_trade_proposal_has_no_supply_effect(self):
        self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu1", combination_id=self.c.id, arrival_month="2026-10")
        self.assertEqual(self._qual(), 0)

    def test_31_dealer_trade_request_sent_has_no_supply_effect(self):
        w = self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu1", combination_id=self.c.id, arrival_month="2026-10")
        self.p.dt.send_request(self.p.full, SCOPE, w)
        self.assertEqual(self._qual(), 0)

    def test_32_dealer_trade_acceptance_per_contract(self):
        w = self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu1", combination_id=self.c.id, arrival_month="2026-10")
        self.p.dt.send_request(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        r = self.p.dt.accept(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))   # default: not firm
        self.assertEqual(r["outcome"], "NO_SUPPLY_EFFECT")
        self.assertEqual(self._qual(), 0)                          # acceptance alone is not supply

    def test_33_completed_dealer_trade_creates_one_qualifying_supply(self):
        w = self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu1", combination_id=self.c.id, arrival_month="2026-10")
        self.p.dt.send_request(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.dt.accept(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        r = self.p.dt.complete(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), received_unit_id="vu1")
        self.assertEqual(r["outcome"], "COMPLETED_TO_CURRENT")
        self.assertEqual(self._qual(), 1)

    def test_34_terminal_dealer_trades_do_not_count(self):
        for i, status in enumerate(("REJECTED", "EXPIRED", "WITHDRAWN")):
            w = self.p.dt.propose(self.p.full, SCOPE, unit_identity=f"vu{i}", combination_id=self.c.id,
                                  arrival_month="2026-10")
            self.p.dt.terminate(self.p.full, SCOPE, w, to_status=status)
        # a failed trade after acceptance
        w = self.p.dt.propose(self.p.full, SCOPE, unit_identity="vuF", combination_id=self.c.id, arrival_month="2026-10")
        self.p.dt.send_request(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.dt.accept(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.dt.terminate(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), to_status="FAILED")
        self.assertEqual(self._qual(), 0)                          # none contribute

    def test_35_unknown_dealer_trade_attempts_not_invented(self):
        # With no recorded dealer-trade action, there is no supply and no dealer_trade row.
        self.assertEqual(self._qual(), 0)
        rows = self.p.wf.conn.execute("SELECT COUNT(*) n FROM dealer_trade_action").fetchone()["n"]
        self.assertEqual(rows, 0)

    def test_36_received_unit_reconciles_with_completed_trade(self):
        w = self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu_recv", combination_id=self.c.id,
                              arrival_month="2026-10")
        self.p.dt.send_request(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.p.dt.accept(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        r = self.p.dt.complete(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), received_unit_id="vu_recv")
        recon = [x for x in self.p.wf.reconciliations_for(w.id) if x.outcome == "COMPLETED_TO_CURRENT"][0]
        self.assertEqual(recon.subject_identity, "vu_recv")        # received unit reconciles to the trade
        confs = self.p.wf.conn.execute("SELECT * FROM execution_confirmation WHERE workflow_id=?", (w.id,)).fetchall()
        self.assertTrue(confs and confs[0]["subject_identity"] == "vu_recv")


if __name__ == "__main__":
    unittest.main()
