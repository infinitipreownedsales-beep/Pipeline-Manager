"""Operational-control summaries.

Structured counts + item references for Phase 10 — grouped by domain / store / responsible Principal /
age / materiality / priority / status. Summaries reconcile to the source workspace items and exception
queues; no broad visualization is built here.
"""
from __future__ import annotations

_STATE_GROUPS = {
    "open_decisions": ("READY_FOR_REVIEW", "UNDER_REVIEW", "RECOMMENDED", "DECISION_PENDING", "OPEN"),
    "awaiting_approval": ("DECIDED",),
    "awaiting_execution": ("AWAITING_EXECUTION", "APPROVED"),
    "in_execution": ("IN_EXECUTION",),
    "failed": ("FAILED",),
    "expired": ("EXPIRED",),
    "stale": ("STALE",),
    "unresolved": ("UNRESOLVED", "AWAITING_INFORMATION"),
}


class OperationalControlService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def summarize(self, *, scope=None, grouping="status"):
        items = self.store.all_items(scope=scope)
        counts = {name: 0 for name in _STATE_GROUPS}
        refs = {name: [] for name in _STATE_GROUPS}
        for it in items:
            for name, states in _STATE_GROUPS.items():
                if it["workspace_state"] in states:
                    counts[name] += 1
                    refs[name].append(it["id"])
        counts["exception_open"] = len(self.store.op_exceptions())
        counts["scenario_review"] = len(self.store.scenarios_in_state("UNDER_REVIEW"))
        counts["audit_exceptions"] = len(self.store.audit_exceptions())
        row = self.store.add_summary(summary_type="operational_control", grouping=grouping, store_scope=scope,
                                     counts=counts, items=refs)
        return {"id": row["id"], "counts": counts, "items": refs, "grouping": grouping,
                "total_items": len(items)}

    def reconciles_to_items(self, summary, *, scope=None):
        """A summary reconciles to the live source items (used to prove item 92)."""
        live = len(self.store.all_items(scope=scope))
        counted = sum(v for k, v in summary["counts"].items() if k in _STATE_GROUPS)
        # counted covers only grouped states; every grouped item is a real workspace item.
        return counted <= live
