"""The engine: recompute every number from the raw exports on every run.

There is no persistence, no cache, no incremental update.  `run()` takes the
parsed inventory + sales + settings and returns a fully-derived result object.
Call it twice with the same inputs and you get byte-identical output; change one
input and everything downstream moves.  That determinism is the entire reason
this exists as code instead of a spreadsheet.

The pipeline, top to bottom:
    time base  ->  per-config metrics  ->  seasonality  ->  inventory position
    ->  demo suppression  ->  per-config order line (base, target, NEED, rank)
"""

from __future__ import annotations

import calendar
import datetime as _dt
import math
import re
from dataclasses import dataclass, field

from .config import Settings
from .ingest import InventoryUnit, Sale
from .keys import xround


# --------------------------------------------------------------------------- #
# Result records
# --------------------------------------------------------------------------- #
@dataclass
class TimeBase:
    today: _dt.date
    latest_midx: int
    earliest_midx: int
    current_midx: int
    part_frac: float          # fraction of the current month elapsed
    span_months: float        # part-adjusted months of sales history
    el90: float               # elapsed months inside the 90-day window
    el180: float              # elapsed months inside the 180-day window
    latest_open: bool         # is the newest sales month the current, partial month?


@dataclass
class ConfigMetrics:
    key: str
    model: str
    code: str
    ext: str
    interior: str
    total: int = 0
    dts: float | None = None      # avg days-to-sell; None = never sold
    hist60: float = 0.0           # lifetime rate normalised to 60 days
    r90: int = 0
    r180: int = 0
    prate: float = 0.0            # blended sell-rate per 60 days (the key number)
    momentum: str = "dormant"
    floor: int = 0
    mom_adj: int = 0
    base: int = 0


@dataclass
class InvPosition:
    onlot: int = 0                       # DLR-INV, non-demo units
    inbound_total: int = 0               # every pipeline unit for this key
    arrivals: dict = field(default_factory=dict)   # calendar-month -> count
    stalled: int = 0                     # on-lot units aged past stall_days
    aged_units: list = field(default_factory=list)  # on-lot units past aged_days
    wholesale_eligible: list = field(default_factory=list)  # aged past MAX(min,DTS)
    onlot_units: list = field(default_factory=list)  # DLR-INV, non-demo unit objects


@dataclass
class OrderLine:
    model: str
    code: str
    ext: str
    interior: str
    trim: str
    key: str
    dts: float | None
    momentum: str
    onlot: int
    inbound: int
    proj_at_arrival: float
    base: int                 # base used for ordering (found -> metric, else 1)
    found: bool               # was this key learned by the engine?
    mom_factor: float
    order_target: int         # momentum-earned, seasonal, at arrival month
    overstock_target: int     # raw seasonal target at the order month
    need: int
    suppressed: bool
    demoted: bool
    eff_demote: bool
    priority: float
    wholesale_now: int
    buy_grade: str = ""
    monthly_plan: list = field(default_factory=list)
    demo_returning: int = 0   # active demos of this config expected back in-window


@dataclass
class EngineResult:
    settings: Settings
    time: TimeBase
    metrics: dict              # key -> ConfigMetrics (learned configs only)
    seasonality: dict          # model -> [12 indices]
    positions: dict            # key -> InvPosition
    lines: list                # OrderLine, one per roster config
    demo_units: list           # InventoryUnit flagged as demo
    inventory: list
    sales: list
    orphans: list              # keys sold/stocked but not on the roster
    arrival_windows: dict = field(default_factory=dict)  # model -> continuous lead (mo)
    preowned: dict = field(default_factory=dict)  # model|code -> PreownedStat


# --------------------------------------------------------------------------- #
# Time base
# --------------------------------------------------------------------------- #
def _days_in_month(d: _dt.date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def compute_time_base(sales: list[Sale], today: _dt.date) -> TimeBase:
    midxs = [s.midx for s in sales if s.midx > 0]
    current_midx = today.year * 12 + today.month
    if not midxs:
        return TimeBase(today, 0, 0, current_midx, 1.0, 1.0, 3.0, 6.0, False)
    latest = max(midxs)
    earliest = min(midxs)
    latest_open = latest == current_midx
    part_frac = max(0.05, today.day / _days_in_month(today)) if latest_open else 1.0
    span = max(0.25, (latest - earliest + 1) - (1 - part_frac))
    return TimeBase(
        today=today,
        latest_midx=latest,
        earliest_midx=earliest,
        current_midx=current_midx,
        part_frac=part_frac,
        span_months=span,
        el90=2 + part_frac,
        el180=5 + part_frac,
        latest_open=latest_open,
    )


# --------------------------------------------------------------------------- #
# Per-config metrics (learned from sales history)
# --------------------------------------------------------------------------- #
def _trade_midx(value):
    """Month index from a trade date: YYYY-MM-DD, YYYY-MM, or YYYYMM."""
    if value in (None, ""):
        return None
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.year * 12 + value.month
    s = str(value).strip()
    m = re.match(r"^(\d{4})[-/]?(\d{2})", s)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2))
    return None


