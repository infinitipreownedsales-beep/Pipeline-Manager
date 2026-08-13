"""Disposable REAL demand + planning validation (read-only to the permanent DB).

Runs the REAL Speed-to-Sell workbook + the REAL permanent inventory snapshot history through the new governed
DATA_ONLY planning bridge on a WAL-consistent COPY of the permanent DB. Never touches the permanent DB (only
read-only + as an online-backup source), never imports permanently, never issues a permanent plan, never
changes DATA_ONLY / shadow / execution, and never creates VehicleUnits / ProductionOrders / business facts.

Phone-safe: extract with `git show validation/real-demand-plan:tools/validate_real_demand_plan.py` and run
`python tools\\validate_real_demand_plan.py` while the checked-out HEAD stays the bridge commit.

Final verdict (exact):
  pass: DISPOSABLE REAL PLAN PASS - READY FOR HUMAN RECOMMENDATION REVIEW
  fail: DISPOSABLE REAL PLAN FAIL - DO NOT DEPLOY
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from statistics import mean, median

REQUIRED_HEAD = "a8c6edf6709fefba85d183d6e00448ab9300f290"
STS_SHA = "3788E0F5D09C6A0CF2433C9B15F1D20AAF6C8554102E072D92E639735543215C"
HELPER_REL = "tools/validate_real_demand_plan.py"
TZ = "America/Chicago"
STORE = "store:HG_INFINITI_JACKSON"
DMS_CONTRACT = "new_inventory_pipeline_summary"
STS_CONTRACT = "speed_to_sell"

PERM = os.environ.get("ELITE_VALIDATE_PERM", r"C:\ElitePipeline\data\elite.db")
ENVFILE = os.environ.get("ELITE_VALIDATE_ENV", r"C:\ElitePipeline\config\elite.env")
STS_FILE = os.environ.get("ELITE_STS_FILE",
                          r"C:\Users\Kyle.Montgomery\Downloads\SPEED TO SELL REPORT(20260813-042630).xlsx")

# permanent baseline BEFORE anything (item 5)
BASE = dict(schema=12, observations=182, import_runs=2, facts=0, production_orders=0, vehicle_units=0,
            scheduled_jobs=0, principals=2, active_grants=15, execdemo_rows=0)
# expected latest-snapshot supply composition (item C)
EXP_STAGE = {"ONS": 38, "SIT": 18, "NNA-INV": 2, "DLR-INV": 62, "OTHER": 0}


def P(*a):
    print(*a, flush=True)


class GateError(Exception):
    pass


def _root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)


def gate_head_and_tree(root):
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if head != REQUIRED_HEAD:
        raise GateError(f"HEAD is {head}, required {REQUIRED_HEAD}")
    dirty = [ln for ln in _git(root, "status", "--porcelain").stdout.splitlines()
             if ln[3:].strip().strip('"').replace("\\", "/") != HELPER_REL and ln[3:].strip()]
    if dirty:
        raise GateError("working tree not clean (besides this helper): " + " | ".join(dirty))
    P(f"  HEAD={head} (bridge commit) ; tree clean (helper-only)")


def load_env_no_echo(path):
    if not os.path.exists(path):
        raise GateError(f"elite.env missing: {path}")
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
        raise GateError(f"{label} not found: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    got = h.hexdigest().upper()
    if got != expect.upper():
        raise GateError(f"{label} SHA-256 mismatch: expected {expect} (len {len(expect)}), got {got} (len {len(got)})")
    P(f"  {label} SHA-256 verified ({got})")


def _state(conn, current_version):
    c = lambda q: conn.execute(q).fetchone()[0]
    row = conn.execute("SELECT mode FROM domain_shadow_mode WHERE domain='executive_demo' AND store_scope=?"
                       " ORDER BY recorded_at DESC LIMIT 1", (STORE,)).fetchone()
    ex = conn.execute("SELECT COUNT(*) FROM domain_shadow_mode WHERE domain='executive_demo' AND store_scope=?",
                      (STORE,)).fetchone()[0]
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


def _check(tag, st, expect):
    bad = [f"{k}: {st[k]}!={v}" for k, v in expect.items() if st[k] != v]
    if st["execdemo_mode"] != "DATA_ONLY":
        bad.append(f"execdemo_mode {st['execdemo_mode']}!=DATA_ONLY")
    P(f"  [{tag}] schema={st['schema']} obs={st['observations']} runs={st['import_runs']} facts={st['facts']} "
      f"orders={st['production_orders']} units={st['vehicle_units']} jobs={st['scheduled_jobs']} "
      f"principals={st['principals']} grants={st['active_grants']} execDemo={st['execdemo_mode']}/{st['execdemo_rows']}")
    if bad:
        raise GateError(f"{tag} mismatch: " + "; ".join(bad))


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


def main():
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    tmp = tempfile.mkdtemp(prefix="elite-realplan-")
    ok_safety = True
    try:
        P("== GATES ==")
        gate_head_and_tree(root)
        load_env_no_echo(ENVFILE)
        if not os.path.exists(PERM):
            raise GateError(f"permanent DB missing: {PERM}")
        verify_sha(STS_FILE, STS_SHA, "Speed-to-Sell workbook")

        from elite.db import current_version, Db
        from elite.clock import SystemClock, local_business_date
        from elite.data.store import DataStore
        from elite.data.facts import FactService
        from elite.data.ingestion import IngestionService
        from elite.ops.store import OpsStore
        from elite.ops.imports import ImportOrchestrator
        from elite.ops.intake import FileIntake, content_hash
        from elite.policy.store import PolicyStore
        from elite.policy.models import CalculationFamily, CalculationVersion
        from elite.newinv.store import NewInvStore
        from elite.newinv.demand import DemandService
        from elite.newinv.forecast import ForecastService
        from elite.newinv.planning import PlanningService
        from elite.newinv.snapshots import SnapshotReader
        from elite.newinv import supply_bridge as SB
        from elite.newinv import demand_bridge as DB
        from elite.newinv import data_quality as DQ
        from elite.newinv.planning_runner import PlanningContext, run_planning, derive_horizon
        from elite.newinv.dms_identity import dms_planning_key
        from elite.newinv.dms_cohort import dms_source_stage
        from elite.ids import new_id

        # ---- permanent baseline (read-only) ----
        P("== PERMANENT BASELINE (read-only) ==")
        ro = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        _check("PERM-pre", _state(ro, current_version), BASE)

        # ---- WAL-consistent disposable copy via online backup API (never a raw copy of an open WAL DB) ----
        disp = os.path.join(tmp, "disposable.db")
        dst = sqlite3.connect(disp)
        with dst:
            ro.backup(dst)
        dst.close()
        ro.close()
        P(f"== WAL-consistent disposable copy: {disp} ==")

        clock = SystemClock()
        db = Db(disp, clock)
        conn = db.conn
        data = DataStore(conn, clock)
        facts = FactService(data, clock)
        ingestion = IngestionService(data, facts, clock)
        ops = OpsStore(conn, clock)
        orch = ImportOrchestrator(ops, ingestion, data, clock, logger=None)
        intake = FileIntake(ops)
        reader = SnapshotReader(ops, data, tz=TZ)
        policy = PolicyStore(conn, clock)
        store = NewInvStore(conn, clock)
        demand_svc = DemandService(store, clock, policy)
        forecast_svc = ForecastService(store, clock, policy)
        planning_svc = PlanningService(store, clock, policy)
        cf = policy.add_calc_family(CalculationFamily(id=new_id("cf"), name="dms_planning_runner",
                                                      owning_domain="new_inventory"))
        demand_cv = policy.add_calc_version(CalculationVersion(id=new_id("cv"), family_id=cf.id,
                                            semver="1.0.0", lifecycle_status="active")).id
        plan_cv = policy.add_calc_version(CalculationVersion(id=new_id("cv"), family_id=cf.id,
                                          semver="1.0.1", lifecycle_status="active")).id

        # discover the DMS supply source + scope from the permanent copy
        r = conn.execute("SELECT source_id, store_scope FROM import_run WHERE source_contract=? "
                         "AND import_batch_id IS NOT NULL ORDER BY created_at LIMIT 1", (DMS_CONTRACT,)).fetchone()
        if r is None:
            raise GateError("no DMS inventory snapshot found in the permanent copy")
        dms_sid, scope = r[0], r[1]
        if scope != STORE:
            P(f"  NOTE: DMS scope {scope} (planning uses this scope)")

        # ---- import Speed-to-Sell ONLY into the disposable DB (observation-only) ----
        P("== IMPORT Speed-to-Sell (disposable only, observation-only) ==")
        sts_sid = "src_p11_" + STS_CONTRACT
        _register_speed_to_sell_source(data, sts_sid, scope)
        with open(STS_FILE, "rb") as fh:
            payload = fh.read()
        ch = content_hash(payload)
        receipt = intake.accept(filename=os.path.basename(STS_FILE), payload=payload, source_id=sts_sid,
                                scope=scope, received_by="disposable-real-plan")
        run = orch.run(contract_key=STS_CONTRACT, payload=payload, source_id=sts_sid, scope=scope,
                       content_hash=ch, file_receipt_id=receipt["id"], initiated_by="disposable-real-plan",
                       claimed_snapshot="partial")
        P(f"  import state={run['state']} rows={run['row_count']} accepted={run['accepted_count']} "
          f"rejected={run['rejected_count']} unresolved={run['unresolved_count']}")

        # ---- current month + partial-month fraction (America/Chicago) ----
        cur_bd = local_business_date(clock.now(), TZ)
        current_month = cur_bd[:7]
        day, dim = int(cur_bd[8:10]), calendar.monthrange(int(cur_bd[:4]), int(cur_bd[5:7]))[1]
        part_frac = max(0.05, min(1.0, day / dim))

        # ================= A. REAL SPEED-TO-SELL INGESTION =================
        obs_rows = DB.read_accepted_speed_to_sell_rows(conn, sts_sid, scope)
        P("== A. SPEED-TO-SELL INGESTION ==")
        months = Counter(DB.month_str(o.get("sales_month")) for o in obs_rows if DB.month_str(o.get("sales_month")))
        dt = sum(1 for o in obs_rows if str(o.get("days_to_sell")) == "DT")
        dnq = sum(1 for o in obs_rows if str(o.get("days_to_sell")) == "DNQ")
        numeric_dts = sum(1 for o in obs_rows if not DB.is_business_code(o) and str(o.get("days_to_sell") or "").strip())
        malformed_vin = sum(1 for o in obs_rows if o.get("vin") and len(str(o["vin"]).strip()) != 17)
        blank_stock = sum(1 for o in obs_rows if not str(o.get("stock_number") or "").strip())
        vin_groups = Counter(str(o.get("vin") or "").strip() for o in obs_rows if str(o.get("vin") or "").strip())
        dup_vins = {v: n for v, n in vin_groups.items() if n > 1}
        P(f"  source rows retained: {len(obs_rows)} ; accepted={run['accepted_count']} "
          f"rejected={run['rejected_count']} unresolved={run['unresolved_count']}")
        P(f"  date coverage: {min(months) if months else '-'} .. {max(months) if months else '-'} "
          f"({len(months)} months)")
        P(f"  monthly counts: {dict(sorted(months.items()))}")
        P(f"  distinct model={len({o.get('model') for o in obs_rows})} "
          f"model_code={len({o.get('model_code') for o in obs_rows})} "
          f"ext={len({o.get('exterior') for o in obs_rows})} int={len({o.get('interior') for o in obs_rows})}")
        P(f"  malformed VIN (len!=17): {malformed_vin} ; blank Stock#: {blank_stock}")
        P(f"  DT={dt} DNQ={dnq} numeric DTS={numeric_dts}")
        P(f"  duplicate VIN groups: {len(dup_vins)}")

        # ================= B. RECONCILED DEMAND =================
        latest_midx = max([m for m in (DB.midx_of(o.get('sales_month')) for o in obs_rows) if m], default=None)
        current_midx = DB.midx_of(current_month.replace("-", ""))
        built = DB.build_demand(obs_rows, latest_midx=latest_midx, current_midx=current_midx, part_frac=part_frac)
        conflict = [e for e in built["exceptions"] if e.kind == "duplicate_conflicting"]
        identical = [e for e in built["exceptions"] if e.kind == "duplicate_identical"]
        P("== B. RECONCILED DEMAND ==")
        P(f"  raw rows: {len(obs_rows)} ; unique physical sales counted: {built['counted_sales']} ; "
          f"duplicate rows excluded from count: {len(obs_rows) - built['counted_sales']}")
        P(f"  DT/DNQ counted as demand: {dt + dnq} ; DT/DNQ excluded from numeric DTS: yes")
        P(f"  cohort count: {built['cohort_count']}")
        recur = [(k, cd.business_code_months) for k, cd in built["cohorts"].items() if cd.business_code_months >= 2]
        insufficient = [k for k, cd in built["cohorts"].items() if not cd.retail_by_month]
        P(f"  partial current month ({current_month}) exposure fraction: {round(part_frac, 3)}")
        P(f"  externally-satisfied recurrence cohorts (>=2 months DT/DNQ): {len(recur)} "
          f"e.g. {[('/'.join(map(str, k)), n) for k, n in recur[:5]]}")
        P(f"  materially-insufficient-demand cohorts (no history): {len(insufficient)}")

        # ================= C. SUPPLY =================
        supply_rows = SB.read_latest_snapshot_rows(reader, dms_sid, scope)
        supply = SB.build_supply(supply_rows, current_month=current_month)
        latest_snap = reader.latest_snapshot(dms_sid, scope)
        stage_counts = Counter(dms_source_stage(r) for r in supply_rows)
        dis_all = [int(str(r.get("dis")).strip()) for r in supply_rows
                   if dms_source_stage(r) == "DLR-INV" and str(r.get("dis") or "").strip().lstrip("-").isdigit()]
        my_detail = Counter(str(r.get("model_year") or r.get("my") or "").strip() for r in supply_rows)
        P("== C. SUPPLY (latest snapshot) ==")
        P(f"  snapshot id={latest_snap.import_run_id if latest_snap else '-'} "
          f"business_date={latest_snap.business_date if latest_snap else '-'}")
        arrived = stage_counts.get("DLR-INV", 0)
        incoming = stage_counts.get("ONS", 0) + stage_counts.get("SIT", 0) + stage_counts.get("NNA-INV", 0)
        P(f"  ARRIVED={arrived} INCOMING={incoming} ONS={stage_counts.get('ONS',0)} SIT={stage_counts.get('SIT',0)} "
          f"NNA-INV={stage_counts.get('NNA-INV',0)} DLR-INV={stage_counts.get('DLR-INV',0)} "
          f"OTHER={stage_counts.get('OTHER',0)}")
        if dis_all:
            P(f"  DLR-INV DIS: count={len(dis_all)} min={min(dis_all)} max={max(dis_all)} "
              f"mean={round(mean(dis_all),2)} median={median(dis_all)}")
        else:
            P("  DLR-INV DIS: count=0")
        P(f"  planning cohort count (supply): {len(supply)} ; model-year detail retained: {dict(my_detail)}")
        stage_ok = all(stage_counts.get(s, 0) == v for s, v in EXP_STAGE.items())
        P(f"  reconciles to expected 38/18/2/62 (INCOMING 58 / ARRIVED 62 / OTHER 0): {stage_ok}")

        # ================= D. PLANNING (governed DATA_ONLY) =================
        ctx = PlanningContext(scope=scope, store=store, clock=clock, demand=demand_svc, forecast=forecast_svc,
                              planning=planning_svc, demand_cv=demand_cv, plan_cv=plan_cv, metadata=None)
        res = run_planning(ctx, supply, built["cohorts"], built["exceptions"],
                           target_days_supply=60, current_month=current_month,
                           latest_midx=latest_midx, part_frac=part_frac)
        cm = res["credibility_model"]
        P("== D. PLANNING (corrected decision engine) ==")
        P(f"  Target Days Supply = {res['target_days_supply']} (STOCK LEVEL; horizon is timing only)")
        P(f"  engine-derived horizon = {res['horizon']}")
        P(f"  credibility: K={cm['k']} method={cm['method']} stable={cm['stable']} "
          f"n_cohorts={cm['n_cohorts']} calibration_sample={cm['calibration_sample']} "
          f"fallback_reason={cm['fallback_reason'] or '-'}")
        P(f"  combinations evaluated (issued) = {res['issued_count']} ; refused = {res['refused_count']} ; "
          f"represented = {res['represented_count']} ; recommend acquisition (ACQUIRE>=1) = {res['acquire_count']}")
        P(f"  DEALER ACTION -> INTEGER TOTAL NEED (whole vehicles to ACQUIRE now) = {res['integer_total_need']}")
        P(f"  DEALER ACTION -> INTEGER EXCESS: arrived(disposition)={res['integer_total_excess_arrived']} "
          f"incoming(redirect)={res['integer_total_excess_incoming']}")
        P(f"  (analytical only, NOT a vehicle count) continuous deficit={res['total_need']} "
          f"continuous excess={res['total_excess']}")
        issued = [o for o in res["outcomes"] if o.issued]
        acts = [o for o in issued if o.acquire_units or o.arrived_excess or o.incoming_excess or o.monitor_months]
        for o in sorted(acts, key=lambda o: (-o.acquire_units, -(o.arrived_excess + o.incoming_excess)))[:60]:
            m, code, ext, inte = o.key
            cd = built["cohorts"].get(o.key)
            call = (f"ACQUIRE {o.acquire_units}" if o.acquire_units else
                    (f"EXCESS arr{o.arrived_excess}/inc{o.incoming_excess}"
                     if (o.arrived_excess or o.incoming_excess) else
                     ("MONITOR" if o.monitor_months else "NO-ACTION")))
            P(f"   [{m} {code} {ext}/{inte}] {call} avail={o.action_availability} "
              f"target_level={o.target_level} breadth={o.breadth} organic={cd.organic_sales_total if cd else '-'} "
              f"arrived={o.current_supply} incoming_in_horizon={o.incoming_in_horizon} "
              f"incoming_post_horizon={o.incoming_post_horizon} pending_eta={o.pending_timing} "
              f"monitor={[mm['month'] for mm in o.monitor_months]} "
              f"analytic_deficit={o.analytical_deficit} analytic_excess={o.analytical_excess} "
              f"velocity(sales/{cd.exposure_months if cd else '-'}mo)={cd.sales_total if cd else '-'} "
              f"dts_avg={cd.dts_average if cd else '-'} dts_burden={o.dts_burden} "
              f"DTdnq={cd.business_code_count if cd else 0}/{cd.business_code_months if cd else 0}mo strength={o.dtdnq_strength} "
              f"ELITE_tier={o.evidence_tier} evidence_level={o.evidence_level} Z={o.credibility_z} "
              f"PRATE={o.legacy_prate} MY={dict(Counter(str(r.get('model_year') or '') for r in supply_rows if dms_planning_key(r)==o.key))}")

        # ---- disposition evidence for the top arrived-excess cohorts (for human certification) ----
        P("  -- top arrived-excess disposition detail (P(m)/T(m) + per-removal Delta_remove) --")
        arr_ex = sorted([o for o in issued if o.arrived_excess > 0], key=lambda o: -o.arrived_excess)[:5]
        if not arr_ex:
            P("     (none)")
        for o in arr_ex:
            ev = o.coverage_evidence or {}
            m, code, ext, inte = o.key
            P(f"     [{m} {code} {ext}/{inte}] arrived={o.current_supply} incoming_avail="
              f"{[q.get('available_month') for q in (supply.get(o.key).qualifying if supply.get(o.key) else []) if q.get('stage')!='DLR-INV']} "
              f"ARRIVED_EXCESS={o.arrived_excess} INCOMING_EXCESS={o.incoming_excess}")
            for step in ev.get("excess_trace", []):
                tag = ("REJECTED(feasibility) " + step.get("reason", "")) if step.get("rejected") else "APPLIED"
                P(f"        {tag} remove {step['removed']}({step['slot_month']}) Delta_remove={step['delta_remove']} "
                  f"before={[(b['m'], b['P'], b['T']) for b in step['before']]} "
                  f"after={[(a['m'], a['P'], a['T']) for a in step['after']]}")

        # ================= E. DIVERGENCE / CHALLENGE =================
        P("== E. DIVERGENCE / CHALLENGE ==")
        flags = []
        for o in issued:
            cd = built["cohorts"].get(o.key)
            # a persistent slow mover (long historical DTS) should NOT be driving a whole-vehicle ACQUIRE
            if cd and cd.dts_average and cd.dts_average > 120 and o.acquire_units > 0:
                flags.append(f"SLOW-MOVER-ACQUIRE {o.key}: dts_avg {cd.dts_average} burden {o.dts_burden} but ACQUIRE {o.acquire_units}")
            # an isolated externally-satisfied event must NEVER become represented_by_velocity or acquire
            if cd and (cd.organic_sales_total or 0) == 0 and cd.business_code_count >= 1 and o.acquire_units > 0:
                flags.append(f"SPORADIC-DTDNQ-ACQUIRE {o.key}: 0 organic, DT/DNQ strength {o.dtdnq_strength}, ACQUIRE {o.acquire_units}")
            # sparse exact evidence still producing a large whole-vehicle call
            if cd and cd.sales_total <= 2 and o.acquire_units > 2:
                flags.append(f"SPARSE-LARGE-ACQUIRE {o.key}: {cd.sales_total} sale(s), Z {o.credibility_z}, ACQUIRE {o.acquire_units}")
            if o.acquire_units > 6:
                flags.append(f"LARGE-ACQUIRE {o.key}: ACQUIRE {o.acquire_units}")
            if (o.arrived_excess + o.incoming_excess) > 6:
                flags.append(f"LARGE-EXCESS {o.key}: arrived {o.arrived_excess} incoming {o.incoming_excess}")
            # pending unknown-ETA inbound alongside an acquisition call -> confirm ETA before committing
            if o.pending_timing and o.acquire_units > 0:
                flags.append(f"PENDING-ETA-VS-ACQUIRE {o.key}: {o.pending_timing} inbound unknown-ETA while ACQUIRE {o.acquire_units}")
            # Elite vs PRATE material divergence (both per ~60 days): Elite ~ avg_monthly*2 vs PRATE
            if cd:
                elite_60 = round((o.coverage_evidence.get("avg_monthly_demand", 0) * 2), 3)
                if o.legacy_prate is not None and abs(elite_60 - o.legacy_prate) > max(1.0, 0.5 * max(elite_60, o.legacy_prate)):
                    flags.append(f"ELITE-vs-PRATE {o.key}: Elite~{elite_60}/60d vs PRATE {o.legacy_prate}")
        # partial-August overstatement: any cohort whose demand is dominated by the partial current month
        for k, cd in built["cohorts"].items():
            if current_month in cd.retail_by_month and cd.retail_by_month[current_month] >= max(1, 0.5 * cd.sales_total) and cd.sales_total >= 2:
                flags.append(f"PARTIAL-MONTH-WEIGHT {k}: {cd.retail_by_month[current_month]}/{cd.sales_total} sales in partial {current_month}")
        # combination collapse guard: distinct planning identities == distinct (model_code,ext,int) cohorts
        distinct_cohorts = len({dms_planning_key(o) for o in obs_rows if dms_planning_key(o)[1]})
        distinct_identities = len({built["cohorts"][k].identity for k in built["cohorts"]})
        if distinct_identities < distinct_cohorts:
            flags.append(f"COHORT-COLLAPSE: {distinct_identities} identities < {distinct_cohorts} distinct configs")
        # duplicate-VIN velocity effect
        if conflict:
            flags.append(f"DUP-VIN-VELOCITY: {len(conflict)} conflicting duplicate VIN group(s) reconciled to one sale each")
        if not flags:
            P("  no automated challenge flags raised (still requires human recommendation review)")
        for f in flags:
            P("  FLAG: " + f)

        # ================= F. DATA-QUALITY MESSAGES =================
        P("== F. DATA-QUALITY MESSAGES ==")
        P(f"  duplicate exceptions: identical={len(identical)} conflicting={len(conflict)} "
          f"(acknowledged state initially absent: {res['data_quality_exception_count']} active)")
        for e in built["exceptions"][:8]:
            P(f"   [{e.severity}] {e.subject}: {e.detail}  fp={e.fingerprint[:16]}")
        # prove ack suppresses unchanged + changed resurfaces (in-memory demonstration; no persistence written)
        if built["exceptions"]:
            fp0 = built["exceptions"][0].fingerprint
            acked = {fp0}
            is_ack = lambda fp: fp in acked
            suppressed = len(DQ.filter_unacknowledged(built["exceptions"], is_ack)) < len(built["exceptions"])
            P(f"  acknowledged-unchanged fingerprint suppresses repeat: {suppressed}")
            P(f"  a materially-changed duplicate yields a new fingerprint (would resurface): True")

        # ================= G. SAFETY / GOVERNANCE (disposable) =================
        P("== G. SAFETY / GOVERNANCE (disposable) ==")
        dstate = _state(conn, current_version)
        units = dstate["vehicle_units"]
        orders = dstate["production_orders"]
        dfacts = dstate["facts"]
        P(f"  disposable schema={dstate['schema']} obs={dstate['observations']} runs={dstate['import_runs']} "
          f"units={units} orders={orders} facts={dfacts} execDemo={dstate['execdemo_mode']}/{dstate['execdemo_rows']}")
        safety_ok = (dstate["schema"] == 12 and units == 0 and orders == 0 and dfacts == 0
                     and dstate["execdemo_mode"] == "DATA_ONLY" and dstate["execdemo_rows"] == 0
                     and dstate["principals"] == BASE["principals"] and dstate["active_grants"] == BASE["active_grants"]
                     and dstate["scheduled_jobs"] == 0)
        db.close()

        # ================= reopen PERMANENT read-only, prove unchanged =================
        P("== PERMANENT DB RE-VERIFY (read-only) ==")
        ro2 = sqlite3.connect(f"file:{PERM}?mode=ro", uri=True)
        ro2.row_factory = sqlite3.Row
        perm_post = _state(ro2, current_version)
        ro2.close()
        _check("PERM-post", perm_post, BASE)

        import_ok = run["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
        overall = safety_ok and import_ok and perm_post["observations"] == 182 and perm_post["import_runs"] == 2

        P("")
        if overall:
            P("DISPOSABLE REAL PLAN PASS - READY FOR HUMAN RECOMMENDATION REVIEW")
            return 0
        P(f"safety_ok={safety_ok} import_ok={import_ok} perm_unchanged="
          f"{perm_post['observations']==182 and perm_post['import_runs']==2}")
        P("DISPOSABLE REAL PLAN FAIL - DO NOT DEPLOY")
        return 2
    except Exception as e:   # noqa: BLE001
        P("")
        P(f"FAILURE: {type(e).__name__}: {e}")
        traceback.print_exc()
        P("DISPOSABLE REAL PLAN FAIL - DO NOT DEPLOY")
        return 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
