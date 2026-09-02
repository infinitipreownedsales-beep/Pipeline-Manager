"""Live wiring for the per-active-unit KEEP / PULL / SWAP decision.

Gathers each authoritative input from the EXISTING readers — never re-asking the operator for data that
already exists in inventory, Service Loaner, Program Inputs, historical used data, or governed policy — and
hands them to the incremental-from-now comparator (keep_pull_swap.compare_actions). Everything is classified:

  AUTHORITATIVE fact  — invoice (governed / inventory), in-service date, tenure, ICV/Velocity terms
  LEARNED estimate    — expected used sale price now / at the future exit, expected sell-time
  PLANNING assumption — daily-prorated write-down, process buffer, recon when governed-absent (=0, flagged)
  UNRESOLVED input    — anything missing; it GATES only the actions that depend on it, never the whole unit

Front-end gross only (no backend / F&I anywhere). Write-down counts once (embedded in adjusted basis). ICV
already earned is sunk/common; Velocity is contingent on meeting the 240-day deadline.
"""
from __future__ import annotations

import datetime as _dt
from statistics import median

from .sl_policy import SLPolicyStore
from .program_inputs import ProgramInputsStore
from .keep_pull_swap import compare_actions
from .sell_time import estimate_sell_time, latest_prudent_release

RESALE_WINDOW_GATE = 5        # minimum observed resales in an age window before a time-sensitive price is defensible


def _my_int(v):
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return int(d[:4]) if len(d) >= 4 else None


def _price_num(v):
    s = str(v if v is not None else "").replace(",", "").replace("$", "").strip()
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _age_months_at(model_year, sale_date):
    """Vehicle lifecycle AGE in whole months at a sale date = months from Jan 1 of its model year to the sale
    date. A continuous axis: two sales in the same integer model-year-age bucket but different months differ."""
    my = _my_int(model_year)
    if my is None:
        return None
    try:
        d = _dt.date.fromisoformat(str(sale_date)[:10])
    except (ValueError, TypeError):
        return None
    return (d.year - my) * 12 + (d.month - 1)


def _code_norm(v):
    """Governed physical-unit model code, normalized (upper-cased, trimmed) or None. A DMS model code (e.g.
    '84616') identifies the trim/model family of a physical unit — it is NOT decoded from VIN structure."""
    s = str(v or "").strip().upper()
    return s or None


def _msrp_maps(inv):
    """Authoritative-MSRP lookups over the physical-unit inventory/pipeline source: (model_code, model_year) ->
    median MSRP, and model_code -> median MSRP (a broader same-code fallback). MSRP is authoritative per physical
    unit and lives ONLY in the inventory/pipeline export (never in retail_history), so this is the single
    authoritative-MSRP source both for normalizing each historical sale into a retention ratio and for the
    current unit. Dealer Vehicle Cost / invoice is never read here — it belongs to the separate basis rail."""
    from collections import defaultdict
    by_code_my, by_code = defaultdict(list), defaultdict(list)
    for r in inv or ():
        code = _code_norm(r.get("model_code"))
        msrp = _price_num(r.get("msrp"))
        my = _my_int(r.get("model_year") or r.get("year") or r.get("my"))
        if code is None or msrp is None or msrp <= 0:
            continue
        by_code[code].append(msrp)
        if my is not None:
            by_code_my[(code, my)].append(msrp)
    return ({k: median(v) for k, v in by_code_my.items()},
            {k: median(v) for k, v in by_code.items()})


def _msrp_for(by_code_my, by_code, code, my):
    """Authoritative original MSRP for a governed (model_code, model_year): the (code, MY)-specific median when
    present, else the broader same-code median. Returns (msrp, basis) or (None, reason). Never manufactured and
    never pooled across materially different model codes."""
    if code is None:
        return None, "model code unresolved"
    if my is not None and (code, my) in by_code_my:
        return by_code_my[(code, my)], f"inventory MSRP for model code {code} MY{my}"
    if code in by_code:
        return by_code[code], f"inventory MSRP for model code {code} (all model years)"
    return None, f"no inventory MSRP for model code {code}"


def _retention_observations(rows, by_code_my, by_code, model):
    """Observed RETENTION points (age_in_months, retention, model_code) from the store's OWN historical retail
    sales, where retention = observed used selling price / authoritative original MSRP. Each sale's original MSRP
    is resolved from the physical-unit inventory source by that sale's own governed (model_code, model_year) —
    Original MSRP for each sale is taken, in order of authority: (1) the sale's OWN retained original MSRP (the
    Reynolds retail-history export carries it — the authoritative historical value, never reconstructed); (2)
    failing that, the inventory (model_code, model_year) MSRP median for that same governed identity. NO raw
    dollar price is ever pooled, and retail_history is never mutated. Sales with no resolvable authoritative MSRP
    are dropped honestly (never normalized by an invented number)."""
    from .preowned_evidence import _is_real_code
    model_u = (model or "").upper()
    # AUTHORITY (2): historical NEW-sale MSRP median by SAME REAL model code + model year, built from the NEW rows
    # in this same ledger (a NEW sale's MSRP is authoritative). Gated on _is_real_code, so a blank/special pseudo-
    # code (e.g. 'BLANK'/'TRUCK') NEVER creates an MSRP anchor. NEW rows are an original-MSRP SOURCE only here —
    # they never enter the used retention cohort itself.
    newsale = {}
    for r in rows or ():
        if r.get("_sale_kind") != "NEW":
            continue
        c = _code_norm(r.get("model_number") or r.get("model_code"))
        if not _is_real_code(c):
            continue
        cmy = _my_int(r.get("year"))
        m = _price_num(r.get("msrp"))
        if cmy is not None and m is not None and m > 0:
            newsale.setdefault((c, cmy), []).append(m)
    newsale_med = {k: median(v) for k, v in newsale.items()}
    out = []
    for r in rows or ():
        if (r.get("model") or "").upper() != model_u:
            continue
        if r.get("_sale_kind") == "NEW":                          # NEW never enters the used retention cohort
            continue
        price = _price_num(r.get("price"))
        am = _age_months_at(r.get("year"), r.get("sold_date"))
        code = _code_norm(r.get("model_number") or r.get("model_code"))
        my = _my_int(r.get("year"))
        if price is None or price <= 0 or am is None or not _is_real_code(code):
            continue                                              # blank/special code never builds a retention obs
        # Original MSRP for the retention denominator, in order of AUTHORITY — NEVER the USED row's own MSRP field
        # (in the combined Reynolds ledger a used row's MSRP is unreliable, often == its Vehicle Price):
        #   (1) exact-VIN historical NEW original MSRP (stamped `_orig_msrp` by the identity bridge); else
        #   (2) historical NEW-sale MSRP median for the SAME REAL model code + SAME model year; else
        #   (3) the governed inventory (model_code, model_year) MSRP median; else
        #   (4) drop the observation (never normalized by an unauthoritative number).
        msrp = _price_num(r.get("_orig_msrp"))                    # (1) exact-VIN original NEW MSRP
        if msrp is None or msrp <= 0:
            msrp = newsale_med.get((code, my))                    # (2) historical NEW-sale (real code, MY) median
        if msrp is None or msrp <= 0:
            msrp, _b = _msrp_for(by_code_my, by_code, code, my)   # (3) governed inventory (code, MY) anchor
        if msrp is None or msrp <= 0:
            continue                                              # (4) drop
        out.append((am, price / msrp, code))
    return out


