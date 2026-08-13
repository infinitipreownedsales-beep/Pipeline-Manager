"""Phase 12 real-demand + planning bridge — governed DATA_ONLY New Inventory recommendations from real DMS
snapshots + real Speed-to-Sell history. Uses a SANITIZED fixture shaped exactly like the real workbook
(row-1 running-tab metadata, row-2 header, DT, DNQ, duplicate-VIN conflicts, partial current month). No real
dealership workbook is committed. Covers the 30 ratified behaviors."""
import os
import tempfile
import unittest

from elite.db import current_version
from elite.ops.fixtures import Phase11, SCOPE as OPS_SCOPE
from elite.ops.intake import content_hash
from elite.newinv.fixtures import Phase4, SCOPE
from elite.newinv.dms_identity import dms_planning_identity, resolve_or_create_planning_combination
from elite.newinv import demand_bridge as DB
from elite.newinv import supply_bridge as SB
from elite.newinv import data_quality as DQ
from elite.newinv.planning_runner import PlanningContext, run_planning, derive_horizon
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx

STS = "speed_to_sell"
HEADERS = ["Sales Month", "Stock Number", "Model", "VIN", "DAYS TO SELL", "MODEL CODE",
           "EXTERIOR CODE", "INTERIOR CODE"]
META = ["LAST ENTERED 2026-08-13 running tab / reference", "", "", "", "", "", "", ""]


def _row(month, vin, dts, code, ext, inte, model="QX60 SPORT", stock=""):
    return [month, stock, model, vin, dts, code, ext, inte]


def sts_workbook(data_rows, *, meta=True):
    grid = ([META] if meta else []) + [HEADERS] + data_rows
    return make_xlsx(grid, sheet_name="SPEED TO SELL REPORT")


def _sem(dts):
    return "business_code" if str(dts) in ("DT", "DNQ") else "numeric"


def D(month, vin, dts, code, ext, inte, model="QX60 SPORT"):
    return {"sales_month": month, "vin": vin, "days_to_sell": dts, "days_to_sell_semantic": _sem(dts),
            "model_code": code, "exterior": ext, "interior": inte, "model": model}


def S(loc, code, ext, inte, dis="", pm="", model="QX60"):
    return {"location": loc, "model_code": code, "ext": ext, "int": inte, "dis": dis,
            "production_month": pm, "model": model}


# ============================ ingestion (real adapter path through Phase 11) ============================
class TestSpeedToSellIngestion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.conn = self.p.stack.db.conn
        self.sid = self.p.source_id(STS)
        rows = [
            _row("202409", "N1", "43", "8331", "QBE", "P", "QX80 LUXE 2WD"),   # numeric, stock present
            _row("202409", "", "DT", "8441", "GAT", "D"),                       # DT, blank stock
            _row("202410", "N3", "DNQ", "8441", "GAT", "D"),                    # DNQ
            _row("202411", "N4", "22", "8441", "GAT", "D"),
            _row("202411", "N5", "18", "5N1AL1FRXS340552", "BW5", "G"),         # malformed-VIN-like model code? no: VIN col
        ]
        # a genuinely malformed VIN in the VIN column, retained as evidence
        rows.append(_row("202412", "N6", "31", "8481", "GAQ", "G"))
        rows[4] = ["202411", "N5", "QX60 SPORT", "5N1AL1FRXS340552", "18", "8441", "BW5", "G"]
        self.rows = rows
        xlsx = sts_workbook(rows)
        self.run = self.p.import_payload(STS, xlsx, chash=content_hash(xlsx))

    def _obs(self):
        import json
        return [json.loads(r["raw_values"]) for r in self.conn.execute(
            "SELECT raw_values FROM source_observation WHERE import_batch_id=?",
            (self.run["import_batch_id"],)).fetchall()]

    def test_01_metadata_row_skipped_header_row2(self):
        self.assertEqual(len(self._obs()), len(self.rows))          # 6 data rows; row-1 metadata skipped

    def test_02_03_all_rows_retained_blank_stock_ok(self):
        obs = self._obs()
        self.assertEqual(len(obs), 6)
        self.assertTrue(any(o.get("stock_number", "") == "" for o in obs))   # blank Stock# accepted/retained

    def test_04_05_dt_dnq_preserved_business_code(self):
        obs = self._obs()
        dt = [o for o in obs if o.get("days_to_sell") == "DT"]
        dnq = [o for o in obs if o.get("days_to_sell") == "DNQ"]
        self.assertEqual(len(dt), 1)
        self.assertEqual(len(dnq), 1)
        self.assertEqual(dt[0]["days_to_sell_semantic"], "business_code")
        self.assertEqual(dnq[0]["days_to_sell_semantic"], "business_code")

    def test_06_malformed_vin_retained_as_evidence(self):
        obs = self._obs()
        self.assertTrue(any(o.get("vin") == "5N1AL1FRXS340552" for o in obs))   # kept verbatim, not fixed

    def test_19_20_21_no_units_orders_facts(self):
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM vehicle_unit").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM production_order").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM business_fact").fetchone()[0], 0)

    def test_29_schema_v12(self):
        self.assertEqual(current_version(self.conn), 12)


