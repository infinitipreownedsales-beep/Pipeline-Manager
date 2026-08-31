"""Service Loaner Intelligence Layer (A + B) — READ ONLY.

A: authoritative operational visibility Elite already possesses (active unit / model / in-service age /
   available mileage / membership+rental state / current & desired fleet / historical turn / sample depth).
B: source-backed empirical evidence from retail_history v3 (recorded resale distribution, recorded gross
   distribution, model-year-maturity-at-resale bins, model/model-year what-if, factor-based evidence quality).

Hard boundary (Phase-4 / C-class gated — none of this is produced here): no ICV / Velocity / write-down /
opportunity-cost, no RETIRE / HOLD / release-by / cascade, no Ideal-Mix determination, no acquisition
recommendation, no loaner-vs-ordinary claim, no trim precision, no former-loaner inference. Ideal stays
Undetermined. Every estimate exposes cohort / n / as-of / observation recency; below-gate samples are
disclosed as Thin and never drive a headline. `sold_date.year - model_year` is model-year age at resale
(maturity), NOT time-in-service; invalid maturity observations are excluded from the analytical cohort with
an explicit count.
"""
from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass, field

from .preowned_evidence import (active_fleet_models, latest_retail_rows, build_preowned_evidence,
                                _distribution, DtsDistribution)

# Named, configurable evidence constants (analysis gates — NOT ratified economic business law).
RESALE_MIN_N = 8          # min recorded resale prices for a headline resale distribution
GROSS_MIN_N = 8           # min recorded-gross observations for a headline recorded-gross distribution
MATURITY_BIN_MIN_N = 5    # min observations per model-year-maturity bin before it is plotted
RECENT_WINDOW_DAYS = 365  # observation-recency window used by the transparent evidence-quality factor

_ACTIVE_STATES = ("ACTIVE_RENTED", "ACTIVE_AVAILABLE", "AWAITING_USED_CARS_RECEIPT")


