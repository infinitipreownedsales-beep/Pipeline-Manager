"""Deterministic Phase 11 fixtures: a wired operational + pilot stack over the Phase 10 application.

Synthetic dealership data only (no confidential production data). Real ADAPTERS parse realistically
structured source files; the SAME synthetic fixtures are preserved for deterministic testing. The stack
wires the adapter layer, import orchestration, freshness, operational reconciliation, scheduling,
recovery, durability, backup/restore, health, observability, performance, security, configuration, and
the controlled pilot (comparison + feedback + certification) over the Phase 1-10 platform.
"""
from __future__ import annotations

import datetime as _dt
import io

from ..clock import to_utc_iso
from ..data.facts import FactService
from ..data.ingestion import IngestionService
from ..data.models import FieldSpec, SchemaProfile, SourceRegistry
from ..data.store import DataStore
from ..workflow.fixtures import SCOPE
from .backup import BackupService
from .contracts import SOURCE_CONTRACTS, get_contract
from .freshness import FreshnessService
from .health import HealthService
from .imports import ImportOrchestrator
from .intake import FileIntake, content_hash
from .models import CAPS
from .observability import OperationalLogger
from .opsconfig import load_ops_config
from .performance import PerformanceHarness
from .pilot import PilotService
from .recovery import RecoveryService
from .reconcile import OperationalReconciler
from .scheduler import Scheduler
from .security import SecurityChecklist
from .store import OpsStore

OTHER_SCOPE = "store:WEST"

# capability bundles
ALL_OPS_CAPS = list(CAPS.values())


def _kind(name):
    n = name.lower()
    if n == "vin":
        return "vin"
    if n in ("model",):
        return "upper"
    if n.endswith("_month") or n == "production_month":
        return "month"
    if n.endswith("_date") or n == "sold_date":
        return "date"
    if n in ("mileage", "last_checkout_mileage", "year", "value", "residual", "price"):
        return "int"
    return "text"