# ============================ planning identity (pure) ============================
class TestPlanningIdentity(unittest.TestCase):
    def test_11_model_code_never_collapses(self):
        a = dms_planning_identity({"model_code": "8331", "exterior": "QBE", "interior": "P"})
        b = dms_planning_identity({"model_code": "8481", "exterior": "QBE", "interior": "P"})
        self.assertNotEqual(a, b)

    def test_13_year_agnostic_join(self):
        supply = dms_planning_identity({"model_code": "84416", "ext": "GAT", "int": "D"})   # 5-digit + MY
        demand = dms_planning_identity({"model_code": "8441", "exterior": "GAT", "interior": "D"})
        self.assertEqual(supply, demand)

    def test_12_trim_drivetrain_unknown(self):
        p4 = Phase4(os.path.join(tempfile.mkdtemp(), "e.db"))
        comb = resolve_or_create_planning_combination(
            p4.store, p4.clock, {"model_code": "8441", "exterior": "GAT", "interior": "D"}, SCOPE)
        self.assertIsNone(comb.trim)
        self.assertIsNone(comb.drivetrain)
        self.assertIsNone(comb.model_year)                          # year-agnostic
        self.assertEqual(comb.lineage_metadata["model_code"], "8441")


# ============================ demand bridge (pure) ============================
class TestDemandBridge(unittest.TestCase):
    def _build(self, rows, part_frac=1.0):
        return DB.build_demand(rows, latest_midx=DB.midx_of("202608"),
                               current_midx=DB.midx_of("202608"), part_frac=part_frac)

    def test_07_duplicate_identical_counts_once(self):
        rows = [D("202602", "VDUP", "DT", "8331", "QBE", "P", "QX80 LUXE 2WD"),
                D("202602", "VDUP", "DT", "8331", "QBE", "P", "QX80 LUXE 2WD")]
        res = self._build(rows)
        self.assertEqual(res["counted_sales"], 1)
        self.assertEqual([e.kind for e in res["exceptions"]], ["duplicate_identical"])

    def test_08_duplicate_conflicting_counts_once_and_flags(self):
        rows = [D("202602", "VCON", "22", "8441", "GAT", "D", "QX60 SPORT"),
                D("202602", "VCON", "25", "8441", "GAT", "D", "QX60 SPORT AWD")]
        res = self._build(rows)
        self.assertEqual(res["counted_sales"], 1)
        self.assertEqual(res["exceptions"][0].kind, "duplicate_conflicting")
        self.assertEqual(res["exceptions"][0].severity, "warning")

    def test_04_05_dt_dnq_demand_positive_dts_neutral(self):
        rows = [D("202601", "V1", "DT", "8441", "GAT", "D"),
                D("202602", "V2", "DNQ", "8441", "GAT", "D"),
                D("202603", "V3", "20", "8441", "GAT", "D")]
        res = self._build(rows)
        c = next(iter(res["cohorts"].values()))
        self.assertEqual(c.sales_total, 3)                          # all three count as demand
        self.assertEqual(c.business_code_count, 2)                  # DT + DNQ
        self.assertEqual(c.dts_values, [20.0])                      # only the numeric contributes to DTS
        self.assertEqual(c.dts_average, 20.0)

    def test_14_partial_current_month_exposure(self):
        rows = [D("202608", "V1", "20", "8441", "GAT", "D")]        # single sale in the partial month
        res = self._build(rows, part_frac=0.2)
        c = next(iter(res["cohorts"].values()))
        self.assertEqual(c.exposure_months, 0.2)                    # not a full month

    def test_24_legacy_prate_computed(self):
        rows = [D("202606", "V1", "20", "8441", "GAT", "D"), D("202607", "V2", "20", "8441", "GAT", "D")]
        res = self._build(rows, part_frac=1.0)
        c = next(iter(res["cohorts"].values()))
        self.assertGreater(c.legacy_prate, 0.0)


