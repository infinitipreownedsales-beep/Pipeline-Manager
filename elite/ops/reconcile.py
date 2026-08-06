"""Operational reconciliation + drift detection.

Reconciles source rows against accepted Business Facts, identities, and domain projections, referencing
the EXACT source and domain records. A difference is recorded as evidence — it never auto-corrects a
domain record. Full/Partial Snapshot semantics from Phase 2 are preserved (a Full-Snapshot absence yields
MISSING_EXPECTED, never a deletion). One physical unit is never duplicated by reconciliation. Where the
cause of a difference is not determinable it stays UNRESOLVED / unknown.
"""
from __future__ import annotations

# Phase 2 reconciliation outcome -> operational (Phase 11) outcome + likely cause.
_MAP = {
    "matched": ("MATCHED", ""),
    "created": ("NEW", ""),
    "distinct": ("NEW", ""),
    "accepted": ("MATCHED", ""),
    "duplicate": ("DUPLICATE", "data"),
    "conflicting": ("CONFLICTING", "identity_or_data"),
    "unresolved": ("IDENTITY_UNRESOLVED", "identity"),
    "rejected": ("UNRESOLVED", "data"),
    "quarantined": ("UNRESOLVED", "data"),
    "absent_in_full_snapshot": ("MISSING_EXPECTED", "absence"),
}


class OperationalReconciler:
    def __init__(self, ops_store, data_store, clock):
        self.ops, self.data, self.clock = ops_store, data_store, clock

    def reconcile_batch(self, *, import_run_id, batch, source_id, scope, domain):
        """Translate the Phase 2 per-row reconciliation of an ingested batch into operational
        reconciliation evidence. Returns a summary dict. Does not mutate any domain record."""
        rows = self.data.conn.execute(
            "SELECT * FROM reconciliation_result WHERE import_batch_id=?", (batch.id,)).fetchall()
        summary = {}
        for r in rows:
            outcome, cause = _MAP.get(r["outcome"], ("UNRESOLVED", "unknown"))
            candidates = r["candidate_entities"]
            subject_ref = None
            if candidates:
                import json as _json
                try:
                    c = _json.loads(candidates)
                    subject_ref = c[0] if c else None
                except Exception:
                    subject_ref = None
            fact_ref = None
            if r["resulting_fact_refs"]:
                import json as _json
                try:
                    fr = _json.loads(r["resulting_fact_refs"])
                    fact_ref = fr[0] if fr else None
                except Exception:
                    fact_ref = None
            self.ops.add_reconciliation(
                import_run_id=import_run_id, source_id=source_id, store_scope=scope, domain=domain,
                subject_ref=subject_ref, source_record_ref=r["source_observation_id"],
                domain_record_ref=fact_ref, outcome=outcome, cause=cause,
                detail=(r["reason"] or None))
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary

    def drift_vs_prior(self, *, import_run_id, source_id, scope, domain, current_subjects, prior_subjects):
        """Record subject-level drift between this import and the prior accepted import (NEW / CHANGED /
        MISSING_EXPECTED / MATCHED). Non-authoritative evidence only."""
        cur, prior = set(current_subjects), set(prior_subjects)
        for s in sorted(cur - prior):
            self.ops.add_reconciliation(import_run_id=import_run_id, source_id=source_id, store_scope=scope,
                                        domain=domain, subject_ref=s, outcome="NEW", cause="")
        for s in sorted(prior - cur):
            self.ops.add_reconciliation(import_run_id=import_run_id, source_id=source_id, store_scope=scope,
                                        domain=domain, subject_ref=s, outcome="MISSING_EXPECTED", cause="absence")
        for s in sorted(cur & prior):
            self.ops.add_reconciliation(import_run_id=import_run_id, source_id=source_id, store_scope=scope,
                                        domain=domain, subject_ref=s, outcome="MATCHED", cause="")