def _retention_at(obs, target, want_code):
    """Median observed RETENTION at ~target age (months), with the governed evidence hierarchy:
      (1) same model_code as the current unit, in the tightest defensible age window;
      (2) else broader same-model retention (all codes — already MSRP-normalized, so trims are comparable);
      (3) else gate.
    Returns (retention, window, n, tier, confidence)."""
    tiers = []
    if want_code is not None:
        tiers.append(("same model code", [o for o in obs if o[2] == want_code]))
    tiers.append(("same model (MSRP-normalized)", obs))
    for tier, pool in tiers:
        for w in (2, 3, 4, 6):
            win = [ret for am, ret, _c in pool if target - w <= am <= target + w]
            if len(win) >= RESALE_WINDOW_GATE:
                conf = "moderate" if w <= 3 else "thin"
                return median(win), w, len(win), tier, conf
    return None, None, 0, None, "none"


def _unit_inventory_facts(inv, vin):
    """This physical unit's authoritative (MSRP, model_code) from the inventory/pipeline source, joined by the
    SAME governed VIN/Serial/Stock linkage used to resolve model year (full VIN <-> Serial/Stock# via value and
    last-8). The operator is never asked to type MSRP. Returns (msrp, model_code); either is None when the unit
    cannot be matched or the matches disagree (honest — a disagreeing code degrades to the broader model tier)."""
    from .preowned_evidence import _id_match_keys
    keys = _id_match_keys(vin)
    if not keys:
        return None, None
    msrps, codes = [], []
    for r in inv or ():
        if keys & _id_match_keys(r.get("vin"), r.get("serial"), r.get("stock_number")):
            m = _price_num(r.get("msrp"))
            if m is not None and m > 0:
                msrps.append(m)
            c = _code_norm(r.get("model_code"))
            if c is not None:
                codes.append(c)
    msrp = median(msrps) if msrps else None
    code = codes[0] if len(set(codes)) == 1 else None
    return msrp, code


def _price_observations(rows, model):
    """Observed used TRANSACTION points (age_in_months, used_selling_price, model_code) from the store's own
    retail sales ledger. `price` is the Reynolds 'Vehicle Price' — verified as the used retail SELLING price
    (a positive transaction price recorded above 'Vehicle Cost', the separate dealer-basis field, which is
    never read here). This is the raw material of the primary market rail: observed transaction price by age."""
    model_u = (model or "").upper()
    out = []
    for r in rows or ():
        if (r.get("model") or "").upper() != model_u:
            continue
        if r.get("_sale_kind") == "NEW":                     # USED-market rail: never price off a NEW delivery
            continue
        price = _price_num(r.get("price"))
        am = _age_months_at(r.get("year"), r.get("sold_date"))
        code = _code_norm(r.get("model_number") or r.get("model_code"))
        if price is None or price <= 0 or am is None or code is None:
            continue
        out.append((am, price, code))
    return out


def _code4(model, code):
    """The RAW first-four-digit configuration code for the used-market comparability tier: the DMS 5-digit code
    with only its 5th digit (the MODEL YEAR) dropped. This is the PURE `code4` reduction — deliberately NOT
    `normalize_code`, whose legacy PLANNING consolidations (QX60 8461→8481, QX80 834x→8381) are demand-cohort
    lineage rules that must NOT silently become used-market transaction comparability. Here 84617/84616/84615
    all reduce to 8461, but 84417→8441 stays separate, 848xx stays its own family, 834x does NOT fold into 8381,
    and 86-gen QX80 stays distinct from 83-gen. Returns None when no 4-digit code resolves. `model` is unused
    (kept for call-site stability); this raw reduction is intentionally model-agnostic."""
    if not code:
        return None
    try:
        from ..newinv.dms_identity import code4
        return code4(code) or None
    except Exception:   # noqa: BLE001 — identity availability must never break the market rail
        return None


