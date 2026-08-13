"""PERMANENT operational deployment of the certified real-demand + continuous-60-day + discrete planning
engine into Kyle's real Elite Pipeline database.

This is NOT a shadow/comparison tool. It ingests the real Speed-to-Sell workbook ONCE into the permanent DB
(observation-only), runs the certified governed DATA_ONLY decision engine against the permanent stores, and
persists the issued New-Inventory planning board the existing UI reads -- so Elite becomes Kyle's actual
inventory decision tool (Supply / ACQUIRE / MONITOR / arrived-disposition / incoming-redirect / evidence /
governed approval workflow / normal re-runs). Autonomous external execution stays OFF.

HARD SAFETY (fail closed):
  * Gate the exact certified HEAD + clean tree (this helper excluded).
  * Verify env/DB path/scope/schema/pre-state/Speed-to-Sell SHA BEFORE anything.
  * DRY-RUN FIRST on a WAL-consistent COPY: reproduce the certified board on the copy and assert it. The
    PERMANENT DB is opened read-write ONLY AFTER the copy reproduces the certified board.
  * Take + verify a pre-deployment backup before the permanent mutation, and a post-deployment backup after.
  * Re-assert the certified board + all governance invariants on the permanent DB, then reopen read-only.
  * On ANY failure: STOP, print a clear failure, preserve the pre-deployment backup, DO NOT repair or
    partially deploy.

It never: changes schema, ELITE_AUTH_SECRET, principals/grants, Executive-Demo release/shadow state, or
enables external execution; and never creates VehicleUnits / ProductionOrders / fabricated business facts.

Phone-safe: extract with `git show deploy/real-plan-permanent:tools/deploy_real_plan_permanent.py` and run the
single Windows command below while the checked-out HEAD stays the certified commit.
"""
from __future__ import annotations

import calendar
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter

REQUIRED_HEAD = "a8c6edf6709fefba85d183d6e00448ab9300f290"
STS_SHA = "3788E0F5D09C6A0CF2433C9B15F1D20AAF6C8554102E072D92E639735543215C"
HELPER_REL = "tools/deploy_real_plan_permanent.py"
TZ = "America/Chicago"
STORE = "store:HG_INFINITI_JACKSON"
DMS_CONTRACT = "new_inventory_pipeline_summary"
STS_CONTRACT = "speed_to_sell"

# The planning as-of is PINNED to the certified review date so the permanent issued board is exactly the one
# ChatGPT/Kyle reviewed (part-month exposure = 13/31). Later normal re-runs use the real current date.
CERT_ASOF = "2026-08-13"

PERM = os.environ.get("ELITE_DB_PATH", r"C:\ElitePipeline\data\elite.db")
PERM_EXPECTED = r"C:\ElitePipeline\data\elite.db"
ENVFILE = os.environ.get("ELITE_VALIDATE_ENV", r"C:\ElitePipeline\config\elite.env")
STS_FILE = os.environ.get("ELITE_STS_FILE",
                          r"C:\Users\Kyle.Montgomery\Downloads\SPEED TO SELL REPORT(20260813-042630).xlsx")
BACKUP_DIR = os.environ.get("ELITE_BACKUP_DIR", r"C:\ElitePipeline\backups")

# permanent pre-state expected from the current certified deployment (item 7)
BASE = dict(schema=12, observations=182, import_runs=2, facts=0, production_orders=0, vehicle_units=0,
            principals=2, active_grants=15)
# certified real board that the permanent issued plan must reproduce (item 14/15)
CERT_BOARD = dict(target_days_supply=60, integer_total_need=28, acquire_count=26,
                  integer_total_excess_arrived=21, integer_total_excess_incoming=2)


def P(*a):
    print(*a, flush=True)


class DeployError(Exception):
    pass


def _root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)


def gate_head_and_tree(root):
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if head != REQUIRED_HEAD:
        raise DeployError(f"HEAD is {head}, required certified {REQUIRED_HEAD}")
    dirty = [ln for ln in _git(root, "status", "--porcelain").stdout.splitlines()
             if ln[3:].strip().strip('"').replace("\\", "/") != HELPER_REL and ln[3:].strip()]
    if dirty:
        raise DeployError("working tree not clean (besides this helper): " + " | ".join(dirty))
    P(f"  HEAD={head} (certified commit) ; tree clean (helper-only)")


def load_env_no_echo(path):
    if not os.path.exists(path):
        raise DeployError(f"elite.env missing: {path}")
    n = 0
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"')
                n += 1
    P(f"  loaded elite.env ({n} keys; no secrets printed)")


