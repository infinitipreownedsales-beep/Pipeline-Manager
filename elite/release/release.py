"""Release package, final readiness certification, release-authorization gate, and cutover runbook.

The final certification distinguishes engineering / data / policy / authority / operator / migration /
rollback / security readiness from OPERATIONALLY_READY and from GO_LIVE_AUTHORIZED. GO_LIVE_AUTHORIZED can
never be set by automated certification — only an explicit governed Decision by an authorized Principal can
authorize a release, and authorization does not itself perform cutover. A release package is immutable once
issued. No production-primary transition occurs without an explicit, unexpired authorization.
"""
from __future__ import annotations

from ..errors import AuthorizationError, ValidationError
import datetime as _dt
from .models import (CAPS, DIMENSIONS, DIMENSION_STATUSES, DIMENSION_OK, OPERATIONAL_PREREQS,
                     AUTH_DISPOSITIONS, RELEASE_RECOMMENDATIONS)


def _parse(ts):
    try:
        return _dt.datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


class ReleasePackageService:
    def __init__(self, release_store, governor, clock, logger=None):
        self.store, self.gov, self.clock, self.logger = release_store, governor, clock, logger

    def build(self, *, version_label, application_revision, migration_level, **kw):
        return self.store.add_release_package(version_label=version_label,
                                              application_revision=application_revision,
                                              migration_level=migration_level, status="draft", **kw)

    def add_artifact(self, release_package_id, *, name, kind, ref, checksum=None):
        return self.store.add_package_artifact(release_package_id=release_package_id, name=name, kind=kind,
                                               ref=ref, checksum=checksum)

    def issue(self, *, principal, scope, release_package_id, correlation_id=None):
        pkg = self.store.get_release_package(release_package_id)
        if pkg is None:
            raise ValidationError(technical_detail="unknown release package")
        if pkg["status"] == "issued":
            return pkg                                   # idempotent: already immutable

        def business(conn):
            conn.execute("UPDATE release_package SET status='issued', issued_at=?, updated_at=? WHERE id=?",
                         (self.store._now(), self.store._now(), release_package_id))
            return (release_package_id, release_package_id), release_package_id
        self.gov.perform(principal_id=principal, capability=CAPS["PACKAGE_ISSUE"], scope=scope,
                         action="release.package.issue", business_fn=business, target_ref=release_package_id,
                         correlation_id=correlation_id)
        return self.store.get_release_package(release_package_id)


