"""Turn an EngineResult into the five clean output tables (brief §19).

    1. Order Priority       — ranked BUILD / alt / option worklist, NEED per config.
    2. Overstock / Wholesale — over-target configs, wholesale-now counts, aged flags.
    3. Wholesale VIN sheet   — printable, VIN-led list of aged eligible units.
    4. Demo Dashboard        — suppressed units, ages, swap flags.
    5. Pace Check            — actual vs predicted 60-day pace per model, with a read.

Each builder returns plain dicts/lists so the same data can be rendered as text,
markdown, CSV or JSON without recomputation.
"""

from __future__ import annotations

from .engine import EngineResult
from .keys import xround

MODELS = ("QX80", "QX60", "QX65")


# --------------------------------------------------------------------------- #
# 1. Order Priority
# --------------------------------------------------------------------------- #
def order_priority(res: EngineResult) -> dict:
    s = res.settings
    out = {}
    for model in MODELS:
        ranked = sorted(
            [l for l in res.lines if l.model == model and l.priority > -1],
            key=lambda l: -l.priority,
        )
        alloc = s.allocations.get(model, 0)
        cumulative = 0
        rows = []
        for i, l in enumerate(ranked, 1):
            cumulative += l.need
            if l.need == 0:
                tier = "○ option"
            elif cumulative <= alloc:
                tier = "✓ BUILD"
            else:
                tier = "↑ alt"
            rows.append({
                "rank": i, "trim": l.trim, "ext": l.ext, "int": l.interior,
                "dts": l.dts, "mom": l.momentum, "need": l.need,
                "cumulative": cumulative, "tier": tier, "key": l.key,
            })
        out[model] = {"allocation": alloc, "rows": rows,
                      "total_need": sum(l.need for l in res.lines if l.model == model)}
    return out


# --------------------------------------------------------------------------- #
# 2. Overstock / Wholesale
# --------------------------------------------------------------------------- #
def overstock(res: EngineResult) -> list:
    rows = []
    for l in res.lines:
        pos = res.positions.get(l.key)
        over = l.onlot - l.overstock_target
        if over < 1:
            continue
        aged = len(pos.aged_units) if pos else 0
        rows.append({
            "model": l.model, "trim": l.trim, "ext": l.ext, "int": l.interior,
            "on_hand": l.onlot, "target": l.overstock_target, "over": over,
            "wholesale_now": l.wholesale_now, "inbound": l.inbound,
            "dts": l.dts, "aged": aged, "key": l.key,
        })
    rows.sort(key=lambda r: (MODELS.index(r["model"]) if r["model"] in MODELS else 9,
                             -r["over"], -r["wholesale_now"]))
    return rows


# --------------------------------------------------------------------------- #
# 3. Wholesale VIN sheet (VIN-led — some aged units have blank/mangled Stock#s)
# --------------------------------------------------------------------------- #
def wholesale_vins(res: EngineResult) -> list:
    """Every wholesale-eligible unit: aged past its window, on-lot, non-demo.

    Capped per config at that config's WHOLESALE_NOW so the sheet lists what
    should actually move, not merely everything that is old.
    """
    rows = []
    for l in res.lines:
        pos = res.positions.get(l.key)
        if not pos or l.wholesale_now <= 0:
            continue
        # Oldest units first; only as many as wholesale_now says to move.
        units = sorted(pos.wholesale_eligible, key=lambda u: -u.dis)[:l.wholesale_now]
        for u in units:
            vin = u.serial or u.stock
            rows.append({
                "stock": u.stock or "—",
                "vin": vin,
                "vin_last6": vin[-6:] if vin else "—",
                "year": u.model_year or u.my or "",
                "model": u.model,
                "trim": l.trim or u.description,
                "ext_int": f"{u.ext}/{u.interior}",
                "days_in_stock": int(u.dis),
            })
    rows.sort(key=lambda r: -r["days_in_stock"])
    for i, r in enumerate(rows, 1):
        r["num"] = i
    return rows


