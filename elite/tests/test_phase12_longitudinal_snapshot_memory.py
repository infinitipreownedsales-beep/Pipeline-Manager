"""Phase 12 longitudinal inventory snapshot memory — read-only, derived, observation-only.

Proves recurring `vehicleInventorySummary` exports form a chronological inventory memory WITHOUT order->VIN
reconciliation, without a new snapshot table, and without a schema migration (v12 stays v12):

  * snapshots are DERIVED from existing import_run/import_batch/source_observation lineage;
  * idempotency is (source, scope, LOCAL BUSINESS DATE [America/Chicago], content hash) for this source
    only — same file same day = replay; same file next day = a new legitimate snapshot; different file same
    day = a new snapshot; unrelated contracts keep pure content-hash replay unchanged;
  * cohort identity is the ratified source-grounded key (model, model_year, model_code, ext, int) — volatile
    Stock#/Serial/Status/Location/DIS/ETA/Production Month never define a cohort;
  * ONS->DLR-INV shows up as a cohort-level portfolio delta / APPARENT_COHORT_ARRIVAL with preserved
    uncertainty, never a same-unit identity claim;
  * DIS aging is authoritative per snapshot;
  * NO ProductionOrder / VehicleUnit / business fact / recommendation is ever created.

Everything runs on throwaway temp databases; the permanent DB is never touched.
"""
import os
import tempfile
import unittest

from elite.clock import local_business_date
from elite.db import current_version
from elite.ops.fixtures import Phase11, SCOPE, INV_VALID
from elite.ops.intake import content_hash
from elite.newinv.dms_cohort import (dms_cohort_key, COHORT_DIMS, INVENTORY_STATE_FIELD, SOURCE_STAGES,
                                     classify_source_stage, dms_source_stage, dms_planning_state,
                                     planning_state_of)
from elite.newinv.snapshots import (SnapshotReader, SnapshotDelta, movement_signals, status_bucket)
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS

CONTRACT = "new_inventory_pipeline_summary"

# cohort A = QX60/2026/60111/BLK/GRY ; cohort B = QX80/2026/83816/WHT/BLK
_ORDER = ["stock", "serial", "status", "my", "model", "code", "desc", "trans",
          "ext", "inte", "msrp", "inv", "location", "dis", "eta", "pmonth"]


def R(stock="", serial="", status="ONS", my="2026", model="QX60", code="60111", desc="",
      trans="AUTO", ext="BLK", inte="GRY", msrp="58,900", inv="55,000", location="",
      dis="", eta="08/20/2026", pmonth="2025-07"):
    """Build one DMS summary row in canonical HEADERS column order."""
    vals = dict(stock=stock, serial=serial, status=status, my=my, model=model, code=code, desc=desc,
                trans=trans, ext=ext, inte=inte, msrp=msrp, inv=inv, location=location, dis=dis,
                eta=eta, pmonth=pmonth)
    return [vals[k] for k in _ORDER]


# REAL DMS semantics: the ONS / DLR-INV pipeline state is carried by LOCATION; Status holds an unrelated
# operational value ("Deal Opened"). The helpers put the pipeline state in Location on purpose.
def A(state, serial, dis=""):
    return R(stock="", serial=serial, status="Deal Opened", model="QX60", code="60111", ext="BLK",
             inte="GRY", location=state, dis=dis)


def B(state, serial):
    return R(stock="", serial=serial, status="Deal Opened", model="QX80", code="83816", ext="WHT",
             inte="BLK", location=state)


# T0: 5x A/ONS, 2x A/DLR-INV, 3x B/ONS
T0 = [A("ONS", f"A-ONS-{i}") for i in range(5)] \
    + [A("DLR-INV", "A-INV-0", 40), A("DLR-INV", "A-INV-1", 12)] \
    + [B("ONS", f"B-ONS-{i}") for i in range(3)]

# T1 (clean apparent arrival for A): 3x A/ONS (-2), 4x A/DLR-INV (+2), 3x B/ONS (unchanged)
T1 = [A("ONS", f"A-ONS-{i}") for i in range(3)] \
    + [A("DLR-INV", "A-INV-0", 41), A("DLR-INV", "A-INV-1", 13),
       A("DLR-INV", "A-INV-2", 1), A("DLR-INV", "A-INV-3", 2)] \
    + [B("ONS", f"B-ONS-{i}") for i in range(3)]