# ============================ data-quality acknowledgement (pure) ============================
class _Meta:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def put_if_absent(self, k, v):
        self.d.setdefault(k, v)


class TestDataQualityAck(unittest.TestCase):
    def _dup(self, dts2):
        rows = [D("202602", "VX", "22", "8441", "GAT", "D", "QX60 SPORT"),
                D("202602", "VX", dts2, "8441", "GAT", "D", "QX60 SPORT AWD")]
        return DB.build_demand(rows, latest_midx=DB.midx_of("202602"),
                               current_midx=DB.midx_of("202608"), part_frac=1.0)["exceptions"]

    def test_09_10_ack_unchanged_suppressed_changed_resurfaces(self):
        meta = _Meta()
        exc = self._dup("25")
        fp = exc[0].fingerprint
        DQ.acknowledge(meta, fp)
        is_ack = DQ.metadata_ack_lookup(meta)
        self.assertEqual(DQ.filter_unacknowledged(exc, is_ack), [])          # acknowledged unchanged -> silent
        exc2 = self._dup("30")                                              # materially changed DTS
        self.assertNotEqual(exc2[0].fingerprint, fp)                        # new fingerprint
        self.assertEqual(len(DQ.filter_unacknowledged(exc2, is_ack)), 1)    # resurfaces


# ============================ supply bridge (pure) ============================
class TestSupplyBridge(unittest.TestCase):
    def test_15_16_17_18_counts_stages_dis(self):
        rows = [S("DLR-INV", "84416", "GAT", "D", dis=40), S("DLR-INV", "84416", "GAT", "D", dis=12),
                S("ONS", "84416", "GAT", "D", pm="2026-10"), S("SIT", "84416", "GAT", "D", pm="2026-11"),
                S("NNA-INV", "84416", "GAT", "D", pm="2026-09")]
        sup = SB.build_supply(rows, current_month="2026-08")
        c = next(iter(sup.values()))
        self.assertEqual(c.current, 2)                              # ARRIVED (DLR-INV)
        self.assertEqual(c.future, 3)                               # INCOMING (ONS+SIT+NNA-INV)
        self.assertEqual(c.stages, {"DLR-INV": 2, "ONS": 1, "SIT": 1, "NNA-INV": 1})   # exact stages preserved
        self.assertEqual(sorted(c.dis_values), [12, 40])           # DIS aging preserved