class FinalReadinessService:
    def __init__(self, release_store, governor, clock, logger=None):
        self.store, self.gov, self.clock, self.logger = release_store, governor, clock, logger

    def certify(self, *, principal, scope, release_package_ref, dimensions, correlation_id=None):
        """`dimensions`: {dimension: {"status":..., "evidence":..., "note":...}}. OPERATIONALLY_READY is
        DERIVED from the prerequisite dimensions; GO_LIVE_AUTHORIZED can NEVER be PASS here (authorization
        is a separate governed Decision)."""
        dims = {d: dict(dimensions.get(d, {"status": "UNRESOLVED"})) for d in DIMENSIONS}
        for d, v in dims.items():
            if v.get("status") not in DIMENSION_STATUSES:
                raise ValidationError(technical_detail=f"invalid status for {d}: {v.get('status')}")
        # derive OPERATIONALLY_READY from prerequisites (unless every prereq ok, it cannot pass)
        prereqs_ok = all(dims[p]["status"] in DIMENSION_OK for p in OPERATIONAL_PREREQS)
        warnings = any(dims[p]["status"] == "PASS_WITH_WARNINGS" for p in OPERATIONAL_PREREQS)
        dims["OPERATIONALLY_READY"] = {
            "status": ("PASS_WITH_WARNINGS" if prereqs_ok and warnings else "PASS" if prereqs_ok else "FAIL"),
            "evidence": "derived from prerequisite dimensions",
            "note": None if prereqs_ok else "one or more prerequisite dimensions are not satisfied"}
        # GO_LIVE_AUTHORIZED reflects the separate authorization state — never set PASS by certification
        auth = self._current_authorization(scope, release_package_ref)
        dims["GO_LIVE_AUTHORIZED"] = {
            "status": "PASS" if auth else "NOT_APPLICABLE",
            "evidence": ("authorization " + auth["id"]) if auth else "no explicit release authorization",
            "note": "set only by an explicit governed release Decision, never by certification"}
        overall = self._overall(dims)

        def business(conn):
            from ..ids import new_id
            cid = new_id("frc")
            import json
            conn.execute("INSERT INTO final_readiness_certification(id,release_package_ref,store_scope,overall,"
                         "certified_by,evidence,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (cid, release_package_ref, scope, overall, principal, json.dumps({}),
                          correlation_id, self.store._now()))
            for d in DIMENSIONS:
                conn.execute("INSERT INTO final_readiness_dimension(id,certification_id,dimension,status,"
                             "evidence,note,recorded_at) VALUES(?,?,?,?,?,?,?)",
                             (new_id("frd"), cid, d, dims[d]["status"], dims[d].get("evidence"),
                              dims[d].get("note"), self.store._now()))
            return (cid, cid), cid
        res = self.gov.perform(principal_id=principal, capability=CAPS["CERTIFY"], scope=scope,
                               action="release.certify", business_fn=business,
                               target_ref=release_package_ref, correlation_id=correlation_id)
        # supersede any prior certification for this package + scope
        for c in self.store.list_certifications():
            if (c["release_package_ref"] == release_package_ref and c["store_scope"] == scope
                    and c["id"] != res["result_ref"] and not c["superseded_by"]):
                self.store.supersede_certification(c["id"], res["result_ref"])
        return self.store.get_certification(res["result_ref"])

    def _overall(self, dims):
        prereqs = [dims[d]["status"] for d in OPERATIONAL_PREREQS]
        if any(s == "FAIL" for s in prereqs):
            return "NOT_READY"
        if any(s == "UNRESOLVED" for s in prereqs):
            return "UNRESOLVED"
        if dims["OPERATIONALLY_READY"]["status"] == "PASS_WITH_WARNINGS":
            return "OPERATIONALLY_READY_WITH_WARNINGS"
        return "OPERATIONALLY_READY"

    def _current_authorization(self, scope, release_package_ref):
        for a in reversed(self.store.list_authorizations()):
            if (a["store_scope"] == scope and a["release_package_ref"] == release_package_ref
                    and not a["superseded_by"] and a["disposition"] in
                    ("AUTHORIZE_GO_LIVE", "AUTHORIZE_LIMITED_DOMAIN_GO_LIVE")):
                exp = _parse(a["expires_at"])
                if exp is None or exp > self.clock.now():
                    return a
        return None

    def dimensions_of(self, certification_id):
        return {d["dimension"]: d for d in self.store.dimensions(certification_id)}

    def final_recommendation(self, scope, release_package_ref):
        certs = [c for c in self.store.list_certifications()
                 if c["store_scope"] == scope and c["release_package_ref"] == release_package_ref
                 and not c["superseded_by"]]
        if not certs:
            return "NOT_READY"
        cert = certs[-1]
        dims = self.dimensions_of(cert["id"])
        op = dims.get("OPERATIONALLY_READY", {}).get("status") if isinstance(dims.get("OPERATIONALLY_READY"), dict) else None
        op = dims["OPERATIONALLY_READY"]["status"] if "OPERATIONALLY_READY" in dims else None
        if op in ("PASS", "PASS_WITH_WARNINGS"):
            return "READY_FOR_EXPLICIT_GO_LIVE_AUTHORIZATION"
        # any single domain independently ready but others blocked -> limited
        if any(dims[p]["status"] in DIMENSION_OK for p in OPERATIONAL_PREREQS) and \
           any(dims[p]["status"] in ("FAIL", "UNRESOLVED") for p in OPERATIONAL_PREREQS):
            return "CONTINUE_PARALLEL_PILOT"
        return "NOT_READY"


