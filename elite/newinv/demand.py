"""Demand baseline — ONE authoritative Demand contract.

Demand is calculated from accepted dealership history + approved policy under a versioned
Calculation Version. It NEVER consumes supply method, CPO/PPO/CTP availability, Dealer Trade
feasibility, Service Loaner / Executive Demo economics, or a desired acquisition path — so a
supply-method change alone can never move Demand truth. Availability is interpreted with sales
(exposure denominator) so "no availability" is never read as "zero demand". Direct exact-
combination evidence outranks inherited lineage evidence; inherited evidence is always labeled;
low sample size and unresolved gaps reduce confidence. Seasonality is bounded and explainable;
sparse history falls back to flat rather than exaggerating.
"""
from __future__ import annotations

from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import (DIRECT_TIERS, LOW_SAMPLE, SEASON_MAX, SEASON_MIN, DemandResult)

# Minimum distinct calendar months of evidence before seasonality is trusted at all.
_MIN_SEASON_MONTHS = 6
_REL_TIER = {"new_model_year": "lineage", "related_family": "family", "attribute": "attribute",
             "generation_change": "lineage"}


def _month_no(m):
    return int(m[5:7])


def _clamp_season(x):
    return max(SEASON_MIN, min(SEASON_MAX, x))


def derive_seasonality(retail_by_month):
    """Derive a bounded, explainable monthly seasonality index from dealership retail. Sparse
    history (too few distinct months) returns a flat index — never an exaggerated coefficient."""
    if not retail_by_month:
        return {}, "flat:no_history"
    by_cal = {}
    for month, count in retail_by_month.items():
        by_cal.setdefault(_month_no(month), []).append(count)
    if len(by_cal) < _MIN_SEASON_MONTHS:
        return {}, f"flat:sparse({len(by_cal)}<{_MIN_SEASON_MONTHS})"
    overall = sum(sum(v) for v in by_cal.values()) / sum(len(v) for v in by_cal.values())
    if overall <= 0:
        return {}, "flat:zero_mean"
    idx = {str(cal): _clamp_season((sum(v) / len(v)) / overall) for cal, v in by_cal.items()}
    return idx, "derived_bounded"


def _baseline_rate(inputs: dict) -> float:
    """Baseline monthly rate. Legacy (no credibility block): sales / exposure with exposure floored at 1
    month — unchanged for every existing caller. Credibility path: the exact rate (sales / real exposure,
    NOT floored) is shrunk toward a higher-level prior by Buhlmann weight Z, so a thin partial-month cohort
    can no longer masquerade as a full monthly velocity. All inputs live in `inputs` so replay reproduces."""
    rbm = inputs["retail_by_month"]
    cred = inputs.get("credibility")
    if not cred:
        return sum(rbm.values()) / max(float(inputs["exposure_months"]), 1.0)
    exact_exposure = max(float(inputs["exposure_months"]), float(cred.get("min_exposure", 1.0)))
    exact_rate = sum(rbm.values()) / exact_exposure if rbm else 0.0
    n = float(cred.get("exact_n", 0))
    k = cred.get("k")
    z = (n / (n + k)) if (k and k > 0) else 1.0
    z = max(0.0, min(z, float(cred.get("z_cap", 1.0))))
    prior = cred.get("prior_rate")
    prior = float(prior) if prior is not None else exact_rate
    return z * exact_rate + (1.0 - z) * prior


def _demand_math(inputs: dict) -> dict:
    """Pure, deterministic Demand computation used by both issue() and replay()."""
    trend = float(inputs["trend"])
    season = inputs["seasonality"]
    baseline_rate = _baseline_rate(inputs)
    out = {}
    for m in inputs["horizon"]:
        s = _clamp_season(float(season.get(str(_month_no(m)), 1.0)))
        out[m] = round(baseline_rate * s * trend, 6)
    return out


def _confidence(tier, sample, gaps):
    if tier == "estimate":
        return "low"
    base = "high" if tier in DIRECT_TIERS else "medium"
    if sample < LOW_SAMPLE or gaps:
        base = {"high": "medium", "medium": "low"}.get(base, base)
    return base