# T1b (ambiguous): 3x A/ONS (-2) but 5x A/DLR-INV (+3) -> magnitudes differ, cohort total +1
T1B = [A("ONS", f"A-ONS-{i}") for i in range(3)] \
    + [A("DLR-INV", f"A-INV-{i}", 10 + i) for i in range(5)] \
    + [B("ONS", f"B-ONS-{i}") for i in range(3)]

DAY0 = "2026-08-12T15:00:00+00:00"     # America/Chicago 2026-08-12
DAY0_LATER = "2026-08-12T22:00:00+00:00"
DAY1 = "2026-08-13T15:00:00+00:00"     # America/Chicago 2026-08-13
DAY2 = "2026-08-14T15:00:00+00:00"


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.sid = self.p.source_id(CONTRACT)
        self.reader = SnapshotReader(self.p.ops, self.p.data)
        self.delta = SnapshotDelta(self.reader)

    def imp(self, rows, *, effective_time=None, chash=None):
        xlsx = make_xlsx([HEADERS] + rows)
        ch = chash or content_hash(xlsx)
        return self.p.import_payload(CONTRACT, xlsx, chash=ch, effective_time=effective_time)

    def _count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]


class TestSnapshotDerivation(_Base):
    # A. Snapshot #1 derives from lineage; backward-compatible with legacy (null observation times).
    def test_snapshot1_derivation_and_legacy_fallback(self):
        run = self.imp(T0, effective_time=DAY0)
        snaps = self.reader.list_snapshots(self.sid, SCOPE)
        self.assertEqual(len(snaps), 1)
        s = snaps[0]
        self.assertEqual(s.import_run_id, run["id"])
        self.assertEqual(s.import_batch_id, run["import_batch_id"])
        self.assertEqual(s.content_hash, run["content_hash"])
        self.assertEqual(s.row_count, len(T0))
        self.assertEqual(s.business_date, "2026-08-12")
        self.assertEqual(len(self.reader.snapshot_rows(s)), len(T0))
        # emulate a Snapshot #1 that predates observation-time propagation: null the time fields and
        # confirm the documented fallback (received_at) still yields a readable snapshot + business date.
        self.conn.execute("UPDATE import_run SET source_effective_time=NULL WHERE id=?", (run["id"],))
        self.conn.execute("UPDATE import_batch SET effective_time=NULL WHERE id=?",
                          (run["import_batch_id"],))
        self.conn.commit()
        s2 = self.reader.list_snapshots(self.sid, SCOPE)[0]
        self.assertTrue(s2.observed_time)                    # falls back to received_at
        self.assertTrue(s2.business_date)                    # still derivable

    # B/C. chronology + latest selection across three business dates.
    def test_chronology_and_latest(self):
        self.imp(T0, effective_time=DAY1)                    # insert out of order on purpose
        self.imp(T0, effective_time=DAY0, chash=content_hash(b"x0"))
        self.imp(T0, effective_time=DAY2, chash=content_hash(b"x2"))
        snaps = self.reader.list_snapshots(self.sid, SCOPE)
        self.assertEqual([s.business_date for s in snaps],
                         ["2026-08-12", "2026-08-13", "2026-08-14"])
        self.assertEqual([s.sequence for s in snaps], [1, 2, 3])
        self.assertEqual(self.reader.latest_snapshot(self.sid, SCOPE).business_date, "2026-08-14")