def _trade_records(trades, tb: TimeBase) -> list:
    """Normalise raw trade dicts into {key, model, midx, days} records."""
    from .keys import build_key, coerce_num, digits_only, model_from_code
    out = []
    for t in trades or []:
        code = digits_only(t.get("code"))
        model = t.get("model") or model_from_code(code)
        ext = str(t.get("ext", "")).strip()
        interior = str(t.get("int", t.get("interior", ""))).strip()
        key = build_key(model, code, ext, interior)
        if not key or not model:
            continue
        days = coerce_num(t.get("days"), None) if t.get("days") not in (None, "") else None
        out.append({"key": key, "model": model,
                    "midx": _trade_midx(t.get("date")), "days": days})
    return out


def compute_metrics(sales: list[Sale], tb: TimeBase, s: Settings,
                    roster: list[dict]) -> dict:
    """Build ConfigMetrics for every config the sales history has seen, plus a
    zero entry for every roster combo it didn't (see the seeding note below).

    Only the *first* row per VIN counts (exports double-list some VINs), so a
    config's TOTAL is genuine unique units, not line count.
    """
    metrics: dict[str, ConfigMetrics] = {}
    for sale in sales:
        if not sale.first_vin or not sale.key or not sale.model:
            continue
        m = metrics.get(sale.key)
        if m is None:
            m = ConfigMetrics(sale.key, sale.model, sale.model_code[:4],
                              sale.ext, sale.interior)
            metrics[sale.key] = m
        m.total += 1
        if sale.days_to_sell is not None:
            m._dts_sum = getattr(m, "_dts_sum", 0.0) + sale.days_to_sell
            m._dts_cnt = getattr(m, "_dts_cnt", 0) + 1
        if sale.midx > tb.latest_midx - 3:
            m.r90 += 1
        if sale.midx > tb.latest_midx - 6:
            m.r180 += 1

    # Fold in outbound dealer trades. A trade out is a sale out the other door:
    # it grades that config's speed to enter/exit inventory (its days-in-stock
    # feeds DTS), counts toward lifetime and recent demand, and so moves PRATE,
    # momentum, and the sell/wholesale rate exactly like a showroom sale.
    for tr in _trade_records(getattr(s, "trades", []), tb):
        m = metrics.get(tr["key"])
        if m is None:
            _, code, ext, interior = tr["key"].split("|")
            m = ConfigMetrics(tr["key"], tr["model"], code, ext, interior)
            metrics[tr["key"]] = m
        m.total += 1
        if tr["days"] is not None:
            m._dts_sum = getattr(m, "_dts_sum", 0.0) + tr["days"]
            m._dts_cnt = getattr(m, "_dts_cnt", 0) + 1
        if tr["midx"] and tb.latest_midx:
            if tr["midx"] > tb.latest_midx - 3:
                m.r90 += 1
            if tr["midx"] > tb.latest_midx - 6:
                m.r180 += 1

    # Seed every roster combo the sales history never mentioned as a *known*
    # zero config.  This is the found-with-base-0 case (a dormant catalog combo),
    # deliberately kept separate from the not-found case (a genuinely novel
    # combination, base 1).  Without this seeding, dead roster combos would look
    # "new" and phantom-order one unit each — exactly the bug the brief warns of.
    for cfg in roster:
        key = f"{cfg['model']}|{cfg['code']}|{cfg['ext']}|{cfg['int']}"
        if key not in metrics:
            metrics[key] = ConfigMetrics(key, cfg["model"], cfg["code"],
                                         cfg["ext"], cfg["int"])

    for m in metrics.values():
        dts_cnt = getattr(m, "_dts_cnt", 0)
        m.dts = xround(getattr(m, "_dts_sum", 0.0) / dts_cnt, 0) if dts_cnt else None
        m.hist60 = xround(m.total / tb.span_months * 2, 2)
        # PRATE — the blend: half the 90-day pace + half the 180-day pace, each
        # divided by *elapsed* time and expressed per 60 days.  The halving and
        # the per-60-day scaling cancel to R90/EL90 + R180/EL180.
        m.prate = m.r90 / tb.el90 + m.r180 / tb.el180
        _classify(m, tb, s)
    return metrics


def _recent_pace_60(m: ConfigMetrics, tb: TimeBase) -> float:
    """Recent 90-day pace expressed per 60 days (R90 normalised by elapsed)."""
    return m.r90 / tb.el90 * 2


