"""Expected Executive Demo lifecycle — a versioned projection.

Uses approved policy only; preserves assumptions and uncertainty; never manufactures expected mileage
or duration (missing required inputs → unresolved / lower confidence). Historical projections are
immutable (append-preserving); current projections may change under new facts or policy. Sunk cost is
not carried forward into later retirement decisions.
"""
from __future__ import annotations


class LifecycleProjectionService:
    def __init__(self, store, clock, calc_version):
        self.store, self.clock, self.calc_version = store, clock, calc_version

    def project(self, scope, *, unit_id=None, candidate_id=None, activation_timing=None, expected_duration=None,
                expected_mileage=None, expected_depreciation=None, expected_retirement_timing=None,
                expected_return_path=None, assumptions=None, uncertainty=None, policy_versions=None):
        """Resolved only when the required inputs are present; otherwise unresolved (never manufactured)."""
        required = (expected_duration, expected_mileage, expected_retirement_timing)
        status = "resolved" if all(v is not None for v in required) else "unresolved"
        return self.store.add_lifecycle_projection(
            scope, status, unit_id=unit_id, candidate_id=candidate_id, activation_timing=activation_timing,
            expected_duration=expected_duration, expected_mileage=expected_mileage,
            expected_depreciation=expected_depreciation, expected_retirement_timing=expected_retirement_timing,
            expected_return_path=expected_return_path, assumptions=assumptions, uncertainty=uncertainty,
            policy_versions=policy_versions, calculation_version=self.calc_version)
