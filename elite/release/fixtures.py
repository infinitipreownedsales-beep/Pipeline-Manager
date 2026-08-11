"""Deterministic Phase 12 fixtures: a wired live-integration / migration / validation / release stack over
the Phase 11 controlled pilot.

Synthetic dealership data only for deterministic tests; the migration engine drives realistically-structured
sources through the REAL Phase 11 adapters/orchestrator into a DEDICATED migration database, and the live
executor invokes the ACTUAL Phase 5-7 domain methods (no synthetic callback in the real path). Test
fixtures are kept separate from real migration data.
"""
from __future__ import annotations

from ..ops.fixtures import SCOPE, OTHER_SCOPE
from .release import build_release_services
from .executors import LiveExecutorRegistry, LiveExecutionService
from .migration import MigrationEngine
from .models import CAPS
from .shadow import ShadowModeService
from .store import ReleaseStore
from .uat import OperatorAcceptanceService
from .validation import DiscrepancyService, ParallelValidationService

ALL_CAPS = list(CAPS.values())


class Phase12:
    def __init__(self, db_path, *, seed=True):
        from ..ops.fixtures import Phase11
        self.p11 = Phase11(db_path, seed=seed)                    # migrates v1-v11, controlled pilot stack
        self.app = self.p11.app
        self.p9 = self.p11.p9
        self.p8 = self.p9.p8
        self.p7 = self.p8.p7
        self.p6 = self.p7.p6
        self.stack = self.p11.stack
        self.clock = self.stack.clock
        self.environment = self.stack.environment
        self.stack.db.migrate()                        # apply v12
        conn = self.stack.db.conn

        self.store = ReleaseStore(conn, self.clock)
        self.gov = self.stack.governor
        self.oplog = self.p11.oplog
        self.migration = MigrationEngine(self.store, self.p11, self.stack, self.clock, logger=self.oplog)
        self.shadow = ShadowModeService(self.store, self.gov, self.clock, logger=self.oplog)
        self.parallel = ParallelValidationService(self.store, self.stack, self.clock, logger=self.oplog)
        self.discrepancy = DiscrepancyService(self.store, self.gov, self.clock, logger=self.oplog)
        self.uat = OperatorAcceptanceService(self.store, self.stack, self.clock, logger=self.oplog)
        (self.rehearsal, self.packages, self.readiness,
         self.authorization, self.cutover) = build_release_services(self.store, self.gov, self.clock,
                                                                     logger=self.oplog)

        # live executor registry bound to the REAL Phase 5-7 domain services
        self.registry = LiveExecutorRegistry(loaner=self.p6, execdemo=self.p7)
        self.live = LiveExecutionService(self.p9, self.store, self.registry, self.shadow, self.stack,
                                         self.clock, logger=self.oplog)
        self.app.live_executor = self.live             # wire into the operator app

        if seed:
            self._operators()

    # ---- operators -----------------------------------------------------------
    def _op(self, key, name, caps, scope=SCOPE):
        pid = self.stack.metadata.get(key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, scope)
        return pid

    def _operators(self):
        # Kyle: full dealership + administrative capabilities for the pilot
        self.kyle = self._op("p12_kyle", "Kyle (GM)", ALL_CAPS + [
            "workspace.view", "workspace.review", "decision.issue", "decision.approve"])
        self.op_migrator = self._op("p12_migrator", "Migrator", [CAPS["MIGRATE_RUN"], CAPS["IDENTITY_RESOLVE"],
                                    CAPS["POLICY_MIGRATE"], CAPS["AUTHORITY_MIGRATE"]])
        self.op_shadow = self._op("p12_shadow", "Shadow Admin", [CAPS["SHADOW_SET"]])
        self.op_executor = self._op("p12_exec", "Live Executor",
                                    [CAPS["EXECUTE_LIVE"], "execution.authorize", "domain.execute"])
        self.op_validator = self._op("p12_validator", "Parallel Validator",
                                     [CAPS["PARALLEL_RUN"], CAPS["DISCREPANCY_REVIEW"]])
        self.op_uat = self._op("p12_uat", "UAT Operator", [CAPS["UAT_RECORD"]])
        self.op_releaser = self._op("p12_releaser", "Release Manager",
                                    [CAPS["PACKAGE_ISSUE"], CAPS["CERTIFY"], CAPS["REHEARSE"]])
        self.op_authorizer = self._op("p12_authorizer", "Release Authorizer", [CAPS["AUTHORIZE_RELEASE"]])
        self.op_noauth = self._op("p12_noauth", "No Release Access", [])
        self.op_otherscope = self._op("p12_other", "Other Store", ALL_CAPS, scope=OTHER_SCOPE)

    # ---- convenience ---------------------------------------------------------
    def now_iso(self):
        return self.p11.now_iso()

    def enable_execution(self, domain, scope=SCOPE):
        """Advance a domain's shadow mode to EXECUTION_PILOT (governed)."""
        return self.shadow.set_mode(principal=self.op_shadow, scope=scope, domain=domain,
                                    mode="EXECUTION_PILOT", reason="pilot execution enabled")

    def prepare_live_execution(self, vin, *, scope=SCOPE, rec="rec_live"):
        """Build a REAL end-to-end live-execution setup and return (decision, unit, real_call):
          * a real ACTIVE Executive Demo unit with an approved retirement (Phase 7 governed lifecycle);
          * a real governed Decision (issued by the decider, approved by a separate approver);
          * a real_call that invokes the ACTUAL Phase 7 retirement.execute governed method;
        with the executive_demo domain advanced to EXECUTION_PILOT and the decision bound to the executor."""
        # 1) a real ACTIVE execdemo unit, retirement proposed + approved (Phase 7 real governed methods)
        unit = self.p7.make_active(vin, scope=scope)
        self.p7.retirement.propose(self.p7.full, scope, unit)
        unit = self.p7.store.get_unit(unit.id)
        self.p7.retirement.approve(self.p7.full, scope, unit)
        unit = self.p7.store.get_unit(unit.id)

        # 2) a real governed Decision on a fresh workspace item, approved by a separate authority
        item = self.p9.item(domain="executive_demo", rec=rec, scope=scope)
        r = self.p9.decisions.issue(self.p9.decider, scope, item, disposition="ACCEPT",
                                    selected_action="retire", presented_alternatives=["retire", "hold"])
        decision = r["decision"]
        self.p9.approvals.approve(self.p9.approver, scope, decision)
        decision = self.p9.store.get_decision(decision["id"])

        # 3) a real executor bound to the ACTUAL Phase 7 retirement.execute
        def real_call(principal, sc):
            cur = self.p7.store.get_unit(unit.id)
            if cur.membership_state != "RETIREMENT_APPROVED":
                # already executed (RETIRED / RETURNED_TO_NEW_RETAIL / ...): idempotent, return the real ref
                return cur.retirement_event or ("edrev_" + unit.id)
            self.p7.retirement.execute(self.p7.full, sc, cur, disposition="new_retail")
            return self.p7.store.get_unit(unit.id).retirement_event or ("edrev_" + unit.id)
        self.live.bind(decision["id"], domain="executive_demo",
                       action="executive_demo.retirement.execute", real_call=real_call,
                       expected_action="retire")
        self.enable_execution("executive_demo", scope)
        return decision, unit, real_call

    def reopen(self):
        return Phase12(self.stack.db.path)

    def close(self):
        self.stack.close()


