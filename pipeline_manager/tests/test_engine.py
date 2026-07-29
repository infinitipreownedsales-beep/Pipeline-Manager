"""Validation tests — the port must reproduce the source workbook exactly.

The reference JSONs in this folder were extracted from the original
ELITE_PIPELINE_MANAGER workbook (recalculated 2026-07-17):

  engine_ref.json — per-config TOTAL / DTS / HIST60 / R90 / R180 / FLOOR /
                    BASE / MOM / PRATE  (the LIVE ENGINE sheet)
  seas_ref.json   — per-model 12-month seasonality index  (LIVE ENGINE)
  grid_ref.json   — per-config ONLOT / PROJ@ARR / NEED / target  (PLANNING GRID,
                    order month SEP, mode CPO, measured windows QX80/60=5, QX65=1).
                    ONLOT and target remain the workbook's; PROJ@ARR and NEED were
                    RE-BASELINED for the Step 2 two-bucket projection fix — the
                    workbook (and the pre-fix engine) sold committed future
                    pipeline down at retail velocity before it arrived, so it
                    re-ordered units it already had coming. Under the fix, on-lot
                    sells down but committed pipeline is credited in full and never
                    consumed before arrival. The re-baseline is provably monotone:
                    onlot and target are unchanged, and NEED only ever dropped
                    (total 52 -> 33 across the 74 configs) — never rose.

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
                 smooth_base=False, seasonality_shrink_k=0,
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


def test_six_month_plan_targets_match_grid_and_orders_carry_forward():
    res = _run()
    plan = _load("plan_ref.json")
    lines = {l.key: l for l in res.lines}
    # ARRIVALS are unchanged from the workbook grid. (The monthly TARGET now uses
    # a smoothed seasonal curve, so it intentionally differs from the raw grid; it
    # is validated for internal consistency in the rolling-sim reconstruction.)
    for key, months in plan.items():
        got = lines[key].monthly_plan
        for i, exp in enumerate(months):
            assert (got[i]["arr"] or 0) == (exp["arr"] or 0), f"{key} month {i} arr"
    # ORDERS now carry the plan's own prior orders forward and sell down at the
    # config's demand pace (prate/2), so a later month tops up to target instead
    # of re-ordering it whole. Reconstruct that rolling sim and require an exact
    # match (this is the documented, corrected behavior).
    s = res.settings
    ov = {}
    for e in s.overrides:
        ov[e["key"]] = ov.get(e["key"], 0) + int(e.get("qty", 0))
    for l in res.lines:
        m = res.metrics.get(l.key)
        pos = res.positions.get(l.key)
        stalled = pos.stalled if pos else 0
        blocked = l.suppressed or l.eff_demote
        nf = 0 if l.base == 0 else 1
        rate = min(s.rate_cap, m.prate / 2) if m else 0.0
        sm = res.seasonality[l.model]
        pseas = [(sm[(c - 1) % 12] + 2 * sm[c] + sm[(c + 1) % 12]) / 4.0 for c in range(12)]
        onhand = float(l.onlot)
        for k in range(6):
            cal = (s.order_month - 1 + k) % 12
            sk = pseas[cal]
            arr = pos.arrivals.get(cal + 1, 0) if pos else 0
            onhand = max(stalled, onhand - rate * sk) + arr
            tgt = max(nf, xround(l.base * sk))
            assert l.monthly_plan[k]["tgt"] == tgt, f"{l.key} m{k} tgt"
            expected = 0 if blocked else max(0, xround(tgt - onhand))
            if k == 0 and not blocked:
                expected += ov.get(l.key, 0)
            onhand += expected
            assert l.monthly_plan[k]["ord"] == expected, f"{l.key} m{k} ord"
    # The QX65 six-month total must be sane (the double-count bug summed to ~65).
    q65 = sum(p["ord"] for l in res.lines if l.model == "QX65" for p in l.monthly_plan)
    assert q65 < 40, f"QX65 six-month plan still inflated: {q65}"


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


def test_committed_pipeline_is_not_re_ordered():
    """Step 2 / TEST 1: once a recommended unit is committed and appears in the
    inventory feed as pipeline it must reduce need and never be re-ordered — even
    when it arrives AFTER the arrival window. The pre-fix engine sold committed
    pipeline down at retail velocity before it arrived, so it re-recommended the
    same production every cycle."""
    from pipeline_manager.ingest import InventoryUnit, parse_arrival_month
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    s = Settings(order_month=9, mode="CPO", anticipate_demo_returns=False)
    today = datetime.date(2026, 7, 28)
    key = "QX80|8361|XKJ|G"
    model, code, ext, interior = key.split("|")

    def line(res):
        return next(l for l in res.lines if l.key == key)

    rec = line(engine.run(inv, sales, s, today=today)).need
    assert rec > 0
    # Commit the recommended units. They arrive in February — well past the ~2.8mo
    # production->arrival window the need is measured at.
    committed = [InventoryUnit(
        stock=f"CM{i}", serial=f"V{i}", status="", my="2026", model=model,
        model_code=code + "1", description="", trans="", ext=ext, interior=interior,
        msrp=90000, inv_cost=85000, location="SIT", dis=0, eta="2/15/2027",
        production_month="2026-12", key=key,
        arrival_month=parse_arrival_month("SIT", "2/15/2027"), model_year=2026)
        for i in range(rec)]
    after = line(engine.run(list(inv) + committed, sales, s, today=today))
    assert after.inbound >= rec            # committed units are in the feed as pipeline
    assert after.proj_at_arrival >= rec    # pipeline credited into the projection...
    assert after.need == 0                 # ...so the whole batch is satisfied — no re-order


def test_supply_feasibility_does_not_touch_demand():
    """3b: the supply layer (PPO input, cycle position, etc.) never changes need /
    target / any demand number — the shortage is identical with and without it."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    a = engine.run(inv, sales, Settings(order_month=9, mode="CPO"), today=_AS_OF)
    ppo = [{"model": "QX80", "code": "8361", "exterior_color": "XKJ",
            "interior_color": "G", "eta": "september", "source": "other-dealer"}]
    b = engine.run(inv, sales, Settings(order_month=9, mode="CPO", ppo_units=ppo,
                   supply_cycle_position="end"), today=_AS_OF)
    da = {l.key: (l.need, l.order_target, l.proj_at_arrival) for l in a.lines}
    db = {l.key: (l.need, l.order_target, l.proj_at_arrival) for l in b.lines}
    assert da == db