def _numeric(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _mileage_int(v):
    """Coerce the stored last-checkout mileage to a clean int (0 is valid), or None when unreported. Robust
    to the value being stored as text (SQLite TEXT affinity) rather than a native integer."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _year_of(sold_date):
    try:
        return int(str(sold_date)[:4])
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Cohort:
    """A historical distribution over a defensible comparable cohort (recorded prices or recorded gross)."""
    kind: str                    # 'resale' | 'gross'
    label: str                   # cohort definition, e.g. 'QX60 · model-year 2023'
    dist: DtsDistribution        # count/min/p25/median/p75/max over the source values
    as_of: str | None            # retail batch received_at (date)
    earliest: str | None         # earliest observation sold_date in the cohort
    latest: str | None           # latest observation sold_date in the cohort
    recent_n: int                # observations within RECENT_WINDOW_DAYS of as_of
    gate: int                    # applicable sample gate
    gated: bool                  # dist.count >= gate

    @property
    def n(self):
        return self.dist.count


@dataclass(frozen=True)
class MaturityBin:
    label: str                   # '0','1',...,'5+'  (model-year age at resale, NOT time in service)
    n: int
    median_price: float | None
    thin: bool                   # n < MATURITY_BIN_MIN_N


@dataclass(frozen=True)
class EvidenceQuality:
    label: str                   # 'Strong' | 'Moderate' | 'Thin'
    sample: str                  # transparent factor descriptions (never collapsed into a hidden score)
    recency: str
    spread: str


@dataclass(frozen=True)
class ModelIntel:
    model: str
    active_units: int
    sales_count: int
    dts: DtsDistribution | None
    resale_model: Cohort | None
    resale_years: tuple = ()
    gross_model: Cohort | None = None
    gross_years: tuple = ()
    maturity: tuple = ()
    maturity_excluded: int = 0
    quality: EvidenceQuality | None = None


@dataclass(frozen=True)
class UnitIntel:
    id: str
    vin: str
    model: str | None
    in_service_date: str | None
    age_days: int | None
    mileage: int | None
    mileage_available: bool
    membership_state: str
    rental_state: str | None
    quality_flags: tuple = ()
    model_year: str = ""                              # authoritative MY from the fleet source ("" when absent)


@dataclass(frozen=True)
class Attention:
    kind: str                    # 'zero_mile' | 'missing_mileage' | 'missing_in_service_date' | 'no_resale_sample'
    message: str
    unit_id: str | None = None
    vin: str | None = None


@dataclass(frozen=True)
class LoanerIntel:
    current_fleet: int
    desired_fleet: int | None
    ideal_fleet: None                        # always None — Undetermined (economics gated)
    composition: tuple                       # ((model, count), ...)
    units: tuple
    attention: tuple
    models: tuple
    retail_as_of: str | None
    retail_loaded: bool
    fleet_models_resolved: bool


# ---- builders ------------------------------------------------------------------------------------------
def _dist_of(rows, valuefn):
    return _distribution([v for v in (valuefn(r) for r in rows) if v is not None])


def _cohort(kind, label, rows, valuefn, gate, as_of):
    # Service Loaner market intelligence is USED-market evidence. Explicit NEW
    # deliveries remain available upstream for identity only.
    rows = [r for r in rows if str(r.get("_sale_kind") or "").strip().upper() != "NEW"]
    vals_rows = [(valuefn(r), str(r.get("sold_date") or "")) for r in rows]
    vals_rows = [(v, d) for (v, d) in vals_rows if v is not None]
    if not vals_rows:
        return None
    dist = _distribution([v for v, _d in vals_rows])
    dates = sorted(d for _v, d in vals_rows if d)
    earliest = dates[0] if dates else None
    latest = dates[-1] if dates else None
    recent_n = 0
    if as_of and latest:
        try:
            cutoff = (_dt.date.fromisoformat(str(as_of)[:10]) - _dt.timedelta(days=RECENT_WINDOW_DAYS))
            recent_n = sum(1 for _v, d in vals_rows if d and _dt.date.fromisoformat(d[:10]) >= cutoff)
        except Exception:   # noqa: BLE001
            recent_n = 0
    return Cohort(kind=kind, label=label, dist=dist, as_of=(str(as_of)[:10] if as_of else None),
                  earliest=earliest, latest=latest, recent_n=recent_n, gate=gate, gated=dist.count >= gate)


def _quality(cohort):
    if cohort is None or cohort.n == 0:
        return EvidenceQuality("Thin", "no usable sample", "—", "—")
    sample = f"n={cohort.n} (gate {cohort.gate})"
    sample_ok = cohort.n >= cohort.gate
    # recency: is the latest observation within the recent window, and how much of the sample is recent
    recency = f"latest {cohort.latest or '—'}, {cohort.recent_n}/{cohort.n} within {RECENT_WINDOW_DAYS}d of as-of"
    recent_ok = cohort.recent_n > 0
    # spread: IQR / median dispersion
    spread_ok = False
    if cohort.dist.median and cohort.dist.p25 is not None and cohort.dist.p75 is not None and cohort.dist.median != 0:
        iqr = cohort.dist.p75 - cohort.dist.p25
        ratio = iqr / abs(cohort.dist.median)
        spread = f"IQR/median = {ratio:.2f}"
        spread_ok = ratio <= 0.6
    else:
        spread = "insufficient to assess"
    if not sample_ok:
        label = "Thin"
    elif recent_ok and spread_ok:
        label = "Strong"
    else:
        label = "Moderate"
    return EvidenceQuality(label, sample, recency, spread)


def _maturity(rows):
    """Model-year age at resale = sold_date.year - model_year. Valid maturity >= 0; invalid/missing excluded
    from the analytical cohort (counted for provenance). Returns (bins, excluded_count)."""
    buckets = defaultdict(list)
    excluded = 0
    for r in rows:
        if str(r.get("_sale_kind") or "").strip().upper() == "NEW":
            continue
        price = _numeric(r.get("price"))
        sy, my = _year_of(r.get("sold_date")), r.get("year")
        if price is None or sy is None or not isinstance(my, int) or isinstance(my, bool):
            excluded += 1
            continue
        mat = sy - my
        if mat < 0:
            excluded += 1                       # invalid maturity — preserved as a count, never reinterpreted
            continue
        buckets["5+" if mat >= 5 else str(mat)].append(price)
    order = ["0", "1", "2", "3", "4", "5+"]
    import statistics as _st
    bins = []
    for k in order:
        vals = buckets.get(k, [])
        if vals:
            bins.append(MaturityBin(label=k, n=len(vals),
                                    median_price=float(_st.median(vals)),
                                    thin=len(vals) < MATURITY_BIN_MIN_N))
    return tuple(bins), excluded


def _age_days(in_service, clock):
    if not in_service:
        return None
    try:
        d = _dt.date.fromisoformat(str(in_service)[:10])
        return (clock.now().date() - d).days
    except Exception:   # noqa: BLE001
        return None


def build_intelligence(conn, scope, prefs, clock):
    from .loaner_cockpit import MetaPrefs, desired_fleet, current_fleet_count

    # Load the combined Reynolds lifecycle once. latest_retail_rows restores the
    # raw New/Used flag and retains NEW rows for exact-VIN identity. Every
    # analytical market consumer below uses only non-NEW rows.
    retail_rows, as_of = latest_retail_rows(conn, scope)
    pe = build_preowned_evidence(
        conn, scope, retail_rows=retail_rows, retail_received_at=as_of
    )                                                  # A: USED composition + DTS + sample depth
    vin_model = active_fleet_models(conn, scope)
    from .preowned_evidence import active_fleet_model_years
    vin_my, my_conflicts = active_fleet_model_years(conn, scope)   # authoritative MY (governed, fail-closed)
    retail_loaded = bool(as_of)

    used_retail_rows = [
        r for r in retail_rows
        if str(r.get("_sale_kind") or "").strip().upper() != "NEW"
    ]

    # by-model USED retail cohorts (B)
    by_model = defaultdict(list)
    for r in used_retail_rows:
        m = r.get("model")
        if isinstance(m, str) and m.strip():
            by_model[m.strip().upper()] = by_model[m.strip().upper()]  # touch
    for r in used_retail_rows:
        m = r.get("model")
        if isinstance(m, str):
            by_model[m.strip().upper()].append(r)

    dts_by_model = {m.model: m for m in pe.models}
    models = []
    for me in pe.models:
        model = me.model
        rows = by_model.get(model, [])
        resale_model = _cohort("resale", f"{model} · all model-years", rows, lambda r: _numeric(r.get("price")),
                               RESALE_MIN_N, as_of) if rows else None
        gross_model = _cohort("gross", f"{model} · all model-years", rows, lambda r: _numeric(r.get("gross_profit")),
                              GROSS_MIN_N, as_of) if rows else None
        # per model-year cohorts (narrowest defensible), gated
        years = defaultdict(list)
        for r in rows:
            y = r.get("year")
            if isinstance(y, int) and not isinstance(y, bool):
                years[y].append(r)
        resale_years, gross_years = [], []
        for y in sorted(years, reverse=True):
            rc = _cohort("resale", f"{model} · model-year {y}", years[y], lambda r: _numeric(r.get("price")),
                         RESALE_MIN_N, as_of)
            gc = _cohort("gross", f"{model} · model-year {y}", years[y], lambda r: _numeric(r.get("gross_profit")),
                         GROSS_MIN_N, as_of)
            if rc:
                resale_years.append(rc)
            if gc:
                gross_years.append(gc)
        maturity, excluded = _maturity(rows)
        # headline quality = the narrowest gated resale cohort, else the model-level cohort
        headline = next((c for c in resale_years if c.gated), resale_model)
        models.append(ModelIntel(model=model, active_units=me.active_units, sales_count=me.sales_count,
                                  dts=me.distribution, resale_model=resale_model,
                                  resale_years=tuple(resale_years), gross_model=gross_model,
                                  gross_years=tuple(gross_years), maturity=maturity,
                                  maturity_excluded=excluded, quality=_quality(headline)))

    # A: active fleet units
    marks = ",".join("?" * len(_ACTIVE_STATES))
    urows = conn.execute(
        f"SELECT id, vin, membership_state, current_rental_state, accepted_in_service_date, last_checkout_mileage "
        f"FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL AND active_fleet_presence=1 "
        f"AND membership_state IN ({marks}) ORDER BY accepted_in_service_date", (scope, *_ACTIVE_STATES)).fetchall()
    units, attention = [], []
    for u in urows:
        vin = (u["vin"] or "").upper()
        model = vin_model.get(vin)
        age = _age_days(u["accepted_in_service_date"], clock)
        mileage = _mileage_int(u["last_checkout_mileage"])
        flags = []
        if u["accepted_in_service_date"] is None:
            flags.append("in-service date not resolved")
            attention.append(Attention("missing_in_service_date",
                                       f"{model or 'unit'} {vin[-6:]} — authoritative in-service date not resolved",
                                       u["id"], vin))
        if mileage is None:
            flags.append("mileage not reported in latest snapshot")
            attention.append(Attention("missing_mileage",
                                       f"{model or 'unit'} {vin[-6:]} — mileage not reported in latest snapshot",
                                       u["id"], vin))
        units.append(UnitIntel(id=u["id"], vin=vin, model=model, in_service_date=u["accepted_in_service_date"],
                               age_days=age, mileage=mileage, mileage_available=mileage is not None,
                               membership_state=u["membership_state"], rental_state=u["current_rental_state"],
                               quality_flags=tuple(flags), model_year=vin_my.get(vin, "")))

    for a in conn.execute(
            "SELECT a.id, a.prompt, u.vin, u.id uid FROM service_loaner_monitoring_alert a "
            "JOIN service_loaner_unit u ON a.service_loaner_unit_id=u.id "
            "WHERE u.store_scope=? AND a.status='active' ORDER BY a.created_at", (scope,)).fetchall():
        attention.insert(0, Attention("zero_mile", a["prompt"] or "Zero-mile rented alert", a["uid"],
                                      (a["vin"] or "").upper()))
    # models with active fleet presence but no defensible resale sample
    for mi in models:
        if mi.active_units and not any(c.gated for c in mi.resale_years) and not (mi.resale_model and mi.resale_model.gated):
            attention.append(Attention("no_resale_sample",
                                       f"{mi.model} — no defensible recorded-resale sample yet (evidence Thin)"))
    # governed model-year source conflicts (ambiguous/malformed) — surfaced, never silently resolved
    for cvin, reason in (my_conflicts or {}).items():
        attention.append(Attention("model_year_conflict",
                                   f"{cvin[-6:]} — model year unresolved: {reason}", None, cvin))

    meta = MetaPrefs(prefs, scope)
    return LoanerIntel(
        current_fleet=current_fleet_count(conn, scope), desired_fleet=desired_fleet(meta), ideal_fleet=None,
        composition=tuple((m.model, m.active_units) for m in pe.models),
        units=tuple(units), attention=tuple(attention), models=tuple(models),
        retail_as_of=(str(as_of)[:10] if as_of else None), retail_loaded=retail_loaded,
        fleet_models_resolved=pe.fleet_models_resolved)
