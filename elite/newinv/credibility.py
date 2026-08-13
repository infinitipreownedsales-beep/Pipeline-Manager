"""Evidence-maturity / credibility layer for the New-Inventory decision engine.

The Phase 4 DemandService point-estimates velocity as sales / exposure at full weight, so a single
partial-month sale becomes a full monthly velocity (the real-data "1 sale -> Need 5" failure). This
module supplies the governed inputs that let DemandService SHRINK a thin exact-combination rate toward a
higher-level, source-grounded prior — WITHOUT fabricating an exact sale and WITHOUT inventing demand from
broader levels. It also scores two decision-evidence signals the engine must weigh: historical
days-to-sell (inventory RISK) and DT/DNQ recurrence (externally-satisfied-demand BREADTH).

Credibility follows Buhlmann: blended_rate = Z*exact_rate + (1-Z)*prior_rate, Z = n / (n + K). K is the
ratio of expected process variance to the variance of hypothetical means, ESTIMATED from the real dealer
panel and accepted only if it is stable under a holdout check. K is never hand-picked to make numbers look
good: if the panel cannot produce a stable variance-ratio K, credibility falls back to shrinkage anchored
at the panel's OWN median cohort evidence volume (a data-derived quantity, recorded with a fallback
reason), which reduces exact-level credibility and leans on higher-level evidence rather than manufacturing
statistical certainty. Every choice (evidence level, Z, stability, calibration sample, fallback reason) is
recorded so a recommendation can explain what evidence drove it.

Hierarchy (source-grounded, exact preserved):
    L0 exact  = model + model_code + exterior + interior   (never fabricated)
    L1        = model + model_code
    L2        = model
Nearest VALID higher level = the closest parent whose own mature sample >= LOW_SAMPLE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median, pvariance

from .models import LOW_SAMPLE

# Minimum panel shape required before a Buhlmann variance-ratio K is even attempted. These gate whether an
# estimate is TRUSTWORTHY; they do not set the estimate's value (K itself is computed from the data).
_MIN_PANEL_COHORTS = 8            # too few cohorts -> between-cohort variance is not estimable
_MIN_PANEL_MONTHS = 3            # a cohort needs a few months before its own variance means anything
_HOLDOUT_FRACTION = 0.30          # last 30% of the window is held out to check that shrinkage helps


def month_series(retail_by_month, first_midx, latest_midx):
    """Dense monthly count vector over [first_midx, latest_midx] (missing months are real 0 sales)."""
    from .demand_bridge import midx_of
    by_midx = {}
    for m, c in retail_by_month.items():
        mi = midx_of(m.replace("-", ""))
        if mi is not None:
            by_midx[mi] = by_midx.get(mi, 0) + c
    return [by_midx.get(mi, 0) for mi in range(first_midx, latest_midx + 1)]


# --------------------------------------------------------------------------------------------------------
# Buhlmann K estimation with a holdout stability gate.
# --------------------------------------------------------------------------------------------------------
@dataclass
class CredibilityModel:
    k: float                       # shrinkage constant actually in force
    method: str                    # "buhlmann_stable" | "fallback_median_sample" | "degenerate"
    stable: bool                   # True only when the variance-ratio K passed the holdout check
    n_cohorts: int
    calibration_sample: int        # total sales across the panel used to calibrate
    epv: float = None              # expected process variance (within-cohort)
    vhm: float = None              # variance of hypothetical means (between-cohort)
    fallback_reason: str = ""

    def weight(self, n):
        """Credibility Z for a cohort with n mature sales. Bounded [0,1]; K<=0 is treated as no shrink."""
        if self.k is None or self.k <= 0:
            return 1.0
        return round(n / (n + self.k), 6)


def _holdout_ok(series_list, k):
    """A minimal stability check: does credibility-shrinking the early window predict the late window at
    least as well as the raw early mean? If shrinkage does not help, the variance-ratio K is not trusted."""
    grand = ([c for s in series_list for c in s])
    if not grand:
        return False
    grand_mean = sum(grand) / len(grand)
    cred_err = raw_err = 0.0
    used = 0
    for s in series_list:
        if len(s) < 2:
            continue
        cut = max(1, int(round(len(s) * (1 - _HOLDOUT_FRACTION))))
        early, late = s[:cut], s[cut:]
        if not late:
            continue
        em = sum(early) / len(early)
        lm = sum(late) / len(late)
        z = len(early) / (len(early) + k) if k > 0 else 1.0
        cred = z * em + (1 - z) * grand_mean
        cred_err += (cred - lm) ** 2
        raw_err += (em - lm) ** 2
        used += 1
    if used == 0:
        return False
    return cred_err <= raw_err + 1e-9


def estimate_k(series_list):
    """Estimate the Buhlmann credibility constant K from the real cohort panel, accepting the
    variance-ratio estimate ONLY if the panel is large enough AND shrinkage helps on a holdout. Otherwise
    fall back to shrinkage anchored at the panel's median cohort sample size (data-derived, not hand-picked).
    """
    usable = [s for s in series_list if len(s) >= _MIN_PANEL_MONTHS and sum(s) > 0]
    total_sales = sum(sum(s) for s in series_list)
    n_cohorts = len(usable)
    if n_cohorts >= _MIN_PANEL_COHORTS:
        means = [sum(s) / len(s) for s in usable]
        epv = sum(pvariance(s) for s in usable) / n_cohorts          # within-cohort (process) variance
        mean_len = sum(len(s) for s in usable) / n_cohorts
        vhm = pvariance(means) - (epv / mean_len if mean_len else 0.0)  # between-cohort, bias-corrected
        if vhm > 1e-9:
            k = epv / vhm
            if k > 0 and _holdout_ok(usable, k):
                return CredibilityModel(k=round(k, 4), method="buhlmann_stable", stable=True,
                                        n_cohorts=n_cohorts, calibration_sample=total_sales,
                                        epv=round(epv, 6), vhm=round(vhm, 6))
    # fallback: anchor shrinkage at the typical cohort's evidence volume (median mature sales), which
    # reduces exact-level credibility for thin cohorts and leans on higher-level evidence.
    samples = [sum(s) for s in series_list if sum(s) > 0]
    if not samples:
        return CredibilityModel(k=None, method="degenerate", stable=False, n_cohorts=n_cohorts,
                                calibration_sample=total_sales,
                                fallback_reason="no_panel_sales")
    k_fb = float(median(samples))
    return CredibilityModel(
        k=round(max(k_fb, 1.0), 4), method="fallback_median_sample", stable=False, n_cohorts=n_cohorts,
        calibration_sample=total_sales,
        fallback_reason=("panel_too_small" if n_cohorts < _MIN_PANEL_COHORTS else "variance_ratio_unstable"))


# --------------------------------------------------------------------------------------------------------
# Hierarchical prior assembly (nearest valid higher level).
# --------------------------------------------------------------------------------------------------------
@dataclass
class PriorRate:
    rate: float = None             # expected monthly rate from the nearest valid higher level (None if none)
    level: str = "none"            # "model_code" (L1) | "model" (L2) | "none"
    sample: int = 0


def _parent_rate(sales, span_months):
    return (sum(1 for _ in sales) / max(span_months, 1.0)) if sales else 0.0


@dataclass
class ParentIndex:
    l1: dict = field(default_factory=dict)     # (model, model_code) -> (rate, sample)
    l2: dict = field(default_factory=dict)     # (model,)            -> (rate, sample)
    grand_rate: float = 0.0                    # empirical-Bayes global prior (mean of cohort rates)


def _cohort_rate(cohort, *, latest_midx, part_frac):
    """One cohort's own monthly rate. Span floored at 1 month (a thin partial-month observation must not
    imply a > 1/month rate)."""
    span = (latest_midx - cohort.first_midx + 1) - (1 - part_frac)
    return cohort.sales_total / max(1.0, span)


def _group_rate(cohorts, *, latest_midx, part_frac):
    """Higher-level prior for a TYPICAL child cohort = the MEAN of the child cohorts' own rates (not the
    pooled sum). This answers 'what does a typical configuration under this parent sell', so a model that
    sells 2/month spread across 20 configurations yields a ~0.1/month per-config prior, never 2/month.
    Returns (mean_child_rate, total_sales) — total_sales is only the maturity gate for using this level."""
    rates = [_cohort_rate(c, latest_midx=latest_midx, part_frac=part_frac) for c in cohorts]
    total = sum(c.sales_total for c in cohorts)
    return round(sum(rates) / len(rates), 6) if rates else 0.0, total


def build_parent_index(cohorts, *, latest_midx, part_frac):
    """Mean-child rate + pooled sample for each L1 (model,model_code) and L2 (model) group, plus an
    empirical-Bayes global prior (mean of all per-cohort rates). `cohorts` are CohortDemand records."""
    l1, l2 = {}, {}
    for c in cohorts:
        model = (c.representative.get("model") or "").strip().upper()
        code = c.key[1] if len(c.key) > 1 else ""
        l1.setdefault((model, code), []).append(c)
        l2.setdefault((model,), []).append(c)
    l1_idx = {k: _group_rate(g, latest_midx=latest_midx, part_frac=part_frac) for k, g in l1.items()}
    l2_idx = {k: _group_rate(g, latest_midx=latest_midx, part_frac=part_frac) for k, g in l2.items()}
    per = [_cohort_rate(c, latest_midx=latest_midx, part_frac=part_frac) for c in cohorts]
    grand = round(sum(per) / len(per), 6) if per else 0.0
    return ParentIndex(l1=l1_idx, l2=l2_idx, grand_rate=grand)


def nearest_prior(cohort_key, representative, index):
    """Nearest higher level whose OWN mature sample >= LOW_SAMPLE: L1 (model+code) preferred, else L2
    (model), else the empirical-Bayes global prior ('portfolio'). Never None while any panel evidence
    exists, so a thin exact cohort shrinks toward real higher-level behavior, never manufactured certainty."""
    model = (representative.get("model") or "").strip().upper()
    code = cohort_key[1] if len(cohort_key) > 1 else ""
    r1 = index.l1.get((model, code))
    if r1 and r1[1] >= LOW_SAMPLE:
        return PriorRate(rate=r1[0], level="model_code", sample=r1[1])
    r2 = index.l2.get((model,))
    if r2 and r2[1] >= LOW_SAMPLE:
        return PriorRate(rate=r2[0], level="model", sample=r2[1])
    return PriorRate(rate=index.grand_rate, level="portfolio", sample=0)


# --------------------------------------------------------------------------------------------------------
# Decision-evidence signals: DT/DNQ recurrence (breadth) and historical DTS (risk).
# --------------------------------------------------------------------------------------------------------
def dtdnq_strength(business_code_midxs, *, latest_midx):
    """Continuous [0,1] strength of an externally-satisfied-demand (DT/DNQ) pattern. NOT a count cutoff:
    it blends frequency, recency, and clustering. One isolated event is weak; repeated, recent, clustered
    events become strong. Empty -> 0."""
    ms = sorted(set(m for m in business_code_midxs if m is not None))
    if not ms:
        return 0.0
    distinct = len(ms)
    # frequency DOMINATES so a single isolated event stays weak: 1 month -> 0, 2 -> 0.5, 3 -> 0.67, 4 -> 0.75
    freq = 1.0 - 1.0 / distinct
    # recency: most recent event within ~6 months scores high, decays beyond
    recency = max(0.0, 1.0 - (latest_midx - ms[-1]) / 6.0)
    # clustering: events packed into a short span score higher than the same count spread thin
    span = (ms[-1] - ms[0] + 1)
    clustering = distinct / span if span else 1.0
    # a lone recent event (freq 0) tops out at 0.25+0.15 = 0.40 < representation threshold; recurrence lifts it
    strength = 0.6 * freq + 0.25 * recency + 0.15 * clustering
    return round(max(0.0, min(1.0, strength)), 4)


def dts_burden(dts_average, dts_sample, dis_median=None):
    """Historical days-to-sell as inventory RISK -> a depth-dampening multiplier in (floor,1]. A persistent,
    well-sampled long DTS materially lowers justified depth (60-day, velocity-first objective); a long DTS
    seen only once or twice dampens little (weak evidence). Current arrived DIS reinforces it. Never zero."""
    if not dts_average or dts_average <= 60:
        base = 1.0
    else:
        base = 60.0 / float(dts_average)          # 120d ->0.5, 180d ->0.33, 240d ->0.25
    # confidence in the slowness scales with how many sales we actually observed the DTS on
    persistence = min(1.0, (dts_sample or 0) / float(LOW_SAMPLE))
    factor = 1.0 - persistence * (1.0 - base)
    # a currently-arrived unit already aging past ~120 days reinforces the risk (bounded extra 15% damp)
    if dis_median is not None and dis_median > 120:
        factor *= 0.85
    return round(max(0.15, min(1.0, factor)), 4)