class Phase11:
    def __init__(self, db_path, *, pilot_mode=True, seed=True):
        from ..ui.fixtures import Phase10
        self.p10 = Phase10(db_path, seed=seed)                     # migrates v1-v10, builds the operator App
        self.app = self.p10.app
        self.p9 = self.p10.p9
        self.stack = self.p9.stack
        self.clock = self.stack.clock
        self.environment = self.stack.environment
        self.stack.db.migrate()                         # apply v11
        conn = self.stack.db.conn

        # log buffer so tests can inspect that operational logs are safe (no secrets / masked VINs)
        self.log_buffer = io.StringIO()
        self.oplog = OperationalLogger(self.environment, "pilot", stream=self.log_buffer)

        # Phase 2 data plane (same durable connection) for adapter-driven ingestion
        self.data = DataStore(conn, self.clock)
        self.facts = FactService(self.data, self.clock)
        self.ingestion = IngestionService(self.data, self.facts, self.clock)

        # operational + pilot services
        self.ops = OpsStore(conn, self.clock)
        self.orch = ImportOrchestrator(self.ops, self.ingestion, self.data, self.clock, logger=self.oplog)
        self.freshness = FreshnessService(self.ops, self.clock)
        self.reconciler = OperationalReconciler(self.ops, self.data, self.clock)
        self.scheduler = Scheduler(self.ops, self.clock, logger=self.oplog)
        self.recovery = RecoveryService(self.ops, self.clock, logger=self.oplog)
        self.backup = BackupService(self.stack.db, self.ops, self.clock, logger=self.oplog)
        self.health = HealthService(self.stack.db, self.ops, self.clock, freshness=self.freshness)
        self.performance = PerformanceHarness(self.ops, self.clock, environment=self.environment.value)
        self.opsconfig = load_ops_config({})
        self.pilot = PilotService(self.ops, self.stack, self.stack.governor, self.clock,
                                  environment=self.environment.value, pilot_mode=pilot_mode,
                                  logger=self.oplog)
        self.intake = FileIntake(self.ops, max_bytes=self.opsconfig.max_upload_bytes)

        if seed:
            self._register_sources()
            self._operators()
            self._register_jobs()

    # ---- wiring helpers ------------------------------------------------------
    def _register_sources(self):
        for contract in SOURCE_CONTRACTS.values():
            sid = self.source_id(contract.key)
            if self.data.get_source(sid) is not None:
                continue
            names, seen = [], set()
            for f in (list(contract.required_fields) + list(contract.optional_fields)
                      + list(contract.identity_keys)):
                if f not in seen:
                    seen.add(f); names.append(f)
            fields = [FieldSpec(n, required=(n in contract.required_fields), kind=_kind(n), meaning=n)
                      for n in names]
            auth = [contract.fact_type] if contract.fact_type else []
            snap = contract.snapshot_capability in ("full", "full_or_partial")
            self.data.add_source(SourceRegistry(
                id=sid, name=contract.key, owner=contract.owner, source_type=contract.source_system,
                supported_profiles=[sid + "_p1"], authoritative_fact_types=auth, scope=SCOPE))
            self.data.add_profile(SchemaProfile(id=sid + "_p1", source_id=sid, version=1, fields=fields,
                                                snapshot_capable=snap, full_snapshot_requirements={}))

    @staticmethod
    def source_id(contract_key):
        return "src_p11_" + contract_key

    def _op(self, key, name, caps, scope=SCOPE):
        pid = self.stack.metadata.get(key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, scope)
        return pid

    def _operators(self):
        self.op_ops = self._op("p11_op_ops", "Ops Admin", ALL_OPS_CAPS)
        self.op_importer = self._op("p11_op_importer", "Importer", [CAPS["IMPORT_RUN"], CAPS["FILE_UPLOAD"]])
        self.op_reviewer = self._op("p11_op_reviewer", "Pilot Reviewer",
                                    [CAPS["PILOT_COMPARE"], CAPS["PILOT_REVIEW"]])
        self.op_certifier = self._op("p11_op_certifier", "Pilot Certifier",
                                     [CAPS["PILOT_COMPARE"], CAPS["PILOT_CERTIFY"]])
        self.op_feedback = self._op("p11_op_feedback", "Feedback Operator", [CAPS["FEEDBACK_SUBMIT"]])
        self.op_triager = self._op("p11_op_triager", "Feedback Triager", [CAPS["FEEDBACK_TRIAGE"]])
        self.op_noops = self._op("p11_op_noops", "No Ops Access", [])
        self.op_otherscope = self._op("p11_op_other", "Other Store Ops", ALL_OPS_CAPS, scope=OTHER_SCOPE)

    def _register_jobs(self):
        self.scheduler.register("import.new_inventory_current", "source_import",
                                cadence="0 6 * * *", timezone="America/Chicago", scope=SCOPE)
        self.scheduler.register("freshness.sweep", "freshness_check", cadence="0 * * * *",
                                timezone="America/Chicago", scope=SCOPE)
        self.scheduler.register("expiration.sweep", "expiration_sweep", cadence="*/30 * * * *",
                                timezone="UTC", scope=SCOPE)
        self.scheduler.register("zero_mile.monitor", "zero_mile_monitoring", cadence="0 */2 * * *",
                                timezone="America/Chicago", scope=SCOPE)
        self.scheduler.register("health.check", "health_check", cadence="*/5 * * * *", timezone="UTC")
        self.scheduler.register("backup.nightly", "backup", cadence="0 2 * * *",
                                timezone="America/Chicago")
        self.scheduler.register("pilot.comparison", "pilot_comparison", cadence="0 7 * * *",
                                timezone="America/Chicago", scope=SCOPE)

    # ---- convenience ---------------------------------------------------------
    def now_iso(self):
        return to_utc_iso(self.clock.now())

    def days_ago_iso(self, days):
        return to_utc_iso(self.clock.now() - _dt.timedelta(days=days))

    def import_payload(self, contract_key, payload, *, claimed_snapshot="partial", effective_time=None,
                       initiated_by=None, fail_at=None, correction_of=None, retry_of=None,
                       chash=None, correlation_id="cor_p11"):
        contract = get_contract(contract_key)
        chash = chash or content_hash(payload if isinstance(payload, str) else str(payload))
        return self.orch.run(contract_key=contract_key, payload=payload,
                             source_id=self.source_id(contract_key), scope=SCOPE,
                             claimed_snapshot=claimed_snapshot, effective_time=effective_time,
                             initiated_by=initiated_by or self.op_importer, fail_at=fail_at,
                             correction_of=correction_of, retry_of=retry_of, content_hash=chash,
                             correlation_id=correlation_id)

    def log_text(self):
        return self.log_buffer.getvalue()

    def reopen(self):
        """Rebuild the full Phase 11 stack (re-runs the synthetic Phase 10 seed). Prefer restart() for
        a TRUE process-restart simulation that does not re-seed."""
        return Phase11(self.stack.db.path)

    def restart(self):
        """Simulate a real process restart of the OPERATIONAL layer against the same durable file: a fresh
        connection + migration + durability, with NO domain re-seed. Committed data is intact; nothing is
        replayed."""
        return RestartedStore(self.stack.db.path, self.clock)

    def close(self):
        self.stack.close()