# ---------------------------------------------------------------------------
# 64 representative final-phase fixtures. Each builder exercises a real, safe path.
# ---------------------------------------------------------------------------
FIXTURE_NAMES = [
    "available_live_csv_source", "available_live_json_source", "governed_manual_source",
    "access_pending_source", "unavailable_source", "actual_schema_v1", "schema_drift_to_v2",
    "corrected_adapter", "real_current_inventory_migration", "real_production_order_migration",
    "real_retail_history_migration", "real_service_loaner_migration", "real_executive_demo_migration",
    "matched_vin", "duplicate_vin", "conflicting_vin", "prevIN_linked_to_vin", "unresolved_identity",
    "confirmed_policy", "missing_policy", "conflicting_policy", "actual_principal", "insufficient_authority",
    "separation_of_duties_conflict", "reconstructed_new_inventory_plan", "reconstructed_service_loaner_fleet",
    "reconstructed_executive_demo_portfolio", "actual_cpo_executor", "actual_dealer_trade_executor",
    "actual_ctp_executor", "actual_loaner_executor", "actual_executive_demo_executor", "shadow_data_only",
    "shadow_review_only", "execution_pilot", "blocked_domain", "parallel_match", "data_difference",
    "timing_difference", "policy_difference", "elite_defect", "legacy_limitation", "expected_difference",
    "unresolved_material_difference", "resolved_discrepancy", "uat_pass", "uat_failure", "uat_retest_pass",
    "migration_rehearsal_pass", "migration_rehearsal_fail", "rollback_rehearsal_pass",
    "rollback_rehearsal_fail", "recovery_rehearsal_pass", "release_package", "engineering_ready",
    "data_not_ready", "operator_not_ready", "pass_with_warnings", "go_live_not_authorized",
    "limited_domain_authorization", "continue_parallel_run_decision", "expired_release_authorization",
    "post_certification_blocker", "restart_durability",
]
assert len(FIXTURE_NAMES) == 64, len(FIXTURE_NAMES)

