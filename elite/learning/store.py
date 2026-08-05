"""SQLite repositories for Phase 8 learning + calibration records.

Predictions and Observations are immutable (no-update/no-delete); everything else is append-
preserving (no-delete). Raw `insert_*` helpers run on a caller-supplied connection so a governed
Calibration transition + transition-history row + activation + Audit Event commit atomically.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id
from .models import ComparisonSpecRuntime, Observation, Pairing, Prediction, PredictionError


def _j(v):
    return json.dumps(v)


def _l(s):
    return json.loads(s) if s else []


def _d(s):
    return json.loads(s) if s else {}


class LearningStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- Prediction (immutable) -------------------------------------------
    def add_prediction(self, p: Prediction) -> Prediction:
        p.created_at = p.created_at or self._now()
        p.issue_time = p.issue_time or p.created_at
        with self.conn:
            self.conn.execute(
                "INSERT INTO prediction(id,prediction_type,owning_domain,subject_entity_type,subject_entity_id,"
                "store_scope,org_scope,issue_time,effective_period,prediction_horizon,predicted_payload,unit_contract,"
                "confidence,uncertainty,evidence_classification,fact_refs,source_state_refs,policy_versions,"
                "calculation_version,model_version,identity_rule_version,comparison_spec_version,comparison_spec_family,"
                "observation_contract,scenario_id,reproducibility_package,implementation_revision,issuing_actor,"
                "resolution_status,status,correction_of,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.prediction_type, p.owning_domain, p.subject_entity_type, p.subject_entity_id, p.store_scope,
                 p.org_scope, p.issue_time, p.effective_period, p.prediction_horizon, _j(p.predicted_payload),
                 _j(p.unit_contract), p.confidence, _j(p.uncertainty), p.evidence_classification, _j(p.fact_refs),
                 _j(p.source_state_refs), _j(p.policy_versions), p.calculation_version, p.model_version,
                 p.identity_rule_version, p.comparison_spec_version, p.comparison_spec_family, p.observation_contract,
                 p.scenario_id, p.reproducibility_package, p.implementation_revision, p.issuing_actor,
                 p.resolution_status, p.status, p.correction_of, p.created_at))
        self._issued("prediction", p.id, p.owning_domain, p.store_scope, p.calculation_version, p.scenario_id)
        return p

    def get_prediction(self, pid):
        return self._prediction(self.conn.execute("SELECT * FROM prediction WHERE id=?", (pid,)).fetchone())

    def predictions_where(self, *, owning_domain=None, scenario_only=None):
        q, args = "SELECT * FROM prediction WHERE 1=1", []
        if owning_domain:
            q, _ = q + " AND owning_domain=?", args.append(owning_domain)
        if scenario_only is True:
            q += " AND scenario_id IS NOT NULL"
        elif scenario_only is False:
            q += " AND scenario_id IS NULL"
        return [self._prediction(r) for r in self.conn.execute(q + " ORDER BY created_at,id", args).fetchall()]

    @staticmethod
    def _prediction(r):
        if not r:
            return None
        return Prediction(
            id=r["id"], prediction_type=r["prediction_type"], owning_domain=r["owning_domain"],
            store_scope=r["store_scope"], subject_entity_type=r["subject_entity_type"],
            subject_entity_id=r["subject_entity_id"], org_scope=r["org_scope"], issue_time=r["issue_time"],
            effective_period=r["effective_period"], prediction_horizon=r["prediction_horizon"],
            predicted_payload=_d(r["predicted_payload"]), unit_contract=_d(r["unit_contract"]),
            confidence=r["confidence"], uncertainty=_d(r["uncertainty"]),
            evidence_classification=r["evidence_classification"], fact_refs=_l(r["fact_refs"]),
            source_state_refs=_l(r["source_state_refs"]), policy_versions=_l(r["policy_versions"]),
            calculation_version=r["calculation_version"], model_version=r["model_version"],
            identity_rule_version=r["identity_rule_version"], comparison_spec_version=r["comparison_spec_version"],
            comparison_spec_family=r["comparison_spec_family"], observation_contract=r["observation_contract"],
            scenario_id=r["scenario_id"], reproducibility_package=r["reproducibility_package"],
            implementation_revision=r["implementation_revision"], issuing_actor=r["issuing_actor"],
            resolution_status=r["resolution_status"], status=r["status"], correction_of=r["correction_of"],
            created_at=r["created_at"])

    def add_prediction_correction(self, prediction_id, correction_type, *, replacement_prediction_id=None,
                                  reason="", correcting_actor=None, metadata=None):
        cid = new_id("pcorr")
        with self.conn:
            self.conn.execute("INSERT INTO prediction_correction(id,prediction_id,correction_type,"
                              "replacement_prediction_id,reason,correcting_actor,metadata,corrected_at) "
                              "VALUES(?,?,?,?,?,?,?,?)",
                              (cid, prediction_id, correction_type, replacement_prediction_id, reason,
                               correcting_actor, _j(metadata or {}), self._now()))
        return cid

    def prediction_corrections(self, prediction_id):
        return self.conn.execute("SELECT * FROM prediction_correction WHERE prediction_id=? ORDER BY corrected_at,id",
                                 (prediction_id,)).fetchall()

    # ---- Decision learning context ----------------------------------------
    def add_decision_context(self, **kw):
        did = new_id("dlc")
        with self.conn:
            self.conn.execute(
                "INSERT INTO decision_learning_context(id,decision_ref,owning_domain,subject_entity_type,"
                "subject_entity_id,store_scope,originating_prediction_refs,recommendation_refs,selected_action,"
                "rejected_alternatives,decision_time,decision_maker,applicable_facts,policies,calculations,confidence,"
                "uncertainty,stated_rationale,operational_constraints,scenario_id,execution_expectation,correction_of,"
                "created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (did, kw.get("decision_ref"), kw.get("owning_domain"), kw.get("subject_entity_type"),
                 kw.get("subject_entity_id"), kw["store_scope"], _j(kw.get("originating_prediction_refs", [])),
                 _j(kw.get("recommendation_refs", [])), kw.get("selected_action"),
                 _j(kw.get("rejected_alternatives", [])), kw.get("decision_time"), kw.get("decision_maker"),
                 _j(kw.get("applicable_facts", [])), _j(kw.get("policies", [])), _j(kw.get("calculations", [])),
                 kw.get("confidence"), _j(kw.get("uncertainty", {})), kw.get("stated_rationale"),
                 _j(kw.get("operational_constraints", [])), kw.get("scenario_id"), kw.get("execution_expectation"),
                 kw.get("correction_of"), self._now()))
        return self.conn.execute("SELECT * FROM decision_learning_context WHERE id=?", (did,)).fetchone()

    def get_decision_context(self, did):
        return self.conn.execute("SELECT * FROM decision_learning_context WHERE id=?", (did,)).fetchone()

    # ---- Observation (immutable) ------------------------------------------
    def add_observation(self, o: Observation) -> Observation:
        o.created_at = o.created_at or self._now()
        o.recorded_time = o.recorded_time or o.created_at
        with self.conn:
            self.conn.execute(
                "INSERT INTO observation(id,observation_type,owning_domain,subject_entity_type,subject_entity_id,"
                "observed_period,observed_payload,unit_contract,fact_refs,source_observation_refs,accepted_time,"
                "recorded_time,store_scope,quality,confidence,completeness,resolution_status,status,provenance,"
                "correction_of,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (o.id, o.observation_type, o.owning_domain, o.subject_entity_type, o.subject_entity_id,
                 o.observed_period, (None if o.observed_payload is None else _j(o.observed_payload)),
                 _j(o.unit_contract), _j(o.fact_refs), _j(o.source_observation_refs), o.accepted_time, o.recorded_time,
                 o.store_scope, o.quality, o.confidence, o.completeness, o.resolution_status, o.status,
                 _j(o.provenance), o.correction_of, o.created_at))
        self._issued("observation", o.id, o.owning_domain, o.store_scope, None, None)
        return o

    def get_observation(self, oid):
        return self._observation(self.conn.execute("SELECT * FROM observation WHERE id=?", (oid,)).fetchone())

    @staticmethod
    def _observation(r):
        if not r:
            return None
        return Observation(
            id=r["id"], observation_type=r["observation_type"], owning_domain=r["owning_domain"],
            store_scope=r["store_scope"], subject_entity_type=r["subject_entity_type"],
            subject_entity_id=r["subject_entity_id"], observed_period=r["observed_period"],
            observed_payload=(None if r["observed_payload"] is None else _d(r["observed_payload"])),
            unit_contract=_d(r["unit_contract"]), fact_refs=_l(r["fact_refs"]),
            source_observation_refs=_l(r["source_observation_refs"]), accepted_time=r["accepted_time"],
            recorded_time=r["recorded_time"], quality=r["quality"], confidence=r["confidence"],
            completeness=r["completeness"], resolution_status=r["resolution_status"], status=r["status"],
            provenance=_d(r["provenance"]), correction_of=r["correction_of"], created_at=r["created_at"])

    def add_observation_correction(self, observation_id, correction_type, *, replacement_observation_id=None,
                                   negates_effect=False, reason="", correcting_actor=None, prior_as_known=None):
        cid = new_id("ocorr")
        with self.conn:
            self.conn.execute("INSERT INTO observation_correction(id,observation_id,correction_type,"
                              "replacement_observation_id,negates_effect,reason,correcting_actor,prior_as_known,"
                              "corrected_at) VALUES(?,?,?,?,?,?,?,?,?)",
                              (cid, observation_id, correction_type, replacement_observation_id, int(negates_effect),
                               reason, correcting_actor, _j(prior_as_known or {}), self._now()))
        return cid

    def observation_corrections(self, observation_id):
        return self.conn.execute("SELECT * FROM observation_correction WHERE observation_id=? ORDER BY corrected_at,id",
                                 (observation_id,)).fetchall()

    # ---- Comparison Specification runtime ---------------------------------
    def insert_comparison_spec(self, conn, c: ComparisonSpecRuntime) -> ComparisonSpecRuntime:
        """Raw insert on a caller-supplied connection — use inside a governed transaction (Calibration
        activation of a new Comparison Specification version)."""
        c.created_at = c.created_at or self._now()
        conn.execute(
            "INSERT INTO comparison_specification_runtime(id,registry_ref,version,prediction_type,observation_type,"
            "subject_entity_type,scope_rules,matching_keys,timing_rules,observation_window,lateness_tolerance,"
            "unit_contract,transformation_rules,aggregation_rules,partial_behavior,conflicting_behavior,"
            "missing_behavior,error_semantics,directionality,materiality_threshold_ref,confidence_rules,status,"
            "effective_start,effective_end,approval_metadata,supersedes,superseded_by,impl_revision,created_at,"
            "version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.id, c.registry_ref, c.version, c.prediction_type, c.observation_type, c.subject_entity_type,
             _j(c.scope_rules), _j(c.matching_keys), _j(c.timing_rules), _j(c.observation_window),
             _j(c.lateness_tolerance), _j(c.unit_contract), _j(c.transformation_rules), _j(c.aggregation_rules),
             c.partial_behavior, c.conflicting_behavior, c.missing_behavior, c.error_semantics, c.directionality,
             c.materiality_threshold_ref, _j(c.confidence_rules), c.status, c.effective_start, c.effective_end,
             _j(c.approval_metadata), c.supersedes, c.superseded_by, c.impl_revision, c.created_at, c.version_no))
        return c

    def add_comparison_spec(self, c: ComparisonSpecRuntime) -> ComparisonSpecRuntime:
        c.created_at = c.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO comparison_specification_runtime(id,registry_ref,version,prediction_type,observation_type,"
                "subject_entity_type,scope_rules,matching_keys,timing_rules,observation_window,lateness_tolerance,"
                "unit_contract,transformation_rules,aggregation_rules,partial_behavior,conflicting_behavior,"
                "missing_behavior,error_semantics,directionality,materiality_threshold_ref,confidence_rules,status,"
                "effective_start,effective_end,approval_metadata,supersedes,superseded_by,impl_revision,created_at,"
                "version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.registry_ref, c.version, c.prediction_type, c.observation_type, c.subject_entity_type,
                 _j(c.scope_rules), _j(c.matching_keys), _j(c.timing_rules), _j(c.observation_window),
                 _j(c.lateness_tolerance), _j(c.unit_contract), _j(c.transformation_rules), _j(c.aggregation_rules),
                 c.partial_behavior, c.conflicting_behavior, c.missing_behavior, c.error_semantics, c.directionality,
                 c.materiality_threshold_ref, _j(c.confidence_rules), c.status, c.effective_start, c.effective_end,
                 _j(c.approval_metadata), c.supersedes, c.superseded_by, c.impl_revision, c.created_at, c.version_no))
        return c

    def get_comparison_spec(self, cid):
        return self._spec(self.conn.execute("SELECT * FROM comparison_specification_runtime WHERE id=?",
                                            (cid,)).fetchone())

    def set_comparison_spec_status(self, cid, status, *, superseded_by=None):
        with self.conn:
            self.conn.execute("UPDATE comparison_specification_runtime SET status=?,superseded_by=? WHERE id=?",
                              (status, superseded_by, cid))
        return self.get_comparison_spec(cid)

    @staticmethod
    def _spec(r):
        if not r:
            return None
        return ComparisonSpecRuntime(
            id=r["id"], version=r["version"], prediction_type=r["prediction_type"],
            observation_type=r["observation_type"], registry_ref=r["registry_ref"],
            subject_entity_type=r["subject_entity_type"], scope_rules=_d(r["scope_rules"]),
            matching_keys=_l(r["matching_keys"]), timing_rules=_d(r["timing_rules"]),
            observation_window=_d(r["observation_window"]), lateness_tolerance=_d(r["lateness_tolerance"]),
            unit_contract=_d(r["unit_contract"]), transformation_rules=_d(r["transformation_rules"]),
            aggregation_rules=_d(r["aggregation_rules"]), partial_behavior=r["partial_behavior"],
            conflicting_behavior=r["conflicting_behavior"], missing_behavior=r["missing_behavior"],
            error_semantics=r["error_semantics"], directionality=r["directionality"],
            materiality_threshold_ref=r["materiality_threshold_ref"], confidence_rules=_d(r["confidence_rules"]),
            status=r["status"], effective_start=r["effective_start"], effective_end=r["effective_end"],
            approval_metadata=_d(r["approval_metadata"]), supersedes=r["supersedes"],
            superseded_by=r["superseded_by"], impl_revision=r["impl_revision"], created_at=r["created_at"],
            version_no=r["version_no"])

    # ---- Pairing -----------------------------------------------------------
    def add_pairing(self, p: Pairing) -> Pairing:
        p.created_at = p.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO prediction_observation_pairing(id,prediction_id,observation_id,comparison_spec_version,"
                "subject_entity_type,subject_entity_id,store_scope,pairing_status,matching_evidence,timing_relationship,"
                "unit_compatible,completeness,confidence,paired_time,rule_or_principal,correction_of,superseded_by,"
                "reason,idempotency_key,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.prediction_id, p.observation_id, p.comparison_spec_version, p.subject_entity_type,
                 p.subject_entity_id, p.store_scope, p.pairing_status, _j(p.matching_evidence), p.timing_relationship,
                 (None if p.unit_compatible is None else int(p.unit_compatible)), p.completeness, p.confidence,
                 p.paired_time, p.rule_or_principal, p.correction_of, p.superseded_by, p.reason, p.idempotency_key,
                 p.created_at, p.version))
        return p

    def get_pairing(self, pid):
        return self._pairing(self.conn.execute("SELECT * FROM prediction_observation_pairing WHERE id=?",
                                              (pid,)).fetchone())

    def pairing_by_idempotency(self, key):
        return self._pairing(self.conn.execute("SELECT * FROM prediction_observation_pairing WHERE idempotency_key=?",
                                              (key,)).fetchone())

    def pairings_for_prediction(self, prediction_id):
        return [self._pairing(r) for r in self.conn.execute(
            "SELECT * FROM prediction_observation_pairing WHERE prediction_id=? ORDER BY created_at,id",
            (prediction_id,)).fetchall()]

    def set_pairing(self, pid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = self.conn.execute(f"UPDATE prediction_observation_pairing SET {cols},version=version+1 "
                                "WHERE id=? AND version=?", (*fields.values(), pid, expected_version))
        return cur.rowcount

    @staticmethod
    def _pairing(r):
        if not r:
            return None
        return Pairing(
            id=r["id"], prediction_id=r["prediction_id"], comparison_spec_version=r["comparison_spec_version"],
            pairing_status=r["pairing_status"], observation_id=r["observation_id"],
            subject_entity_type=r["subject_entity_type"], subject_entity_id=r["subject_entity_id"],
            store_scope=r["store_scope"], matching_evidence=_d(r["matching_evidence"]),
            timing_relationship=r["timing_relationship"],
            unit_compatible=(None if r["unit_compatible"] is None else bool(r["unit_compatible"])),
            completeness=r["completeness"], confidence=r["confidence"], paired_time=r["paired_time"],
            rule_or_principal=r["rule_or_principal"], correction_of=r["correction_of"],
            superseded_by=r["superseded_by"], reason=r["reason"], idempotency_key=r["idempotency_key"],
            created_at=r["created_at"], version=r["version"])

    def add_pairing_review(self, pairing_id, reviewer, outcome, *, notes=""):
        rid = new_id("prev")
        with self.conn:
            self.conn.execute("INSERT INTO pairing_review(id,pairing_id,reviewer,outcome,notes,reviewed_at) "
                              "VALUES(?,?,?,?,?,?)", (rid, pairing_id, reviewer, outcome, notes, self._now()))
        return rid

    # ---- Error -------------------------------------------------------------
    def add_error(self, e: PredictionError) -> PredictionError:
        e.created_at = e.created_at or self._now()
        e.calculation_time = e.calculation_time or e.created_at
        with self.conn:
            self.conn.execute(
                "INSERT INTO prediction_error(id,pairing_id,prediction_id,observation_id,comparison_spec_version,"
                "expected_value,actual_value,signed_error,absolute_error,percentage_error,bounded_error,timing_error,"
                "classification,materiality,confidence,resolution_status,calculation_time,calculation_version,"
                "reproducibility_package,correction_of,superseded_by,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e.id, e.pairing_id, e.prediction_id, e.observation_id, e.comparison_spec_version, e.expected_value,
                 e.actual_value, e.signed_error, e.absolute_error, e.percentage_error, e.bounded_error, e.timing_error,
                 e.classification, e.materiality, e.confidence, e.resolution_status, e.calculation_time,
                 e.calculation_version, e.reproducibility_package, e.correction_of, e.superseded_by, e.created_at))
        self._issued("error", e.id, None, None, e.calculation_version, None)
        return e

    def get_error(self, eid):
        return self._error(self.conn.execute("SELECT * FROM prediction_error WHERE id=?", (eid,)).fetchone())

    @staticmethod
    def _error(r):
        if not r:
            return None
        return PredictionError(
            id=r["id"], pairing_id=r["pairing_id"], prediction_id=r["prediction_id"],
            comparison_spec_version=r["comparison_spec_version"], observation_id=r["observation_id"],
            expected_value=r["expected_value"], actual_value=r["actual_value"], signed_error=r["signed_error"],
            absolute_error=r["absolute_error"], percentage_error=r["percentage_error"],
            bounded_error=r["bounded_error"], timing_error=r["timing_error"], classification=r["classification"],
            materiality=r["materiality"], confidence=r["confidence"], resolution_status=r["resolution_status"],
            calculation_time=r["calculation_time"], calculation_version=r["calculation_version"],
            reproducibility_package=r["reproducibility_package"], correction_of=r["correction_of"],
            superseded_by=r["superseded_by"], created_at=r["created_at"])

    def add_error_correction(self, error_id, correction_type, *, replacement_error_id=None, reason=""):
        cid = new_id("ecorr")
        with self.conn:
            self.conn.execute("INSERT INTO error_correction(id,error_id,correction_type,replacement_error_id,reason,"
                              "corrected_at) VALUES(?,?,?,?,?,?)",
                              (cid, error_id, correction_type, replacement_error_id, reason, self._now()))
        return cid

    # ---- Attribution -------------------------------------------------------
    def add_attribution(self, error_id, *, proposed_factor, factor_category, subject_entity_id=None,
                        confidence="medium", evidence_strength="weak", status="PROPOSED", source="automated",
                        correction_of=None):
        aid = new_id("attr")
        with self.conn:
            self.conn.execute("INSERT INTO attribution(id,error_id,subject_entity_id,proposed_factor,factor_category,"
                              "confidence,evidence_strength,status,source,reviewing_principal,review_time,correction_of,"
                              "superseded_by,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (aid, error_id, subject_entity_id, proposed_factor, factor_category, confidence,
                               evidence_strength, status, source, None, None, correction_of, None, self._now(), 1))
        return self.get_attribution(aid)

    def get_attribution(self, aid):
        return self.conn.execute("SELECT * FROM attribution WHERE id=?", (aid,)).fetchone()

    def attributions_for_error(self, error_id):
        return self.conn.execute("SELECT * FROM attribution WHERE error_id=? ORDER BY created_at,id",
                                 (error_id,)).fetchall()

    def set_attribution(self, aid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = self.conn.execute(f"UPDATE attribution SET {cols},version=version+1 WHERE id=? AND version=?",
                                (*fields.values(), aid, expected_version))
        return cur.rowcount

    def add_attribution_evidence(self, attribution_id, *, evidence_kind, supports, description="", fact_refs=None):
        eid = new_id("aev")
        with self.conn:
            self.conn.execute("INSERT INTO attribution_evidence(id,attribution_id,evidence_kind,supports,description,"
                              "fact_refs,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (eid, attribution_id, evidence_kind, int(supports), description, _j(fact_refs or []),
                               self._now()))
        return eid

    def evidence_for_attribution(self, attribution_id):
        return self.conn.execute("SELECT * FROM attribution_evidence WHERE attribution_id=? ORDER BY recorded_at,id",
                                 (attribution_id,)).fetchall()

    def add_attribution_review(self, attribution_id, reviewer, outcome, *, preserves_automated=True, notes=""):
        rid = new_id("arev")
        with self.conn:
            self.conn.execute("INSERT INTO attribution_review(id,attribution_id,reviewer,outcome,preserves_automated,"
                              "notes,reviewed_at) VALUES(?,?,?,?,?,?,?)",
                              (rid, attribution_id, reviewer, outcome, int(preserves_automated), notes, self._now()))
        return rid

    # ---- Learning Signal ---------------------------------------------------
    def add_learning_signal(self, owning_domain, *, subject_or_cohort=None, error_refs=None, attribution_refs=None,
                            pattern_type=None, evidence_window=None, sample_size=0, recurrence=0, direction=None,
                            magnitude=None, confidence="low", stability="unstable", data_quality_conditions=None,
                            proposed_review_area=None, status="CANDIDATE", correction_of=None):
        sid = new_id("lsig")
        with self.conn:
            self.conn.execute("INSERT INTO learning_signal(id,owning_domain,subject_or_cohort,error_refs,"
                              "attribution_refs,pattern_type,evidence_window,sample_size,recurrence,direction,magnitude,"
                              "confidence,stability,data_quality_conditions,proposed_review_area,status,correction_of,"
                              "superseded_by,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (sid, owning_domain, subject_or_cohort, _j(error_refs or []), _j(attribution_refs or []),
                               pattern_type, evidence_window, sample_size, recurrence, direction,
                               (None if magnitude is None else _j(magnitude)), confidence, stability,
                               _j(data_quality_conditions or {}), proposed_review_area, status, correction_of, None,
                               self._now(), 1))
        for ref in (error_refs or []):
            self._signal_source(sid, "error", ref)
        for ref in (attribution_refs or []):
            self._signal_source(sid, "attribution", ref)
        return self.get_learning_signal(sid)

    def _signal_source(self, sid, kind, ref):
        with self.conn:
            self.conn.execute("INSERT INTO learning_signal_source(id,learning_signal_id,source_type,source_ref,"
                              "recorded_at) VALUES(?,?,?,?,?)", (new_id("lss"), sid, kind, ref, self._now()))

    def get_learning_signal(self, sid):
        return self.conn.execute("SELECT * FROM learning_signal WHERE id=?", (sid,)).fetchone()

    def signal_sources(self, sid):
        return self.conn.execute("SELECT * FROM learning_signal_source WHERE learning_signal_id=?", (sid,)).fetchall()

    def set_learning_signal(self, sid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = self.conn.execute(f"UPDATE learning_signal SET {cols},version=version+1 WHERE id=? AND version=?",
                                (*fields.values(), sid, expected_version))
        return cur.rowcount

    def signals_in_domain(self, owning_domain, *, status=None):
        q, args = "SELECT * FROM learning_signal WHERE owning_domain=?", [owning_domain]
        if status:
            q, _ = q + " AND status=?", args.append(status)
        return self.conn.execute(q + " ORDER BY created_at,id", args).fetchall()

    # ---- Calibration proposal (governed lifecycle) ------------------------
    def insert_calibration(self, conn, **kw):
        cid = kw.get("id") or new_id("calp")
        conn.execute("INSERT INTO calibration_proposal(id,target_type,target_family,current_version,proposed_change,"
                     "affected_domains,expected_benefit,known_risks,proposed_effective_period,rollback_plan,proposer,"
                     "review_state,approval_state,approving_principal,decision_ref,activation_ref,rejection_reason,"
                     "policy_review_recommendation,correction_of,superseded_by,created_at,version) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, kw["target_type"], kw.get("target_family"), kw.get("current_version"),
                      _j(kw.get("proposed_change", {})), _j(kw.get("affected_domains", [])),
                      _j(kw.get("expected_benefit", {})), _j(kw.get("known_risks", [])),
                      kw.get("proposed_effective_period"), _j(kw.get("rollback_plan", {})), kw.get("proposer"),
                      kw.get("review_state", "DRAFT"), kw.get("approval_state"), kw.get("approving_principal"),
                      kw.get("decision_ref"), kw.get("activation_ref"), kw.get("rejection_reason"),
                      kw.get("policy_review_recommendation"), kw.get("correction_of"), None, self._now(), 1))
        return cid

    def add_calibration(self, **kw):
        with self.conn:
            cid = self.insert_calibration(self.conn, **kw)
        return self.get_calibration(cid)

    def get_calibration(self, cid):
        return self.conn.execute("SELECT * FROM calibration_proposal WHERE id=?", (cid,)).fetchone()

    def set_calibration(self, conn, cid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = conn.execute(f"UPDATE calibration_proposal SET {cols},version=version+1 WHERE id=? AND version=?",
                           (*fields.values(), cid, expected_version))
        return cur.rowcount

    def calibrations_in_state(self, review_state):
        return self.conn.execute("SELECT * FROM calibration_proposal WHERE review_state=? ORDER BY created_at,id",
                                 (review_state,)).fetchall()

    def add_calibration_evidence(self, calibration_proposal_id, *, evidence_kind, learning_signal_ref=None,
                                 description="", refs=None):
        eid = new_id("cev")
        with self.conn:
            self.conn.execute("INSERT INTO calibration_evidence(id,calibration_proposal_id,evidence_kind,"
                              "learning_signal_ref,description,refs,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (eid, calibration_proposal_id, evidence_kind, learning_signal_ref, description,
                               _j(refs or []), self._now()))
        return eid

    def insert_calibration_transition(self, conn, calibration_proposal_id, from_state, to_state, *, actor, action,
                                      detail=""):
        tid = new_id("ctr")
        conn.execute("INSERT INTO calibration_transition(id,calibration_proposal_id,from_state,to_state,actor,action,"
                     "audit_ref,detail,at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (tid, calibration_proposal_id, from_state, to_state, actor, action, None, detail, self._now()))
        return tid

    def calibration_transitions(self, calibration_proposal_id):
        return self.conn.execute("SELECT * FROM calibration_transition WHERE calibration_proposal_id=? "
                                 "ORDER BY at,id", (calibration_proposal_id,)).fetchall()

    # ---- validation --------------------------------------------------------
    def add_validation_run(self, calibration_proposal_id, *, current_version, proposed_version, training_window=None,
                           evaluation_window=None, dataset_refs=None, hypothetical=True, leakage_checked=True,
                           calculation_version=None, reproducibility_package=None, status="completed"):
        rid = new_id("cvr")
        with self.conn:
            self.conn.execute("INSERT INTO calibration_validation_run(id,calibration_proposal_id,current_version,"
                              "proposed_version,training_window,evaluation_window,dataset_refs,hypothetical,"
                              "leakage_checked,calculation_version,reproducibility_package,run_time,status) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (rid, calibration_proposal_id, current_version, proposed_version, training_window,
                               evaluation_window, _j(dataset_refs or []), int(hypothetical), int(leakage_checked),
                               calculation_version, reproducibility_package, self._now(), status))
        return self.conn.execute("SELECT * FROM calibration_validation_run WHERE id=?", (rid,)).fetchone()

    def add_validation_result(self, validation_run_id, *, cohort, current_error, proposed_error, delta, direction,
                              material, notes=""):
        rid = new_id("cvres")
        with self.conn:
            self.conn.execute("INSERT INTO calibration_validation_result(id,validation_run_id,cohort,current_error,"
                              "proposed_error,delta,direction,material,notes,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (rid, validation_run_id, cohort, str(current_error), str(proposed_error), str(delta),
                               direction, int(material), notes, self._now()))
        return rid

    def validation_results(self, validation_run_id):
        return self.conn.execute("SELECT * FROM calibration_validation_result WHERE validation_run_id=? "
                                 "ORDER BY recorded_at,id", (validation_run_id,)).fetchall()

    # ---- activation + rollback --------------------------------------------
    def insert_activation(self, conn, calibration_proposal_id, *, target_type, activated_version_ref,
                          activated_version_kind, effective_start, scheduled, prior_version_ref, actor):
        aid = new_id("cact")
        conn.execute("INSERT INTO calibration_activation(id,calibration_proposal_id,target_type,activated_version_ref,"
                     "activated_version_kind,effective_start,scheduled,prior_version_ref,actor,activated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (aid, calibration_proposal_id, target_type, activated_version_ref, activated_version_kind,
                      effective_start, int(scheduled), prior_version_ref, actor, self._now()))
        return aid

    def activation_for(self, calibration_proposal_id):
        return self.conn.execute("SELECT * FROM calibration_activation WHERE calibration_proposal_id=?",
                                 (calibration_proposal_id,)).fetchone()

    def get_activation(self, aid):
        return self.conn.execute("SELECT * FROM calibration_activation WHERE id=?", (aid,)).fetchone()

    def insert_rollback(self, conn, calibration_proposal_id, *, activation_ref, restored_version_ref, reason, actor,
                        effective_start):
        rid = new_id("crb")
        conn.execute("INSERT INTO calibration_rollback(id,calibration_proposal_id,activation_ref,restored_version_ref,"
                     "reason,actor,effective_start,rolled_back_at) VALUES(?,?,?,?,?,?,?,?)",
                     (rid, calibration_proposal_id, activation_ref, restored_version_ref, reason, actor,
                      effective_start, self._now()))
        return rid

    def rollback_for(self, calibration_proposal_id):
        return self.conn.execute("SELECT * FROM calibration_rollback WHERE calibration_proposal_id=? "
                                 "ORDER BY rolled_back_at,id", (calibration_proposal_id,)).fetchall()

    # ---- issued-output index ----------------------------------------------
    def _issued(self, output_type, output_id, owning_domain, scope, calc_version, scenario_id):
        with self.conn:
            self.conn.execute("INSERT INTO learning_issued_output(id,output_type,output_id,owning_domain,store_scope,"
                              "calculation_version,scenario_id,issued_time) VALUES(?,?,?,?,?,?,?,?)",
                              (new_id("lio"), output_type, output_id, owning_domain, scope, calc_version, scenario_id,
                               self._now()))

    def issued_outputs(self, output_type=None):
        if output_type:
            return self.conn.execute("SELECT * FROM learning_issued_output WHERE output_type=? ORDER BY issued_time",
                                     (output_type,)).fetchall()
        return self.conn.execute("SELECT * FROM learning_issued_output ORDER BY issued_time").fetchall()
