"""SQLite repositories for Phase 9 governance + operational-control records.

Governed Decisions, readiness assessments, and acknowledgments are immutable; everything else is
append-preserving (no-delete). Raw `insert_*`/`set_*` helpers run on a caller-supplied connection so a
governed action's business write + Audit Event commit atomically (Phase 1 Governor). This store
REFERENCES authoritative domain records by id; it never copies domain calculations.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id


def _j(v):
    return json.dumps(v)


def _l(s):
    return json.loads(s) if s else []


def _d(s):
    return json.loads(s) if s else {}


class GovernStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- Decision Workspace item ------------------------------------------
    def add_workspace_item(self, **kw):
        wid = kw.get("id") or new_id("dwi")
        with self.conn:
            self._insert_workspace(self.conn, wid, kw)
        return self.get_workspace_item(wid)

    def _insert_workspace(self, conn, wid, kw):
        conn.execute(
            "INSERT INTO decision_workspace_item(id,owning_domain,subject_entity_type,subject_entity_id,store_scope,"
            "org_scope,recommendation_ref,prediction_ref,economic_call_ref,execution_status_ref,planning_refs,"
            "scenario_id,priority,unresolved,assigned_reviewer,required_authority,workspace_state,decision_ref,"
            "approval_state,execution_state,completion_state,acknowledgment_state,expiration,stale,evidence_refs,"
            "raw_history_refs,applicable_facts,applicable_versions,correction_of,superseded_by,created_at,version) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, kw.get("owning_domain"), kw.get("subject_entity_type"), kw.get("subject_entity_id"),
             kw["store_scope"], kw.get("org_scope"), kw.get("recommendation_ref"), kw.get("prediction_ref"),
             kw.get("economic_call_ref"), kw.get("execution_status_ref"), _j(kw.get("planning_refs", [])),
             kw.get("scenario_id"), kw.get("priority"), kw.get("unresolved"), kw.get("assigned_reviewer"),
             kw.get("required_authority"), kw.get("workspace_state", "OPEN"), kw.get("decision_ref"),
             kw.get("approval_state"), kw.get("execution_state"), kw.get("completion_state"),
             kw.get("acknowledgment_state"), kw.get("expiration"), int(kw.get("stale", 0)),
             _j(kw.get("evidence_refs", [])), _j(kw.get("raw_history_refs", [])), _j(kw.get("applicable_facts", [])),
             _j(kw.get("applicable_versions", {})), kw.get("correction_of"), kw.get("superseded_by"), self._now(), 1))

    def get_workspace_item(self, wid):
        return self.conn.execute("SELECT * FROM decision_workspace_item WHERE id=?", (wid,)).fetchone()

    def set_workspace_item(self, conn, wid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = conn.execute(f"UPDATE decision_workspace_item SET {cols},version=version+1 WHERE id=? AND version=?",
                           (*fields.values(), wid, expected_version))
        return cur.rowcount

    def set_workspace_item_now(self, wid, expected_version, **fields):
        with self.conn:
            return self.set_workspace_item(self.conn, wid, expected_version, **fields)

    def items_in_state(self, workspace_state, *, scope=None):
        q, args = "SELECT * FROM decision_workspace_item WHERE workspace_state=?", [workspace_state]
        if scope:
            q, _ = q + " AND store_scope=?", args.append(scope)
        return self.conn.execute(q + " ORDER BY created_at,id", args).fetchall()

    def all_items(self, *, scope=None):
        q, args = "SELECT * FROM decision_workspace_item WHERE 1=1", []
        if scope:
            q, _ = q + " AND store_scope=?", args.append(scope)
        return self.conn.execute(q + " ORDER BY created_at,id", args).fetchall()

    def add_workspace_revision(self, conn, workspace_item_id, revision_no, *, recommendation_ref=None,
                               workspace_state=None, snapshot=None, reason=""):
        rid = new_id("dwr")
        conn.execute("INSERT INTO decision_workspace_revision(id,workspace_item_id,revision_no,recommendation_ref,"
                     "workspace_state,snapshot,reason,at) VALUES(?,?,?,?,?,?,?,?)",
                     (rid, workspace_item_id, revision_no, recommendation_ref, workspace_state,
                      _j(snapshot or {}), reason, self._now()))
        return rid

    def workspace_revisions(self, workspace_item_id):
        return self.conn.execute("SELECT * FROM decision_workspace_revision WHERE workspace_item_id=? "
                                 "ORDER BY revision_no,at", (workspace_item_id,)).fetchall()

    # ---- Governed Decision -------------------------------------------------
    def insert_decision(self, conn, **kw):
        did = kw.get("id") or new_id("gdec")
        conn.execute(
            "INSERT INTO governed_decision(id,workspace_item_id,owning_domain,subject_entity_type,subject_entity_id,"
            "store_scope,decision_type,disposition,selected_action,selected_alternative,decision_maker,decision_time,"
            "rationale,confidence_ack,uncertainty_ack,operational_constraints,source_recommendation_ref,"
            "recommendation_revision,facts,versions,scenario_id,expiration,idempotency_key,correlation_id,override,"
            "override_reason,correction_of,supersedes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, kw.get("workspace_item_id"), kw.get("owning_domain"), kw.get("subject_entity_type"),
             kw.get("subject_entity_id"), kw["store_scope"], kw.get("decision_type"), kw["disposition"],
             kw.get("selected_action"), kw.get("selected_alternative"), kw.get("decision_maker"),
             kw.get("decision_time") or self._now(), kw.get("rationale"), kw.get("confidence_ack"),
             kw.get("uncertainty_ack"), _j(kw.get("operational_constraints", [])), kw.get("source_recommendation_ref"),
             kw.get("recommendation_revision"), _j(kw.get("facts", [])), _j(kw.get("versions", {})),
             kw.get("scenario_id"), kw.get("expiration"), kw.get("idempotency_key"), kw.get("correlation_id"),
             int(kw.get("override", 0)), kw.get("override_reason"), kw.get("correction_of"), kw.get("supersedes"),
             self._now()))
        return did

    def get_decision(self, did):
        return self.conn.execute("SELECT * FROM governed_decision WHERE id=?", (did,)).fetchone()

    def decisions_for_item(self, workspace_item_id):
        return self.conn.execute("SELECT * FROM governed_decision WHERE workspace_item_id=? ORDER BY created_at,id",
                                 (workspace_item_id,)).fetchall()

    def add_alternative(self, conn, decision_id, alternative, *, presented=True, detail=""):
        aid = new_id("dalt")
        conn.execute("INSERT INTO decision_alternative(id,decision_id,alternative,presented,detail,recorded_at) "
                     "VALUES(?,?,?,?,?,?)", (aid, decision_id, alternative, int(presented), detail, self._now()))
        return aid

    def alternatives_for(self, decision_id):
        return self.conn.execute("SELECT * FROM decision_alternative WHERE decision_id=? ORDER BY recorded_at,id",
                                 (decision_id,)).fetchall()

    # ---- Approval ----------------------------------------------------------
    def insert_approval(self, conn, decision_id, **kw):
        aid = kw.get("id") or new_id("dapp")
        conn.execute(
            "INSERT INTO decision_approval(id,decision_id,approving_principal,approval_time,scope,authority,"
            "approved_action,quantity,subject_identity,conditions,expiration,idempotency_key,status,correction_of,"
            "revoked,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, decision_id, kw.get("approving_principal"), kw.get("approval_time") or self._now(), kw.get("scope"),
             kw.get("authority", "granted"), kw.get("approved_action"), kw.get("quantity"),
             kw.get("subject_identity"), _j(kw.get("conditions", {})), kw.get("expiration"),
             kw.get("idempotency_key"), kw.get("status", "approved"), kw.get("correction_of"),
             int(kw.get("revoked", 0)), self._now()))
        return aid

    def get_approval(self, aid):
        return self.conn.execute("SELECT * FROM decision_approval WHERE id=?", (aid,)).fetchone()

    def approvals_for(self, decision_id):
        return self.conn.execute("SELECT * FROM decision_approval WHERE decision_id=? ORDER BY created_at,id",
                                 (decision_id,)).fetchall()

    # ---- Execution authorization ------------------------------------------
    def insert_execution_auth(self, conn, decision_id, **kw):
        eid = kw.get("id") or new_id("exauth")
        conn.execute(
            "INSERT INTO execution_authorization(id,decision_id,approval_id,execution_capability,authorized_executor,"
            "authorized_time,expiration,expected_action,domain_execution_ref,completion_ref,reconciliation_outcome,"
            "state,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, decision_id, kw.get("approval_id"), kw.get("execution_capability"), kw.get("authorized_executor"),
             kw.get("authorized_time") or self._now(), kw.get("expiration"), kw.get("expected_action"),
             kw.get("domain_execution_ref"), kw.get("completion_ref"), kw.get("reconciliation_outcome"),
             kw.get("state", "authorized"), kw.get("idempotency_key"), self._now()))
        return eid

    def get_execution_auth(self, eid):
        return self.conn.execute("SELECT * FROM execution_authorization WHERE id=?", (eid,)).fetchone()

    def set_execution_auth(self, conn, eid, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE execution_authorization SET {cols} WHERE id=?", (*fields.values(), eid))

    def execauths_for(self, decision_id):
        return self.conn.execute("SELECT * FROM execution_authorization WHERE decision_id=? ORDER BY created_at,id",
                                 (decision_id,)).fetchall()

    # ---- reconciliation ----------------------------------------------------
    def insert_reconciliation(self, conn, decision_id, outcome, *, approval_id=None, execution_authorization_id=None,
                              detail=""):
        rid = new_id("drec")
        conn.execute("INSERT INTO decision_execution_reconciliation(id,decision_id,approval_id,"
                     "execution_authorization_id,outcome,detail,recorded_at) VALUES(?,?,?,?,?,?,?)",
                     (rid, decision_id, approval_id, execution_authorization_id, outcome, detail, self._now()))
        return rid

    def add_reconciliation(self, decision_id, outcome, **kw):
        with self.conn:
            return self.insert_reconciliation(self.conn, decision_id, outcome, **kw)

    def reconciliations_for(self, decision_id):
        return self.conn.execute("SELECT * FROM decision_execution_reconciliation WHERE decision_id=? "
                                 "ORDER BY recorded_at,id", (decision_id,)).fetchall()

    # ---- acknowledgment ----------------------------------------------------
    def insert_ack(self, conn, **kw):
        aid = kw.get("id") or new_id("dack")
        conn.execute("INSERT INTO decision_acknowledgment(id,decision_id,workspace_item_id,acknowledging_principal,"
                     "acknowledgment_type,acknowledged_at,comment,scope,correlation_id,idempotency_key,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (aid, kw.get("decision_id"), kw.get("workspace_item_id"), kw.get("acknowledging_principal"),
                      kw.get("acknowledgment_type", "receipt"), kw.get("acknowledged_at") or self._now(),
                      kw.get("comment"), kw.get("scope"), kw.get("correlation_id"), kw.get("idempotency_key"),
                      self._now()))
        return aid

    def ack_by_idempotency(self, key):
        return self.conn.execute("SELECT * FROM decision_acknowledgment WHERE idempotency_key=?", (key,)).fetchone()

    def acks_for_decision(self, decision_id):
        return self.conn.execute("SELECT * FROM decision_acknowledgment WHERE decision_id=? ORDER BY created_at,id",
                                 (decision_id,)).fetchall()

    # ---- expiration + staleness -------------------------------------------
    def add_expiration(self, target_type, target_ref, *, expires_at=None, policy_versions=None):
        eid = new_id("gexp")
        with self.conn:
            self.conn.execute("INSERT INTO governance_expiration(id,target_type,target_ref,expires_at,expired,"
                              "policy_versions,recorded_at) VALUES(?,?,?,?,?,?,?)",
                              (eid, target_type, target_ref, expires_at, 0, _j(policy_versions or []), self._now()))
        return eid

    def mark_expired(self, eid):
        with self.conn:
            self.conn.execute("UPDATE governance_expiration SET expired=1 WHERE id=?", (eid,))

    def expirations_for(self, target_ref):
        return self.conn.execute("SELECT * FROM governance_expiration WHERE target_ref=? ORDER BY recorded_at",
                                 (target_ref,)).fetchall()

    def add_staleness(self, target_type, target_ref, *, stale, reason="", triggering_fact=None,
                      triggering_version=None, policy_versions=None):
        sid = new_id("gstale")
        with self.conn:
            self.conn.execute("INSERT INTO governance_staleness_result(id,target_type,target_ref,stale,reason,"
                              "triggering_fact,triggering_version,policy_versions,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)",
                              (sid, target_type, target_ref, int(stale), reason, triggering_fact, triggering_version,
                               _j(policy_versions or []), self._now()))
        return self.conn.execute("SELECT * FROM governance_staleness_result WHERE id=?", (sid,)).fetchone()

    def staleness_for(self, target_ref):
        return self.conn.execute("SELECT * FROM governance_staleness_result WHERE target_ref=? ORDER BY recorded_at",
                                 (target_ref,)).fetchall()

    # ---- Scenario administration ------------------------------------------
    def insert_scenario(self, conn, **kw):
        sid = kw.get("id") or new_id("scadm")
        conn.execute("INSERT INTO scenario_administration(id,scenario_id,owner,owning_domain,store_scope,description,"
                     "assumptions,overrides,official_baseline_ref,status,reviewer,expiration,comparison_output,"
                     "correction_of,superseded_by,created_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, kw["scenario_id"], kw.get("owner"), kw.get("owning_domain"), kw["store_scope"],
                      kw.get("description"), _j(kw.get("assumptions", {})), _j(kw.get("overrides", {})),
                      kw.get("official_baseline_ref"), kw.get("status", "DRAFT"), kw.get("reviewer"),
                      kw.get("expiration"), _j(kw.get("comparison_output", {})), kw.get("correction_of"),
                      kw.get("superseded_by"), self._now(), 1))
        return sid

    def add_scenario(self, **kw):
        with self.conn:
            sid = self.insert_scenario(self.conn, **kw)
        return self.get_scenario(sid)

    def get_scenario(self, sid):
        return self.conn.execute("SELECT * FROM scenario_administration WHERE id=?", (sid,)).fetchone()

    def set_scenario(self, conn, sid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = conn.execute(f"UPDATE scenario_administration SET {cols},version=version+1 WHERE id=? AND version=?",
                           (*fields.values(), sid, expected_version))
        return cur.rowcount

    def set_scenario_now(self, sid, expected_version, **fields):
        with self.conn:
            return self.set_scenario(self.conn, sid, expected_version, **fields)

    def scenarios_in_state(self, status):
        return self.conn.execute("SELECT * FROM scenario_administration WHERE status=? ORDER BY created_at,id",
                                 (status,)).fetchall()

    def add_scenario_share(self, scenario_admin_id, *, shared_by, shared_with, scope=None, note=""):
        sid = new_id("scsh")
        with self.conn:
            self.conn.execute("INSERT INTO scenario_share(id,scenario_admin_id,shared_by,shared_with,scope,note,"
                              "shared_at) VALUES(?,?,?,?,?,?,?)",
                              (sid, scenario_admin_id, shared_by, shared_with, scope, note, self._now()))
        return sid

    def shares_for(self, scenario_admin_id):
        return self.conn.execute("SELECT * FROM scenario_share WHERE scenario_admin_id=? ORDER BY shared_at",
                                 (scenario_admin_id,)).fetchall()

    def add_scenario_review(self, scenario_admin_id, *, reviewer, outcome, comment=""):
        rid = new_id("screv")
        with self.conn:
            self.conn.execute("INSERT INTO scenario_review(id,scenario_admin_id,reviewer,outcome,comment,reviewed_at) "
                              "VALUES(?,?,?,?,?,?)", (rid, scenario_admin_id, reviewer, outcome, comment, self._now()))
        return rid

    def insert_promotion(self, conn, scenario_admin_id, target_type, **kw):
        pid = kw.get("id") or new_id("scprom")
        conn.execute("INSERT INTO scenario_promotion_request(id,scenario_admin_id,target_type,requested_by,routed_to,"
                     "review_ref,status,evidence,limitations,rejection_reason,created_at,version) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (pid, scenario_admin_id, target_type, kw.get("requested_by"), kw.get("routed_to"),
                      kw.get("review_ref"), kw.get("status", "requested"), _j(kw.get("evidence", {})),
                      _j(kw.get("limitations", {})), kw.get("rejection_reason"), self._now(), 1))
        return pid

    def get_promotion(self, pid):
        return self.conn.execute("SELECT * FROM scenario_promotion_request WHERE id=?", (pid,)).fetchone()

    def set_promotion(self, conn, pid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = conn.execute(f"UPDATE scenario_promotion_request SET {cols},version=version+1 WHERE id=? AND version=?",
                           (*fields.values(), pid, expected_version))
        return cur.rowcount

    def promotions_in_state(self, status):
        return self.conn.execute("SELECT * FROM scenario_promotion_request WHERE status=? ORDER BY created_at,id",
                                 (status,)).fetchall()

    def add_policy_review_request(self, conn, *, source_type, source_ref, requested_by, target_policy_family=None,
                                  rationale=""):
        rid = new_id("prr")
        conn.execute("INSERT INTO policy_review_request(id,source_type,source_ref,requested_by,target_policy_family,"
                     "rationale,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (rid, source_type, source_ref, requested_by, target_policy_family, rationale, "open", self._now()))
        return rid

    def policy_review_requests(self):
        return self.conn.execute("SELECT * FROM policy_review_request ORDER BY created_at,id").fetchall()

    # ---- authority admin ---------------------------------------------------
    def insert_delegation(self, conn, **kw):
        did = kw.get("id") or new_id("adel")
        conn.execute("INSERT INTO authority_delegation(id,delegator,delegate,capability,scope,grant_ref,reason,"
                     "granted_at,expiration,active,revoked_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (did, kw["delegator"], kw["delegate"], kw["capability"], kw["scope"], kw.get("grant_ref"),
                      kw.get("reason"), self._now(), kw.get("expiration"), 1, None, 1))
        return did

    def get_delegation(self, did):
        return self.conn.execute("SELECT * FROM authority_delegation WHERE id=?", (did,)).fetchone()

    def set_delegation(self, conn, did, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = conn.execute(f"UPDATE authority_delegation SET {cols},version=version+1 WHERE id=? AND version=?",
                           (*fields.values(), did, expected_version))
        return cur.rowcount

    def delegations_for(self, delegate):
        return self.conn.execute("SELECT * FROM authority_delegation WHERE delegate=? ORDER BY granted_at,id",
                                 (delegate,)).fetchall()

    def insert_temporary_grant(self, conn, **kw):
        tid = kw.get("id") or new_id("atmp")
        conn.execute("INSERT INTO authority_temporary_grant(id,principal_id,capability,scope,grant_ref,grantor,reason,"
                     "effective_start,expiration,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (tid, kw["principal_id"], kw["capability"], kw["scope"], kw.get("grant_ref"), kw.get("grantor"),
                      kw.get("reason"), kw.get("effective_start"), kw["expiration"], self._now()))
        return tid

    def temporary_grants_for(self, principal_id):
        return self.conn.execute("SELECT * FROM authority_temporary_grant WHERE principal_id=? ORDER BY created_at",
                                 (principal_id,)).fetchall()

    # ---- separation of duties ---------------------------------------------
    def add_sod_rule(self, *, rule_type, owning_domain=None, action_a=None, action_b=None,
                     materiality_threshold=None, scope=None, policy_versions=None):
        rid = new_id("sodr")
        with self.conn:
            self.conn.execute("INSERT INTO separation_of_duties_rule(id,rule_type,owning_domain,action_a,action_b,"
                              "materiality_threshold,scope,policy_versions,status,created_at,version) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              (rid, rule_type, owning_domain, action_a, action_b, materiality_threshold, scope,
                               _j(policy_versions or []), "active", self._now(), 1))
        return self.conn.execute("SELECT * FROM separation_of_duties_rule WHERE id=?", (rid,)).fetchone()

    def sod_rules(self, *, rule_type=None):
        if rule_type:
            return self.conn.execute("SELECT * FROM separation_of_duties_rule WHERE rule_type=? AND status='active'",
                                     (rule_type,)).fetchall()
        return self.conn.execute("SELECT * FROM separation_of_duties_rule WHERE status='active'").fetchall()

    def insert_sod_exception(self, conn, **kw):
        eid = kw.get("id") or new_id("sode")
        conn.execute("INSERT INTO separation_of_duties_exception(id,rule_id,decision_ref,actor_a,actor_b,detail,"
                     "override,override_principal,override_reason,audit_ref,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, kw.get("rule_id"), kw.get("decision_ref"), kw.get("actor_a"), kw.get("actor_b"),
                      kw.get("detail"), int(kw.get("override", 0)), kw.get("override_principal"),
                      kw.get("override_reason"), kw.get("audit_ref"), self._now()))
        return eid

    def add_sod_exception(self, **kw):
        with self.conn:
            return self.insert_sod_exception(self.conn, **kw)

    def sod_exceptions(self):
        return self.conn.execute("SELECT * FROM separation_of_duties_exception ORDER BY recorded_at,id").fetchall()

    # ---- audit exception ---------------------------------------------------
    def add_audit_exception(self, *, kind, expected_action=None, correlation_id=None, subject_ref=None, detail=""):
        eid = new_id("auex")
        with self.conn:
            self.conn.execute("INSERT INTO audit_exception(id,expected_action,correlation_id,subject_ref,kind,detail,"
                              "status,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                              (eid, expected_action, correlation_id, subject_ref, kind, detail, "open", self._now()))
        return self.conn.execute("SELECT * FROM audit_exception WHERE id=?", (eid,)).fetchone()

    def audit_exceptions(self):
        return self.conn.execute("SELECT * FROM audit_exception ORDER BY recorded_at,id").fetchall()

    # ---- operational exception queues -------------------------------------
    def add_op_exception(self, *, queue, source_type, source_ref, owning_domain=None, store_scope=None,
                         subject_entity_id=None, priority="normal", reason=""):
        eid = new_id("opex")
        with self.conn:
            self.conn.execute("INSERT INTO operational_exception_item(id,queue,owning_domain,source_type,source_ref,"
                              "store_scope,subject_entity_id,priority,reason,status,created_at,version) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (eid, queue, owning_domain, source_type, source_ref, store_scope, subject_entity_id,
                               priority, reason, "open", self._now(), 1))
        return self.get_op_exception(eid)

    def get_op_exception(self, eid):
        return self.conn.execute("SELECT * FROM operational_exception_item WHERE id=?", (eid,)).fetchone()

    def set_op_exception(self, conn, eid, expected_version, **fields):
        cols = ",".join(f"{k}=?" for k in fields)
        cur = conn.execute(f"UPDATE operational_exception_item SET {cols},version=version+1 WHERE id=? AND version=?",
                           (*fields.values(), eid, expected_version))
        return cur.rowcount

    def op_exceptions(self, *, queue=None, status="open"):
        q, args = "SELECT * FROM operational_exception_item WHERE status=?", [status]
        if queue:
            q, _ = q + " AND queue=?", args.append(queue)
        return self.conn.execute(q + " ORDER BY created_at,id", args).fetchall()

    # ---- operational-control summary --------------------------------------
    def add_summary(self, *, summary_type, grouping=None, store_scope=None, owning_domain=None, counts=None,
                    items=None):
        sid = new_id("ocs")
        with self.conn:
            self.conn.execute("INSERT INTO operational_control_summary(id,summary_type,grouping,store_scope,"
                              "owning_domain,counts,items,issued_at) VALUES(?,?,?,?,?,?,?,?)",
                              (sid, summary_type, grouping, store_scope, owning_domain, _j(counts or {}),
                               _j(items or []), self._now()))
        return self.conn.execute("SELECT * FROM operational_control_summary WHERE id=?", (sid,)).fetchone()

    # ---- readiness ---------------------------------------------------------
    def insert_readiness(self, conn, **kw):
        rid = kw.get("id") or new_id("rdy")
        conn.execute("INSERT INTO domain_readiness_assessment(id,owning_domain,store_scope,classification,"
                     "required_policy_present,calc_versions_active,source_contracts_available,unresolved_identities,"
                     "stale_imports,test_evidence,authority_coverage,sod_coverage,audit_health,unresolved_critical,"
                     "operational_owner,blockers,warnings,evidence,revision,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (rid, kw["owning_domain"], kw.get("store_scope"), kw["classification"],
                      int(kw.get("required_policy_present", 0)), int(kw.get("calc_versions_active", 0)),
                      int(kw.get("source_contracts_available", 0)), kw.get("unresolved_identities", 0),
                      kw.get("stale_imports", 0), _j(kw.get("test_evidence", {})),
                      int(kw.get("authority_coverage", 0)), int(kw.get("sod_coverage", 0)),
                      kw.get("audit_health", "unknown"), kw.get("unresolved_critical", 0), kw.get("operational_owner"),
                      _j(kw.get("blockers", [])), _j(kw.get("warnings", [])), _j(kw.get("evidence", {})),
                      kw.get("revision", 1), self._now()))
        return rid

    def add_readiness(self, **kw):
        with self.conn:
            rid = self.insert_readiness(self.conn, **kw)
        return self.get_readiness(rid)

    def get_readiness(self, rid):
        return self.conn.execute("SELECT * FROM domain_readiness_assessment WHERE id=?", (rid,)).fetchone()

    def readiness_for(self, owning_domain):
        return self.conn.execute("SELECT * FROM domain_readiness_assessment WHERE owning_domain=? "
                                 "ORDER BY created_at,id", (owning_domain,)).fetchall()

    # ---- issued output -----------------------------------------------------
    def issued(self, output_type, output_id, *, owning_domain=None, scope=None, scenario_id=None):
        with self.conn:
            self.conn.execute("INSERT INTO governance_issued_output(id,output_type,output_id,owning_domain,store_scope,"
                              "scenario_id,issued_time) VALUES(?,?,?,?,?,?,?)",
                              (new_id("gio"), output_type, output_id, owning_domain, scope, scenario_id, self._now()))

    def issued_outputs(self, output_type=None):
        if output_type:
            return self.conn.execute("SELECT * FROM governance_issued_output WHERE output_type=? ORDER BY issued_time",
                                     (output_type,)).fetchall()
        return self.conn.execute("SELECT * FROM governance_issued_output ORDER BY issued_time").fetchall()
