"""Pure-engine tests for the continuous 60-day replenishment + discrete whole-vehicle action engine.

These exercise the checkpoint convention, the forecast tail, actionability (MONITOR vs ACQUIRE), supply
timing, the no-150-day-bug proof, and the arrived-vs-incoming excess mirror -- directly against the pure
functions in elite/newinv/replenishment.py (no service stack, so they are fast and exact)."""
import unittest

from elite.newinv import replenishment as R


def flat(months, rate=1.0):
    return {m: rate for m in months}


# Aug is "now"; the action horizon is the three months after it, forecast tail adds Dec/Jan.
NOW = "2026-08"
ACTION = ["2026-09", "2026-10", "2026-11"]
EXT = R.extended_months(ACTION)                      # + 2026-12, 2027-01
MX = flat(EXT, 1.0)                                   # flat 1 unit/month across horizon + tail


class TestCheckpointConvention(unittest.TestCase):
    # A. end-of-September P consumes September demand; T(September) is the NEXT 60 days (Oct+Nov), not Sep+Oct
    def test_checkpoint_no_double_count(self):
        cps = R.build_checkpoints(arrived=2, confirmed_avail=[], action_avail=[], monthly_expected=MX,
                                  action_horizon=ACTION, current_month=NOW)
        sep = cps[0]
        self.assertEqual(sep.month, "2026-09")
        self.assertAlmostEqual(sep.position, 2 - 1)          # arrived 2 minus September demand consumed
        self.assertAlmostEqual(sep.target, 2.0)              # T(Sep) = Oct + Nov = 1 + 1 (September NOT included)
        # October checkpoint consumes Sep+Oct demand; target is Nov+Dec
        self.assertAlmostEqual(cps[1].position, 2 - 2)
        self.assertAlmostEqual(cps[1].target, 2.0)

    # B. forecast tail: T(November) uses Dec/Jan; Dec/Jan are NOT action-horizon months (never bought now)
    def test_forecast_tail(self):
        self.assertEqual(EXT[-2:], ["2026-12", "2027-01"])
        t_nov = R.forward_target(MX, "2026-11")
        self.assertAlmostEqual(t_nov, 2.0)                   # Dec + Jan forward demand
        self.assertNotIn("2026-12", ACTION)
        self.assertNotIn("2027-01", ACTION)