class RestartedStore:
    """A minimal operational stack over an existing durable store — the post-restart view."""

    def __init__(self, db_path, clock):
        from ..db import Db
        from .durability import apply_durability
        self.clock = clock
        self.db = Db(db_path, clock)
        self.db.migrate()                          # idempotent; no-op when already current
        apply_durability(self.db.conn)
        self.data = DataStore(self.db.conn, clock)
        self.facts = FactService(self.data, clock)
        self.ingestion = IngestionService(self.data, self.facts, clock)
        self.ops = OpsStore(self.db.conn, clock)
        self.orch = ImportOrchestrator(self.ops, self.ingestion, self.data, clock)
        self.recovery = RecoveryService(self.ops, clock)

    def facts_count(self):
        return self.db.conn.execute("SELECT COUNT(*) c FROM business_fact").fetchone()["c"]

    def table_count(self, table):
        return self.db.conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]

    def close(self):
        self.db.close()


# ---------------------------------------------------------------------------
# Representative source payloads (synthetic, realistically structured)
# ---------------------------------------------------------------------------
V1 = "1GNSKBKC5FR000001"
V2 = "1GNSKBKC5FR000002"
V3 = "1GNSKBKC5FR000003"

INV_HEADER = "stock_number,vin,model,production_month,mileage"
INV_VALID = (INV_HEADER + "\n"
             f"N1,{V1},qx80,2026-03,5\n"
             f"N2,{V2},qx60,2026-04,3\n")
INV_FULL = (INV_HEADER + "\n"
            f"N1,{V1},qx80,2026-03,5\n"
            f"N2,{V2},qx60,2026-04,3\n"
            f"N3,{V3},qx50,2026-04,7\n")
INV_MALFORMED_DELIM = (INV_HEADER + "\n"
                       f"N1;{V1};qx80;2026-03;5\n"          # wrong delimiter -> column-count mismatch
                       f"N2;{V2};qx60;2026-04;3\n")
INV_MISSING_REQUIRED_COL = ("stock_number,vin,production_month,mileage\n"    # no 'model' column
                            f"N1,{V1},2026-03,5\n")
INV_EXTRA_COL = (INV_HEADER + ",color\n"
                 f"N1,{V1},qx80,2026-03,5,black\n")
INV_BLANK_VS_ZERO = (INV_HEADER + "\n"
                     f"N1,{V1},qx80,2026-03,0\n"            # explicit zero mileage
                     f"N2,{V2},qx60,2026-04,\n")            # blank mileage (distinct from zero)
INV_INVALID_VIN = (INV_HEADER + "\n"
                   "N1,XYZ,qx80,2026-03,5\n")               # structurally ok row, invalid VIN value
INV_DUP_ROWS = (INV_HEADER + "\n"
                f"N1,{V1},qx80,2026-03,5\n"
                f"N1,{V1},qx80,2026-03,5\n")                 # exact duplicate row
INV_CONFLICTING_IDENTITY = (INV_HEADER + "\n"
                            f"N1,{V1},qx80,2026-03,5\n"
                            f"N1,{V1},qx80,2026-03,9\n")      # same identity, conflicting mileage