# ============================ governed DATA_ONLY runner (against real Phase 4 services) ============================
class TestPlanningRunner(unittest.TestCase):
    def setUp(self):
        self.p4 = Phase4(os.path.join(tempfile.mkdtemp(), "e.db"))
        self.ctx = PlanningContext(scope=SCOPE, store=self.p4.store, clock=self.p4.clock,
                                   demand=self.p4.demand, forecast=self.p4.forecasts,
                                   planning=self.p4.planning, demand_cv=self.p4.demand_cv,
                                   plan_cv=self.p4.plan_cv, metadata=self.p4.stack.metadata)
        self.conn = self.p4.store.conn

    def _demand(self, months=range(1, 9)):
        rows = [D(f"2026{m:02d}", f"V{m}", "20", "8441", "GAT", "D") for m in months]
        return DB.build_demand(rows, latest_midx=DB.midx_of("202608"),
                               current_midx=DB.midx_of("202608"), part_frac=0.2)

    def test_22_23_26_28_issue_with_real_demand(self):
        built = self._demand()
        sup = SB.build_supply([S("DLR-INV", "84416", "GAT", "D", dis=30),
                               S("ONS", "84416", "GAT", "D", pm="2026-10")], current_month="2026-08")
        res = run_planning(self.ctx, sup, built["cohorts"], built["exceptions"],
                           target_days_supply=60, current_month="2026-08")
        self.assertEqual(res["issued_count"], 1)
        self.assertEqual(res["target_days_supply"], 60)            # Target Days Supply passed as objective
        o = res["outcomes"][0]
        self.assertTrue(o.issued)
        self.assertEqual(o.evidence_tier, "exact")                # Elite DemandService authoritative
        self.assertEqual(o.coverage_evidence["target_days_supply"], 60)
        # existing UI reads the issued plan
        rows = self.conn.execute("SELECT COUNT(*) FROM inventory_plan_result WHERE store_scope=? "
                                 "AND status='issued'", (SCOPE,)).fetchone()[0]
        self.assertEqual(rows, 1)

    def test_25_insufficient_demand_refuses(self):
        # cohort with supply but NO demand history -> refuse, never fabricate need/excess
        sup = SB.build_supply([S("DLR-INV", "83316", "QBE", "P", dis=10)], current_month="2026-08")
        res = run_planning(self.ctx, sup, {}, [], target_days_supply=60, current_month="2026-08")
        self.assertEqual(res["issued_count"], 0)
        self.assertEqual(res["refused_count"], 1)
        self.assertEqual(res["outcomes"][0].refused_reason, "no_accepted_demand_history")
        self.assertEqual(res["total_need"], 0.0)                   # no fabricated need

    def test_24_legacy_prate_cannot_override(self):
        built = self._demand()
        sup = SB.build_supply([S("DLR-INV", "84416", "GAT", "D", dis=30)], current_month="2026-08")
        res = run_planning(self.ctx, sup, built["cohorts"], built["exceptions"],
                           target_days_supply=60, current_month="2026-08")
        o = res["outcomes"][0]
        self.assertIsNotNone(o.legacy_prate)                      # PRATE reported as comparison
        # authoritative demand/need comes from Elite (evidence_tier exact), not PRATE
        self.assertEqual(o.evidence_tier, "exact")

    def test_19_20_21_no_units_orders_facts_or_execution(self):
        built = self._demand()
        sup = SB.build_supply([S("DLR-INV", "84416", "GAT", "D", dis=30)], current_month="2026-08")
        run_planning(self.ctx, sup, built["cohorts"], built["exceptions"],
                     target_days_supply=60, current_month="2026-08")
        for t in ("vehicle_unit", "production_order", "business_fact"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)

    def test_29_schema_v12(self):
        self.assertEqual(current_version(self.conn), 12)

    def test_horizon_derived_not_configured(self):
        sup = SB.build_supply([S("ONS", "84416", "GAT", "D", pm="2026-11")], current_month="2026-08")
        hz = derive_horizon("2026-08", sup)
        self.assertEqual(hz[0], "2026-09")                        # derived from now + incoming window
        self.assertIn("2026-11", hz)


# ============ decision-engine correction: credibility + time-phased order-up-to + breadth/depth ============
# Uses the REAL disposable-validation failure shapes (sanitized numbers; no dealer file committed): the
# 1-partial-month-sale -> Need 5 explosion, 180-day slow movers, isolated vs recurrent DT/DNQ, post-horizon
# and unknown-ETA incoming, and the gross-vs-net distinction.
def _panel(extra=()):
    """A modest, mostly-sparse cohort panel (so calibration has real cross-cohort context) plus `extra`."""
    rows = []
    # 10 QX60 model-code cohorts (codes 83x1, distinct from the special codes tested below), 2-4 sales
    # each spread over 2025-2026 (typical thin dealer history) so calibration has cross-cohort context.
    for i in range(10):
        for j in range((i % 3) + 2):
            rows.append(D(f"20{25 + (j % 2)}{((i + j) % 12) + 1:02d}", f"P{i:02d}{j:02d}00000000{i}",
                          "45", f"83{i}1", "GAT", "D", model="QX60 SPORT"))
    return rows + list(extra)


def _run(rows, supply_rows, *, tds=60, latest="202608", pf=1.0):
    p4 = Phase4(os.path.join(tempfile.mkdtemp(), "e.db"))
    ctx = PlanningContext(scope=SCOPE, store=p4.store, clock=p4.clock, demand=p4.demand,
                          forecast=p4.forecasts, planning=p4.planning, demand_cv=p4.demand_cv,
                          plan_cv=p4.plan_cv, metadata=p4.stack.metadata)
    built = DB.build_demand(rows, latest_midx=DB.midx_of(latest), current_midx=DB.midx_of("202608"),
                            part_frac=pf)
    sup = SB.build_supply(supply_rows, current_month="2026-08")
    res = run_planning(ctx, sup, built["cohorts"], built["exceptions"], target_days_supply=tds,
                       current_month="2026-08", latest_midx=DB.midx_of(latest), part_frac=pf)
    return p4, res


