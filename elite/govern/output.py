"""Operational workspace output slices — smallest REAL structured outputs for Phase 10.

Each uses stored records and exposes Call / Why / Proof + references (recommendation / Economic Call /
Execution Status / Decision / approval / execution / reconciliation), versions, evidence, Scenario
identity, responsible Principal, authority, expiration, staleness, Audit references, and a Raw History
path. Not the full Phase 10 UX.
"""
from __future__ import annotations

import json


def _item(it):
    return {"workspace_item_id": it["id"], "domain": it["owning_domain"],
            "subject": (it["subject_entity_type"], it["subject_entity_id"]), "call": it["workspace_state"],
            "recommendation_ref": it["recommendation_ref"], "economic_call_ref": it["economic_call_ref"],
            "execution_status_ref": it["execution_status_ref"], "decision_ref": it["decision_ref"],
            "approval_state": it["approval_state"], "execution_state": it["execution_state"],
            "scenario_id": it["scenario_id"], "priority": it["priority"], "expiration": it["expiration"],
            "stale": bool(it["stale"]), "required_authority": it["required_authority"],
            "raw_history_path": f"decision_workspace_item/{it['id']}"}


def decision_inbox(store, *, scope=None):
    return [_item(it) for it in store.all_items(scope=scope)
            if it["workspace_state"] not in ("SUPERSEDED", "CANCELLED", "COMPLETED")]


def recommendation_detail(store, item_id, *, resolvers=None):
    from .workspace import WorkspaceService
    it = store.get_workspace_item(item_id)
    return WorkspaceService(store, None).review(it, resolvers=resolvers) if it else None


def decision_slice(store, decision_id):
    d = store.get_decision(decision_id)
    if d is None:
        return None
    return {"decision_id": d["id"], "disposition": d["disposition"], "selected_action": d["selected_action"],
            "decision_maker": d["decision_maker"], "rationale": d["rationale"], "override": bool(d["override"]),
            "override_reason": d["override_reason"], "scenario_id": d["scenario_id"],
            "source_recommendation_ref": d["source_recommendation_ref"],
            "recommendation_revision": d["recommendation_revision"], "correction_of": d["correction_of"],
            "supersedes": d["supersedes"], "versions": json.loads(d["versions"] or "{}"),
            "alternatives": [{"alternative": a["alternative"], "presented": bool(a["presented"])}
                             for a in store.alternatives_for(d["id"])],
            "reconciliation": [r["outcome"] for r in store.reconciliations_for(d["id"])],
            "raw_history_path": f"governed_decision/{d['id']}"}


def approval_queue(store, *, scope=None):
    return [_item(it) for it in store.items_in_state("DECIDED", scope=scope)]


def execution_queue(store, *, scope=None):
    return [_item(it) for it in store.all_items(scope=scope)
            if it["workspace_state"] in ("APPROVED", "AWAITING_EXECUTION", "IN_EXECUTION")]


def acknowledgment_queue(store, *, scope=None):
    out = []
    for it in store.all_items(scope=scope):
        if it["decision_ref"] and not store.acks_for_decision(it["decision_ref"]):
            out.append(_item(it))
    return out


def stale_expired_queue(store, *, scope=None):
    return [_item(it) for it in store.all_items(scope=scope)
            if bool(it["stale"]) or it["workspace_state"] in ("STALE", "EXPIRED")]


def scenario_admin_slice(store, *, status=None):
    rows = store.scenarios_in_state(status) if status else \
        store.conn.execute("SELECT * FROM scenario_administration ORDER BY created_at,id").fetchall()
    return [{"scenario_admin_id": s["id"], "scenario_id": s["scenario_id"], "owner": s["owner"],
             "domain": s["owning_domain"], "status": s["status"], "reviewer": s["reviewer"],
             "expiration": s["expiration"], "raw_history_path": f"scenario_administration/{s['id']}"} for s in rows]


def scenario_comparison(store, scenario_admin_id):
    s = store.get_scenario(scenario_admin_id)
    if s is None:
        return None
    return {"scenario_id": s["scenario_id"], "overrides": json.loads(s["overrides"] or "{}"),
            "official_baseline_ref": s["official_baseline_ref"],
            "comparison_output": json.loads(s["comparison_output"] or "{}"), "status": s["status"]}


def promotion_queue(store, *, status="requested"):
    return [{"promotion_id": p["id"], "scenario_admin_id": p["scenario_admin_id"], "target_type": p["target_type"],
             "routed_to": p["routed_to"], "status": p["status"], "review_ref": p["review_ref"]}
            for p in store.promotions_in_state(status)]


def authority_admin_slice(store, delegate=None):
    q = "SELECT * FROM authority_delegation" + (" WHERE delegate=?" if delegate else "") + " ORDER BY granted_at,id"
    rows = store.conn.execute(q, ((delegate,) if delegate else ())).fetchall()
    return [{"delegation_id": d["id"], "delegator": d["delegator"], "delegate": d["delegate"],
             "capability": d["capability"], "scope": d["scope"], "active": bool(d["active"]),
             "grant_ref": d["grant_ref"], "expiration": d["expiration"]} for d in rows]


def sod_exceptions_slice(store):
    return [{"exception_id": e["id"], "rule_id": e["rule_id"], "actor_a": e["actor_a"], "actor_b": e["actor_b"],
             "override": bool(e["override"]), "override_principal": e["override_principal"],
             "override_reason": e["override_reason"], "detail": e["detail"]} for e in store.sod_exceptions()]


def audit_review_slice(audit_admin, principal, scope, **filters):
    rows = audit_admin.review(principal, scope, **filters)
    return [{"audit_id": r["id"], "actor": r["actor"], "action": r["action"], "result": r["result"],
             "target_ref": r["target_ref"], "correlation_id": r["correlation_id"], "scope": r["scope"]}
            for r in rows]


def exception_queue_slice(store, *, queue=None, status="open"):
    return [{"exception_id": e["id"], "queue": e["queue"], "domain": e["owning_domain"],
             "source_type": e["source_type"], "source_ref": e["source_ref"], "priority": e["priority"],
             "status": e["status"], "reason": e["reason"],
             "raw_history_path": f"{e['source_type']}/{e['source_ref']}"}
            for e in store.op_exceptions(queue=queue, status=status)]


def readiness_slice(store, owning_domain):
    rows = store.readiness_for(owning_domain)
    if not rows:
        return None
    r = rows[-1]
    return {"domain": r["owning_domain"], "classification": r["classification"],
            "blockers": json.loads(r["blockers"] or "[]"), "warnings": json.loads(r["warnings"] or "[]"),
            "required_policy_present": bool(r["required_policy_present"]),
            "authority_coverage": bool(r["authority_coverage"]), "revision": r["revision"],
            "raw_history_path": f"domain_readiness_assessment/{r['id']}"}
