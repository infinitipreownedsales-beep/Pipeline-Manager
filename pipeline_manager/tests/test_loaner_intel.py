"""Tests for the Loaner Intelligence engine, pinned to the real 10-year export."""
import datetime as _dt
import os

from pipeline_manager import loaner_intel as li

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSV = os.path.join(_PKG, "sample_data", "loaner_history.csv")
_TEXT = open(_CSV, encoding="utf-8-sig").read()


def _load():
    return li.load_csv(_TEXT)


def test_parses_and_flags_infiniti_and_loaners():
    sales = _load()
    assert len(sales) > 15000
    inf = [s for s in sales if s.is_infiniti]
    assert len(inf) > 2000
    loaners = [s for s in inf if s.is_loaner]
    # LP/LNP cohort is real and sizeable
    assert 200 < len(loaners) < 500


def test_loaner_stock_and_vin_priority():
    # a bare LP stock is a loaner; a lineage suffix (LP1234A) still is; VIN
    # continuity promotes any row sharing a loaner VIN.
    assert li._is_loaner_stock("LP21560")
    assert li._is_loaner_stock("LNP21560")
    assert li._is_loaner_stock("LP21560A")
    assert li._is_loaner_stock("LP21560B")
    assert not li._is_loaner_stock("N15106")
    assert not li._is_loaner_stock("P10408")   # P-prefix is not LP/LNP
    assert li._strip_suffix("LP21560A") == "LP21560"


def test_color_canonicalization_merges_abbreviations():
    assert li._canon_color("wht") == "WHITE"
    assert li._canon_color("BLK") == "BLACK"
    # multi-word real colors are left intact
    assert li._canon_color("Glacier White") == "GLACIER WHITE"


def test_age_curve_is_monotone_after_smoothing():
    a = li.analyze(_load(), half_life_months=24)
    curve = a["age_curves"]["QX60"]["points"]
    smooth = [p["price_smooth"] for p in curve if p["price_smooth"] is not None]
    # smoothed price never rises with age
    assert all(smooth[i] >= smooth[i + 1] for i in range(len(smooth) - 1))
    # retention starts at 1.0 and ends well below (real depreciation)
    assert curve[0]["retention_smooth"] == 1.0
    assert curve[-1]["retention_smooth"] < 0.6


def test_loaner_vs_retail_has_both_cohorts():
    a = li.analyze(_load(), half_life_months=24)
    lv = a["loaner_vs_retail"]
    assert lv["overall"]["loaner"]["n"] > 150
    assert lv["overall"]["retail"]["n"] > 1000
    # loaners come out of service young; ordinary used stock is older
    assert lv["overall"]["loaner"]["avg_age_mo"] <= lv["overall"]["retail"]["avg_age_mo"]
    # QX60 is the dominant loaner model -> present in the per-model split
    assert "QX60" in lv["per_model"]


def test_seasonality_covers_twelve_months_with_indices():
    a = li.analyze(_load(), half_life_months=24)
    months = a["seasonality"]["months"]
    assert len(months) == 12
    idx = [m["price_index"] for m in months if m["price_index"]]
    assert idx and all(0.5 < v < 1.6 for v in idx)


def test_recency_weighting_shifts_estimates():
    sales = _load()
    a_recent = li.analyze(sales, half_life_months=6)     # heavy recency
    a_flat = li.analyze(sales, half_life_months=100000)   # ~equal weight
    # weights actually differ -> at least one model's median price moves
    p_recent = {k: v["points"][0]["price"] for k, v in a_recent["age_curves"].items()}
    p_flat = {k: v["points"][0]["price"] for k, v in a_flat["age_curves"].items()}
    assert any(p_recent.get(k) != p_flat.get(k) for k in p_recent)


def test_predictor_is_monotone_in_age_and_reports_confidence():
    a = li.analyze(_load(), half_life_months=24)
    pred = a["_predictor"]
    prices = []
    for age in (0, 12, 24, 36, 48, 60):
        r = pred("QX60", "LUXE", None, "WHITE", 6, age_months=age)
        assert r["ok"] and 0.0 <= r["confidence"] <= 1.0
        assert r["price_low"] <= r["price"] <= r["price_high"]
        prices.append(r["price"])
    assert all(prices[i] >= prices[i + 1] for i in range(len(prices) - 1))
    # unknown model degrades gracefully
    assert pred("DELOREAN", "DMC12", 1985, "STAINLESS", 6, age_months=6)["ok"] is False


def test_predictor_resale_feeds_loaner_economics():
    # The Pipeline Manager tool prices a loaner candidate's resale from this
    # predictor at ~service-age. Pin the model-level values the JS economics
    # consume so the JS<->Python bridge can't drift silently.
    a = li.analyze(_load(), half_life_months=24)
    pred = a["_predictor"]
    qx80 = pred("QX80", None, None, None, None, age_months=3)
    qx60 = pred("QX60", None, None, None, None, age_months=3)
    assert qx80["ok"] and qx80["price"] == 69000 and qx80["n"] == 54
    assert qx60["ok"] and qx60["price"] == 41300 and qx60["n"] == 262
    # a nameplate with no history (QX65 is new) has no curve -> economics fall
    # back to the modeled floor
    assert pred("QX65", None, None, None, None, age_months=3)["ok"] is False


def test_model_performance_ranks_and_benchmarks():
    a = li.analyze(_load(), half_life_months=24)
    mp = a["model_perf"]
    assert mp["store"]["gross"] is not None
    models = {m["model"]: m for m in mp["models"]}
    assert "QX60" in models and "QX80" in models
    # every model row carries a store-relative gross delta
    assert all("gross_vs_store" in m for m in mp["models"])


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("PASS ", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", repr(e))
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