def _classify(m: ConfigMetrics, tb: TimeBase, s: Settings) -> None:
    """Momentum, velocity floor and base — brief §6/§7/§8."""
    recent60 = _recent_pace_60(m, tb)
    dts_ok60 = m.dts is not None and m.dts <= 60

    # Momentum. ACCEL needs two sales in 90 days (the "prove itself" bar).
    if m.r90 >= 2 and recent60 > m.hist60 * 1.15 and dts_ok60:
        m.momentum = "ACCEL"
    elif m.r90 == 0 and m.r180 > 0:
        m.momentum = "on cadence"
    elif m.r90 > 0 and recent60 < m.hist60 * 0.6:
        m.momentum = "cooling"
    elif m.r90 > 0:
        m.momentum = "steady"
    else:
        m.momentum = "dormant"

    # Velocity floor. The DTS<=90 gate is the paperweight veto: a config that
    # takes longer than that to sell can never earn a stocking base.
    #
    # smooth_base (default, best logic): carry the 60-day pace as a *continuous*
    # value so a hairline change (e.g. the elapsed-time drift within a month)
    # can't flip the base by a whole unit and get amplified by seasonality. The
    # single rounding happens once, at the final order number.
    # Legacy (workbook parity): round the pace into an integer floor here.
    if m.prate >= 0.5 and m.dts is not None and m.dts <= s.paperweight_dts:
        m.floor = max(1.0, m.prate) if s.smooth_base else float(max(1, xround(m.prate)))
    elif m.dts is not None and m.dts <= 60 and m.r180 > 0:
        m.floor = 1.0
    else:
        m.floor = 0.0

    m.mom_adj = 1 if m.momentum == "ACCEL" else (-1 if m.momentum == "cooling" else 0)
    base = 0.0 if m.floor == 0 else max(1.0, m.floor + m.mom_adj)
    m.base = base if s.smooth_base else int(base)


# --------------------------------------------------------------------------- #
# Seasonality (per model, computed live from the sales history)
# --------------------------------------------------------------------------- #
def compute_seasonality(sales: list[Sale], tb: TimeBase, shrink_k: float = 0.0) -> dict:
    """12-month multiplier curve per model, normalised to average 1.0.

    Each calendar month's raw sales are divided by how many times that month
    *occurred* in the data span (part-adjusted for an open current month), which
    turns supply into a comparable monthly rate; the curve is that rate indexed
    to its own 12-month average.

    `shrink_k` (>0) tames sparse-data noise: a month index is pulled toward the
    neutral 1.0 by weight n/(n+shrink_k), where n is that month's sales count. A
    peak built on one December (n=1) barely moves the curve; a peak on 20 sales
    keeps most of its lift. This stops a single data point from swinging the order
    4x. shrink_k=0 reproduces the raw workbook curve (its parity test pins that).
    """
    latest_calm = ((tb.latest_midx - 1) % 12) + 1 if tb.latest_midx else 0
    out: dict[str, list[float]] = {}
    for model in ("QX80", "QX60", "QX65"):
        sales_by_month = [0] * 12
        for s in sales:
            if s.first_vin and s.model == model and s.midx > 0:
                cal_m = ((s.midx - 1) % 12)
                sales_by_month[cal_m] += 1
        rates = []
        for m in range(1, 13):
            occ = max(1, math.floor((tb.latest_midx - m) / 12)
                      - math.ceil((tb.earliest_midx - m) / 12) + 1)
            occ = occ - (1 - tb.part_frac if latest_calm == m else 0)
            occ = max(0.1, occ)
            rates.append(sales_by_month[m - 1] / occ)
        avg = sum(rates) / 12 if rates else 0
        raw = [1.0 if avg == 0 else r / avg for r in rates]
        if shrink_k and shrink_k > 0:
            damped = [1.0 + (raw[m] - 1.0) * (sales_by_month[m] / (sales_by_month[m] + shrink_k))
                      for m in range(12)]
            da = sum(damped) / 12
            out[model] = [d / da for d in damped] if da > 0 else damped
        else:
            out[model] = raw
    return out


# --------------------------------------------------------------------------- #
# Demo suppression (brief §14)
# --------------------------------------------------------------------------- #
def _is_demo(stock: str, demo_prefixes: list[str]) -> bool:
    """Prefix match — demo Stock#s are name-mangled (real stock# + driver name)."""
    return any(p and stock.startswith(p) for p in demo_prefixes)


# --------------------------------------------------------------------------- #
# Inventory position per config
# --------------------------------------------------------------------------- #
def _match_prev_loaner(u: InventoryUnit, prev_loaners):
    """Return the previous-loaner entry matching this unit's Stock#, or None."""
    for e in prev_loaners or []:
        st = str(e.get("stock", "")).strip()
        if st and u.stock.startswith(st):
            return e
    return None