def _observed_price_at(obs, target, want_code, model=""):
    """Median observed used TRANSACTION price at ~target age (months) for the SAME comparable, tightest defensible
    age window first. Governed code tiers, most specific first:
      (1) EXACT model code (the full DMS code) — trim- AND model-year-specific;
      (2) SAME RAW first-four-digit configuration across model years (the 5th DMS digit is model year) — so a
          current-model-year unit resolves against its own configuration's older used comparables at the same
          lifecycle age (the whole point of pricing by age). NO family consolidation: only the same raw 4-digit
          configuration is pooled (84617↔84616 via 8461; 84417/848xx/834x/86-gen stay separate);
      (3) EXPLICIT APPROVED MARKET-COMPARABILITY PREDECESSOR — when the configuration's DMS code CHANGED across
          model years (e.g. QX60 AUTOGRAPH AWD: 2026 = 84816/8481, 2027 = 84617/8461), the current config may
          borrow its predecessor's observed used-transaction evidence, but ONLY via an explicit governed
          relationship in loaner/market_lineage.py (same model + governed trim/drivetrain; direct one-hop; never
          demand/planning/package lineage, never normalize_code).
    Never widens the ±window or lowers the sample gate; never pools different configurations. Returns
    (dollars, window, n, (tier_label, code_shown)) or (None, None, 0, None)."""
    if want_code is None:
        return None, None, 0, None
    want4 = _code4(model, want_code)
    tiers = [("same model code", [o for o in obs if o[2] == want_code], want_code)]
    if want4 is not None:
        tiers.append(("same raw configuration code",
                      [o for o in obs if _code4(model, o[2]) == want4], want4))
        try:
            from .market_lineage import market_predecessors
            for pred4 in market_predecessors(model, want4):     # direct approved predecessors only (no chaining)
                tiers.append(("market-lineage predecessor",
                              [o for o in obs if _code4(model, o[2]) == pred4], f"{pred4} -> current {want4}"))
        except Exception:   # noqa: BLE001 — market-lineage availability must never break the rail
            pass
    for label, pool, code_shown in tiers:
        for w in (2, 3, 4, 6):
            win = [p for am, p, _c in pool if target - w <= am <= target + w]
            if len(win) >= RESALE_WINDOW_GATE:
                return median(win), w, len(win), (label, code_shown)
    return None, None, 0, None


# Market-comparability lineage is intentionally separate from demand/planning lineage.
_MARKET_PREDECESSOR = {
    "84617": ("84816",),  # 2027 QX60 AUTOGRAPH AWD <- 2026 QX60 AUTOGRAPH AWD
}

# Planning assumptions only. These are editable starting points, not historical fact.
SERVICE_LOANER_RECON_DEFAULTS = {
    "QX60": {"low": 500.0, "expected": 1000.0, "high": 1500.0},
    "QX65": {"low": 600.0, "expected": 1200.0, "high": 1800.0},
    "QX80": {"low": 750.0, "expected": 1500.0, "high": 2500.0},
}


def _recon_assumption(model, override=None, *, governed_expected=None):
    """The expected/low/high reconditioning planning band for a model. Precedence:
      1. a GOVERNED Program Input recon value (the authoritative business-approved expected recon $ — its band
         is derived proportionally from the model's default band so the sensitivity display stays consistent);
      2. a scenario what-if override dict (unchanged — never persisted);
      3. the explicit governed DEFAULT band for the model (labelled, surfaced in Proof — never silent intuition).
    The decision-material value is `expected`; `source` records which of the three supplied it."""
    m=(model or '').upper().strip()
    base=dict(SERVICE_LOANER_RECON_DEFAULTS.get(m, {"low": 750.0, "expected": 1250.0, "high": 2000.0}))
    source="governed default band (no recon recorded in Program Inputs)"
    if governed_expected is not None:
        try:
            e=float(governed_expected)
            if e >= 0:
                de=float(base["expected"]) or 1.0
                lo_r=float(base["low"])/de
                hi_r=float(base["high"])/de
                base={"low": round(e*lo_r, 2), "expected": e, "high": round(e*hi_r, 2)}
                source="governed Program Input (recon)"
        except Exception:
            pass
    if isinstance(override, dict):
        for k in ("low","expected","high"):
            try:
                v=float(override.get(k))
                if v >= 0:
                    base[k]=v
            except Exception:
                pass
        source="scenario what-if override"
    vals=sorted([base["low"],base["expected"],base["high"]])
    return {"low": vals[0], "expected": vals[1], "high": vals[2], "source": source}


def _recon_sensitivity(pre_recon_net, model, override=None):
    recon=_recon_assumption(model, override)
    pre=float(pre_recon_net)
    return {
        "recon_low": recon["low"],
        "recon_expected": recon["expected"],
        "recon_high": recon["high"],
        "net_low_recon": round(pre-recon["low"],2),
        "net_expected_recon": round(pre-recon["expected"],2),
        "net_high_recon": round(pre-recon["high"],2),
        "break_even_recon": round(max(pre,0.0),2),
    }



def _direct_comparable_price_at(observations, target_age, unit_code):
    # Thin direct USED-dollar comparable before broad-model retention.
    code = _code_norm(unit_code)
    if not code:
        return None

    exact = {code}
    code4 = {c for _am, _p, c in observations if c and code[:4] and str(c).startswith(code[:4])}
    pred = set(_MARKET_PREDECESSOR.get(code, ()))

    tiers = (
        ("exact full model code", exact),
        ("explicit market predecessor", pred),
        ("same raw code4", code4),
    )
    for label, allowed in tiers:
        if not allowed:
            continue
        for w in (2, 3, 4, 6):
            vals = [p for am, p, c in observations
                    if c in allowed and abs(am - target_age) <= w and p is not None and p > 0]
            if vals:
                vals = sorted(vals)
                n = len(vals)
                mid = n // 2
                med = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0
                shown = ",".join(sorted(allowed))
                return med, w, n, label, shown
    return None


