"""Validation tests — the port must reproduce the source workbook exactly.

The reference JSONs in this folder were extracted from the original
ELITE_PIPELINE_MANAGER workbook (recalculated 2026-07-17):

  engine_ref.json — per-config TOTAL / DTS / HIST60 / R90 / R180 / FLOOR /
                    BASE / MOM / PRATE  (the LIVE ENGINE sheet)
  seas_ref.json   — per-model 12-month seasonality index  (LIVE ENGINE)
  grid_ref.json   — per-config ONLOT / PROJ@ARR / NEED / target  (PLANNING GRID,
                    order month SEP, mode CPO, measured windows QX80/60=5, QX65=1)

Run with `pytest` or directly: `python pipeline_manager/tests/test_engine.py`.
"""

from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline_manager import Settings, engine, reports
from pipeline_manager.ingest import load_inventory, load_sales
from pipeline_manager.keys import build_key, xround

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_AS_OF = datetime.date(2026, 7, 17)   # the workbook's recalculation date


def _load(fname):
    return json.load(open(os.path.join(_HERE, fname), encoding="utf-8"))


def _run(**kw):
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    # Pinned windows, demo-return modeling OFF, and the legacy rounded floor
    # reproduce the source workbook. All three are validated against the workbook
    # cell-for-cell; the data-driven window, demo-return anticipation, and the
    # continuous smooth base are newer layers with their own tests.
    s = Settings(order_month=9, mode="CPO", anticipate_demo_returns=False,
                 smooth_base=False, cpo_windows={"QX80": 5, "QX60": 5, "QX65": 1}, **kw)
    return engine.run(inv, sales, s, today=_AS_OF)


# --------------------------------------------------------------------------- #
# Key normalisation (brief §3, §17, §18)
# --------------------------------------------------------------------------- #
def test_key_normalisation():
    # 5-digit inventory code drops the model-year digit.
    assert build_key("QX80", "83116", "QBE", "C") == "QX80|8311|QBE|C"
    # QX80 Sport 834x consolidates to 8381, interior G/D -> D.
    assert build_key("QX80", "83416", "GAT", "G") == "QX80|8381|GAT|D"
    assert build_key("QX80", "8341", "QBE", "D") == "QX80|8381|QBE|D"
    # QX60 8461 folds into 8481.
    assert build_key("QX60", "84616", "GAQ", "K") == "QX60|8481|GAQ|K"


def test_excel_rounding():
    # Round half away from zero (Excel ROUND), not banker's rounding.
    assert xround(6.5) == 7 and xround(200.5) == 201 and xround(-2.5) == -3
    assert xround(14.5) == 15 and xround(96.5) == 97
    assert xround(0.125, 2) == 0.13     # 1/8 is float-exact -> 12.5 -> 13


# --------------------------------------------------------------------------- #
# Engine metrics (LIVE ENGINE)
# --------------------------------------------------------------------------- #
def test_engine_metrics_match_workbook():
    res = _run()
    ref = _load("engine_ref.json")
    checked = 0
    for key, rv in ref.items():
        if (rv["TOTAL"] or 0) == 0:
            continue                      # zero-sales combos verified separately
        m = res.metrics.get(key)
        assert m is not None, f"missing learned config {key}"
        checked += 1
        assert m.total == rv["TOTAL"], key
        assert m.r90 == (rv["R90"] or 0), key
        assert m.r180 == (rv["R180"] or 0), key
        assert m.floor == (rv["FLOOR"] or 0), key
        assert m.base == (rv["BASE"] or 0), key
        assert m.momentum == rv["MOM"], key
        exp_dts = None if rv["DTS"] in (None, "") else float(rv["DTS"])
        got_dts = None if m.dts is None else float(m.dts)
        assert exp_dts == got_dts, f"{key} DTS {got_dts} != {exp_dts}"
        assert abs(m.hist60 - (rv["HIST60"] or 0)) <= 0.011, key
        assert abs(m.prate - (rv["PRATE"] or 0)) <= 0.011, key
    assert checked >= 100


def test_zero_sales_roster_is_found_not_new():
    """A roster combo with no sales must resolve base 0 (dormant, found), NOT
    base 1 (new/not-found) — else it phantom-orders (brief §13, §20)."""
    res = _run()
    checked = 0
    for l in res.lines:
        m = res.metrics.get(l.key)
        if m is None or m.total != 0:
            continue                       # only zero-sales roster combos
        checked += 1
        base, found = engine._base_for_order(l.key, res.metrics)
        assert found is True, f"{l.key} should be seeded as found"
        assert base == 0, f"{l.key} base should be 0, got {base}"
    assert checked >= 10                    # there really are dormant combos


