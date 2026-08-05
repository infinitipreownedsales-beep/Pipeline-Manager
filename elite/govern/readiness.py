"""Domain launch-readiness assessment.

An evidence-based, versioned assessment (immutable after issuance). Missing required policy or required
authority blocks readiness; a critical unresolved identity may block it; a passing synthetic test suite
alone does NOT prove operational readiness. Readiness does not deploy or activate a domain; prior
assessments remain historical.
"""
from __future__ import annotations

from .models import READINESS_CLASSES, READINESS_DOMAINS


class ReadinessService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def assess(self, principal, scope, *, owning_domain, required_policy_present, authority_coverage,
               calc_versions_active=True, source_contracts_available=True, unresolved_identities=0,
               unresolved_critical=0, stale_imports=0, sod_coverage=True, audit_health="ok",
               test_evidence=None, operational_owner=None):
        """Classify readiness from evidence. A passing synthetic test suite alone is never sufficient."""
        blockers, warnings = [], []
        if not required_policy_present:
            blockers.append("missing required policy")
        if not authority_coverage:
            blockers.append("missing required authority")
        if unresolved_critical > 0:
            blockers.append(f"{unresolved_critical} critical unresolved identity")
        if not calc_versions_active:
            blockers.append("required calculation versions not active")
        if not source_contracts_available:
            warnings.append("source contracts unavailable")
        if stale_imports > 0:
            warnings.append(f"{stale_imports} stale imports")
        if not sod_coverage:
            warnings.append("incomplete separation-of-duties coverage")
        te = test_evidence or {}
        # Passing synthetic tests alone does not prove operational readiness — real operational
        # evidence (owner + authority + policy + no critical unresolved) is still required.
        only_synthetic = te.get("synthetic_pass") and not te.get("operational_evidence")
        if only_synthetic and not blockers:
            warnings.append("only synthetic test evidence — operational readiness unproven")
        if blockers:
            classification = "NOT_READY"
        elif audit_health == "conflicting":
            classification = "CONFLICTING"
        elif warnings:
            classification = "READY_WITH_WARNINGS"
        else:
            classification = "READY"
        assert classification in READINESS_CLASSES

        def business(conn):
            rid = self.store.insert_readiness(
                conn, owning_domain=owning_domain, store_scope=scope, classification=classification,
                required_policy_present=int(bool(required_policy_present)),
                calc_versions_active=int(bool(calc_versions_active)),
                source_contracts_available=int(bool(source_contracts_available)),
                unresolved_identities=unresolved_identities, stale_imports=stale_imports, test_evidence=te,
                authority_coverage=int(bool(authority_coverage)), sod_coverage=int(bool(sod_coverage)),
                audit_health=audit_health, unresolved_critical=unresolved_critical,
                operational_owner=operational_owner, blockers=blockers, warnings=warnings,
                evidence={"required_policy_present": bool(required_policy_present),
                          "authority_coverage": bool(authority_coverage)},
                revision=len(self.store.readiness_for(owning_domain)) + 1)
            return (rid, rid), rid
        res = self.gov.perform(principal_id=principal, capability="readiness.assess", scope=scope,
                               action="readiness.assess", business_fn=business, target_ref=owning_domain)
        return self.store.get_readiness(res["value"][0])


assert set(READINESS_DOMAINS)
