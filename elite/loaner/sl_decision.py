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


def _recon_assumption(model, override=None):
    m=(model or '').upper().strip()
    base=dict(SERVICE_LOANER_RECON_DEFAULTS.get(m, {"low": 750.0, "expected": 1250.0, "high": 2000.0}))
    if isinstance(override, dict):
        for k in ("low","expected","high"):
            try:
                v=float(override.get(k))
                if v >= 0:
                    base[k]=v
            except Exception:
                pass
    vals=sorted([base["low"],base["expected"],base["high"]])
    return {"low": vals[0], "expected": vals[1], "high": vals[2]}


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


def _market_price(retail_rows, inv, model, model_year, sale_date, unit_msrp, unit_code):
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
    price_obs = _price_observations(retail_rows, model)
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


def build_unit_decision(app, scope, unit, mi, *, today=None, swap_candidate_net=None, keep_horizon_days=None):
    """Assemble the KEEP/PULL/SWAP decision for one active Service-Loaner `unit` (a UnitIntel) whose model
    evidence is `mi` (a ModelIntel). Reads governed policy + Program Inputs; forecasts the future exit price
    from maturity evidence. Returns {action, nets, components, missing, gated, confidence, why, facts}."""
    pol = SLPolicyStore(app.prefs, scope)
    pis = ProgramInputsStore(app.prefs, scope)
    today = today or _iso_today(app.stack.clock)
    vin = unit.vin
    model = (unit.model or "").upper()
    my = getattr(unit, "model_year", "") or ""
    in_service = unit.in_service_date
    tenure_days_now = unit.age_days
    gated = []

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
    total_to_retail = (vel_e.day_cap if (vel_e and vel_e.day_cap is not None) else 240)  # 240 = total-to-retail

    # --- learned estimates ---
    retail_rows = _retail_rows(app, scope)
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

    # --- forward exit prices (front-end) from the TIME-SENSITIVE observed resale curve ---
    # price is a function of the actual SALE DATE (continuous age-in-months), so holding to a later date yields a
    # different empirical price even when both dates fall in the same integer model-year-age bucket. This prevents
    # KEEP looking superior merely because write-down lowers basis while a flat resale price stays constant.
    def _exit_date(days_from_in_service):
        if not in_service:
            return None
        try:
            return (_dt.date.fromisoformat(in_service[:10])
                    + _dt.timedelta(days=int(days_from_in_service))).isoformat()
        except (ValueError, TypeError):
            return None
    sale_now = _exit_date(tenure_days_now or 0)
    sale_future = _exit_date((tenure_days_now or 0) + keep_horizon_days + (sell_days or 0))
    # Market/value rail: resolve THIS unit's authoritative MSRP + model code from the already-loaded inventory /
    # pipeline physical-unit source (same governed VIN/Serial/Stock linkage used for MY — never a manual entry),
    # then price from OBSERVED RETENTION (used price / authoritative MSRP) applied to this unit's own MSRP.
    inv = _inventory_rows(app, scope)
    unit_msrp, unit_code = _unit_inventory_facts(inv, vin)
    if unit_msrp is None or unit_code is None:
        # VIN-lifecycle fallback: a Service Loaner has moved OUT of today's New-Retail snapshot, but its
        # authoritative MSRP + model code were retained when it was new inventory (the pipeline summary is a
        # per-business-date longitudinal-memory source). Recover them from any retained snapshot — never a
        # manual entry — so the unit is not gated merely for no longer being in the latest inventory export.
        lm, lc = _lifecycle_facts(app, scope, vin)
        unit_msrp = unit_msrp if unit_msrp is not None else lm
        unit_code = unit_code or lc
    price_now, pn_basis, pn_conf = _market_price(retail_rows, inv, model, my, sale_now, unit_msrp, unit_code)
    price_future, pf_basis, pf_conf = _market_price(retail_rows, inv, model, my, sale_future, unit_msrp,
                                                    unit_code)
    if price_now is None:
        gated.append("expected used price now")
    if price_future is None:
        gated.append("expected future used price (KEEP)")

    # --- Velocity contingency: is the projected FINAL SALE within the 240-day deadline? ---
    def _within_deadline(extra_hold_days):
        if not in_service or sell_days is None or total_to_retail is None:
            return True                                     # unknown -> do not fabricate a forfeit
        return (tenure_days_now or 0) + extra_hold_days + sell_days <= total_to_retail
    vel_now = _within_deadline(0)
    vel_future = _within_deadline(keep_horizon_days)

    recon = 0                                               # governed recon not modelled yet -> 0 (planning), flagged

    res = compare_actions(invoice=invoice, monthly_rate=rate, tenure_days_now=tenure_days_now,
                          keep_extra_days=keep_horizon_days, used_price_now=price_now,
                          used_price_future=price_future, recon=recon, velocity_contingent=velocity or 0,
                          velocity_preserved_now=vel_now, velocity_preserved_future=vel_future,
                          icv_earned=icv or 0, swap_candidate_net=swap_candidate_net)

    action = res["best"] or "UNRESOLVED"
    confidence = _confidence(pn_conf, pf_conf, gated)
    why = _why(action, res, vel_now, vel_future, keep_horizon_days, model, sell, gated)
    facts = {"vin": vin, "model": model, "model_year": my, "in_service": in_service,
             "tenure_days": tenure_days_now, "mileage": (unit.mileage if unit.mileage_available else None),
             "invoice": invoice, "rate": rate, "rate_src": rate_src, "icv": icv, "velocity": velocity,
             "total_to_retail_days": total_to_retail, "sell_time": sell, "release": release,
             "unit_msrp": unit_msrp, "unit_model_code": unit_code,
             "price_now": price_now, "price_now_basis": pn_basis, "price_future": price_future,
             "price_future_basis": pf_basis, "recon": recon}
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