def _market_price(retail_rows, inv, model, model_year, sale_date, unit_msrp, unit_code, market_cache=None):
    """Expected used SELLING PRICE for a SPECIFIC physical unit at a specific sale date, on the market/value rail
    only (dealer Vehicle Cost / invoice is never mixed in). Governed evidence hierarchy, most authoritative
    first:

      PRIMARY — observed transaction price -> later observed transaction price. The store's own recorded used
        SELLING dollars for the SAME governed comparable (model code / trim) at the sale's lifecycle age. This
        is a direct, empirically-observed price by age; because it is trim-specific it already differentiates
        units, with NO MSRP involved.
      SECONDARY (fallback) — when same-comparable transaction evidence is insufficient, borrow a broader
        same-model cohort's observed RETENTION (used price / authoritative original MSRP) and re-scale by THIS
        unit's own authoritative MSRP. MSRP is used ONLY here, as the fallback normalizer.
      else GATE — no defensible observed evidence (never manufactured).

    Returns (price, provenance, confidence)."""
    target = _age_months_at(model_year, sale_date)
    if target is None:
        return None, "model-year / sale-date unresolved — cannot place on the age curve", "none"
    model_u = (model or "").upper()

    # PRIMARY: observed used transaction dollars for the same governed comparable (exact model code first, then
    # the year-agnostic config code so a current-model-year unit matches its own config's older used sales).
    market_cache = market_cache if isinstance(market_cache, dict) else {}
    cache_key = ("price_obs", model_u)
    price_obs = market_cache.get(cache_key)
    if price_obs is None:
        price_obs = _price_observations(retail_rows, model)
        market_cache[cache_key] = price_obs
    dollars, w, n, tinfo = _observed_price_at(price_obs, target, unit_code, model_u)
    if dollars is not None:
        conf = "moderate" if w <= 3 else "thin"
        tier_label, code_shown = tinfo
        return (round(dollars, 2),
                f"{model_u} observed used transaction price median ${dollars:,.0f} at ~{target}mo age "
                f"(±{w}mo, n={n}, {tier_label} {code_shown})", conf)

    # THIN DIRECT-COMPARABLE FALLBACK: when the normal sample-gated primary rail is thin,
    # prefer actual observed USED selling dollars from the same governed configuration or explicit
    # market predecessor over broad-model MSRP-normalized retention.
    thin_direct = _direct_comparable_price_at(price_obs, target, unit_code)
    if thin_direct is not None:
        dollars, tw, tn, tier_label, code_shown = thin_direct
        return (round(dollars, 2),
                f"{model_u} direct observed USED comparable median ${dollars:,.0f} at ~{target}mo age "
                f"(+/-{tw}mo, n={tn}, {tier_label} {code_shown}; thin direct evidence outranks "
                "broad-model MSRP-normalized retention)", "thin")

    # REFERENCE ONLY â€” broad-model MSRP-normalized retention is NOT authoritative enough
    # to create a physical-unit Service-Loaner recommendation dollar. It can be useful as
    # contextual evidence, but when exact / governed comparable USED transaction evidence
    # above is insufficient, this unit must gate rather than manufacture a forecast from
    # a broader model cohort.

    return None, (f"insufficient {model_u} observed used-price evidence within ±6mo of ~{target}mo age "
                  "— gated (not manufactured)"), "none"


def _iso_today(clock):
    from ..clock import to_utc_iso
    return to_utc_iso(clock.now())[:10]


def _price_at_model_year_age(mi, age_years):
    """Expected used SELLING PRICE from the dealership's own AGE-SPECIFIC maturity evidence (median recorded
    price by model-year age at resale). Returns (price, basis_label, confidence).

    The evidence hierarchy PRESERVES age/depreciation behaviour and never collapses to a static all-model-years
    median (which would give materially-different units the same price and make future holding look favourable
    only because write-down lowers basis while a flat price stays constant):
      * exact maturity-age bin (populated) -> moderate;
      * else the NEAREST populated maturity-age bin (still age-specific, so now vs future differ by age) -> thin;
      * else GATE — no defensible age-aware curve exists (unknown model-year age gates here too)."""
    if mi is None:
        return None, "no model evidence", "none"
    if age_years is None:
        # Model-year age unknown (unit MY unresolved). Never price off a static all-MY median or the oldest
        # cohort — gate honestly so the decision is not driven by a flat, depreciation-blind number.
        return None, "model-year age unknown (unit model year unresolved) — no age-specific resale cohort", "none"
    bins = [b for b in (getattr(mi, "maturity", ()) or ()) if b.median_price is not None]
    label = "5+" if age_years >= 5 else str(max(0, int(age_years)))
    for b in bins:
        if b.label == label and not b.thin:
            return float(b.median_price), f"maturity age {label}", "moderate"
    near = _nearest_maturity_bin(bins, age_years)         # still age-specific -> preserves depreciation
    if near is not None:
        return float(near.median_price), f"nearest maturity age {near.label} (age {label} thin/absent)", "thin"
    return None, "no defensible age-specific resale evidence", "none"


def _bin_age(label):
    """Numeric model-year age for a maturity-bin label ('0','1',...,'5+' -> 0,1,...,5)."""
    d = "".join(ch for ch in str(label or "") if ch.isdigit())
    return int(d) if d else None


def _nearest_maturity_bin(bins, age_years):
    """The populated maturity bin whose model-year age is closest to `age_years` (ties -> the OLDER/lower-priced
    bin, the conservative resale side). Age-specific by construction, so it preserves depreciation across time."""
    cand = [(abs(_bin_age(b.label) - int(age_years)), -_bin_age(b.label), b)
            for b in bins if _bin_age(b.label) is not None]
    return min(cand)[2] if cand else None