def test_supply_feasibility_reports_workflows_not_a_ranking():
    """3b (feasibility model): each workflow answers only 'can I satisfy this
    shortage — available now, and arriving before/during the demand window?'.
    Workflows are NOT scored or ranked; there is no fit and no 'winner'. Dealer
    Trade is immediate; a late Factory Order is infeasible; CTP closes late in the
    cycle; a PPO landing in the window is feasible."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    key = "QX80|8361|XKJ|G"
    model, code, ext, interior = key.split("|")
    om = 9
    base = engine.run(inv, sales, Settings(order_month=om, mode="CPO",
                      anticipate_demo_returns=False), today=_AS_OF)
    bl = next(l for l in base.lines if l.key == key)
    assert bl.need > 0 and bl.demand_open is not None
    open_off = int(round(bl.demand_open))
    # Here the Factory Order lands after the demand window (demand opens ~OCT, CPO
    # arrives ~NOV) — so it should read INFEASIBLE.
    assert base.arrival_windows["QX80"] > open_off + 1

    def ppo(off):
        month = ((om - 1 + off) % 12) + 1
        return {"model": model, "code": code, "exterior_color": ext,
                "interior_color": interior, "eta": f"{month}/15/2026", "source": "dealer-A"}

    # End of the cycle -> CTP window is closed; a PPO lands in the window.
    s = Settings(order_month=om, mode="CPO", anticipate_demo_returns=False,
                 supply_cycle_position="end", ppo_units=[ppo(open_off)])
    res = engine.run(inv, sales, s, today=_AS_OF)
    row = {r["key"]: r for r in reports.supply_feasibility(res)}[key]
    assert row["cycle_position"] == "end"
    assert "recommended" not in row                           # no winner
    wf = {w["workflow"]: w for w in row["workflows"]}
    assert "fit" not in wf["Factory Order"]                   # no competitive score
    # Dealer Trade — immediate, always feasible.
    assert wf["Dealer Trade"]["feasible"] and wf["Dealer Trade"]["arrival_offset"] == 0.0
    # PPO landing in the window -> feasible.
    assert wf["PPO"]["feasible"] and wf["PPO"]["satisfies_window"]
    # CTP window closed at end of month -> unavailable, infeasible, with a reason.
    assert not wf["CTP"]["available"] and not wf["CTP"]["feasible"]
    assert "closed" in wf["CTP"]["reason"]
    # Factory Order arrives after the window -> infeasible, reason says so.
    assert not wf["Factory Order"]["feasible"] and "after" in wf["Factory Order"]["reason"]
    # The feasible list is the set of feasible workflows — no ranking.
    assert "Dealer Trade" in row["feasible"] and "PPO" in row["feasible"]
    assert "CTP" not in row["feasible"] and "Factory Order" not in row["feasible"]


def test_supply_feasibility_early_arrival_is_feasible_no_aging_penalty():
    """3b: 'before or during the window' is feasible — early arrival is NOT
    penalised (the aging-penalty concept is gone; supply is feasibility, not fit)."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    key = "QX80|8361|XKJ|G"
    model, code, ext, interior = key.split("|")
    om = 9
    base = engine.run(inv, sales, Settings(order_month=om, mode="CPO",
                      anticipate_demo_returns=False), today=_AS_OF)
    bl = next(l for l in base.lines if l.key == key)
    open_off = int(round(bl.demand_open))
    # A PPO arriving at the ORDER month (earliest possible, well before the window).
    ppo = [{"model": model, "code": code, "exterior_color": ext, "interior_color": interior,
            "eta": f"{om}/15/2026", "source": "early-unit"}]
    res = engine.run(inv, sales, Settings(order_month=om, mode="CPO",
                     anticipate_demo_returns=False, ppo_units=ppo), today=_AS_OF)
    row = {r["key"]: r for r in reports.supply_feasibility(res)}[key]
    wf = {w["workflow"]: w for w in row["workflows"]}
    assert wf["PPO"]["arrival_offset"] < open_off      # arrives early
    assert wf["PPO"]["feasible"]                        # still feasible — no aging penalty


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


