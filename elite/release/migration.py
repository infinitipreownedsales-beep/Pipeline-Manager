"""Real-data migration engine.

Live-source connection inventory (real availability; unavailable sources classified, never fabricated);
real adapter configuration (registered schema versions, reviewable mappings, corrections -> new version);
controlled real-source ingestion into a DEDICATED migration/pilot database (never production-primary);
real identity migration (9 outcomes; one physical unit = one Vehicle Unit; pre-VIN -> VIN never duplicates;
conflicts blocked; governed manual resolution); real historical-data migration (no invented events;
snapshot history is not false continuous availability; migration date is not event date; totals reconcile);
governed policy + authority migration (from confirmed values only; missing blocks; no overgrant); and real
domain-state reconstruction from accepted real facts.
"""
from __future__ import annotations

from ..errors import AuthorizationError, ValidationError
from .models import (CAPS, IDENTITY_OUTCOMES, IDENTITY_BLOCKING, SOURCE_CLASSES, SOURCE_INGESTIBLE)


class MigrationEngine:
    def __init__(self, release_store, ops, stack, clock, logger=None):
        self.store = release_store          # ReleaseStore
        self.ops = ops                      # Phase11 stack (orch/ingestion/data/ops)
        self.stack = stack
        self.clock = clock
        self.logger = logger

    # ---- live-source inventory ----------------------------------------------
    def record_connection(self, *, source_family, classification, actual_system=None, source_owner=None,
                          access_method=None, availability=None, integration_status=None,
                          unresolved_blocker=None, **kw):
        if classification not in SOURCE_CLASSES:
            raise ValidationError(technical_detail=f"unknown source classification {classification}")
        return self.store.add_connection(
            source_family=source_family, classification=classification, actual_system=actual_system,
            source_owner=source_owner, access_method=access_method, availability=availability,
            integration_status=integration_status, unresolved_blocker=unresolved_blocker, **kw)

    def ingestible(self, connection):
        return connection["classification"] in SOURCE_INGESTIBLE

    # ---- adapter configuration ----------------------------------------------
    def register_schema(self, source_family, version, *, schema=None, mapping=None):
        return self.store.add_schema_version(source_family, version, schema_json=schema, mapping_json=mapping)

    def correct_adapter(self, source_family, new_version, *, schema=None, mapping=None):
        """A corrected adapter is a NEW version; prior versions remain (replayable)."""
        prior = self.store.schema_versions(source_family)
        row = self.store.add_schema_version(source_family, new_version, schema_json=schema, mapping_json=mapping)
        return row, [r["version"] for r in prior]

    # ---- migration run + real ingestion -------------------------------------
    def start_run(self, *, initiated_by, target_db="migration.db", environment="migration", correlation_id=None):
        return self.store.add_migration_run(initiated_by=initiated_by, target_db=target_db,
                                            environment=environment, state="STARTED", correlation_id=correlation_id)

    def migrate_source(self, migration_run_id, *, contract_key, payload, source_family, scope,
                       claimed_snapshot="partial", effective_time=None, content_hash=None,
                       correction_of=None, fail_at=None, correlation_id=None):
        """Import a real source through the Phase 11 adapter + orchestrator into the dedicated migration db,
        then record migration_run_source + per-fact reconciliation. Idempotent; failed preserves prior."""
        run = self.ops.import_payload(contract_key, payload, claimed_snapshot=claimed_snapshot,
                                      effective_time=effective_time, chash=content_hash,
                                      correction_of=correction_of, fail_at=fail_at)
        batch = None
        if run["import_batch_id"]:
            batch = self.ops.data.get_batch(run["import_batch_id"])
        self.store.add_run_source(
            migration_run_id=migration_run_id, source_family=source_family,
            import_run_ref=run["id"], content_hash=run["content_hash"], row_count=run["row_count"],
            accepted_count=run["accepted_count"], rejected_count=run["rejected_count"],
            snapshot_type=(batch.validated_snapshot_type if batch else None), outcome=run["state"])
        # per-fact reconciliation evidence
        if batch is not None:
            for r in self.ops.data.conn.execute(
                    "SELECT * FROM reconciliation_result WHERE import_batch_id=?", (batch.id,)).fetchall():
                self.store.add_fact_recon(
                    migration_run_id=migration_run_id, fact_type=contract_key, subject_ref=None,
                    source_row_ref=r["source_observation_id"], resulting_fact_ref=None,
                    outcome=r["outcome"], cause=(r["reason"] or None))
        return run

    # ---- identity migration -------------------------------------------------
    def migrate_identity(self, migration_run_id, *, subject_kind, source_key, existing_ref=None,
                         prevIN_of=None, duplicate_of=None, conflict=False, invalid=False,
                         evidence=None):
        """Deterministic identity reconciliation. One physical unit stays one Vehicle Unit; a pre-VIN order
        transitioning to a VIN stays one future identity; conflicts stay unresolved."""
        if invalid:
            outcome, ref = "EXCLUDED_INVALID", None
        elif conflict:
            outcome, ref = "CONFLICTING_IDENTITY", None
        elif duplicate_of is not None:
            outcome, ref = "DUPLICATE_RECONCILED", duplicate_of
        elif prevIN_of is not None:
            outcome, ref = "PREVIN_LINKED_TO_VIN", prevIN_of
        elif existing_ref is not None:
            outcome, ref = "MATCHED_EXISTING", existing_ref
        else:
            outcome, ref = "CREATED_CANONICAL", "vu:" + str(source_key)
        return self.store.add_identity_recon(
            migration_run_id=migration_run_id, subject_kind=subject_kind, source_key=source_key,
            resolved_entity_ref=ref, outcome=outcome, evidence=evidence,
            cause=("identity" if outcome in IDENTITY_BLOCKING else None))

    def resolve_identity_manually(self, *, principal, scope, migration_run_id, source_key, resolved_entity_ref,
                                  reason, subject_kind="vehicle", correlation_id=None):
        """Manual identity resolution requires authority, a reason, and an Audit Event (governed)."""
        if not reason:
            raise ValidationError(technical_detail="manual identity resolution requires a reason")

        def business(conn):
            from ..ids import new_id
            rid = new_id("mir")
            conn.execute(
                "INSERT INTO migration_identity_reconciliation(id,migration_run_id,subject_kind,source_key,"
                "resolved_entity_ref,outcome,cause,authority,reason,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rid, migration_run_id, subject_kind, source_key, resolved_entity_ref, "CORRECTION_REQUIRED",
                 "manual", principal, reason, self.store._now()))
            return (rid, rid), rid
        res = self.stack.governor.perform(principal_id=principal, capability=CAPS["IDENTITY_RESOLVE"],
                                          scope=scope, action="release.identity.resolve",
                                          business_fn=business, correlation_id=correlation_id)
        # record the audit-linked resolved mapping as a subsequent MATCHED evidence row
        return self.store.add_identity_recon(
            migration_run_id=migration_run_id, subject_kind=subject_kind, source_key=source_key,
            resolved_entity_ref=resolved_entity_ref, outcome="MATCHED_EXISTING", cause=None,
            authority=principal, reason=reason, audit_ref=res.get("audit_id"),
            correction_of="manual:" + str(source_key))

    def unresolved_identities(self, migration_run_id=None):
        return [r for r in self.store.identity_recons(migration_run_id)
                if r["outcome"] in IDENTITY_BLOCKING and not r["audit_ref"]]

    # ---- historical migration -----------------------------------------------
    def migrate_history(self, migration_run_id, *, fact_type, subject_ref, source_row_ref, event_date,
                        migration_date, snapshot=False, duplicate_of=None):
        """Record a historical fact migration. The migration date never replaces the event date; snapshot
        history is flagged (not continuous availability); a duplicate row does not duplicate a fact."""
        if duplicate_of is not None:
            outcome, cause = "DUPLICATE", "data"
        elif snapshot:
            outcome, cause = "SNAPSHOT_POINT", "snapshot"     # a point observation, not continuous
        else:
            outcome, cause = "MIGRATED", None
        detail = f"event_date={event_date}; migration_date={migration_date}; snapshot={int(snapshot)}"
        return self.store.add_fact_recon(
            migration_run_id=migration_run_id, fact_type=fact_type, subject_ref=subject_ref,
            source_row_ref=source_row_ref, resulting_fact_ref=(None if duplicate_of else "fact:" + subject_ref),
            outcome=outcome, cause=cause, detail=detail)

    # ---- policy migration ---------------------------------------------------
    def migrate_policy(self, *, principal, scope, policy_family, proposed_value, owner, evidence,
                       effective_date, authority, conflict_with=None, correlation_id=None):
        """Create a governed policy-resolution record from a CONFIRMED dealership value. A synthetic fixture
        value cannot become official policy (evidence + owner + authority required)."""
        if not (owner and evidence and authority and effective_date):
            raise ValidationError(message="Policy migration requires owner, evidence, authority, effective date.",
                                  technical_detail="synthetic/unattested value cannot become official policy")
        status = "conflicting" if conflict_with else "confirmed"

        def business(conn):
            from ..ids import new_id
            rid = new_id("mpr")
            now = self.store._now()
            conn.execute(
                "INSERT INTO migration_policy_resolution(id,policy_family,proposed_value,owner,evidence,"
                "store_scope,effective_date,authority,status,conflict_with,recorded_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, policy_family, str(proposed_value), owner, evidence, scope, effective_date, authority,
                 status, conflict_with, now, now))
            return (rid, rid), rid
        res = self.stack.governor.perform(principal_id=principal, capability=CAPS["POLICY_MIGRATE"], scope=scope,
                                          action="release.policy.migrate", business_fn=business,
                                          correlation_id=correlation_id)
        return self.store.conn.execute("SELECT * FROM migration_policy_resolution WHERE id=?",
                                       (res["result_ref"],)).fetchone()

    def required_policies_present(self, scope, required_families):
        have = {r["policy_family"] for r in self.store.policy_resolutions(scope) if r["status"] == "confirmed"}
        return [f for f in required_families if f not in have]           # missing families block readiness

    # ---- authority migration ------------------------------------------------
    def migrate_authority(self, *, principal, scope, principal_ref, capability, role=None, grant_scope=None,
                          temporary=False, expires_at=None, correlation_id=None):
        """Grant a real capability at an EXPLICIT scope (governed + audited). Overbroad grants are rejected."""
        grant_scope = grant_scope or scope
        if grant_scope in ("*", "") or capability in ("*", ""):
            raise ValidationError(message="Overbroad authority grant rejected.",
                                  technical_detail=f"explicit scope + capability required (got {grant_scope}/{capability})")
        if temporary and not expires_at:
            raise ValidationError(technical_detail="temporary grant requires an expiry")

        def business(conn):
            from ..ids import new_id, grant_id
            gid = grant_id()
            now = self.store._now()
            # raw grant insert within the governed transaction (no nested transaction)
            conn.execute(
                "INSERT INTO capability_grant(id,principal_id,capability,authority,scope,active,granted_at,"
                "revoked_at,version) VALUES(?,?,?,?,?,?,?,?,?)",
                (gid, principal_ref, capability, principal, grant_scope, 1, now, None, 1))
            rid = new_id("mac")
            conn.execute(
                "INSERT INTO migration_authority_configuration(id,principal_ref,role,capability,store_scope,"
                "grant_ref,status,temporary,expires_at,recorded_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rid, principal_ref, role, capability, grant_scope, gid, "configured",
                 1 if temporary else 0, expires_at, now, now))
            return (rid, gid), rid
        res = self.stack.governor.perform(principal_id=principal, capability=CAPS["AUTHORITY_MIGRATE"], scope=scope,
                                          action="release.authority.migrate", business_fn=business,
                                          correlation_id=correlation_id)
        return self.store.conn.execute("SELECT * FROM migration_authority_configuration WHERE id=?",
                                       (res["result_ref"],)).fetchone()

    # ---- domain-state reconstruction ----------------------------------------
    def reconstruct_domain_state(self, migration_run_id, *, domain, real_fact_refs, output_ref, scope):
        """Record that a domain output was reconstructed from ACCEPTED REAL facts (not synthetic fixtures)."""
        return self.store.add_fact_recon(
            migration_run_id=migration_run_id, fact_type="reconstruct:" + domain, subject_ref=output_ref,
            source_row_ref=",".join(real_fact_refs[:5]), resulting_fact_ref=output_ref,
            outcome="RECONSTRUCTED", cause=None,
            detail=f"domain={domain}; scope={scope}; real_facts={len(real_fact_refs)}")