# --------------------------------------------------------------------------- #
# 4. Demo Dashboard
# --------------------------------------------------------------------------- #
def demo_dashboard(res: EngineResult) -> list:
    import datetime as _dt
    s = res.settings
    rows = []
    for u in res.demo_units:
        days_in_stock = int(u.dis)
        # Days-as-demo from an explicit start date if we have one, else fall
        # back to days-in-stock (the workbook's own fallback).
        days_as_demo = days_in_stock
        for prefix, start in s.demo_starts.items():
            if prefix and u.stock.startswith(prefix):
                try:
                    d0 = _dt.date.fromisoformat(str(start))
                    days_as_demo = (res.time.today - d0).days
                except ValueError:
                    pass
                break
        note = ""
        for prefix, txt in s.demo_notes.items():
            if prefix and u.stock.startswith(prefix):
                note = str(txt).strip()
                break
        rows.append({
            "stock": u.stock, "vehicle": u.description, "msrp": u.msrp,
            "days_in_stock": days_in_stock, "days_as_demo": days_as_demo,
            "note": note,
            "swap": "⚠ SWAP" if days_as_demo > s.swap_threshold else "OK",
        })
    rows.sort(key=lambda r: -r["days_as_demo"])
    return rows


def previous_loaners(res: EngineResult) -> list:
    """Returned loaners now back in sellable inventory: real market days
    (days-in-stock minus the hidden demo period), never wholesale-flagged."""
    by_stock = {}
    for e in res.settings.prev_loaners:
        st = str(e.get("stock", "")).strip()
        if st:
            by_stock[st] = e
    rows = []
    for u in res.inventory:
        if u.is_dlr_inv and u.prev_loaner:
            entry = next((v for k, v in by_stock.items() if u.stock.startswith(k)), {})
            rows.append({
                "stock": u.stock, "vehicle": u.description,
                "ext_int": f"{u.ext}/{u.interior}",
                "dms_dis": int(u.dis), "retail_days": int(u.eff_dis),
                "days_out": int(u.dis - u.eff_dis),
                "note": str(entry.get("note", "")).strip(),
                "key": u.key,
            })
    rows.sort(key=lambda r: -r["retail_days"])
    return rows


# --------------------------------------------------------------------------- #
# Executive Demo Board — best combos to put execs into (VIN-led)
# --------------------------------------------------------------------------- #
def _demo_score(m) -> float:
    """Rank a config's fitness as an executive demo.

    A demo accumulates miles and age, so it must resell fast once released:
    days-to-sell dominates. Proven repeat depth (lifetime + recent) and current
    heat keep whims and one-offs off the board.
    """
    dts_component = max(0.0, (50 - m.dts) / 50.0) * 40      # faster resale = better
    pace = min(m.prate, 5.0) * 8                             # recent 60-day pace
    depth = min(m.total, 12) * 2                             # proven demand pool
    heat = m.r90 * 4                                         # live demand
    mom = {"ACCEL": 10, "steady": 6, "on cadence": 3}.get(m.momentum, 0)
    return dts_component + pace + depth + heat + mom


def _demo_reason(m) -> str:
    bits = [f"{int(m.dts)}-day resale", f"{m.total} sold lifetime"]
    if m.r90:
        bits.append(f"{m.r90} in 90d")
    elif m.r180:
        bits.append(f"{m.r180} in 180d")
    if m.momentum in ("ACCEL", "cooling"):
        bits.append(m.momentum)
    return " · ".join(bits)


