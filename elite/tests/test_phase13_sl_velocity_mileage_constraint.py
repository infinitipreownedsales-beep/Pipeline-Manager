
import unittest

from elite.loaner.sl_decision import _velocity_mileage_constraint


class TestVelocityMileageConstraint(unittest.TestCase):
    def test_above_cap_is_definitive_release_due(self):
        r = _velocity_mileage_constraint(10788, 10000)
        self.assertEqual(r["status"], "breached")
        self.assertTrue(r["release_due_now"])

    def test_exact_cap_has_no_remaining_loaner_mileage(self):
        r = _velocity_mileage_constraint(10000, 10000)
        self.assertEqual(r["status"], "at_cap")
        self.assertTrue(r["release_due_now"])

    def test_below_cap_does_not_force_action(self):
        r = _velocity_mileage_constraint(7436, 10000)
        self.assertEqual(r["status"], "within_cap")
        self.assertFalse(r["release_due_now"])

    def test_missing_mileage_fails_closed_without_false_pull(self):
        r = _velocity_mileage_constraint(None, 10000)
        self.assertEqual(r["status"], "unknown")
        self.assertFalse(r["release_due_now"])

    def test_missing_cap_is_not_applicable(self):
        r = _velocity_mileage_constraint(12000, None)
        self.assertEqual(r["status"], "not_applicable")
        self.assertFalse(r["release_due_now"])


if __name__ == "__main__":
    unittest.main()