def test_previous_loaner_subtracts_demo_period_and_never_wholesales():
    """Only the hidden demo period (taken -> returned) is subtracted from
    days-in-stock, and a returned loaner is never wholesale-flagged (miles)."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    today = _AS_OF
    u = next(x for x in inv if x.is_dlr_inv and x.dis > 100)

    def wholesaled(res):
        pos = res.positions.get(u.key)
        return pos is not None and any(x.stock == u.stock for x in pos.wholesale_eligible)

    assert wholesaled(engine.run(inv, sales, Settings(), today=today))   # aged on DMS days
    pl = [{"stock": u.stock, "taken": "2026-04-01", "returned": "2026-05-01",
           "note": "REED / body shop"}]                                  # 30 days out
    r = engine.run(inv, sales, Settings(prev_loaners=pl), today=today)
    rep = reports.previous_loaners(r)
    assert rep and rep[0]["dms_dis"] == int(u.dis)
    assert rep[0]["days_out"] == 30
    assert rep[0]["retail_days"] == int(u.dis) - 30       # market time = DMS - days out
    assert rep[0]["note"] == "REED / body shop"
    assert not wholesaled(r)                              # previous demos never wholesale


def test_suppress_by_code_removes_from_order_priority_only():
    """A bare code suppresses the whole trim from order suggestions (NEED 0, not
    on the priority list), but its on-lot/inbound units still count and it still
    shows in overstock. And roster_add extends the orderable universe."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    r = engine.run(inv, sales, Settings(order_month=9, mode="CPO",
                   suppress=[{"code": "8411"}]), today=_AS_OF)
    eight411 = [l for l in r.lines if l.code == "8411"]
    assert eight411
    assert all(l.need == 0 and l.priority == -1 for l in eight411)   # never suggested
    assert sum(l.onlot for l in eight411) > 0                        # inventory still counts
    over_keys = {(x["ext"], x["int"]) for x in reports.overstock(r)}
    assert any((l.ext, l.interior) in over_keys for l in eight411)   # still in overstock
    # roster_add makes a new combo orderable
    r2 = engine.run(inv, sales, Settings(roster_add=[
        {"model": "QX60", "code": "8411", "ext": "ZZZ", "int": "Q"}]), today=_AS_OF)
    assert any(l.key == "QX60|8411|ZZZ|Q" for l in r2.lines)


def test_loaner_economics_writes_down_cost_and_banks_bonus():
    from pipeline_manager import loaner
    s = Settings(loaner_icv={"QX80": 600, "QX60": 500, "QX65": 500},
                 loaner_depr_pct=1.25, loaner_service_months=3,
                 loaner_velocity_bonus=2500, loaner_recon=0)
    # cost 60,000; MSRP 66,000; used sells in 30 days at 58,000; $3k rebate.
    e = loaner.loaner_economics(60000, 66000, "QX60", 30, 58000, s, rebate=3000)
    assert e["icv_total"] == 500                  # ONE-TIME allowance, not x months
    assert e["depr_total"] == round(60000 * 0.0125 * 3)   # 2,250 off invoice cost (monthly)
    assert e["bonus_ok"] and e["bonus"] == 2500   # 3mo + ~1mo <= 7, miles 3,600 < 10k
    assert e["cheapest_new"] == 57000             # invoice 60k - rebate 3k
    assert e["adjusted_cost"] == 60000 - 500 - 2250 - 2500
    assert e["used_gross"] == 58000 - e["adjusted_cost"]   # preowned gross


