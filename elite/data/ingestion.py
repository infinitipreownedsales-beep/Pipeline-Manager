"""Import Batch ingestion + reconciliation.

Turns a received payload into an Import Batch, preserved Source Observations
(raw + normalized), resolved identities, accepted Business Facts, and a
reconciliation outcome for EVERY source row. Upload/parse success is never
acceptance. Replay is idempotent; a corrected replay preserves prior history.
Snapshot semantics are contract-driven; a Full Snapshot's absence only yields a
scoped reconciliation signal, never a removal or invented lifecycle fact.
"""
from __future__ import annotations

import hashlib

from ..clock import to_utc_iso
from ..errors import ValidationError
from ..ids import new_id
from . import identity as idres
from .contracts import classify_snapshot, validate_row
from .models import ImportBatch, ReconciliationResult, SourceObservation
from .normalize import Special, vin_status


def checksum(raw_text: str) -> str:
    return "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


# Entity kinds that assert a PHYSICAL identity — a real unit/order that ingestion resolves (and, when new,
# creates) via VIN / manufacturer-order-id. Every OTHER entity_kind is observation-only: its rows are
# retained verbatim as immutable Source Observations and NEVER cause a VehicleUnit / ProductionOrder /
# business fact to be created, even when a VIN is present. Physical-identity assertion (and duplicate-VIN
# collapse) is reserved for sources that genuinely describe physical inventory; observation-only demand /
# pipeline evidence (e.g. Speed-to-Sell, DMS pipeline summaries) is reconciled downstream in the derived
# demand/supply bridges, never destroyed at ingestion.
_PHYSICAL_ENTITY_KINDS = frozenset({"vehicle", "order"})


def _record_identity(entity_kind, row, normalized, stock_identity=True):
    if entity_kind == "order":
        moid = normalized.get("manufacturer_order_id")
        if isinstance(moid, str) and moid:
            return "moid:" + moid
    vin = normalized.get("vin")
    if isinstance(vin, str) and vin_status(vin) == "valid":
        return "vin:" + vin
    # stock_number is an identity/dedup fallback ONLY where the source contract declares it identity-bearing.
    # A source that reuses placeholder stock numbers (e.g. "75" across many distinct vehicles) passes
    # stock_identity=False so those rows never collapse to a single stock:<value> key.
    if stock_identity:
        for k in ("stock_number", "stock", "id"):
            if isinstance(row.get(k), str) and row.get(k).strip():
                return f"{k}:" + row[k].strip()
    return None


