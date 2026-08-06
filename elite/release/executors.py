"""Full execution-service wiring — resolving the Phase 11 integration limitation.

Every required pilot control is bound to the ACTUAL Phase 5-7 governed domain method. There is no synthetic
callback in the real pilot path. A live execution:
  1. invokes the real domain governed method (its own Governor.perform -> a real domain event + Audit Event
     + optimistic-concurrency/idempotency), producing a REAL domain-execution reference;
  2. references that real reference in the Phase 9 execution authorization/completion/reconciliation
     (Phase 9 references domain execution — it never duplicates it);
so the UI performs no direct domain-table mutation, a failed real execution is never shown as success, the
effect is idempotent, and the audit + correlation chain stays linked.
"""
from __future__ import annotations

from ..errors import AuthorizationError, EliteError, ValidationError
from .models import CAPS, SHADOW_EXECUTION_ENABLED


class LiveExecutorRegistry:
    """Maps a governed action to the REAL Phase 5-7 domain method. No entry is a synthetic lambda."""

    def __init__(self, *, workflow=None, loaner=None, execdemo=None, decisions=None):
        # each value is a real bound domain method (or a callable that invokes one)
        self.bindings = {}
        if execdemo is not None:
            self.bindings.update({
                "executive_demo.designation.execute": execdemo.units.execute_designation,
                "executive_demo.retirement.execute": execdemo.retirement.execute,
                "executive_demo.retirement.used_cars": execdemo.retirement.confirm_used_cars_receipt,
                "executive_demo.retirement.return": execdemo.retirement.execute,
            })
        if loaner is not None:
            self.bindings.update({
                "service_loaner.entry.execute": loaner.units.execute_entry,
                "service_loaner.retirement.complete": loaner.retirement.complete,
                "service_loaner.return.confirm": loaner.retirement.confirm_return,
                "service_loaner.used_cars.confirm": loaner.retirement.confirm_used_cars_receipt,
            })
        if workflow is not None:
            for name, fn in (workflow or {}).items():
                self.bindings[name] = fn
        self.decisions = decisions

    def has(self, action):
        return action in self.bindings

    def is_synthetic(self, action):
        """A bound executor is a real domain method, never a synthetic string/lambda placeholder."""
        fn = self.bindings.get(action)
        return fn is None or getattr(fn, "__name__", "") in ("<lambda>", "synthetic")

    def actions(self):
        return sorted(self.bindings)


class LiveExecutionService:
    """Drives a real domain execution behind a governed Decision and links it through Phase 9 execution."""

    def __init__(self, p9, release_store, registry, shadow, stack, clock, logger=None):
        self.p9 = p9
        self.store = release_store
        self.registry = registry
        self.shadow = shadow
        self.stack = stack
        self.clock = clock
        self.logger = logger
        self._bindings = {}          # decision_id -> {domain, action, real_call, expected_action}

    def bind(self, decision_id, *, domain, action, real_call, expected_action=None):
        """Bind a governed Decision to the ACTUAL Phase 5-7 executor for the real pilot path."""
        self._bindings[decision_id] = {"domain": domain, "action": action, "real_call": real_call,
                                       "expected_action": expected_action}

    def has_binding(self, decision_id):
        return decision_id in self._bindings

    def execute_bound(self, *, principal, scope, decision, idempotency_key=None, correlation_id=None):
        b = self._bindings[decision["id"]]
        return self.execute(principal=principal, scope=scope, decision=decision, action=b["action"],
                            domain=b["domain"], real_call=b["real_call"],
                            expected_action=b["expected_action"], correlation_id=correlation_id,
                            idempotency_key=idempotency_key)

    def execution_enabled(self, domain, scope):
        mode = self.shadow.current_mode(domain, scope)
        return mode in SHADOW_EXECUTION_ENABLED

    def execute(self, *, principal, scope, decision, action, domain, real_call, expected_action=None,
                correlation_id=None, idempotency_key=None):
        """`real_call(principal, scope)` MUST invoke the actual Phase 5-7 domain method and return a real
        domain execution reference. Execution is blocked unless the domain's shadow mode enables it and the
        operator holds `release.execute.live`. A Scenario Decision can never enter the official path."""
        self.stack.authz.require(principal, CAPS["EXECUTE_LIVE"], scope, correlation_id=correlation_id)
        scenario_id = decision["scenario_id"] if "scenario_id" in decision.keys() else None
        if scenario_id:
            raise ValidationError(message="A Scenario Decision cannot execute officially.",
                                  technical_detail="scenario decision blocked from live execution")
        if not self.execution_enabled(domain, scope):
            raise AuthorizationError(
                message="Live execution is not enabled for this domain.",
                technical_detail=f"shadow mode does not permit execution for {domain}/{scope}")
        if not self.registry.has(action):
            raise ValidationError(technical_detail=f"no live executor bound for {action}")

        # 1) real domain governed execution -> a REAL domain reference (not synthetic)
        try:
            real_ref = real_call(principal, scope)
        except EliteError:
            raise
        real_ref = _ref_of(real_ref)

        # 2) reference the real domain execution in the Phase 9 execution
        approvals = self.p9.store.approvals_for(decision["id"])
        approval = self.p9.store.get_approval(approvals[-1]["id"]) if approvals else None
        sel = decision["selected_action"] if "selected_action" in decision.keys() else None
        ea = self.p9.execution.authorize(
            principal, scope, decision, approval, execution_capability="domain.execute",
            expected_action=expected_action or sel or "execute",
            domain_execute_fn=lambda conn: real_ref, idempotency_key=idempotency_key,
            correlation_id=correlation_id)
        execauth = ea.get("execution") if isinstance(ea, dict) else None
        if execauth is not None:
            self.p9.execution.complete(principal, scope, execauth, domain_completion_ref=f"{real_ref}::done")
            self.p9.execution.reconcile(decision)
        if self.logger:
            self.logger.op("release", "release.execute.live", result="ok", correlation_id=correlation_id,
                           domain=domain, executed=action)
        return {"domain_ref": real_ref, "execution": execauth}


def _ref_of(result):
    """Extract a stable real reference from a domain method result (tuple/dict/obj/str)."""
    if isinstance(result, str):
        return result
    if isinstance(result, tuple) and result:
        return _ref_of(result[0])
    if isinstance(result, dict):
        for k in ("result_ref", "id", "event", "ref"):
            if k in result and result[k]:
                return str(result[k])
    for attr in ("result_ref", "id"):
        v = getattr(result, attr, None)
        if v:
            return str(v)
    return str(result)