def _by_code(res, code):
    return next((o for o in res["outcomes"] if o.key[1] == code), None)


class TestDecisionEngineCorrection(unittest.TestCase):
    # (2/3) sparse explosion killed: a single partial-month sale no longer yields ~Need 5
    def test_sparse_single_sale_does_not_explode(self):
        rows = _panel(extra=[D("202608", "SPARSE0000000001", "5", "8599", "QBE", "G", model="QX65 SPORT")])
        _p, res = _run(rows, [], pf=0.4194)
        o = _by_code(res, "8599")
        self.assertIsNotNone(o)
        self.assertLess(o.need, 2.0)                       # was 5.0 under the old model
        self.assertLess(o.credibility_z, 0.5)              # heavily shrunk (n=1)
        self.assertIn(o.evidence_level, ("model", "model_code", "portfolio"))

    # (5/8) historical DTS is risk evidence: a persistent 180-day mover is dampened, not stocked deep
    def test_slow_mover_dts_burden_suppresses_depth(self):
        slow = [D(f"2025{(j % 12) + 1:02d}", f"SLOW{j:02d}00000000X", "180", "8131", "QBE", "W",
                  model="QX65") for j in range(8)]
        _p, res = _run(_panel(extra=slow), [])
        o = _by_code(res, "8131")
        self.assertIsNotNone(o)
        self.assertLess(o.dts_burden, 0.5)                 # 180-day DTS materially raises the burden
        self.assertLessEqual(o.need, 1.0)                  # not stocked deep despite 8 sales

    # (9) DT/DNQ affects BREADTH not DEPTH: isolated event weak; recurrence represents but does not scale
    def test_dtdnq_isolated_weak_recurrent_breadth_only(self):
        iso = [D("202607", "DTISO00000000001", "DT", "8961", "KAD", "G", model="QX60 SPORT")]
        recur = [D(f"2026{m:02d}", f"DNQ{m:02d}0000000Q", "DNQ", "8971", "KAD", "K", model="QX60 SPORT")
                 for m in (3, 5, 7)]
        _p, res = _run(_panel(extra=iso + recur), [])
        iso_o, rec_o = _by_code(res, "8961"), _by_code(res, "8971")
        self.assertLess(iso_o.dtdnq_strength, 0.5)         # one isolated DT is weak evidence
        self.assertGreaterEqual(rec_o.dtdnq_strength, 0.5)  # recurrence is stronger
        # recurrence may justify carrying ONE (breadth); it never scales depth to many
        if rec_o.breadth == "represented_by_recurrence":
            self.assertLessEqual(rec_o.target_level, 1.0)

    # (1/4) time-phased order-up-to: incoming credited only when it arrives; post-horizon not netted now
    def test_supply_timing_order_up_to(self):
        base = [D(f"2026{m:02d}", f"TIM{m:02d}0000000001", "30", "8481", "XB3", "P", model="QX60") for m in range(1, 9)]
        # arrived 1 + incoming within horizon 1 -> position 2
        _p, r_in = _run(_panel(base), [S("DLR-INV", "84811", "XB3", "P", dis=20),
                                       S("ONS", "84811", "XB3", "P", pm="2026-10")])
        # arrived 1 + incoming FAR future (2027, beyond horizon) -> only arrived counts now
        _p, r_post = _run(_panel(base), [S("DLR-INV", "84811", "XB3", "P", dis=20),
                                         S("ONS", "84811", "XB3", "P", pm="2027-06")])
        a, b = _by_code(r_in, "8481"), _by_code(r_post, "8481")
        self.assertEqual(a.incoming_in_horizon, 1)
        self.assertEqual(b.incoming_post_horizon, 1)
        self.assertGreaterEqual(b.need, a.need)            # crediting later supply now would be wrong
        self.assertGreaterEqual(a.current_supply, 1)

    # (4/5) unknown-ETA incoming stays uncertain: never counted as immediately available
    def test_unknown_eta_is_pending_not_credited(self):
        base = [D(f"2026{m:02d}", f"UNK{m:02d}0000000001", "30", "8491", "GAT", "D", model="QX60") for m in range(1, 9)]
        _p, res = _run(_panel(base), [S("ONS", "84911", "GAT", "D", pm="")])   # blank production/ETA
        o = _by_code(res, "8491")
        self.assertEqual(o.pending_timing, 1)              # surfaced as pending, not available
        self.assertEqual(o.incoming_in_horizon, 0)

    # (item 11/12) totals are NET: Total Need sums only actionable acquisition; gross target kept separately
    def test_total_need_is_net_and_gross_is_separate(self):
        _p, res = _run(_panel(), [])
        self.assertAlmostEqual(res["total_need"],
                               round(sum(max(0.0, o.need) for o in res["outcomes"] if o.issued), 4), places=4)
        # every issued plan keeps a gross target coverage that is NOT the acquisition number
        p4b, res2 = _run(_panel(), [])
        issued = [o for o in res2["outcomes"] if o.issued and o.plan_id]
        self.assertTrue(issued)
        plan = p4b.store.get_plan(issued[0].plan_id)
        self.assertIn("target_units", plan.desired_ending_coverage)
        self.assertEqual(plan.evidence["model"], "time_phased_order_up_to")

    # (calibration) a credibility model is calibrated from the panel and recorded with stability + sample
    def test_credibility_model_calibrated_and_recorded(self):
        _p, res = _run(_panel(), [])
        cm = res["credibility_model"]
        self.assertIn(cm["method"], ("buhlmann_stable", "fallback_median_sample", "degenerate"))
        self.assertGreater(cm["calibration_sample"], 0)
        self.assertIsInstance(cm["stable"], bool)

    # (Phase 4 invariant preserved) adding qualifying supply never RAISES net Need
    def test_added_qualifying_never_raises_need(self):
        base = [D(f"2026{m:02d}", f"INV{m:02d}0000000001", "30", "8451", "GAT", "D", model="QX60") for m in range(1, 9)]
        _p, r0 = _run(_panel(base), [])
        _p, r1 = _run(_panel(base), [S("DLR-INV", "84511", "GAT", "D", dis=15)])
        n0, n1 = _by_code(r0, "8451").need, _by_code(r1, "8451").need
        self.assertLessEqual(n1, n0)

    # (governance) no physical entities / facts from the planning run; schema stays v12
    def test_planning_creates_no_entities_v12(self):
        p4, res = _run(_panel(), [S("DLR-INV", "84011", "GAT", "D", dis=20)])
        for t in ("vehicle_unit", "production_order", "business_fact"):
            self.assertEqual(p4.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)
        self.assertEqual(current_version(p4.store.conn), 12)


