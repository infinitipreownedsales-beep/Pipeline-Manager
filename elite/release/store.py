"""SQLite repositories for Phase 12 live-integration / migration / validation / release records (v12).

Immutable evidence tables are enforced by DB triggers; this store never mutates them. Append-preserving
lifecycle rows update in place but are never deleted. A release package is immutable once issued.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id


def _j(v):
    if v is None or isinstance(v, str):
        return v
    return json.dumps(v)


class ReleaseStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    def _ins(self, table, **c):
        keys = list(c)
        with self.conn:
            self.conn.execute(f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",
                              tuple(c[k] for k in keys))
        return c

    def _get(self, table, rid):
        return self.conn.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()

    def _upd(self, table, rid, **c):
        if "updated_at" not in c and self._has_col(table, "updated_at"):
            c["updated_at"] = self._now()
        sets = ",".join(f"{k}=?" for k in c)
        with self.conn:
            self.conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", tuple(c.values()) + (rid,))
        return self._get(table, rid)

    def _has_col(self, table, col):
        return any(r["name"] == col for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall())

    # ---- live-source inventory -----------------------------------------------
    def add_connection(self, **c):
        c.setdefault("id", new_id("lsc")); c.setdefault("recorded_at", self._now())
        c.setdefault("updated_at", c["recorded_at"])
        for k in ("identity_fields",):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("live_source_connection", **c)

    def get_connection(self, cid):
        return self._get("live_source_connection", cid)

    def list_connections(self):
        return self.conn.execute("SELECT * FROM live_source_connection ORDER BY recorded_at").fetchall()

    def add_schema_version(self, source_family, version, **c):
        existing = self.conn.execute(
            "SELECT * FROM live_source_schema_version WHERE source_family=? AND version=?",
            (source_family, version)).fetchone()
        if existing is not None:
            return existing
        c.update(id=new_id("lssv"), source_family=source_family, version=version)
        c.setdefault("registered_at", self._now())
        for k in ("schema_json", "mapping_json"):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("live_source_schema_version", **c)

    def schema_versions(self, source_family):
        return self.conn.execute(
            "SELECT * FROM live_source_schema_version WHERE source_family=? ORDER BY version",
            (source_family,)).fetchall()

    # ---- migration runs ------------------------------------------------------
    def add_migration_run(self, **c):
        c.setdefault("id", new_id("mig")); c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"]); c.setdefault("started_at", c["created_at"])
        for k in ("input_manifest", "counts_json"):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("migration_run", **c)

    def update_migration_run(self, rid, **c):
        for k in ("counts_json", "input_manifest"):
            if k in c:
                c[k] = _j(c[k])
        return self._upd("migration_run", rid, **c)

    def get_migration_run(self, rid):
        return self._get("migration_run", rid)

    def add_run_source(self, **c):
        c.setdefault("id", new_id("mrs")); c.setdefault("recorded_at", self._now())
        return self._ins("migration_run_source", **c)

    def run_sources(self, migration_run_id=None):
        if migration_run_id is None:
            return self.conn.execute("SELECT * FROM migration_run_source ORDER BY recorded_at").fetchall()
        return self.conn.execute("SELECT * FROM migration_run_source WHERE migration_run_id=?",
                                 (migration_run_id,)).fetchall()

    # ---- identity + fact reconciliation --------------------------------------
    def add_identity_recon(self, **c):
        c.setdefault("id", new_id("mir")); c.setdefault("recorded_at", self._now())
        if "evidence" in c:
            c["evidence"] = _j(c["evidence"])
        return self._ins("migration_identity_reconciliation", **c)

    def identity_recons(self, migration_run_id=None):
        if migration_run_id:
            return self.conn.execute(
                "SELECT * FROM migration_identity_reconciliation WHERE migration_run_id=? ORDER BY recorded_at",
                (migration_run_id,)).fetchall()
        return self.conn.execute(
            "SELECT * FROM migration_identity_reconciliation ORDER BY recorded_at").fetchall()

    def add_fact_recon(self, **c):
        c.setdefault("id", new_id("mfr")); c.setdefault("recorded_at", self._now())
        return self._ins("migration_fact_reconciliation", **c)

    def fact_recons(self, migration_run_id=None):
        if migration_run_id:
            return self.conn.execute(
                "SELECT * FROM migration_fact_reconciliation WHERE migration_run_id=? ORDER BY recorded_at",
                (migration_run_id,)).fetchall()
        return self.conn.execute("SELECT * FROM migration_fact_reconciliation ORDER BY recorded_at").fetchall()

    # ---- policy + authority migration ----------------------------------------
    def add_policy_resolution(self, **c):
        c.setdefault("id", new_id("mpr")); c.setdefault("recorded_at", self._now())
        c.setdefault("updated_at", c["recorded_at"])
        return self._ins("migration_policy_resolution", **c)

    def update_policy_resolution(self, rid, **c):
        return self._upd("migration_policy_resolution", rid, **c)

    def policy_resolutions(self, scope=None):
        if scope:
            return self.conn.execute(
                "SELECT * FROM migration_policy_resolution WHERE store_scope=? ORDER BY recorded_at",
                (scope,)).fetchall()
        return self.conn.execute("SELECT * FROM migration_policy_resolution ORDER BY recorded_at").fetchall()

    def add_authority_config(self, **c):
        c.setdefault("id", new_id("mac")); c.setdefault("recorded_at", self._now())
        c.setdefault("updated_at", c["recorded_at"])
        return self._ins("migration_authority_configuration", **c)

    def authority_configs(self, scope=None):
        if scope:
            return self.conn.execute(
                "SELECT * FROM migration_authority_configuration WHERE store_scope=? ORDER BY recorded_at",
                (scope,)).fetchall()
        return self.conn.execute("SELECT * FROM migration_authority_configuration ORDER BY recorded_at").fetchall()

    # ---- shadow mode (event log; latest = current) ---------------------------
    def add_shadow_mode(self, **c):
        c.setdefault("id", new_id("shm")); c.setdefault("recorded_at", self._now())
        return self._ins("domain_shadow_mode", **c)

    def current_shadow_mode(self, domain, scope):
        r = self.conn.execute(
            "SELECT * FROM domain_shadow_mode WHERE domain=? AND store_scope=? ORDER BY recorded_at DESC LIMIT 1",
            (domain, scope)).fetchone()
        return r

    def shadow_history(self, domain, scope):
        return self.conn.execute(
            "SELECT * FROM domain_shadow_mode WHERE domain=? AND store_scope=? ORDER BY recorded_at",
            (domain, scope)).fetchall()

    # ---- parallel validation -------------------------------------------------
    def add_parallel_run(self, **c):
        c.setdefault("id", new_id("pvr")); c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        return self._ins("parallel_validation_run", **c)

    def update_parallel_run(self, rid, **c):
        return self._upd("parallel_validation_run", rid, **c)

    def get_parallel_run(self, rid):
        return self._get("parallel_validation_run", rid)

    def list_parallel_runs(self):
        return self.conn.execute("SELECT * FROM parallel_validation_run ORDER BY created_at").fetchall()

    def add_parallel_result(self, **c):
        c.setdefault("id", new_id("pvres")); c.setdefault("recorded_at", self._now())
        for k in ("elite_value", "legacy_value", "difference"):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("parallel_validation_result", **c)

    def get_parallel_result(self, rid):
        return self._get("parallel_validation_result", rid)

    def review_parallel_result(self, rid, reviewer, disposition, notes=None):
        with self.conn:
            self.conn.execute(
                "UPDATE parallel_validation_result SET reviewer=?, disposition=?, notes=?, reviewed_at=? WHERE id=?",
                (reviewer, disposition, notes, self._now(), rid))
        return self._get("parallel_validation_result", rid)

    def parallel_results(self, parallel_run_id=None):
        if parallel_run_id:
            return self.conn.execute(
                "SELECT * FROM parallel_validation_result WHERE parallel_run_id=? ORDER BY recorded_at",
                (parallel_run_id,)).fetchall()
        return self.conn.execute("SELECT * FROM parallel_validation_result ORDER BY recorded_at").fetchall()

    # ---- discrepancy ---------------------------------------------------------
    def add_discrepancy(self, **c):
        c.setdefault("id", new_id("disc")); c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        return self._ins("discrepancy_record", **c)

    def get_discrepancy(self, rid):
        return self._get("discrepancy_record", rid)

    def update_discrepancy(self, rid, **c):
        return self._upd("discrepancy_record", rid, **c)

    def list_discrepancies(self, scope=None):
        if scope:
            return self.conn.execute("SELECT * FROM discrepancy_record WHERE store_scope=? ORDER BY created_at",
                                     (scope,)).fetchall()
        return self.conn.execute("SELECT * FROM discrepancy_record ORDER BY created_at").fetchall()

    def add_discrepancy_transition(self, **c):
        c.setdefault("id", new_id("dtr")); c.setdefault("recorded_at", self._now())
        return self._ins("discrepancy_transition", **c)

    def discrepancy_transitions(self, discrepancy_id):
        return self.conn.execute(
            "SELECT * FROM discrepancy_transition WHERE discrepancy_id=? ORDER BY recorded_at",
            (discrepancy_id,)).fetchall()

    # ---- UAT -----------------------------------------------------------------
    def add_uat_test(self, **c):
        c.setdefault("id", new_id("uat")); c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        return self._ins("operator_acceptance_test", **c)

    def get_uat_test(self, rid):
        return self._get("operator_acceptance_test", rid)

    def update_uat_test(self, rid, **c):
        return self._upd("operator_acceptance_test", rid, **c)

    def add_uat_result(self, **c):
        c.setdefault("id", new_id("uatr")); c.setdefault("recorded_at", self._now())
        return self._ins("operator_acceptance_result", **c)

    def uat_results(self, uat_test_id=None):
        if uat_test_id:
            return self.conn.execute(
                "SELECT * FROM operator_acceptance_result WHERE uat_test_id=? ORDER BY recorded_at",
                (uat_test_id,)).fetchall()
        return self.conn.execute("SELECT * FROM operator_acceptance_result ORDER BY recorded_at").fetchall()

    def list_uat_tests(self):
        return self.conn.execute("SELECT * FROM operator_acceptance_test ORDER BY created_at").fetchall()

    # ---- rehearsals ----------------------------------------------------------
    def add_migration_rehearsal(self, **c):
        c.setdefault("id", new_id("mreh")); c.setdefault("recorded_at", self._now())
        for k in ("steps_json", "input_hashes", "output_counts"):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("migration_rehearsal", **c)

    def add_rollback_rehearsal(self, **c):
        c.setdefault("id", new_id("rreh")); c.setdefault("recorded_at", self._now())
        if "inflight_actions" in c:
            c["inflight_actions"] = _j(c["inflight_actions"])
        return self._ins("rollback_rehearsal", **c)

    def add_recovery_rehearsal(self, **c):
        c.setdefault("id", new_id("vreh")); c.setdefault("recorded_at", self._now())
        return self._ins("recovery_rehearsal", **c)

    def migration_rehearsals(self):
        return self.conn.execute("SELECT * FROM migration_rehearsal ORDER BY recorded_at").fetchall()

    def rollback_rehearsals(self):
        return self.conn.execute("SELECT * FROM rollback_rehearsal ORDER BY recorded_at").fetchall()

    def recovery_rehearsals(self):
        return self.conn.execute("SELECT * FROM recovery_rehearsal ORDER BY recorded_at").fetchall()

    # ---- release package -----------------------------------------------------
    def add_release_package(self, **c):
        c.setdefault("id", new_id("rel")); c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        for k in ("adapter_versions", "policy_versions", "calc_versions", "authority_matrix",
                  "unresolved_risks", "checksum_manifest", "known_limitations"):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("release_package", **c)

    def get_release_package(self, rid):
        return self._get("release_package", rid)

    def update_release_package(self, rid, **c):
        return self._upd("release_package", rid, **c)

    def issue_release_package(self, rid):
        with self.conn:
            self.conn.execute("UPDATE release_package SET status='issued', issued_at=?, updated_at=? WHERE id=?",
                              (self._now(), self._now(), rid))
        return self.get_release_package(rid)

    def add_package_artifact(self, **c):
        c.setdefault("id", new_id("rpa")); c.setdefault("recorded_at", self._now())
        return self._ins("release_package_artifact", **c)

    def package_artifacts(self, release_package_id):
        return self.conn.execute("SELECT * FROM release_package_artifact WHERE release_package_id=?",
                                 (release_package_id,)).fetchall()

    # ---- final certification + authorization ---------------------------------
    def add_certification(self, **c):
        c.setdefault("id", new_id("frc")); c.setdefault("created_at", self._now())
        if "evidence" in c:
            c["evidence"] = _j(c["evidence"])
        return self._ins("final_readiness_certification", **c)

    def get_certification(self, rid):
        return self._get("final_readiness_certification", rid)

    def supersede_certification(self, rid, by):
        return self._upd("final_readiness_certification", rid, superseded_by=by)

    def add_dimension(self, **c):
        c.setdefault("id", new_id("frd")); c.setdefault("recorded_at", self._now())
        return self._ins("final_readiness_dimension", **c)

    def dimensions(self, certification_id):
        return self.conn.execute("SELECT * FROM final_readiness_dimension WHERE certification_id=?",
                                 (certification_id,)).fetchall()

    def list_certifications(self):
        return self.conn.execute("SELECT * FROM final_readiness_certification ORDER BY created_at").fetchall()

    def add_authorization(self, **c):
        c.setdefault("id", new_id("auth")); c.setdefault("created_at", self._now())
        for k in ("enabled_domains", "warnings_ack", "risks_ack"):
            if k in c:
                c[k] = _j(c[k])
        return self._ins("release_authorization_decision", **c)

    def get_authorization(self, rid):
        return self._get("release_authorization_decision", rid)

    def supersede_authorization(self, rid, by):
        with self.conn:
            self.conn.execute("UPDATE release_authorization_decision SET superseded_by=? WHERE id=?", (by, rid))
        return self.get_authorization(rid)

    def list_authorizations(self):
        return self.conn.execute("SELECT * FROM release_authorization_decision ORDER BY created_at").fetchall()

    # ---- cutover runbook -----------------------------------------------------
    def add_cutover_runbook(self, **c):
        c.setdefault("id", new_id("cutrb")); c.setdefault("recorded_at", self._now())
        return self._ins("cutover_runbook_reference", **c)

    def cutover_runbooks(self):
        return self.conn.execute("SELECT * FROM cutover_runbook_reference ORDER BY recorded_at").fetchall()