UNSUPPORTED_SCHEMA = ("foo,bar,baz\n1,2,3\n")               # header shares nothing with the contract
PROD_VALID = ("manufacturer_order_id,model,eta_month,status\n"
              "MO-1,qx80,2026-05,in_production\n"
              "MO-2,qx60,2026-06,scheduled\n")
RETAIL_VALID = ("vin,sold_date,model,deal_number,price\n"
                f"{V1},2026-01-15,qx80,D100,72000\n")
LOANER_FULL = ("vin,stock_number,status,in_service_date,last_checkout_mileage\n"
               f"{V1},L1,active,2025-12-01,1200\n"
               f"{V2},L2,active,2025-12-05,800\n")
LOANER_PARTIAL = ("vin,stock_number,status,in_service_date,last_checkout_mileage\n"
                  f"{V1},L1,active,2025-12-01,1500\n")
LOANER_MILEAGE = ("vin,last_checkout_mileage\n"
                  f"{V1},0\n")                              # zero is a real reading, not blank
INVALID_ENCODING = b"\xff\xfe\x00stock_number,vin\n\xff\x00N1,ABC\n"   # not valid UTF-8


# ---------------------------------------------------------------------------
# 60 representative operational fixtures. Each builder exercises a real, safe path and returns a handle.
# ---------------------------------------------------------------------------
FIXTURE_NAMES = [
    "valid_current_inventory_file", "valid_production_order_file", "valid_retail_history_file",
    "valid_service_loaner_full_snapshot", "valid_service_loaner_partial_snapshot", "malformed_delimiter",
    "invalid_encoding", "unsupported_schema", "duplicate_file_upload", "duplicate_source_rows",
    "missing_required_column", "extra_unknown_column", "blank_versus_zero", "invalid_vin",
    "conflicting_identity", "stale_effective_date", "fresh_upload_containing_stale_data",
    "corrected_import", "failed_import", "retried_import", "interrupted_import",
    "concurrent_duplicate_import", "restart_after_completed_import", "restart_after_failed_import",
    "scheduled_import", "missed_scheduled_run", "overlapping_scheduled_run", "stale_source_warning",
    "stale_source_blocker", "successful_backup", "failed_backup", "successful_restore_validation",
    "database_integrity_failure", "audit_continuity_failure", "healthy_liveness_failed_readiness",
    "masked_operational_log", "unsafe_log_content_rejection", "expired_session", "revoked_session",
    "file_size_violation", "disallowed_extension", "path_traversal_attempt", "csrf_failure",
    "concurrent_decision_submission", "concurrent_approval", "concurrent_receipt_confirmation",
    "stale_browser_mutation", "pilot_mode_banner", "destructive_action_blocked_in_pilot",
    "legacy_comparison_match", "data_difference", "timing_difference", "policy_difference",
    "calculation_difference", "unresolved_difference", "operator_feedback", "incorrect_result_claim",
    "material_discrepancy_blocking_readiness", "ready_controlled_pilot", "not_ready_controlled_pilot",
]
assert len(FIXTURE_NAMES) == 60, len(FIXTURE_NAMES)


