"""Learned post-loaner sell-time + release backsolve (Stage 6/7 adversarial): most-specific reliable cohort,
graceful degradation when sparse, no fabricated precision; release backsolves from the final-sale deadline
measured on the actual in-service date."""
import unittest

from elite.loaner.sell_time import estimate_sell_time, latest_prudent_release, release_signal, MIN_SAMPLE


def _sale(model, year, trim, dts, dr="AWD"):
    return {"model": model, "year": str(year), "trim": trim, "drivetrain": dr, "days_to_sell": dts}


class TestSellTime(unittest.TestCase):
    def test_uses_most_specific_defensible_cohort(self):
        rows = [_sale("QX60", 2024, "LUXE", 30) for _ in range(MIN_SAMPLE)]           # specific cohort
        rows += [_sale("QX60", 2023, "PURE", 90) for _ in range(MIN_SAMPLE)]           # noise at model level
        est = estimate_sell_time(rows, model="QX60", model_year="2024", trim="LUXE", drivetrain="AWD")
        self.assertEqual(est["basis"], "model+MY+trim+drivetrain")
        self.assertEqual(est["days"], 30)
        self.assertIn(est["confidence"], ("strong", "moderate"))

    def test_degrades_to_model_when_specific_is_thin(self):
        rows = [_sale("QX60", 2024, "LUXE", 30)]                                        # only 1 specific
        rows += [_sale("QX60", 2022, "PURE", 60) for _ in range(MIN_SAMPLE)]            # model cohort defensible
        est = estimate_sell_time(rows, model="QX60", model_year="2024", trim="LUXE")
        self.assertEqual(est["basis"], "model")                                        # broadened intelligently
        self.assertGreaterEqual(est["n"], MIN_SAMPLE)

    def test_sparse_returns_thin_not_none(self):
        rows = [_sale("QX60", 2024, "LUXE", 40)]                                        # single sale total
        est = estimate_sell_time(rows, model="QX60", model_year="2024", trim="LUXE")
        self.assertIsNotNone(est)                                                       # best available, not blocked
        self.assertEqual(est["confidence"], "thin")                                     # honest low confidence
        self.assertEqual(est["days"], 40)

    def test_no_model_history_is_none(self):
        rows = [_sale("QX80", 2024, "SPORT", 50) for _ in range(MIN_SAMPLE)]
        self.assertIsNone(estimate_sell_time(rows, model="QX60"))                       # no QX60 history at all

    def test_missing_fields_degrade_gracefully(self):
        rows = [_sale("QX60", 2024, "LUXE", 45) for _ in range(MIN_SAMPLE)]
        # target has no trim/drivetrain -> skips those levels, still resolves at model+MY
        est = estimate_sell_time(rows, model="QX60", model_year="2024")
        self.assertEqual(est["basis"], "model+MY")


class TestReleaseBacksolve(unittest.TestCase):
    def test_backsolve_from_deadline(self):
        r = latest_prudent_release(in_service_date="2026-02-10", total_to_retail_days=240,
                                   expected_sell_time_days=45, process_buffer_days=20)
        self.assertEqual(r["deadline"], "2026-10-08")          # 2026-02-10 + 240d
        self.assertEqual(r["release_by"], "2026-08-04")        # deadline − 45 − 20 = 65 days earlier

    def test_missing_input_fails_closed(self):
        self.assertIsNone(latest_prudent_release(in_service_date=None, total_to_retail_days=240,
                                                 expected_sell_time_days=45, process_buffer_days=20))
        self.assertIsNone(latest_prudent_release(in_service_date="2026-02-10", total_to_retail_days=240,
                                                 expected_sell_time_days=None, process_buffer_days=20))

    def test_longer_selltime_or_buffer_pulls_release_earlier(self):
        base = latest_prudent_release(in_service_date="2026-02-10", total_to_retail_days=240,
                                      expected_sell_time_days=45, process_buffer_days=20)["release_by"]
        longer = latest_prudent_release(in_service_date="2026-02-10", total_to_retail_days=240,
                                        expected_sell_time_days=60, process_buffer_days=20)["release_by"]
        self.assertLess(longer, base)                          # more sell time -> release sooner


class TestReleaseSignal(unittest.TestCase):
    def test_keep_runway(self):
        self.assertEqual(release_signal("2026-05-01", "2026-08-04")["signal"], "KEEP_RUNWAY")

    def test_release_due_within_window(self):
        r = release_signal("2026-07-25", "2026-08-04")
        self.assertEqual(r["signal"], "RELEASE_DUE")
        self.assertEqual(r["days_to_release"], 10)

    def test_release_overdue(self):
        self.assertEqual(release_signal("2026-09-01", "2026-08-04")["signal"], "RELEASE_OVERDUE")

    def test_unknown_when_no_release(self):
        self.assertEqual(release_signal("2026-05-01", None)["signal"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