class TestIdempotency(_Base):
    # D. same file + same business date twice -> one snapshot (replay).
    def test_same_day_same_hash_is_replay(self):
        r1 = self.imp(T0, effective_time=DAY0)
        n1 = self._count("source_observation")
        b1 = self._count("import_batch")
        r2 = self.imp(T0, effective_time=DAY0_LATER)         # same hash, same Chicago day, later clock
        self.assertEqual(r1["id"], r2["id"])                 # ops layer: replay
        self.assertEqual(self._count("source_observation"), n1)   # data layer: no new observations
        self.assertEqual(self._count("import_batch"), b1)         # both layers agree
        self.assertEqual(len(self.reader.list_snapshots(self.sid, SCOPE)), 1)

    # E. same file/hash on the next business date -> two distinct snapshots.
    def test_next_day_same_hash_is_new_snapshot(self):
        r1 = self.imp(T0, effective_time=DAY0)
        n1 = self._count("source_observation")
        r2 = self.imp(T0, effective_time=DAY1)
        self.assertNotEqual(r1["id"], r2["id"])
        self.assertEqual(self._count("source_observation"), 2 * n1)
        snaps = self.reader.list_snapshots(self.sid, SCOPE)
        self.assertEqual([s.business_date for s in snaps], ["2026-08-12", "2026-08-13"])
        # both idempotency layers created a new record (ops run + data batch agree).
        self.assertEqual(self._count("import_batch"), 2)

    # F. different content on the SAME business date -> two snapshots, chronological.
    def test_same_day_different_hash_is_new_snapshot(self):
        self.imp(T0, effective_time=DAY0)
        self.imp(T0 + [B("ONS", "B-ONS-extra")], effective_time=DAY0_LATER)  # different bytes
        snaps = self.reader.list_snapshots(self.sid, SCOPE)
        self.assertEqual(len(snaps), 2)
        self.assertEqual([s.business_date for s in snaps], ["2026-08-12", "2026-08-12"])
        self.assertLessEqual(snaps[0].observed_time, snaps[1].observed_time)

    # G. America/Chicago civil-date boundary (pure) + straddling midnight yields distinct snapshots.
    def test_america_chicago_boundary(self):
        # 04:30Z = 23:30 CDT previous day; 05:30Z = 00:30 CDT same day.
        self.assertEqual(local_business_date("2026-08-13T04:30:00+00:00"), "2026-08-12")
        self.assertEqual(local_business_date("2026-08-13T05:30:00+00:00"), "2026-08-13")
        self.imp(T0, effective_time="2026-08-13T04:30:00+00:00")   # business date 08-12
        self.imp(T0, effective_time="2026-08-13T05:30:00+00:00")   # business date 08-13 (same bytes)
        snaps = self.reader.list_snapshots(self.sid, SCOPE)
        self.assertEqual([s.business_date for s in snaps], ["2026-08-12", "2026-08-13"])

    # O. unrelated contract keeps pure content-hash replay (business date must NOT change its behavior).
    def test_unrelated_contract_unchanged(self):
        ch = content_hash(INV_VALID)
        r1 = self.p.import_payload("new_inventory_current", INV_VALID, effective_time=DAY0, chash=ch)
        r2 = self.p.import_payload("new_inventory_current", INV_VALID, effective_time=DAY1, chash=ch)
        self.assertEqual(r1["id"], r2["id"])                 # replay despite a different business date

    def test_observation_time_propagated(self):
        # H(8): run.source_effective_time, batch.effective_time, source_observation.observed_time all set.
        run = self.imp(T0, effective_time=DAY0)
        self.assertEqual(self.conn.execute(
            "SELECT source_effective_time FROM import_run WHERE id=?", (run["id"],)).fetchone()[0], DAY0)
        self.assertEqual(self.conn.execute(
            "SELECT effective_time FROM import_batch WHERE id=?",
            (run["import_batch_id"],)).fetchone()[0], DAY0)
        obs_times = {r[0] for r in self.conn.execute(
            "SELECT observed_time FROM source_observation WHERE import_batch_id=?",
            (run["import_batch_id"],)).fetchall()}
        self.assertEqual(obs_times, {DAY0})


