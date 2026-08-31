import unittest

from elite.loaner.preowned_evidence import summarize_model_sales, summarize_model_year_sales
from elite.loaner.sell_time import estimate_sell_time
from elite.loaner.intelligence import _cohort, _maturity


class TestServiceLoanerUsedEvidenceSplit(unittest.TestCase):
    def test_preowned_summaries_exclude_explicit_new(self):
        rows = [
            {"model": "QX60", "year": 2027, "days_to_sell": 5, "_sale_kind": "NEW"},
            {"model": "QX60", "year": 2027, "days_to_sell": 7, "_sale_kind": "NEW"},
            {"model": "QX60", "year": 2026, "days_to_sell": 30, "_sale_kind": "USED"},
            {"model": "QX60", "year": 2026, "days_to_sell": 40, "_sale_kind": "USED"},
        ]
        model = summarize_model_sales(rows, {"QX60": 1})[0]
        self.assertEqual(model.sales_count, 2)
        self.assertEqual(model.numeric_dts_count, 2)
        self.assertEqual(model.median_dts, 35.0)

        years = summarize_model_year_sales(rows, {"QX60": 1}, min_sample=1)
        self.assertEqual([(x.year, x.sales_count) for x in years], [(2026, 2)])

    def test_legacy_unflagged_row_remains_eligible(self):
        model = summarize_model_sales(
            [{"model": "QX60", "year": 2026, "days_to_sell": 22}],
            {"QX60": 1},
        )[0]
        self.assertEqual(model.sales_count, 1)

    def test_sell_time_never_uses_new_delivery_dts(self):
        rows = [
            *[{"model": "QX60", "year": 2027, "days_to_sell": 5, "_sale_kind": "NEW"} for _ in range(10)],
            *[{"model": "QX60", "year": 2026, "days_to_sell": 40, "_sale_kind": "USED"} for _ in range(6)],
        ]
        got = estimate_sell_time(rows, model="QX60", model_year="2027")
        self.assertEqual(got["days"], 40.0)
        self.assertEqual(got["n"], 6)
        self.assertEqual(got["basis"], "model")

    def test_resale_cohort_excludes_new(self):
        rows = [
            {"price": 100.0, "sold_date": "2026-08-01", "_sale_kind": "NEW"},
            {"price": 50.0, "sold_date": "2026-08-02", "_sale_kind": "USED"},
        ]
        c = _cohort("resale", "QX60", rows, lambda r: r.get("price"), 1, "2026-08-31")
        self.assertEqual(c.dist.count, 1)
        self.assertEqual(c.dist.median, 50.0)

    def test_maturity_excludes_new_price(self):
        rows = [
            {"price": 100.0, "sold_date": "2027-05-01", "year": 2027, "_sale_kind": "NEW"},
            {"price": 50.0, "sold_date": "2026-05-01", "year": 2026, "_sale_kind": "USED"},
        ]
        bins, excluded = _maturity(rows)
        self.assertEqual(excluded, 0)
        self.assertEqual(len(bins), 1)
        self.assertEqual(bins[0].label, "0")
        self.assertEqual(bins[0].n, 1)
        self.assertEqual(bins[0].median_price, 50.0)


if __name__ == "__main__":
    unittest.main()
