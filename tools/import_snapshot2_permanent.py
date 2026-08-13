"""Snapshot #2 PERMANENT import helper (governed, backup-bracketed, one-shot).

Self-contained helper committed on the temporary branch `validation/snapshot2-permanent`
(parent = certified commit 5e7669400b30d9b1664dc2ed9b65485888611d24). It is designed to run
while the checked-out Windows HEAD remains the certified production commit (extract with
`git show validation/snapshot2-permanent:tools/import_snapshot2_permanent.py`).

It performs the PERMANENT Snapshot #2 operation against the real permanent DB, exactly once,
with a verified backup taken before AND after the write. Unlike the disposable validator this
writes to the permanent store — every gate below must pass BEFORE any import write occurs.

Sequence:
  GATES (no write): HEAD == certified ; clean tree (helper-only) ; load elite.env (no secret echo) ;
    resolve + require scope store:HG_INFINITI_JACKSON ; verify workbook SHA-256 ; permanent baseline
    (schema 12 / 62 obs / 1 run / 0 facts,orders,units,jobs / 2 principals / 15 grants / DATA_ONLY /
    exactly one snapshot / Snapshot #1 == 62) ; confirm (65) not already a completed Snapshot #2.
  PRE-IMPORT RECOVERY GATE: one shipped BackupService backup + validate_restore, all criteria true;
    otherwise STOP before import.
  IMPORT: candidate (65) exactly once via real FileIntake + ImportOrchestrator (no scheduled jobs,
    no recommendations, no shadow change, no accounts/grants, no orders/units/facts).
  POST-IMPORT ASSERTIONS: 182 obs / 2 runs / 2 snapshots ; Snapshot #1 == 62 unchanged ; Snapshot #2
    == 120 latest ; source stages ONS 38/SIT 18/NNA-INV 2/DLR-INV 62/OTHER 0 ; planning INCOMING 58/
    ARRIVED 62/OTHER 0 ; DLR-INV DIS 62 / 0..187 / mean ~49.73 / median 40 ; serial unknown ; identities
    unresolved ; invariants held ; no recommendation/decision/execution rows.
  POST-IMPORT BACKUP: a second verified backup + validate_restore of the new state.
  FINAL REOPEN: close, reopen read-only, re-verify final state; print both backup ids/artifacts.

Verdict lines (exact):
  success             : SNAPSHOT 2 PERMANENT IMPORT PASS - 2 SNAPSHOTS / 182 OBSERVATIONS / VERIFIED BACKUP
  failure before write: SNAPSHOT 2 PERMANENT IMPORT GATE FAIL - NO IMPORT PERFORMED
  failure after write : SNAPSHOT 2 PERMANENT IMPORT POSTCHECK FAIL - STOP / DO NOT RETRY
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from collections import Counter

REQUIRED_HEAD = "5e7669400b30d9b1664dc2ed9b65485888611d24"
EXPECT_SHA = "CF4EFF1AE32712A0DFA7E2F779CB51FCB0D32D4EF6E57569239A3A458D9F2A2A"   # 64-char SHA-256

TZ = "America/Chicago"
STORE = "store:HG_INFINITI_JACKSON"
CONTRACT = "new_inventory_pipeline_summary"
HELPER_REL = "tools/import_snapshot2_permanent.py"

ENVFILE = os.environ.get("ELITE_IMPORT_ENV", r"C:\ElitePipeline\config\elite.env")
CAND = os.environ.get("ELITE_IMPORT_CAND",
                      r"C:\Users\Kyle.Montgomery\Downloads\vehicleInventorySummary (65).xlsx")
DEFAULT_PERM = r"C:\ElitePipeline\data\elite.db"
DEFAULT_BACKUP_DIR = r"C:\ElitePipeline\backups"

# permanent-state baseline BEFORE import
BASE = dict(schema=12, observations=62, import_runs=1, facts=0, production_orders=0,
            vehicle_units=0, scheduled_jobs=0, principals=2, active_grants=15, execdemo_rows=0)
# permanent-state expectation AFTER import
POST = dict(BASE, observations=182, import_runs=2)
# known real Snapshot #2 composition
EXP_STAGE = {"ONS": 38, "SIT": 18, "NNA-INV": 2, "DLR-INV": 62, "OTHER": 0}   # sum = 120
EXP_PLAN = {"INCOMING": 58, "ARRIVED": 62, "OTHER": 0}

_IMPORTED = False   # set True the instant the permanent import write completes (phase classifier)


def P(*a):
    print(*a, flush=True)


class GateError(Exception):
    """Raised for a failure BEFORE any permanent write (safe: no import performed)."""


class PostError(Exception):
    """Raised for a failure AFTER the permanent write (import may already be permanent)."""


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def gate_head_and_tree(root):
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if head != REQUIRED_HEAD:
        raise GateError(f"HEAD is {head}, required certified commit {REQUIRED_HEAD}")
    dirty = []
    for line in _git(root, "status", "--porcelain").stdout.splitlines():
        path = line[3:].strip().strip('"')
        if path.replace("\\", "/") == HELPER_REL:
            continue
        if path:
            dirty.append(line)
    if dirty:
        raise GateError("working tree not clean (besides this helper): " + " | ".join(dirty))
    P(f"  HEAD={head} (certified) ; working tree clean (helper-only)")


def load_env_no_echo(path):
    if not os.path.exists(path):
        raise GateError(f"elite.env missing: {path}")
    n = 0
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"')
            n += 1
    P(f"  loaded elite.env ({n} keys; values not printed)")


def verify_sha(path):
    if not os.path.exists(path):
        raise GateError(f"candidate workbook not found: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    got = h.hexdigest().upper()
    if got != EXPECT_SHA.upper():
        raise GateError(f"candidate SHA-256 mismatch: expected {EXPECT_SHA} (len {len(EXPECT_SHA)}), "
                        f"computed {got} (len {len(got)})")
    P(f"  candidate SHA-256 verified ({got})")


def _state(conn, current_version):
    c = lambda q: conn.execute(q).fetchone()[0]
    row = conn.execute("SELECT mode FROM domain_shadow_mode WHERE domain='executive_demo'"
                       " AND store_scope=? ORDER BY recorded_at DESC LIMIT 1", (STORE,)).fetchone()
    ex = conn.execute("SELECT COUNT(*) FROM domain_shadow_mode WHERE domain='executive_demo'"
                      " AND store_scope=?", (STORE,)).fetchone()[0]
    return dict(schema=current_version(conn),
                observations=c("SELECT COUNT(*) FROM source_observation"),
                import_runs=c("SELECT COUNT(*) FROM import_run"),
                facts=c("SELECT COUNT(*) FROM business_fact"),
                production_orders=c("SELECT COUNT(*) FROM production_order"),
                vehicle_units=c("SELECT COUNT(*) FROM vehicle_unit"),
                scheduled_jobs=c("SELECT COUNT(*) FROM scheduled_job"),
                principals=c("SELECT COUNT(*) FROM principal"),
                active_grants=c("SELECT COUNT(*) FROM capability_grant WHERE active=1"),
                execdemo_rows=ex, execdemo_mode=(row[0] if row else "DATA_ONLY"))


def _check_state(tag, st, expect, err):
    bad = [f"{k}: got {st[k]} != {v}" for k, v in expect.items() if st[k] != v]
    if st["execdemo_mode"] != "DATA_ONLY":
        bad.append(f"execdemo_mode {st['execdemo_mode']} != DATA_ONLY")
    P(f"  [{tag}] schema={st['schema']} obs={st['observations']} runs={st['import_runs']} "
      f"facts={st['facts']} orders={st['production_orders']} units={st['vehicle_units']} "
      f"jobs={st['scheduled_jobs']} principals={st['principals']} grants={st['active_grants']} "
      f"execDemo[{STORE}]={st['execdemo_mode']}/{st['execdemo_rows']}")
    if bad:
        raise err(f"{tag} state mismatch: " + "; ".join(bad))


def _sensitive_tables(conn):
    return sorted(n[0] for n in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if any(x in n[0].lower() for x in ("recommend", "decision", "execution")))


def _counts(conn, tables):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def _verify_backup(backup, ops_get, dest_dir, tmp_restores, label):
    """Create one backup + validate a restore; require every criterion true. Returns (id, artifact)."""
    rec = backup.create_backup(dest_dir)
    rdir = tempfile.mkdtemp(prefix="elite-restore-")
    tmp_restores.append(rdir)
    rv = backup.validate_restore(rec["id"], rdir)
    P(f"  [{label}] backup id={rec['id']} status={rec['status']} integrity={rec['integrity_verified']} "
      f"artifact={rec['artifact_ref']}")
    P(f"  [{label}] restore started={rv['started_ok']} version_matched={rv['migration_version_matched']} "
      f"counts_matched={rv['counts_matched']}")
    ok = (rec["status"] == "verified" and rec["integrity_verified"] == 1
          and rv["started_ok"] == 1 and rv["migration_version_matched"] == 1 and rv["counts_matched"] == 1)
    return rec, rv, ok


def run():
    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    global _IMPORTED
    tmp_restores = []
    try:
        # ---------------------------------------------------------------- GATES (no write)
        P("== GATES (no write) ==")
        gate_head_and_tree(root)
        load_env_no_echo(ENVFILE)
        verify_sha(CAND)
        PERM = os.environ.get("ELITE_DB_PATH") or DEFAULT_PERM
        BK = os.environ.get("ELITE_BACKUP_DIR") or DEFAULT_BACKUP_DIR
        if not os.path.exists(PERM):
            raise GateError(f"permanent DB missing: {PERM}")

        from elite.db import current_version, Db
        from elite.clock import SystemClock
        from elite.data.store import DataStore
        from elite.data.facts import FactService
        from elite.data.ingestion import IngestionService
        from elite.ops.store import OpsStore
        from elite.ops.imports import ImportOrchestrator
        from elite.ops.intake import FileIntake, content_hash
        from elite.ops.backup import BackupService
        from elite.newinv.snapshots import SnapshotReader, SnapshotDelta, movement_signals
        from elite.newinv.dms_cohort import dms_source_stage, dms_planning_state, SOURCE_STAGES

        # baseline: permanent DB read-only
        P("== PERMANENT BASELINE (read-only) ==")
        ro = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        _check_state("PERM-pre", _state(ro, current_version), BASE, GateError)
        ro.close()

        # open the real permanent DB (no migrate; already v12), build the real services
        clock = SystemClock()
        db = Db(PERM, clock)
        conn = db.conn
        data = DataStore(conn, clock)
        facts = FactService(data, clock)
        ingestion = IngestionService(data, facts, clock)
        ops = OpsStore(conn, clock)
        orch = ImportOrchestrator(ops, ingestion, data, clock, logger=None)   # no scheduled jobs registered
        intake = FileIntake(ops)
        reader = SnapshotReader(ops, data, tz=TZ)
        delta = SnapshotDelta(reader)
        backup = BackupService(db, ops, clock, logger=None)                    # shipped backup mechanism

        # resolve source + scope from existing lineage; require exact store
        r = conn.execute(
            "SELECT source_id, store_scope, import_batch_id FROM import_run"
            " WHERE source_contract=? AND state IN ('COMPLETED','COMPLETED_WITH_WARNINGS')"
            " AND import_batch_id IS NOT NULL ORDER BY created_at LIMIT 1", (CONTRACT,)).fetchone()
        if r is None:
            raise GateError("no completed Snapshot #1 import_run found for the contract")
        SID, SCOPE, SNAP1_BATCH = r[0], r[1], r[2]
        if SCOPE != STORE:
            raise GateError(f"resolved scope {SCOPE} != required {STORE}")
        P(f"  source={SID} scope={SCOPE} (== {STORE})")

        snaps0 = reader.list_snapshots(SID, SCOPE)
        if len(snaps0) != 1:
            raise GateError(f"expected exactly one valid inventory snapshot, found {len(snaps0)}")
        if len(reader.snapshot_rows(snaps0[0])) != 62 or snaps0[0].import_batch_id != SNAP1_BATCH:
            raise GateError("Snapshot #1 does not have exactly 62 observations")

        # confirm the candidate is NOT already a completed permanent Snapshot #2
        with open(CAND, "rb") as fh:
            payload = fh.read()
        ch = content_hash(payload)
        if ops.find_import_run_by_hash(SID, SCOPE, ch) is not None:
            raise GateError("candidate (65) is already present as a completed import — refusing to re-import")

        # capture invariant baselines (compared again post-import)
        inv = (["business_fact", "production_order", "vehicle_unit", "scheduled_job",
                "principal", "capability_grant"] + _sensitive_tables(conn))
        before_inv = _counts(conn, inv)
        obs_before = conn.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0]

        # ---------------------------------------------------------------- PRE-IMPORT RECOVERY GATE
        P("== PRE-IMPORT VERIFIED BACKUP (recovery gate) ==")
        rec_pre, rv_pre, ok_pre = _verify_backup(backup, ops.get_backup, BK, tmp_restores, "PRE")
        if not ok_pre:
            raise GateError("pre-import backup did not fully verify — STOP before import")

        # ---------------------------------------------------------------- PERMANENT IMPORT (one write)
        P("== PERMANENT IMPORT (candidate 65, exactly once) ==")
        receipt = intake.accept(filename="vehicleInventorySummary (65).xlsx", payload=payload,
                                source_id=SID, scope=SCOPE, received_by="permanent-import")
        run_rec = orch.run(contract_key=CONTRACT, payload=payload, source_id=SID, scope=SCOPE,
                           content_hash=ch, file_receipt_id=receipt["id"],
                           initiated_by="permanent-import", claimed_snapshot="partial")
        _IMPORTED = True   # from here on, any failure is a POST-import failure
        P(f"  state={run_rec['state']} recon={run_rec['reconciliation_status']} rows={run_rec['row_count']} "
          f"accepted={run_rec['accepted_count']} rejected={run_rec['rejected_count']} "
          f"unresolved={run_rec['unresolved_count']}")
        if run_rec["state"] not in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
            raise PostError(f"import did not complete: {run_rec['state']}")

        # ---------------------------------------------------------------- POST-IMPORT ASSERTIONS
        P("== POST-IMPORT ASSERTIONS ==")
        _check_state("PERM-post", _state(conn, current_version), POST, PostError)
        snaps = reader.list_snapshots(SID, SCOPE)
        if len(snaps) != 2:
            raise PostError(f"snapshot count != 2 ({len(snaps)})")
        s1b, s2 = snaps[0], snaps[1]
        latest = reader.latest_snapshot(SID, SCOPE)
        if s1b.import_batch_id != SNAP1_BATCH or len(reader.snapshot_rows(s1b)) != 62:
            raise PostError("Snapshot #1 changed after import")
        if s2.import_run_id != run_rec["id"] or latest.import_run_id != s2.import_run_id:
            raise PostError("latest_snapshot did not resolve to Snapshot #2")
        s2_rows = reader.snapshot_rows(s2)
        if len(s2_rows) != 120:
            raise PostError(f"Snapshot #2 rows != 120 ({len(s2_rows)})")

        serial_ok = all(x.get("serial_semantic", "unknown") == "unknown" for x in s2_rows)
        ident_unres = all(row[1] == "unresolved" for row in conn.execute(
            "SELECT id, identity_status FROM source_observation WHERE import_batch_id=?", (s2.import_batch_id,)))
        if not (serial_ok and ident_unres):
            raise PostError("Snapshot #2 serial/identity safety violated")

        stage = Counter(dms_source_stage(x) for x in s2_rows)
        plan = Counter(dms_planning_state(x) for x in s2_rows)
        P("  SOURCE STAGES : " + ", ".join(f"{s}={stage.get(s, 0)}" for s in SOURCE_STAGES))
        P("  PLANNING STATE: " + ", ".join(f"{p}={plan.get(p, 0)}" for p in ("INCOMING", "ARRIVED", "OTHER")))
        for s, v in EXP_STAGE.items():
            if stage.get(s, 0) != v:
                raise PostError(f"source stage {s}: got {stage.get(s, 0)} != {v}")
        for p, v in EXP_PLAN.items():
            if plan.get(p, 0) != v:
                raise PostError(f"planning state {p}: got {plan.get(p, 0)} != {v}")

        aging = reader.dis_distribution(s2)
        P(f"  DLR-INV DIS aging: count={aging['count']} min={aging['min']} max={aging['max']} "
          f"mean={aging['mean']} median={aging['median']}")
        if not (aging["count"] == 62 and aging["min"] == 0 and aging["max"] == 187
                and abs(aging["median"] - 40) <= 0.5 and abs(aging["mean"] - 49.73) <= 0.01):
            raise PostError("DLR-INV DIS aging mismatch vs expected (62 / 0..187 / ~49.73 / 40)")

        after_inv = _counts(conn, inv)
        changed = {t: (before_inv[t], after_inv[t]) for t in inv if before_inv[t] != after_inv[t]}
        if changed:
            raise PostError(f"import touched invariant tables: {changed}")
        obs_after = conn.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0]
        if obs_after != obs_before + 120:
            raise PostError(f"observation delta != 120 ({obs_before} -> {obs_after})")
        P("  invariants held: facts=0 orders=0 units=0 jobs=0 principals=2 grants=15 "
          f"execDemo[{STORE}]=DATA_ONLY/0 ; no recommendation/decision/execution rows created")

        # portfolio delta (informational)
        rep = delta.compare(s1b, s2)

        def dsum(a):
            return sum(getattr(c, a) for c in rep.cohorts)

        P("== PORTFOLIO DELTA (#1 -> #2) ==")
        P(f"  SOURCE-STAGE deltas : ONS {dsum('ons_delta'):+d}  SIT {dsum('sit_delta'):+d}  "
          f"NNA-INV {dsum('nna_delta'):+d}  DLR-INV {dsum('dlr_delta'):+d}  OTHER {dsum('other_delta'):+d}")
        P(f"  PLANNING-STATE deltas: INCOMING {dsum('incoming_delta'):+d}  "
          f"ARRIVED {dsum('arrived_delta'):+d}  OTHER {dsum('other_delta'):+d}")
        for s in movement_signals(rep):
            P(f"  {s.signal}: {s.label} {s.from_stage}->{s.to_stage} net~{s.inferred_net_movement} "
              f"confidence={s.confidence} reasons={s.ambiguity_reasons or 'none'} "
              f"[cohort-level; NOT a same-unit claim]")

        # ---------------------------------------------------------------- POST-IMPORT VERIFIED BACKUP
        P("== POST-IMPORT VERIFIED BACKUP ==")
        rec_post, rv_post, ok_post = _verify_backup(backup, ops.get_backup, BK, tmp_restores, "POST")
        if not ok_post:
            raise PostError("post-import backup did not fully verify")

        db.close()

        # ---------------------------------------------------------------- FINAL REOPEN (read-only)
        P("== FINAL REOPEN (read-only) ==")
        ro2 = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro2.row_factory = sqlite3.Row
        _check_state("PERM-final", _state(ro2, current_version), POST, PostError)
        rdata = DataStore(ro2, clock)
        rreader = SnapshotReader(OpsStore(ro2, clock), rdata, tz=TZ)
        fsnaps = rreader.list_snapshots(SID, SCOPE)
        if len(fsnaps) != 2:
            raise PostError(f"final snapshot count != 2 ({len(fsnaps)})")
        ro2.close()

        P("== BACKUP ARTIFACTS ==")
        P(f"  PRE-IMPORT  backup id={rec_pre['id']}  artifact={rec_pre['artifact_ref']}")
        P(f"  POST-IMPORT backup id={rec_post['id']}  artifact={rec_post['artifact_ref']}")

        P("")
        P("SNAPSHOT 2 PERMANENT IMPORT PASS - 2 SNAPSHOTS / 182 OBSERVATIONS / VERIFIED BACKUP")
        return 0
    finally:
        for d in tmp_restores:
            shutil.rmtree(d, ignore_errors=True)   # throwaway restore-validation copies only


if __name__ == "__main__":
    try:
        code = run()
        sys.exit(code)
    except GateError as e:
        P("")
        P(f"GATE FAILURE (before import): {e}")
        P("SNAPSHOT 2 PERMANENT IMPORT GATE FAIL - NO IMPORT PERFORMED")
        sys.exit(1)
    except PostError as e:
        P("")
        P(f"POST-IMPORT FAILURE: {e}")
        P("The import may already be permanent. DO NOT retry automatically; inspect the permanent DB.")
        P("SNAPSHOT 2 PERMANENT IMPORT POSTCHECK FAIL - STOP / DO NOT RETRY")
        sys.exit(2)
    except Exception as e:   # noqa: BLE001 - unknown failure; classify by whether the write happened
        P("")
        P(f"UNEXPECTED FAILURE: {type(e).__name__}: {e}")
        traceback.print_exc()
        if _IMPORTED:
            P("The import may already be permanent. DO NOT retry automatically; inspect the permanent DB.")
            P("SNAPSHOT 2 PERMANENT IMPORT POSTCHECK FAIL - STOP / DO NOT RETRY")
            sys.exit(2)
        P("SNAPSHOT 2 PERMANENT IMPORT GATE FAIL - NO IMPORT PERFORMED")
        sys.exit(1)
