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
    s = Settings(order_month=9, mode="CPO",
                 cpo_windows={"QX80": 5, "QX60": 5, "QX65": 1}, **kw)
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