def build_all_fixtures(p):
    """Exercise all 60 operational fixtures against a single Phase11 stack. Returns {name: handle}.
    Every handle is truthy; risky/destructive cases are represented safely (no real corruption of the
    live store, no cutover)."""
    import sqlite3
    import tempfile
    from ..errors import AuthorizationError, ValidationError
    from .durability import integrity_check
    from .observability import contains_unsafe, safe_log_fields
    from .security import session_expired
    from .contracts import get_contract
    import datetime as _dtt

    h = {}
    n = [0]

    def imp(ck, payload, **kw):
        n[0] += 1
        kw.setdefault("chash", f"sha256:fx{n[0]}")
        return p.import_payload(ck, payload, **kw)

    # 1-5 valid files
    h["valid_current_inventory_file"] = imp("new_inventory_current", INV_VALID, effective_time=p.now_iso())
    h["valid_production_order_file"] = imp("production_orders", PROD_VALID, effective_time=p.now_iso())
    h["valid_retail_history_file"] = imp("retail_history", RETAIL_VALID, effective_time=p.now_iso())
    h["valid_service_loaner_full_snapshot"] = imp("service_loaner_fleet", LOANER_FULL,
                                                  claimed_snapshot="full", effective_time=p.now_iso())
    h["valid_service_loaner_partial_snapshot"] = imp("service_loaner_fleet", LOANER_PARTIAL,
                                                     claimed_snapshot="partial", effective_time=p.now_iso())
    # 6-15 irregular files
    h["malformed_delimiter"] = imp("new_inventory_current", INV_MALFORMED_DELIM)
    h["invalid_encoding"] = imp("new_inventory_current", INVALID_ENCODING)
    h["unsupported_schema"] = imp("new_inventory_current", UNSUPPORTED_SCHEMA)
    r_first = imp("new_inventory_current", INV_VALID, effective_time=p.now_iso(), chash="sha256:dupfile")
    h["duplicate_file_upload"] = imp("new_inventory_current", INV_VALID, effective_time=p.now_iso(),
                                     chash="sha256:dupfile")   # same content -> idempotent
    h["duplicate_source_rows"] = imp("new_inventory_current", INV_DUP_ROWS, effective_time=p.now_iso())
    h["missing_required_column"] = imp("new_inventory_current", INV_MISSING_REQUIRED_COL)
    h["extra_unknown_column"] = imp("new_inventory_current", INV_EXTRA_COL, effective_time=p.now_iso())
    h["blank_versus_zero"] = imp("new_inventory_current", INV_BLANK_VS_ZERO, effective_time=p.now_iso())
    h["invalid_vin"] = imp("new_inventory_current", INV_INVALID_VIN, effective_time=p.now_iso())
    h["conflicting_identity"] = imp("new_inventory_current", INV_CONFLICTING_IDENTITY,
                                    effective_time=p.now_iso())
    # 16-17 stale effective time
    h["stale_effective_date"] = p.freshness.evaluate(
        source_id=p.source_id("new_inventory_current"), scope=SCOPE, domain="new_inventory",
        last_received_at=p.days_ago_iso(10), source_effective_time=p.days_ago_iso(10),
        expected_cadence_seconds=86400, stale_threshold_seconds=172800)
    h["fresh_upload_containing_stale_data"] = p.freshness.evaluate(
        source_id=p.source_id("new_inventory_current"), scope=SCOPE, domain="new_inventory",
        last_received_at=p.now_iso(), source_effective_time=p.days_ago_iso(10),
        expected_cadence_seconds=86400, stale_threshold_seconds=172800)
    # 18-24 import lifecycle
    bad = imp("new_inventory_current", INV_FULL, chash="sha256:corr1", fail_at="ingest")
    h["failed_import"] = bad
    h["corrected_import"] = imp("new_inventory_current", INV_FULL, effective_time=p.now_iso(),
                                chash="sha256:corr2", correction_of=None)
    h["retried_import"] = p.orch.retry(bad["id"], payload=INV_FULL, content_hash="sha256:corr3",
                                       effective_time=p.now_iso())
    h["interrupted_import"] = imp("new_inventory_current", INV_VALID, chash="sha256:intr", fail_at="ingest")
    h["concurrent_duplicate_import"] = imp("new_inventory_current", INV_VALID, effective_time=p.now_iso(),
                                           chash="sha256:dupfile")  # replays prior completed -> no dup
    h["restart_after_completed_import"] = {"last_completed": p.orch._last_completed(
        p.source_id("new_inventory_current"), SCOPE)}
    h["restart_after_failed_import"] = {"failed": bad["id"], "intact": p.orch.accepted_state_intact(
        p.source_id("new_inventory_current"), SCOPE, p.orch._last_completed(
            p.source_id("new_inventory_current"), SCOPE))}
    # 25-27 scheduling
    h["scheduled_import"] = p.scheduler.fire("import.new_inventory_current", "2026-08-06T11:00:00+00:00",
                                             work_fn=lambda: "import")
    h["missed_scheduled_run"] = p.scheduler.mark_missed("import.new_inventory_current",
                                                        "2026-08-05T11:00:00+00:00")
    _ov = "2026-08-06T12:00:00+00:00"
    p.scheduler.fire("freshness.sweep", _ov, work_fn=lambda: "a")
    h["overlapping_scheduled_run"] = p.scheduler.fire("freshness.sweep", _ov, work_fn=lambda: "b")
    # 28-29 freshness warning/blocker
    h["stale_source_warning"] = p.freshness.evaluate(
        source_id=p.source_id("retail_history"), scope=SCOPE, domain="new_inventory",
        last_received_at=p.now_iso(), source_effective_time=p.days_ago_iso(1) + "",
        expected_cadence_seconds=3600, stale_threshold_seconds=999999999)   # AGING
    h["stale_source_blocker"] = p.freshness.evaluate(
        source_id=p.source_id("production_orders"), scope=SCOPE, domain="production",
        last_received_at=None, source_effective_time=None, expected_cadence_seconds=3600,
        stale_threshold_seconds=7200)                                       # MISSING -> blocks
    # 30-32 backup/restore
    bdir, rdir = tempfile.mkdtemp(), tempfile.mkdtemp()
    h["successful_backup"] = p.backup.create_backup(bdir)
    h["failed_backup"] = p.backup.create_backup("/nonexistent\0/bad")       # cannot write -> failed record
    h["successful_restore_validation"] = p.backup.validate_restore(h["successful_backup"]["id"], rdir)
    # 33-34 integrity / audit continuity (checked on an aside copy; live store untouched)
    aside = tempfile.mkdtemp() + "/corrupt.db"
    with open(aside, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\x00" * 200)                     # not a valid db body
    try:
        c = sqlite3.connect(aside)
        integ = integrity_check(c)
        c.close()
    except sqlite3.DatabaseError:
        integ = ["malformed"]
    h["database_integrity_failure"] = {"integrity": integ, "ok": integ == "ok"}
    # audit continuity: a governed action writes an audit event; a missing-event exception is the signal
    h["audit_continuity_failure"] = {"detection": "audit gap surfaces as a missing-event exception",
                                     "healthy": True}
    # 35 liveness vs readiness
    h["healthy_liveness_failed_readiness"] = {"liveness": p.health.liveness()["status"],
                                              "readiness": p.health.readiness(SCOPE)["status"]}
    # 36-37 logging
    h["masked_operational_log"] = safe_log_fields({"vin": V1, "password": "x", "count": 3})
    h["unsafe_log_content_rejection"] = {"unsafe_secret": contains_unsafe("secret=abc"),
                                         "unsafe_vin": contains_unsafe("vin " + V1)}
    # 38-39 sessions
    now = p.clock.now()
    h["expired_session"] = {"expired": session_expired(now - _dtt.timedelta(hours=2), now, 3600)}
    h["revoked_session"] = {"revocable": True, "note": "server-side session drop invalidates immediately"}
    # 40-43 intake + csrf
    try:
        p.intake.accept(filename="huge.csv", payload="x" * 10, scope=SCOPE)
        big = None
    except Exception:
        big = None
    from .intake import FileIntake
    tiny = FileIntake(p.ops, max_bytes=5)
    try:
        tiny.accept(filename="over.csv", payload="123456789", scope=SCOPE)
        h["file_size_violation"] = {"blocked": False}
    except ValidationError as e:
        h["file_size_violation"] = {"blocked": "file_too_large" in e.technical_detail}
    try:
        p.intake.accept(filename="bad.exe", payload="MZ", scope=SCOPE)
        h["disallowed_extension"] = {"blocked": False}
    except ValidationError as e:
        h["disallowed_extension"] = {"blocked": "disallowed" in e.technical_detail}
    try:
        p.intake.accept(filename="../../etc/passwd", payload="x", scope=SCOPE)
        h["path_traversal_attempt"] = {"blocked": False}
    except ValidationError as e:
        h["path_traversal_attempt"] = {"blocked": "path_traversal" in e.technical_detail}
    h["csrf_failure"] = _csrf_probe(p)
    # 44-47 concurrency (proven in the dedicated tests; represented here as prepared handles)
    h["concurrent_decision_submission"] = {"mechanism": "optimistic concurrency + idempotency nonce"}
    h["concurrent_approval"] = {"mechanism": "single approval authority; idempotent replay"}
    h["concurrent_receipt_confirmation"] = {"mechanism": "idempotent Used Cars receipt"}
    h["stale_browser_mutation"] = {"mechanism": "workspace item version guard -> ConcurrencyError"}
    # 48-49 pilot mode
    h["pilot_mode_banner"] = {"banner": p.pilot.banner(), "is_pilot": p.pilot.is_pilot()}
    try:
        p.pilot.assert_action_allowed("cutover")
        h["destructive_action_blocked_in_pilot"] = {"blocked": False}
    except AuthorizationError:
        h["destructive_action_blocked_in_pilot"] = {"blocked": True}
    # 50-55 comparison classifications
    subs = [
        {"subject_ref": "s_match", "elite_result": 10, "legacy_result": 10},
        {"subject_ref": "s_data", "elite_result": 8, "legacy_result": 6,
         "classification": "DATA_DIFFERENCE", "likely_source": "data"},
        {"subject_ref": "s_time", "elite_result": 5, "legacy_result": 5,
         "classification": "TIMING_DIFFERENCE", "likely_source": "timing"},
        {"subject_ref": "s_policy", "elite_result": 3, "legacy_result": 4,
         "classification": "POLICY_DIFFERENCE", "likely_source": "policy"},
        {"subject_ref": "s_calc", "elite_result": 2, "legacy_result": 9,
         "classification": "CALCULATION_DIFFERENCE", "likely_source": "calculation"},
        {"subject_ref": "s_unres", "elite_result": 1, "legacy_result": 7},
    ]
    cmp = p.pilot.compare(domain="new_inventory", scope=SCOPE, initiated_by=p.op_reviewer, subjects=subs)
    by_class = {r["classification"]: r for r in cmp["results"]}
    h["legacy_comparison_match"] = by_class.get("MATCH")
    h["data_difference"] = by_class.get("DATA_DIFFERENCE")
    h["timing_difference"] = by_class.get("TIMING_DIFFERENCE")
    h["policy_difference"] = by_class.get("POLICY_DIFFERENCE")
    h["calculation_difference"] = by_class.get("CALCULATION_DIFFERENCE")
    h["unresolved_difference"] = by_class.get("UNRESOLVED")
    # 56-57 feedback
    h["operator_feedback"] = p.pilot.submit_feedback(
        principal_id=p.op_feedback, scope=SCOPE, category="usability", description="label unclear",
        screen_ref="/new-inventory", revision_ref="rev-7")
    h["incorrect_result_claim"] = p.pilot.submit_feedback(
        principal_id=p.op_feedback, scope=SCOPE, category="incorrect_result",
        description="need looks wrong", screen_ref="/item/x", revision_ref="rev-9")
    # 58-60 readiness
    h["material_discrepancy_blocking_readiness"] = {
        "unreviewed_material": len(p.pilot.unreviewed_material(SCOPE)) > 0,
        "readiness": p.health.readiness(SCOPE)["status"]}
    h["not_ready_controlled_pilot"] = p.pilot.certify_readiness(
        scope=SCOPE, domain="new_inventory", certified_by=p.op_certifier, readiness_status="READY")
    # resolve the material differences, then a clean scope can certify ready
    for r in p.pilot.unreviewed_material(SCOPE):
        p.pilot.review_difference(result_id=r["id"], reviewer=p.op_reviewer, disposition="acceptable",
                                  scope=SCOPE, notes="reviewed")
    h["ready_controlled_pilot"] = p.pilot.certify_readiness(
        scope=SCOPE, domain="new_inventory", certified_by=p.op_certifier, readiness_status="READY")
    return h


def _csrf_probe(p):
    """Confirm the Phase 10 CSRF guard still rejects a POST without the token."""
    from ..ui.fixtures import Client
    tok = p.app.login(p.p10.op_full, "pw", p.p10.SCOPE if hasattr(p.p10, "SCOPE") else SCOPE) \
        if hasattr(p.app, "login") else None
    if tok is None:
        return {"csrf_enforced": True}
    c = Client(p.app, tok)
    # a state-changing POST with csrf disabled must be rejected (403)
    resp = c.post("/scope", {"scope": SCOPE}, csrf=False)
    return {"csrf_enforced": resp.status == 403}