def _iso(v):
    try:
        return _dt.date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _loaner_days_out(entry) -> int | None:
    """Days a loaner was OUT of sellable stock (taken -> returned) = the hidden
    demo period. Only this is subtracted from days-in-stock; the days the unit
    was publicly available before and after the demo still count as market time."""
    taken, returned = _iso(entry.get("taken")), _iso(entry.get("returned"))
    if taken and returned:
        return max(0, (returned - taken).days)
    return None


def compute_positions(inventory: list[InventoryUnit], metrics: dict, s: Settings,
                      today: _dt.date, loaner_prefixes: list | None = None) -> dict:
    loaner_prefixes = loaner_prefixes or []
    positions: dict[str, InvPosition] = {}
    for u in inventory:
        if not u.key:
            continue
        pos = positions.setdefault(u.key, InvPosition())
        demo = _is_demo(u.stock, s.demo_stocks)
        loaner = _is_demo(u.stock, loaner_prefixes)
        if u.is_dlr_inv:
            # A returned loaner is sellable again and takes precedence over a stale
            # demo-roster entry: marking a unit Returned always registers, even if
            # its demo row was left in place. (Its retail clock subtracts only the
            # hidden demo period taken->returned; a bare legacy `since` falls back
            # to today - since.)
            entry = _match_prev_loaner(u, s.prev_loaners)
            if entry is None and (demo or loaner):
                continue  # active demo / in-service loaner: out of sellable math
            if entry is not None:
                u.prev_loaner = True
                days_out = _loaner_days_out(entry)
                if days_out is not None:
                    u.retail_dis = max(0, u.dis - days_out)
                elif _iso(entry.get("since")):
                    u.retail_dis = max(0, (today - _iso(entry.get("since"))).days)
            pos.onlot += 1
            pos.onlot_units.append(u)
            if u.eff_dis >= s.stall_days:
                pos.stalled += 1
            if u.eff_dis > s.aged_days:
                pos.aged_units.append(u)
            met = metrics.get(u.key)
            dts = met.dts if (met and met.dts is not None) else 9999
            # Demos and previous demos are never wholesale-flagged — the miles
            # make them a different disposal, not a print-and-send wholesale unit.
            if u.eff_dis > max(s.wholesale_min_age, dts) and not u.prev_loaner:
                pos.wholesale_eligible.append(u)
        else:
            pos.inbound_total += 1
            if u.arrival_month:
                pos.arrivals[u.arrival_month] = pos.arrivals.get(u.arrival_month, 0) + 1
    return positions


# --------------------------------------------------------------------------- #
# Projection at arrival (brief §12)
# --------------------------------------------------------------------------- #
def _proj_rate(m: ConfigMetrics | None, dts: float | None, s: Settings) -> float:
    """Monthly draw-down rate for the CPO chain, capped at rate_cap/month."""
    prate_half = (m.prate / 2) if m else 0.0
    dts_rate = (30.4 / dts) if (m and m.r90 > 0 and dts and dts > 0) else 0.0
    return min(s.rate_cap, max(prate_half, dts_rate))


def compute_demo_returns(demo_units, s: Settings, today: _dt.date) -> dict:
    """When each active demo is expected to re-enter sellable inventory, as a
    month offset from the order month, keyed by config.

    Return timing = when the demo reaches the swap threshold (its age as a demo,
    from an explicit start date if known, else days-in-stock). A demo already
    past the threshold returns imminently (offset 0). Offsets before the order
    month collapse to 0 (it is back before the order lands).
    """
    returns: dict[str, list] = {}
    if not s.anticipate_demo_returns:
        return returns
    order_year = today.year if s.order_month >= today.month else today.year + 1
    order_start = _dt.date(order_year, s.order_month, 1)
    for u in demo_units:
        if not u.key:
            continue
        days_as_demo = u.dis
        for prefix, start in s.demo_starts.items():
            if prefix and u.stock.startswith(prefix):
                try:
                    days_as_demo = (today - _dt.date.fromisoformat(str(start))).days
                except ValueError:
                    pass
                break
        return_date = today + _dt.timedelta(days=max(0, s.swap_threshold - days_as_demo))
        offset = max(0, round((return_date - order_start).days / _DAYS_PER_MONTH))
        returns.setdefault(u.key, []).append(offset)
    return returns


_DAYS_PER_MONTH = 30.44


def _production_date(production_month):
    """Representative production date: the middle of the stated month.

    We only know the *month* a unit was built ('2026-03'), so mid-month (the
    15th) is the unbiased point estimate — using the 1st would systematically
    overstate every lead by ~half a month.
    """
    try:
        y, m = str(production_month).split("-")[:2]
        return _dt.date(int(y), int(m), 15)
    except (ValueError, AttributeError):
        return None