def executive_demos(res: EngineResult) -> dict:
    """Per model, the best proven fast-moving combos to demo, with in-stock VINs.

    A combo qualifies only if it is a genuine fast, repeat seller (DTS under the
    demo cap, enough lifetime sales, live 180-day demand) — never a one-off. Each
    surfaced combo offers up to N fresh, in-stock, non-demo VINs to assign; a
    strong combo with nothing on the lot is flagged to order for a demo.
    """
    s = res.settings
    out = {}
    for model in MODELS:
        picks = []
        for l in res.lines:
            if l.model != model or l.suppressed:
                continue
            m = res.metrics.get(l.key)
            if not m or m.dts is None:
                continue
            if not (m.dts <= s.demo_pick_max_dts and m.total >= s.demo_pick_min_total
                    and m.r180 >= s.demo_pick_min_r180 and m.momentum != "dormant"):
                continue
            pos = res.positions.get(l.key)
            fresh = sorted(pos.onlot_units, key=lambda u: u.dis) if pos else []
            units = [{
                "stock": u.stock or "—",
                "vin": (u.serial or u.stock),
                "vin_last6": (u.serial or u.stock)[-6:] if (u.serial or u.stock) else "—",
                "dis": int(u.dis), "msrp": u.msrp,
                "year": u.model_year or u.my or "", "ext_int": f"{u.ext}/{u.interior}",
            } for u in fresh[:s.demo_vins_per_combo]]
            # A small nudge so an in-stock combo edges out an equally-fast combo
            # you'd have to order — without letting it outrank a clearly faster one.
            score = _demo_score(m) + (6 if units else 0)
            picks.append({
                "trim": l.trim, "ext": l.ext, "int": l.interior, "key": l.key,
                "dts": m.dts, "total": m.total, "r90": m.r90, "r180": m.r180,
                "momentum": m.momentum, "score": round(score, 1),
                "reason": _demo_reason(m), "onlot": l.onlot,
                "backup": max(0, l.onlot - 1),  # units left if you pull one for a demo
                "units": units, "in_stock": bool(units),
            })
        picks.sort(key=lambda p: -p["score"])
        out[model] = picks[:s.demo_picks_per_model]
    return out


# --------------------------------------------------------------------------- #
# Loaner / ICV program
# --------------------------------------------------------------------------- #
def loaner_board(res: EngineResult) -> dict:
    """Per model, the best configs to cycle through the courtesy-loaner fleet."""
    from . import loaner
    return loaner.loaner_candidates(res)


def loaner_fleet(res: EngineResult) -> dict:
    """Current in-service fleet + cascading release schedule and add count."""
    from . import loaner
    return loaner.loaner_fleet(res)


def build_sequence(res: EngineResult) -> dict:
    """Power-ranked, unit-by-unit RETAIL build sequence per model.

    This is the retail order only — it never mixes in loaner-fleet units. (The
    loaner fleet is a separate recommendation in the Loaner section; injecting its
    loss-making picks here made a model with no retail need look like a broken
    order of losses.) Retail need is expanded to individual units, where each
    successive unit of a combo decays in priority (order_unit_decay) — so a
    dominant combo front-loads several units, but a marginal combo yields after
    one or two and a stronger combo's later units can still outrank it. Runs of
    the same combo are grouped: "order 3× A, then 2× B, then 2 more× A". If the
    loaner program is active, the fleet's cascade intake is *reported* as slots
    reserved out of allocation, but those units are shown in the Loaner section,
    not here.
    """
    from . import loaner
    s = res.settings
    plan = loaner.loaner_order_plan(res)
    out = {}
    for model in MODELS:
        alloc = s.allocations.get(model, 0)
        reserved = plan["per_model"].get(model, 0)     # loaner slots (netting note)
        eff_alloc = max(0, alloc - reserved)
        # Rank combos by priority and show each ONCE with its full quantity — the
        # actionable order ("order N of A, then M of B"). Splitting a combo's units
        # into scattered 1x chips read as duplicates/broken to a user.
        combos = sorted(
            [l for l in res.lines
             if l.model == model and not l.suppressed and l.need > 0 and l.priority > -1],
            key=lambda l: -l.priority)
        groups, filled = [], 0
        for l in combos:
            # split a combo across the allocation line only if it straddles it
            take_build = max(0, min(int(l.need), eff_alloc - filled))
            take_alt = int(l.need) - take_build
            if take_build > 0:
                groups.append({"key": l.key, "trim": l.trim, "ext": l.ext, "int": l.interior,
                               "stream": "retail", "tier": "build", "qty": take_build,
                               "dts": l.dts, "momentum": l.momentum})
                filled += take_build
            if take_alt > 0:
                groups.append({"key": l.key, "trim": l.trim, "ext": l.ext, "int": l.interior,
                               "stream": "retail", "tier": "alt", "qty": take_alt,
                               "dts": l.dts, "momentum": l.momentum})
        total_units = sum(int(l.need) for l in combos)
        build_total = sum(g["qty"] for g in groups if g["tier"] == "build")
        out[model] = {
            "allocation": alloc, "fleet_reserved": reserved, "eff_alloc": eff_alloc,
            "retail_build": build_total, "groups": groups, "total_units": total_units,
        }
    return {"intake": plan["intake"], "service_months": plan["service_months"],
            "fleet_units": plan["fleet_units"], "per_model": out}