class TestActionabilityAndNo150Bug(unittest.TestCase):
    # No-150-day-bug: flat demand, T=2, arrived=2, no incoming -> ACQUIRE is bounded to the actionable window,
    # remainder is MONITOR; total acquired is far below the old horizon-demand + buffer (~5).
    def test_no_150_day_bug(self):
        plan = R.allocate(arrived=2, confirmed_avail=[], monthly_expected=MX, action_horizon=ACTION,
                          current_month=NOW)
        self.assertLessEqual(plan.acquire_units, 1)          # not 5; near-term protection only
        self.assertTrue(any(m["month"] == "2026-11" for m in plan.monitor_months))   # Nov gap monitored
        # the monitored Nov gap is flagged not-actionable (beyond the protection window)
        nov = next(m for m in plan.monitor_months if m["month"] == "2026-11")
        self.assertFalse(nov["actionable"])

    # D. a shortage that only appears beyond the protection window is MONITOR, never ACQUIRE now
    def test_future_gap_is_monitor_not_acquire(self):
        # arrived covers the near-term fully; demand only bites late (Nov)
        mx = {"2026-09": 0.0, "2026-10": 0.0, "2026-11": 2.0, "2026-12": 1.0, "2027-01": 1.0}
        plan = R.allocate(arrived=2, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertEqual(plan.acquire_units, 0)              # nothing due now
        self.assertTrue(plan.monitor_months)                 # future risk surfaced

    # C. continuous replenishment: at ~60-day coverage with timely monthly arrivals, no acquisition needed
    def test_continuous_replenishment_holds(self):
        confirmed = ["2026-09", "2026-10", "2026-11"]        # one arrival per month matches 1/mo demand
        plan = R.allocate(arrived=2, confirmed_avail=confirmed, monthly_expected=MX, action_horizon=ACTION,
                          current_month=NOW)
        self.assertEqual(plan.acquire_units, 0)              # steady state holds ~60 days


class TestSupplyTiming(unittest.TestCase):
    # E. a September-available unit repairs September/October; a November-available unit cannot repair September
    def test_timed_slot_repairs_only_from_availability(self):
        base = R.build_checkpoints(arrived=0, confirmed_avail=[], action_avail=[], monthly_expected=MX,
                                   action_horizon=ACTION, current_month=NOW)
        sep_slot = R.build_checkpoints(arrived=0, confirmed_avail=["2026-09"], action_avail=[],
                                       monthly_expected=MX, action_horizon=ACTION, current_month=NOW)
        nov_slot = R.build_checkpoints(arrived=0, confirmed_avail=["2026-11"], action_avail=[],
                                       monthly_expected=MX, action_horizon=ACTION, current_month=NOW)
        # September position improves with the September slot, unchanged with the November slot
        self.assertGreater(sep_slot[0].position, base[0].position)
        self.assertEqual(nov_slot[0].position, base[0].position)      # Nov slot cannot help September


class TestExcessMirror(unittest.TestCase):
    # H. removing an arrived unit that guards early coverage is rejected; a late incoming redirect is allowed
    def test_arrived_guarded_incoming_redirectable(self):
        # low demand so late November arrivals are genuine surplus, while the single arrived unit still
        # guards the early (Sep/Oct) coverage -> incoming is redirected, arrived is retained
        mx = flat(EXT, 0.2)
        plan = R.allocate(arrived=1, confirmed_avail=["2026-11", "2026-11"], monthly_expected=mx,
                          action_horizon=ACTION, current_month=NOW)
        self.assertGreaterEqual(plan.incoming_excess, 1)     # late surplus redirectable
        self.assertEqual(plan.arrived_excess, 0)             # arrived guards early coverage, not stripped

    def test_pure_arrived_overstock_is_removable(self):
        # heavy arrived overstock with light demand -> arrived units are genuine excess
        mx = flat(EXT, 0.2)
        plan = R.allocate(arrived=6, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertGreaterEqual(plan.arrived_excess, 1)
        self.assertEqual(plan.acquire_units, 0)


class TestActionabilityTiming(unittest.TestCase):
    # A. lead-period demand is included: today's quantity uses END-of-lead-checkpoint projected position
    # (arrived + incoming by lead - demand through lead), NOT static arrived+incoming.
    def test_lead_period_demand_included(self):
        r = 0.812
        mx = flat(EXT, r)
        base = R.build_checkpoints(arrived=0, confirmed_avail=[], action_avail=[], monthly_expected=mx,
                                   action_horizon=ACTION, current_month=NOW)
        # protection checkpoint = 2026-09 (now+lead); its position already consumed September demand
        self.assertAlmostEqual(base[0].position, 0 - r)          # NOT static 0; demand depletes it
        plan = R.allocate(arrived=0, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertEqual(plan.marginal_trace[0]["protection_checkpoint"], "2026-09")

    # B + C. QX65 real-failure regression: unit #3 was justified ONLY by October -> now ACQUIRE 2, Oct/Nov MONITOR
    def test_qx65_no_october_frontload(self):
        r = 0.812                                                # T = 2r = 1.624 (real T=1.62386)
        mx = flat(EXT, r)
        plan = R.allocate(arrived=0, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertEqual(plan.acquire_units, 2)                  # was 3 (October front-loaded); now 2
        mon = {m["month"] for m in plan.monitor_months}
        self.assertIn("2026-10", mon)                            # October deferred to a future review
        self.assertIn("2026-11", mon)
        self.assertNotIn("2026-09", mon)                         # the acted-on checkpoint is not a monitor
        # the checkpoint objective picked the loss-minimizing whole quantity at September
        lbq = plan.marginal_trace[0]["loss_by_q"]
        self.assertEqual(min(lbq, key=lbq.get), 2)

    # D. next-review transition: at the SEPTEMBER review, an October gap that was MONITOR becomes ACQUIRE
    def test_next_review_transition(self):
        r = 0.812
        sept_now = "2026-09"                                     # advance the review to September
        horizon = ["2026-10", "2026-11", "2026-12"]
        mx = flat(R.extended_months(horizon), r)
        plan = R.allocate(arrived=0, confirmed_avail=[], monthly_expected=mx, action_horizon=horizon,
                          current_month=sept_now)
        self.assertGreaterEqual(plan.acquire_units, 1)          # October is now the protected checkpoint -> ACQUIRE
        self.assertEqual(plan.marginal_trace[0]["protection_checkpoint"], "2026-10")

    # E. no 150-day regression: the future horizon stays VISIBLE (MONITOR) but is not purchased today
    def test_future_visible_not_purchased(self):
        mx = flat(EXT, 1.0)                                      # T=2, demand 1/mo, arrived 2, no incoming
        plan = R.allocate(arrived=2, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertLessEqual(plan.acquire_units, 1)             # bounded to the protected checkpoint
        self.assertTrue(plan.monitor_months)                    # later months remain visible as future risk


class TestExcessFeasibility(unittest.TestCase):
    # 1 + 2. QX60 8481 XKJ/K regression: a positive summed Delta cannot override a future coverage violation.
    # With aged arrived inventory (Co=1.5) the 4th removal has +Delta but creates a below-target/stockout
    # trajectory, so feasibility stops removal at 3 (not 4). Not hardcoded to 3 -- driven by the constraint.
    def test_qx60_8481_stops_at_three(self):
        r = 0.3802                                            # T = 2r = 0.7604 (real target)
        mx = flat(EXT, r)
        plan = R.allocate(arrived=5, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW, co=1.5)          # aged -> overstock cost raises 4th Delta positive
        self.assertEqual(plan.arrived_excess, 3)
        rejected = [s for s in plan.excess_trace if s.get("rejected")]
        self.assertTrue(rejected)                             # the +Delta 4th removal is explicitly rejected
        self.assertGreater(rejected[0]["delta_remove"], 0)    # positive Delta ...
        self.assertIn("infeasible", rejected[0]["reason"])    # ... blocked by feasibility
        # the rejected trajectory would have gone below target / negative
        after = {x["m"]: x["P"] for x in rejected[0]["after"]}
        self.assertLess(after["2026-11"], 0)

    # 3. an arrived removal that would create a stockout is rejected
    def test_arrived_removal_creating_stockout_rejected(self):
        mx = flat(EXT, 1.0)                                   # T=2, demand 1/mo
        plan = R.allocate(arrived=3, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW, co=2.0)          # strong overstock incentive to over-remove
        # arrived just barely covers; feasibility must not strip below target/stockout
        for step in [s for s in plan.excess_trace if s.get("feasible")]:
            self.assertGreaterEqual(min(x["P"] - x["T"] for x in step["after"]), -1e-6)

    # 4. an arrived removal that stays >= T at every checkpoint is allowed
    def test_arrived_removal_above_target_allowed(self):
        mx = flat(EXT, 0.2)                                   # T=0.4, light demand
        plan = R.allocate(arrived=6, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertGreaterEqual(plan.arrived_excess, 1)       # genuine surplus removable
        for step in [s for s in plan.excess_trace if s.get("feasible")]:
            self.assertGreaterEqual(min(x["P"] - x["T"] for x in step["after"]), -1e-6)

    # 5. a timed incoming redirect is allowed when later coverage stays protected
    def test_incoming_redirect_allowed_when_protected(self):
        mx = flat(EXT, 0.2)                                   # low demand; Nov arrivals are true surplus
        plan = R.allocate(arrived=1, confirmed_avail=["2026-11", "2026-11"], monthly_expected=mx,
                          action_horizon=ACTION, current_month=NOW)
        self.assertGreaterEqual(plan.incoming_excess, 1)
        self.assertEqual(plan.arrived_excess, 0)              # arrived guards early coverage

    # 6. a timed incoming redirect is rejected when removing it creates an unrepairable future shortage
    def test_incoming_redirect_rejected_when_needed(self):
        # arrived covers Sep/Oct but Nov demand needs the Nov arrival; removing it stocks out November
        mx = {"2026-09": 0.4, "2026-10": 0.4, "2026-11": 2.0, "2026-12": 0.4, "2027-01": 0.4}
        plan = R.allocate(arrived=1, confirmed_avail=["2026-11"], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertEqual(plan.incoming_excess, 0)             # Nov arrival is needed -> not redirected

    # 7. feasibility is recomputed after every removal (sequential)
    def test_sequential_feasibility_recompute(self):
        mx = flat(EXT, 0.3802)
        plan = R.allocate(arrived=5, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW, co=1.5)
        applied = [s for s in plan.excess_trace if s.get("feasible")]
        # every APPLIED removal left a feasible (>= target) trajectory at the moment it was applied
        for step in applied:
            self.assertGreaterEqual(min(x["P"] - x["T"] for x in step["after"]), -1e-6)


class TestDiscreteCrossing(unittest.TestCase):
    # G. a fractional deficit can round to a whole acquisition (crossing the continuous target)
    def test_crossing_add(self):
        # small but real forward demand, zero supply -> at least represent with one whole unit
        mx = flat(EXT, 0.35)                                  # T ~ 0.7 forward
        plan = R.allocate(arrived=0, confirmed_avail=[], monthly_expected=mx, action_horizon=ACTION,
                          current_month=NOW)
        self.assertEqual(plan.acquire_units, 1)               # one whole car for a 0.7 objective


if __name__ == "__main__":
    unittest.main(verbosity=2)
