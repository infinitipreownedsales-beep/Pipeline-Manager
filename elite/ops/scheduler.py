"""Controlled scheduling for expected imports and operational checks.

Job identity is stable (`job_key`). Firing is idempotent: a second fire for the same scheduled instant
does not repeat the work (guarded by a UNIQUE claim row). An overlapping run does not duplicate work. A
missed run remains visible as evidence. Schedules carry an explicit timezone; clock drift / DST never
silently shift a business-effective period (business-effective time is owned by the source, not the
scheduler). A manual run is distinguishable from a scheduled run (`trigger`). Scheduler failure records a
failed run and never corrupts operational state.
"""
from __future__ import annotations

import sqlite3


class Scheduler:
    def __init__(self, ops_store, clock, logger=None):
        self.ops, self.clock, self.logger = ops_store, clock, logger

    def register(self, job_key, kind, *, cadence=None, timezone="UTC", scope=None, description=None):
        return self.ops.upsert_job(job_key, kind, cadence=cadence, timezone=timezone, scope=scope,
                                   description=description)

    def set_enabled(self, job_key, enabled):
        return self.ops.set_job_enabled(job_key, enabled)

    def fire(self, job_key, scheduled_for, *, trigger="scheduled", work_fn=None, correlation_id=None):
        """Fire a job for a specific scheduled instant. Returns the run row. Idempotent + overlap-safe:
        a duplicate fire for the same (job_key, scheduled_for, trigger) returns the existing run without
        repeating work."""
        job = self.ops.get_job(job_key)
        if job is None:
            raise ValueError(f"unknown job {job_key}")
        if not job["enabled"]:
            return self.ops.add_job_run(job["id"], job_key, scheduled_for, "skipped_disabled", trigger)

        existing = self.ops.find_job_run(job_key, scheduled_for, trigger)
        if existing is not None:
            return existing                          # idempotent / overlap: no duplicate work

        try:
            claim = self.ops.claim_job_run(job["id"], job_key, scheduled_for, trigger, correlation_id)
        except sqlite3.IntegrityError:
            # concurrent claim won the race -> overlap; do not duplicate work
            return self.ops.find_job_run(job_key, scheduled_for, trigger)

        try:
            detail = None
            if work_fn is not None:
                detail = work_fn()
            run = self.ops.finish_job_run(claim["id"], "ran",
                                          detail if isinstance(detail, str) else None)
            if self.logger:
                self.logger.op("scheduler", "scheduler.fire", result="ran", correlation_id=correlation_id,
                               job_key=job_key, trigger=trigger)
            return run
        except Exception as e:
            # scheduler/work failure: record a failed run; operational state is not corrupted
            self.ops.finish_job_run(claim["id"], "failed", type(e).__name__)
            if self.logger:
                self.logger.op_error("scheduler", "scheduler.fire", type(e).__name__,
                                     correlation_id=correlation_id, job_key=job_key)
            return self.ops.conn.execute("SELECT * FROM scheduled_job_run WHERE id=?",
                                         (claim["id"],)).fetchone()

    def run_manual(self, job_key, scheduled_for, *, work_fn=None, correlation_id=None):
        return self.fire(job_key, scheduled_for, trigger="manual", work_fn=work_fn,
                         correlation_id=correlation_id)

    def mark_missed(self, job_key, scheduled_for):
        """Record that an expected scheduled instant did not fire (visible evidence)."""
        job = self.ops.get_job(job_key)
        existing = self.ops.find_job_run(job_key, scheduled_for, "scheduled")
        if existing is not None:
            return existing
        return self.ops.add_job_run(job["id"], job_key, scheduled_for, "missed", "scheduled")

    def detect_missed(self, job_key, expected_instants):
        """Given the instants a job SHOULD have fired at, record any without a run as missed."""
        out = []
        for inst in expected_instants:
            if self.ops.find_job_run(job_key, inst, "scheduled") is None:
                out.append(self.mark_missed(job_key, inst))
        return out