def _arrival_date(u, today: _dt.date):
    """The exact date a unit landed / will land, to the day where the data allows.

      * on-lot -> today minus days-in-stock (exact)
      * inbound with a real ETA date -> that date (exact)
      * inbound with only a month ('Month of August') -> the 15th of that month
    """
    if u.is_dlr_inv:
        return today - _dt.timedelta(days=round(u.dis))
    d = _parse_eta_full_date(u.eta)
    if d is not None:
        return d
    if u.arrival_month:
        year = today.year if u.arrival_month >= today.month else today.year + 1
        return _dt.date(year, u.arrival_month, 15)
    return None


def _parse_eta_full_date(eta):
    """Parse an ETA string to an exact date, or None if only a month is given."""
    if eta is None:
        return None
    s = re.sub(r"week of", "", str(eta), flags=re.I).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def compute_arrival_windows(inventory, today: _dt.date, s: Settings) -> dict:
    """Continuous, trend-weighted production->arrival lead per model, in months.

    Measured ONLY from units that have actually ARRIVED (on-lot):

      * on-lot units  -> (today - days-in-stock)      - (mid production month)

    Inbound units are intentionally excluded: their ETA is an estimate, and the
    units you add for a future window would otherwise perturb this measured lead,
    moving the seasonal target and the need for the very window you are fulfilling.
    Arrived-only keeps the window (and thus the target) independent of the orders
    being planned, so per-config need is monotonic in added inventory — adding a
    qualifying unit can only lower it. Samples are weighted by how recent each
    unit's production is, averaged, floored at min_cpo_window, and a model with no
    arrived units falls back to the default lead.
    """
    fallback = {"QX80": 3.0, "QX60": 2.0, "QX65": 2.0}
    out = {}
    for model in ("QX80", "QX60", "QX65"):
        wsum = lsum = 0.0
        for u in inventory:
            if u.model != model or not u.is_dlr_inv:   # arrived (on-lot) only
                continue
            prod = _production_date(u.production_month)
            arr = _arrival_date(u, today)
            if prod is None or arr is None:
                continue
            lead = (arr - prod).days / _DAYS_PER_MONTH
            if not (0 <= lead <= 12):
                continue
            months_since_prod = max(0.0, (today - prod).days / _DAYS_PER_MONTH)
            w = 0.5 ** (months_since_prod / max(0.5, s.lead_halflife))
            wsum += w
            lsum += w * lead
        if wsum == 0:
            out[model] = fallback[model]
        else:
            out[model] = max(s.min_cpo_window, lsum / wsum)   # BASE production->arrival (no order pad)
    return out


def resolve_windows(inventory, today, s: Settings) -> dict:
    """Per-model lead time, distinct per mode: MID-MONTH = today (0); PPO = the
    vehicle's own production->arrival lead (auto or manual); CPO = that lead PLUS
    the order->production lead (order_lead_pad)."""
    auto = compute_arrival_windows(inventory, today, s)
    pad = float(getattr(s, "order_lead_pad", 0.0) or 0.0)
    out = {}
    for model in ("QX80", "QX60", "QX65"):
        v = s.window_setting(model)
        if isinstance(v, str) and v.strip().lower() == "auto":
            base = auto[model]
        else:
            base = max(s.min_cpo_window, float(v))
        out[model] = 0.0 if s.mode == "MID-MONTH" else (base + pad if s.mode == "CPO" else base)
    return out


def _interp_seas(seas_model, om, offset):
    """Seasonality at a *continuous* arrival offset from the order month, so a
    fractional window between two months blends their multipliers instead of
    snapping onto one (peak) month."""
    lo = int(math.floor(offset))
    frac = offset - lo
    a = seas_model[(om - 1 + lo) % 12]
    b = seas_model[(om - 1 + lo + 1) % 12]
    return a + (b - a) * frac


def _proj_chain(model, pos, metric, seas, s: Settings, n=8, returns=()) -> list:
    """Forward sell-down chain proj_0..proj_n.

    Each month: sell down at the config's pace and that month's seasonality,
    never below the held floor (stalled units + demos that have come back), then
    add whatever lands that month (inbound pipeline + returning demos). proj_0
    swallows everything already back before the window opens so it isn't ordered
    twice. A returned demo joins the held floor -- used, higher-mileage stock
    that lingers rather than reselling at the config's fresh pace.
    """
    om = s.order_month
    rate = _proj_rate(metric, metric.dts if metric else None, s)

    def arrivals_at(offset):
        return pos.arrivals.get(((om - 1 + offset) % 12) + 1, 0)

    def demos_at(offset):
        return sum(1 for r in returns if r == offset)

    def demos_by(offset):     # returned and still held by this month
        return sum(1 for r in returns if r <= offset)

    later = sum(arrivals_at(k) for k in range(1, n + 1))
    proj = [pos.onlot + max(0, pos.inbound_total - later) + demos_at(0)]
    for k in range(1, n + 1):
        held = pos.stalled + demos_by(k)
        seas_m = seas[model][(om - 1 + (k - 1)) % 12]
        proj.append(max(held, proj[k - 1] - rate * seas_m) + arrivals_at(k) + demos_at(k))
    return proj


