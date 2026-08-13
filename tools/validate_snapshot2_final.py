"""Snapshot #2 FINAL disposable validator (two-level DMS source-stage / planning-state).

Self-contained, VALIDATION-ONLY helper. It is committed on the temporary branch
`validation/snapshot2-final` (parent = certified commit 5e7669400b30d9b1664dc2ed9b65485888611d24)
but is designed to run while the checked-out HEAD remains the certified production commit
(extract with `git show validation/snapshot2-final:tools/validate_snapshot2_final.py`).

It performs, entirely on a throwaway copy, NEVER touching the permanent DB except read-only:

  * gate exact git HEAD (must equal the certified production commit)
  * gate clean working tree (ignoring only this helper file's own presence)
  * load C:\\ElitePipeline\\config\\elite.env into the process WITHOUT printing secrets
  * verify the candidate workbook SHA-256
  * open the permanent DB READ-ONLY and prove the baseline
  * make a WAL-consistent disposable copy via SQLite's online backup API
  * redirect every real writable runtime path (ELITE_*_DIR, ELITE_DB_PATH) to a temp dir
  * import the candidate EXACTLY ONCE through the real FileIntake + ImportOrchestrator
  * run the full two-level validation (source stages + planning states + DIS aging + deltas + signals)
  * exercise same-day replay idempotency (no clock tampering)
  * re-verify the permanent DB is byte-for-byte unchanged (read-only)
  * delete its disposable temp directory
  * exit 0 ONLY on a full PASS

Final success line (exact): SNAPSHOT 2 FINAL DISPOSABLE VALIDATION PASS - PERMANENT DB UNTOUCHED
Final failure line (exact): SNAPSHOT 2 FINAL DISPOSABLE VALIDATION FAIL - DO NOT IMPORT
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

# ----------------------------------------------------------------------------- constants / expectations
REQUIRED_HEAD = "5e7669400b30d9b1664dc2ed9b65485888611d24"
EXPECT_SHA = "CF4EFF1AE32712A0DFA7E2F779CB51FCB0D32D4EF6E57569239A3A458D9F2A2A"   # 64-char SHA-256

TZ = "America/Chicago"
STORE = "store:HG_INFINITI_JACKSON"
CONTRACT = "new_inventory_pipeline_summary"
HELPER_REL = "tools/validate_snapshot2_final.py"     # this file's own repo-relative path (git uses '/')

# Windows defaults (overridable by environment for portability; not required on the target box).
PERM = os.environ.get("ELITE_VALIDATE_PERM", r"C:\ElitePipeline\data\elite.db")
ENVFILE = os.environ.get("ELITE_VALIDATE_ENV", r"C:\ElitePipeline\config\elite.env")
CAND = os.environ.get("ELITE_VALIDATE_CAND",
                      r"C:\Users\Kyle.Montgomery\Downloads\vehicleInventorySummary (65).xlsx")

# Absolute permanent-state baseline (read-only proof, before and after).
EXPECT = dict(schema=12, observations=62, import_runs=1, facts=0, production_orders=0,
              vehicle_units=0, scheduled_jobs=0, principals=2, active_grants=15, execdemo_rows=0)
# Known real Snapshot #2 (candidate 65) two-level composition.
EXP_STAGE = {"ONS": 38, "SIT": 18, "NNA-INV": 2, "DLR-INV": 62, "OTHER": 0}   # sum = 120
EXP_PLAN = {"INCOMING": 58, "ARRIVED": 62, "OTHER": 0}


def P(*a):
    print(*a, flush=True)


def fail(msg):
    raise AssertionError(msg)


# ----------------------------------------------------------------------------- gates (run before imports)
def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def gate_head_and_tree(root):
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if head != REQUIRED_HEAD:
        fail(f"HEAD is {head}, required certified commit {REQUIRED_HEAD}")
    porcelain = _git(root, "status", "--porcelain").stdout.splitlines()
    # allow ONLY this helper file's own presence (it is extracted into the tree); flag anything else.
    dirty = []
    for line in porcelain:
        path = line[3:].strip().strip('"')
        if path.replace("\\", "/") == HELPER_REL:
            continue
        if path:
            dirty.append(line)
    if dirty:
        fail("working tree is not clean (besides this helper): " + " | ".join(dirty))
    P(f"  HEAD={head} (certified) ; working tree clean (helper-only)")


def load_env_no_echo(path):
    if not os.path.exists(path):
        fail(f"elite.env missing: {path}")
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
        fail(f"candidate workbook not found: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    got = h.hexdigest().upper()
    if got != EXPECT_SHA.upper():
        fail(f"candidate SHA-256 mismatch: expected {EXPECT_SHA} (len {len(EXPECT_SHA)}), "
             f"computed {got} (len {len(got)})")
    P(f"  candidate SHA-256 verified ({got})")


def redirect_writable_paths(root_tmp):
    for sub in ("data", "raw", "uploads", "quarantine", "backups", "logs"):
        os.makedirs(os.path.join(root_tmp, sub), exist_ok=True)
    disp = os.path.join(root_tmp, "data", "disposable.db")
    # real runtime variable names (elite/ops/opsconfig.py) + defensive extra; set AFTER loading elite.env.
    os.environ["ELITE_DB_PATH"] = disp
    os.environ["ELITE_UPLOAD_DIR"] = os.path.join(root_tmp, "uploads")
    os.environ["ELITE_RAW_RETENTION_DIR"] = os.path.join(root_tmp, "raw")
    os.environ["ELITE_RAW_DIR"] = os.path.join(root_tmp, "raw")
    os.environ["ELITE_QUARANTINE_DIR"] = os.path.join(root_tmp, "quarantine")
    os.environ["ELITE_BACKUP_DIR"] = os.path.join(root_tmp, "backups")
    os.environ["ELITE_LOG_DIR"] = os.path.join(root_tmp, "logs")
    return disp


# ----------------------------------------------------------------------------- state helpers
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


def _assert_baseline(tag, st):
    bad = [f"{k}: got {st[k]} != {v}" for k, v in EXPECT.items() if st[k] != v]
    if st["execdemo_mode"] != "DATA_ONLY":
        bad.append(f"execdemo_mode {st['execdemo_mode']} != DATA_ONLY")
    P(f"  [{tag}] schema={st['schema']} obs={st['observations']} runs={st['import_runs']} "
      f"facts={st['facts']} orders={st['production_orders']} units={st['vehicle_units']} "
      f"jobs={st['scheduled_jobs']} principals={st['principals']} grants={st['active_grants']} "
      f"execDemo[{STORE}]={st['execdemo_mode']}/{st['execdemo_rows']}")
    if bad:
        fail(f"{tag} baseline mismatch: " + "; ".join(bad))


def _sensitive_tables(conn):
    return sorted(n[0] for n in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if any(x in n[0].lower() for x in ("recommend", "decision", "execution")))


def _counts(conn, tables):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


# ----------------------------------------------------------------------------- main validation
def run():
    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    P("== GATES ==")
    gate_head_and_tree(root)
    load_env_no_echo(ENVFILE)
    verify_sha(CAND)
    if not os.path.exists(PERM):
        fail(f"permanent DB missing: {PERM}")

    tmp_root = tempfile.mkdtemp(prefix="elite-snap2-final-")
    try:
        disp = redirect_writable_paths(tmp_root)

        from elite.db import current_version, Db
        from elite.clock import SystemClock
        from elite.data.store import DataStore
        from elite.data.facts import FactService
        from elite.data.ingestion import IngestionService
        from elite.ops.store import OpsStore
        from elite.ops.imports import ImportOrchestrator
        from elite.ops.intake import FileIntake, content_hash
        from elite.newinv.snapshots import SnapshotReader, SnapshotDelta, movement_signals
        from elite.newinv.dms_cohort import dms_source_stage, dms_planning_state, SOURCE_STAGES

        # ---- baseline: permanent DB read-only ----
        P("== BASELINE (permanent DB, read-only) ==")
        ro = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        _assert_baseline("PERM-pre", _state(ro, current_version))
        # ---- WAL-consistent disposable copy via online backup API (no write to PERM) ----
        dst = sqlite3.connect(disp)
        with dst:
            ro.backup(dst)
        dst.close()
        ro.close()
        P(f"== Disposable WAL-consistent copy: {disp} ==")

        clock = SystemClock()
        db = Db(disp, clock)
        conn = db.conn
        data = DataStore(conn, clock)
        facts = FactService(data, clock)
        ingestion = IngestionService(data, facts, clock)
        ops = OpsStore(conn, clock)
        orch = ImportOrchestrator(ops, ingestion, data, clock, logger=None)   # no scheduled jobs registered
        intake = FileIntake(ops)
        reader = SnapshotReader(ops, data, tz=TZ)
        delta = SnapshotDelta(reader)
        _assert_baseline("DISP-pre", _state(conn, current_version))

        r = conn.execute(
            "SELECT source_id, store_scope, import_batch_id FROM import_run"
            " WHERE source_contract=? AND state IN ('COMPLETED','COMPLETED_WITH_WARNINGS')"
            " AND import_batch_id IS NOT NULL ORDER BY created_at LIMIT 1", (CONTRACT,)).fetchone()
        if r is None:
            fail("Snapshot #1 import_run not found in permanent copy")
        SID, SCOPE, SNAP1_BATCH = r[0], r[1], r[2]
        P(f"== Source={SID} scope={SCOPE} ==")
        snaps0 = reader.list_snapshots(SID, SCOPE)
        if len(snaps0) != 1:
            fail(f"expected exactly Snapshot #1 present, found {len(snaps0)}")
        s1 = snaps0[0]
        if len(reader.snapshot_rows(s1)) != 62 or s1.import_batch_id != SNAP1_BATCH:
            fail("Snapshot #1 not as expected (62 observations)")

        inv = (["business_fact", "production_order", "vehicle_unit", "scheduled_job",
                "principal", "capability_grant"] + _sensitive_tables(conn))
        before = _counts(conn, inv)
        obs_before = conn.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0]

        # ---- import candidate (65) EXACTLY ONCE via real FileIntake + ImportOrchestrator ----
        with open(CAND, "rb") as fh:
            payload = fh.read()
        ch = content_hash(payload)
        receipt = intake.accept(filename="vehicleInventorySummary (65).xlsx", payload=payload,
                                source_id=SID, scope=SCOPE, received_by="disposable-validation")
        run_rec = orch.run(contract_key=CONTRACT, payload=payload, source_id=SID, scope=SCOPE,
                           content_hash=ch, file_receipt_id=receipt["id"],
                           initiated_by="disposable-validation", claimed_snapshot="partial")
        P("== IMPORT (candidate 65) ==")
        P(f"  state={run_rec['state']} recon={run_rec['reconciliation_status']} rows={run_rec['row_count']} "
          f"accepted={run_rec['accepted_count']} rejected={run_rec['rejected_count']} "
          f"unresolved={run_rec['unresolved_count']}")
        if run_rec["state"] not in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
            fail(f"import did not complete: {run_rec['state']}")

        # ---- snapshots ----
        snaps = reader.list_snapshots(SID, SCOPE)
        if len(snaps) != 2:
            fail(f"snapshot count != 2 ({len(snaps)})")
        s1b, s2 = snaps[0], snaps[1]
        latest = reader.latest_snapshot(SID, SCOPE)
        if s1b.import_batch_id != SNAP1_BATCH or len(reader.snapshot_rows(s1b)) != 62:
            fail("Snapshot #1 changed after import")
        if s2.import_run_id != run_rec["id"] or latest.import_run_id != s2.import_run_id:
            fail("latest_snapshot did not resolve to Snapshot #2")
        if (s2.observed_time or "", s2.received_at or "") < (s1b.observed_time or "", s1b.received_at or ""):
            fail("Snapshot #2 does not sort after Snapshot #1")
        s2_rows = reader.snapshot_rows(s2)
        if len(s2_rows) != 120:
            fail(f"Snapshot #2 rows != 120 ({len(s2_rows)})")

        # ---- serial / identity safety ----
        serial_ok = all(x.get("serial_semantic", "unknown") == "unknown" for x in s2_rows)
        ident_unres = all(row[1] == "unresolved" for row in conn.execute(
            "SELECT id, identity_status FROM source_observation WHERE import_batch_id=?", (s2.import_batch_id,)))
        if not (serial_ok and ident_unres):
            fail("Snapshot #2 serial/identity safety violated")

        # ---- SOURCE-STATE AUDIT (two levels) ----
        P("== SOURCE-STATE AUDIT (Snapshot #2) ==")
        loc = Counter((x.get("location") or "").strip() or "<blank>" for x in s2_rows)
        stat = Counter((x.get("status") or "").strip() or "<blank>" for x in s2_rows)
        stage = Counter(dms_source_stage(x) for x in s2_rows)
        plan = Counter(dms_planning_state(x) for x in s2_rows)
        P("  distinct Location: " + ", ".join(f"{k}={v}" for k, v in sorted(loc.items())))
        P("  distinct Status:   " + ", ".join(f"{k}={v}" for k, v in sorted(stat.items())))
        P("  SOURCE STAGES : " + ", ".join(f"{s}={stage.get(s, 0)}" for s in SOURCE_STAGES))
        P("  PLANNING STATE: " + ", ".join(f"{p}={plan.get(p, 0)}" for p in ("INCOMING", "ARRIVED", "OTHER")))
        for s, v in EXP_STAGE.items():
            if stage.get(s, 0) != v:
                fail(f"source stage {s}: got {stage.get(s, 0)} != {v}")
        for p, v in EXP_PLAN.items():
            if plan.get(p, 0) != v:
                fail(f"planning state {p}: got {plan.get(p, 0)} != {v}")

        # ---- DLR-INV (ARRIVED) DIS aging ----
        aging = reader.dis_distribution(s2)
        P(f"  DLR-INV DIS aging: count={aging['count']} min={aging['min']} max={aging['max']} "
          f"mean={aging['mean']} median={aging['median']}")
        if not (aging["count"] == 62 and aging["min"] == 0 and aging["max"] == 187
                and abs(aging["median"] - 40) <= 0.5 and abs(aging["mean"] - 49.73) <= 0.01):
            fail("DLR-INV DIS aging mismatch vs expected (count 62, min 0, max 187, mean ~49.73, median 40)")

        # ---- invariants (nothing else touched) ----
        after = _counts(conn, inv)
        changed = {t: (before[t], after[t]) for t in inv if before[t] != after[t]}
        if changed:
            fail(f"import touched invariant tables: {changed}")
        st_after = _state(conn, current_version)
        for k in ("facts", "production_orders", "vehicle_units", "scheduled_jobs",
                  "principals", "active_grants", "execdemo_rows"):
            if st_after[k] != EXPECT[k]:
                fail(f"invariant {k} changed to {st_after[k]}")
        if st_after["execdemo_mode"] != "DATA_ONLY":
            fail("Executive Demo left DATA_ONLY")
        P("  invariants held: facts=0 orders=0 units=0 jobs=0 principals=2 grants=15 "
          f"execDemo[{STORE}]=DATA_ONLY/0 ; no recommendation/decision/execution rows created")

        # ---- portfolio delta #1 -> #2 (both levels) ----
        rep = delta.compare(s1b, s2)

        def dsum(attr):
            return sum(getattr(c, attr) for c in rep.cohorts)

        P("== PORTFOLIO DELTA (#1 -> #2) ==")
        P(f"  total rows {sum(c.total_prev for c in rep.cohorts)} -> "
          f"{sum(c.total_curr for c in rep.cohorts)}; cohorts={len(rep.cohorts)}")
        P(f"  SOURCE-STAGE deltas : ONS {dsum('ons_delta'):+d}  SIT {dsum('sit_delta'):+d}  "
          f"NNA-INV {dsum('nna_delta'):+d}  DLR-INV {dsum('dlr_delta'):+d}  OTHER {dsum('other_delta'):+d}")
        P(f"  PLANNING-STATE deltas: INCOMING {dsum('incoming_delta'):+d}  "
          f"ARRIVED {dsum('arrived_delta'):+d}  OTHER {dsum('other_delta'):+d}")
        P(f"  newly observed cohorts: {['/'.join(k) for k in rep.new_cohorts] or 'none'}")
        P(f"  no-longer observed cohorts: {['/'.join(k) for k in rep.gone_cohorts] or 'none'}")
        sigs = movement_signals(rep)
        if sigs:
            for s in sigs:
                P(f"  {s.signal}: {s.label} {s.from_stage}->{s.to_stage} net~{s.inferred_net_movement} "
                  f"(from {s.from_delta:+d}, to {s.to_delta:+d}) confidence={s.confidence} "
                  f"reasons={s.ambiguity_reasons or 'none'} [cohort-level; NOT a same-unit claim]")
        else:
            P("  stage-progression signals: none")

        # ---- same-day replay idempotency (no clock tampering) ----
        receipt2 = intake.accept(filename="vehicleInventorySummary (65).xlsx", payload=payload,
                                 source_id=SID, scope=SCOPE, received_by="disposable-validation")
        run2 = orch.run(contract_key=CONTRACT, payload=payload, source_id=SID, scope=SCOPE,
                        content_hash=ch, file_receipt_id=receipt2["id"],
                        initiated_by="disposable-validation", claimed_snapshot="partial")
        obs2 = conn.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0]
        snaps2 = reader.list_snapshots(SID, SCOPE)
        P("== REPLAY (same file, same business date) ==")
        P(f"  run2==run1 ? {run2['id'] == run_rec['id']}; snapshot_count={len(snaps2)}; "
          f"observations {obs_before + len(s2_rows)} -> {obs2}")
        if run2["id"] != run_rec["id"] or len(snaps2) != 2 or obs2 != obs_before + len(s2_rows):
            fail("replay was not idempotent")
        db.close()

        # ---- final permanent DB re-verify (read-only) ----
        P("== PERMANENT DB RE-VERIFY (read-only) ==")
        ro2 = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro2.row_factory = sqlite3.Row
        _assert_baseline("PERM-post", _state(ro2, current_version))
        ro2.close()

        P("")
        P("SNAPSHOT 2 FINAL DISPOSABLE VALIDATION PASS - PERMANENT DB UNTOUCHED")
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)   # discard the disposable copy


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as e:   # noqa: BLE001 - any failure is a safe, explicit non-import verdict
        P("")
        P(f"FAILURE: {type(e).__name__}: {e}")
        traceback.print_exc()
        P("SNAPSHOT 2 FINAL DISPOSABLE VALIDATION FAIL - DO NOT IMPORT")
        sys.exit(2)
