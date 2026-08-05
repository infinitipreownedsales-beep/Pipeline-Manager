"""SQLite repositories for Phase 7 Executive Demo records.

Units, membership history, portfolio plans, opportunity-cost / lifecycle / economic results,
retirement events, Used Cars receipts, reconciliation results, and issued outputs are append-
preserving (DB triggers block deletes; the Used Cars receipt is also immutable). Raw `insert_*`
helpers run on a caller-supplied connection so a governed transition + membership-history row +
supply effect + Audit Event commit atomically. This is a SEPARATE store from Service Loaner.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id
from .models import EconomicResult, ExecDemoUnit, RetirementAction


def _j(v):
    return json.dumps(v)


def _l(s):
    return json.loads(s) if s else []


def _d(s):
    return json.loads(s) if s else {}


class ExecDemoStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- Executive Demo Unit ----------------------------------------------
    def insert_unit(self, conn, u: ExecDemoUnit) -> ExecDemoUnit:
        u.created_at = u.created_at or self._now()
        conn.execute(
            "INSERT INTO executive_demo_unit(id,vehicle_unit_id,vin,store_scope,combination_id,membership_state,"
            "designation_decision,designation_execution_event,active_date,in_service_or_activation_date,current_mileage,"
            "assigned_role,model_preference_evidence,portfolio_role,retirement_decision,retirement_event,"
            "return_to_retail_event,used_cars_receipt,current_economic_result,active_fleet_supply_ref,correction_of,"
            "superseded_by,quality_status,confidence,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (u.id, u.vehicle_unit_id, u.vin, u.store_scope, u.combination_id, u.membership_state, u.designation_decision,
             u.designation_execution_event, u.active_date, u.in_service_or_activation_date, u.current_mileage,
             u.assigned_role, u.model_preference_evidence, u.portfolio_role, u.retirement_decision, u.retirement_event,
             u.return_to_retail_event, u.used_cars_receipt, u.current_economic_result, u.active_fleet_supply_ref,
             u.correction_of, u.superseded_by, u.quality_status, u.confidence, u.created_at, u.version))
        return u

    def add_unit(self, u: ExecDemoUnit) -> ExecDemoUnit:
        with self.conn:
            self.insert_unit(self.conn, u)
        return u

    def get_unit(self, uid):
        return self._unit(self.conn.execute("SELECT * FROM executive_demo_unit WHERE id=?", (uid,)).fetchone())

    def unit_for_vehicle(self, vehicle_unit_id, scope, *, active_only=False):
        q = "SELECT * FROM executive_demo_unit WHERE vehicle_unit_id=? AND store_scope=?"
        if active_only:
            q += " AND superseded_by IS NULL"
        return self._unit(self.conn.execute(q + " ORDER BY created_at DESC LIMIT 1", (vehicle_unit_id, scope)).fetchone())

    def units_in_states(self, scope, states):
        marks = ",".join("?" * len(states))
        rows = self.conn.execute(f"SELECT * FROM executive_demo_unit WHERE store_scope=? AND membership_state IN "
                                 f"({marks}) AND superseded_by IS NULL ORDER BY created_at", (scope, *states)).fetchall()
        return [self._unit(r) for r in rows]

    def set_unit_field(self, conn, uid, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE executive_demo_unit SET {cols} WHERE id=?", (*fields.values(), uid))

    @staticmethod
    def _unit(r):
        if not r:
            return None
        return ExecDemoUnit(
            id=r["id"], store_scope=r["store_scope"], vehicle_unit_id=r["vehicle_unit_id"], vin=r["vin"],
            combination_id=r["combination_id"], membership_state=r["membership_state"],
            designation_decision=r["designation_decision"], designation_execution_event=r["designation_execution_event"],
            active_date=r["active_date"], in_service_or_activation_date=r["in_service_or_activation_date"],
            current_mileage=r["current_mileage"], assigned_role=r["assigned_role"],
            model_preference_evidence=r["model_preference_evidence"], portfolio_role=r["portfolio_role"],
            retirement_decision=r["retirement_decision"], retirement_event=r["retirement_event"],
            return_to_retail_event=r["return_to_retail_event"], used_cars_receipt=r["used_cars_receipt"],
            current_economic_result=r["current_economic_result"], active_fleet_supply_ref=r["active_fleet_supply_ref"],
            correction_of=r["correction_of"], superseded_by=r["superseded_by"], quality_status=r["quality_status"],
            confidence=r["confidence"], created_at=r["created_at"], version=r["version"])

    def insert_membership_history(self, conn, unit_id, from_state, to_state, *, actor, action,
                                  reconciliation_ref=None, audit_ref=None, detail=""):
        hid = new_id("edh")
        conn.execute("INSERT INTO executive_demo_membership_history(id,executive_demo_unit_id,from_state,to_state,actor,"
                     "action,reconciliation_ref,audit_ref,detail,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (hid, unit_id, from_state, to_state, actor, action, reconciliation_ref, audit_ref, detail, self._now()))
        return hid

    def membership_history(self, unit_id):
        return self.conn.execute("SELECT * FROM executive_demo_membership_history WHERE executive_demo_unit_id=? "
                                 "ORDER BY at,id", (unit_id,)).fetchall()

    # ---- portfolio requirement + plan -------------------------------------
    def add_requirement(self, scope, *, required_size, model_representation=None, model_preference_ref=None,
                        policy_versions=None):
        rid = new_id("edpr")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_portfolio_requirement(id,store_scope,required_size,"
                              "model_representation,model_preference_ref,policy_versions,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (rid, scope, required_size, _j(model_representation or {}), model_preference_ref,
                               _j(policy_versions or []), self._now()))
        return rid

    def add_portfolio_plan(self, scope, *, required_size, current_active, committed, need, selected, best_overall=None,
                           tradeoffs=None, sacrifices=None, need_basis=None, policy_versions=None,
                           calculation_version=None, scenario_id=None):
        pid = new_id("edpp")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_portfolio_plan(id,store_scope,required_size,current_active,"
                              "committed,need,selected,tradeoffs,sacrifices,best_overall,need_basis,policy_versions,"
                              "calculation_version,scenario_id,issued_time,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (pid, scope, required_size, current_active, committed, need, _j(selected),
                               _j(tradeoffs or []), _j(sacrifices or []), _j(best_overall or {}), _j(need_basis or {}),
                               _j(policy_versions or []), calculation_version, scenario_id, self._now(), "issued"))
        self._issued("portfolio_plan", pid, None, scope, calculation_version, scenario_id)
        return self.conn.execute("SELECT * FROM executive_demo_portfolio_plan WHERE id=?", (pid,)).fetchone()

    # ---- candidate + eligibility ------------------------------------------
    def add_candidate(self, **kw):
        cid = new_id("edc")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_candidate(id,vehicle_unit_id,combination_id,store_scope,model,"
                              "model_year,age_days,mileage,eligibility,new_retail_refs,opportunity_cost_ref,expected_value,"
                              "expected_lifecycle_ref,policy_versions,calculation_version,source_refs,quality_status,"
                              "confidence,scenario_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (cid, kw.get("vehicle_unit_id"), kw.get("combination_id"), kw.get("store_scope"),
                               kw.get("model"), kw.get("model_year"), kw.get("age_days"), kw.get("mileage"),
                               kw.get("eligibility"), _j(kw.get("new_retail_refs", {})), kw.get("opportunity_cost_ref"),
                               _j(kw.get("expected_value", {})), kw.get("expected_lifecycle_ref"),
                               _j(kw.get("policy_versions", [])), kw.get("calculation_version"),
                               _j(kw.get("source_refs", [])), kw.get("quality_status", "ok"),
                               kw.get("confidence", "medium"), kw.get("scenario_id"), self._now()))
        return self.conn.execute("SELECT * FROM executive_demo_candidate WHERE id=?", (cid,)).fetchone()

    def add_eligibility(self, vehicle_unit_id, combination_id, scope, outcome, *, reasons=None, policy_versions=None):
        eid = new_id("edel")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_eligibility_result(id,vehicle_unit_id,combination_id,store_scope,"
                              "outcome,reasons,policy_versions,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                              (eid, vehicle_unit_id, combination_id, scope, outcome, _j(reasons or []),
                               _j(policy_versions or []), self._now()))
        return self.conn.execute("SELECT * FROM executive_demo_eligibility_result WHERE id=?", (eid,)).fetchone()

    # ---- model preference --------------------------------------------------
    def add_preference(self, scope, resolution_status, *, preferred=None, hierarchy=None, substitutions=None,
                       policy_version=None, subject_scope=None, note="", scenario_id=None):
        pid = new_id("edmp")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_model_preference_resolution(id,store_scope,resolution_status,"
                              "preferred,hierarchy,substitutions,policy_version,scope,note,scenario_id,recorded_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              (pid, scope, resolution_status, preferred, _j(hierarchy or []), _j(substitutions or []),
                               policy_version, _j(subject_scope or {}), note, scenario_id, self._now()))
        return self.conn.execute("SELECT * FROM executive_demo_model_preference_resolution WHERE id=?", (pid,)).fetchone()

    # ---- opportunity cost --------------------------------------------------
    def add_opportunity_cost(self, vehicle_unit_id, combination_id, scope, *, affected_months, plan_position, cost_value,
                             expected_return_path=None, confidence="medium", policy_versions=None,
                             calculation_version=None, plan_refs=None, reproducibility_package=None, scenario_id=None):
        oid = new_id("edoc")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_opportunity_cost_result(id,vehicle_unit_id,combination_id,"
                              "store_scope,affected_months,plan_position,cost_value,expected_return_path,confidence,"
                              "policy_versions,calculation_version,plan_refs,reproducibility_package,scenario_id,issued_time)"
                              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (oid, vehicle_unit_id, combination_id, scope, _j(affected_months), plan_position,
                               _j(cost_value), expected_return_path, confidence, _j(policy_versions or []),
                               calculation_version, _j(plan_refs or []), reproducibility_package, scenario_id, self._now()))
        return self.conn.execute("SELECT * FROM executive_demo_opportunity_cost_result WHERE id=?", (oid,)).fetchone()

    # ---- lifecycle projection ---------------------------------------------
    def add_lifecycle_projection(self, scope, resolution_status, *, unit_id=None, candidate_id=None,
                                 activation_timing=None, expected_duration=None, expected_mileage=None,
                                 expected_depreciation=None, expected_retirement_timing=None, expected_return_path=None,
                                 assumptions=None, uncertainty=None, policy_versions=None, calculation_version=None):
        lid = new_id("edlc")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_lifecycle_projection(id,executive_demo_unit_id,candidate_id,"
                              "store_scope,activation_timing,expected_duration,expected_mileage,expected_depreciation,"
                              "expected_retirement_timing,expected_return_path,assumptions,uncertainty,resolution_status,"
                              "policy_versions,calculation_version,issued_time,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (lid, unit_id, candidate_id, scope, activation_timing, expected_duration, expected_mileage,
                               expected_depreciation, expected_retirement_timing, expected_return_path,
                               _j(assumptions or {}), _j(uncertainty or {}), resolution_status, _j(policy_versions or []),
                               calculation_version, self._now(), "issued"))
        return self.conn.execute("SELECT * FROM executive_demo_lifecycle_projection WHERE id=?", (lid,)).fetchone()

    # ---- economic result + execution --------------------------------------
    def add_economic(self, e: EconomicResult) -> EconomicResult:
        e.issued_time = e.issued_time or self._now()
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_economic_result(id,executive_demo_unit_id,candidate_id,"
                              "store_scope,decision_point,alternatives,economic_call,opportunity_cost_ref,expected_benefit,"
                              "retirement_impact,assumptions,uncertainty,resolution_status,policy_versions,"
                              "calculation_version,fact_refs,reproducibility_package,scenario_id,issued_time,status) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (e.id, e.executive_demo_unit_id, e.candidate_id, e.store_scope, e.decision_point,
                               _j(e.alternatives), _j(e.economic_call), e.opportunity_cost_ref, _j(e.expected_benefit),
                               _j(e.retirement_impact), _j(e.assumptions), _j(e.uncertainty), e.resolution_status,
                               _j(e.policy_versions), e.calculation_version, _j(e.fact_refs), e.reproducibility_package,
                               e.scenario_id, e.issued_time, e.status))
        self._issued("economic", e.id, e.executive_demo_unit_id, e.store_scope, e.calculation_version, e.scenario_id)
        return e

    def get_economic(self, eid):
        r = self.conn.execute("SELECT * FROM executive_demo_economic_result WHERE id=?", (eid,)).fetchone()
        if not r:
            return None
        return EconomicResult(id=r["id"], executive_demo_unit_id=r["executive_demo_unit_id"], store_scope=r["store_scope"],
                resolution_status=r["resolution_status"], decision_point=r["decision_point"], candidate_id=r["candidate_id"],
                alternatives=_l(r["alternatives"]), economic_call=_d(r["economic_call"]),
                opportunity_cost_ref=r["opportunity_cost_ref"], expected_benefit=_d(r["expected_benefit"]),
                retirement_impact=_d(r["retirement_impact"]), assumptions=_d(r["assumptions"]),
                uncertainty=_d(r["uncertainty"]), policy_versions=_l(r["policy_versions"]),
                calculation_version=r["calculation_version"], fact_refs=_l(r["fact_refs"]),
                reproducibility_package=r["reproducibility_package"], scenario_id=r["scenario_id"],
                issued_time=r["issued_time"], status=r["status"])

    def add_execution_status(self, unit_id, economic_result_id, status, *, reason="", blocking_factors=None):
        sid = new_id("edes")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_execution_status(id,executive_demo_unit_id,economic_result_id,"
                              "status,reason,blocking_factors,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (sid, unit_id, economic_result_id, status, reason, _j(blocking_factors or []), self._now()))
        return self.conn.execute("SELECT * FROM executive_demo_execution_status WHERE id=?", (sid,)).fetchone()

    # ---- designation + retirement actions ---------------------------------
    def add_designation_action(self, unit_id, scope, lifecycle_status, *, candidate_id=None, economic_result_id=None,
                               decision_ref=None):
        aid = new_id("edda")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_designation_action(id,executive_demo_unit_id,store_scope,"
                              "lifecycle_status,candidate_id,economic_result_id,decision_ref,approval_time,"
                              "cancellation_status,correction_of,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (aid, unit_id, scope, lifecycle_status, candidate_id, economic_result_id, decision_ref,
                               None, None, None, self._now(), 1))
        return aid

    def set_designation_action(self, conn, aid, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE executive_demo_designation_action SET {cols},version=version+1 WHERE id=?",
                     (*fields.values(), aid))

    def get_designation_action(self, aid):
        return self.conn.execute("SELECT * FROM executive_demo_designation_action WHERE id=?", (aid,)).fetchone()

    def add_retirement_eligibility(self, unit_id, eligible, *, reasons=None, policy_versions=None, tenure_days=None):
        rid = new_id("edre")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_retirement_eligibility(id,executive_demo_unit_id,eligible,"
                              "reasons,policy_versions,tenure_days,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (rid, unit_id, int(eligible), _j(reasons or []), _j(policy_versions or []), tenure_days,
                               self._now()))
        return rid

    def insert_retirement_action(self, conn, a: RetirementAction) -> RetirementAction:
        a.created_at = a.created_at or self._now()
        conn.execute("INSERT INTO executive_demo_retirement_action(id,executive_demo_unit_id,store_scope,lifecycle_status,"
                     "economic_result_id,decision_ref,approval_time,cancellation_status,correction_of,created_at,version) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (a.id, a.executive_demo_unit_id, a.store_scope, a.lifecycle_status, a.economic_result_id,
                      a.decision_ref, a.approval_time, a.cancellation_status, a.correction_of, a.created_at, a.version))
        return a

    def add_retirement_action(self, a: RetirementAction) -> RetirementAction:
        with self.conn:
            self.insert_retirement_action(self.conn, a)
        return a

    def get_retirement_action(self, aid):
        r = self.conn.execute("SELECT * FROM executive_demo_retirement_action WHERE id=?", (aid,)).fetchone()
        if not r:
            return None
        return RetirementAction(id=r["id"], executive_demo_unit_id=r["executive_demo_unit_id"], store_scope=r["store_scope"],
                lifecycle_status=r["lifecycle_status"], economic_result_id=r["economic_result_id"],
                decision_ref=r["decision_ref"], approval_time=r["approval_time"], cancellation_status=r["cancellation_status"],
                correction_of=r["correction_of"], created_at=r["created_at"], version=r["version"])

    def set_retirement_action(self, conn, aid, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE executive_demo_retirement_action SET {cols},version=version+1 WHERE id=?",
                     (*fields.values(), aid))

    def add_retirement_event(self, conn, unit_id, retirement_action_id, scope):
        eid = new_id("edrev")
        conn.execute("INSERT INTO executive_demo_retirement_event(id,executive_demo_unit_id,retirement_action_id,"
                     "store_scope,membership_reconciled,event_time) VALUES(?,?,?,?,?,?)",
                     (eid, unit_id, retirement_action_id, scope, 1, self._now()))
        return eid

    def add_return_to_retail_event(self, conn, unit_id, retirement_event_ref, scope, *, restored_supply_ref, confirmed_by):
        rid = new_id("edrtr")
        conn.execute("INSERT INTO executive_demo_return_to_retail_event(id,executive_demo_unit_id,retirement_event_ref,"
                     "store_scope,restored_supply_ref,confirmed_by,confirmed_at) VALUES(?,?,?,?,?,?,?)",
                     (rid, unit_id, retirement_event_ref, scope, restored_supply_ref, confirmed_by, self._now()))
        return rid

    # ---- used cars receipt (idempotent, immutable) ------------------------
    def add_used_cars_receipt(self, conn, unit_id, vehicle_unit_id, retirement_event_ref, scope, *, confirming_principal,
                              correlation_id=None, audit_ref=None):
        rid = new_id("educr")
        conn.execute("INSERT INTO executive_demo_used_cars_receipt(id,executive_demo_unit_id,vehicle_unit_id,"
                     "retirement_event_ref,store_scope,confirming_principal,correlation_id,audit_ref,confirmed_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?)",
                     (rid, unit_id, vehicle_unit_id, retirement_event_ref, scope, confirming_principal, correlation_id,
                      audit_ref, self._now()))
        return rid

    def used_cars_receipt_for(self, unit_id):
        return self.conn.execute("SELECT * FROM executive_demo_used_cars_receipt WHERE executive_demo_unit_id=?",
                                 (unit_id,)).fetchone()

    # ---- reconciliation ----------------------------------------------------
    def insert_reconciliation(self, conn, unit_id, vehicle_unit_id, scope, outcome, *, supply_ref=None, detail=""):
        rid = new_id("edrr")
        conn.execute("INSERT INTO executive_demo_reconciliation_result(id,executive_demo_unit_id,vehicle_unit_id,"
                     "store_scope,outcome,supply_ref,detail,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                     (rid, unit_id, vehicle_unit_id, scope, outcome, supply_ref, detail, self._now()))
        return rid

    def add_reconciliation(self, unit_id, vehicle_unit_id, scope, outcome, *, supply_ref=None, detail=""):
        with self.conn:
            return self.insert_reconciliation(self.conn, unit_id, vehicle_unit_id, scope, outcome, supply_ref=supply_ref,
                                              detail=detail)

    def reconciliations_for(self, unit_id):
        return self.conn.execute("SELECT * FROM executive_demo_reconciliation_result WHERE executive_demo_unit_id=? "
                                 "ORDER BY recorded_at,id", (unit_id,)).fetchall()

    # ---- scenario + resale + issued ---------------------------------------
    def add_scenario_result(self, scenario_id, scope, kind, overrides, output, *, baseline_ref=None):
        sid = new_id("edsc")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_scenario_result(id,scenario_id,store_scope,kind,overrides,"
                              "output,baseline_ref,issued_time) VALUES(?,?,?,?,?,?,?,?)",
                              (sid, scenario_id, scope, kind, _j(overrides), _j(output), baseline_ref, self._now()))
        return self.conn.execute("SELECT * FROM executive_demo_scenario_result WHERE id=?", (sid,)).fetchone()

    def add_resale_reference(self, unit_id, **kw):
        rid = new_id("edres")
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_resale_reference(id,executive_demo_unit_id,designation_ref,"
                              "retirement_event_ref,return_path,used_cars_receipt_ref,resale_event_ref,resale_value,"
                              "predicted_ref,observed_ref,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              (rid, unit_id, kw.get("designation_ref"), kw.get("retirement_event_ref"),
                               kw.get("return_path"), kw.get("used_cars_receipt_ref"), kw.get("resale_event_ref"),
                               _j(kw.get("resale_value", {})), kw.get("predicted_ref"), kw.get("observed_ref"),
                               self._now()))
        return rid

    def _issued(self, output_type, output_id, unit_id, scope, calc_version, scenario_id):
        with self.conn:
            self.conn.execute("INSERT INTO executive_demo_issued_output(id,output_type,output_id,executive_demo_unit_id,"
                              "store_scope,calculation_version,scenario_id,issued_time) VALUES(?,?,?,?,?,?,?,?)",
                              (new_id("edio"), output_type, output_id, unit_id, scope, calc_version, scenario_id,
                               self._now()))

    def issued_outputs(self, output_type=None):
        if output_type:
            return self.conn.execute("SELECT * FROM executive_demo_issued_output WHERE output_type=? ORDER BY issued_time",
                                     (output_type,)).fetchall()
        return self.conn.execute("SELECT * FROM executive_demo_issued_output ORDER BY issued_time").fetchall()
