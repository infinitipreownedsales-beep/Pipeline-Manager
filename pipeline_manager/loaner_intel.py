"""Loaner Intelligence — a dealership depreciation & resale engine.

This module learns, from our OWN historical used-car sales, how Infiniti
vehicles hold value and sell after they come out of the service-loaner fleet.
Nothing here is hardcoded market lore; every number is discovered from the
data that is imported.

What the source data supports (and what it does not)
----------------------------------------------------
The 10-year export carries: sale date, stock #, model year, make, model, trim,
exterior color, VIN, days-to-sell, vehicle cost, selling price, gross. It does
NOT carry an odometer reading or an original MSRP, and interior color is empty.
So this engine models value retention on the **vehicle-age** axis (the standard
retention axis) rather than a mileage axis, measures resale price / gross /
velocity rather than %-off-sticker, and leaves clearly named hooks
(`age_months`, bucket edges) where a mileage feed can slot in later.

Age is approximated from the model year using a September model-year anchor:
    age_months = (sale_year - model_year) * 12 + (sale_month - 9), floored at 0.
That is an approximation, documented as such wherever it surfaces.

Recency weighting
-----------------
Every sale is weighted by 0.5 ** (months_ago / half_life) so recent market
behavior pulls the projections without throwing away the long history. The
half-life is configurable (default 24 months). Set it huge to weight all
history equally.

The engine is pure computation — no rendering. `analyze()` returns a plain
dict that the JS dashboard mirrors 1:1 and that the tests pin.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import math
from collections import defaultdict

# --------------------------------------------------------------------------- #
# Tunables (mirrored in the JS engine)
# --------------------------------------------------------------------------- #
DEFAULT_HALF_LIFE_MONTHS = 24.0
MODEL_YEAR_ANCHOR_MONTH = 9          # a MY is treated as starting in Sept
MIN_CELL_N = 5                       # below this a cell is "thin" (low confidence)
AGE_BUCKETS = [0, 6, 12, 18, 24, 36, 48, 60, 84]   # months; mileage hook goes here
LOANER_PREFIXES = ("LP", "LNP")
INFINITI_MODELS_ORDER = ["QX80", "QX60", "QX55", "QX50", "QX30", "Q50", "Q60",
                         "Q70", "Q70L", "QX70", "G37", "JX"]


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _money(x):
    if x is None:
        return None
    s = str(x).replace(",", "").replace("$", "").strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(x):
    try:
        return int(float(str(x).strip()))
    except (ValueError, TypeError):
        return None


def _norm(s):
    return str(s or "").strip().upper()


def _strip_suffix(stock):
    """LP21560A / LP21560B -> LP21560 : drop a trailing alpha lineage suffix."""
    s = _norm(stock)
    i = len(s)
    while i > 0 and s[i - 1].isalpha():
        i -= 1
    # keep the leading alpha prefix (LP/LNP/etc.) — only strip a *trailing* run
    # of letters that follows the digits
    return s[:i] if any(c.isdigit() for c in s[:i]) else s


def _is_loaner_stock(stock):
    s = _norm(stock)
    base = _strip_suffix(s)
    return s.startswith(LOANER_PREFIXES) or base.startswith(LOANER_PREFIXES)


def _make_family(make):
    """"BMW SAV" -> "BMW", "CHEVROLET TRUCK" -> "CHEVROLET"."""
    m = _norm(make)
    for tail in (" SAV", " SAC", " TRUCK", " VAN"):
        if m.endswith(tail):
            m = m[: -len(tail)]
    return m.strip()


def _model_norm(model):
    m = _norm(model)
    # collapse trailing body-style noise ("G37 SEDAN" -> "G37")
    return m.split()[0] if m else m


# Common single-token color abbreviations seen in the export. Only exact
# whole-string tokens are expanded — multi-word names (GLACIER WHITE,
# BLACK OBSIDIAN) are genuinely distinct colors and are left intact.
_COLOR_ABBR = {
    "WHT": "WHITE", "BLK": "BLACK", "GRY": "GRAY", "GREY": "GRAY", "SLV": "SILVER",
    "SIL": "SILVER", "BLU": "BLUE", "GRN": "GREEN", "GLD": "GOLD", "BRN": "BROWN",
    "CHR": "CHARCOAL", "CHAR": "CHARCOAL", "GRPH": "GRAPHITE", "OBS": "OBSIDIAN",
}


def _canon_color(color):
    c = _norm(color)
    return _COLOR_ABBR.get(c, c)


# INFINITI trim keywords, most-specific first, so "PURE FWD" (inventory) and
# "3.0T PURE" (history) both resolve to the PURE curve, "AUTOG" -> "AUTOGRAPH".
_TRIM_WORDS = ["AUTOGRAPH", "SENSORY", "ESSENTIAL", "SIGNATURE", "LIMITED",
               "PREMIUM", "LUXE", "PURE", "SPORT"]


def _trim_word(trim):
    t = _norm(trim).replace("AUTOG ", "AUTOGRAPH ")
    if t.strip() == "AUTOG":
        t = "AUTOGRAPH"
    for w in _TRIM_WORDS:
        if w in t:
            return w
    return ""


# --------------------------------------------------------------------------- #
# Record
# --------------------------------------------------------------------------- #
class Sale:
    __slots__ = ("date", "year", "month", "quarter", "stock", "vin", "model_year",
                 "make", "model", "trim", "ext", "cost", "price", "gross", "dts",
                 "age_months", "is_infiniti", "is_loaner", "weight")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def parse_rows(rows):
    """rows: list[dict] (csv.DictReader). Returns list[Sale] with loaner + age
    resolved. VIN continuity wins over stock heuristics for the loaner flag."""
    out = []
    loaner_vins = set()
    staged = []
    for r in rows:
        raw_date = str(r.get("Sales Date", "")).strip()
        if len(raw_date) < 8 or not raw_date[:8].isdigit():
            continue
        y, mo, d = int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])
        try:
            date = _dt.date(y, mo, max(1, d))
        except ValueError:
            continue
        vin = _norm(r.get("VIN"))
        stock = _norm(r.get("Stock Number"))
        my = _int(r.get("Year"))
        make = _make_family(r.get("Make"))
        model = _model_norm(r.get("Model"))
        age = None
        if my:
            age = max(0, (y - my) * 12 + (mo - MODEL_YEAR_ANCHOR_MONTH))
        loaner_stock = _is_loaner_stock(stock)
        if loaner_stock and vin:
            loaner_vins.add(vin)
        staged.append((r, date, y, mo, vin, stock, my, make, model, age, loaner_stock))
    for (r, date, y, mo, vin, stock, my, make, model, age, loaner_stock) in staged:
        is_loaner = loaner_stock or (vin in loaner_vins)
        out.append(Sale(
            date=date, year=y, month=mo, quarter=(mo - 1) // 3 + 1,
            stock=stock, vin=vin, model_year=my, make=make,
            model=model, trim=_norm(r.get("Trim")), ext=_canon_color(r.get("Exterior Color")),
            cost=_money(r.get("Vehicle Cost")), price=_money(r.get("Vehicle Price")),
            gross=_money(r.get("Gross Profit")), dts=_int(r.get("Days to Sell")),
            age_months=age, is_infiniti=make.startswith("INFINITI"),
            is_loaner=is_loaner, weight=1.0))
    return out


def load_csv(text):
    return parse_rows(list(csv.DictReader(io.StringIO(text))))


# --------------------------------------------------------------------------- #
# Weighted statistics
# --------------------------------------------------------------------------- #
def assign_weights(sales, half_life_months=DEFAULT_HALF_LIFE_MONTHS, as_of=None):
    """Exponential recency decay by whole months since the sale."""
    if not sales:
        return sales
    as_of = as_of or max(s.date for s in sales)
    hl = max(0.5, float(half_life_months))
    for s in sales:
        months_ago = max(0.0, (as_of.year - s.date.year) * 12 + (as_of.month - s.date.month))
        s.weight = 0.5 ** (months_ago / hl)
    return sales


def _wmean(pairs):
    """pairs: iterable of (value, weight) with value not None."""
    num = den = 0.0
    for v, w in pairs:
        if v is None:
            continue
        num += v * w
        den += w
    return (num / den) if den else None


def _wmedian(pairs):
    vals = [(v, w) for v, w in pairs if v is not None and w > 0]
    if not vals:
        return None
    vals.sort(key=lambda t: t[0])
    total = sum(w for _, w in vals)
    half = total / 2.0
    run = 0.0
    for v, w in vals:
        run += w
        if run >= half:
            return v
    return vals[-1][0]


def _wpct(pairs, p):
    vals = [(v, w) for v, w in pairs if v is not None and w > 0]
    if not vals:
        return None
    vals.sort(key=lambda t: t[0])
    total = sum(w for _, w in vals)
    thresh = total * p
    run = 0.0
    for v, w in vals:
        run += w
        if run >= thresh:
            return v
    return vals[-1][0]


def _cell(rows, field):
    """Weighted summary of one field over rows -> {median, mean, p25, p75, n, wn}."""
    pairs = [(getattr(r, field), r.weight) for r in rows if getattr(r, field) is not None]
    n = len(pairs)
    return {
        "median": _round(_wmedian(pairs)),
        "mean": _round(_wmean(pairs)),
        "p25": _round(_wpct(pairs, 0.25)),
        "p75": _round(_wpct(pairs, 0.75)),
        "n": n,
        "wn": round(sum(w for _, w in pairs), 2),
    }


def _round(x, nd=0):
    if x is None:
        return None
    return round(x, nd) if nd else round(x)


def _confidence(n):
    """0..1 confidence from effective sample size (saturating)."""
    if n <= 0:
        return 0.0
    return round(min(1.0, math.log10(n + 1) / math.log10(MIN_CELL_N * 6 + 1)), 3)


# --------------------------------------------------------------------------- #
# Analytics builders
# --------------------------------------------------------------------------- #
def _age_bucket(age):
    if age is None:
        return None
    b = AGE_BUCKETS[0]
    for edge in AGE_BUCKETS:
        if age >= edge:
            b = edge
        else:
            break
    return b


def _bucket_label(edge):
    if edge == 0:
        return "0–6mo"
    if edge < 24:
        return f"{edge}–{edge + 6}mo"
    yr = edge // 12
    return f"{yr}yr+" if edge >= 60 else f"{yr}yr"


def age_curves(infiniti, by_trim=False):
    """Value-retention curve per model (optionally per model+trim) on the age
    axis. Retention = price median at each bucket / price median at the youngest
    populated bucket (labeled — it is resale-relative, not MSRP-relative)."""
    groups = defaultdict(lambda: defaultdict(list))
    for s in infiniti:
        if s.price is None or s.age_months is None:
            continue
        key = (s.model, s.trim) if by_trim else (s.model,)
        groups[key][_age_bucket(s.age_months)].append(s)
    out = {}
    for key, buckets in groups.items():
        points = []
        for edge in AGE_BUCKETS:
            rows = buckets.get(edge)
            if not rows:
                continue
            pc = _cell(rows, "price")
            gc = _cell(rows, "gross")
            points.append({"age": edge, "label": _bucket_label(edge),
                           "price": pc["median"], "gross": gc["median"],
                           "dts": _cell(rows, "dts")["median"], "n": pc["n"]})
        if not points:
            continue
        base = next((p["price"] for p in points if p["price"]), None)
        # Monotone (non-increasing) price envelope: real depreciation doesn't
        # rise with age; upticks are thin-sample noise. Running-min from the
        # youngest bucket gives a clean curve the predictor can lean on, while
        # the raw median stays visible for honesty.
        run = None
        for p in points:
            if p["price"] is not None:
                run = p["price"] if run is None else min(run, p["price"])
            p["price_smooth"] = run
            p["retention"] = round(p["price"] / base, 3) if base and p["price"] else None
            p["retention_smooth"] = round(run / base, 3) if base and run else None
        name = key[0] if len(key) == 1 else f"{key[0]} {key[1]}"
        out["|".join(str(k) for k in key)] = {"model": key[0], "label": name,
                                              "points": points, "base_price": base}
    return out


def color_analytics(infiniti, min_n=MIN_CELL_N):
    """Per model, exterior-color resale performance and premium vs the model's
    own weighted baseline. Interior color is unavailable in the source."""
    by_model = defaultdict(list)
    for s in infiniti:
        if s.ext:
            by_model[s.model].append(s)
    out = {}
    for model, rows in by_model.items():
        base_price = _wmean([(r.price, r.weight) for r in rows])
        base_gross = _wmean([(r.gross, r.weight) for r in rows])
        base_dts = _wmean([(r.dts, r.weight) for r in rows])
        colors = defaultdict(list)
        for r in rows:
            colors[r.ext].append(r)
        items = []
        for color, crows in colors.items():
            pc, gc, dc = _cell(crows, "price"), _cell(crows, "gross"), _cell(crows, "dts")
            if pc["n"] < min_n:
                continue
            items.append({
                "color": color, "n": pc["n"], "price": pc["median"], "gross": gc["median"],
                "dts": dc["median"],
                "price_prem": _round(pc["mean"] - base_price) if (pc["mean"] and base_price) else None,
                "gross_prem": _round(gc["mean"] - base_gross) if (gc["mean"] and base_gross) else None,
                "dts_delta": _round(dc["mean"] - base_dts) if (dc["mean"] and base_dts) else None,
                "conf": _confidence(pc["n"]),
            })
        items.sort(key=lambda x: (x["gross_prem"] is None, -(x["gross_prem"] or 0)))
        if items:
            out[model] = {"baseline": {"price": _round(base_price), "gross": _round(base_gross),
                                       "dts": _round(base_dts)}, "colors": items}
    return out


def trim_analytics(infiniti, min_n=MIN_CELL_N):
    by_model = defaultdict(lambda: defaultdict(list))
    for s in infiniti:
        if s.trim:
            by_model[s.model][s.trim].append(s)
    out = {}
    for model, trims in by_model.items():
        items = []
        for trim, rows in trims.items():
            pc, gc, dc = _cell(rows, "price"), _cell(rows, "gross"), _cell(rows, "dts")
            ac = _cell(rows, "age_months")
            if pc["n"] < min_n:
                continue
            items.append({"trim": trim, "n": pc["n"], "price": pc["median"],
                          "gross": gc["median"], "dts": dc["median"],
                          "avg_age_mo": ac["median"], "conf": _confidence(pc["n"])})
        items.sort(key=lambda x: (x["gross"] is None, -(x["gross"] or 0)))
        if items:
            out[model] = items
    return out


def model_performance(infiniti, benchmark_all):
    """Rank Infiniti models; compare gross & velocity to the whole-store mean."""
    store_gross = _wmean([(s.gross, s.weight) for s in benchmark_all])
    store_dts = _wmean([(s.dts, s.weight) for s in benchmark_all])
    by_model = defaultdict(list)
    for s in infiniti:
        by_model[s.model].append(s)
    items = []
    for model, rows in by_model.items():
        pc, gc, dc = _cell(rows, "price"), _cell(rows, "gross"), _cell(rows, "dts")
        loaner_n = sum(1 for r in rows if r.is_loaner)
        items.append({
            "model": model, "n": pc["n"], "loaner_n": loaner_n,
            "price": pc["median"], "gross": gc["median"], "dts": dc["median"],
            "gross_vs_store": _round(gc["mean"] - store_gross) if (gc["mean"] and store_gross) else None,
            "dts_vs_store": _round(dc["mean"] - store_dts) if (dc["mean"] and store_dts) else None,
            "conf": _confidence(pc["n"]),
        })
    order = {m: i for i, m in enumerate(INFINITI_MODELS_ORDER)}
    items.sort(key=lambda x: order.get(x["model"], 99))
    return {"store": {"gross": _round(store_gross), "dts": _round(store_dts)}, "models": items}


def seasonality(infiniti):
    """Monthly & quarterly resale index vs the annual weighted mean."""
    ann_price = _wmean([(s.price, s.weight) for s in infiniti])
    ann_gross = _wmean([(s.gross, s.weight) for s in infiniti])
    months, quarters = [], []
    by_m = defaultdict(list)
    by_q = defaultdict(list)
    for s in infiniti:
        by_m[s.month].append(s)
        by_q[s.quarter].append(s)
    for m in range(1, 13):
        rows = by_m.get(m, [])
        pc, gc, dc = _cell(rows, "price"), _cell(rows, "gross"), _cell(rows, "dts")
        pm = _wmean([(r.price, r.weight) for r in rows])
        months.append({"month": m, "n": pc["n"], "gross": gc["median"], "dts": dc["median"],
                       "price_index": round(pm / ann_price, 3) if (pm and ann_price) else None,
                       "wn": pc["wn"]})
    for q in range(1, 5):
        rows = by_q.get(q, [])
        gc = _cell(rows, "gross")
        qm = _wmean([(r.price, r.weight) for r in rows])
        quarters.append({"quarter": q, "n": gc["n"], "gross": gc["median"],
                         "price_index": round(qm / ann_price, 3) if (qm and ann_price) else None})
    return {"annual_price": _round(ann_price), "annual_gross": _round(ann_gross),
            "months": months, "quarters": quarters}


def loaner_vs_retail(infiniti):
    """The headline: how do out-of-service loaners resell vs ordinary used
    Infiniti — overall and per model — on gross, price, velocity, and age."""
    def summ(rows):
        pc, gc, dc, ac = (_cell(rows, "price"), _cell(rows, "gross"),
                          _cell(rows, "dts"), _cell(rows, "age_months"))
        return {"n": pc["n"], "price": pc["median"], "gross": gc["median"],
                "dts": dc["median"], "avg_age_mo": ac["median"]}
    loan = [s for s in infiniti if s.is_loaner]
    ret = [s for s in infiniti if not s.is_loaner]
    per_model = {}
    models = sorted({s.model for s in loan}, key=lambda m: -sum(1 for s in loan if s.model == m))
    for m in models:
        lm = [s for s in loan if s.model == m]
        rm = [s for s in ret if s.model == m]
        if len(lm) < MIN_CELL_N:
            continue
        per_model[m] = {"loaner": summ(lm), "retail": summ(rm)}
    return {"overall": {"loaner": summ(loan), "retail": summ(ret)},
            "per_model": per_model, "loaner_total": len(loan)}


# --------------------------------------------------------------------------- #
# Predictive estimator
# --------------------------------------------------------------------------- #
def _factor(sub_mean, base_mean, lo=0.75, hi=1.35):
    if not sub_mean or not base_mean:
        return 1.0
    return max(lo, min(hi, sub_mean / base_mean))


def build_predictor(infiniti):
    """Return a closure predicting resale for a spec. Transparent: an age-curve
    base for the model (+trim when it has support), nudged by a color factor and
    a seasonal factor, all discovered & recency-weighted. Confidence follows the
    effective sample behind the estimate."""
    curves_model = age_curves(infiniti, by_trim=False)
    curves_trim = age_curves(infiniti, by_trim=True)
    colors = color_analytics(infiniti, min_n=3)
    seas = seasonality(infiniti)
    model_base_price = {}
    for m in {s.model for s in infiniti}:
        rows = [s for s in infiniti if s.model == m]
        model_base_price[m] = _wmean([(r.price, r.weight) for r in rows])
    # best trim curve per model + trim keyword, so inventory trims ("PURE FWD")
    # resolve to the history curve ("PURE") instead of silently falling to model
    trim_by_model: dict = {}
    for key, c in curves_trim.items():
        model, _, trimstr = key.partition("|")
        tw = _trim_word(trimstr)
        if not tw:
            continue
        n = sum(p["n"] for p in c["points"])
        cur = trim_by_model.setdefault(model, {}).get(tw)
        if cur is None or n > cur[1]:
            trim_by_model[model][tw] = (key, n)

    def _resolve_trim_key(model, trim):
        tw = _trim_word(trim)
        hit = trim_by_model.get(model, {}).get(tw)
        return hit[0] if hit else f"{model}|{trim}"

    def _curve_value(curve_key, age, field="price"):
        c = (curves_trim if "|" in curve_key and curve_key.split("|")[1] else
             curves_model).get(curve_key)
        if not c or not c["points"]:
            return None, 0
        bucket = _age_bucket(age if age is not None else 6)
        pts = c["points"]
        # prefer the monotone-smoothed price so predictions never rise with age
        fld = "price_smooth" if field == "price" else field
        exact = next((p for p in pts if p["age"] == bucket), None)
        if exact and exact.get(fld) is not None:
            return exact[fld], exact["n"]
        # nearest populated bucket
        best = min(pts, key=lambda p: abs(p["age"] - bucket))
        return best.get(fld), best["n"]

    def predict(model, trim=None, model_year=None, color=None, month=None,
                age_months=None, as_of_year=None):
        model = _model_norm(model)
        trim = _norm(trim) if trim else ""
        color = _canon_color(color) if color else ""
        if age_months is None and model_year and as_of_year:
            age_months = max(0, (as_of_year - model_year) * 12 +
                             ((month or MODEL_YEAR_ANCHOR_MONTH) - MODEL_YEAR_ANCHOR_MONTH))
        # base value: prefer the resolved trim curve, fall back to model curve
        val = n = None
        tkey = _resolve_trim_key(model, trim) if trim else None
        if tkey:
            val, n = _curve_value(tkey, age_months, "price")
        if not val:
            val, n = _curve_value(model, age_months, "price")
            tkey = None
        if not val:
            return {"ok": False, "reason": "no comparable history for this model"}
        gkey = tkey or model
        gross, _ = _curve_value(gkey, age_months, "gross")
        dts, _ = _curve_value(gkey, age_months, "dts")
        # color factor
        cfac = 1.0
        if color and model in colors:
            crow = next((c for c in colors[model]["colors"] if c["color"] == color), None)
            base = colors[model]["baseline"]["price"]
            if crow and crow.get("price") and base:
                cfac = _factor(crow["price"], base)
        # seasonal factor
        sfac = 1.0
        if month:
            mrow = seas["months"][month - 1]
            if mrow.get("price_index"):
                sfac = max(0.9, min(1.1, mrow["price_index"]))
        price = round(val * cfac * sfac)
        conf = _confidence(n or 0)
        # widen the band when we leaned on factors / thin cells
        spread = 0.06 + 0.14 * (1 - conf)
        return {"ok": True, "price": price,
                "price_low": round(price * (1 - spread)), "price_high": round(price * (1 + spread)),
                "gross": _round(gross), "dts": _round(dts),
                "color_factor": round(cfac, 3), "season_factor": round(sfac, 3),
                "n": n, "confidence": conf}

    return predict


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #
def analyze(sales, half_life_months=DEFAULT_HALF_LIFE_MONTHS, as_of=None):
    """Full analysis dict. `sales` is the parsed list from load_csv/parse_rows."""
    assign_weights(sales, half_life_months, as_of)
    infiniti = [s for s in sales if s.is_infiniti]
    as_of = as_of or (max((s.date for s in sales), default=_dt.date.today()))
    predictor = build_predictor(infiniti)
    makes = defaultdict(list)
    for s in sales:
        makes[s.make].append(s)
    bench = sorted(({"make": mk, **{k: _cell(rows, f)[k2] for f, k, k2 in
                                    [("gross", "gross", "median"), ("dts", "dts", "median"),
                                     ("price", "price", "median")]}, "n": len(rows)}
                    for mk, rows in makes.items()), key=lambda x: -x["n"])[:10]
    return {
        "meta": {
            "rows": len(sales), "infiniti_rows": len(infiniti),
            "loaner_rows": sum(1 for s in infiniti if s.is_loaner),
            "date_min": min((s.date for s in sales), default=None),
            "date_max": max((s.date for s in sales), default=None),
            "as_of": as_of, "half_life_months": half_life_months,
            "age_axis": True, "mileage_axis": False,
            "note": "Retention is modeled on vehicle age (no odometer in source); "
                    "age approximated from model year with a Sept anchor.",
        },
        "age_curves": age_curves(infiniti, by_trim=False),
        "age_curves_trim": age_curves(infiniti, by_trim=True),
        "color": color_analytics(infiniti),
        "trim": trim_analytics(infiniti),
        "model_perf": model_performance(infiniti, sales),
        "seasonality": seasonality(infiniti),
        "loaner_vs_retail": loaner_vs_retail(infiniti),
        "benchmark": bench,
        "_predictor": predictor,   # callable; not JSON-serialized
    }