class ReleaseAuthorizationService:
    def __init__(self, release_store, governor, clock, logger=None):
        self.store, self.gov, self.clock, self.logger = release_store, governor, clock, logger

    def authorize(self, *, principal, scope, release_package_ref, certification_ref, disposition,
                  enabled_domains=None, warnings_ack=None, risks_ack=None, rollback_plan_ref=None,
                  expires_at=None, sod_second=None, correlation_id=None):
        """The explicit governed release Decision. Never automated; requires an authorized Principal. Does
        NOT itself perform cutover. AUTHORIZE_GO_LIVE requires the referenced certification to be
        operationally ready per policy; a limited-domain authorization must name its exact domains."""
        if disposition not in AUTH_DISPOSITIONS:
            raise ValidationError(technical_detail=f"unknown disposition {disposition}")
        pkg = self.store.get_release_package(release_package_ref)
        if pkg is None or pkg["status"] != "issued":
            raise ValidationError(message="Authorization requires an issued release package.",
                                  technical_detail="release package not issued")
        cert = self.store.get_certification(certification_ref)
        if cert is None:
            raise ValidationError(technical_detail="unknown certification")
        if disposition in ("AUTHORIZE_GO_LIVE", "AUTHORIZE_LIMITED_DOMAIN_GO_LIVE"):
            dims = {d["dimension"]: d["status"] for d in self.store.dimensions(cert["id"])}
            if disposition == "AUTHORIZE_GO_LIVE" and dims.get("OPERATIONALLY_READY") not in DIMENSION_OK:
                raise ValidationError(message="Go-live authorization requires operational readiness.",
                                      technical_detail="OPERATIONALLY_READY not satisfied")
            if disposition == "AUTHORIZE_LIMITED_DOMAIN_GO_LIVE" and not enabled_domains:
                raise ValidationError(message="A limited-domain authorization must name its domains.",
                                      technical_detail="enabled_domains required")

        def business(conn):
            from ..ids import new_id
            import json
            aid = new_id("auth")
            conn.execute(
                "INSERT INTO release_authorization_decision(id,release_package_ref,certification_ref,disposition,"
                "store_scope,enabled_domains,warnings_ack,risks_ack,rollback_plan_ref,authorized_by,sod_second,"
                "expires_at,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, release_package_ref, certification_ref, disposition, scope,
                 json.dumps(enabled_domains or []), json.dumps(warnings_ack or []), json.dumps(risks_ack or []),
                 rollback_plan_ref, principal, sod_second, expires_at, correlation_id, self.store._now()))
            return (aid, aid), aid
        res = self.gov.perform(principal_id=principal, capability=CAPS["AUTHORIZE_RELEASE"], scope=scope,
                               action="release.authorize", business_fn=business, target_ref=release_package_ref,
                               correlation_id=correlation_id)
        # a new authorization supersedes a prior active one for the same package + scope
        for a in self.store.list_authorizations():
            if (a["release_package_ref"] == release_package_ref and a["store_scope"] == scope
                    and a["id"] != res["result_ref"] and not a["superseded_by"]):
                self.store.supersede_authorization(a["id"], res["result_ref"])
        return self.store.get_authorization(res["result_ref"])

    def active_authorization(self, scope, release_package_ref):
        for a in reversed(self.store.list_authorizations()):
            if (a["store_scope"] == scope and a["release_package_ref"] == release_package_ref
                    and not a["superseded_by"]
                    and a["disposition"] in ("AUTHORIZE_GO_LIVE", "AUTHORIZE_LIMITED_DOMAIN_GO_LIVE")):
                exp = _parse(a["expires_at"])
                if exp is not None and exp <= self.clock.now():
                    return None                              # expired cannot be used
                return a
        return None

    def is_go_live_authorized(self, scope, release_package_ref):
        return self.active_authorization(scope, release_package_ref) is not None


class CutoverRunbookService:
    def __init__(self, release_store, clock):
        self.store, self.clock = release_store, clock

    def record(self, *, release_package_ref, runbook_ref, version, prerequisites, abort_criteria,
               rollback_trigger, rollback_steps):
        return self.store.add_cutover_runbook(
            release_package_ref=release_package_ref, runbook_ref=runbook_ref, version=version,
            prerequisites=prerequisites, abort_criteria=abort_criteria, rollback_trigger=rollback_trigger,
            rollback_steps=rollback_steps)


def build_release_services(release_store, governor, clock, logger=None):
    """Construct the rehearsal, package, readiness, authorization, and cutover services together."""
    from .rehearsal import RehearsalService
    return (RehearsalService(release_store, clock, logger=logger),
            ReleasePackageService(release_store, governor, clock, logger=logger),
            FinalReadinessService(release_store, governor, clock, logger=logger),
            ReleaseAuthorizationService(release_store, governor, clock, logger=logger),
            CutoverRunbookService(release_store, clock))