def test_genuinely_new_combo_is_base_one():
    """A key the engine has never seen (not roster, not sales) -> base 1."""
    res = _run()
    base, found = engine._base_for_order("QX80|8311|ZZZ|Q", res.metrics)
    assert found is False and base == 1


# --------------------------------------------------------------------------- #
# Seasonality (LIVE ENGINE)
# --------------------------------------------------------------------------- #
def test_seasonality_match_workbook():
    res = _run()
    ref = _load("seas_ref.json")
    for model, arr in ref.items():
        for i, exp in enumerate(arr):
            assert abs(res.seasonality[model][i] - exp) <= 0.001, (model, i)


# --------------------------------------------------------------------------- #
# Order math (PLANNING GRID)
# --------------------------------------------------------------------------- #
def test_projection_need_target_match_grid():
    res = _run()
    grid = _load("grid_ref.json")
    lines = {l.key: l for l in res.lines}
    for key, g in grid.items():
        l = lines[key]
        assert l.onlot == (g["onlot"] or 0), f"{key} onlot"
        assert abs(l.proj_at_arrival - (g["proj"] or 0)) <= 0.15, f"{key} proj"
        assert l.need == (g["need"] or 0), f"{key} need"
        assert l.overstock_target == (g["tgt_m"] or 0), f"{key} target"


def test_six_month_plan_matches_grid():
    res = _run()
    plan = _load("plan_ref.json")
    lines = {l.key: l for l in res.lines}
    for key, months in plan.items():
        got = lines[key].monthly_plan
        for i, exp in enumerate(months):
            for f in ("tgt", "arr", "ord"):
                assert (got[i][f] or 0) == (exp[f] or 0), f"{key} month {i} {f}"


def test_order_priority_ranking_matches_workbook():
    res = _run()
    op = reports.order_priority(res)
    ref = _load("op_ref.json")
    for model in ("QX80", "QX60", "QX65"):
        mine, exp = op[model]["rows"], ref[model]
        assert len(mine) == len(exp), model
        for mr, er in zip(mine, exp):
            assert (mr["trim"], mr["ext"], mr["int"], mr["need"], mr["tier"]) == \
                   (er["trim"], er["ext"], er["int"], er["need"], er["tier"]), (model, mr["rank"])