# --------------------------------------------------------------------------- #
# Retail Forecast — what the inventory you own is capable of producing
# --------------------------------------------------------------------------- #
def retail_forecast(res: EngineResult) -> dict:
    """Inventory-driven retail projection, not a pace extrapolation.

    For each config, projected retail over a horizon = MIN(demand, available):
      demand    = the config's monthly sell pace x seasonality x horizon-months
      available = on-lot (minus what should be wholesaled) + inbound arriving in
                  the horizon
    So a hot config with no stock forecasts low (inventory-limited) and a deep
    config with soft demand forecasts at its true velocity (demand-limited).
    Summed per model + total, for This month / Next 30 / Next 60 days, plus a
    days-of-supply and an inventory-health read (tight vs heavy).
    """
    import calendar as _cal
    import datetime as _dt
    today = res.time.today
    s = res.settings
    days_left = _cal.monthrange(today.year, today.month)[1] - today.day + 1
    horizons = [("This month", days_left), ("Next 30 days", 30), ("Next 60 days", 60)]

    def seas_factor(days, seas):
        return sum(seas[(today + _dt.timedelta(days=d)).month - 1] for d in range(days)) / days if days else 1.0

    def inbound_in(pos, days):
        if not pos:
            return 0
        end = today + _dt.timedelta(days=days)
        n = 0
        for cm, cnt in pos.arrivals.items():
            year = today.year if cm >= today.month else today.year + 1
            if today <= _dt.date(year, cm, 15) <= end:
                n += cnt
        return n

    def pace(l):
        m = res.metrics.get(l.key)
        return min(s.rate_cap, (m.prate / 2) if m else 0.0)

    out = {"horizons": [{"label": lab, "days": d} for lab, d in horizons],
           "per_model": {}, "total": {"forecast": [0.0, 0.0, 0.0]}}
    for model in MODELS:
        lines = [l for l in res.lines if l.model == model]
        onlot = sum(l.onlot for l in lines)
        inbound = sum(l.inbound for l in lines)
        monthly_demand = sum(pace(l) for l in lines)
        forecasts, demands = [], []
        for hi, (lab, days) in enumerate(horizons):
            months = days / _DAYS_PER_MONTH
            sf = seas_factor(days, res.seasonality[model])
            proj = 0.0
            for l in lines:
                pos = res.positions.get(l.key)
                avail = max(0, l.onlot - l.wholesale_now) + inbound_in(pos, days)
                proj += min(pace(l) * sf * months, avail)
            forecasts.append(round(proj))
            demands.append(round(monthly_demand * sf * months))
            out["total"]["forecast"][hi] += proj
        # 60-day demand vs available -> health
        demand60 = monthly_demand * seas_factor(60, res.seasonality[model]) * (60 / _DAYS_PER_MONTH)
        avail60 = sum(max(0, l.onlot - l.wholesale_now) + inbound_in(res.positions.get(l.key), 60)
                      for l in lines)
        if demand60 <= 0.01:
            health = "cold — little live demand"
        elif avail60 < demand60 * 0.85:
            health = "tight — demand outruns stock"
        elif avail60 > demand60 * 1.6:
            health = "heavy — stock outruns demand"
        else:
            health = "balanced"
        dos = round(onlot / monthly_demand * _DAYS_PER_MONTH) if monthly_demand > 0 else None
        out["per_model"][model] = {
            "forecast": forecasts, "demand": demands, "onlot": onlot, "inbound": inbound,
            "monthly_demand": round(monthly_demand, 1), "days_supply": dos,
            "demand60": round(demand60), "avail60": avail60, "health": health,
        }
    out["total"]["forecast"] = [round(x) for x in out["total"]["forecast"]]
    out["total"]["onlot"] = sum(d["onlot"] for d in out["per_model"].values())
    out["total"]["inbound"] = sum(d["inbound"] for d in out["per_model"].values())
    return out


_DAYS_PER_MONTH = 30.44