def _proj_at(chain, offset):
    """On-hand projection at a continuous month offset (linear between months)."""
    lo = int(math.floor(offset))
    if lo >= len(chain) - 1:
        return chain[-1]
    frac = offset - lo
    return chain[lo] + (chain[lo + 1] - chain[lo]) * frac


def project_at_arrival(model, pos, metric, seas, s: Settings, window, returns=()):
    """Return (projection_at_arrival, full proj chain) for a fractional window."""
    chain = _proj_chain(model, pos, metric, seas, s,
                        n=max(8, int(math.ceil(window)) + 1), returns=returns)
    # CPO and PPO both measure a FUTURE order against what you'll hold at arrival
    # (the window projection). MID-MONTH is the right-now dealer-trade snapshot:
    # what you could obtain/hold today, so it uses current on-hand + inbound.
    if s.mode == "MID-MONTH":
        proj = pos.onlot + pos.inbound_total + sum(1 for r in returns if r == 0)
        return xround(proj, 1), chain
    return xround(_proj_at(chain, window), 1), chain


# --------------------------------------------------------------------------- #
# Order lines
# --------------------------------------------------------------------------- #
def _base_for_order(key, metrics) -> tuple[int, bool]:
    """The critical not-found vs. error split (brief §13).

    Found in the engine  -> use the learned base (0 is allowed; never order off
                            a config the math zeroed out).
    Genuinely not found  -> base 1: a brand-new combination, stock one and watch.
    """
    m = metrics.get(key)
    if m is None:
        return 1, False
    return m.base, True


def _mom_factor(m: ConfigMetrics | None, dts: float | None, s: Settings) -> float:
    """Momentum-earned seasonality factor (brief §10), capped at 1.0."""
    r90 = m.r90 if m else 0
    r180 = m.r180 if m else 0
    accel = m.momentum == "ACCEL" if m else False
    if r90 >= 2 or accel:
        base = 1.0
    elif r90 == 1:
        base = 0.6
    elif r90 == 0 and r180 >= 2:
        base = 0.35
    elif r90 == 0 and r180 == 1:
        base = 0.25
    else:
        base = 0.15
    if dts is None:
        pen = 1.0
    elif dts > 90:
        pen = 0.6
    elif dts > 60:
        pen = 0.85
    else:
        pen = 1.0
    return min(1.0, base * pen)


def _matches(entry: dict, model, ext, interior, key) -> bool:
    """Match a suppress/demote entry; blank fields are wildcards."""
    if "key" in entry:
        return entry["key"] == key
    def ok(field_val, actual):
        fv = str(field_val or "").strip()
        return fv == "" or fv == actual
    code = key.split("|")[1] if "|" in key else ""
    has_criterion = any(str(entry.get(f, "")).strip() for f in ("model", "code", "ext", "int"))
    return has_criterion and ok(entry.get("model"), model) and ok(entry.get("code"), code) \
        and ok(entry.get("ext"), ext) and ok(entry.get("int"), interior)


def _suppressed(key, model, code, ext, interior, s: Settings, trim="") -> bool:
    """Discontinued / no-longer-orderable. The 'code' field takes either a model
    code (e.g. 8411 — one model year) or a trim/model NAME (e.g. PURE, or
    'QX60 PURE') which suppresses every matching config regardless of year code.
    Ext and Int are optional wildcards to narrow either kind."""
    import re
    from .keys import digits_only
    if code == "8461":  # hardcoded discontinued (brief §17)
        return True
    hay = f"{model or ''} {trim or ''}".upper()
    for e in s.suppress:
        raw = str(e.get("code", "")).strip()
        if not raw:
            continue
        ee = str(e.get("ext", "")).strip()
        ei = str(e.get("int", "")).strip()
        ext_ok = ee == "" or ee == ext
        int_ok = ei == "" or ei == interior
        ec = digits_only(raw)[:4]
        if ec:
            if ec == code and ext_ok and int_ok:
                return True
            continue
        toks = [t for t in re.sub(r"[^A-Z0-9 ]", " ", raw.upper()).split() if t and not t.isdigit()]
        if toks and all(t in hay for t in toks) and ext_ok and int_ok:
            return True
    return False


