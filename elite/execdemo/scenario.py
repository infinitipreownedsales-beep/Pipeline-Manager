"""Executive Demo scenario exploration — isolated hypothetical context.

Scenario values do not change official policy or official portfolio state; a shared scenario does not
imply approval; overrides remain visible; the official baseline is preserved. Promotion to official
policy would be a separate governed action (Phase 3), not performed here.
"""
from __future__ import annotations


class ScenarioService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def explore(self, scenario_id, scope, *, kind, overrides, output, baseline_ref=None):
        return self.store.add_scenario_result(scenario_id, scope, kind, overrides, output, baseline_ref=baseline_ref)
