"""Service-Loaner self-balancing planning engine — calculated future acquisition need from authoritative
state (no invented numbers), with unknowns preserved as unknowns."""
import os
import tempfile
import unittest

from elite.loaner.self_balancing import compute_requirement, build_requirement
from elite.loaner.fixtures import Phase6
from elite.workflow.fixtures import SCOPE


class TestComputeRequirement(unittest.TestCase):
    def test_at_or_above_target_no_exits_needs_zero(self):
        r = compute_requirement(desired=20, current_active=27)
        self.assertEqual(r.calculated_need, 0)
        self.assertEqual(r.resolution, "resolved_zero")
        self.assertEqual(r.source, "none")              # do not add — preserve Retail supply

    def test_exits_below_target_creates_need(self):
        # 27 active, 9 governed exits before Oct, 0 committed replacements -> remaining 18, need 2
        r = compute_requirement(desired=20, current_active=27, projected_future_exits=9)
        self.assertEqual(r.remaining, 18)
        self.assertEqual(r.calculated_need, 2)
        self.assertEqual(r.resolution, "resolved_need")
        self.assertEqual(r.source, "order_specific")    # order for SL rather than short Retail

    def test_committed_incoming_reduces_need(self):
        r = compute_requirement(desired=20, current_active=27, projected_future_exits=9, committed_incoming=1)
        self.assertEqual(r.calculated_need, 1)          # 1 already designated incoming covers one replacement

    def test_projected_fleet_above_target_no_order(self):
        r = compute_requirement(desired=20, current_active=25, projected_future_exits=2)  # remaining 23 > 20
        self.assertEqual(r.calculated_need, 0)
        self.assertEqual(r.source, "none")

    def test_unresolved_timing_is_lower_bound_not_guessed(self):
        r = compute_requirement(desired=20, current_active=27, unresolved_timing_units=27)
        self.assertEqual(r.calculated_need, 0)          # at target -> zero, but...
        self.assertTrue(r.is_lower_bound)               # exits unknown could raise it; stated, not fabricated

    def test_no_target_cannot_plan(self):
        r = compute_requirement(desired=None, current_active=27)
        self.assertEqual(r.resolution, "no_target")
        self.assertEqual(r.source, "unresolved")
        self.assertEqual(r.calculated_need, 0)          # never fabricate a need without a target

    def test_releasing_now_excluded_from_remaining(self):
        r = compute_requirement(desired=20, current_active=27, releasing_now=3)  # remaining 24
        self.assertEqual(r.remaining, 24)
        self.assertEqual(r.calculated_need, 0)          # still above target


class TestBuildRequirementLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _prefs(self):
        from elite.ui.prefs import PrefsService
        return PrefsService(self.p.store.conn, self.p.clock)

    def test_build_counts_and_reads_target(self):
        for i in range(4):
            self.p.make_active(f"1GNSKBKC5FR10000{i}")               # 4 active units
        from elite.loaner.loaner_cockpit import MetaPrefs, set_desired_fleet
        prefs = self._prefs()
        set_desired_fleet(MetaPrefs(prefs, SCOPE), 3)                 # target below current
        r = build_requirement(self.p.store.conn, SCOPE, prefs)
        self.assertEqual(r.current_active, 4)
        self.assertEqual(r.desired, 3)
        self.assertEqual(r.calculated_need, 0)                       # 4 >= 3, needs none


if __name__ == "__main__":
    unittest.main(verbosity=2)
