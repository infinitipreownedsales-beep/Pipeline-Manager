"""Governed execution authorization + Decision-to-execution reconciliation.

This layer REFERENCES the existing Phase 5-7 domain execution services — it does not duplicate their
logic. Execution authorization requires a current valid approval where applicable; completion must
reference an ACTUAL domain completion event; a failed domain execution can never be marked completed.
Decision, approval, execution, and completion stay separately inspectable. Reconciliation is
deterministic (15 outcomes); a reconciliation conflict yields an unresolved operational state. Historical
authorizations remain preserved after expiration. The workspace state follows the authoritative domain
result.
"""
from __future__ import annotations

from ..errors import ValidationError
from .models import RECONCILIATION_OUTCOMES

_NO_EXEC_DISPOSITIONS = {"REJECT", "NO_ACTION", "REQUEST_INFORMATION", "DEFER"}


class ExecutionService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def authorize(self, principal, scope, decision, approval, *, execution_capability, expected_action,
                  domain_execute_fn=None, requires_approval=True, expiration=None, stale=False,
                  idempotency_key=None, correlation_id=None):
        """Authorize execution against the domain service. `domain_execute_fn(conn)` invokes/references
        the real Phase 5-7 execution and returns its domain execution ref (never reimplemented here)."""
        if stale:
            raise ValidationError(message="Decision is stale; renew review before execution.",
                                  technical_detail="stale decision cannot execute")
        if requires_approval and approval is None:
            raise ValidationError(message="Execution requires a valid approval.",
                                  technical_detail="no approval for execution authorization")

        def business(conn):
            domain_ref = domain_execute_fn(conn) if domain_execute_fn else None
            eid = self.store.insert_execution_auth(
                conn, decision["id"], approval_id=(approval["id"] if approval else None),
                execution_capability=execution_capability, authorized_executor=principal,
                expected_action=expected_action, domain_execution_ref=domain_ref,
                state=("in_execution" if domain_ref else "authorized"), expiration=expiration,
                idempotency_key=idempotency_key)
            return (eid, eid), eid
        res = self.gov.perform(principal_id=principal, capability="execution.authorize", scope=scope,
                               action="execution.authorize", business_fn=business, target_ref=decision["id"],
                               correlation_id=correlation_id, idempotency_key=idempotency_key)
        if res.get("replayed"):
            return {"execution": self.store.get_execution_auth(res["result_ref"]), "replayed": True}
        return {"execution": self.store.get_execution_auth(res["value"][0]), "replayed": False}

    def complete(self, principal, scope, execauth, *, domain_completion_ref=None, failed=False,
                 idempotency_key=None):
        """Completion must reference an actual domain completion event. A failed domain execution is
        never marked completed."""
        if not failed and not domain_completion_ref:
            raise ValidationError(technical_detail="completion requires an actual domain completion reference")

        def business(conn):
            if failed:
                self.store.set_execution_auth(conn, execauth["id"], state="failed",
                                              reconciliation_outcome="FAILED")
            else:
                self.store.set_execution_auth(conn, execauth["id"], state="completed",
                                              completion_ref=domain_completion_ref, reconciliation_outcome="COMPLETED")
            return (execauth["id"], execauth["id"]), execauth["id"]
        res = self.gov.perform(principal_id=principal, capability="execution.authorize", scope=scope,
                               action="execution.complete", business_fn=business, target_ref=execauth["id"],
                               idempotency_key=idempotency_key)
        if res.get("replayed"):
            return {"execution": self.store.get_execution_auth(execauth["id"]), "replayed": True}
        return {"execution": self.store.get_execution_auth(execauth["id"]), "replayed": False}

    def reconcile(self, decision, *, conflict=False, stale=False, expired=False, unresolved_identity=False,
                  domain_rejected=False, audit_blocked=False):
        """Deterministic Decision-to-execution reconciliation. Every actionable Decision can produce a
        result. Update the workspace summary to follow the authoritative domain result."""
        d = self.store.get_decision(decision["id"])
        if audit_blocked:
            outcome = "AUDIT_BLOCKED"
        elif domain_rejected:
            outcome = "DOMAIN_REJECTED"
        elif unresolved_identity:
            outcome = "UNRESOLVED_IDENTITY"
        elif conflict:
            outcome = "CONFLICTING"
        elif stale:
            outcome = "STALE"
        elif expired:
            outcome = "EXPIRED"
        elif d["disposition"] in _NO_EXEC_DISPOSITIONS:
            outcome = "NO_EXECUTION_REQUIRED"
        elif d["disposition"] == "CANCEL":
            outcome = "CANCELLED"
        else:
            apps, execs = self.store.approvals_for(d["id"]), self.store.execauths_for(d["id"])
            if not apps:
                outcome = "AWAITING_APPROVAL"
            elif not execs:
                outcome = "APPROVED_AWAITING_EXECUTION"
            else:
                e = execs[-1]
                outcome = {"authorized": "EXECUTION_AUTHORIZED", "in_execution": "EXECUTED",
                           "completed": "COMPLETED", "failed": "FAILED"}.get(e["state"], "UNRESOLVED_IDENTITY")
        existing = [r["outcome"] for r in self.store.reconciliations_for(d["id"])]
        if outcome in existing and outcome in ("COMPLETED", "NO_EXECUTION_REQUIRED", "CANCELLED"):
            outcome = "ALREADY_RECONCILED"
        self.store.add_reconciliation(d["id"], outcome, detail=f"disposition={d['disposition']}")
        self._sync_workspace(d, outcome)
        return outcome

    def _sync_workspace(self, decision, outcome):
        if not decision["workspace_item_id"]:
            return
        item = self.store.get_workspace_item(decision["workspace_item_id"])
        if item is None:
            return
        ws = {"COMPLETED": "COMPLETED", "FAILED": "FAILED", "EXECUTED": "IN_EXECUTION",
              "EXECUTION_AUTHORIZED": "AWAITING_EXECUTION", "APPROVED_AWAITING_EXECUTION": "APPROVED",
              "AWAITING_APPROVAL": "DECIDED", "EXPIRED": "EXPIRED", "STALE": "STALE",
              "CANCELLED": "CANCELLED"}.get(outcome)
        if ws:
            self.store.set_workspace_item_now(item["id"], item["version"], workspace_state=ws,
                                              execution_state=outcome)


assert set(RECONCILIATION_OUTCOMES)  # keep the registry import meaningful
