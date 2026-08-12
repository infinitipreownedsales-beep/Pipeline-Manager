"""SQLite repositories for Phase 2 records. Persistence sits behind these methods;
they can be reimplemented on another store without changing callers. Versioned
records use optimistic concurrency.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..errors import ConcurrencyError, PersistenceError
from .models import (BusinessFact, IdentityEvidence, ImportBatch, ProductionOrder,
                     ReconciliationResult, SchemaProfile, SourceObservation,
                     SourceRegistry, VehicleUnit, FieldSpec)
from .normalize import decode, encode


def _j(v):
    return json.dumps(v)


def _norm_dump(d: dict) -> str:
    return json.dumps({k: encode(v) for k, v in d.items()})


def _norm_load(s: str) -> dict:
    return {k: decode(v) for k, v in json.loads(s).items()}


class DataStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    # ---- source registry / schema profile ---------------------------------
    def add_source(self, s: SourceRegistry) -> SourceRegistry:
        s.registered_at = s.registered_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute(
                "INSERT INTO source_registry(id,name,owner,source_type,supported_profiles,"
                "authoritative_fact_types,scope,status,effective_from,effective_to,registered_at,version)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (s.id, s.name, s.owner, s.source_type, _j(s.supported_profiles),
                 _j(s.authoritative_fact_types), s.scope, s.status, s.effective_from,
                 s.effective_to, s.registered_at, s.version))
        return s

    def get_source(self, source_id):
        r = self.conn.execute("SELECT * FROM source_registry WHERE id=?", (source_id,)).fetchone()
        if not r:
            return None
        return SourceRegistry(id=r["id"], name=r["name"], owner=r["owner"], source_type=r["source_type"],
                              supported_profiles=json.loads(r["supported_profiles"] or "[]"),
                              authoritative_fact_types=json.loads(r["authoritative_fact_types"] or "[]"),
                              scope=r["scope"], status=r["status"], effective_from=r["effective_from"],
                              effective_to=r["effective_to"], registered_at=r["registered_at"], version=r["version"])

    def add_profile(self, p: SchemaProfile) -> SchemaProfile:
        p.created_at = p.created_at or to_utc_iso(self.clock.now())
        fields = [vars(f) for f in p.fields]
        with self.conn:
            self.conn.execute(
                "INSERT INTO schema_profile(id,source_id,version,fields,snapshot_capable,"
                "full_snapshot_requirements,scope_rules,effective_time_rule,compatibility_status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.source_id, p.version, _j(fields), int(p.snapshot_capable),
                 _j(p.full_snapshot_requirements), p.scope_rules, p.effective_time_rule,
                 p.compatibility_status, p.created_at))
        return p

    def get_profile(self, source_id, version):
        r = self.conn.execute("SELECT * FROM schema_profile WHERE source_id=? AND version=?",
                              (source_id, version)).fetchone()
        return self._profile(r)

    @staticmethod
    def _profile(r):
        if not r:
            return None
        return SchemaProfile(id=r["id"], source_id=r["source_id"], version=r["version"],
                             fields=[FieldSpec(**f) for f in json.loads(r["fields"])],
                             snapshot_capable=bool(r["snapshot_capable"]),
                             full_snapshot_requirements=json.loads(r["full_snapshot_requirements"] or "{}"),
                             scope_rules=r["scope_rules"], effective_time_rule=r["effective_time_rule"],
                             compatibility_status=r["compatibility_status"], created_at=r["created_at"])

    # ---- payload + batch ---------------------------------------------------
    def get_payload(self, checksum):
        return self.conn.execute("SELECT * FROM import_payload WHERE checksum=?", (checksum,)).fetchone()

    def add_payload(self, checksum, raw_text, batch_id):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO import_payload(checksum,raw_text,first_batch_id,created_at)"
                              " VALUES(?,?,?,?)", (checksum, raw_text, batch_id, to_utc_iso(self.clock.now())))

    def find_completed_batch(self, source_id, scope, checksum):
        r = self.conn.execute(
            "SELECT * FROM import_batch WHERE source_id=? AND store_scope=? AND payload_checksum=?"
            " AND lifecycle_status='completed' AND replay_of IS NULL ORDER BY received_at LIMIT 1",
            (source_id, scope, checksum)).fetchone()
        return self._batch(r)

    def find_completed_batch_for_business_date(self, source_id, scope, checksum, business_date, tz):
        """Business-date-aware replay lookup (longitudinal-snapshot sources). Mirrors the ops-layer rule so
        the two idempotency layers always agree: a prior COMPLETED batch with identical content is a replay
        only when its observation anchor (effective_time -> received_at) falls on the same local business
        date; a later business day is a new snapshot."""
        from ..clock import local_business_date
        rows = self.conn.execute(
            "SELECT * FROM import_batch WHERE source_id=? AND store_scope=? AND payload_checksum=?"
            " AND lifecycle_status='completed' AND replay_of IS NULL ORDER BY received_at",
            (source_id, scope, checksum)).fetchall()
        for r in rows:
            anchor = r["effective_time"] or r["received_at"]
            if anchor and local_business_date(anchor, tz) == business_date:
                return self._batch(r)
        return None

    def add_batch(self, b: ImportBatch) -> ImportBatch:
        with self.conn:
            self.conn.execute(
                "INSERT INTO import_batch(id,source_id,schema_profile_version,payload_checksum,received_at,"
                "effective_time,store_scope,claimed_snapshot_type,validated_snapshot_type,lifecycle_status,"
                "row_count,accepted_count,rejected_count,quarantined_count,duplicate_count,conflicting_count,"
                "unresolved_count,detail,correlation_id,replay_of) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (b.id, b.source_id, b.schema_profile_version, b.payload_checksum, b.received_at, b.effective_time,
                 b.store_scope, b.claimed_snapshot_type, b.validated_snapshot_type, b.lifecycle_status, b.row_count,
                 b.accepted_count, b.rejected_count, b.quarantined_count, b.duplicate_count, b.conflicting_count,
                 b.unresolved_count, b.detail, b.correlation_id, b.replay_of))
        return b

    def update_batch(self, b: ImportBatch):
        with self.conn:
            self.conn.execute(
                "UPDATE import_batch SET validated_snapshot_type=?,lifecycle_status=?,row_count=?,accepted_count=?,"
                "rejected_count=?,quarantined_count=?,duplicate_count=?,conflicting_count=?,unresolved_count=?,detail=?"
                " WHERE id=?",
                (b.validated_snapshot_type, b.lifecycle_status, b.row_count, b.accepted_count, b.rejected_count,
                 b.quarantined_count, b.duplicate_count, b.conflicting_count, b.unresolved_count, b.detail, b.id))

    def get_batch(self, batch_id):
        return self._batch(self.conn.execute("SELECT * FROM import_batch WHERE id=?", (batch_id,)).fetchone())

    @staticmethod
    def _batch(r):
        if not r:
            return None
        return ImportBatch(id=r["id"], source_id=r["source_id"], schema_profile_version=r["schema_profile_version"],
                           payload_checksum=r["payload_checksum"], received_at=r["received_at"],
                           effective_time=r["effective_time"], store_scope=r["store_scope"],
                           claimed_snapshot_type=r["claimed_snapshot_type"],
                           validated_snapshot_type=r["validated_snapshot_type"], lifecycle_status=r["lifecycle_status"],
                           row_count=r["row_count"], accepted_count=r["accepted_count"], rejected_count=r["rejected_count"],
                           quarantined_count=r["quarantined_count"], duplicate_count=r["duplicate_count"],
                           conflicting_count=r["conflicting_count"], unresolved_count=r["unresolved_count"],
                           detail=r["detail"], correlation_id=r["correlation_id"], replay_of=r["replay_of"])

    # ---- observation -------------------------------------------------------
    def add_observation(self, o: SourceObservation) -> SourceObservation:
        o.recorded_time = o.recorded_time or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute(
                "INSERT INTO source_observation(id,import_batch_id,source_record_identity,raw_values,normalized_values,"
                "observed_time,recorded_time,source_scope,validation_status,identity_status,acceptance_status,"
                "provenance,supersedes_ref,correction_ref) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (o.id, o.import_batch_id, o.source_record_identity, _j(o.raw_values), _norm_dump(o.normalized_values),
                 o.observed_time, o.recorded_time, o.source_scope, o.validation_status, o.identity_status,
                 o.acceptance_status, _j(o.provenance), o.supersedes_ref, o.correction_ref))
        return o

    def get_observation(self, obs_id):
        r = self.conn.execute("SELECT * FROM source_observation WHERE id=?", (obs_id,)).fetchone()
        if not r:
            return None
        return SourceObservation(id=r["id"], import_batch_id=r["import_batch_id"],
                                 source_record_identity=r["source_record_identity"],
                                 raw_values=json.loads(r["raw_values"]), normalized_values=_norm_load(r["normalized_values"]),
                                 observed_time=r["observed_time"], recorded_time=r["recorded_time"],
                                 source_scope=r["source_scope"], validation_status=r["validation_status"],
                                 identity_status=r["identity_status"], acceptance_status=r["acceptance_status"],
                                 provenance=json.loads(r["provenance"] or "{}"), supersedes_ref=r["supersedes_ref"],
                                 correction_ref=r["correction_ref"])

    def list_observations(self, batch_id):
        return [self.get_observation(r["id"]) for r in
                self.conn.execute("SELECT id FROM source_observation WHERE import_batch_id=?", (batch_id,)).fetchall()]

    # ---- vehicle unit / production order / alias ---------------------------
    def add_vehicle(self, v: VehicleUnit) -> VehicleUnit:
        v.created_at = v.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO vehicle_unit(id,vin,identity_status,store_scope,created_at,corrected_at,version)"
                              " VALUES(?,?,?,?,?,?,?)",
                              (v.id, v.vin, v.identity_status, v.store_scope, v.created_at, v.corrected_at, v.version))
        return v

    def find_vehicle_by_vin(self, vin, scope):
        r = self.conn.execute("SELECT * FROM vehicle_unit WHERE vin=? AND store_scope=?", (vin, scope)).fetchone()
        return self._vehicle(r)

    def get_vehicle(self, vid):
        return self._vehicle(self.conn.execute("SELECT * FROM vehicle_unit WHERE id=?", (vid,)).fetchone())

    def correct_vehicle(self, vid, expected_version, corrected_at):
        with self.conn:
            cur = self.conn.execute("UPDATE vehicle_unit SET corrected_at=?,version=version+1 WHERE id=? AND version=?",
                                    (corrected_at, vid, expected_version))
            if cur.rowcount == 0:
                raise ConcurrencyError(technical_detail=f"vehicle {vid} version mismatch")
        return self.get_vehicle(vid)

    @staticmethod
    def _vehicle(r):
        return None if not r else VehicleUnit(id=r["id"], vin=r["vin"], identity_status=r["identity_status"],
                                              store_scope=r["store_scope"], created_at=r["created_at"],
                                              corrected_at=r["corrected_at"], version=r["version"])

    def add_order(self, o: ProductionOrder) -> ProductionOrder:
        o.created_at = o.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO production_order(id,manufacturer_order_id,vin,linked_vehicle_unit_id,"
                              "identity_status,store_scope,created_at,version) VALUES(?,?,?,?,?,?,?,?)",
                              (o.id, o.manufacturer_order_id, o.vin, o.linked_vehicle_unit_id, o.identity_status,
                               o.store_scope, o.created_at, o.version))
        return o

    def find_orders_by_moid(self, moid, scope):
        rows = self.conn.execute("SELECT * FROM production_order WHERE manufacturer_order_id=? AND store_scope=?",
                                 (moid, scope)).fetchall()
        return [self._order(r) for r in rows]

    def get_order(self, oid):
        return self._order(self.conn.execute("SELECT * FROM production_order WHERE id=?", (oid,)).fetchone())

    def link_order_vin(self, oid, expected_version, vin, vehicle_unit_id):
        with self.conn:
            cur = self.conn.execute("UPDATE production_order SET vin=?,linked_vehicle_unit_id=?,identity_status='linked',"
                                    "version=version+1 WHERE id=? AND version=?", (vin, vehicle_unit_id, oid, expected_version))
            if cur.rowcount == 0:
                raise ConcurrencyError(technical_detail=f"order {oid} version mismatch")
        return self.get_order(oid)

    @staticmethod
    def _order(r):
        return None if not r else ProductionOrder(id=r["id"], manufacturer_order_id=r["manufacturer_order_id"],
                                                  vin=r["vin"], linked_vehicle_unit_id=r["linked_vehicle_unit_id"],
                                                  identity_status=r["identity_status"], store_scope=r["store_scope"],
                                                  created_at=r["created_at"], version=r["version"])

    def add_alias(self, entity_type, entity_id, alias_type, alias_value, scope, source_ref):
        from ..ids import new_id
        with self.conn:
            self.conn.execute("INSERT INTO entity_alias(id,entity_type,entity_id,alias_type,alias_value,store_scope,"
                              "source_ref,created_at) VALUES(?,?,?,?,?,?,?,?)",
                              (new_id("als"), entity_type, entity_id, alias_type, alias_value, scope, source_ref,
                               to_utc_iso(self.clock.now())))

    def find_alias(self, alias_type, alias_value, scope):
        return self.conn.execute("SELECT * FROM entity_alias WHERE alias_type=? AND alias_value=? AND store_scope=?",
                                 (alias_type, alias_value, scope)).fetchall()

    # ---- identity evidence -------------------------------------------------
    def add_evidence(self, e: IdentityEvidence) -> IdentityEvidence:
        e.recorded_at = e.recorded_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO identity_evidence(id,source_ref,record_ref,entity_type,identifier_type,"
                              "identifier_value,candidate_entities,resolution_status,resolution_rule_version,confidence,"
                              "resolver,reason,recorded_at,correction_ref,store_scope) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (e.id, e.source_ref, e.record_ref, e.entity_type, e.identifier_type, e.identifier_value,
                               _j(e.candidate_entities), e.resolution_status, e.resolution_rule_version, e.confidence,
                               e.resolver, e.reason, e.recorded_at, e.correction_ref, e.store_scope))
        return e

    def list_evidence_for(self, identifier_type, identifier_value, scope):
        rows = self.conn.execute("SELECT * FROM identity_evidence WHERE identifier_type=? AND identifier_value=?"
                                 " AND store_scope=? ORDER BY recorded_at", (identifier_type, identifier_value, scope)).fetchall()
        return [IdentityEvidence(id=r["id"], entity_type=r["entity_type"], identifier_type=r["identifier_type"],
                                 identifier_value=r["identifier_value"], resolution_status=r["resolution_status"],
                                 recorded_at=r["recorded_at"], source_ref=r["source_ref"], record_ref=r["record_ref"],
                                 candidate_entities=json.loads(r["candidate_entities"] or "[]"),
                                 resolution_rule_version=r["resolution_rule_version"], confidence=r["confidence"],
                                 resolver=r["resolver"], reason=r["reason"], correction_ref=r["correction_ref"],
                                 store_scope=r["store_scope"]) for r in rows]

    # ---- business fact -----------------------------------------------------
    def add_fact(self, f: BusinessFact) -> BusinessFact:
        f.recorded_time = f.recorded_time or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO business_fact(id,fact_type,subject_entity_type,subject_entity_id,payload,"
                              "effective_time,recorded_time,observation_refs,source_authority,quality_status,status,"
                              "correction_of,superseded_by,reversal_of,store_scope,provenance,version)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (f.id, f.fact_type, f.subject_entity_type, f.subject_entity_id, _j(f.payload),
                               f.effective_time, f.recorded_time, _j(f.observation_refs), f.source_authority,
                               f.quality_status, f.status, f.correction_of, f.superseded_by, f.reversal_of,
                               f.store_scope, _j(f.provenance), f.version))
        return f

    def get_fact(self, fid):
        return self._fact(self.conn.execute("SELECT * FROM business_fact WHERE id=?", (fid,)).fetchone())

    def set_fact_status(self, fid, expected_version, status, superseded_by=None):
        with self.conn:
            cur = self.conn.execute("UPDATE business_fact SET status=?,superseded_by=COALESCE(?,superseded_by),"
                                    "version=version+1 WHERE id=? AND version=?", (status, superseded_by, fid, expected_version))
            if cur.rowcount == 0:
                raise ConcurrencyError(technical_detail=f"fact {fid} version mismatch")
        return self.get_fact(fid)

    def facts_for(self, subject_type, subject_id, fact_type, scope, only_current=False):
        q = ("SELECT * FROM business_fact WHERE subject_entity_type=? AND subject_entity_id=? AND fact_type=?"
             " AND store_scope=?" + (" AND status='current'" if only_current else "") + " ORDER BY recorded_time")
        rows = self.conn.execute(q, (subject_type, subject_id, fact_type, scope)).fetchall()
        return [self._fact(r) for r in rows]

    @staticmethod
    def _fact(r):
        if not r:
            return None
        return BusinessFact(id=r["id"], fact_type=r["fact_type"], subject_entity_type=r["subject_entity_type"],
                            subject_entity_id=r["subject_entity_id"], payload=json.loads(r["payload"] or "{}"),
                            recorded_time=r["recorded_time"], status=r["status"], effective_time=r["effective_time"],
                            observation_refs=json.loads(r["observation_refs"] or "[]"), source_authority=r["source_authority"],
                            quality_status=r["quality_status"], correction_of=r["correction_of"],
                            superseded_by=r["superseded_by"], reversal_of=r["reversal_of"], store_scope=r["store_scope"],
                            provenance=json.loads(r["provenance"] or "{}"), version=r["version"])

    # ---- reconciliation ----------------------------------------------------
    def add_recon(self, rr: ReconciliationResult) -> ReconciliationResult:
        rr.recorded_at = rr.recorded_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO reconciliation_result(id,import_batch_id,source_observation_id,"
                              "candidate_entities,outcome,reason,resulting_fact_refs,conflict_refs,reviewer,recorded_at)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (rr.id, rr.import_batch_id, rr.source_observation_id, _j(rr.candidate_entities),
                               rr.outcome, rr.reason, _j(rr.resulting_fact_refs), _j(rr.conflict_refs), rr.reviewer,
                               rr.recorded_at))
        return rr

    def recon_for_batch(self, batch_id):
        rows = self.conn.execute("SELECT outcome,COUNT(*) c FROM reconciliation_result WHERE import_batch_id=?"
                                 " GROUP BY outcome", (batch_id,)).fetchall()
        return {r["outcome"]: r["c"] for r in rows}

    def recon_count(self, batch_id):
        return self.conn.execute("SELECT COUNT(*) c FROM reconciliation_result WHERE import_batch_id=?",
                                 (batch_id,)).fetchone()["c"]