def _dts_band(dts) -> int:
    if dts is None:
        return 0
    if dts <= 20:
        return 4
    if dts <= 40:
        return 3
    if dts <= 70:
        return 2
    if dts <= 100:
        return 1
    return 0


def _priority(line_key, model, dts, momentum, need, proj, order_tgt, seas_arr,
              eff_demote, row_index) -> float:
    """Rank score — velocity/DTS + momentum + seasonality (brief §16).

    NEED>0 lines get a +1000 floor so a real need always outranks an option.
    Options (NEED=0) only score if steady/accel/on-cadence AND DTS<=90.
    """
    mom_band = {"ACCEL": 4, "steady": 2, "on cadence": 1}.get(momentum, 0)
    dts_band = _dts_band(dts)
    seas_band = 2 if seas_arr >= 1.3 else (1 if seas_arr >= 1 else 0)
    tiebreak = row_index / 100000.0
    if need > 0:
        proj_band = 4 if proj == 0 else (2 if proj < order_tgt else 0)
        return 1000 + dts_band + mom_band + proj_band + seas_band - 1000 * eff_demote - tiebreak
    if momentum in ("ACCEL", "steady", "on cadence") and (dts is not None and dts <= 90):
        return dts_band + mom_band + seas_band - 1000 * eff_demote - tiebreak
    return -1


def _buy_grade(momentum, mom_factor, need) -> str:
    """A quick read on order conviction (mirrors the workbook's badge column)."""
    if need <= 0:
        return ""
    if momentum == "ACCEL" or mom_factor >= 0.85:
        return "💚 STRONG"
    if mom_factor >= 0.35:
        return "🔵 STEADY"
    return "🟡 SPECULATIVE"


def build_lines(s, metrics, seas, positions, aged_brakes, override_map, windows,
                demo_returns) -> list:
    lines: list[OrderLine] = []
    for i, cfg in enumerate(s.effective_roster()):
        model, code, ext, interior = cfg["model"], cfg["code"], cfg["ext"], cfg["int"]
        key = f"{model}|{code}|{ext}|{interior}"
        metric = metrics.get(key)
        pos = positions.get(key, InvPosition())
        dts = metric.dts if metric else None

        base, found = _base_for_order(key, metrics)
        mf = _mom_factor(metric, dts, s)
        seas_order = seas[model][(s.order_month - 1) % 12]
        window = windows[model]   # already mode-resolved: CPO = base+pad, PPO = base, MID-MONTH = 0
        seas_arr = _interp_seas(seas[model], s.order_month, window)

        returns = demo_returns.get(key, [])
        proj_at_arr, chain = project_at_arrival(model, pos, metric, seas, s, window, returns)

        suppressed = _suppressed(key, model, code, ext, interior, s, cfg.get("trim", ""))
        demoted = any(_matches(e, model, ext, interior, key) for e in s.demote)
        r90 = metric.r90 if metric else 0
        eff_demote = demoted and r90 < s.prove_bar

        # Momentum-earned seasonal target, at the arrival month.
        need_floor = 0 if base == 0 else 1
        order_target = max(need_floor, xround(base * (1 + (seas_arr - 1) * mf)))
        # Raw seasonal target at the order month (for overstock comparison).
        overstock_target = max(need_floor, xround(base * seas_order))

        aged_brake = aged_brakes.get(key, 0)
        override_qty = override_map.get(key, 0)
        if suppressed or eff_demote:
            need = 0
        else:
            need = max(0, xround(order_target - proj_at_arr - aged_brake)) + override_qty

        # Overstock / wholesale-now (brief §15). Discontinued combos still
        # surface here — you can't reorder them, but you can move existing stock.
        rate = _proj_rate(metric, dts, s)
        excess = max(0, xround(pos.onlot + pos.inbound_total - 3 * rate - overstock_target))
        wholesale_now = min(excess, len(pos.wholesale_eligible))

        momentum = metric.momentum if metric else "dormant"
        # A discontinued combo is never an order suggestion (build or option) —
        # you cannot build it — even though its on-lot/inbound units still count.
        prio = -1 if suppressed else _priority(
            key, model, dts, momentum, need, proj_at_arr, order_target,
            seas_arr, eff_demote, i)

        # Six-month rolling plan. Each month shows the seasonal target, what
        # arrives, and what to order. Crucially this carries its OWN prior orders
        # forward: on-hand sells down at the config's seasonal pace, then takes in
        # scheduled inbound arrivals AND the units this plan already ordered, so a
        # later month only tops up the gap to target instead of re-ordering the
        # whole target every month (which otherwise multiplies a 6-month plan into
        # ~6x the real need and spikes on a seasonal peak).
        # Plan sell-down uses the config's actual monthly DEMAND pace (prate is
        # per 60 days -> /2 per month), NOT the projection's _proj_rate. The
        # latter takes max(pace, 30.4/DTS), and 30.4/DTS is retail *velocity*
        # (how fast one unit sells once on the lot), not how many sell per month.
        # For a fast-but-thin combo (DTS 7, two lifetime sales) that reads ~4/mo
        # of phantom demand, evaporating inventory every month and making the plan
        # re-order the full target repeatedly. Pace keeps carried units on hand.
        # The plan uses a center-weighted 3-month smoothing of the seasonal curve
        # (prev + 2*this + next)/4, so the ORDER cadence isn't a spike-and-coast:
        # you build ahead of a peak instead of dumping it all in the peak month and
        # ordering zero around it. (NEED / order-priority still uses the sharp
        # arrival-month curve; only this 6-month schedule is smoothed.)
        sm = seas[model]
        plan_seas = [(sm[(c - 1) % 12] + 2 * sm[c] + sm[(c + 1) % 12]) / 4.0 for c in range(12)]
        blocked = suppressed or eff_demote
        plan_rate = min(s.rate_cap, metric.prate / 2) if metric else 0.0
        onhand = float(pos.onlot)
        held = float(pos.stalled)
        monthly_plan = []
        for k in range(6):
            cal = (s.order_month - 1 + k) % 12
            seas_k = plan_seas[cal]
            arr = pos.arrivals.get(cal + 1, 0)
            onhand = max(held, onhand - plan_rate * seas_k) + arr
            tgt = max(need_floor, xround(base * seas_k))
            order_k = 0 if blocked else max(0, xround(tgt - onhand))
            if k == 0 and not blocked:
                order_k += override_qty
            onhand += order_k          # carry ordered units forward
            monthly_plan.append({"month": cal + 1, "tgt": tgt, "arr": arr, "ord": order_k})

        lines.append(OrderLine(
            model=model, code=code, ext=ext, interior=interior, trim=cfg.get("trim", ""),
            key=key, dts=dts, momentum=momentum,
            onlot=pos.onlot, inbound=pos.inbound_total, proj_at_arrival=proj_at_arr,
            base=base, found=found, mom_factor=mf,
            order_target=order_target, overstock_target=overstock_target, need=need,
            suppressed=suppressed, demoted=demoted, eff_demote=eff_demote,
            priority=prio, wholesale_now=wholesale_now,
            buy_grade=_buy_grade(momentum, mf, need), monthly_plan=monthly_plan,
            demo_returning=len(returns),
        ))
    return lines