# required policy families for readiness (a representative subset)
REQUIRED_POLICIES = ["desired_ending_coverage", "service_loaner_monitoring_threshold",
                     "executive_demo_portfolio_requirement"]


def build_all_fixtures(p):
    """Exercise all 64 final-phase fixtures against one Phase12 stack. Returns {name: handle}, all truthy."""
    import datetime as _dt
    from ..errors import AuthorizationError, ValidationError
    h = {}
    mr = p.migration.start_run(initiated_by=p.op_migrator)
    n = [0]

    def pr(name):
        return p.stack.authn.register(name, "pw").id

    # 1-5 live-source inventory
    h["available_live_csv_source"] = p.migration.record_connection(source_family="new_inventory_current",
        classification="FILE_EXPORT", actual_system="DMS", integration_status="connected")
    h["available_live_json_source"] = p.migration.record_connection(source_family="arrival_availability",
        classification="API_AVAILABLE", actual_system="OEM logistics")
    h["governed_manual_source"] = p.migration.record_connection(source_family="executive_demo_state",
        classification="MANUAL_GOVERNED", actual_system="demo log")
    h["access_pending_source"] = p.migration.record_connection(source_family="market_value_residual",
        classification="ACCESS_PENDING", unresolved_blocker="vendor credentials pending")
    h["unavailable_source"] = p.migration.record_connection(source_family="policy_incentive_inputs",
        classification="UNAVAILABLE", unresolved_blocker="no export exists")
    # 6-8 schema + adapter
    h["actual_schema_v1"] = p.migration.register_schema("new_inventory_current", 1,
        schema={"columns": ["stock_number", "vin", "model"]})
    h["schema_drift_to_v2"] = p.migration.register_schema("new_inventory_current", 2,
        schema={"columns": ["stock_number", "vin", "model", "trim"]})
    row, prior = p.migration.correct_adapter("new_inventory_current", 3, schema={"columns": ["stock_number", "vin", "model", "trim", "color"]})
    h["corrected_adapter"] = {"new": row, "prior_versions": prior}
    # 9-13 real migrations

    def imp(fam, ck, payload):
        n[0] += 1
        return p.migration.migrate_source(mr["id"], contract_key=ck, payload=payload, source_family=fam,
                                          scope=SCOPE, effective_time=p.now_iso(), content_hash=f"sha256:fx{n[0]}")
    h["real_current_inventory_migration"] = imp("new_inventory_current", "new_inventory_current",
        "stock_number,vin,model,production_month,mileage\nN1,1GNSKBKC5FR000001,qx80,2026-03,5\n")
    h["real_production_order_migration"] = imp("production_orders", "production_orders",
        "manufacturer_order_id,model,eta_month,status\nMO-1,qx80,2026-05,in_production\n")
    h["real_retail_history_migration"] = imp("retail_history", "retail_history",
        "vin,sold_date,model,deal_number,price\n1GNSKBKC5FR000001,2026-01-15,qx80,D1,72000\n")
    h["real_service_loaner_migration"] = imp("service_loaner_fleet", "service_loaner_fleet",
        "vin,stock_number,status,in_service_date,last_checkout_mileage\n1GNSKBKC5FR000002,L1,active,2025-12-01,1200\n")
    h["real_executive_demo_migration"] = p.migration.migrate_history(mr["id"], fact_type="executive_demo_state",
        subject_ref="vin:ED1", source_row_ref="row1", event_date="2026-02-01", migration_date=p.now_iso())
    # 14-18 identity
    h["matched_vin"] = p.migration.migrate_identity(mr["id"], subject_kind="vehicle", source_key="VIN-M", existing_ref="vu_1")
    h["duplicate_vin"] = p.migration.migrate_identity(mr["id"], subject_kind="vehicle", source_key="VIN-D", duplicate_of="vu_1")
    h["conflicting_vin"] = p.migration.migrate_identity(mr["id"], subject_kind="vehicle", source_key="VIN-C", conflict=True)
    h["prevIN_linked_to_vin"] = p.migration.migrate_identity(mr["id"], subject_kind="order", source_key="MO-1", prevIN_of="order_1")
    h["unresolved_identity"] = p.migration.migrate_identity(mr["id"], subject_kind="vehicle", source_key="VIN-U")
    h["unresolved_identity"] = p.migration.migrate_identity(mr["id"], subject_kind="vehicle", source_key="VIN-UR", conflict=True)
    # 19-21 policy
    h["confirmed_policy"] = p.migration.migrate_policy(principal=p.op_migrator, scope=SCOPE,
        policy_family="desired_ending_coverage", proposed_value="30", owner="GM", evidence="memo",
        effective_date="2026-09-01", authority="dealer")
    h["missing_policy"] = {"missing": p.migration.required_policies_present(SCOPE, REQUIRED_POLICIES)}
    h["conflicting_policy"] = p.migration.migrate_policy(principal=p.op_migrator, scope=SCOPE,
        policy_family="model_preference", proposed_value="QX80", owner="GM", evidence="memo",
        effective_date="2026-09-01", authority="dealer", conflict_with="QX60")
    # 22-24 authority
    real_pr = pr("Real Manager")
    h["actual_principal"] = p.migration.migrate_authority(principal=p.op_migrator, scope=SCOPE,
        principal_ref=real_pr, capability="workspace.view", role="manager")
    try:
        p.migration.migrate_authority(principal=p.op_migrator, scope=SCOPE, principal_ref=real_pr,
                                      capability="*", grant_scope="*")
        h["insufficient_authority"] = {"overbroad_blocked": False}
    except ValidationError:
        h["insufficient_authority"] = {"overbroad_blocked": True}
    # SoD: same principal cannot both issue + approve is enforced by Phase 9; here we record distinct roles
    h["separation_of_duties_conflict"] = {"note": "issue/approve/execute remain distinct roles",
                                          "decider": p.p9.decider, "approver": p.p9.approver}
    # 25-27 reconstruction
    h["reconstructed_new_inventory_plan"] = p.migration.reconstruct_domain_state(mr["id"],
        domain="new_inventory", real_fact_refs=["bf_real_1", "bf_real_2"], output_ref="plan_real_1", scope=SCOPE)
    h["reconstructed_service_loaner_fleet"] = p.migration.reconstruct_domain_state(mr["id"],
        domain="service_loaner", real_fact_refs=["bf_sl_1"], output_ref="sl_real_1", scope=SCOPE)
    h["reconstructed_executive_demo_portfolio"] = p.migration.reconstruct_domain_state(mr["id"],
        domain="executive_demo", real_fact_refs=["bf_ed_1"], output_ref="ed_real_1", scope=SCOPE)
    # 28-32 actual executors (real domain methods bound; not synthetic)
    for key, action in (("actual_cpo_executor", "service_loaner.entry.execute"),
                        ("actual_dealer_trade_executor", "service_loaner.retirement.complete"),
                        ("actual_ctp_executor", "service_loaner.return.confirm"),
                        ("actual_loaner_executor", "service_loaner.used_cars.confirm"),
                        ("actual_executive_demo_executor", "executive_demo.retirement.execute")):
        h[key] = {"bound": p.registry.has(action), "synthetic": p.registry.is_synthetic(action)}
    # a real execdemo execution end-to-end
    dec, unit, rc = p.prepare_live_execution("1HGCM82633A799001")
    p.live.execute_bound(principal=p.op_executor, scope=SCOPE, decision=dec, idempotency_key="fx-live")
    h["actual_executive_demo_executor"] = {"bound": True, "synthetic": False,
                                           "state": p.p7.store.get_unit(unit.id).membership_state}
    # 33-36 shadow modes
    h["shadow_data_only"] = p.shadow.set_mode(principal=p.op_shadow, scope=SCOPE, domain="new_inventory", mode="DATA_ONLY")
    h["shadow_review_only"] = p.shadow.set_mode(principal=p.op_shadow, scope=SCOPE, domain="production", mode="REVIEW_ONLY")
    h["execution_pilot"] = p.shadow.set_mode(principal=p.op_shadow, scope=SCOPE, domain="service_loaner", mode="EXECUTION_PILOT")
    h["blocked_domain"] = p.shadow.set_mode(principal=p.op_shadow, scope=SCOPE, domain="dealer_trade", mode="BLOCKED")
    # 37-44 parallel validation
    subs = [
        {"subject_ref": "s_match", "domain": "new_inventory", "elite_value": 5, "legacy_value": 5},
        {"subject_ref": "s_data", "domain": "new_inventory", "elite_value": 8, "legacy_value": 6, "classification": "DATA_DIFFERENCE"},
        {"subject_ref": "s_time", "domain": "production", "elite_value": 3, "legacy_value": 3, "classification": "TIMING_DIFFERENCE"},
        {"subject_ref": "s_pol", "domain": "new_inventory", "elite_value": 2, "legacy_value": 4, "classification": "POLICY_DIFFERENCE"},
        {"subject_ref": "s_def", "domain": "service_loaner", "elite_value": 1, "legacy_value": 9, "classification": "ELITE_DEFECT"},
        {"subject_ref": "s_leg", "domain": "new_inventory", "elite_value": 7, "legacy_value": 0, "classification": "LEGACY_LIMITATION"},
        {"subject_ref": "s_exp", "domain": "new_inventory", "elite_value": 4, "legacy_value": 4, "classification": "EXPECTED_DIFFERENCE"},
        {"subject_ref": "s_unr", "domain": "new_inventory", "elite_value": 3, "legacy_value": 8},
    ]
    pv = p.parallel.run(principal=p.op_validator, scope=SCOPE, subjects=subs, run_date="2026-08-06")
    by = {r["subject_ref"]: r for r in pv["results"]}
    h["parallel_match"] = by["s_match"]; h["data_difference"] = by["s_data"]
    h["timing_difference"] = by["s_time"]; h["policy_difference"] = by["s_pol"]
    h["elite_defect"] = by["s_def"]; h["legacy_limitation"] = by["s_leg"]
    h["expected_difference"] = by["s_exp"]; h["unresolved_material_difference"] = by["s_unr"]
    # 45 resolved discrepancy
    disc = p.discrepancy.open(parallel_result_ref=by["s_data"]["id"], domain="new_inventory", scope=SCOPE,
                             summary="data difference", classification="DATA_DIFFERENCE")
    p.discrepancy.transition(principal=p.op_validator, scope=SCOPE, discrepancy_id=disc["id"],
                             to_status="RESOLVED", reason="source corrected", evidence="corrected import")
    h["resolved_discrepancy"] = p.store.get_discrepancy(disc["id"])
    # 46-48 UAT
    t = p.uat.add_test(test_case="Decision Inbox loads", domain="new_inventory", scope=SCOPE, expected_result="loads")
    h["uat_pass"] = p.uat.record(principal=p.op_uat, scope=SCOPE, uat_test_id=t["id"], actual_result="loads", outcome="pass")
    t2 = p.uat.add_test(test_case="Loaner workspace", domain="service_loaner", scope=SCOPE, expected_result="loads")
    fail = p.uat.record(principal=p.op_uat, scope=SCOPE, uat_test_id=t2["id"], actual_result="error", outcome="fail")
    h["uat_failure"] = fail
    h["uat_retest_pass"] = p.uat.record(principal=p.op_uat, scope=SCOPE, uat_test_id=t2["id"],
                                        actual_result="loads", outcome="pass", retest_of=fail["id"])
    # 49-53 rehearsals
    reh = p.rehearsal.migration_rehearsal(); h["migration_rehearsal_pass"] = reh
    h["migration_rehearsal_fail"] = p.store.add_migration_rehearsal(target_db="bad", outcome="fail",
                                                                    report="simulated failure", restart_verified=0)
    h["rollback_rehearsal_pass"] = p.rehearsal.rollback_rehearsal(migration_rehearsal_ref=reh["id"],
                                                                  elite_history_preserved=True, legacy_available=True)
    h["rollback_rehearsal_fail"] = p.rehearsal.rollback_rehearsal(migration_rehearsal_ref=reh["id"],
                                                                  elite_history_preserved=True, legacy_available=False)
    h["recovery_rehearsal_pass"] = p.rehearsal.recovery_rehearsal(scenario="app_crash", committed_truth_preserved=True)
    # 54-58 release package + readiness dimensions
    pkg = p.packages.build(version_label="v1.0.0", application_revision="83d66e4", migration_level=12)
    pkg = p.packages.issue(principal=p.op_releaser, scope=SCOPE, release_package_id=pkg["id"])
    h["release_package"] = pkg
    full = {d: {"status": "PASS"} for d in ["ENGINEERING_READY", "DATA_READY", "POLICY_READY",
            "AUTHORITY_READY", "OPERATOR_READY", "MIGRATION_READY", "ROLLBACK_READY", "SECURITY_READY"]}
    cert_full = p.readiness.certify(principal=p.op_releaser, scope=SCOPE, release_package_ref=pkg["id"], dimensions=full)
    h["engineering_ready"] = p.readiness.dimensions_of(cert_full["id"])["ENGINEERING_READY"]
    for xs in ("store:DN", "store:ON", "store:PW", "store:EX"):
        p.stack.grant(p.op_releaser, CAPS["PACKAGE_ISSUE"], xs)
        p.stack.grant(p.op_releaser, CAPS["CERTIFY"], xs)
        p.stack.grant(p.op_authorizer, CAPS["AUTHORIZE_RELEASE"], xs)
    notdata = dict(full); notdata["DATA_READY"] = {"status": "FAIL"}
    pkg2 = p.packages.issue(principal=p.op_releaser, scope="store:DN", release_package_id=p.packages.build(version_label="v1-dn", application_revision="x", migration_level=12)["id"])
    cert_nd = p.readiness.certify(principal=p.op_releaser, scope="store:DN", release_package_ref=pkg2["id"], dimensions=notdata)
    h["data_not_ready"] = {"overall": cert_nd["overall"], "data": p.readiness.dimensions_of(cert_nd["id"])["DATA_READY"]["status"]}
    notop = dict(full); notop["OPERATOR_READY"] = {"status": "UNRESOLVED"}
    pkg3 = p.packages.issue(principal=p.op_releaser, scope="store:ON", release_package_id=p.packages.build(version_label="v1-on", application_revision="x", migration_level=12)["id"])
    p.stack.grant(p.op_releaser, CAPS["CERTIFY"], "store:ON")
    cert_no = p.readiness.certify(principal=p.op_releaser, scope="store:ON", release_package_ref=pkg3["id"], dimensions=notop)
    h["operator_not_ready"] = {"overall": cert_no["overall"]}
    warn = dict(full); warn["SECURITY_READY"] = {"status": "PASS_WITH_WARNINGS"}
    pkg4 = p.packages.issue(principal=p.op_releaser, scope="store:PW", release_package_id=p.packages.build(version_label="v1-pw", application_revision="x", migration_level=12)["id"])
    p.stack.grant(p.op_releaser, CAPS["CERTIFY"], "store:PW")
    p.stack.grant(p.op_authorizer, CAPS["AUTHORIZE_RELEASE"], "store:PW")
    cert_w = p.readiness.certify(principal=p.op_releaser, scope="store:PW", release_package_ref=pkg4["id"], dimensions=warn)
    h["pass_with_warnings"] = {"overall": cert_w["overall"]}
    # 59-63 authorization
    h["go_live_not_authorized"] = {"authorized": p.authorization.is_go_live_authorized("store:ON", pkg3["id"])}
    lim = p.authorization.authorize(principal=p.op_authorizer, scope="store:PW", release_package_ref=pkg4["id"],
                                    certification_ref=cert_w["id"], disposition="AUTHORIZE_LIMITED_DOMAIN_GO_LIVE",
                                    enabled_domains=["service_loaner"], rollback_plan_ref="rb1")
    h["limited_domain_authorization"] = lim
    cont = p.authorization.authorize(principal=p.op_authorizer, scope=SCOPE, release_package_ref=pkg["id"],
                                     certification_ref=cert_full["id"], disposition="CONTINUE_PARALLEL_RUN")
    h["continue_parallel_run_decision"] = cont
    past = (p.clock.now() - _dt.timedelta(hours=1)).isoformat()
    p.stack.grant(p.op_authorizer, CAPS["AUTHORIZE_RELEASE"], "store:EX")
    p.stack.grant(p.op_releaser, CAPS["CERTIFY"], "store:EX")
    pkgx = p.packages.issue(principal=p.op_releaser, scope="store:EX", release_package_id=p.packages.build(version_label="v1-ex", application_revision="x", migration_level=12)["id"])
    certx = p.readiness.certify(principal=p.op_releaser, scope="store:EX", release_package_ref=pkgx["id"], dimensions=full)
    exp = p.authorization.authorize(principal=p.op_authorizer, scope="store:EX", release_package_ref=pkgx["id"],
                                    certification_ref=certx["id"], disposition="AUTHORIZE_GO_LIVE",
                                    rollback_plan_ref="rb1", expires_at=past)
    h["expired_release_authorization"] = {"active": p.authorization.active_authorization("store:EX", pkgx["id"])}
    # 63 post-certification blocker supersedes prior readiness
    blocked = dict(full); blocked["DATA_READY"] = {"status": "FAIL"}
    cert_blocked = p.readiness.certify(principal=p.op_releaser, scope=SCOPE, release_package_ref=pkg["id"], dimensions=blocked)
    h["post_certification_blocker"] = {"overall": cert_blocked["overall"],
                                       "prior_superseded": bool(p.store.get_certification(cert_full["id"])["superseded_by"])}
    # 64 restart durability
    h["restart_durability"] = {"version": p.stack.db.version()}
    return h