class TestCohortAndDelta(_Base):
    # H. cohort grouping uses exactly (model, model_year, model_code, ext, int).
    def test_cohort_key_dimensions(self):
        self.assertEqual(COHORT_DIMS, ("model", "model_year", "model_code", "ext", "int"))
        a = dms_cohort_key({"model": "QX60", "model_year": "2026", "model_code": "60111",
                            "ext": "BLK", "int": "GRY"})
        a_same = dms_cohort_key({"model": "qx60", "model_year": "2026", "model_code": "60111",
                                 "ext": "blk", "int": "gry", "stock_number": "999", "dis": "5"})
        a_diff = dms_cohort_key({"model": "QX60", "model_year": "2026", "model_code": "65220",
                                 "ext": "BLK", "int": "GRY"})
        self.assertEqual(a, a_same)                          # normalization + volatile fields ignored
        self.assertNotEqual(a, a_diff)                       # model_code distinguishes

    # I. volatile fields changing does not change the cohort; delta still sees one cohort.
    def test_volatile_change_keeps_cohort(self):
        base = [A("ONS", "s1"), A("ONS", "s2")]
        moved = [R(stock="X9", serial="s1", status="DLR-INV", model="QX60", code="60111", ext="BLK",
                   inte="GRY", location="LOT-7", dis=9, eta="09/01/2026", pmonth="2025-09"),
                 R(stock="Z1", serial="s2", status="DLR-INV", model="QX60", code="60111", ext="BLK",
                   inte="GRY", location="LOT-3", dis=4, eta="09/02/2026", pmonth="2025-09")]
        self.imp(base, effective_time=DAY0)
        self.imp(moved, effective_time=DAY1)
        rep = self.delta.latest_delta(self.sid, SCOPE)
        self.assertEqual(len(rep.cohorts), 1)                # same cohort despite every volatile field changing
        self.assertEqual(rep.new_cohorts, [])
        self.assertEqual(rep.gone_cohorts, [])

    # J. blank Stock# rows are retained and never affect the cohort key.
    def test_blank_stock_retained(self):
        run = self.imp([A("ONS", "s1"), A("ONS", "s2")], effective_time=DAY0)
        rows = self.reader.snapshot_rows(self.reader.latest_snapshot(self.sid, SCOPE))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.get("stock_number", "") == "" for r in rows))
        self.assertEqual(len({dms_cohort_key(r) for r in rows}), 1)

    # K. ONS -> DLR-INV shows up as a cohort delta.
    def test_ons_to_dlr_delta(self):
        self.imp(T0, effective_time=DAY0)
        self.imp(T1, effective_time=DAY1)
        rep = self.delta.latest_delta(self.sid, SCOPE)
        a = next(c for c in rep.cohorts if c.key == dms_cohort_key(
            {"model": "QX60", "model_year": "2026", "model_code": "60111", "ext": "BLK", "int": "GRY"}))
        self.assertEqual(a.ons_delta, -2)
        self.assertEqual(a.dlr_delta, 2)
        self.assertEqual(a.total_delta, 0)
        b = next(c for c in rep.cohorts if c.key == dms_cohort_key(
            {"model": "QX80", "model_year": "2026", "model_code": "83816", "ext": "WHT", "int": "BLK"}))
        self.assertEqual((b.ons_delta, b.dlr_delta), (0, 0))

    def test_new_and_gone_cohorts(self):
        self.imp([A("ONS", "a1")], effective_time=DAY0)
        self.imp([B("ONS", "b1")], effective_time=DAY1)
        rep = self.delta.latest_delta(self.sid, SCOPE)
        self.assertEqual(len(rep.new_cohorts), 1)            # B appeared
        self.assertEqual(len(rep.gone_cohorts), 1)           # A no longer observed


class TestMovementInference(_Base):
    # K(cont). clean INCOMING->ARRIVED movement -> APPARENT_COHORT_ARRIVAL, provisional, never same-unit.
    def test_clean_apparent_arrival(self):
        self.imp(T0, effective_time=DAY0)
        self.imp(T1, effective_time=DAY1)
        sigs = movement_signals(self.delta.latest_delta(self.sid, SCOPE))
        arr = [s for s in sigs if s.signal == "APPARENT_COHORT_ARRIVAL"]
        self.assertEqual(len(arr), 1)
        s = arr[0]
        self.assertEqual((s.from_stage, s.to_stage), ("INCOMING", "ARRIVED"))
        self.assertEqual(s.inferred_net_movement, 2)
        self.assertEqual(s.confidence, "provisional")
        self.assertEqual(s.ambiguity_reasons, [])
        # every emitted signal is cohort-level and never "proven"
        self.assertTrue(all(x.confidence in ("provisional", "ambiguous") for x in sigs))

    # L. confounded movement stays AMBIGUOUS and never becomes a proven / same-unit claim.
    def test_ambiguous_movement_not_proven(self):
        self.imp(T0, effective_time=DAY0)
        self.imp(T1B, effective_time=DAY1)
        sigs = movement_signals(self.delta.latest_delta(self.sid, SCOPE))
        arr = next(x for x in sigs if x.signal == "APPARENT_COHORT_ARRIVAL")
        self.assertEqual(arr.confidence, "ambiguous")
        self.assertTrue(arr.ambiguity_reasons)
        self.assertNotIn(arr.confidence, ("proven", "certain"))

    # stage-progression signals are distinct and cohort-level. Cohort A shows SIT->NNA-INV; cohort B
    # (different model) shows NNA-INV->DLR-INV. A single cohort's net NNA delta cannot show both.
    def test_stage_progression_signals(self):
        t0 = ([A("SIT", f"sA-{i}") for i in range(4)] + [A("NNA-INV", f"nA-{i}") for i in range(2)]
              + [B("NNA-INV", f"nB-{i}") for i in range(3)] + [B("DLR-INV", f"dB-{i}") for i in range(1)])
        t1 = ([A("SIT", f"sA-{i}") for i in range(2)] + [A("NNA-INV", f"nA-{i}") for i in range(4)]
              + [B("NNA-INV", f"nB-{i}") for i in range(1)] + [B("DLR-INV", f"dB-{i}") for i in range(3)])
        self.imp(t0, effective_time=DAY0)
        self.imp(t1, effective_time=DAY1)
        sigs = movement_signals(self.delta.latest_delta(self.sid, SCOPE))
        kinds = {s.signal for s in sigs}
        self.assertIn("APPARENT_SEA_TO_US_INVENTORY", kinds)             # cohort A: SIT down + NNA-INV up
        self.assertIn("APPARENT_US_INVENTORY_TO_DEALER_ARRIVAL", kinds)  # cohort B: NNA-INV down + DLR-INV up
        sea = next(s for s in sigs if s.signal == "APPARENT_SEA_TO_US_INVENTORY")
        self.assertEqual((sea.from_stage, sea.to_stage), ("SIT", "NNA-INV"))
        self.assertEqual(sea.inferred_net_movement, 2)
        self.assertEqual(sea.confidence, "provisional")
        us = next(s for s in sigs if s.signal == "APPARENT_US_INVENTORY_TO_DEALER_ARRIVAL")
        self.assertEqual((us.from_stage, us.to_stage), ("NNA-INV", "DLR-INV"))
        # never a same-unit claim: every signal is cohort-level with a provisional/ambiguous confidence
        self.assertTrue(all(s.confidence in ("provisional", "ambiguous") for s in sigs))


