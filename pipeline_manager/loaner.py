"""Loaner-program economics: which units to cycle through the ICV courtesy
fleet for the best preowned profit, and a cascading release schedule.

The one thing the retail engine can't see is how a unit moves on the *preowned*
side — so this module is where preowned velocity and price live, either measured
from a pasted used/CPO sales history or modeled from the new-car demand signal.

Three math problems, done in order:

  1. COST — the true cost per combo (invoice, from the inventory export).
  2. USED VALUE — what a comparable current / 1-MY-old unit sells for. Until real
     data is pasted this is modeled as 80% of the CHEAPEST NEW price, and the
     cheapest new price is invoice MINUS the current rebate (what a customer can
     buy a *new* one for). Real used sales + public wholesale/auction comps
     replace the 80% — that street price is what you could re-buy the unit for,
     so a written-down cost above it means you're upside down.
  3. RESULT — the write-downs only reduce the preowned cost basis WHEN the unit
     retires from the fleet; then preowned_gross tells you if the retail resale
     is at (or near) profit.

    cheapest_new  = cost - rebate[model]
    used_price    = measured  ELSE  preowned_price_pct x cheapest_new   (~0.80)
    icv_total     = ICV[model]                      (ONE-TIME, booked at report-in)
    depr_total    = (cost or MSRP) x depr% x service_months
    bonus         = velocity_bonus IF retailed within max_months AND under mile_cap
    adjusted_cost = cost - icv_total - depr_total - bonus
    preowned_gross = used_price - adjusted_cost - recon      (can be negative)

The ICV is a single allowance per vehicle, not a monthly one; the unit must stay
in service >= min months to keep it. Only the write-down accrues monthly.

A unit is a good loaner when that used_gross is real money *and* it clears the
used market fast enough to retail inside the max_months / mile_cap window (so the
$2,500 bonus is actually captured, not forfeited). Because loaners replace
retailable units, the board also weighs opportunity cost: burning your fastest
new-seller as a loaner costs a quick new sale.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from .keys import digits_only, xround

MODELS = ("QX80", "QX60", "QX65")
_DAYS_PER_MONTH = 30.44


# --------------------------------------------------------------------------- #
# Preowned velocity + price (measured, else modeled)
# --------------------------------------------------------------------------- #
@dataclass
class PreownedStat:
    used_dts: float          # days-to-sell on the preowned side
    used_price: float        # typical preowned retail price
    count: int               # sample size (0 for a modeled stat)
    modeled: bool            # True = inferred from new-car demand, not measured


def _rep_maps(inventory) -> tuple[dict, dict, dict, dict]:
    """Representative cost & MSRP per config key and per trim (model|code),
    averaged over the units actually in the pipeline."""
    csum, msum, cnt = {}, {}, {}
    tcsum, tmsum, tcnt = {}, {}, {}
    for u in inventory:
        if not u.key:
            continue
        code = u.key.split("|")[1]
        tkey = f"{u.model}|{code}"
        if u.inv_cost:
            csum[u.key] = csum.get(u.key, 0.0) + u.inv_cost
            cnt[u.key] = cnt.get(u.key, 0) + 1
            tcsum[tkey] = tcsum.get(tkey, 0.0) + u.inv_cost
            tcnt[tkey] = tcnt.get(tkey, 0) + 1
        if u.msrp:
            msum[u.key] = msum.get(u.key, 0.0) + u.msrp
            tmsum[tkey] = tmsum.get(tkey, 0.0) + u.msrp
    cost_key = {k: csum[k] / cnt[k] for k in csum if cnt.get(k)}
    msrp_key = {k: msum[k] / cnt[k] for k in msum if cnt.get(k)}
    cost_trim = {k: tcsum[k] / tcnt[k] for k in tcsum if tcnt.get(k)}
    msrp_trim = {k: tmsum[k] / tcnt[k] for k in tmsum if tcnt.get(k)}
    return cost_key, msrp_key, cost_trim, msrp_trim


def rep_cost_msrp(key, model, code, cost_key, msrp_key, cost_trim, msrp_trim) -> tuple[float, float]:
    tkey = f"{model}|{code}"
    cost = cost_key.get(key) or cost_trim.get(tkey) or 0.0
    msrp = msrp_key.get(key) or msrp_trim.get(tkey) or 0.0
    return cost, msrp


def compute_preowned(s, metrics, inventory) -> dict:
    """Preowned stat per trim (model|code). Measured from preowned_sales when
    present, otherwise modeled: used velocity tracks the new-car days-to-sell and
    used price = a share of INVOICE (the store's own new selling price), since a
    nearly-new, sub-10k-mile loaner retails at ~that same point."""
    cost_key, msrp_key, cost_trim, msrp_trim = _rep_maps(inventory)

    # Measured: aggregate pasted preowned sales by trim.
    measured: dict[str, dict] = {}
    for r in s.preowned_sales or []:
        code = digits_only(r.get("code"))[:4]
        model = str(r.get("model", "")).strip().upper()
        if not model or not code:
            continue
        tkey = f"{model}|{code}"
        days = _num(r.get("days"))
        price = _num(r.get("price")) or _num(r.get("gross"))
        agg = measured.setdefault(tkey, {"d": 0.0, "dc": 0, "p": 0.0, "pc": 0, "n": 0})
        agg["n"] += 1
        if days is not None:
            agg["d"] += days
            agg["dc"] += 1
        if price is not None:
            agg["p"] += price
            agg["pc"] += 1

    def modeled_price(tkey):
        model = tkey.split("|")[0]
        rebate = float((s.rebates or {}).get(model, 0) or 0)
        cheapest_new = max(0.0, cost_trim.get(tkey, 0.0) - rebate)
        return cheapest_new * s.preowned_price_pct

    out: dict[str, PreownedStat] = {}
    for tkey, a in measured.items():
        dts = a["d"] / a["dc"] if a["dc"] else _model_avg_dts(metrics, tkey.split("|")[0])
        price = a["p"] / a["pc"] if a["pc"] else modeled_price(tkey)
        out[tkey] = PreownedStat(round(dts, 1), round(price, 0), a["n"], modeled=False)

    # Modeled fallback for every trim in the pipeline not already measured.
    trims = {f"{u.model}|{u.key.split('|')[1]}" for u in inventory if u.key}
    for tkey in trims:
        if tkey in out:
            continue
        model = tkey.split("|")[0]
        used_dts = _trim_new_dts(metrics, tkey) or _model_avg_dts(metrics, model) or 45.0
        out[tkey] = PreownedStat(round(used_dts, 1), round(modeled_price(tkey), 0), 0, modeled=True)
    return out


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _trim_new_dts(metrics, tkey) -> float | None:
    model, code = tkey.split("|")
    vals = [m.dts for m in metrics.values()
            if m.model == model and m.code == code and m.dts is not None and m.total > 0]
    return sum(vals) / len(vals) if vals else None


def _model_avg_dts(metrics, model) -> float | None:
    vals = [m.dts for m in metrics.values()
            if m.model == model and m.dts is not None and m.total > 0]
    return sum(vals) / len(vals) if vals else None


# --------------------------------------------------------------------------- #
# The shared money model (Python + JS must agree)
# --------------------------------------------------------------------------- #
def loaner_economics(cost, msrp, model, used_dts, used_price, s, rebate=0.0) -> dict:
    """Full loaner P&L for one unit at the planned service length.

    Returns the cheapest-new price, the write-down stack, whether the velocity
    bonus is captured, the adjusted cost basis, and the preowned gross that
    results (negative = upside down: you could re-buy it cheaper on the street).
    """
    icv = float((s.loaner_icv or {}).get(model, 0) or 0)
    svc = max(0, int(s.loaner_service_months))
    icv_total = icv                          # one-time allowance, booked once
    base_val = cost if str(s.loaner_depr_base).lower() != "msrp" else msrp
    depr_total = base_val * (s.loaner_depr_pct / 100.0) * svc

    used_months = (used_dts or 0) / _DAYS_PER_MONTH
    sale_month = svc + used_months            # program start -> retailed
    miles_at_sale = s.loaner_miles_per_month * svc
    bonus_ok = (sale_month <= s.loaner_max_months) and (miles_at_sale < s.loaner_mile_cap)
    bonus = float(s.loaner_velocity_bonus) if bonus_ok else 0.0

    cheapest_new = max(0.0, cost - float(rebate or 0))
    adjusted_cost = cost - icv_total - depr_total - bonus
    preowned_gross = (used_price or 0) - adjusted_cost - float(s.loaner_recon)
    return {
        "cost": round(cost, 0), "msrp": round(msrp, 0), "rebate": round(float(rebate or 0), 0),
        "cheapest_new": round(cheapest_new, 0),
        "icv_total": round(icv_total, 0), "depr_total": round(depr_total, 0),
        "bonus": round(bonus, 0), "bonus_ok": bonus_ok,
        "adjusted_cost": round(adjusted_cost, 0),
        "used_price": round(used_price or 0, 0),
        # kept as `used_gross` for the report/UI key, but it is the preowned gross
        "used_gross": round(preowned_gross, 0),
        "upside_down": preowned_gross < 0,
        "sale_month": round(sale_month, 1), "miles_at_sale": int(miles_at_sale),
        "service_months": svc,
    }


# --------------------------------------------------------------------------- #
# Candidate board — which configs to put into the program
# --------------------------------------------------------------------------- #
def _loaner_score(econ, pstat, metric) -> float:
    """Rank a config as a loaner candidate.

    Primary: preowned gross — the profit (or loss) once it retires from the fleet
    and retails used. Losses drag hard (an upside-down unit you'd re-buy cheaper on
    the street is the opposite of a good loaner). Then reward fast used turn and a
    captured bonus, and lightly penalize burning a very fast NEW seller.
    """
    gross = econ["used_gross"]
    gross_band = max(-60.0, min(40.0, gross / 500.0))         # $20k gross -> 40; losses drag
    vel = max(0.0, (60 - (pstat.used_dts or 60)) / 60.0) * 20  # faster used = better
    bonus_band = 10.0 if econ["bonus_ok"] else 0.0
    opp = 0.0
    if metric and metric.dts is not None and metric.r90 >= 2 and metric.dts <= 30:
        opp = -8.0
    measured_bonus = 3.0 if not pstat.modeled else 0.0
    return gross_band + vel + bonus_band + opp + measured_bonus


def _all_candidates(res) -> list:
    """Every non-suppressed config priced as a loaner candidate, with econ."""
    s = res.settings
    cost_key, msrp_key, cost_trim, msrp_trim = _rep_maps(res.inventory)
    pre = res.preowned
    out = []
    for l in res.lines:
        if l.suppressed:
            continue
        model = l.model
        code = l.key.split("|")[1]
        pstat = pre.get(f"{model}|{code}")
        if not pstat:
            continue
        cost, msrp = rep_cost_msrp(l.key, model, code, cost_key, msrp_key,
                                   cost_trim, msrp_trim)
        if cost <= 0 and msrp <= 0:
            continue
        metric = res.metrics.get(l.key)
        rebate = float((s.rebates or {}).get(model, 0) or 0)
        # Measured used price is trim-level; a modeled price anchors to THIS
        # config's cheapest-new (invoice - rebate) at preowned_price_pct (~80%).
        used_price = (max(0.0, cost - rebate) * s.preowned_price_pct
                      if pstat.modeled else pstat.used_price)
        econ = loaner_economics(cost, msrp, model, pstat.used_dts, used_price, s,
                                rebate=rebate)
        pos = res.positions.get(l.key)
        fresh = sorted(pos.onlot_units, key=lambda u: u.dis) if pos else []
        units = [{
            "stock": u.stock or "—", "vin": (u.serial or u.stock),
            "vin_last6": (u.serial or u.stock)[-6:] if (u.serial or u.stock) else "—",
            "dis": int(u.dis), "msrp": u.msrp, "cost": u.inv_cost,
            "year": u.model_year or u.my or "", "ext_int": f"{u.ext}/{u.interior}",
        } for u in fresh[:s.demo_vins_per_combo]]
        score = _loaner_score(econ, pstat, metric) + (4 if units else 0)
        out.append({
            "model": model, "trim": l.trim, "ext": l.ext, "int": l.interior, "key": l.key,
            "used_dts": pstat.used_dts, "used_price": econ["used_price"],
            "modeled": pstat.modeled, "score": round(score, 1),
            "net_value": econ["used_gross"], "econ": econ,
            "new_dts": l.dts, "onlot": l.onlot, "in_stock": bool(units),
            "units": units, "reason": _cand_reason(econ, pstat, l),
        })
    out.sort(key=lambda p: -p["score"])
    return out


def loaner_candidates(res) -> dict:
    """Per model, the best configs to designate as loaners, VIN-led from current
    sellable inventory (like the executive demo board)."""
    s = res.settings
    out = {m: [] for m in MODELS}
    for p in _all_candidates(res):
        out[p["model"]].append(p)
    return {m: out[m][:s.demo_picks_per_model] for m in MODELS}


def loaner_order_plan(res) -> dict:
    """Problem 3 — how many fresh units to bring into the loaner fleet on this
    order (auto cascade), and which combos fill those slots (best preowned
    economics). The fleet replaces retailable units, so these are netted out of
    each model's allocation in the build sequence.

    Cascade intake = fleet_target / service_months (to hold the target in service
    when each unit serves that many months, one cascades in as one cascades out).
    Slots are filled round-robin over the best-preowned combos so the fleet spans
    the strongest economics rather than piling onto a single config.
    """
    s = res.settings
    svc = max(1, int(s.loaner_service_months))
    intake = max(0, round(s.loaner_fleet_target / svc))
    ranked = _all_candidates(res)                # best preowned first
    fleet_units, per_model = [], {m: 0 for m in MODELS}
    if intake and ranked:
        i, guard = 0, 0
        counts = {}
        # round-robin one unit per combo, cycling, until intake is filled
        while len(fleet_units) < intake and guard < intake * len(ranked) + len(ranked):
            c = ranked[i % len(ranked)]
            counts[c["key"]] = counts.get(c["key"], 0) + 1
            fleet_units.append({"model": c["model"], "key": c["key"], "trim": c["trim"],
                                "ext": c["ext"], "int": c["int"],
                                "econ": c["econ"], "net_value": c["net_value"],
                                "n": counts[c["key"]]})
            per_model[c["model"]] += 1
            i += 1
            guard += 1
    return {"intake": intake, "service_months": svc,
            "fleet_units": fleet_units, "per_model": per_model}


def _cand_reason(econ, pstat, line) -> str:
    src = "modeled" if pstat.modeled else f"{pstat.count} used sales"
    g = int(econ["used_gross"])
    bits = [(f"${g:,} preowned profit" if g >= 0 else f"-${abs(g):,} preowned LOSS"),
            f"{int(pstat.used_dts)}-day used turn ({src})"]
    if econ["upside_down"]:
        bits.append("⚠ upside-down vs. street")
    bits.append("✓ bonus" if econ["bonus_ok"] else "✗ misses bonus window")
    if line.dts is not None and line.dts <= 30 and line.momentum in ("ACCEL", "steady"):
        bits.append("fast new-seller — weigh opportunity cost")
    return " · ".join(bits)


# --------------------------------------------------------------------------- #
# Fleet + cascading release schedule
# --------------------------------------------------------------------------- #
def _match_unit(stock, inventory):
    for u in inventory:
        if stock and u.stock.startswith(stock):
            return u
    return None


def loaner_fleet(res) -> dict:
    """Current in-service fleet with each unit's age, miles, projected release
    and status, plus how many to add this month to hold the fleet target
    (cascading release keeps the release dates staggered)."""
    s = res.settings
    today = res.time.today
    cost_key, msrp_key, cost_trim, msrp_trim = _rep_maps(res.inventory)
    pre = res.preowned

    rows, releasing = [], 0
    for e in s.loaner_units or []:
        stock = str(e.get("stock", "")).strip()
        if not stock:
            continue
        start = _iso(e.get("start"))
        months = ((today - start).days / _DAYS_PER_MONTH) if start else 0.0
        miles = _num(e.get("miles"))
        if miles is None:
            miles = s.loaner_miles_per_month * months
        u = _match_unit(stock, res.inventory)
        model = u.model if u else str(e.get("model", "")).strip().upper()
        icv = float((s.loaner_icv or {}).get(model, 0) or 0)
        release_at = start + _dt.timedelta(days=round(s.loaner_max_months * _DAYS_PER_MONTH)) \
            if start else None
        eligible = months >= s.loaner_min_months
        near_cap = miles >= s.loaner_mile_cap * 0.9
        near_time = months >= s.loaner_max_months - 1
        if not eligible:
            status = f"🅗 HOLD · {_ceil_days(s.loaner_min_months, months)}d to ICV"
        elif near_cap or near_time:
            status = "🔴 RELEASE NOW"
            releasing += 1
        else:
            status = "🟢 READY"
        rows.append({
            "stock": stock, "model": model,
            "vehicle": u.description if u else "",
            "ext_int": f"{u.ext}/{u.interior}" if u else "",
            "months": round(months, 1), "miles": int(miles),
            # ICV is a one-time allowance, secured only once the unit clears the
            # min-months floor; 0 (pending) while it is still on HOLD.
            "icv_secured": int(icv) if eligible else 0, "icv": int(icv),
            "eligible": eligible, "status": status,
            "release_by": release_at.isoformat() if release_at else "",
            "note": str(e.get("note", "")).strip(),
        })
    rows.sort(key=lambda r: -r["months"])

    in_service = len(rows)
    after_release = in_service - releasing
    to_add = max(0, s.loaner_fleet_target - after_release)
    return {
        "target": s.loaner_fleet_target, "in_service": in_service,
        "releasing_now": releasing, "to_add": to_add, "rows": rows,
    }


def _iso(v):
    try:
        return _dt.date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _ceil_days(min_months, months) -> int:
    import math
    return max(0, math.ceil((min_months - months) * _DAYS_PER_MONTH))


def loaner_stock_prefixes(s) -> list:
    """Stock# prefixes of in-service loaners — pulled from sellable inventory
    exactly like demos (loaners replace retailable units)."""
    return [str(e.get("stock", "")).strip() for e in (s.loaner_units or [])
            if str(e.get("stock", "")).strip()]
