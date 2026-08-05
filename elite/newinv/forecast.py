"""Month-by-month forecast issuance + reconciliation.

Forecasts are monthly over an explicit horizon (never only an annualized average). Monthly
values reconcile to the forecast total; combination totals reconcile to model totals and model
totals to portfolio totals. A previously issued forecast is immutable — a changed current
forecast is a NEW issued result, never a rewrite. Official and hypothetical (scenario)
forecasts remain distinct.
"""
from __future__ import annotations

from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import ForecastMonth, ForecastResult


class ForecastService:
    def __init__(self, store, clock, policy_store):
        self.store, self.clock, self.policy = store, clock, policy_store

    def issue(self, demand_result, *, calculation_version, issue_date=None, lineage_refs=None,
              input_state_refs=None):
        horizon = sorted(demand_result.monthly_expected)
        cum, months = 0.0, []
        for i, m in enumerate(horizon):
            exp = demand_result.monthly_expected[m]
            cum = round(cum + exp, 6)
            months.append(ForecastMonth(id=new_id("fm"), forecast_id="", month=m, expected_retail=exp,
                                        cumulative_expected=cum, confidence=demand_result.confidence, seq=i))
        total = round(sum(demand_result.monthly_expected.values()), 6)
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "forecast", "calculation_version": calculation_version,
                                    "demand_result": demand_result.id,
                                    "monthly": demand_result.monthly_expected, "total": total},
            calculation_timestamp=self.store._now(), implementation_revision="phase4-forecast",
            output_reference=output_checksum({"months": demand_result.monthly_expected, "total": total})))
        f = ForecastResult(
            id=new_id("fc"), store_scope=demand_result.store_scope, issue_date=issue_date or self.store._now(),
            combination_id=demand_result.combination_id, horizon_start=horizon[0] if horizon else None,
            horizon_end=horizon[-1] if horizon else None, total_expected=total, confidence=demand_result.confidence,
            input_state_refs=list(input_state_refs or []), policy_versions=list(demand_result.policy_versions),
            calculation_version=calculation_version, lineage_refs=list(lineage_refs or []),
            scenario_id=demand_result.scenario_id, reproducibility_package=pkg.id, demand_result_id=demand_result.id,
            months=months)
        return self.store.add_forecast(f)


def reconcile_months(forecast) -> bool:
    """Monthly values reconcile to the forecast total (to float tolerance)."""
    return abs(sum(m.expected_retail for m in forecast.months) - forecast.total_expected) < 1e-6


def reconcile_totals(child_totals, parent_total) -> bool:
    """Combination→model or model→portfolio total reconciliation."""
    return abs(sum(child_totals) - parent_total) < 1e-6