class TestDisAndSafety(_Base):
    # M. DIS aging is authoritative per snapshot; history is derivable.
    def test_dis_history(self):
        self.imp(T0, effective_time=DAY0)
        self.imp(T1, effective_time=DAY1)
        snaps = self.reader.list_snapshots(self.sid, SCOPE)
        d0 = self.reader.dis_distribution(snaps[0])
        self.assertEqual(d0["count"], 2)
        self.assertEqual((d0["min"], d0["max"]), (12, 40))
        cur = self.reader.current_aging(self.sid, SCOPE)     # latest snapshot DLR-INV DIS
        self.assertEqual(cur["count"], 4)
        self.assertEqual(sorted(cur["values"]), [1, 2, 13, 41])
        self.assertEqual(cur["min"], 1)
        self.assertEqual(cur["max"], 41)

    def test_source_stage_and_planning_state(self):
        # exact source stage comes from Location (case/space-insensitive); planning state is derived.
        self.assertEqual(INVENTORY_STATE_FIELD, "location")
        self.assertEqual(SOURCE_STAGES, ("ONS", "SIT", "NNA-INV", "DLR-INV", "OTHER"))
        for raw, stage, plan in [
            ("ONS", "ONS", "INCOMING"),
            (" sit ", "SIT", "INCOMING"),
            ("nna-inv", "NNA-INV", "INCOMING"),
            ("DLR-INV", "DLR-INV", "ARRIVED"),
            ("Deal Opened", "OTHER", "OTHER"),
            ("", "OTHER", "OTHER"),
        ]:
            self.assertEqual(classify_source_stage(raw), stage)
            self.assertEqual(planning_state_of(classify_source_stage(raw)), plan)
            self.assertEqual(dms_source_stage({"location": raw, "status": "Deal Opened"}), stage)
            self.assertEqual(dms_planning_state({"location": raw, "status": "Deal Opened"}), plan)
        # Status must NEVER override Location: DLR-INV in Status but SIT in Location -> SIT / INCOMING
        self.assertEqual(dms_source_stage({"location": "SIT", "status": "DLR-INV"}), "SIT")
        self.assertEqual(dms_planning_state({"location": "SIT", "status": "DLR-INV"}), "INCOMING")

    def test_status_field_preserved_as_evidence(self):
        # importing does not discard Status; it is retained verbatim in the observation row
        self.imp([A("NNA-INV", "s1")], effective_time=DAY0)
        rows = self.reader.snapshot_rows(self.reader.latest_snapshot(self.sid, SCOPE))
        self.assertEqual(rows[0]["status"], "Deal Opened")       # preserved
        self.assertEqual(rows[0]["location"], "NNA-INV")         # drives the stage
        self.assertEqual(dms_source_stage(rows[0]), "NNA-INV")
        self.assertEqual(dms_planning_state(rows[0]), "INCOMING")

    # N. observation-only: no ProductionOrder / VehicleUnit / business fact created.
    def test_no_business_entities_created(self):
        self.imp(T0, effective_time=DAY0)
        self.imp(T1, effective_time=DAY1)
        self.assertEqual(self._count("business_fact"), 0)
        self.assertEqual(self._count("production_order"), 0)
        self.assertEqual(self._count("vehicle_unit"), 0)
        self.assertGreater(self._count("source_observation"), 0)
        self.assertTrue(all(
            r["identity_status"] == "unresolved" for r in self.conn.execute(
                "SELECT identity_status FROM source_observation").fetchall()))

    # schema must remain v12 throughout.
    def test_schema_stays_v12(self):
        self.imp(T0, effective_time=DAY0)
        self.assertEqual(current_version(self.conn), 12)


