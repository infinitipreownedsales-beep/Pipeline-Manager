"""Import orchestration — an authoritative import-run service.

Drives a single source payload through the state machine
RECEIVED -> VALIDATING -> VALIDATED -> INGESTING -> INGESTED -> RECONCILING ->
COMPLETED / COMPLETED_WITH_WARNINGS, with REJECTED / FAILED / CANCELLED / SUPERSEDED as needed.

Guarantees:
  * Same file content is idempotent (a prior COMPLETED run with the same content hash short-circuits;
    Phase 2 ingestion is itself idempotent, so replay never duplicates facts).
  * A failed import preserves the prior accepted state (Phase 2 ingestion is atomic; on interruption
    before or during acceptance nothing is committed).
  * Partial ingestion never masquerades as complete (only INGESTED->RECONCILING->COMPLETED reaches a
    completed state; a failure lands in FAILED, never COMPLETED).
  * A retry links to the failed run via retry_of.
  * The operator sees a safe, actionable failure (import_run_error holds a safe message, never a secret
    or a raw customer row).
"""
from __future__ import annotations

from ..errors import EliteError
from .adapters import run_adapter
from .contracts import get_contract
from .models import IMPORT_ACCEPTED
from .reconcile import OperationalReconciler


class ImportInterrupted(Exception):
    """Test/operational hook used to simulate a crash at a named stage (no real effect leaks)."""