class DemandService:
    """Note the constructor and issue() signatures: no supply parameter exists at all."""

    def __init__(self, store, clock, policy_store):
        self.store, self.clock, self.policy = store, clock, policy_store

    def issue(self, combination, scope, horizon, *, retail_by_month=None, exposure_months=0.0,
              sample_size=0, trend=1.0, trend_method="stable", seasonality=None, inherited=None,
              inherit_allowed=False, gaps=False, policy_versions=None, calculation_version,
              scenario_id=None, source_refs=None, fact_refs=None, credibility=None):
        retail_by_month = retail_by_month or {}
        exact = sum(retail_by_month.values()) > 0
        if exact:
            tier, direct = "exact", True
            rbm, exp, samp = retail_by_month, exposure_months, sample_size
            src = "direct_exact_combination"
        elif inherited and inherit_allowed:
            rel = inherited.get("relationship", "related_family")
            tier, direct = _REL_TIER.get(rel, "family"), False
            rbm, exp = inherited.get("retail_by_month", {}), inherited.get("exposure_months", exposure_months)
            samp = inherited.get("sample_size", 0)
            src = f"inherited:{rel}:{inherited.get('source_combination', '')}"
        else:
            tier, direct = "estimate", False
            rbm, exp, samp, src = {}, max(exposure_months, 0.0), 0, "low_confidence_estimate"

        season, season_note = (({str(k): _clamp_season(v) for k, v in seasonality.items()}, "policy_or_given")
                               if seasonality else derive_seasonality(rbm))
        inputs = {"horizon": list(horizon), "retail_by_month": dict(rbm), "exposure_months": exp,
                  "seasonality": season, "trend": float(trend)}
        # Credibility (evidence-maturity) shrinkage — only when the caller supplies a governed block; the
        # exact rate is blended toward a higher-level prior so thin exact cohorts do not over-call. The block
        # is embedded in `inputs` so replay reproduces the same monthly output.
        if credibility is not None:
            inputs["credibility"] = dict(credibility)
        monthly = _demand_math(inputs)
        conf = _confidence(tier, samp, gaps)
        if credibility is not None and credibility.get("evidence_level"):
            # confidence reflects corroboration: an uncorroborated thin exact cohort is never "high"
            if credibility.get("evidence_level") in ("portfolio", "none") and samp < LOW_SAMPLE:
                conf = "low"

        checksum = output_checksum(monthly)
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "demand", "calculation_version": calculation_version,
                                    "inputs": inputs, "policy_versions": list(policy_versions or []),
                                    "evidence_tier": tier, "monthly_expected": monthly},
            calculation_timestamp=self.store._now(), implementation_revision="phase4-demand",
            output_reference=checksum))

        d = DemandResult(
            id=new_id("dem"), store_scope=scope, combination_id=combination.id if combination else None,
            horizon_start=horizon[0] if horizon else None, horizon_end=horizon[-1] if horizon else None,
            monthly_expected=monthly, baseline_evidence={"source": src, "retail_by_month": rbm, "exposure_months": exp},
            evidence_tier=tier, direct_evidence=direct, availability_adjustment="retail_per_available_month",
            seasonality_ref={"index": season, "note": season_note},
            trend_ref={"factor": trend, "method": trend_method}, confidence=conf,
            uncertainty={"sample_size": samp, "gaps": bool(gaps), "tier": tier,
                         "credibility": (dict(credibility) if credibility is not None else None)},
            policy_versions=list(policy_versions or []), calculation_version=calculation_version,
            source_refs=list(source_refs or []), fact_refs=list(fact_refs or []),
            reproducibility_package=pkg.id, scenario_id=scenario_id)
        return self.store.add_demand(d)

    def replay(self, package_id):
        """Recompute Demand from the pinned reproducibility package. Must reproduce the same
        monthly output + checksum."""
        pkg = self.policy.get_reproducibility(package_id)
        monthly = _demand_math(pkg.refs["inputs"])
        return monthly, (output_checksum(monthly) == pkg.output_reference)