def _authoritative_model_year_for_unit(unit, vin, retail_rows=None, inv=None):
    """Resolve MY only from explicit authoritative fields tied to the exact physical VIN.
    No VIN-character decoding and no model-code inference. Conflicts fail closed."""
    vals = []

    def _year(v):
        s = str(v or "").strip()
        if len(s) == 4 and s.isdigit() and 2000 <= int(s) <= 2100:
            return s
        return ""

    explicit = _year(getattr(unit, "model_year", "") or "")
    if explicit:
        return explicit, "service-loaner unit"

    vin_u = str(vin or "").strip().upper()
    if not vin_u:
        return "", "no VIN"

    for r in inv or ():
        rv = str(r.get("vin") or r.get("VIN") or "").strip().upper()
        if rv != vin_u:
            continue
        y = _year(r.get("year") or r.get("model_year") or r.get("my"))
        if y:
            vals.append((y, "exact VIN inventory history"))

    for r in retail_rows or ():
        rv = str(r.get("vin") or r.get("VIN") or "").strip().upper()
        if rv != vin_u:
            continue
        if str(r.get("_sale_kind") or "").upper() != "NEW":
            continue
        y = _year(r.get("year") or r.get("model_year") or r.get("my"))
        if y:
            vals.append((y, "exact VIN historical NEW sale"))

    years = sorted({y for y, _src in vals})
    if len(years) != 1:
        return "", ("conflicting exact-VIN model-year evidence" if len(years) > 1
                    else "no exact-VIN model-year evidence")
    year = years[0]
    sources = sorted({src for y, src in vals if y == year})
    return year, " + ".join(sources)



ACTIVE_LOANER_BROAD_MARKET_GATE = 8
ACTIVE_LOANER_BROAD_MARKET_MAX_SPREAD = 0.15


def _percentile(values, p):
    """Linear percentile without a third-party dependency."""
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * float(p)
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


def _same_my_used_market_band(retail_rows, model, model_year, sale_date, market_cache=None):
    """Bounded broad-market evidence for an active loaner with unknown configuration.

    This is intentionally narrower than a generic model fallback:
      * explicit NEW deliveries are never eligible;
      * model AND model-year must match;
      * price must be an observed USED selling price;
      * the first age window with at least 8 observations is used;
      * broad-market spread must stay <= 15% IQR/median.

    The result is an uncertainty band, not a claim that the physical unit is the
    median configuration. The decision layer must prove the same action at P25,
    P50 and P75 before it may use this fallback.
    """
    target = _age_months_at(model_year, sale_date)
    if target is None:
        return None
    model_u = str(model or "").strip().upper()
    my_s = str(model_year or "").strip()
    if not model_u or not my_s:
        return None

    cache = market_cache if isinstance(market_cache, dict) else {}
    key = ("active_loaner_broad_same_my_used", model_u, my_s)
    obs = cache.get(key)
    if obs is None:
        obs = []
        for r in retail_rows or ():
            if str(r.get("_sale_kind") or "").strip().upper() == "NEW":
                continue
            if str(r.get("model") or "").strip().upper() != model_u:
                continue
            ry = str(r.get("year") or r.get("model_year") or r.get("my") or "").strip()
            if ry != my_s:
                continue
            sold = str(r.get("sold_date") or r.get("sale_date") or "")[:10]
            age = _age_months_at(my_s, sold)
            price = _price_num(r.get("price"))
            if age is None or price is None or float(price) <= 0:
                continue
            obs.append((float(age), float(price), sold))
        cache[key] = obs

    for window in (2, 3, 4, 6):
        matched = [(p, sold) for age, p, sold in obs if abs(age - target) <= window]
        if len(matched) < ACTIVE_LOANER_BROAD_MARKET_GATE:
            continue
        prices = [p for p, _sold in matched]
        p25 = _percentile(prices, 0.25)
        p50 = _percentile(prices, 0.50)
        p75 = _percentile(prices, 0.75)
        if p50 is None or p50 <= 0:
            return None
        spread = (p75 - p25) / p50
        if spread > ACTIVE_LOANER_BROAD_MARKET_MAX_SPREAD:
            return None
        dates = sorted(sold for _p, sold in matched if sold)
        return {
            "target_age_months": int(target),
            "window_months": window,
            "n": len(matched),
            "p25": round(p25, 2),
            "p50": round(p50, 2),
            "p75": round(p75, 2),
            "iqr_to_median": round(spread, 4),
            "oldest_sale": dates[0] if dates else None,
            "latest_sale": dates[-1] if dates else None,
        }
    return None


def _paired_bounded_market(now_band, future_band):
    """P25->P25, P50->P50, P75->P75 with no unearned appreciation credit."""
    if not now_band or not future_band:
        return None
    out = {}
    for q in ("p25", "p50", "p75"):
        now_v = float(now_band[q])
        observed_future = float(future_band[q])
        out[q] = {
            "now": round(now_v, 2),
            "future_observed": round(observed_future, 2),
            "future_decision": round(min(now_v, observed_future), 2),
        }
    return out



def _velocity_mileage_constraint(last_checkout_mileage, mile_cap):
    """Resolve only what authoritative Last Checkout Mileage can prove."""
    if mile_cap is None:
        return {
            "status": "not_applicable",
            "mile_cap": None,
            "last_checkout_mileage": last_checkout_mileage,
            "release_due_now": False,
        }
    try:
        cap = int(mile_cap)
    except (TypeError, ValueError):
        return {
            "status": "unknown",
            "mile_cap": None,
            "last_checkout_mileage": last_checkout_mileage,
            "release_due_now": False,
        }
    if last_checkout_mileage is None:
        return {
            "status": "unknown",
            "mile_cap": cap,
            "last_checkout_mileage": None,
            "release_due_now": False,
        }
    try:
        miles = int(last_checkout_mileage)
    except (TypeError, ValueError):
        return {
            "status": "unknown",
            "mile_cap": cap,
            "last_checkout_mileage": None,
            "release_due_now": False,
        }
    if miles > cap:
        status = "breached"
        due = True
    elif miles == cap:
        status = "at_cap"
        due = True
    else:
        status = "within_cap"
        due = False
    return {
        "status": status,
        "mile_cap": cap,
        "last_checkout_mileage": miles,
        "release_due_now": due,
    }


