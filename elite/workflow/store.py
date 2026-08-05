"""SQLite repositories for Phase 5 workflow records.

Governed workflow / transition / reconciliation / issued records are append-preserving (DB
triggers block deletes). Projections (pipeline / ETA) may be superseded but prior-as-known
remains inspectable. Raw `insert_*`/`_raw` helpers run on a caller-supplied connection so a
governed transition + its supply effect + its Audit Event commit atomically.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id
from .models import (EditabilityResult, EtaRecord, IncomingRisk, ModelYearTransition,
                     ProductionPipeline, ReconciliationResult, SupplyWorkflow)


def _j(v):
    return json.dumps(v)


def _l(s):
    return json.loads(s) if s else []


def _d(s):
    return json.loads(s) if s else {}


class WorkflowStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- production pipeline ----------------------------------------------
    def add_pipeline(self, p: ProductionPipeline) -> ProductionPipeline:
        p.recorded_time = p.recorded_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO production_pipeline_projection(id,production_order_id,combination_id,store_scope,"
                "order_status,production_status,allocation_status,vin_status,build_timing,shipment_timing,eta_start,"
                "eta_end,arrival_month,source_refs,fact_refs,identity_refs,quality_status,confidence,status,conflict,"
                "recorded_time,effective_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.production_order_id, p.combination_id, p.store_scope, p.order_status, p.production_status,
                 p.allocation_status, p.vin_status, p.build_timing, p.shipment_timing, p.eta_start, p.eta_end,
                 p.arrival_month, _j(p.source_refs), _j(p.fact_refs), _j(p.identity_refs), p.quality_status,
                 p.confidence, p.status, p.conflict, p.recorded_time, p.effective_time))
        return p

    def supersede_pipeline(self, pipeline_id, new_status="superseded"):
        with self.conn:
            self.conn.execute("UPDATE production_pipeline_projection SET status=? WHERE id=?",
                              (new_status, pipeline_id))

    def get_pipeline(self, pid):
        return self._pipe(self.conn.execute("SELECT * FROM production_pipeline_projection WHERE id=?",
                                            (pid,)).fetchone())

    def pipeline_for_order(self, production_order_id, *, current_only=True):
        q = ("SELECT * FROM production_pipeline_projection WHERE production_order_id=?"
             + (" AND status='current'" if current_only else "") + " ORDER BY recorded_time,id")
        return [self._pipe(r) for r in self.conn.execute(q, (production_order_id,)).fetchall()]

    @staticmethod
    def _pipe(r):
        if not r:
            return None
        return ProductionPipeline(
            id=r["id"], store_scope=r["store_scope"], production_order_id=r["production_order_id"],
            combination_id=r["combination_id"], order_status=r["order_status"], production_status=r["production_status"],
            allocation_status=r["allocation_status"], vin_status=r["vin_status"], build_timing=r["build_timing"],
            shipment_timing=r["shipment_timing"], eta_start=r["eta_start"], eta_end=r["eta_end"],
            arrival_month=r["arrival_month"], source_refs=_l(r["source_refs"]), fact_refs=_l(r["fact_refs"]),
            identity_refs=_d(r["identity_refs"]), quality_status=r["quality_status"], confidence=r["confidence"],
            status=r["status"], conflict=r["conflict"], recorded_time=r["recorded_time"],
            effective_time=r["effective_time"])

    # ---- ETA history -------------------------------------------------------
    def add_eta(self, e: EtaRecord) -> EtaRecord:
        e.recorded_time = e.recorded_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO eta_history(id,production_order_id,pipeline_id,precision,eta_start,eta_end,arrival_month,"
                "confidence,stale,conflicting,supersedes,source_refs,recorded_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e.id, e.production_order_id, e.pipeline_id, e.precision, e.eta_start, e.eta_end, e.arrival_month,
                 e.confidence, int(e.stale), int(e.conflicting), e.supersedes, _j(e.source_refs), e.recorded_time))
        return e

    def eta_history_for(self, production_order_id):
        rows = self.conn.execute("SELECT * FROM eta_history WHERE production_order_id=? ORDER BY recorded_time,id",
                                 (production_order_id,)).fetchall()
        return [EtaRecord(id=r["id"], precision=r["precision"], production_order_id=r["production_order_id"],
                          pipeline_id=r["pipeline_id"], eta_start=r["eta_start"], eta_end=r["eta_end"],
                          arrival_month=r["arrival_month"], confidence=r["confidence"], stale=bool(r["stale"]),
                          conflicting=bool(r["conflicting"]), supersedes=r["supersedes"],
                          source_refs=_l(r["source_refs"]), recorded_time=r["recorded_time"]) for r in rows]

    # ---- editability -------------------------------------------------------
    def add_editability(self, e: EditabilityResult) -> EditabilityResult:
        e.recorded_time = e.recorded_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO editability_result(id,production_order_id,store_scope,editability_state,editable_dimensions,"
                "cutoff,source_refs,policy_refs,confidence,unresolved_conditions,recorded_time) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (e.id, e.production_order_id, e.store_scope, e.editability_state, _j(e.editable_dimensions), e.cutoff,
                 _j(e.source_refs), _j(e.policy_refs), e.confidence, _j(e.unresolved_conditions), e.recorded_time))
        return e

    def editability_for(self, production_order_id):
        r = self.conn.execute("SELECT * FROM editability_result WHERE production_order_id=? ORDER BY recorded_time DESC,"
                              "id DESC LIMIT 1", (production_order_id,)).fetchone()
        if not r:
            return None
        return EditabilityResult(id=r["id"], editability_state=r["editability_state"],
                                 production_order_id=r["production_order_id"], store_scope=r["store_scope"],
                                 editable_dimensions=_l(r["editable_dimensions"]), cutoff=r["cutoff"],
                                 source_refs=_l(r["source_refs"]), policy_refs=_l(r["policy_refs"]),
                                 confidence=r["confidence"], unresolved_conditions=_l(r["unresolved_conditions"]),
                                 recorded_time=r["recorded_time"])

    # ---- model-year transition --------------------------------------------
    def add_model_year_transition(self, m: ModelYearTransition) -> ModelYearTransition:
        m.recorded_time = m.recorded_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO model_year_transition_result(id,store_scope,model,outgoing_model_year,incoming_model_year,"
                "overlap,lineage_status,transition_window,arrival_risk,constrained_incoming,evidence,policy_refs,"
                "confidence,recorded_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (m.id, m.store_scope, m.model, m.outgoing_model_year, m.incoming_model_year, m.overlap, m.lineage_status,
                 _j(m.transition_window), m.arrival_risk, int(m.constrained_incoming), _j(m.evidence),
                 _j(m.policy_refs), m.confidence, m.recorded_time))
        return m

    # ---- incoming risk -----------------------------------------------------
    def add_risk(self, r: IncomingRisk) -> IncomingRisk:
        r.issued_time = r.issued_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO incoming_risk_result(id,subject_kind,subject_ref,combination_id,store_scope,classification,"
                "reasons,timing,affected_need_window,source_facts,policy_versions,calculation_version,confidence,"
                "reproducibility_package,issued_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.id, r.subject_kind, r.subject_ref, r.combination_id, r.store_scope, r.classification, _j(r.reasons),
                 _j(r.timing), _j(r.affected_need_window), _j(r.source_facts), _j(r.policy_versions),
                 r.calculation_version, r.confidence, r.reproducibility_package, r.issued_time))
        return r

    def get_risk(self, rid):
        r = self.conn.execute("SELECT * FROM incoming_risk_result WHERE id=?", (rid,)).fetchone()
        if not r:
            return None
        return IncomingRisk(id=r["id"], classification=r["classification"], subject_kind=r["subject_kind"],
                            subject_ref=r["subject_ref"], combination_id=r["combination_id"], store_scope=r["store_scope"],
                            reasons=_l(r["reasons"]), timing=_d(r["timing"]),
                            affected_need_window=_d(r["affected_need_window"]), source_facts=_l(r["source_facts"]),
                            policy_versions=_l(r["policy_versions"]), calculation_version=r["calculation_version"],
                            confidence=r["confidence"], reproducibility_package=r["reproducibility_package"],
                            issued_time=r["issued_time"])

    # ---- supply workflow (raw + wrapped) ----------------------------------
    def insert_workflow(self, conn, w: SupplyWorkflow) -> SupplyWorkflow:
        w.created_at = w.created_at or self._now()
        conn.execute(
            "INSERT INTO supply_workflow(id,workflow_type,subject_identity,subject_kind,combination_id,store_scope,"
            "target_month,quantity,originating_need_ref,qualifying_supply_at_propose,expected_resulting_supply,"
            "proposal_reason,evidence,policy_versions,calculation_version,approval_decision,execution_refs,"
            "lifecycle_status,idempotency_identity,audit_refs,reproducibility_package,scenario_id,created_at,version)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (w.id, w.workflow_type, w.subject_identity, w.subject_kind, w.combination_id, w.store_scope, w.target_month,
             w.quantity, w.originating_need_ref, w.qualifying_supply_at_propose, _j(w.expected_resulting_supply),
             w.proposal_reason, _j(w.evidence), _j(w.policy_versions), w.calculation_version, w.approval_decision,
             _j(w.execution_refs), w.lifecycle_status, w.idempotency_identity, _j(w.audit_refs),
             w.reproducibility_package, w.scenario_id, w.created_at, w.version))
        return w

    def add_workflow(self, w: SupplyWorkflow) -> SupplyWorkflow:
        with self.conn:
            self.insert_workflow(self.conn, w)
        return w

    def get_workflow(self, wid):
        r = self.conn.execute("SELECT * FROM supply_workflow WHERE id=?", (wid,)).fetchone()
        if not r:
            return None
        return SupplyWorkflow(
            id=r["id"], workflow_type=r["workflow_type"], store_scope=r["store_scope"],
            subject_identity=r["subject_identity"], subject_kind=r["subject_kind"], combination_id=r["combination_id"],
            target_month=r["target_month"], quantity=r["quantity"], originating_need_ref=r["originating_need_ref"],
            qualifying_supply_at_propose=r["qualifying_supply_at_propose"],
            expected_resulting_supply=_d(r["expected_resulting_supply"]), proposal_reason=r["proposal_reason"],
            evidence=_d(r["evidence"]), policy_versions=_l(r["policy_versions"]),
            calculation_version=r["calculation_version"], approval_decision=r["approval_decision"],
            execution_refs=_l(r["execution_refs"]), lifecycle_status=r["lifecycle_status"],
            idempotency_identity=r["idempotency_identity"], audit_refs=_l(r["audit_refs"]),
            reproducibility_package=r["reproducibility_package"], scenario_id=r["scenario_id"],
            created_at=r["created_at"], version=r["version"])

    def insert_transition(self, conn, workflow_id, from_status, to_status, *, actor, action,
                          reconciliation_ref=None, audit_ref=None, detail=""):
        tid = new_id("swt")
        conn.execute(
            "INSERT INTO supply_workflow_transition(id,workflow_id,from_status,to_status,actor,action,"
            "reconciliation_ref,audit_ref,detail,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (tid, workflow_id, from_status, to_status, actor, action, reconciliation_ref, audit_ref, detail,
             self._now()))
        return tid

    def transitions_for(self, workflow_id):
        return self.conn.execute("SELECT * FROM supply_workflow_transition WHERE workflow_id=? ORDER BY at,id",
                                 (workflow_id,)).fetchall()

    def add_evidence(self, workflow_id, evidence_kind, ref, detail=""):
        with self.conn:
            self.conn.execute("INSERT INTO supply_workflow_evidence(id,workflow_id,evidence_kind,ref,detail,recorded_at)"
                              " VALUES(?,?,?,?,?,?)", (new_id("swe"), workflow_id, evidence_kind, ref, detail, self._now()))

    # ---- action detail tables ---------------------------------------------
    def add_cpo_action(self, conn, **kw):
        aid = new_id("cpoa")
        conn.execute("INSERT INTO cpo_action(id,workflow_id,production_order_id,allocation_ref,combination_id,"
                     "discrete_quantity,arrival_month,commitment_ref,completion_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (aid, kw.get("workflow_id"), kw.get("production_order_id"), kw.get("allocation_ref"),
                      kw.get("combination_id"), kw.get("discrete_quantity", 1), kw.get("arrival_month"),
                      kw.get("commitment_ref"), kw.get("completion_ref"), self._now()))
        return aid

    def add_ppo_action(self, conn, **kw):
        aid = new_id("ppoa")
        conn.execute("INSERT INTO ppo_action(id,workflow_id,order_or_unit_id,allocation_evidence,combination_id,"
                     "discrete_quantity,arrival_month,commitment_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (aid, kw.get("workflow_id"), kw.get("order_or_unit_id"), kw.get("allocation_evidence"),
                      kw.get("combination_id"), kw.get("discrete_quantity", 1), kw.get("arrival_month"),
                      kw.get("commitment_ref"), self._now()))
        return aid

    def add_dealer_trade_action(self, conn, **kw):
        aid = new_id("dta")
        conn.execute("INSERT INTO dealer_trade_action(id,workflow_id,direction,counterparty,unit_identity,"
                     "combination_id,arrival_month,received_vehicle_unit_id,commitment_ref,completion_ref,created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (aid, kw.get("workflow_id"), kw.get("direction", "incoming"), kw.get("counterparty"),
                      kw.get("unit_identity"), kw.get("combination_id"), kw.get("arrival_month"),
                      kw.get("received_vehicle_unit_id"), kw.get("commitment_ref"), kw.get("completion_ref"),
                      self._now()))
        return aid

    def add_dealer_trade_status(self, dealer_trade_id, status, *, actor=None, reason=""):
        with self.conn:
            self.conn.execute("INSERT INTO dealer_trade_status_history(id,dealer_trade_id,status,actor,reason,at)"
                              " VALUES(?,?,?,?,?,?)", (new_id("dts"), dealer_trade_id, status, actor, reason, self._now()))

    def add_ctp_action(self, conn, **kw):
        aid = new_id("ctpa")
        conn.execute("INSERT INTO ctp_action(id,workflow_id,production_order_id,original_combination_id,"
                     "proposed_combination_id,editability_ref,cutoff,originating_need_ref,originating_excess_ref,"
                     "expected_portfolio_effect,resulting_order_state,superseded_future_supply,new_future_supply,"
                     "created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (aid, kw.get("workflow_id"), kw.get("production_order_id"), kw.get("original_combination_id"),
                      kw.get("proposed_combination_id"), kw.get("editability_ref"), kw.get("cutoff"),
                      kw.get("originating_need_ref"), kw.get("originating_excess_ref"),
                      _j(kw.get("expected_portfolio_effect", {})), kw.get("resulting_order_state"),
                      kw.get("superseded_future_supply"), kw.get("new_future_supply"), self._now()))
        return aid

    def update_ctp_result(self, ctp_id, *, resulting_order_state=None, superseded_future_supply=None,
                          new_future_supply=None):
        with self.conn:
            self.conn.execute("UPDATE ctp_action SET resulting_order_state=COALESCE(?,resulting_order_state),"
                              "superseded_future_supply=COALESCE(?,superseded_future_supply),"
                              "new_future_supply=COALESCE(?,new_future_supply) WHERE id=?",
                              (resulting_order_state, superseded_future_supply, new_future_supply, ctp_id))

    def add_ctp_change_detail(self, conn, ctp_id, dimension, from_value, to_value, accepted=None):
        conn.execute("INSERT INTO ctp_change_detail(id,ctp_id,dimension,from_value,to_value,accepted,at)"
                     " VALUES(?,?,?,?,?,?,?)",
                     (new_id("ctpc"), ctp_id, dimension, from_value, to_value,
                      None if accepted is None else int(accepted), self._now()))

    def ctp_action_for_workflow(self, workflow_id):
        return self.conn.execute("SELECT * FROM ctp_action WHERE workflow_id=? ORDER BY created_at LIMIT 1",
                                 (workflow_id,)).fetchone()

    # ---- reconciliation ----------------------------------------------------
    def insert_reconciliation(self, conn, rr: ReconciliationResult) -> ReconciliationResult:
        rr.recorded_at = rr.recorded_at or self._now()
        conn.execute(
            "INSERT INTO commitment_reconciliation_result(id,workflow_id,transition_ref,outcome,subject_identity,"
            "combination_id,supply_ref,prior_qualifying,new_qualifying,detail,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (rr.id, rr.workflow_id, rr.transition_ref, rr.outcome, rr.subject_identity, rr.combination_id, rr.supply_ref,
             rr.prior_qualifying, rr.new_qualifying, rr.detail, rr.recorded_at))
        return rr

    def add_reconciliation(self, rr: ReconciliationResult) -> ReconciliationResult:
        with self.conn:
            self.insert_reconciliation(self.conn, rr)
        return rr

    def reconciliations_for(self, workflow_id):
        rows = self.conn.execute("SELECT * FROM commitment_reconciliation_result WHERE workflow_id=? ORDER BY recorded_at,id",
                                 (workflow_id,)).fetchall()
        return [ReconciliationResult(id=r["id"], outcome=r["outcome"], workflow_id=r["workflow_id"],
                                     transition_ref=r["transition_ref"], subject_identity=r["subject_identity"],
                                     combination_id=r["combination_id"], supply_ref=r["supply_ref"],
                                     prior_qualifying=r["prior_qualifying"], new_qualifying=r["new_qualifying"],
                                     detail=r["detail"], recorded_at=r["recorded_at"]) for r in rows]

    # ---- sequential planning ----------------------------------------------
    def add_sequential_run(self, scope, *, base_portfolio_ref=None, calculation_version=None, scenario_id=None):
        rid = new_id("seqr")
        with self.conn:
            self.conn.execute("INSERT INTO sequential_planning_run(id,store_scope,base_portfolio_ref,status,"
                              "calculation_version,scenario_id,created_at) VALUES(?,?,?,?,?,?,?)",
                              (rid, scope, base_portfolio_ref, "running", calculation_version, scenario_id, self._now()))
        return rid

    def set_run_status(self, run_id, status):
        with self.conn:
            self.conn.execute("UPDATE sequential_planning_run SET status=? WHERE id=?", (status, run_id))

    def add_sequential_step(self, run_id, seq, *, action_ref, combination_id, causing_action, plan_ref,
                            need_before, need_after, excess_after, suppressed=False, outcome=""):
        sid = new_id("seqs")
        with self.conn:
            self.conn.execute("INSERT INTO sequential_planning_step(id,run_id,seq,action_ref,combination_id,"
                              "causing_action,plan_ref,need_before,need_after,excess_after,suppressed,outcome,at)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (sid, run_id, seq, action_ref, combination_id, causing_action, plan_ref, need_before,
                               need_after, excess_after, int(suppressed), outcome, self._now()))
        return sid

    def steps_for(self, run_id):
        return self.conn.execute("SELECT * FROM sequential_planning_step WHERE run_id=? ORDER BY seq,at",
                                 (run_id,)).fetchall()

    # ---- workflow issued-output ref + execution confirmation --------------
    def add_workflow_issued_output(self, workflow_id, causing_action, output_type, output_id, *, combination_id=None,
                                   scope=None, calculation_version=None, scenario_id=None):
        with self.conn:
            self.conn.execute("INSERT INTO workflow_issued_output_reference(id,workflow_id,causing_action,output_type,"
                              "output_id,combination_id,store_scope,calculation_version,scenario_id,issued_time)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (new_id("wior"), workflow_id, causing_action, output_type, output_id, combination_id,
                               scope, calculation_version, scenario_id, self._now()))

    def workflow_issued_outputs(self, workflow_id):
        return self.conn.execute("SELECT * FROM workflow_issued_output_reference WHERE workflow_id=? ORDER BY issued_time,id",
                                 (workflow_id,)).fetchall()

    def add_execution_confirmation(self, workflow_id, kind, *, subject_identity=None, resulting_supply_ref=None,
                                   outcome="", detail=""):
        cid = new_id("exc")
        with self.conn:
            self.conn.execute("INSERT INTO execution_confirmation(id,workflow_id,confirmation_kind,subject_identity,"
                              "resulting_supply_ref,outcome,detail,confirmed_at) VALUES(?,?,?,?,?,?,?,?)",
                              (cid, workflow_id, kind, subject_identity, resulting_supply_ref, outcome, detail,
                               self._now()))
        return cid