def verify_sha(path, expect, label):
    if not os.path.exists(path):
        raise DeployError(f"{label} not found: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    got = h.hexdigest().upper()
    if got != expect.upper():
        raise DeployError(f"{label} SHA-256 mismatch: expected {expect}, got {got}")
    P(f"  {label} SHA-256 verified ({got})")


def _state(conn, current_version):
    c = lambda q: conn.execute(q).fetchone()[0]
    row = conn.execute("SELECT mode FROM domain_shadow_mode WHERE domain='executive_demo' AND store_scope=?"
                       " ORDER BY recorded_at DESC LIMIT 1", (STORE,)).fetchone()
    return dict(schema=current_version(conn),
                observations=c("SELECT COUNT(*) FROM source_observation"),
                import_runs=c("SELECT COUNT(*) FROM import_run"),
                facts=c("SELECT COUNT(*) FROM business_fact"),
                production_orders=c("SELECT COUNT(*) FROM production_order"),
                vehicle_units=c("SELECT COUNT(*) FROM vehicle_unit"),
                principals=c("SELECT COUNT(*) FROM principal"),
                active_grants=c("SELECT COUNT(*) FROM capability_grant WHERE active=1"),
                execdemo_mode=(row[0] if row else "DATA_ONLY"))


def _check(tag, st, expect):
    bad = [f"{k}: {st[k]}!={v}" for k, v in expect.items() if st.get(k) != v]
    P(f"  [{tag}] schema={st['schema']} obs={st['observations']} runs={st['import_runs']} facts={st['facts']} "
      f"orders={st['production_orders']} units={st['vehicle_units']} principals={st['principals']} "
      f"grants={st['active_grants']} execDemo={st['execdemo_mode']}")
    if st["execdemo_mode"] != "DATA_ONLY":
        bad.append(f"execdemo_mode {st['execdemo_mode']}!=DATA_ONLY")
    if bad:
        raise DeployError(f"{tag} mismatch: " + "; ".join(bad))


def online_backup(src_path, dst_path):
    """WAL-consistent backup via the SQLite online-backup API (never a raw copy of an open WAL DB)."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()


def verify_backup(dst_path, current_version, expect):
    ro = sqlite3.connect(f"file:{dst_path}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    st = _state(ro, current_version)
    ro.close()
    bad = [f"{k}: {st.get(k)}!={v}" for k, v in expect.items() if st.get(k) != v]
    if bad:
        raise DeployError(f"backup verify {dst_path} mismatch: " + "; ".join(bad))
    P(f"  backup verified: {dst_path} (obs={st['observations']} runs={st['import_runs']} "
      f"units={st['vehicle_units']} orders={st['production_orders']} facts={st['facts']})")


def _register_speed_to_sell_source(data, sid, scope):
    from elite.data.models import FieldSpec, SchemaProfile, SourceRegistry
    from elite.ops.contracts import get_contract
    from elite.ops.fixtures import _kind
    contract = get_contract(STS_CONTRACT)
    if data.get_source(sid) is not None:
        return
    names, seen = [], set()
    for f in list(contract.required_fields) + list(contract.optional_fields) + list(contract.identity_keys):
        if f not in seen:
            seen.add(f)
            names.append(f)
    fields = [FieldSpec(n, required=(n in contract.required_fields), kind=_kind(n), meaning=n) for n in names]
    data.add_source(SourceRegistry(id=sid, name=contract.key, owner=contract.owner,
                                   source_type=contract.source_system, supported_profiles=[sid + "_p1"],
                                   authoritative_fact_types=[], scope=scope))
    data.add_profile(SchemaProfile(id=sid + "_p1", source_id=sid, version=1, fields=fields,
                                   snapshot_capable=False, full_snapshot_requirements={}))


def _asof():
    """Pinned certified as-of -> (current_month, part_frac)."""
    y, m, d = int(CERT_ASOF[:4]), int(CERT_ASOF[5:7]), int(CERT_ASOF[8:10])
    dim = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}", max(0.05, min(1.0, d / dim))


def _run_engine(conn, clock, sts_sid, dms_sid, scope, do_import, payload, ch, receipt_id):
    """Import Speed-to-Sell (observation-only) if requested, then run the certified engine and return the
    result dict. Shared by the dry-run (on a copy) and the permanent deployment so both are identical."""
    from elite.newinv import supply_bridge as SB
    from elite.newinv import demand_bridge as DB
    from elite.newinv.snapshots import SnapshotReader
    from elite.newinv.store import NewInvStore
    from elite.newinv.demand import DemandService
    from elite.newinv.forecast import ForecastService
    from elite.newinv.planning import PlanningService
    from elite.newinv.planning_runner import PlanningContext, run_planning
    from elite.data.store import DataStore
    from elite.data.facts import FactService
    from elite.data.ingestion import IngestionService
    from elite.ops.store import OpsStore
    from elite.ops.imports import ImportOrchestrator
    from elite.policy.store import PolicyStore
    from elite.policy.models import CalculationFamily, CalculationVersion
    from elite.ids import new_id

    data = DataStore(conn, clock)
    ops = OpsStore(conn, clock)
    reader = SnapshotReader(ops, data, tz=TZ)
    policy = PolicyStore(conn, clock)
    store = NewInvStore(conn, clock)
    if do_import:
        facts = FactService(data, clock)
        ingestion = IngestionService(data, facts, clock)
        orch = ImportOrchestrator(ops, ingestion, data, clock, logger=None)
        _register_speed_to_sell_source(data, sts_sid, scope)
        run = orch.run(contract_key=STS_CONTRACT, payload=payload, source_id=sts_sid, scope=scope,
                       content_hash=ch, file_receipt_id=receipt_id, initiated_by="permanent-deploy",
                       claimed_snapshot="partial")
        P(f"  Speed-to-Sell import: state={run['state']} rows={run['row_count']} "
          f"accepted={run['accepted_count']} rejected={run['rejected_count']} unresolved={run['unresolved_count']}")

    cf = policy.add_calc_family(CalculationFamily(id=new_id("cf"), name="dms_planning_runner",
                                                  owning_domain="new_inventory"))
    demand_cv = policy.add_calc_version(CalculationVersion(id=new_id("cv"), family_id=cf.id,
                                        semver="1.0.0", lifecycle_status="active")).id
    plan_cv = policy.add_calc_version(CalculationVersion(id=new_id("cv"), family_id=cf.id,
                                      semver="1.0.1", lifecycle_status="active")).id
    demand_svc = DemandService(store, clock, policy)
    forecast_svc = ForecastService(store, clock, policy)
    planning_svc = PlanningService(store, clock, policy)

    obs_rows = DB.read_accepted_speed_to_sell_rows(conn, sts_sid, scope)
    current_month, part_frac = _asof()
    latest_midx = max([m for m in (DB.midx_of(o.get("sales_month")) for o in obs_rows) if m], default=None)
    current_midx = DB.midx_of(current_month.replace("-", ""))
    built = DB.build_demand(obs_rows, latest_midx=latest_midx, current_midx=current_midx, part_frac=part_frac)
    supply_rows = SB.read_latest_snapshot_rows(reader, dms_sid, scope)
    supply = SB.build_supply(supply_rows, current_month=current_month)
    ctx = PlanningContext(scope=scope, store=store, clock=clock, demand=demand_svc, forecast=forecast_svc,
                          planning=planning_svc, demand_cv=demand_cv, plan_cv=plan_cv, metadata=None)
    res = run_planning(ctx, supply, built["cohorts"], built["exceptions"], target_days_supply=60,
                       current_month=current_month, latest_midx=latest_midx, part_frac=part_frac)
    return res


def _find(res, code, ext, inte):
    return next((o for o in res["outcomes"] if o.issued and o.key[1] == code
                 and o.key[2] == ext and o.key[3] == inte), None)


def assert_board(res, tag):
    """Assert the permanent/dry-run board reproduces the certified real board + the two named regressions."""
    board = dict(target_days_supply=res["target_days_supply"], integer_total_need=res["integer_total_need"],
                 acquire_count=res["acquire_count"],
                 integer_total_excess_arrived=res["integer_total_excess_arrived"],
                 integer_total_excess_incoming=res["integer_total_excess_incoming"])
    P(f"  [{tag}] board = {board}")
    bad = [f"{k}: {board[k]}!={v}" for k, v in CERT_BOARD.items() if board[k] != v]
    qx65 = _find(res, "8501", "QBE", "G")
    if qx65 is None or qx65.acquire_units != 2:
        bad.append(f"QX65 8501 QBE/G ACQUIRE={getattr(qx65,'acquire_units',None)}!=2")
    else:
        P(f"  [{tag}] QX65 8501 QBE/G = ACQUIRE {qx65.acquire_units} (Oct/Nov MONITOR: "
          f"{[mm['month'] for mm in qx65.monitor_months]})")
    qx60 = _find(res, "8481", "XKJ", "K")
    if qx60 is None or qx60.arrived_excess != 3:
        bad.append(f"QX60 8481 XKJ/K ARRIVED_EXCESS={getattr(qx60,'arrived_excess',None)}!=3")
    else:
        rejected = [s for s in (qx60.coverage_evidence or {}).get("excess_trace", []) if s.get("rejected")]
        if not rejected:
            bad.append("QX60 8481 XKJ/K: expected a feasibility-rejected 4th removal, found none")
        else:
            P(f"  [{tag}] QX60 8481 XKJ/K = ARRIVED_EXCESS {qx60.arrived_excess}; "
              f"4th removal REJECTED (Delta={rejected[0]['delta_remove']}, {rejected[0].get('reason','')})")
    if bad:
        raise DeployError(f"{tag} certified-board mismatch: " + "; ".join(bad))
    P(f"  [{tag}] certified real board reproduced.")


def main():
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    ts = time.strftime("%Y%m%d-%H%M%S")
    pre_backup = os.path.join(BACKUP_DIR, f"elite-predeploy-{ts}.db")
    post_backup = os.path.join(BACKUP_DIR, f"elite-postdeploy-{ts}.db")
    tmp = tempfile.mkdtemp(prefix="elite-deploy-")
    mutated = False
    try:
        from elite.db import current_version, Db
        from elite.clock import SystemClock
        from elite.ops.intake import FileIntake, content_hash
        from elite.ops.store import OpsStore

        # ---------- GATES ----------
        P("== GATES ==")
        gate_head_and_tree(root)
        load_env_no_echo(ENVFILE)
        if os.path.abspath(os.environ.get("ELITE_DB_PATH", "")) != os.path.abspath(PERM_EXPECTED):
            raise DeployError(f"ELITE_DB_PATH={os.environ.get('ELITE_DB_PATH')} != {PERM_EXPECTED}")
        if os.path.abspath(PERM) != os.path.abspath(PERM_EXPECTED):
            raise DeployError(f"permanent DB path {PERM} != {PERM_EXPECTED}")
        if not os.path.exists(PERM):
            raise DeployError(f"permanent DB missing: {PERM}")
        verify_sha(STS_FILE, STS_SHA, "Speed-to-Sell workbook")

        # ---------- PERMANENT PRE-STATE (read-only) ----------
        P("== PERMANENT PRE-STATE (read-only) ==")
        ro = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        _check("PERM-pre", _state(ro, current_version), BASE)
        r = ro.execute("SELECT source_id, store_scope FROM import_run WHERE source_contract=? "
                       "AND import_batch_id IS NOT NULL ORDER BY created_at LIMIT 1", (DMS_CONTRACT,)).fetchone()
        if r is None:
            raise DeployError("no DMS inventory snapshot found in the permanent DB")
        dms_sid, scope = r[0], r[1]
        if scope != STORE:
            raise DeployError(f"permanent scope {scope} != {STORE}")
        ro.close()
        P(f"  DMS source={dms_sid} scope={scope}")

        with open(STS_FILE, "rb") as fh:
            payload = fh.read()
        ch = content_hash(payload)
        sts_sid = "src_p11_" + STS_CONTRACT

        # ---------- DRY-RUN on a WAL-consistent COPY (no permanent mutation) ----------
        P("== DRY-RUN on WAL-consistent COPY (permanent DB untouched) ==")
        copy = os.path.join(tmp, "dryrun.db")
        online_backup(PERM, copy)
        cclock = SystemClock()
        cdb = Db(copy, cclock)
        crec = FileIntake(OpsStore(cdb.conn, cclock)).accept(
            filename=os.path.basename(STS_FILE), payload=payload, source_id=sts_sid, scope=scope,
            received_by="permanent-deploy-dryrun")
        dry = _run_engine(cdb.conn, cclock, sts_sid, dms_sid, scope, True, payload, ch, crec["id"])
        assert_board(dry, "DRY-RUN")
        cdb.conn.close()

        # ---------- PRE-DEPLOYMENT BACKUP (+verify) ----------
        P("== PRE-DEPLOYMENT BACKUP ==")
        online_backup(PERM, pre_backup)
        verify_backup(pre_backup, current_version, BASE)

        # ---------- PERMANENT DEPLOYMENT (import once + issue governed plan) ----------
        P("== PERMANENT DEPLOYMENT (import Speed-to-Sell once + issue governed plan) ==")
        clock = SystemClock()
        db = Db(PERM, clock)
        rec = FileIntake(OpsStore(db.conn, clock)).accept(
            filename=os.path.basename(STS_FILE), payload=payload, source_id=sts_sid, scope=scope,
            received_by="permanent-deploy")
        mutated = True
        res = _run_engine(db.conn, clock, sts_sid, dms_sid, scope, True, payload, ch, rec["id"])
        db.conn.commit()
        assert_board(res, "PERMANENT")
        plan_count = db.conn.execute("SELECT COUNT(*) FROM inventory_plan_result WHERE store_scope=? "
                                     "AND status='issued'", (scope,)).fetchone()[0]
        P(f"  issued New-Inventory plans (UI-visible): {plan_count}")

        # ---------- POST-STATE governance (permanent) ----------
        P("== PERMANENT POST-STATE (governance) ==")
        post = _state(db.conn, current_version)
        _check("PERM-post", post, dict(schema=12, facts=0, production_orders=0, vehicle_units=0,
                                       principals=2, active_grants=15))
        sts_rows = res_rowcount(db.conn, sts_sid, scope)
        P(f"  observations: {BASE['observations']} -> {post['observations']} "
          f"(+{post['observations'] - BASE['observations']}; Speed-to-Sell rows retained = {sts_rows})")
        db.conn.close()

        # ---------- POST-DEPLOYMENT BACKUP (+verify) ----------
        P("== POST-DEPLOYMENT BACKUP ==")
        online_backup(PERM, post_backup)
        vro = sqlite3.connect(f"file:{post_backup}?mode=ro", uri=True); vro.row_factory = sqlite3.Row
        _check("POST-BACKUP", _state(vro, current_version),
               dict(schema=12, facts=0, production_orders=0, vehicle_units=0, principals=2, active_grants=15))
        vro.close()

        # ---------- REOPEN PERMANENT READ-ONLY + RE-VERIFY ----------
        P("== REOPEN PERMANENT READ-ONLY (re-verify) ==")
        ro2 = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True); ro2.row_factory = sqlite3.Row
        st2 = _state(ro2, current_version)
        _check("PERM-reopen", st2, dict(schema=12, facts=0, production_orders=0, vehicle_units=0,
                                        principals=2, active_grants=15))
        plans2 = ro2.execute("SELECT COUNT(*) FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                             (scope,)).fetchone()[0]
        ro2.close()
        P(f"  permanent issued plans after reopen: {plans2}")

        P("")
        P("== DEPLOYMENT SUMMARY ==")
        P(f"  INTEGER TOTAL NEED = {res['integer_total_need']} ; acquiring combinations = {res['acquire_count']}")
        P(f"  ARRIVED EXCESS = {res['integer_total_excess_arrived']} ; "
          f"INCOMING EXCESS = {res['integer_total_excess_incoming']}")
        P(f"  issued UI plans = {plans2} ; pre-backup = {pre_backup} ; post-backup = {post_backup}")
        P("  Elite is now Kyle's live DATA_ONLY inventory tool (autonomous external execution NOT enabled).")
        P("PERMANENT DEPLOYMENT PASS - ELITE OPERATIONAL")
        return 0
    except Exception as e:  # noqa: BLE001 - fail closed on anything
        P("")
        P("!! PERMANENT DEPLOYMENT FAILED !!")
        P(f"  reason: {type(e).__name__}: {e}")
        if mutated:
            P(f"  the permanent DB MAY have been partially mutated. DO NOT USE IT. Restore from the")
            P(f"  pre-deployment backup: {pre_backup}")
            P(f"  (restore = stop the app, replace {PERM} with the backup file, restart). No auto-repair performed.")
        else:
            P(f"  permanent DB was NOT mutated (failure happened before deployment).")
            if os.path.exists(pre_backup):
                P(f"  pre-deployment backup (if created) preserved at: {pre_backup}")
        P("PERMANENT DEPLOYMENT FAIL - DO NOT DEPLOY")
        traceback.print_exc()
        return 1


def res_rowcount(conn, sts_sid, scope):
    return conn.execute(
        "SELECT COUNT(*) FROM source_observation o JOIN import_batch b ON o.import_batch_id=b.id "
        "WHERE b.source_id=? AND b.store_scope=?", (sts_sid, scope)).fetchone()[0]


if __name__ == "__main__":
    sys.exit(main())
