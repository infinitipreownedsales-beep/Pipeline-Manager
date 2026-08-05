"""Deterministic Calibration backtesting + validation.

Compares a current version and a proposed version over PRESERVED historical inputs + outcomes and their
prediction errors, per material cohort. Backtesting never rewrites historical issued Predictions; its
results are labeled hypothetical; training/evaluation windows stay distinguishable; leakage of future
Observation into historical Prediction inputs is prohibited. It identifies cohorts improved / worsened
/ unchanged and flags when an aggregate improvement hides material cohort degradation. Synthetic
fixtures prove the foundation — no machine learning is implemented merely to satisfy Phase 8.
"""
from __future__ import annotations

from ..errors import ValidationError


class BacktestService:
    def __init__(self, store, policy_store, clock, calc_version):
        self.store, self.policy, self.clock, self.calc_version = store, policy_store, clock, calc_version

    def run(self, calibration_proposal_id, *, current_version, proposed_version, cohorts, training_window=None,
            evaluation_window=None, dataset_refs=None, leakage=False):
        """`cohorts`: [{name, current_error, proposed_error, material}]. Returns the stored run + a
        summary. Leakage (future Observation into historical inputs) is prohibited."""
        if leakage:
            raise ValidationError(message="Backtest leakage is prohibited.",
                                  technical_detail="future observation leaked into historical prediction inputs")
        run = self.store.add_validation_run(
            calibration_proposal_id, current_version=current_version, proposed_version=proposed_version,
            training_window=training_window, evaluation_window=evaluation_window, dataset_refs=dataset_refs,
            hypothetical=True, leakage_checked=True, calculation_version=self.calc_version)
        improved, worsened, unchanged = [], [], []
        agg_current, agg_proposed, hides = 0.0, 0.0, False
        for c in cohorts:
            cur_e, prop_e = float(c["current_error"]), float(c["proposed_error"])
            delta = round(prop_e - cur_e, 6)                      # negative => proposed error lower => improved
            direction = "improved" if delta < 0 else "worsened" if delta > 0 else "unchanged"
            material = bool(c.get("material"))
            self.store.add_validation_result(run["id"], cohort=c["name"], current_error=cur_e, proposed_error=prop_e,
                                             delta=delta, direction=direction, material=material)
            (improved if direction == "improved" else worsened if direction == "worsened" else unchanged).append(
                c["name"])
            agg_current += cur_e
            agg_proposed += prop_e
            if material and direction == "worsened":
                hides = True                                      # a material cohort degraded
        aggregate_delta = round(agg_proposed - agg_current, 6)
        summary = {"run_id": run["id"], "improved": improved, "worsened": worsened, "unchanged": unchanged,
                   "aggregate_delta": aggregate_delta, "aggregate_improved": aggregate_delta < 0,
                   "hides_material_degradation": bool(hides and aggregate_delta < 0), "hypothetical": True}
        return summary