# --------------------------------------------------------------------------- #
# 5. Pace Check
# --------------------------------------------------------------------------- #
def pace_check(res: EngineResult) -> list:
    tb = res.time
    rows = []
    for model in MODELS:
        model_sales = [s for s in res.sales if s.first_vin and s.model == model]
        actual_90 = sum(1 for s in model_sales if s.midx > tb.latest_midx - 3)
        act_60 = xround(actual_90 / tb.el90 * 2, 1)
        pred_60 = xround(sum(m.hist60 for m in res.metrics.values() if m.model == model), 1)
        variance = xround(act_60 - pred_60, 1)
        band = max(2.0, 0.25 * pred_60)
        if variance > band:
            read = "AHEAD of forecast"
        elif variance < -band:
            read = "BEHIND forecast"
        else:
            read = "ON TARGET"
        # Coverage = share of a model's sales the engine can actually parse into
        # a config key. Legacy QX50/QX55 sales map to QX65 at the model level by
        # design (brief §18), so they count as seen here; the orphan list in
        # data_health separately flags configs that sell but have no order line.
        total = len(model_sales)
        mapped = sum(1 for s in model_sales if s.key in res.metrics)
        coverage = (mapped / total) if total else 1.0
        if coverage < 0.85:
            read += "  (coverage <85% — read is soft)"
        rows.append({
            "model": model, "actual_90": actual_90, "act_60_pace": act_60,
            "pred_60_pace": pred_60, "variance": variance, "read": read,
            "coverage": round(coverage, 3),
        })
    return rows


# --------------------------------------------------------------------------- #
# Fleet 60-day target (context table) + orphans (data health)
# --------------------------------------------------------------------------- #
def fleet_targets(res: EngineResult) -> dict:
    """Model 60-day stock target by month = this month's rate + next month's,
    seasonally correct, from the live per-model monthly sell rate."""
    out = {}
    for model in MODELS:
        # Reconstruct the monthly rate from seasonality * average rate.
        # rate[m] = index[m] * avg_rate ; avg_rate recovered from hist60 sum.
        rates = _monthly_rates(res, model)
        out[model] = [xround(rates[m] + rates[(m + 1) % 12]) for m in range(12)]
    return out


def _monthly_rates(res: EngineResult, model: str) -> list:
    """Per-calendar-month unit sell rate for a model (part-adjusted)."""
    tb = res.time
    import math
    latest_calm = ((tb.latest_midx - 1) % 12) + 1 if tb.latest_midx else 0
    sales_by_month = [0] * 12
    for s in res.sales:
        if s.first_vin and s.model == model and s.midx > 0:
            sales_by_month[(s.midx - 1) % 12] += 1
    rates = []
    for m in range(1, 13):
        occ = max(1, math.floor((tb.latest_midx - m) / 12)
                  - math.ceil((tb.earliest_midx - m) / 12) + 1)
        occ = max(0.1, occ - (1 - tb.part_frac if latest_calm == m else 0))
        rates.append(sales_by_month[m - 1] / occ)
    return rates


def data_health(res: EngineResult) -> dict:
    tb = res.time
    orphans = []
    for o in res.orphans:
        m = res.metrics.get(o["key"])
        orphans.append({"key": o["key"], "sales": o["sales"],
                        "dts": m.dts if m else None})
    return {
        "latest_month": f"{tb.latest_midx // 12}-{tb.latest_midx % 12:02d}",
        "latest_open": tb.latest_open,
        "part_frac": round(tb.part_frac, 3),
        "span_months": round(tb.span_months, 2),
        "window_90_spans": round(tb.el90, 2),
        "orphans": orphans,
        "learned_configs": len(res.metrics),
    }


def build_all(res: EngineResult) -> dict:
    return {
        "order_priority": order_priority(res),
        "overstock": overstock(res),
        "wholesale_vins": wholesale_vins(res),
        "demo_dashboard": demo_dashboard(res),
        "previous_loaners": previous_loaners(res),
        "executive_demos": executive_demos(res),
        "loaner_board": loaner_board(res),
        "loaner_fleet": loaner_fleet(res),
        "build_sequence": build_sequence(res),
        "retail_forecast": retail_forecast(res),
        "pace_check": pace_check(res),
        "fleet_targets": fleet_targets(res),
        "data_health": data_health(res),
    }