def _market_horizon_dates(in_service, tenure_days_now, keep_horizon_days):
    """Market-value dates for PULL-now vs KEEP-until-release.

    Used-inventory sell time is intentionally NOT part of this clock. It is a
    separate empirical clock used to backsolve the latest prudent loaner release
    from the total-to-retail deadline. With zero remaining KEEP horizon, both
    actions must reference the same market date.
    """
    if not in_service or tenure_days_now is None:
        return None, None
    try:
        now = _dt.date.fromisoformat(str(in_service)[:10]) + _dt.timedelta(days=int(tenure_days_now))
        extra = max(0, int(keep_horizon_days or 0))
    except (ValueError, TypeError):
        return None, None
    return now.isoformat(), (now + _dt.timedelta(days=extra)).isoformat()


def build_unit_decision(app, scope, unit, mi, *, today=None, swap_candidate_net=None, keep_horizon_days=None, retail_rows=None, inv=None, market_cache=None):
    """Assemble the KEEP/PULL/SWAP decision for one active Service-Loaner `unit` (a UnitIntel) whose model
    evidence is `mi` (a ModelIntel). Reads governed policy + Program Inputs; forecasts the future exit price
    from maturity evidence. Returns {action, nets, components, missing, gated, confidence, why, facts}."""
    pol = SLPolicyStore(app.prefs, scope)
    pis = ProgramInputsStore(app.prefs, scope)
    today = today or _iso_today(app.stack.clock)
    vin = unit.vin
    model = (unit.model or "").upper()
    in_service = unit.in_service_date
    tenure_days_now = unit.age_days
    gated = []

    # Shared physical/history rows are needed before program-value resolution.
    if retail_rows is None:
        retail_rows = _retail_rows(app, scope)
    if inv is None:
        inv = _inventory_rows(app, scope)
    my, my_source = _authoritative_model_year_for_unit(unit, vin, retail_rows=retail_rows, inv=inv)
    if not my:
        gated.append("authoritative model year")

    # --- authoritative facts ---
    invoice = pol.invoice_for_vin(vin)
    if invoice is None:
        gated.append("authoritative invoice")
    if not in_service or tenure_days_now is None:
        gated.append("authoritative in-service date / tenure")
    in_month = in_service[:7] if in_service else None
    rate, rate_src = pol.writedown_monthly_rate(in_month)
    icv_e = pis.applicable("icv", model, in_month, model_year=my) if in_month else None
    vel_e = pis.applicable("velocity", model, in_month, model_year=my) if in_month else None
    icv = icv_e.value if icv_e else None
    velocity = vel_e.value if vel_e else None
    velocity_mile_cap = (vel_e.mile_cap if (vel_e and vel_e.mile_cap is not None) else None)
    observed_mileage = (unit.mileage if unit.mileage_available else None)
    velocity_mileage = _velocity_mileage_constraint(observed_mileage, velocity_mile_cap)
    mileage_release_due_now = bool(velocity_mileage["release_due_now"])
    total_to_retail = (vel_e.day_cap if (vel_e and vel_e.day_cap is not None) else 240)  # 240 = total-to-retail

    # --- learned estimates ---
    sell = estimate_sell_time(retail_rows, model=model, model_year=my, trim=None, drivetrain=None)
    sell_days = sell["days"] if sell else None
    buffer_days = pol.protection_buffer_days()
    release = latest_prudent_release(in_service_date=in_service, total_to_retail_days=total_to_retail,
                                     expected_sell_time_days=sell_days, process_buffer_days=buffer_days)
    # KEEP horizon: hold to the latest prudent release point (never beyond); 0 when already at/over it
    if keep_horizon_days is None:
        keep_horizon_days = 0
        if release:
            try:
                keep_horizon_days = max(0, (_dt.date.fromisoformat(release["release_by"])
                                            - _dt.date.fromisoformat(today)).days)
            except (ValueError, TypeError):
                keep_horizon_days = 0

    # --- time-sensitive market-value horizons ---
    # PULL is valued at the release-now market; KEEP is valued at the future
    # Service-Loaner release market. Historical used sell-time remains a separate
    # clock used only to protect the total-to-retail deadline. Never add sell-time
    # to the KEEP market horizon: with zero remaining hold, both dates must match.
    sale_now, sale_future = _market_horizon_dates(in_service, tenure_days_now, keep_horizon_days)
    # Market/value rail: resolve THIS unit's authoritative MSRP + model code from the already-loaded inventory /
    # pipeline physical-unit source (same governed VIN/Serial/Stock linkage used for MY — never a manual entry),
    # then price from OBSERVED RETENTION (used price / authoritative MSRP) applied to this unit's own MSRP.
    unit_msrp, unit_code = _unit_inventory_facts(inv, vin)
    if unit_msrp is None or unit_code is None:
        # VIN-lifecycle fallback: a Service Loaner has moved OUT of today's New-Retail snapshot, but its
        # authoritative MSRP + model code were retained when it was new inventory (the pipeline summary is a
        # per-business-date longitudinal-memory source). Recover them from any retained snapshot — never a
        # manual entry — so the unit is not gated merely for no longer being in the latest inventory export.
        lm, lc = _lifecycle_facts(app, scope, vin)
        unit_msrp = unit_msrp if unit_msrp is not None else lm
        unit_code = unit_code or lc
    price_now, pn_basis, pn_conf = _market_price(retail_rows, inv, model, my, sale_now, unit_msrp, unit_code,
                                                    market_cache=market_cache)
    price_future, pf_basis, pf_conf = _market_price(retail_rows, inv, model, my, sale_future, unit_msrp,
                                                    unit_code, market_cache=market_cache)
    if price_now is None:
        gated.append("expected used price now")
    if price_future is None:
        gated.append("expected future used price (KEEP)")

    # --- Velocity contingency: is the projected FINAL SALE within the 240-day deadline? ---

    # Active-loaner fallback for physical units whose exact configuration identity
    # cannot be recovered. Never changes the ADD rail: this is only inside the
    # current-fleet KEEP/PULL/SWAP decision.
    market_uncertainty = None
    bounded_pairs = None
    release_by = release.get("release_by") if isinstance(release, dict) else None
    release_due_now = bool(release_by and str(release_by) <= str(today))

    # Do not mix one direct comparable with one broad estimate. The bounded rail
    # is eligible only when BOTH direct prices are unresolved and this physical
    # unit has neither governed model-code nor governed MSRP identity.
    if (price_now is None and price_future is None
            and not unit_code and unit_msrp is None):
        now_band = _same_my_used_market_band(
            retail_rows, model, my, sale_now, market_cache=market_cache
        )
        future_band = _same_my_used_market_band(
            retail_rows, model, my, sale_future, market_cache=market_cache
        )
        bounded_pairs = _paired_bounded_market(now_band, future_band)
        if bounded_pairs:
            price_now = bounded_pairs["p50"]["now"]
            price_future = bounded_pairs["p50"]["future_decision"]
            pn_conf = pf_conf = "moderate"
            pn_basis = (
                f"{model} MY{my} broad same-MY USED market median ${price_now:,.0f} "
                f"at ~{now_band['target_age_months']}mo (±{now_band['window_months']}mo, "
                f"n={now_band['n']}, IQR/median={now_band['iqr_to_median']:.2f}); "
                "configuration unknown — action must survive P25/P50/P75"
            )
            observed_future = bounded_pairs["p50"]["future_observed"]
            cap_note = (
                "future cohort appreciation not credited"
                if observed_future > price_future else
                "observed future cohort used directly"
            )
            pf_basis = (
                f"{model} MY{my} broad same-MY USED future median observed "
                f"${observed_future:,.0f}; decision value ${price_future:,.0f} "
                f"at ~{future_band['target_age_months']}mo "
                f"(±{future_band['window_months']}mo, n={future_band['n']}); {cap_note}"
            )
            market_uncertainty = {
                "method": "paired same-model + same-MY USED P25/P50/P75",
                "now": now_band,
                "future": future_band,
                "paired": bounded_pairs,
                "future_appreciation_credit": False,
            }

    # The direct configuration-specific rail gated before this bounded fallback
    # was attempted. Once the bounded rail has supplied BOTH prices, those two
    # price-gate labels are stale and must be removed. Preserve every other gate.
    if bounded_pairs:
        gated = [
            g for g in gated
            if g not in (
                "expected used price now",
                "expected future used price (KEEP)",
            )
        ]

    def _within_deadline(extra_hold_days):
        if not in_service or sell_days is None or total_to_retail is None:
            return True                                     # unknown -> do not fabricate a forfeit
        return (tenure_days_now or 0) + extra_hold_days + sell_days <= total_to_retail
    vel_now = _within_deadline(0)
    vel_future = _within_deadline(keep_horizon_days)

    # Constraint-first Velocity eligibility. A known observed breach means the
    # bonus is already not protectable. At the exact cap, PULL may still preserve
    # eligibility now, but KEEP cannot consume another Service-Loaner mile.
    if velocity_mileage["status"] == "breached":
        vel_now = False
        vel_future = False
    elif velocity_mileage["status"] == "at_cap":
        vel_future = False

    # Same governed recon rail as ADD: the authoritative expected recon $ from Program Inputs (by model +
    # in-service month + model year), else the explicit governed default band. One recon source everywhere.
    _recon_e = pis.applicable("recon", model, in_month, model_year=my) if in_month else None
    _governed_recon = _recon_e.value if (_recon_e is not None and _recon_e.value is not None) else None
    recon_assumption = _recon_assumption(model, governed_expected=_governed_recon)
    recon = float(recon_assumption["expected"])

    res = compare_actions(invoice=invoice, monthly_rate=rate, tenure_days_now=tenure_days_now,
                          keep_extra_days=keep_horizon_days, used_price_now=price_now,
                          used_price_future=price_future, recon=recon, velocity_contingent=velocity or 0,
                          velocity_preserved_now=vel_now, velocity_preserved_future=vel_future,
                          icv_earned=icv or 0, swap_candidate_net=swap_candidate_net)


    # If the broad bounded rail was used, the median is not allowed to decide
    # alone. Re-run the exact same economics at persistent P25/P50/P75 ranks.
    robust_actions = None
    robust_results = None
    if bounded_pairs:
        robust_results = {}
        for q in ("p25", "p50", "p75"):
            pair = bounded_pairs[q]
            robust_results[q] = compare_actions(
                invoice=invoice, monthly_rate=rate, tenure_days_now=tenure_days_now,
                keep_extra_days=keep_horizon_days,
                used_price_now=pair["now"],
                used_price_future=pair["future_decision"],
                recon=recon,
                velocity_contingent=velocity or 0,
                velocity_preserved_now=vel_now,
                velocity_preserved_future=vel_future,
                icv_earned=icv or 0,
                swap_candidate_net=swap_candidate_net,
            )
        robust_actions = [robust_results[q]["best"] for q in ("p25", "p50", "p75")]
        res = robust_results["p50"]

    if mileage_release_due_now:
        action = "PULL"
    elif bounded_pairs and release_due_now:
        action = "PULL"
    elif bounded_pairs:
        stable = {a for a in robust_actions if a}
        if len(stable) == 1 and len(robust_actions) == 3 and all(robust_actions):
            action = next(iter(stable))
        else:
            action = "UNRESOLVED"
            gated.append(
                "unknown configuration changes KEEP/PULL outcome across observed "
                "same-model/model-year USED market range"
            )
    else:
        action = res["best"] or "UNRESOLVED"

    confidence = _confidence(pn_conf, pf_conf, gated)
    why = _why(action, res, vel_now, vel_future, keep_horizon_days, model, sell, gated)
    if mileage_release_due_now:
        miles = velocity_mileage["last_checkout_mileage"]
        cap = velocity_mileage["mile_cap"]
        mileage_word = "breached" if velocity_mileage["status"] == "breached" else "reached"
        timing_note = (
            f" Latest prudent release was also {release_by}."
            if release_due_now and release_by else ""
        )
        why = (
            f"PULL / RETIRE now — governed Velocity mileage cap {cap:,} has been "
            f"{mileage_word}; Last Checkout Mileage is {miles:,}. "
            "Because Last Checkout Mileage is not a live odometer, current actual "
            "mileage can only be equal or higher, never safely lower."
            f"{timing_note}"
        )
    elif bounded_pairs and release_due_now:
        why = (
            f"PULL / RETIRE now — latest prudent release was {release_by}. "
            "The remaining Service-Loaner hold is zero; timing control governs. "
            "Current used value is bounded by same-model/model-year USED evidence."
        )
    elif bounded_pairs and action != "UNRESOLVED":
        margins = {}
        for q, qr in robust_results.items():
            pull = qr["nets"].get("PULL")
            keep = qr["nets"].get("KEEP")
            margins[q] = (
                round(float(keep) - float(pull), 2)
                if pull is not None and keep is not None else None
            )
        why = (
            f"{action} is robust despite unknown configuration: the same action wins "
            f"at P25/P50/P75 of the observed same-MY USED market. "
            f"KEEP−PULL sensitivity {margins}."
        )
    elif bounded_pairs:
        why = (
            "Cannot recommend KEEP/PULL yet — unknown configuration changes the "
            "decision across P25/P50/P75 of the observed same-MY USED market."
        )
    facts = {"vin": vin, "model": model, "model_year": my, "model_year_source": my_source,
             "in_service": in_service,
             "tenure_days": tenure_days_now, "mileage": (unit.mileage if unit.mileage_available else None),
             "invoice": invoice, "rate": rate, "rate_src": rate_src, "icv": icv, "velocity": velocity,
             "velocity_mile_cap": velocity_mile_cap, "velocity_mileage": velocity_mileage,
             "total_to_retail_days": total_to_retail, "sell_time": sell, "release": release,
             "unit_msrp": unit_msrp, "unit_model_code": unit_code,
             "price_now": price_now, "price_now_basis": pn_basis, "price_future": price_future,
             "price_future_basis": pf_basis, "recon": recon}

    facts["market_uncertainty"] = market_uncertainty
    facts["release_due_now"] = release_due_now
    facts["robust_actions"] = robust_actions
    return {"action": action, "nets": res["nets"], "components": res["components"],
            "missing": res["missing"], "gated": gated, "confidence": confidence, "why": why, "facts": facts}


