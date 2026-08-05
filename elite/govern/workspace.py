"""Consolidated Decision Workspace + recommendation review.

A workspace item REFERENCES authoritative domain output (recommendation / Prediction / Economic Call /
Execution Status / planning refs) — it never copies domain calculations into a second source of truth.
The workspace state summarizes operational control and never replaces the domain lifecycle. A changed
current recommendation creates a NEW revision (or a superseding item); prior reviewed recommendations
remain historical. Review exposes Call / Why / Proof + facts, versions, confidence, uncertainty, and a
Raw History path, and never invents missing explanation.
"""
from __future__ import annotations

from ..errors import ValidationError


class WorkspaceService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def create_item(self, *, owning_domain, store_scope, recommendation_ref, subject_entity_type=None,
                    subject_entity_id=None, economic_call_ref=None, execution_status_ref=None, prediction_ref=None,
                    planning_refs=None, scenario_id=None, priority="normal", unresolved=None, required_authority=None,
                    evidence_refs=None, raw_history_refs=None, applicable_facts=None, applicable_versions=None,
                    workspace_state="READY_FOR_REVIEW"):
        return self.store.add_workspace_item(
            owning_domain=owning_domain, store_scope=store_scope, recommendation_ref=recommendation_ref,
            subject_entity_type=subject_entity_type, subject_entity_id=subject_entity_id,
            economic_call_ref=economic_call_ref, execution_status_ref=execution_status_ref,
            prediction_ref=prediction_ref, planning_refs=planning_refs or [], scenario_id=scenario_id,
            priority=priority, unresolved=unresolved, required_authority=required_authority,
            evidence_refs=evidence_refs or [], raw_history_refs=raw_history_refs or [],
            applicable_facts=applicable_facts or [], applicable_versions=applicable_versions or {},
            workspace_state=workspace_state)

    def revise(self, item, *, new_recommendation_ref, reason, snapshot=None):
        """A changed current recommendation creates a new workspace revision (prior remains historical)."""
        n = len(self.store.workspace_revisions(item["id"])) + 1
        with self.store.conn:
            self.store.add_workspace_revision(self.store.conn, item["id"], n,
                                              recommendation_ref=item["recommendation_ref"],
                                              workspace_state=item["workspace_state"],
                                              snapshot=snapshot or {}, reason=reason)
            rc = self.store.set_workspace_item(self.store.conn, item["id"], item["version"],
                                               recommendation_ref=new_recommendation_ref,
                                               workspace_state="READY_FOR_REVIEW")
        if rc == 0:
            raise ValidationError(technical_detail="workspace item stale")
        return self.store.get_workspace_item(item["id"])

    def supersede(self, item, *, new_item_kw, reason):
        """Supersede an item with a new one (prior preserved, linked)."""
        new_item = self.create_item(owning_domain=item["owning_domain"], store_scope=item["store_scope"],
                                    **new_item_kw)
        self.store.set_workspace_item_now(item["id"], item["version"], workspace_state="SUPERSEDED",
                                          superseded_by=new_item["id"])
        return self.store.get_workspace_item(new_item["id"])

    def request_information(self, item, *, note=""):
        """Review may request additional information WITHOUT altering the source result."""
        self.store.set_workspace_item_now(item["id"], item["version"], workspace_state="AWAITING_INFORMATION")
        return self.store.get_workspace_item(item["id"])

    def review(self, item, *, resolvers=None):
        """Return the review projection (Call / Why / Proof) built from the referenced domain records.
        `resolvers` maps a ref field to a callable returning that domain record (never copied here —
        resolved live for display). Missing explanation stays absent (never invented)."""
        resolvers = resolvers or {}
        proof = {"recommendation_ref": item["recommendation_ref"], "prediction_ref": item["prediction_ref"],
                 "economic_call_ref": item["economic_call_ref"], "execution_status_ref": item["execution_status_ref"]}
        why = {}
        for key, fn in resolvers.items():
            why[key] = fn(item)
        import json
        return {"call": item["workspace_state"], "why": why, "proof": proof,
                "domain": item["owning_domain"], "subject": (item["subject_entity_type"], item["subject_entity_id"]),
                "priority": item["priority"], "unresolved": item["unresolved"], "scenario_id": item["scenario_id"],
                "applicable_facts": json.loads(item["applicable_facts"] or "[]"),
                "applicable_versions": json.loads(item["applicable_versions"] or "{}"),
                "evidence": json.loads(item["evidence_refs"] or "[]"),
                "raw_history_path": f"decision_workspace_item/{item['id']}",
                "explanation_present": bool(why)}
