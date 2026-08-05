"""SQLite repositories for Phase 3 policy/version records (behind method contracts).
Immutable value payloads (enforced by triggers) + optimistic concurrency on
lifecycle updates. History is append-preserving."""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..errors import ConcurrencyError
from ..ids import new_id
from .models import (CalculationFamily, CalculationVersion, ComparisonSpecificationVersion,
                     IdentityRuleVersion, ModelVersion, PolicyFamily, PolicyVersion,
                     ReproducibilityPackage)


def _j(v): return json.dumps(v)


class PolicyStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    # ---- policy family ----
    def add_family(self, f: PolicyFamily) -> PolicyFamily:
        f.created_at = f.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute(
                "INSERT INTO policy_family(id,name,category,owning_domain,value_schema,allowed_scope_dimensions,"
                "default_resolution,approval_required,correction_rules,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f.id, f.name, f.category, f.owning_domain, _j(f.value_schema), _j(f.allowed_scope_dimensions),
                 _j(f.default_resolution), int(f.approval_required), _j(f.correction_rules), f.status, f.created_at))
        return f

    def get_family(self, fid):
        r = self.conn.execute("SELECT * FROM policy_family WHERE id=?", (fid,)).fetchone()
        if not r:
            return None
        return PolicyFamily(id=r["id"], name=r["name"], category=r["category"], owning_domain=r["owning_domain"],
                            value_schema=json.loads(r["value_schema"] or "{}"),
                            allowed_scope_dimensions=json.loads(r["allowed_scope_dimensions"] or "[]"),
                            default_resolution=json.loads(r["default_resolution"] or "{}"),
                            approval_required=bool(r["approval_required"]),
                            correction_rules=json.loads(r["correction_rules"] or "{}"), status=r["status"],
                            created_at=r["created_at"])

    # ---- policy version ----
    def insert_version(self, conn, v: PolicyVersion) -> PolicyVersion:
        """Raw insert on the CALLER's connection (no own transaction). Use inside a
        governed transaction so the write commits atomically with its Audit Event."""
        v.recorded_time = v.recorded_time or to_utc_iso(self.clock.now())
        conn.execute(
            "INSERT INTO policy_version(id,family_id,version_number,value,source,evidence_refs,scope,"
            "effective_start,effective_end,start_inclusive,end_inclusive,recorded_time,approval_state,"
            "approving_principal,approved_time,scheduled_activation,lifecycle_status,supersedes,superseded_by,"
            "correction_of,revocation,reason,provenance,store_scope,is_scenario,scenario_id,version)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (v.id, v.family_id, v.version_number, _j(v.value), v.source, _j(v.evidence_refs), _j(v.scope),
             v.effective_start, v.effective_end, int(v.start_inclusive), int(v.end_inclusive), v.recorded_time,
             v.approval_state, v.approving_principal, v.approved_time, v.scheduled_activation, v.lifecycle_status,
             v.supersedes, v.superseded_by, v.correction_of, _j(v.revocation), v.reason, _j(v.provenance),
             v.store_scope, int(v.is_scenario), v.scenario_id, v.version))
        return v

    def add_version(self, v: PolicyVersion) -> PolicyVersion:
        with self.conn:
            self.insert_version(self.conn, v)
        return v

    def get_version(self, vid):
        return self._ver(self.conn.execute("SELECT * FROM policy_version WHERE id=?", (vid,)).fetchone())

    def update_version_lifecycle(self, vid, expected_version, *, lifecycle_status=None, approval_state=None,
                                 approving_principal=None, approved_time=None, scheduled_activation=None,
                                 superseded_by=None, supersedes=None, correction_of=None, revocation=None, reason=None):
        cur = self.get_version(vid)
        if cur is None:
            raise ConcurrencyError(technical_detail="policy version not found")
        fields = dict(lifecycle_status=lifecycle_status or cur.lifecycle_status,
                      approval_state=approval_state or cur.approval_state,
                      approving_principal=approving_principal or cur.approving_principal,
                      approved_time=approved_time or cur.approved_time,
                      scheduled_activation=scheduled_activation if scheduled_activation is not None else cur.scheduled_activation,
                      superseded_by=superseded_by or cur.superseded_by, supersedes=supersedes or cur.supersedes,
                      correction_of=correction_of or cur.correction_of,
                      revocation=_j(revocation) if revocation is not None else _j(cur.revocation),
                      reason=reason or cur.reason)
        with self.conn:
            c = self.conn.execute(
                "UPDATE policy_version SET lifecycle_status=?,approval_state=?,approving_principal=?,approved_time=?,"
                "scheduled_activation=?,superseded_by=?,supersedes=?,correction_of=?,revocation=?,reason=?,version=version+1"
                " WHERE id=? AND version=?",
                (fields["lifecycle_status"], fields["approval_state"], fields["approving_principal"],
                 fields["approved_time"], fields["scheduled_activation"], fields["superseded_by"], fields["supersedes"],
                 fields["correction_of"], fields["revocation"], fields["reason"], vid, expected_version))
            if c.rowcount == 0:
                raise ConcurrencyError(technical_detail=f"policy version {vid} stale (expected v{expected_version})")
        return self.get_version(vid)

    def versions_for_family(self, family_id, *, scenario_id="__official__"):
        if scenario_id == "__official__":
            rows = self.conn.execute("SELECT * FROM policy_version WHERE family_id=? AND is_scenario=0", (family_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM policy_version WHERE family_id=? AND (is_scenario=0 OR scenario_id=?)",
                                     (family_id, scenario_id)).fetchall()
        return [self._ver(r) for r in rows]

    @staticmethod
    def _ver(r):
        if not r:
            return None
        return PolicyVersion(id=r["id"], family_id=r["family_id"], version_number=r["version_number"],
                             value=json.loads(r["value"]), lifecycle_status=r["lifecycle_status"],
                             recorded_time=r["recorded_time"], source=r["source"],
                             evidence_refs=json.loads(r["evidence_refs"] or "[]"), scope=json.loads(r["scope"] or "{}"),
                             effective_start=r["effective_start"], effective_end=r["effective_end"],
                             start_inclusive=bool(r["start_inclusive"]), end_inclusive=bool(r["end_inclusive"]),
                             approval_state=r["approval_state"], approving_principal=r["approving_principal"],
                             approved_time=r["approved_time"], scheduled_activation=r["scheduled_activation"],
                             supersedes=r["supersedes"], superseded_by=r["superseded_by"], correction_of=r["correction_of"],
                             revocation=json.loads(r["revocation"] or "{}"), reason=r["reason"],
                             provenance=json.loads(r["provenance"] or "{}"), store_scope=r["store_scope"],
                             is_scenario=bool(r["is_scenario"]), scenario_id=r["scenario_id"], version=r["version"])

    # ---- calculation family / version ----
    def add_calc_family(self, f: CalculationFamily) -> CalculationFamily:
        f.created_at = f.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO calculation_family(id,name,owning_domain,purpose,input_contract_version,"
                              "output_contract_version,determinism,required_policy_families,status,created_at)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (f.id, f.name, f.owning_domain, f.purpose, f.input_contract_version,
                               f.output_contract_version, f.determinism, _j(f.required_policy_families), f.status,
                               f.created_at))
        return f

    def get_calc_family(self, fid):
        r = self.conn.execute("SELECT * FROM calculation_family WHERE id=?", (fid,)).fetchone()
        if not r:
            return None
        return CalculationFamily(id=r["id"], name=r["name"], owning_domain=r["owning_domain"], purpose=r["purpose"],
                                 input_contract_version=r["input_contract_version"],
                                 output_contract_version=r["output_contract_version"], determinism=r["determinism"],
                                 required_policy_families=json.loads(r["required_policy_families"] or "[]"),
                                 status=r["status"], created_at=r["created_at"])

    def insert_calc_version(self, conn, v: CalculationVersion) -> CalculationVersion:
        """Raw insert on a caller-supplied connection (no own transaction) — use inside a governed
        transaction (e.g. a Phase 8 Calibration activation that creates a new Calculation Version)."""
        v.created_at = v.created_at or to_utc_iso(self.clock.now())
        conn.execute("INSERT INTO calculation_version(id,family_id,semver,impl_revision,input_contract_version,"
                     "output_contract_version,required_policy_families,effective_start,effective_end,"
                     "lifecycle_status,approval_metadata,supersedes,superseded_by,rollback_of,change_summary,"
                     "reproducibility_metadata,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (v.id, v.family_id, v.semver, v.impl_revision, v.input_contract_version,
                      v.output_contract_version, _j(v.required_policy_families), v.effective_start,
                      v.effective_end, v.lifecycle_status, _j(v.approval_metadata), v.supersedes,
                      v.superseded_by, v.rollback_of, v.change_summary, _j(v.reproducibility_metadata),
                      v.created_at, v.version))
        return v

    def add_calc_version(self, v: CalculationVersion) -> CalculationVersion:
        with self.conn:
            self.insert_calc_version(self.conn, v)
        return v

    def get_calc_version(self, vid):
        r = self.conn.execute("SELECT * FROM calculation_version WHERE id=?", (vid,)).fetchone()
        if not r:
            return None
        return CalculationVersion(id=r["id"], family_id=r["family_id"], semver=r["semver"],
                                  lifecycle_status=r["lifecycle_status"], impl_revision=r["impl_revision"],
                                  input_contract_version=r["input_contract_version"],
                                  output_contract_version=r["output_contract_version"],
                                  required_policy_families=json.loads(r["required_policy_families"] or "[]"),
                                  effective_start=r["effective_start"], effective_end=r["effective_end"],
                                  approval_metadata=json.loads(r["approval_metadata"] or "{}"), supersedes=r["supersedes"],
                                  superseded_by=r["superseded_by"], rollback_of=r["rollback_of"],
                                  change_summary=r["change_summary"],
                                  reproducibility_metadata=json.loads(r["reproducibility_metadata"] or "{}"),
                                  created_at=r["created_at"], version=r["version"])

    def set_calc_version_status(self, vid, expected_version, status, *, superseded_by=None):
        with self.conn:
            c = self.conn.execute("UPDATE calculation_version SET lifecycle_status=?,superseded_by=COALESCE(?,superseded_by),"
                                  "version=version+1 WHERE id=? AND version=?", (status, superseded_by, vid, expected_version))
            if c.rowcount == 0:
                raise ConcurrencyError(technical_detail=f"calc version {vid} stale")
        return self.get_calc_version(vid)

    # ---- model / identity-rule / comparison-spec / reproducibility ----
    def insert_model_version(self, conn, m: ModelVersion) -> ModelVersion:
        """Raw insert on a caller-supplied connection — use inside a governed transaction."""
        m.created_at = m.created_at or to_utc_iso(self.clock.now())
        conn.execute("INSERT INTO model_version(id,model_family,version,scope,purpose,status,activation,"
                     "supersedes,evidence_refs,calibration_proposal,validation_status,rollback_ref,created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (m.id, m.model_family, m.version, _j(m.scope), m.purpose, m.status, m.activation,
                      m.supersedes, _j(m.evidence_refs), m.calibration_proposal, m.validation_status,
                      m.rollback_ref, m.created_at))
        return m

    def add_model_version(self, m: ModelVersion) -> ModelVersion:
        with self.conn:
            self.insert_model_version(self.conn, m)
        return m

    def get_model_version(self, mid):
        r = self.conn.execute("SELECT * FROM model_version WHERE id=?", (mid,)).fetchone()
        if not r:
            return None
        return ModelVersion(id=r["id"], model_family=r["model_family"], version=r["version"], status=r["status"],
                            scope=json.loads(r["scope"] or "{}"), purpose=r["purpose"], activation=r["activation"],
                            supersedes=r["supersedes"], evidence_refs=json.loads(r["evidence_refs"] or "[]"),
                            calibration_proposal=r["calibration_proposal"], validation_status=r["validation_status"],
                            rollback_ref=r["rollback_ref"], created_at=r["created_at"])

    def activate_model_version(self, mid, when):
        with self.conn:
            self.conn.execute("UPDATE model_version SET status='active',activation=? WHERE id=?",
                              (to_utc_iso(when), mid))
        return self.get_model_version(mid)

    def add_identity_rule_version(self, r: IdentityRuleVersion) -> IdentityRuleVersion:
        r.created_at = r.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO identity_rule_version(id,rule_family,version,entity_types,rule_summary,"
                              "impl_revision,status,effective_start,effective_end,approval_metadata,supersedes,created_at)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (r.id, r.rule_family, r.version, _j(r.entity_types), r.rule_summary, r.impl_revision,
                               r.status, r.effective_start, r.effective_end, _j(r.approval_metadata), r.supersedes,
                               r.created_at))
        return r

    def active_identity_rule(self, rule_family):
        row = self.conn.execute("SELECT * FROM identity_rule_version WHERE rule_family=? AND status='active'"
                                " ORDER BY created_at DESC LIMIT 1", (rule_family,)).fetchone()
        return None if not row else row["id"]

    def set_identity_rule_status(self, rid, status):
        with self.conn:
            self.conn.execute("UPDATE identity_rule_version SET status=? WHERE id=?", (status, rid))

    def add_comparison_spec(self, c: ComparisonSpecificationVersion) -> ComparisonSpecificationVersion:
        c.created_at = c.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO comparison_specification_version(id,version,prediction_type,observation_type,"
                              "subject_entity_type,timing_rules,matching_rules,unit_contract,status,effective_start,"
                              "effective_end,approval_metadata,supersedes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (c.id, c.version, c.prediction_type, c.observation_type, c.subject_entity_type,
                               _j(c.timing_rules), _j(c.matching_rules), _j(c.unit_contract), c.status,
                               c.effective_start, c.effective_end, _j(c.approval_metadata), c.supersedes, c.created_at))
        return c

    def get_comparison_spec(self, cid):
        r = self.conn.execute("SELECT * FROM comparison_specification_version WHERE id=?", (cid,)).fetchone()
        return None if not r else ComparisonSpecificationVersion(
            id=r["id"], version=r["version"], status=r["status"], prediction_type=r["prediction_type"],
            observation_type=r["observation_type"], subject_entity_type=r["subject_entity_type"],
            timing_rules=json.loads(r["timing_rules"] or "{}"), matching_rules=json.loads(r["matching_rules"] or "{}"),
            unit_contract=json.loads(r["unit_contract"] or "{}"), effective_start=r["effective_start"],
            effective_end=r["effective_end"], approval_metadata=json.loads(r["approval_metadata"] or "{}"),
            supersedes=r["supersedes"], created_at=r["created_at"])

    def add_reproducibility(self, p: ReproducibilityPackage) -> ReproducibilityPackage:
        p.created_at = p.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO reproducibility_package(id,refs,dealership_tz,calculation_timestamp,"
                              "implementation_revision,output_reference,created_at) VALUES(?,?,?,?,?,?,?)",
                              (p.id, _j(p.refs), p.dealership_tz, p.calculation_timestamp, p.implementation_revision,
                               p.output_reference, p.created_at))
        return p

    def get_reproducibility(self, pid):
        r = self.conn.execute("SELECT * FROM reproducibility_package WHERE id=?", (pid,)).fetchone()
        return None if not r else ReproducibilityPackage(
            id=r["id"], refs=json.loads(r["refs"]), dealership_tz=r["dealership_tz"],
            calculation_timestamp=r["calculation_timestamp"], implementation_revision=r["implementation_revision"],
            output_reference=r["output_reference"], created_at=r["created_at"])

    # ---- activation / rollback history ----
    def record_activation(self, target_type, target_id, action, actor, detail=""):
        with self.conn:
            self.conn.execute("INSERT INTO version_activation_history(id,target_type,target_id,action,actor,at,detail)"
                              " VALUES(?,?,?,?,?,?,?)", (new_id("vah"), target_type, target_id, action, actor,
                                                         to_utc_iso(self.clock.now()), detail))

    def activation_history(self, target_id):
        return self.conn.execute("SELECT * FROM version_activation_history WHERE target_id=? ORDER BY at",
                                 (target_id,)).fetchall()

    def record_rollback(self, target_type, from_id, to_id, actor, reason=""):
        with self.conn:
            self.conn.execute("INSERT INTO version_rollback_history(id,target_type,from_id,to_id,actor,at,reason)"
                              " VALUES(?,?,?,?,?,?,?)", (new_id("vrh"), target_type, from_id, to_id, actor,
                                                        to_utc_iso(self.clock.now()), reason))

    def rollback_history(self, target_type):
        return self.conn.execute("SELECT * FROM version_rollback_history WHERE target_type=? ORDER BY at",
                                 (target_type,)).fetchall()