class ImportOrchestrator:
    def __init__(self, ops_store, ingestion, data_store, clock, logger=None):
        self.ops = ops_store
        self.ingestion = ingestion
        self.data = data_store
        self.clock = clock
        self.logger = logger
        self.reconciler = OperationalReconciler(ops_store, data_store, clock)

    # -- helpers ---------------------------------------------------------------
    def _last_completed(self, source_id, scope):
        runs = [r for r in self.ops.list_import_runs(source_id, scope)
                if r["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")]
        return runs[-1]["id"] if runs else None

    def _fail(self, run, stage, err, correlation_id):
        safe = err.message if isinstance(err, EliteError) else "An unexpected import error occurred."
        cls = err.category if isinstance(err, EliteError) else type(err).__name__
        self.ops.add_import_error(run["id"], stage, cls, safe, correlation_id)
        self.ops.update_import_run(run["id"], state="FAILED", failure_stage=stage, error_class=cls,
                                   completed_at=self.ops._now())
        if self.logger:
            self.logger.op_error("import", "import.run", cls, correlation_id=correlation_id,
                                 stage=stage, run_id=run["id"])
        return self.ops.get_import_run(run["id"])

    # -- main entry ------------------------------------------------------------
    def run(self, *, contract_key, payload=None, rows=None, source_id, scope, initiated_by=None,
            scheduled_actor=None, claimed_snapshot="partial", effective_time=None, correlation_id=None,
            file_receipt_id=None, content_hash=None, retry_of=None, correction_of=None, fail_at=None):
        contract = get_contract(contract_key)
        if contract is None:
            from ..errors import ValidationError
            raise ValidationError(technical_detail=f"unknown source contract {contract_key}")

        # register adapter version (idempotent)
        self.ops.add_adapter_version(f"{contract.key}.{contract.file_kind}", 1,
                                     source_family=contract.key, file_kind=contract.file_kind,
                                     description=f"adapter for {contract.key}",
                                     transforms_doc="strip/whitespace; declared-numeric currency cleanup")

        # Longitudinal-snapshot sources anchor idempotency on the local business date. Resolve the
        # observation time once (trustworthy DMS/export as-of -> FileIntake receipt -> import time) and
        # thread it consistently into the run, batch, and observations. Other sources are unaffected.
        snapshot_tz = "America/Chicago"
        snapshot_bdate = None
        if getattr(contract, "snapshot_idempotency", "content_hash") == "content_hash_per_business_date":
            from ..clock import local_business_date
            obs_ts = effective_time
            if obs_ts is None and file_receipt_id:
                receipt = self.ops.get_file_receipt(file_receipt_id)
                if receipt is not None:
                    obs_ts = receipt["received_at"]
            if obs_ts is None:
                obs_ts = self.ops._now()
            effective_time = obs_ts
            snapshot_bdate = local_business_date(obs_ts, snapshot_tz)

        # idempotency: a prior COMPLETED run with the same content short-circuits (no new facts). For a
        # longitudinal-snapshot source the match additionally requires the same local business date.
        if content_hash and correction_of is None and retry_of is None:
            if snapshot_bdate is not None:
                prior = self.ops.find_import_run_by_hash_and_business_date(
                    source_id, scope, content_hash, snapshot_bdate, snapshot_tz)
            else:
                prior = self.ops.find_import_run_by_hash(source_id, scope, content_hash)
            if prior is not None:
                if self.logger:
                    self.logger.op("import", "import.run", result="idempotent_replay",
                                   correlation_id=correlation_id, run_id=prior["id"])
                return prior

        prior_valid = self._last_completed(source_id, scope)
        run = self.ops.add_import_run(
            source_id=source_id, source_contract=contract_key,
            adapter_key=f"{contract.key}.{contract.file_kind}", adapter_version=1,
            file_receipt_id=file_receipt_id, content_hash=content_hash, store_scope=scope,
            initiated_by=initiated_by, scheduled_actor=scheduled_actor, state="RECEIVED",
            source_effective_time=effective_time, correlation_id=correlation_id, retry_of=retry_of,
            prior_valid_state_ref=prior_valid, started_at=self.ops._now())

        # ---- VALIDATING ----
        self.ops.update_import_run(run["id"], state="VALIDATING")
        try:
            if fail_at == "validate":
                raise ImportInterrupted("interrupted during validation")
            adapter = run_adapter(contract, payload if payload is not None else rows,
                                  file_kind=contract.file_kind)
        except EliteError as e:
            # a structurally invalid / unsupported file is REJECTED (not a crash)
            self.ops.add_import_error(run["id"], "VALIDATING", e.category, e.message, correlation_id)
            self.ops.update_import_run(run["id"], state="REJECTED", failure_stage="VALIDATING",
                                       error_class=e.category, completed_at=self.ops._now())
            if self.logger:
                self.logger.op_error("import", "import.run", e.category, correlation_id=correlation_id,
                                     stage="VALIDATING", run_id=run["id"])
            return self.ops.get_import_run(run["id"])
        except Exception as e:
            return self._fail(run, "VALIDATING", e, correlation_id)

        self.ops.update_import_run(run["id"], state="VALIDATED", row_count=len(adapter.rows))

        # ---- INGESTING (acceptance) ----
        self.ops.update_import_run(run["id"], state="INGESTING")
        try:
            if fail_at in ("ingest", "before_acceptance"):
                # interruption BEFORE acceptance: never call ingestion -> no facts accepted.
                raise ImportInterrupted("interrupted before acceptance")
            batch = self.ingestion.ingest(**adapter.ingest_kwargs(
                source_id=source_id, scope=scope, entity_kind=contract.entity_kind,
                fact_type=contract.fact_type, claimed_snapshot=claimed_snapshot,
                effective_time=effective_time, correlation_id=correlation_id, correction_of=correction_of,
                observed_time=(effective_time if snapshot_bdate is not None else None),
                snapshot_business_date=snapshot_bdate, snapshot_tz=snapshot_tz))
        except EliteError as e:
            return self._fail(run, "INGESTING", e, correlation_id)
        except Exception as e:
            return self._fail(run, "INGESTING", e, correlation_id)

        self.ops.update_import_run(
            run["id"], state="INGESTED", import_batch_id=batch.id, row_count=batch.row_count,
            accepted_count=batch.accepted_count, rejected_count=batch.rejected_count,
            duplicate_count=batch.duplicate_count, unresolved_count=batch.unresolved_count)

        # ---- RECONCILING ----
        self.ops.update_import_run(run["id"], state="RECONCILING")
        try:
            if fail_at == "reconcile":
                raise ImportInterrupted("interrupted during reconciliation")
            summary = self.reconciler.reconcile_batch(
                import_run_id=run["id"], batch=batch, source_id=source_id, scope=scope,
                domain=contract.domain)
        except Exception as e:
            # facts are already atomically accepted (INGESTED); the run is FAILED, never COMPLETED.
            return self._fail(run, "RECONCILING", e, correlation_id)

        warnings = (batch.rejected_count + batch.duplicate_count + batch.conflicting_count
                    + batch.unresolved_count) > 0 or "MISSING_EXPECTED" in summary
        final_state = "COMPLETED_WITH_WARNINGS" if warnings else "COMPLETED"
        recon_status = "warnings" if warnings else "clean"
        self.ops.update_import_run(run["id"], state=final_state, reconciliation_status=recon_status,
                                   completed_at=self.ops._now())
        if self.logger:
            self.logger.op("import", "import.run", result=final_state.lower(),
                           correlation_id=correlation_id, run_id=run["id"],
                           accepted=batch.accepted_count)
        return self.ops.get_import_run(run["id"])

    def retry(self, failed_run_id, **kw):
        """Retry a FAILED/REJECTED run. Links via retry_of. Corrected content (or a fixed file) then
        succeeds; unchanged content that previously failed for data reasons fails again, still linked."""
        failed = self.ops.get_import_run(failed_run_id)
        if failed is None:
            from ..errors import ValidationError
            raise ValidationError(technical_detail=f"unknown import run {failed_run_id}")
        kw.setdefault("contract_key", failed["source_contract"])
        kw.setdefault("source_id", failed["source_id"])
        kw.setdefault("scope", failed["store_scope"])
        return self.run(retry_of=failed_run_id, **kw)

    def cancel(self, run_id, correlation_id=None):
        """Cancel a non-terminal run, preserving history."""
        run = self.ops.get_import_run(run_id)
        if run and run["state"] not in ("COMPLETED", "COMPLETED_WITH_WARNINGS", "REJECTED", "FAILED"):
            self.ops.update_import_run(run_id, state="CANCELLED", completed_at=self.ops._now())
        return self.ops.get_import_run(run_id)

    def accepted_state_intact(self, source_id, scope, expected_last_completed):
        """True if the last COMPLETED run is still the expected one (a failed import did not corrupt it)."""
        return self._last_completed(source_id, scope) == expected_last_completed