class IngestionService:
    def __init__(self, store, facts, clock):
        self.store, self.facts, self.clock = store, facts, clock

    def ingest(self, *, source_id, profile_version, rows, raw_text, scope,
               entity_kind="vehicle", fact_type=None, claimed_snapshot="partial",
               correlation_id=None, effective_time=None, correction_of=None, stock_identity=True,
               observed_time=None, snapshot_business_date=None, snapshot_tz="America/Chicago"):
        source = self.store.get_source(source_id)
        if source is None:
            raise ValidationError(technical_detail=f"unknown source {source_id}")
        profile = self.store.get_profile(source_id, profile_version)
        if profile is None:
            raise ValidationError(technical_detail=f"unknown schema profile {source_id} v{profile_version}")

        cs = checksum(raw_text)
        if correction_of is None:
            # A longitudinal-snapshot source (snapshot_business_date supplied) dedups per (source, scope,
            # business date, content) so an identical export on a later business day is a new snapshot;
            # every other source keeps pure content-hash replay (unchanged behavior).
            if snapshot_business_date is not None:
                prior = self.store.find_completed_batch_for_business_date(
                    source_id, scope, cs, snapshot_business_date, snapshot_tz)
            else:
                prior = self.store.find_completed_batch(source_id, scope, cs)
            if prior is not None:
                return prior            # idempotent: exact replay, no new official effect

        validated_snapshot, note = classify_snapshot(profile, claimed_snapshot, len(rows))
        batch = self.store.add_batch(ImportBatch(
            id=new_id("imb"), source_id=source_id, schema_profile_version=profile_version, payload_checksum=cs,
            received_at=to_utc_iso(self.clock.now()), store_scope=scope, claimed_snapshot_type=claimed_snapshot,
            validated_snapshot_type=validated_snapshot, lifecycle_status="received", row_count=len(rows),
            effective_time=effective_time, correlation_id=correlation_id, replay_of=correction_of, detail=note))
        self.store.add_payload(cs, raw_text, batch.id)

        counts = dict(accepted=0, rejected=0, quarantined=0, duplicate=0, conflicting=0, unresolved=0)
        seen = {}                 # record identity -> normalized values (within-batch dedup)
        observed_subjects = set()

        for i, row in enumerate(rows):
            vstatus, normalized = validate_row(profile, row)
            obs = self.store.add_observation(SourceObservation(
                id=new_id("obs"), import_batch_id=batch.id, raw_values=row, normalized_values=normalized,
                recorded_time=to_utc_iso(self.clock.now()), validation_status=vstatus, acceptance_status="pending",
                source_scope=scope, observed_time=observed_time,
                source_record_identity=_record_identity(entity_kind, row, normalized, stock_identity),
                provenance={"source": source_id, "batch": batch.id, "row": i}))

            outcome, acceptance, fact_refs, candidates = self._reconcile_row(
                source, profile, entity_kind, fact_type, scope, row, normalized, vstatus, obs, seen,
                observed_subjects, effective_time, stock_identity)

            obs.acceptance_status = acceptance
            self.store.conn.execute("UPDATE source_observation SET acceptance_status=?, identity_status=? WHERE id=?",
                                    (acceptance, outcome, obs.id))
            self.store.add_recon(ReconciliationResult(
                id=new_id("rec"), import_batch_id=batch.id, source_observation_id=obs.id, outcome=outcome,
                recorded_at=to_utc_iso(self.clock.now()), candidate_entities=candidates,
                resulting_fact_refs=fact_refs, reason=vstatus if vstatus != "valid" else ""))
            bucket = {"matched": "accepted", "created": "accepted", "distinct": "accepted",
                      "accepted": "accepted", "observation": "accepted"}.get(outcome, outcome)
            counts[bucket] = counts.get(bucket, 0) + 1

        # Full Snapshot absence: only a scoped reconciliation SIGNAL, never a removal.
        if validated_snapshot == "full" and fact_type:
            known = self._known_subjects(fact_type, scope)
            for subj in known - observed_subjects:
                self.store.add_recon(ReconciliationResult(
                    id=new_id("rec"), import_batch_id=batch.id, source_observation_id=None,
                    outcome="absent_in_full_snapshot", recorded_at=to_utc_iso(self.clock.now()),
                    candidate_entities=[subj], reason="present in prior current facts, absent from this full snapshot"))
            if known and len(observed_subjects) < 0.5 * len(known):
                note = (note + " | " if note else "") + "suspicious population reduction: review required"

        batch.accepted_count = counts["accepted"]; batch.rejected_count = counts["rejected"]
        batch.quarantined_count = counts["quarantined"]; batch.duplicate_count = counts["duplicate"]
        batch.conflicting_count = counts["conflicting"]; batch.unresolved_count = counts["unresolved"]
        batch.validated_snapshot_type = validated_snapshot
        batch.detail = note
        batch.lifecycle_status = "completed"
        self.store.update_batch(batch)
        return self.store.get_batch(batch.id)

    def _reconcile_row(self, source, profile, entity_kind, fact_type, scope, row, normalized,
                       vstatus, obs, seen, observed_subjects, effective_time, stock_identity=True):
        if vstatus == "rejected":
            return "rejected", "rejected", [], []
        if vstatus == "quarantined":
            # Validation applies before physical-vs-observation identity semantics. An
            # observation-only source must preserve malformed rows as quarantined evidence,
            # never promote them to accepted evidence merely because no physical identity is resolved.
            return "quarantined", "quarantined", [], []
        # Observation-only source (non-physical entity_kind): retain the valid row as immutable evidence
        # with NO physical-identity resolution. This creates no VehicleUnit / ProductionOrder / business
        # fact even when the row carries a VIN (the VIN stays verbatim in the stored observation for the
        # derived demand/supply bridges). Duplicate-VIN reconciliation is a derived concern, never collapsed here.
        if entity_kind not in _PHYSICAL_ENTITY_KINDS:
            return "observation", "accepted", [], []
        key = _record_identity(entity_kind, row, normalized, stock_identity)
        if key is not None and key in seen:
            return ("duplicate", "duplicate", [], []) if seen[key] == normalized \
                else ("conflicting", "conflicting", [], [])
        if key is not None:
            seen[key] = normalized

        if entity_kind == "order":
            status, entity, _ = idres.resolve_production_order(
                self.store, normalized.get("manufacturer_order_id"), normalized.get("vin"), scope,
                source_ref=source.id, record_ref=obs.id)
        else:
            status, entity, _ = idres.resolve_vehicle(self.store, normalized.get("vin"), scope,
                                                       source_ref=source.id, record_ref=obs.id)
        if status == idres.UNRESOLVED or entity is None:
            return "unresolved", "unresolved", [], []
        candidates = [entity.id]
        if vstatus == "quarantined":       # structurally ok but has invalid values -> not fact-eligible
            return "quarantined", "quarantined", [], candidates
        observed_subjects.add(entity.id)
        fact_refs = []
        if fact_type and source.is_authoritative(fact_type, scope):
            f = self.facts.create(source=source, fact_type=fact_type, subject_type=entity_kind,
                                  subject_id=entity.id, payload={k: _plain(v) for k, v in normalized.items()},
                                  scope=scope, observation_refs=[obs.id], effective_time=effective_time)
            fact_refs = [f.id]
        return status, "accepted", fact_refs, candidates

    def _known_subjects(self, fact_type, scope):
        rows = self.store.conn.execute(
            "SELECT DISTINCT subject_entity_id FROM business_fact WHERE fact_type=? AND store_scope=?"
            " AND status='current'", (fact_type, scope)).fetchall()
        return {r["subject_entity_id"] for r in rows}


def _plain(v):
    return {"__special__": v.value} if isinstance(v, Special) else v
