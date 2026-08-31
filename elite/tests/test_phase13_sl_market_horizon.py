import unittest

from elite.loaner.sl_decision import _market_horizon_dates


class TestServiceLoanerMarketHorizon(unittest.TestCase):
    def test_zero_keep_horizon_has_identical_market_dates(self):
        now, future = _market_horizon_dates("2026-02-10", 202, 0)
        self.assertEqual(now, "2026-08-31")
        self.assertEqual(future, "2026-08-31")

    def test_future_market_date_moves_only_by_loaner_keep_horizon(self):
        now, future = _market_horizon_dates("2026-03-17", 167, 30)
        self.assertEqual(now, "2026-08-31")
        self.assertEqual(future, "2026-09-30")

    def test_negative_keep_horizon_clamps_to_zero(self):
        now, future = _market_horizon_dates("2026-02-10", 202, -5)
        self.assertEqual(now, future)

    def test_missing_authoritative_clock_fails_closed(self):
        self.assertEqual(_market_horizon_dates(None, 10, 30), (None, None))
        self.assertEqual(_market_horizon_dates("2026-02-10", None, 30), (None, None))


if __name__ == "__main__":
    unittest.main()
