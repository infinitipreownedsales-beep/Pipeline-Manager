"""Service Loaner policy/scenario exploration — isolated hypothetical context.

Scenario values do not change official policy; scenario decisions do not alter official fleet state;
a shared scenario does not imply approval; scenario output identifies its overrides; the official
baseline is preserved. Promotion to official policy would be a separate governed action (Phase 3),
deliberately not performed here.
"""
from __future__ import annotations


class ScenarioService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def explore(self, scenario_id, scope, *, kind, overrides, output, baseline_ref=None):
        """Record an isolated Service Loaner scenario result. `overrides` names the hypothetical
        changes (fleet size / eligibility / write-down / retirement timing / threshold / monitoring
        duration / market value). Never touches official policy or fleet state."""
        return self.store.add_scenario_result(scenario_id, scope, kind, overrides, output, baseline_ref=baseline_ref)
