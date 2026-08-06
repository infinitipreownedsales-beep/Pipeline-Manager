"""Operator acceptance testing against the real pilot application.

UAT is conducted by operators on the real application (not developer tests). A result is immutable evidence;
a failure remains historical; a retest is a NEW result linked to the original (which is never erased); a
material failure blocks affected-domain readiness. Missing operator sign-off stays missing.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from .models import CAPS, UAT_OUTCOMES


class OperatorAcceptanceService:
    def __init__(self, release_store, stack, clock, logger=None):
        self.store, self.stack, self.clock, self.logger = release_store, stack, clock, logger

    def add_test(self, *, test_case, domain, scope, expected_result, environment_revision="pilot",
                 source_revision="real", operator=None):
        return self.store.add_uat_test(test_case=test_case, domain=domain, store_scope=scope,
                                       expected_result=expected_result, environment_revision=environment_revision,
                                       source_revision=source_revision, operator=operator, status="pending")

    def record(self, *, principal, scope, uat_test_id, actual_result, outcome, evidence=None, issue_ref=None,
               disposition=None, retest_of=None, correlation_id=None):
        if outcome not in UAT_OUTCOMES:
            raise ValidationError(technical_detail=f"unknown UAT outcome {outcome}")
        test = self.store.get_uat_test(uat_test_id)
        if test is None:
            raise ValidationError(technical_detail="unknown UAT test")

        def business(conn):
            rid = new_id("uatr")
            conn.execute(
                "INSERT INTO operator_acceptance_result(id,uat_test_id,operator,actual_result,outcome,evidence,"
                "issue_ref,disposition,retest_of,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rid, uat_test_id, principal, actual_result, outcome, evidence, issue_ref, disposition,
                 retest_of, self.store._now()))
            conn.execute("UPDATE operator_acceptance_test SET status=?, operator=?, updated_at=? WHERE id=?",
                         (outcome, principal, self.store._now(), uat_test_id))
            return (rid, rid), rid
        res = self.stack.governor.perform(principal_id=principal, capability=CAPS["UAT_RECORD"], scope=scope,
                                          action="release.uat.record", business_fn=business,
                                          target_ref=uat_test_id, correlation_id=correlation_id)
        return self.store.conn.execute("SELECT * FROM operator_acceptance_result WHERE id=?",
                                       (res["result_ref"],)).fetchone()

    def material_failures(self, scope=None):
        """Tests whose current state is fail/block with no later passing retest."""
        out = []
        for t in self.store.list_uat_tests():
            if scope and t["store_scope"] != scope:
                continue
            results = self.store.uat_results(t["id"])
            if not results:
                continue
            latest = results[-1]
            if latest["outcome"] in ("fail", "block"):
                out.append(t)
        return out

    def has_signoff(self, scope, required_domains):
        """True only if every required domain has at least one PASS result recorded by an operator."""
        passed = set()
        for t in self.store.list_uat_tests():
            if scope and t["store_scope"] != scope:
                continue
            if any(r["outcome"] == "pass" for r in self.store.uat_results(t["id"])):
                passed.add(t["domain"])
        return all(d in passed for d in required_domains)