def test_loaner_modeled_used_price_is_80pct_of_cheapest_new_and_flags_upside_down():
    from pipeline_manager import loaner
    # Modeled QX80: invoice ~110k, $10k rebate -> cheapest-new 100k, used ~80k.
    # Write-downs (a few k) can't cover the ~30k drop, so it is upside down.
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    res = engine.run(inv, sales, Settings(
        loaner_icv={"QX80": 650, "QX60": 500, "QX65": 500},
        rebates={"QX80": 10000, "QX60": 0, "QX65": 0}), today=_AS_OF)
    q80 = res.loaner_board if False else reports.loaner_board(res)["QX80"]
    assert q80, "expected QX80 candidates"
    for p in q80:
        e = p["econ"]
        # used price modeled at 80% of (invoice - rebate)
        assert abs(e["used_price"] - 0.80 * e["cheapest_new"]) <= 1
        assert e["cheapest_new"] == e["cost"] - 10000
        # deeply discounted new -> conservative used floor -> upside down here
        assert e["upside_down"] and p["net_value"] < 0


def test_loaner_bonus_forfeited_when_used_turn_blows_the_window():
    from pipeline_manager import loaner
    s = Settings(loaner_max_months=7, loaner_service_months=3)
    # A 5-month used turn: 3 + ~5 = 8 months > 7 -> bonus lost.
    slow = loaner.loaner_economics(60000, 66000, "QX60", 150, 58000, s)
    assert not slow["bonus_ok"] and slow["bonus"] == 0
    fast = loaner.loaner_economics(60000, 66000, "QX60", 20, 58000, s)
    assert fast["bonus_ok"] and fast["used_gross"] > slow["used_gross"]


def test_loaner_depr_base_msrp_uses_window_sticker():
    from pipeline_manager import loaner
    s = Settings(loaner_depr_base="msrp", loaner_depr_pct=1.25, loaner_service_months=4)
    e = loaner.loaner_economics(60000, 80000, "QX80", 30, 70000, s)
    assert e["depr_total"] == round(80000 * 0.0125 * 4)   # off MSRP, not cost


def test_in_service_loaners_leave_sellable_inventory():
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    onlot = [u for u in inv if u.is_dlr_inv]
    victim = onlot[0]
    base = engine.run(inv, sales, Settings(), today=_AS_OF)
    with_loaner = engine.run(inv, sales, Settings(
        loaner_units=[{"stock": victim.stock, "start": "2026-04-01"}]), today=_AS_OF)
    assert with_loaner.positions[victim.key].onlot == base.positions[victim.key].onlot - 1


def test_loaner_board_ranks_by_used_gross_and_flags_bonus():
    res = engine.run(
        load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv")),
        load_sales(os.path.join(_PKG, "sample_data", "sales.csv")),
        Settings(loaner_icv={"QX80": 600, "QX60": 500, "QX65": 500}), today=_AS_OF)
    board = reports.loaner_board(res)
    assert set(board) == {"QX80", "QX60", "QX65"}
    for picks in board.values():
        # in-stock candidates first (you can designate them today), then by score
        assert picks == sorted(picks, key=lambda p: (0 if p["in_stock"] else 1, -p["score"]))
        for p in picks:
            assert "used_gross" in p["econ"] and "bonus_ok" in p["econ"]


def test_measured_preowned_overrides_modeled():
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    modeled = engine.run(inv, sales, Settings(), today=_AS_OF)
    measured = engine.run(inv, sales, Settings(preowned_sales=[
        {"model": "QX60", "code": "8411", "days": 12, "price": 48000},
        {"model": "QX60", "code": "8411", "days": 18, "price": 47000},
    ]), today=_AS_OF)
    assert modeled.preowned["QX60|8411"].modeled is True
    st = measured.preowned["QX60|8411"]
    assert st.modeled is False and st.count == 2 and st.used_dts == 15.0