# ===================== regression: Speed-to-Sell physical-identity leak (REAL 17-char VINs) =====================
# Blind-spot fix. The original TestSpeedToSellIngestion used non-VIN-shaped synthetic ids ("N1"...), so
# resolve_vehicle always returned UNRESOLVED and no unit was ever created -- masking that a VIN-bearing
# observation-only source WOULD create a physical VehicleUnit. The REAL Speed-to-Sell workbook carries valid
# 17-char VINs and leaked 400 VehicleUnits at ingestion. These tests use REAL-shaped VALID VINs and prove
# ingestion creates zero physical entities while retaining each VIN verbatim for the DERIVED demand bridge,
# that duplicate reconciliation still works on that derived layer, that planning still functions from the
# observation-derived demand, and that a genuine PHYSICAL (vehicle) source still resolves a unit normally.
V1 = "5N1AL0MN9NC300001"
V2 = "5N1AL0MN9NC300002"
V3 = "5N1AL0MN9NC300004"


class TestSpeedToSellPhysicalIdentityLeakRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.conn = self.p.stack.db.conn
        self.sid = self.p.source_id(STS)
        # real-shaped rows: distinct valid VINs across months, an IDENTICAL-duplicate VIN, and a
        # materially-CONFLICTING-duplicate VIN (same VIN, different days-to-sell) -- the real shapes.
        self.rows = [
            _row("202603", V1, "20", "8441", "GAT", "D"),
            _row("202604", V2, "35", "8441", "GAT", "D"),
            _row("202605", V3, "18", "8441", "GAT", "D"),
            _row("202603", V1, "20", "8441", "GAT", "D"),   # identical duplicate of V1
            _row("202605", V2, "99", "8441", "GAT", "D"),   # conflicting duplicate of V2 (different DTS/month)
        ]
        xlsx = sts_workbook(self.rows)
        self.run = self.p.import_payload(STS, xlsx, chash=content_hash(xlsx))

    def _obs_rows(self):
        return DB.read_accepted_speed_to_sell_rows(self.conn, self.sid, SCOPE)

    def _count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    # (1)+(2) every real-VIN row retained as a Source Observation, VIN verbatim, duplicate NOT collapsed
    def test_rows_retained_and_vin_verbatim(self):
        obs = self._obs_rows()
        self.assertEqual(len(obs), len(self.rows))                  # all rows retained
        vins = [o.get("vin") for o in obs]
        for v in (V1, V2, V3):
            self.assertIn(v, vins)                                  # valid 17-char VIN kept verbatim
        self.assertEqual(vins.count(V1), 2)                         # duplicate preserved, not destroyed

    # (4)+(5)+(6) ingestion of VIN-bearing observation-only rows creates NO physical entity / fact
    def test_zero_units_orders_facts(self):
        self.assertEqual(self._count("vehicle_unit"), 0)            # <-- the leak: was 400 on real data
        self.assertEqual(self._count("production_order"), 0)
        self.assertEqual(self._count("business_fact"), 0)
        outs = {r[0] for r in self.conn.execute(
            "SELECT DISTINCT identity_status FROM source_observation").fetchall()}
        self.assertEqual(outs, {"observation"})                    # explicit observation-only outcome

    # (3) duplicate-VIN reconciliation still works on the DERIVED demand layer, using the retained VIN
    def test_duplicate_reconciliation_uses_vin(self):
        counted, exceptions = DB.reconcile(self._obs_rows())
        by_vin = {}
        for c in counted:
            by_vin[c.vin] = by_vin.get(c.vin, 0) + 1
        self.assertEqual(by_vin.get(V1), 1)                         # identical duplicate counted once
        self.assertEqual(by_vin.get(V2), 1)                         # conflicting duplicate counted once
        kinds = {e.kind for e in exceptions}
        self.assertIn("duplicate_identical", kinds)                 # benign duplicate surfaced
        self.assertIn("duplicate_conflicting", kinds)               # material conflict surfaced

    # (7) planning still functions from the observation-derived demand (issues, creates no physical entity)
    def test_planning_functions_from_observation_demand(self):
        rows = self._obs_rows()
        built = DB.build_demand(rows, latest_midx=DB.midx_of("202605"),
                                current_midx=DB.midx_of("202608"), part_frac=1.0)
        self.assertGreaterEqual(built["counted_sales"], 3)         # demand derived from ingested observations
        p4 = Phase4(os.path.join(self.tmp, "p4.db"))
        ctx = PlanningContext(scope=SCOPE, store=p4.store, clock=p4.clock, demand=p4.demand,
                              forecast=p4.forecasts, planning=p4.planning, demand_cv=p4.demand_cv,
                              plan_cv=p4.plan_cv, metadata=p4.stack.metadata)
        sup = SB.build_supply([S("DLR-INV", "84416", "GAT", "D", dis=30)], current_month="2026-08")
        res = run_planning(ctx, sup, built["cohorts"], built["exceptions"],
                           target_days_supply=60, current_month="2026-08")
        self.assertGreaterEqual(res["issued_count"], 1)            # planning still functions
        for t in ("vehicle_unit", "production_order", "business_fact"):
            self.assertEqual(p4.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)

    # (8) a genuine PHYSICAL (vehicle) source with the SAME valid VIN still resolves + creates a VehicleUnit
    def test_physical_vehicle_source_still_resolves(self):
        from elite.data.fixtures import Phase2
        p2 = Phase2(os.path.join(self.tmp, "p2.db"))
        batch = p2.ingest_dms([{"stock_number": "N1", "vin": V1, "model": "qx60",
                                "production_month": "2026-03", "mileage": "5"}])
        self.assertEqual(batch.accepted_count, 1)
        units = p2.store.conn.execute("SELECT COUNT(*) FROM vehicle_unit").fetchone()[0]
        self.assertEqual(units, 1)                                  # physical resolution intact (not broken)

    def test_schema_v12(self):
        self.assertEqual(current_version(self.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