def _confidence(pn_conf, pf_conf, gated):
    if gated:
        return "gated"
    order = {"none": 0, "thin": 1, "moderate": 2, "strong": 3}
    return min((pn_conf, pf_conf), key=lambda c: order.get(c, 0))


def _why(action, res, vel_now, vel_future, keep_days, model, sell, gated):
    if action == "UNRESOLVED":
        return ("Cannot recommend an action yet — missing: " + ", ".join(gated) + ". The available facts are "
                "shown; supply the missing authoritative input to resolve.")
    c = res["components"]
    if action == "KEEP":
        base = (f"Keep this {model} in service: holding lowers its basis (more write-down) and the expected "
                f"exit gross improves to ${_n(c['front_end_gross_future'])} vs ${_n(c['front_end_gross_now'])} now")
        if not vel_future and vel_now:
            base += " even though keeping risks the Velocity deadline"
        return base + "."
    if action == "PULL":
        why = f"Pull this {model} now: releasing today yields the better total position (${_n(c['front_end_gross_now'])} front-end gross"
        if vel_now and not vel_future:
            why += "; keeping longer would forfeit Velocity"
        why += ")."
        return why
    if action == "SWAP":
        return (f"Swap: pull this {model} now and place the stronger New-Retail candidate into the slot — the "
                "combined dealership result beats keeping the current unit.")
    return ""


def _n(v):
    return "—" if v is None else f"{v:,.0f}"


def _retail_rows(app, scope):
    try:
        from .preowned_evidence import latest_retail_rows
        rows, _as_of = latest_retail_rows(app.stack.db.conn, scope)
        return rows
    except Exception:   # noqa: BLE001
        return []


def _inventory_rows(app, scope):
    """Raw per-unit inventory/pipeline rows (the authoritative physical-unit MSRP + model-code source). Never
    breaks the decision if inventory is unavailable — the market rail then gates honestly."""
    try:
        from .placement import read_new_retail_units
        return read_new_retail_units(app, scope) or []
    except Exception:   # noqa: BLE001
        return []


def _lifecycle_facts(app, scope, vin):
    """This unit's authoritative (MSRP, model_code) from the FULL inventory/pipeline lifecycle (every retained
    business-date snapshot), used when the unit has left today's latest New-Retail snapshot. Read-only; returns
    (None, None) if inventory is unavailable so the market rail still gates honestly."""
    try:
        from .preowned_evidence import inventory_lifecycle_facts
        return inventory_lifecycle_facts(app.stack.db.conn, scope, vin)
    except Exception:   # noqa: BLE001
        return None, None