def test_build_sequence_is_retail_only_and_ignores_loaner_fleet():
    """Step 1 boundary: loaner / preowned economics must NOT influence factory
    ordering. The retail build sequence is driven by retail NEED alone, uses the
    FULL allocation, and never reserves slots for the loaner fleet — so turning the
    loaner program on must leave the build sequence byte-identical."""
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    alloc = {"QX80": 50, "QX60": 100, "QX65": 100}
    # Loaner program ACTIVE (ICV set, fleet target) — historically this reserved
    # allocation out of the build sequence. It must no longer do so.
    s_on = Settings(order_month=9, loaner_fleet_target=20, loaner_service_months=4,
                    loaner_icv={"QX80": 650, "QX60": 500, "QX65": 500}, allocations=alloc)
    s_off = Settings(order_month=9, allocations=alloc)
    bs_on = reports.build_sequence(engine.run(inv, sales, s_on, today=_AS_OF))
    bs_off = reports.build_sequence(engine.run(inv, sales, s_off, today=_AS_OF))
    # No loaner/fleet keys leak into the ordering output at all.
    assert "fleet_units" not in bs_on and "intake" not in bs_on
    for model, d in bs_on["per_model"].items():
        assert all(g["stream"] == "retail" for g in d["groups"])   # retail only
        assert d["eff_alloc"] == d["allocation"]                   # full allocation, no reservation
        assert "fleet_reserved" not in d                           # reservation concept removed
        build = sum(g["qty"] for g in d["groups"] if g["tier"] == "build")
        assert build <= d["allocation"]
    # The decisive Step-1 guarantee: activating the loaner program does not change
    # a single unit of the factory order.
    assert bs_on["per_model"] == bs_off["per_model"]
    # decay 0 keeps a combo's units contiguous (whole combo before the next)
    s0 = Settings(order_month=9, order_unit_decay=0.0)
    g0 = reports.build_sequence(engine.run(inv, sales, s0, today=_AS_OF))["per_model"]["QX80"]["groups"]
    keys = [g["key"] for g in g0]
    assert len(keys) == len(set(keys))            # no combo appears in two separate runs


def test_sales_loader_accepts_real_export_column_names():
    # Real Speed-to-Sell exports label these EXTERIOR/INTERIOR CODE and Stock
    # Number (not EXT/INT CODE / Stock#). If unrecognized, ext/int parse blank,
    # no sale matches a config, and every config looks dormant -> NEED 0 forever
    # (the QX65 bug). The loader must accept both namings.
    import tempfile
    from pipeline_manager.ingest import load_sales
    csv = ("Sales Month,Stock Number,Model,VIN,DAYS TO SELL,MODEL CODE,EXTERIOR CODE,INTERIOR CODE\n"
           "202607,N15550,QX65 SPORT AWD,VIN0001,7,85117,XEX,G\n"
           "202607,N15551,QX65 AUTOG AWD,VIN0002,12,85217,XKJ,K\n")
    p = os.path.join(tempfile.mkdtemp(), "s.csv")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(csv)
    sales = load_sales(p)
    assert len(sales) == 2
    s0 = sales[0]
    assert s0.ext == "XEX" and s0.interior == "G" and s0.stock == "N15550"
    assert s0.key == "QX65|8511|XEX|G"    # 5-digit code -> 4-digit, keyed with ext/int
    assert sales[1].key == "QX65|8521|XKJ|K"


def test_retail_forecast_is_inventory_constrained():
    inv = load_inventory(os.path.join(_PKG, "sample_data", "inventory.csv"))
    sales = load_sales(os.path.join(_PKG, "sample_data", "sales.csv"))
    res = engine.run(inv, sales, Settings(order_month=9), today=_AS_OF)
    f = reports.retail_forecast(res)
    assert [h["days"] for h in f["horizons"]][1:] == [30, 60]
    for model, d in f["per_model"].items():
        assert len(d["forecast"]) == 3
        # forward windows are non-decreasing (longer window -> more retail)
        assert d["forecast"][1] <= d["forecast"][2]
        # "This month" is a full-month total: at least what's already retailed
        # this calendar month (it may exceed the forward-only 30-day window)
        assert d["forecast"][0] >= d["sold_mtd"]
        # inventory-constrained: 60-day retail never exceeds what you can hold
        assert d["forecast"][2] <= d["avail60"] + 1
        # never forecasts more than the market demands
        assert d["forecast"][2] <= d["demand"][2] + 1
        assert d["health"] in ("balanced", "tight — demand outruns stock",
                               "heavy — stock outruns demand", "cold — little live demand")
    # month-to-date total is the sum across models
    assert f["total"]["sold_mtd"] == sum(d["sold_mtd"] for d in f["per_model"].values())
    # total is the sum across models
    assert f["total"]["forecast"][2] == sum(d["forecast"][2] for d in f["per_model"].values()) \
        or abs(f["total"]["forecast"][2] - sum(d["forecast"][2] for d in f["per_model"].values())) <= 2


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
