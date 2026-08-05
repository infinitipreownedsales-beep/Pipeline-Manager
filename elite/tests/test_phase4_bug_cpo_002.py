"""Phase 4 focused regression for BUG-CPO-002 — continuous-replenishment vs. discrete-
commitment conflation. Proves the canonical contracts WITHOUT implementing the CPO workflow:
a synthetic CPO-like commitment stands in as Committed Supply only.

Ten-point contract:
 1. Baseline Demand is calculated.
 2. Baseline qualifying Supply is calculated.
 3. Need is calculated.
 4. An approved synthetic CPO-like commitment is added only as Committed Supply.
 5. Demand remains unchanged.
 6. Qualifying Supply increases by exactly the committed quantity.
 7. Need decreases or remains unchanged.
 8. Need never increases.
 9. Replaying the same commitment does not count twice.
10. Changing the commitment label / acquisition path does not create a different Demand result.
"""
import os
import tempfile
import unittest

from elite.newinv.fixtures import SCOPE, Phase4


class TestBugCpo002(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase4(os.path.join(self.tmp, "elite.db"))
        self.c = self.p.combination(exterior_color="BLACK")
        months = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p.seed_retail(self.c, {m: 2 for m in months})    # demand 2/mo
        self.p.seed_availability(self.c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2,
                                          "snapshot": "full"} for m in months])

    def tearDown(self):
        self.p.close()

    def test_bug_cpo_002_full_contract(self):
        # 1. Baseline Demand
        d0 = self.p.issue_demand(self.c)
        self.assertTrue(d0.monthly_expected)
        baseline_demand = dict(d0.monthly_expected)

        # 2. Baseline qualifying Supply (none yet)
        qual0 = len(self.p.supply.qualifying_supply(self.c.id, SCOPE))
        self.assertEqual(qual0, 0)

        # 3. Need calculated
        plan0 = self.p.issue_plan(self.c, d0, coverage_target=2)   # requirement 12 + 2 = 14
        self.assertGreater(plan0.need, 0)
        baseline_need = plan0.need

        # 4. Approved synthetic CPO-like commitment added ONLY as Committed Supply
        self.p.approved_commitment(self.c, unit_id="cpo_sep", arrival_month="2026-09",
                                   commitment_type="cpo_like")
        counts = self.p.supply.counts(self.c.id, SCOPE)
        self.assertEqual(counts["committed"], 1)
        self.assertEqual(counts["current"], 0)
        self.assertEqual(counts["future"], 0)                      # not double-projected as future

        # 5. Demand unchanged (Demand never reads supply/commitment)
        d1 = self.p.issue_demand(self.c)
        self.assertEqual(d1.monthly_expected, baseline_demand)

        # 6. Qualifying Supply increases by exactly the committed quantity (+1)
        qual1 = len(self.p.supply.qualifying_supply(self.c.id, SCOPE))
        self.assertEqual(qual1, qual0 + 1)

        # 7 & 8. Need decreases or unchanged, never increases
        plan1 = self.p.issue_plan(self.c, d1, coverage_target=2)
        self.assertLessEqual(plan1.need, baseline_need)
        self.assertEqual(plan1.need, baseline_need - 1)            # exactly one unit of Need retired

        # 9. Replaying the SAME commitment does not count twice
        #    (the qualifying set dedups by unit identity; re-approving is idempotent by identity)
        self.p.supply.propose_commitment(self.c.id, SCOPE, commitment_type="cpo_like",
                                         unit_or_order_id="cpo_sep", arrival_month="2026-09")
        # even if a duplicate commitment record for the same unit exists, qualifying counts once
        qual_dup = len(self.p.supply.qualifying_supply(self.c.id, SCOPE))
        self.assertEqual(qual_dup, qual1)
        plan_dup = self.p.issue_plan(self.c, d1, coverage_target=2)
        self.assertEqual(plan_dup.need, plan1.need)                # no double credit

        # 10. Changing the commitment label / acquisition path yields the SAME Demand
        self.p.approved_commitment(self.c, unit_id="path_unit", arrival_month="2026-10",
                                   commitment_type="dealer_trade_like")
        d2 = self.p.issue_demand(self.c)
        self.assertEqual(d2.monthly_expected, baseline_demand)

    def test_bug_cpo_002_ladder_is_monotone(self):
        # Adding qualifying supply one unit at a time never raises Need (monotone non-increasing).
        d = self.p.issue_demand(self.c)
        needs = [self.p.issue_plan(self.c, d, coverage_target=2).need]
        for i in range(6):
            self.p.approved_commitment(self.c, unit_id=f"cpo_{i}", arrival_month="2026-09")
            needs.append(self.p.issue_plan(self.c, d, coverage_target=2).need)
        for earlier, later in zip(needs, needs[1:]):
            self.assertLessEqual(later, earlier)               # never increases
        self.assertEqual(needs[0] - needs[-1], min(needs[0], 6))   # each committed unit retired one Need


if __name__ == "__main__":
    unittest.main()
