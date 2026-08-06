"""Sustained dual-system parallel run + governed discrepancy burn-down.

Parallel validation captures dated Elite-vs-legacy comparisons, preserves BOTH outputs, classifies each
difference, and mutates neither tool. Discrepancy burn-down is governed: each transition is evidence-based
and audited, a confirmed Elite defect enters the defect registry, and a material unresolved discrepancy
blocks affected-domain readiness. The required duration + sample coverage are an approved release criterion
(not a hardcoded number).
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from .models import (CAPS, PARALLEL_CLASSES, PARALLEL_MATERIAL, DISCREPANCY_STATUSES,
                     DISCREPANCY_BLOCKING)


class ParallelValidationService:
    def __init__(self, release_store, stack, clock, logger=None):
        self.store, self.stack, self.clock, self.logger = release_store, stack, clock, logger

    def run(self, *, principal, scope, subjects, run_date, elite_revision="elite", legacy_revision="legacy",
            correlation_id=None):
        self.stack.authz.require(principal, CAPS["PARALLEL_RUN"], scope, correlation_id=correlation_id)
        run = self.store.add_parallel_run(run_date=run_date, store_scope=scope, elite_revision=elite_revision,
                                          legacy_revision=legacy_revision, initiated_by=principal,
                                          correlation_id=correlation_id)
        match = diff = unresolved = material = 0
        results = []
        for s in subjects:
            elite, legacy = s.get("elite_value"), s.get("legacy_value")
            cls = s.get("classification") or ("MATCH" if elite == legacy else "UNRESOLVED")
            if cls not in PARALLEL_CLASSES:
                raise ValidationError(technical_detail=f"unknown classification {cls}")
            mat = "material" if cls in PARALLEL_MATERIAL else "immaterial"
            if cls == "MATCH":
                match += 1
            else:
                diff += 1
                if cls == "UNRESOLVED":
                    unresolved += 1
                if cls in PARALLEL_MATERIAL:
                    material += 1
            res = self.store.add_parallel_result(
                parallel_run_id=run["id"], domain=s.get("domain"), subject_ref=s.get("subject_ref"),
                elite_value=elite, legacy_value=legacy,
                difference=(None if cls == "MATCH" else {"elite": elite, "legacy": legacy}),
                classification=cls, materiality=mat,
                readiness_impact=("blocks" if cls in PARALLEL_MATERIAL else "none"))
            results.append(self.store.get_parallel_result(res["id"]))
        self.store.update_parallel_run(run["id"], subject_count=len(subjects), match_count=match,
                                       difference_count=diff, unresolved_count=unresolved,
                                       material_count=material)
        return {"run": self.store.get_parallel_run(run["id"]), "results": results}

    def review_result(self, *, principal, scope, result_id, disposition, notes=None, correlation_id=None):
        res = self.store.get_parallel_result(result_id)
        if res is None:
            raise ValidationError(technical_detail=f"unknown parallel result {result_id}")

        def business(conn):
            conn.execute(
                "UPDATE parallel_validation_result SET reviewer=?, disposition=?, notes=?, reviewed_at=? WHERE id=?",
                (principal, disposition, notes, self.store._now(), result_id))
            return (result_id, result_id), result_id
        self.stack.governor.perform(principal_id=principal, capability=CAPS["DISCREPANCY_REVIEW"], scope=scope,
                                    action="release.parallel.review", business_fn=business, target_ref=result_id,
                                    correlation_id=correlation_id)
        return self.store.get_parallel_result(result_id)

    def unreviewed_material(self, scope=None):
        rows = self.store.conn.execute(
            "SELECT r.* FROM parallel_validation_result r JOIN parallel_validation_run run"
            " ON r.parallel_run_id=run.id WHERE (r.disposition IS NULL OR r.disposition='')"
            + (" AND run.store_scope=?" if scope else ""), (scope,) if scope else ()).fetchall()
        return [r for r in rows if r["classification"] in PARALLEL_MATERIAL]


class DiscrepancyService:
    def __init__(self, release_store, governor, clock, logger=None):
        self.store, self.gov, self.clock, self.logger = release_store, governor, clock, logger

    def open(self, *, parallel_result_ref, domain, scope, summary, classification=None, materiality="material"):
        rec = self.store.add_discrepancy(parallel_result_ref=parallel_result_ref, domain=domain,
                                         store_scope=scope, summary=summary, status="OPEN",
                                         classification=classification, materiality=materiality)
        self.store.add_discrepancy_transition(discrepancy_id=rec["id"], from_status=None, to_status="OPEN",
                                              actor="system", reason="opened from parallel difference")
        return self.store.get_discrepancy(rec["id"])

    def transition(self, *, principal, scope, discrepancy_id, to_status, reason, evidence=None,
                   defect_ref=None, correlation_id=None):
        if to_status not in DISCREPANCY_STATUSES:
            raise ValidationError(technical_detail=f"unknown discrepancy status {to_status}")
        rec = self.store.get_discrepancy(discrepancy_id)
        if rec is None:
            raise ValidationError(technical_detail="unknown discrepancy")
        if not (reason and (evidence or to_status in ("TRIAGED",))):
            raise ValidationError(message="A discrepancy transition requires a reason and evidence.",
                                  technical_detail="classification requires evidence")

        def business(conn):
            tid = new_id("dtr")
            conn.execute(
                "INSERT INTO discrepancy_transition(id,discrepancy_id,from_status,to_status,actor,reason,"
                "evidence,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                (tid, discrepancy_id, rec["status"], to_status, principal, reason, evidence, self.store._now()))
            conn.execute("UPDATE discrepancy_record SET status=?, defect_ref=COALESCE(?,defect_ref), updated_at=? "
                         "WHERE id=?", (to_status, defect_ref, self.store._now(), discrepancy_id))
            return (discrepancy_id, discrepancy_id), discrepancy_id
        self.gov.perform(principal_id=principal, capability=CAPS["DISCREPANCY_REVIEW"], scope=scope,
                         action="release.discrepancy.transition", business_fn=business,
                         target_ref=discrepancy_id, correlation_id=correlation_id)
        return self.store.get_discrepancy(discrepancy_id)

    def burn_down(self, scope=None):
        rows = self.store.list_discrepancies(scope)
        by_status = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        return {"total": len(rows), "by_status": by_status,
                "blocking": [r["id"] for r in rows if r["status"] in DISCREPANCY_BLOCKING]}

    def blocking(self, scope=None):
        return [r for r in self.store.list_discrepancies(scope) if r["status"] in DISCREPANCY_BLOCKING]