# --------------------------------------------------------------------------- #
# The headline requirement: determinism
# --------------------------------------------------------------------------- #
def test_auto_window_is_data_driven_and_continuous():
    """Auto windows come from real production->arrival leads, are continuous
    (fractional), and — by not snapping arrival onto a peak month — pull the
    QX80 build well below the fixed-3-month result."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    auto = engine.run(inv, sales, Settings(order_month=9, mode="CPO"), today=_AS_OF)
    assert auto.settings.cpo_windows["QX80"] == "auto"        # default is auto
    w = auto.arrival_windows
    assert 1.5 < w["QX80"] < 3.0 and abs(w["QX80"] - round(w["QX80"])) > 0.05  # fractional
    fixed3 = engine.run(inv, sales, Settings(order_month=9, mode="CPO",
                        cpo_windows={"QX80": 3, "QX60": 2, "QX65": 2}), today=_AS_OF)
    auto80 = sum(l.need for l in auto.lines if l.model == "QX80")
    fixed80 = sum(l.need for l in fixed3.lines if l.model == "QX80")
    assert auto80 < fixed80        # continuous window doesn't over-order at the Dec peak


def test_projection_credits_residual_inbound():
    """Configs with inbound units must project residual on-hand at arrival, not
    assume a total sell-out (the 'we'll still have one or two' case)."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    res = engine.run(inv, sales, Settings(order_month=9, mode="CPO"), today=_AS_OF)
    line = next(l for l in res.lines if l.key == "QX80|8361|XKJ|G")  # 1 lot + 2 inbound
    assert line.inbound == 2 and line.proj_at_arrival > 0


def test_executive_demo_board():
    """Demo picks must be proven fast movers (never one-off whims), ranked, with
    a VIN where one is in stock, across all three models."""
    res = _run()
    ed = reports.executive_demos(res)
    s = res.settings
    for model in ("QX80", "QX60", "QX65"):
        picks = ed[model]
        assert picks, f"{model} should surface at least one demo pick"
        assert len(picks) <= s.demo_picks_per_model
        scores = [p["score"] for p in picks]
        assert scores == sorted(scores, reverse=True)          # ranked
        for p in picks:
            assert p["dts"] <= s.demo_pick_max_dts              # fast resale
            assert p["total"] >= s.demo_pick_min_total          # not a one-off
            assert p["r180"] >= s.demo_pick_min_r180            # repeat demand
            assert p["momentum"] != "dormant"
            if p["in_stock"]:
                assert p["units"] and p["units"][0]["vin"]      # VIN-led
    # A single-lifetime-sale config (a "whim") must never appear.
    all_keys = {p["key"] for m in ed.values() for p in m}
    assert "QX65|8511|GAT|G" not in all_keys   # 1 sold, DTS 10 — fast but unproven


def test_demo_return_is_anticipated_and_held():
    """A config with an out demo must project that unit coming back (so ordering
    doesn't over-replace it) and hold it as slow-moving stock — lowering NEED vs
    treating the demo as gone forever."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    key = "QX80|8361|GAT|A"                       # has an active demo (N15126)
    on = engine.run(inv, sales, Settings(order_month=9, mode="CPO",
                    anticipate_demo_returns=True), today=_AS_OF)
    off = engine.run(inv, sales, Settings(order_month=9, mode="CPO",
                     anticipate_demo_returns=False), today=_AS_OF)
    lon = next(l for l in on.lines if l.key == key)
    loff = next(l for l in off.lines if l.key == key)
    assert lon.demo_returning >= 1
    assert lon.proj_at_arrival > loff.proj_at_arrival    # the returning unit shows up
    assert lon.need <= loff.need                         # so we don't over-order


def test_outbound_trades_grade_velocity():
    """A dealer trade out grades that config like a sale: it counts toward
    volume and recency, and its days-in-stock moves DTS — fast trades faster,
    slow trades slower."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    key = "QX80|8311|KH3|G"

    def dts_total(trades):
        r = engine.run(inv, sales, Settings(order_month=9, mode="CPO", trades=trades),
                       today=_AS_OF)
        m = r.metrics[key]
        return m.dts, m.total, m.r90

    base_dts, base_total, base_r90 = dts_total([])
    fast_dts, fast_total, fast_r90 = dts_total(
        [{"date": "2026-07", "model": "QX80", "code": "8311", "ext": "KH3", "int": "G", "days": 15}])
    slow_dts, _, _ = dts_total(
        [{"date": "2026-07", "model": "QX80", "code": "8311", "ext": "KH3", "int": "G", "days": 115}])
    assert fast_total == base_total + 1 and fast_r90 == base_r90 + 1
    assert fast_dts < base_dts < slow_dts        # 15-day speeds it up, 115-day slows it


def test_smooth_base_is_stable_across_the_month():
    """The continuous base must not flip day-to-day on a rounding boundary the way
    the legacy rounded floor does (the QBE/C 2<->3 wobble)."""
    import datetime as _d
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    key = "QX80|8311|QBE|C"
    smooth, legacy = [], []
    for day in (1, 8, 15, 22, 28):
        d = _d.date(2026, 7, day)
        smooth.append(engine.run(inv, sales, Settings(order_month=9, mode="CPO",
                      smooth_base=True), today=d).metrics[key].base)
        legacy.append(engine.run(inv, sales, Settings(order_month=9, mode="CPO",
                      smooth_base=False), today=d).metrics[key].base)
    assert max(legacy) - min(legacy) >= 1        # legacy visibly flips (2<->3)
    assert max(smooth) - min(smooth) < 1         # smooth base drifts, never flips a whole unit


def test_previous_loaner_uses_retail_clock():
    """A returned loaner's aging runs from re-entry (its real time on the public
    market), not the inflated DMS days-in-stock — so it isn't wrongly wholesaled
    the moment it reappears."""
    import datetime as _d
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    today = _AS_OF
    u = next(x for x in inv if x.is_dlr_inv and x.dis > 100)

    def wholesaled(res):
        pos = res.positions.get(u.key)
        return pos is not None and any(x.stock == u.stock for x in pos.wholesale_eligible)

    assert wholesaled(engine.run(inv, sales, Settings(), today=today))   # aged on DMS days
    pl = [{"stock": u.stock, "since": (today - _d.timedelta(days=8)).isoformat()}]
    r = engine.run(inv, sales, Settings(prev_loaners=pl), today=today)
    assert not wholesaled(r)                       # 8 real market days -> not aged
    rep = reports.previous_loaners(r)
    assert rep and rep[0]["retail_days"] == 8 and rep[0]["dms_dis"] == int(u.dis)


def test_recompute_is_deterministic():
    a = reports.build_all(_run())
    b = reports.build_all(_run())
    assert json.dumps(a, default=str, sort_keys=True) == \
           json.dumps(b, default=str, sort_keys=True)


def test_hardcoded_rules():
    res = _run()
    lines = {l.key: l for l in res.lines}
    # 8461 is always suppressed (NEED 0).
    for l in res.lines:
        if l.code == "8461":
            assert l.suppressed and l.need == 0
    # Loaner hardcode: QX60 Pure FWD QBE/K carries +8.
    assert lines["QX60|8411|QBE|K"].need >= 8
    # INT=N is demoted (ranked last / NEED 0 unless it proves through).
    n_lines = [l for l in res.lines if l.interior == "N"]
    assert n_lines and all(l.demoted for l in n_lines)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