class TestPipelineStages(_Base):
    # A cohort observed across all four defined stages, then progressed one snapshot later.
    def _four_stage(self, ons, sit, nna, dlr_dis):
        rows = [A("ONS", f"o-{i}") for i in range(ons)]
        rows += [A("SIT", f"s-{i}") for i in range(sit)]
        rows += [A("NNA-INV", f"n-{i}") for i in range(nna)]
        rows += [A("DLR-INV", f"d-{i}", dlr_dis[i]) for i in range(len(dlr_dis))]
        return rows

    def test_exact_source_stage_and_planning_state_deltas(self):
        # T0: ONS=5, SIT=4, NNA-INV=2, DLR-INV=2 ; T1: ONS=3, SIT=2, NNA-INV=3, DLR-INV=4
        self.imp(self._four_stage(5, 4, 2, [10, 20]), effective_time=DAY0)
        self.imp(self._four_stage(3, 2, 3, [10, 20, 1, 2]), effective_time=DAY1)
        rep = self.delta.latest_delta(self.sid, SCOPE)
        c = next(x for x in rep.cohorts if x.label.startswith("QX60"))
        # A. exact source-stage deltas
        self.assertEqual((c.ons_prev, c.ons_curr, c.ons_delta), (5, 3, -2))
        self.assertEqual((c.sit_prev, c.sit_curr, c.sit_delta), (4, 2, -2))
        self.assertEqual((c.nna_prev, c.nna_curr, c.nna_delta), (2, 3, 1))
        self.assertEqual((c.dlr_prev, c.dlr_curr, c.dlr_delta), (2, 4, 2))
        self.assertEqual(c.other_delta, 0)
        # B. broader planning-state deltas  (INCOMING = ONS+SIT+NNA-INV ; ARRIVED = DLR-INV)
        self.assertEqual((c.incoming_prev, c.incoming_curr, c.incoming_delta), (11, 8, -3))
        self.assertEqual((c.arrived_prev, c.arrived_curr, c.arrived_delta), (2, 4, 2))
        self.assertEqual(c.total_delta, -1)

    def test_dis_aging_only_dlr_inv(self):
        # SIT / NNA-INV / ONS rows carry DIS-like values but must NEVER contribute to dealer DIS aging.
        rows = ([R(serial="o1", location="ONS", dis=999)]
                + [R(serial="s1", location="SIT", dis=888)]
                + [R(serial="n1", location="NNA-INV", dis=777)]
                + [R(serial="d1", location="DLR-INV", dis=0),
                   R(serial="d2", location="DLR-INV", dis=40),
                   R(serial="d3", location="DLR-INV", dis=187)])
        self.imp(rows, effective_time=DAY0)
        aging = self.reader.current_aging(self.sid, SCOPE)
        self.assertEqual(aging["count"], 3)                       # only the 3 DLR-INV rows
        self.assertEqual(sorted(aging["values"]), [0, 40, 187])   # 999/888/777 excluded
        self.assertEqual((aging["min"], aging["max"]), (0, 187))

    def test_incoming_stages_have_no_dis(self):
        self.imp([R(serial="s1", location="SIT", dis=500),
                  R(serial="n1", location="NNA-INV", dis=400)], effective_time=DAY0)
        aging = self.reader.current_aging(self.sid, SCOPE)
        self.assertEqual(aging["count"], 0)                       # no arrived rows -> no aging


if __name__ == "__main__":
    unittest.main(verbosity=2)