def _find_orphans(sales, inventory, roster) -> list:
    roster_keys = {f"{c['model']}|{c['code']}|{c['ext']}|{c['int']}" for c in roster}
    seen: dict[str, int] = {}
    for s in sales:
        if s.first_vin and s.key and s.key not in roster_keys:
            seen[s.key] = seen.get(s.key, 0) + 1
    return sorted(({"key": k, "sales": v} for k, v in seen.items()),
                  key=lambda d: -d["sales"])


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(inventory, sales, settings: Settings, today: _dt.date | None = None) -> EngineResult:
    from . import loaner as _loaner
    today = today or _dt.date.today()
    tb = compute_time_base(sales, today)
    metrics = compute_metrics(sales, tb, settings, settings.effective_roster())
    seas = compute_seasonality(sales, tb, getattr(settings, "seasonality_shrink_k", 0.0))
    loaner_prefixes = _loaner.loaner_stock_prefixes(settings)
    positions = compute_positions(inventory, metrics, settings, today, loaner_prefixes)

    aged_brakes: dict[str, int] = {}
    for e in settings.aged_memory:
        if e.get("active", 1) in (1, True, "1"):
            aged_brakes[e["key"]] = aged_brakes.get(e["key"], 0) + 1
    override_map: dict[str, int] = {}
    for e in settings.overrides:
        override_map[e["key"]] = override_map.get(e["key"], 0) + int(e.get("qty", 0))

    windows = resolve_windows(inventory, today, settings)
    demo_units = [u for u in inventory
                  if u.is_dlr_inv and _is_demo(u.stock, settings.demo_stocks)
                  and _match_prev_loaner(u, settings.prev_loaners) is None]
    demo_returns = compute_demo_returns(demo_units, settings, today)
    lines = build_lines(settings, metrics, seas, positions, aged_brakes,
                        override_map, windows, demo_returns)
    orphans = _find_orphans(sales, inventory, settings.effective_roster())
    preowned = _loaner.compute_preowned(settings, metrics, inventory)

    return EngineResult(
        settings=settings, time=tb, metrics=metrics, seasonality=seas,
        positions=positions, lines=lines, demo_units=demo_units,
        inventory=inventory, sales=sales, orphans=orphans,
        arrival_windows=windows, preowned=preowned,
    )
