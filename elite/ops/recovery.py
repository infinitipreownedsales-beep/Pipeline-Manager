"""Restart and crash recovery.

On restart the durable store is intact: a committed transaction stays committed, and a rolled-back
transaction left no partial authoritative state (Phase 2 ingestion and the Phase 1 Governor are atomic).
This service reconciles any import run that was left mid-flight by an interruption: a run stuck in a
non-terminal state (RECEIVED / VALIDATING / VALIDATED / INGESTING / RECONCILING) becomes FAILED and
reviewable, recording the stage it was interrupted at. Recovery never deletes evidence and never replays
a completed effect.
"""
from __future__ import annotations

from .models import IMPORT_TERMINAL

_INFLIGHT = {"RECEIVED", "VALIDATING", "VALIDATED", "INGESTING", "RECONCILING"}


class RecoveryService:
    def __init__(self, ops_store, clock, logger=None):
        self.ops, self.clock, self.logger = ops_store, clock, logger

    def recover(self, source_id=None, scope=None):
        """Mark any in-flight import run as interrupted/FAILED (reviewable). Idempotent: a run already
        terminal is left untouched, so calling recover twice replays nothing."""
        recovered = []
        for r in self.ops.list_import_runs(source_id, scope):
            if r["state"] in _INFLIGHT and r["state"] not in IMPORT_TERMINAL:
                self.ops.add_import_error(r["id"], r["state"], "interrupted",
                                          "The import was interrupted by a restart and did not complete.")
                self.ops.update_import_run(r["id"], state="FAILED", failure_stage=r["state"],
                                           error_class="interrupted", completed_at=self.ops._now())
                recovered.append(self.ops.get_import_run(r["id"]))
                if self.logger:
                    self.logger.op("recovery", "recovery.import", result="marked_failed",
                                   run_id=r["id"], stage=r["state"])
        return recovered

    def recovery_status(self, scope=None):
        runs = self.ops.list_import_runs(scope=scope)
        inflight = [r["id"] for r in runs if r["state"] in _INFLIGHT]
        return {"in_flight": inflight,
                "completed": [r["id"] for r in runs if r["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")],
                "failed": [r["id"] for r in runs if r["state"] == "FAILED"]}
