"""SQLite repositories for Phase 6 Service Loaner records.

Units, membership history, economic results, retirement events, Used Cars receipts,
reconciliation results, and issued outputs are append-preserving (DB triggers block deletes; the
Used Cars receipt is also immutable). Raw `insert_*` helpers run on a caller-supplied connection so
a governed transition + membership-history row + Audit Event commit atomically.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id
from .models import (CheckoutMileage, EconomicResult, InServiceDateResolution, MonitoringAlert,
                     RetirementAction, ServiceLoanerUnit)


def _j(v):
    return json.dumps(v)


def _l(s):
    return json.loads(s) if s else []


def _d(s):
    return json.loads(s) if s else {}


class LoanerStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- Service Loaner Unit ----------------------------------------------
    def insert_unit(self, conn, u: ServiceLoanerUnit) -> ServiceLoanerUnit:
        u.created_at = u.created_at or self._now()
        conn.execute(
            "INSERT INTO service_loaner_unit(id,vehicle_unit_id,vin,store_scope,combination_id,membership_state,"
            "accepted_in_service_date,in_service_date_authority,current_rental_state,last_checkout_mileage,"
            "last_accepted_snapshot,active_fleet_presence,entry_decision,entry_execution_event,retirement_decision,"
            "return_confirmation,retirement_event,used_cars_receipt,return_to_retail_ref,correction_of,superseded_by,"
            "quality_status,confidence,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (u.id, u.vehicle_unit_id, u.vin, u.store_scope, u.combination_id, u.membership_state,
             u.accepted_in_service_date, u.in_service_date_authority, u.current_rental_state, u.last_checkout_mileage,
             u.last_accepted_snapshot, int(u.active_fleet_presence), u.entry_decision, u.entry_execution_event,
             u.retirement_decision, u.return_confirmation, u.retirement_event, u.used_cars_receipt,
             u.return_to_retail_ref, u.correction_of, u.superseded_by, u.quality_status, u.confidence, u.created_at,
             u.version))
        return u

    def add_unit(self, u: ServiceLoanerUnit) -> ServiceLoanerUnit:
        with self.conn:
            self.insert_unit(self.conn, u)
        return u

    def get_unit(self, uid):
        return self._unit(self.conn.execute("SELECT * FROM service_loaner_unit WHERE id=?", (uid,)).fetchone())

    def unit_for_vin(self, vin, scope, *, active_only=False):
        q = "SELECT * FROM service_loaner_unit WHERE vin=? AND store_scope=?"
        if active_only:
            q += " AND superseded_by IS NULL"
        return self._unit(self.conn.execute(q + " ORDER BY created_at DESC LIMIT 1", (vin, scope)).fetchone())

    def units_in_states(self, scope, states):
        marks = ",".join("?" * len(states))
        rows = self.conn.execute(f"SELECT * FROM service_loaner_unit WHERE store_scope=? AND membership_state IN "
                                 f"({marks}) AND superseded_by IS NULL ORDER BY created_at", (scope, *states)).fetchall()
        return [self._unit(r) for r in rows]

    def set_unit_field(self, conn, uid, **fields):
        """Raw field update on the governed connection (no membership_state — that goes through a
        governed transition)."""
        cols = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE service_loaner_unit SET {cols} WHERE id=?", (*fields.values(), uid))

    @staticmethod
    def _unit(r):
        if not r:
            return None
        return ServiceLoanerUnit(
            id=r["id"], store_scope=r["store_scope"], vehicle_unit_id=r["vehicle_unit_id"], vin=r["vin"],
            combination_id=r["combination_id"], membership_state=r["membership_state"],
            accepted_in_service_date=r["accepted_in_service_date"], in_service_date_authority=r["in_service_date_authority"],
            current_rental_state=r["current_rental_state"], last_checkout_mileage=r["last_checkout_mileage"],
            last_accepted_snapshot=r["last_accepted_snapshot"], active_fleet_presence=bool(r["active_fleet_presence"]),
            entry_decision=r["entry_decision"], entry_execution_event=r["entry_execution_event"],
            retirement_decision=r["retirement_decision"], return_confirmation=r["return_confirmation"],
            retirement_event=r["retirement_event"], used_cars_receipt=r["used_cars_receipt"],
            return_to_retail_ref=r["return_to_retail_ref"], correction_of=r["correction_of"],
            superseded_by=r["superseded_by"], quality_status=r["quality_status"], confidence=r["confidence"],
            created_at=r["created_at"], version=r["version"])

    def insert_membership_history(self, conn, unit_id, from_state, to_state, *, actor, action,
                                  reconciliation_ref=None, audit_ref=None, detail=""):
        hid = new_id("slh")
        conn.execute("INSERT INTO service_loaner_membership_history(id,service_loaner_unit_id,from_state,to_state,"
                     "actor,action,reconciliation_ref,audit_ref,detail,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (hid, unit_id, from_state, to_state, actor, action, reconciliation_ref, audit_ref, detail,
                      self._now()))
        return hid

    def membership_history(self, unit_id):
        return self.conn.execute("SELECT * FROM service_loaner_membership_history WHERE service_loaner_unit_id=? "
                                 "ORDER BY at,id", (unit_id,)).fetchall()

    # ---- snapshot reconciliation ------------------------------------------
    def add_snapshot_recon(self, import_batch_id, snapshot_type, scope, vin, unit_id, outcome, reason=""):
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_snapshot_reconciliation(id,import_batch_id,snapshot_type,"
                              "store_scope,vin,service_loaner_unit_id,outcome,reason,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)",
                              (new_id("ssr"), import_batch_id, snapshot_type, scope, vin, unit_id, outcome, reason,
                               self._now()))

    def snapshot_recons(self, import_batch_id):
        return self.conn.execute("SELECT * FROM service_loaner_snapshot_reconciliation WHERE import_batch_id=? "
                                 "ORDER BY recorded_at,id", (import_batch_id,)).fetchall()

    # ---- operational state ------------------------------------------------
    def add_operational_state(self, unit_id, *, snapshot_ref=None, rental_state=None, availability_state=None,
                              conflict=None, source_refs=None):
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_operational_state(id,service_loaner_unit_id,snapshot_ref,"
                              "rental_state,availability_state,conflict,source_refs,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                              (new_id("los"), unit_id, snapshot_ref, rental_state, availability_state, conflict,
                               _j(source_refs or []), self._now()))

    # ---- in-service date ---------------------------------------------------
    def add_in_service_resolution(self, r: InServiceDateResolution) -> InServiceDateResolution:
        r.recorded_at = r.recorded_at or self._now()
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_in_service_date_resolution(id,service_loaner_unit_id,"
                              "candidate_values,source,evidence,authority_level,effective_time,accepted_value,"
                              "conflict_state,correction_of,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              (r.id, r.service_loaner_unit_id, _j(r.candidate_values), r.source, _j(r.evidence),
                               r.authority_level, r.effective_time, r.accepted_value, r.conflict_state,
                               r.correction_of, r.recorded_at))
        return r

    def in_service_resolutions(self, unit_id):
        rows = self.conn.execute("SELECT * FROM service_loaner_in_service_date_resolution WHERE "
                                 "service_loaner_unit_id=? ORDER BY recorded_at,id", (unit_id,)).fetchall()
        return [InServiceDateResolution(id=r["id"], service_loaner_unit_id=r["service_loaner_unit_id"],
                candidate_values=_l(r["candidate_values"]), source=r["source"], evidence=_d(r["evidence"]),
                authority_level=r["authority_level"], effective_time=r["effective_time"],
                accepted_value=r["accepted_value"], conflict_state=r["conflict_state"],
                correction_of=r["correction_of"], recorded_at=r["recorded_at"]) for r in rows]

    # ---- checkout mileage --------------------------------------------------
    def add_mileage(self, m: CheckoutMileage) -> CheckoutMileage:
        m.recorded_at = m.recorded_at or self._now()
        with self.conn:
            # supersede prior current mileage for this unit
            if m.status == "current":
                self.conn.execute("UPDATE service_loaner_checkout_mileage_fact SET status='superseded' WHERE "
                                  "service_loaner_unit_id=? AND status='current'", (m.service_loaner_unit_id,))
            self.conn.execute("INSERT INTO service_loaner_checkout_mileage_fact(id,service_loaner_unit_id,value_kind,"
                              "value,snapshot_ref,source,provenance,status,supersedes,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (m.id, m.service_loaner_unit_id, m.value_kind, m.value, m.snapshot_ref, m.source,
                               _j(m.provenance), m.status, m.supersedes, m.recorded_at))
        return m

    def current_mileage(self, unit_id):
        r = self.conn.execute("SELECT * FROM service_loaner_checkout_mileage_fact WHERE service_loaner_unit_id=? AND "
                              "status='current' ORDER BY recorded_at DESC,id DESC LIMIT 1", (unit_id,)).fetchone()
        return None if not r else CheckoutMileage(id=r["id"], service_loaner_unit_id=r["service_loaner_unit_id"],
                value_kind=r["value_kind"], value=r["value"], snapshot_ref=r["snapshot_ref"], source=r["source"],
                provenance=_d(r["provenance"]), status=r["status"], supersedes=r["supersedes"], recorded_at=r["recorded_at"])

    def mileage_history(self, unit_id):
        return self.conn.execute("SELECT * FROM service_loaner_checkout_mileage_fact WHERE service_loaner_unit_id=? "
                                 "ORDER BY recorded_at,id", (unit_id,)).fetchall()

    # ---- monitoring alerts -------------------------------------------------
    def add_alert(self, a: MonitoringAlert) -> MonitoringAlert:
        a.created_at = a.created_at or self._now()
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_monitoring_alert(id,service_loaner_unit_id,rule,prompt,status,"
                              "snapshot_ref,in_service_date,elapsed_days,threshold_days,policy_refs,cleared_reason,"
                              "created_at,cleared_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (a.id, a.service_loaner_unit_id, a.rule, a.prompt, a.status, a.snapshot_ref,
                               a.in_service_date, a.elapsed_days, a.threshold_days, _j(a.policy_refs),
                               a.cleared_reason, a.created_at, a.cleared_at))
        return a

    def clear_alert(self, alert_id, reason):
        with self.conn:
            self.conn.execute("UPDATE service_loaner_monitoring_alert SET status='cleared',cleared_reason=?,cleared_at=? "
                              "WHERE id=?", (reason, self._now(), alert_id))

    def active_alert(self, unit_id, rule):
        r = self.conn.execute("SELECT * FROM service_loaner_monitoring_alert WHERE service_loaner_unit_id=? AND rule=? "
                              "AND status='active' ORDER BY created_at DESC LIMIT 1", (unit_id, rule)).fetchone()
        return None if not r else self._alert(r)

    def alerts_for(self, unit_id):
        return [self._alert(r) for r in self.conn.execute("SELECT * FROM service_loaner_monitoring_alert WHERE "
                "service_loaner_unit_id=? ORDER BY created_at,id", (unit_id,)).fetchall()]

    @staticmethod
    def _alert(r):
        return MonitoringAlert(id=r["id"], service_loaner_unit_id=r["service_loaner_unit_id"], rule=r["rule"],
                prompt=r["prompt"], status=r["status"], snapshot_ref=r["snapshot_ref"], in_service_date=r["in_service_date"],
                elapsed_days=r["elapsed_days"], threshold_days=r["threshold_days"], policy_refs=_l(r["policy_refs"]),
                cleared_reason=r["cleared_reason"], created_at=r["created_at"], cleared_at=r["cleared_at"])

    # ---- entry candidates + portfolio plan --------------------------------
    def add_entry_candidate(self, vehicle_unit_id, combination_id, scope, *, eligibility, eligibility_reasons=None,
                            availability=None, new_retail_opportunity_cost=None, actual_state=None):
        cid = new_id("slc")
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_entry_candidate(id,vehicle_unit_id,combination_id,store_scope,"
                              "eligibility,eligibility_reasons,availability,new_retail_opportunity_cost,actual_state,"
                              "recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (cid, vehicle_unit_id, combination_id, scope, eligibility, _j(eligibility_reasons or []),
                               availability, _j(new_retail_opportunity_cost or {}), actual_state, self._now()))
        return cid

    def add_portfolio_plan(self, scope, *, required_quantity, current_active, selected, sacrifices=None,
                           need_basis=None, policy_versions=None, calculation_version=None, scenario_id=None):
        pid = new_id("slp")
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_portfolio_plan(id,store_scope,required_quantity,current_active,"
                              "selected,sacrifices,need_basis,policy_versions,calculation_version,scenario_id,issued_time,"
                              "status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (pid, scope, required_quantity, current_active, _j(selected), _j(sacrifices or []),
                               _j(need_basis or {}), _j(policy_versions or []), calculation_version, scenario_id,
                               self._now(), "issued"))
        self._issued("portfolio_plan", pid, None, scope, calculation_version, scenario_id)
        return self.conn.execute("SELECT * FROM service_loaner_portfolio_plan WHERE id=?", (pid,)).fetchone()

    # ---- economic result + execution status -------------------------------
    def add_economic(self, e: EconomicResult) -> EconomicResult:
        e.issued_time = e.issued_time or self._now()
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_economic_result(id,service_loaner_unit_id,store_scope,"
                              "decision_point,alternatives,economic_call,assumptions,uncertainty,resolution_status,"
                              "policy_versions,calculation_version,fact_refs,reproducibility_package,scenario_id,issued_time,"
                              "status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (e.id, e.service_loaner_unit_id, e.store_scope, e.decision_point, _j(e.alternatives),
                               _j(e.economic_call), _j(e.assumptions), _j(e.uncertainty), e.resolution_status,
                               _j(e.policy_versions), e.calculation_version, _j(e.fact_refs), e.reproducibility_package,
                               e.scenario_id, e.issued_time, e.status))
        self._issued("economic", e.id, e.service_loaner_unit_id, e.store_scope, e.calculation_version, e.scenario_id)
        return e

    def get_economic(self, eid):
        r = self.conn.execute("SELECT * FROM service_loaner_economic_result WHERE id=?", (eid,)).fetchone()
        if not r:
            return None
        return EconomicResult(id=r["id"], service_loaner_unit_id=r["service_loaner_unit_id"], store_scope=r["store_scope"],
                resolution_status=r["resolution_status"], decision_point=r["decision_point"],
                alternatives=_l(r["alternatives"]), economic_call=_d(r["economic_call"]), assumptions=_d(r["assumptions"]),
                uncertainty=_d(r["uncertainty"]), policy_versions=_l(r["policy_versions"]),
                calculation_version=r["calculation_version"], fact_refs=_l(r["fact_refs"]),
                reproducibility_package=r["reproducibility_package"], scenario_id=r["scenario_id"],
                issued_time=r["issued_time"], status=r["status"])

    def add_execution_status(self, unit_id, economic_result_id, status, *, reason="", blocking_factors=None):
        sid = new_id("sles")
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_execution_status(id,service_loaner_unit_id,economic_result_id,"
                              "status,reason,blocking_factors,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (sid, unit_id, economic_result_id, status, reason, _j(blocking_factors or []), self._now()))
        return self.conn.execute("SELECT * FROM service_loaner_execution_status WHERE id=?", (sid,)).fetchone()

    # ---- retirement --------------------------------------------------------
    def add_retirement_eligibility(self, unit_id, eligible, *, reasons=None, policy_versions=None, tenure_days=None):
        rid = new_id("slre")
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_retirement_eligibility(id,service_loaner_unit_id,eligible,"
                              "reasons,policy_versions,tenure_days,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (rid, unit_id, int(eligible), _j(reasons or []), _j(policy_versions or []), tenure_days,
                               self._now()))
        return rid

    def insert_retirement_action(self, conn, a: RetirementAction) -> RetirementAction:
        a.created_at = a.created_at or self._now()
        conn.execute("INSERT INTO service_loaner_retirement_action(id,service_loaner_unit_id,store_scope,lifecycle_status,"
                     "economic_result_id,decision_ref,approval_time,provisional,cancellation_status,correction_of,"
                     "created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (a.id, a.service_loaner_unit_id, a.store_scope, a.lifecycle_status, a.economic_result_id,
                      a.decision_ref, a.approval_time, int(a.provisional), a.cancellation_status, a.correction_of,
                      a.created_at, a.version))
        return a

    def add_retirement_action(self, a: RetirementAction) -> RetirementAction:
        with self.conn:
            self.insert_retirement_action(self.conn, a)
        return a

    def get_retirement_action(self, aid):
        r = self.conn.execute("SELECT * FROM service_loaner_retirement_action WHERE id=?", (aid,)).fetchone()
        if not r:
            return None
        return RetirementAction(id=r["id"], service_loaner_unit_id=r["service_loaner_unit_id"], store_scope=r["store_scope"],
                lifecycle_status=r["lifecycle_status"], economic_result_id=r["economic_result_id"],
                decision_ref=r["decision_ref"], approval_time=r["approval_time"], provisional=bool(r["provisional"]),
                cancellation_status=r["cancellation_status"], correction_of=r["correction_of"], created_at=r["created_at"],
                version=r["version"])

    def set_retirement_action(self, conn, aid, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE service_loaner_retirement_action SET {cols},version=version+1 WHERE id=?",
                     (*fields.values(), aid))

    def add_return_confirmation(self, conn, unit_id, retirement_action_id, *, actual_event_ref, confirmed_by):
        cid = new_id("slrc")
        conn.execute("INSERT INTO service_loaner_return_confirmation(id,service_loaner_unit_id,retirement_action_id,"
                     "actual_event_ref,confirmed_by,confirmed_at) VALUES(?,?,?,?,?,?)",
                     (cid, unit_id, retirement_action_id, actual_event_ref, confirmed_by, self._now()))
        return cid

    def add_retirement_event(self, conn, unit_id, retirement_action_id, return_confirmation_id, scope):
        eid = new_id("slrev")
        conn.execute("INSERT INTO service_loaner_retirement_event(id,service_loaner_unit_id,retirement_action_id,"
                     "return_confirmation_id,store_scope,membership_reconciled,event_time) VALUES(?,?,?,?,?,?,?)",
                     (eid, unit_id, retirement_action_id, return_confirmation_id, scope, 1, self._now()))
        return eid

    # ---- used cars receipt (idempotent, immutable) ------------------------
    def add_used_cars_receipt(self, conn, unit_id, vehicle_unit_id, retirement_event_ref, scope, *,
                              confirming_principal, correlation_id=None, audit_ref=None):
        rid = new_id("ucr")
        conn.execute("INSERT INTO used_cars_receipt(id,service_loaner_unit_id,vehicle_unit_id,retirement_event_ref,"
                     "store_scope,confirming_principal,correlation_id,audit_ref,confirmed_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (rid, unit_id, vehicle_unit_id, retirement_event_ref, scope, confirming_principal, correlation_id,
                      audit_ref, self._now()))
        return rid

    def used_cars_receipt_for(self, unit_id):
        return self.conn.execute("SELECT * FROM used_cars_receipt WHERE service_loaner_unit_id=?", (unit_id,)).fetchone()

    # ---- service loaner reconciliation ------------------------------------
    def insert_reconciliation(self, conn, unit_id, vehicle_unit_id, scope, outcome, *, supply_ref=None, detail=""):
        rid = new_id("slrr")
        conn.execute("INSERT INTO service_loaner_reconciliation_result(id,service_loaner_unit_id,vehicle_unit_id,"
                     "store_scope,outcome,supply_ref,detail,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                     (rid, unit_id, vehicle_unit_id, scope, outcome, supply_ref, detail, self._now()))
        return rid

    def add_reconciliation(self, unit_id, vehicle_unit_id, scope, outcome, *, supply_ref=None, detail=""):
        with self.conn:
            return self.insert_reconciliation(self.conn, unit_id, vehicle_unit_id, scope, outcome,
                                              supply_ref=supply_ref, detail=detail)

    def reconciliations_for(self, unit_id):
        return self.conn.execute("SELECT * FROM service_loaner_reconciliation_result WHERE service_loaner_unit_id=? "
                                 "ORDER BY recorded_at,id", (unit_id,)).fetchall()

    # ---- scenario + resale + issued ---------------------------------------
    def add_scenario_result(self, scenario_id, scope, kind, overrides, output, *, baseline_ref=None):
        sid = new_id("slsr")
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_scenario_result(id,scenario_id,store_scope,kind,overrides,"
                              "output,baseline_ref,issued_time) VALUES(?,?,?,?,?,?,?,?)",
                              (sid, scenario_id, scope, kind, _j(overrides), _j(output), baseline_ref, self._now()))
        return self.conn.execute("SELECT * FROM service_loaner_scenario_result WHERE id=?", (sid,)).fetchone()

    def add_resale_reference(self, unit_id, *, retirement_event_ref=None, used_cars_receipt_ref=None,
                             resale_event_ref=None, resale_timing=None, resale_value=None, predicted_ref=None,
                             observed_ref=None):
        rid = new_id("slres")
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_resale_reference(id,service_loaner_unit_id,retirement_event_ref,"
                              "used_cars_receipt_ref,resale_event_ref,resale_timing,resale_value,predicted_ref,observed_ref,"
                              "recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (rid, unit_id, retirement_event_ref, used_cars_receipt_ref, resale_event_ref, resale_timing,
                               _j(resale_value or {}), predicted_ref, observed_ref, self._now()))
        return rid

    def _issued(self, output_type, output_id, unit_id, scope, calc_version, scenario_id):
        with self.conn:
            self.conn.execute("INSERT INTO service_loaner_issued_output(id,output_type,output_id,service_loaner_unit_id,"
                              "store_scope,calculation_version,scenario_id,issued_time) VALUES(?,?,?,?,?,?,?,?)",
                              (new_id("slio"), output_type, output_id, unit_id, scope, calc_version, scenario_id,
                               self._now()))

    def issued_outputs(self, output_type=None):
        if output_type:
            return self.conn.execute("SELECT * FROM service_loaner_issued_output WHERE output_type=? ORDER BY issued_time",
                                     (output_type,)).fetchall()
        return self.conn.execute("SELECT * FROM service_loaner_issued_output ORDER BY issued_time").fetchall()
