"""SQLite repositories for Phase 4 New Inventory records (behind method contracts).

Issued results (Demand / forecast / plan / portfolio) are append-preserving (DB triggers
block deletes). Supply/retail projections are recomputable snapshots; issued planning
outputs are never mutated in place.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id
from .models import (AvailabilityInterval, CombinationLineage, CurrentSupply, DemandResult,
                     DesiredCoverageResolution, ForecastMonth, ForecastResult, FutureSupply,
                     InventoryPlanMonth, InventoryPlanResult, PortfolioPlanResult, RetailHistory,
                     SellableCombination, SupplyCommitment)


def _j(v):
    return json.dumps(v)


def _l(s):
    return json.loads(s) if s else []


def _d(s):
    return json.loads(s) if s else {}


class NewInvStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- Sellable Combination ---------------------------------------------
    def add_combination(self, c: SellableCombination) -> SellableCombination:
        c.created_at = c.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO sellable_combination(id,store_scope,franchise,model,model_year,trim,drivetrain,"
                "exterior_color,interior_color,canonical_identity,source_refs,quality_status,status,lineage_metadata,"
                "correction_of,created_at,corrected_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.store_scope, c.franchise, c.model, c.model_year, c.trim, c.drivetrain, c.exterior_color,
                 c.interior_color, c.canonical_identity, _j(c.source_refs), c.quality_status, c.status,
                 _j(c.lineage_metadata), c.correction_of, c.created_at, c.corrected_at, c.version))
        return c

    def get_combination(self, cid):
        return self._comb(self.conn.execute("SELECT * FROM sellable_combination WHERE id=?", (cid,)).fetchone())

    def find_combination_by_identity(self, canonical_identity, scope, *, active_only=True):
        q = ("SELECT * FROM sellable_combination WHERE canonical_identity=? AND store_scope=?"
             + (" AND status='active'" if active_only else "") + " ORDER BY created_at LIMIT 1")
        return self._comb(self.conn.execute(q, (canonical_identity, scope)).fetchone())

    def set_combination_status(self, cid, expected_version, status, *, corrected_at=None):
        with self.conn:
            self.conn.execute("UPDATE sellable_combination SET status=?,corrected_at=COALESCE(?,corrected_at),"
                              "version=version+1 WHERE id=? AND version=?", (status, corrected_at, cid, expected_version))
        return self.get_combination(cid)

    @staticmethod
    def _comb(r):
        if not r:
            return None
        return SellableCombination(
            id=r["id"], store_scope=r["store_scope"], franchise=r["franchise"], model=r["model"],
            model_year=r["model_year"], trim=r["trim"], drivetrain=r["drivetrain"], exterior_color=r["exterior_color"],
            interior_color=r["interior_color"], canonical_identity=r["canonical_identity"],
            source_refs=_l(r["source_refs"]), quality_status=r["quality_status"], status=r["status"],
            lineage_metadata=_d(r["lineage_metadata"]), correction_of=r["correction_of"], created_at=r["created_at"],
            corrected_at=r["corrected_at"], version=r["version"])

    def add_combination_alias(self, combination_id, alias_type, alias_value, scope, source_ref=None):
        with self.conn:
            self.conn.execute("INSERT INTO sellable_combination_alias(id,combination_id,alias_type,alias_value,"
                              "store_scope,source_ref,created_at) VALUES(?,?,?,?,?,?,?)",
                              (new_id("sca"), combination_id, alias_type, alias_value, scope, source_ref, self._now()))

    def aliases_for(self, combination_id):
        return self.conn.execute("SELECT * FROM sellable_combination_alias WHERE combination_id=? ORDER BY created_at",
                                 (combination_id,)).fetchall()

    def add_lineage(self, ln: CombinationLineage) -> CombinationLineage:
        ln.created_at = ln.created_at or self._now()
        with self.conn:
            self.conn.execute("INSERT INTO combination_lineage(id,from_combination_id,to_combination_id,relationship,"
                              "comparability,approved_rule_ref,evidence_refs,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                              (ln.id, ln.from_combination_id, ln.to_combination_id, ln.relationship, ln.comparability,
                               ln.approved_rule_ref, _j(ln.evidence_refs), ln.status, ln.created_at))
        return ln

    def lineage_into(self, to_combination_id):
        rows = self.conn.execute("SELECT * FROM combination_lineage WHERE to_combination_id=? AND status='active'",
                                 (to_combination_id,)).fetchall()
        return [CombinationLineage(id=r["id"], from_combination_id=r["from_combination_id"],
                                   to_combination_id=r["to_combination_id"], relationship=r["relationship"],
                                   comparability=r["comparability"], approved_rule_ref=r["approved_rule_ref"],
                                   evidence_refs=_l(r["evidence_refs"]), status=r["status"], created_at=r["created_at"])
                for r in rows]

    # ---- Current Supply ----------------------------------------------------
    def add_current_supply(self, s: CurrentSupply) -> CurrentSupply:
        s.calculation_timestamp = s.calculation_timestamp or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO current_supply_projection(id,vehicle_unit_id,combination_id,store_scope,availability_state,"
                "arrival_date,available_for_retail_date,age_days,source_state_refs,fact_refs,retail_eligible,"
                "exclusion_reason,quality_status,confidence,calculation_timestamp,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s.id, s.vehicle_unit_id, s.combination_id, s.store_scope, s.availability_state, s.arrival_date,
                 s.available_for_retail_date, s.age_days, _j(s.source_state_refs), _j(s.fact_refs),
                 int(s.retail_eligible), s.exclusion_reason, s.quality_status, s.confidence,
                 s.calculation_timestamp, s.status))
        return s

    def current_supply_for(self, combination_id, scope, *, eligible_only=False):
        q = ("SELECT * FROM current_supply_projection WHERE combination_id=? AND store_scope=? AND status='current'"
             + (" AND retail_eligible=1" if eligible_only else "") + " ORDER BY calculation_timestamp,id")
        return [self._cur(r) for r in self.conn.execute(q, (combination_id, scope)).fetchall()]

    @staticmethod
    def _cur(r):
        return CurrentSupply(
            id=r["id"], store_scope=r["store_scope"], availability_state=r["availability_state"],
            vehicle_unit_id=r["vehicle_unit_id"], combination_id=r["combination_id"], arrival_date=r["arrival_date"],
            available_for_retail_date=r["available_for_retail_date"], age_days=r["age_days"],
            source_state_refs=_l(r["source_state_refs"]), fact_refs=_l(r["fact_refs"]),
            retail_eligible=bool(r["retail_eligible"]), exclusion_reason=r["exclusion_reason"],
            quality_status=r["quality_status"], confidence=r["confidence"],
            calculation_timestamp=r["calculation_timestamp"], status=r["status"])

    # ---- Future Supply -----------------------------------------------------
    def add_future_supply(self, s: FutureSupply) -> FutureSupply:
        s.calculation_timestamp = s.calculation_timestamp or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO future_supply_projection(id,production_order_id,combination_id,store_scope,production_state,"
                "eta_start,eta_end,arrival_month,timing_confidence,editability,cancellation_status,source_refs,fact_refs,"
                "identity_linkage,quality_status,calculation_timestamp,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s.id, s.production_order_id, s.combination_id, s.store_scope, s.production_state, s.eta_start,
                 s.eta_end, s.arrival_month, s.timing_confidence, s.editability, s.cancellation_status,
                 _j(s.source_refs), _j(s.fact_refs), _j(s.identity_linkage), s.quality_status,
                 s.calculation_timestamp, s.status))
        return s

    def future_supply_for(self, combination_id, scope, *, active_only=True):
        q = ("SELECT * FROM future_supply_projection WHERE combination_id=? AND store_scope=? AND status='current'"
             + (" AND (cancellation_status IS NULL OR cancellation_status='')" if active_only else "")
             + " ORDER BY arrival_month,id")
        return [self._fut(r) for r in self.conn.execute(q, (combination_id, scope)).fetchall()]

    @staticmethod
    def _fut(r):
        return FutureSupply(
            id=r["id"], store_scope=r["store_scope"], production_order_id=r["production_order_id"],
            combination_id=r["combination_id"], production_state=r["production_state"], eta_start=r["eta_start"],
            eta_end=r["eta_end"], arrival_month=r["arrival_month"], timing_confidence=r["timing_confidence"],
            editability=r["editability"], cancellation_status=r["cancellation_status"], source_refs=_l(r["source_refs"]),
            fact_refs=_l(r["fact_refs"]), identity_linkage=_d(r["identity_linkage"]), quality_status=r["quality_status"],
            calculation_timestamp=r["calculation_timestamp"], status=r["status"])

    # ---- Committed Supply --------------------------------------------------
    def add_commitment(self, c: SupplyCommitment) -> SupplyCommitment:
        c.created_at = c.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO supply_commitment(id,unit_or_order_id,unit_identity_kind,combination_id,store_scope,"
                "commitment_type,decision_ref,approval_time,expected_supply_timing,arrival_month,lifecycle_status,"
                "commitment_source,supersedes,superseded_by,cancellation_status,fact_refs,audit_refs,created_at,version)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.unit_or_order_id, c.unit_identity_kind, c.combination_id, c.store_scope, c.commitment_type,
                 c.decision_ref, c.approval_time, c.expected_supply_timing, c.arrival_month, c.lifecycle_status,
                 c.commitment_source, c.supersedes, c.superseded_by, c.cancellation_status, _j(c.fact_refs),
                 _j(c.audit_refs), c.created_at, c.version))
        return c

    def get_commitment(self, cid):
        return self._commit(self.conn.execute("SELECT * FROM supply_commitment WHERE id=?", (cid,)).fetchone())

    def set_commitment_status(self, cid, expected_version, lifecycle_status, *, cancellation_status=None,
                              superseded_by=None):
        with self.conn:
            self.conn.execute("UPDATE supply_commitment SET lifecycle_status=?,cancellation_status=COALESCE(?,"
                              "cancellation_status),superseded_by=COALESCE(?,superseded_by),version=version+1"
                              " WHERE id=? AND version=?",
                              (lifecycle_status, cancellation_status, superseded_by, cid, expected_version))
        return self.get_commitment(cid)

    def commitments_for(self, combination_id, scope, *, committed_only=False):
        q = ("SELECT * FROM supply_commitment WHERE combination_id=? AND store_scope=?"
             + (" AND lifecycle_status='committed'" if committed_only else "") + " ORDER BY created_at,id")
        return [self._commit(r) for r in self.conn.execute(q, (combination_id, scope)).fetchall()]

    @staticmethod
    def _commit(r):
        if not r:
            return None
        return SupplyCommitment(
            id=r["id"], store_scope=r["store_scope"], commitment_type=r["commitment_type"],
            unit_or_order_id=r["unit_or_order_id"], unit_identity_kind=r["unit_identity_kind"],
            combination_id=r["combination_id"], decision_ref=r["decision_ref"], approval_time=r["approval_time"],
            expected_supply_timing=r["expected_supply_timing"], arrival_month=r["arrival_month"],
            lifecycle_status=r["lifecycle_status"], commitment_source=r["commitment_source"], supersedes=r["supersedes"],
            superseded_by=r["superseded_by"], cancellation_status=r["cancellation_status"], fact_refs=_l(r["fact_refs"]),
            audit_refs=_l(r["audit_refs"]), created_at=r["created_at"], version=r["version"])

    # ---- Historical Retail -------------------------------------------------
    def add_retail(self, rh: RetailHistory) -> RetailHistory:
        rh.created_at = rh.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO retail_history_projection(id,retail_event_ref,vehicle_unit_id,combination_id,store_scope,"
                "retail_date,retail_month,arrival_refs,availability_refs,model_year,source_refs,fact_refs,quality_status,"
                "status,correction_of,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rh.id, rh.retail_event_ref, rh.vehicle_unit_id, rh.combination_id, rh.store_scope, rh.retail_date,
                 rh.retail_month, _j(rh.arrival_refs), _j(rh.availability_refs), rh.model_year, _j(rh.source_refs),
                 _j(rh.fact_refs), rh.quality_status, rh.status, rh.correction_of, rh.created_at))
        return rh

    def set_retail_status(self, rid, status):
        with self.conn:
            self.conn.execute("UPDATE retail_history_projection SET status=? WHERE id=?", (status, rid))

    def retail_for(self, combination_id, scope, *, current_only=True):
        q = ("SELECT * FROM retail_history_projection WHERE combination_id=? AND store_scope=?"
             + (" AND status='current'" if current_only else "") + " ORDER BY retail_date,id")
        return [self._retail(r) for r in self.conn.execute(q, (combination_id, scope)).fetchall()]

    @staticmethod
    def _retail(r):
        return RetailHistory(
            id=r["id"], store_scope=r["store_scope"], combination_id=r["combination_id"],
            vehicle_unit_id=r["vehicle_unit_id"], retail_event_ref=r["retail_event_ref"], retail_date=r["retail_date"],
            retail_month=r["retail_month"], arrival_refs=_l(r["arrival_refs"]), availability_refs=_l(r["availability_refs"]),
            model_year=r["model_year"], source_refs=_l(r["source_refs"]), fact_refs=_l(r["fact_refs"]),
            quality_status=r["quality_status"], status=r["status"], correction_of=r["correction_of"],
            created_at=r["created_at"])

    # ---- Availability ------------------------------------------------------
    def add_availability(self, a: AvailabilityInterval) -> AvailabilityInterval:
        a.created_at = a.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO availability_interval(id,combination_id,store_scope,bucket,period_start,period_end,"
                "available_state,available_unit_days,opening_depth,closing_depth,arrivals,retail_events,stockout_periods,"
                "source_refs,fact_refs,quality_status,confidence,unresolved_gaps,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (a.id, a.combination_id, a.store_scope, a.bucket, a.period_start, a.period_end, a.available_state,
                 a.available_unit_days, a.opening_depth, a.closing_depth, a.arrivals, a.retail_events,
                 _j(a.stockout_periods), _j(a.source_refs), _j(a.fact_refs), a.quality_status, a.confidence,
                 _j(a.unresolved_gaps), a.created_at))
        return a

    def availability_for(self, combination_id, scope):
        rows = self.conn.execute("SELECT * FROM availability_interval WHERE combination_id=? AND store_scope=?"
                                 " ORDER BY period_start,id", (combination_id, scope)).fetchall()
        return [self._avail(r) for r in rows]

    @staticmethod
    def _avail(r):
        return AvailabilityInterval(
            id=r["id"], store_scope=r["store_scope"], available_state=r["available_state"],
            combination_id=r["combination_id"], bucket=r["bucket"], period_start=r["period_start"],
            period_end=r["period_end"], available_unit_days=r["available_unit_days"], opening_depth=r["opening_depth"],
            closing_depth=r["closing_depth"], arrivals=r["arrivals"], retail_events=r["retail_events"],
            stockout_periods=_l(r["stockout_periods"]), source_refs=_l(r["source_refs"]), fact_refs=_l(r["fact_refs"]),
            quality_status=r["quality_status"], confidence=r["confidence"], unresolved_gaps=_l(r["unresolved_gaps"]),
            created_at=r["created_at"])

    # ---- Demand result -----------------------------------------------------
    def add_demand(self, d: DemandResult) -> DemandResult:
        d.issued_time = d.issued_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO demand_result(id,combination_id,store_scope,horizon_start,horizon_end,monthly_expected,"
                "baseline_evidence,evidence_tier,direct_evidence,availability_adjustment,seasonality_ref,trend_ref,"
                "confidence,uncertainty,policy_versions,calculation_version,source_refs,fact_refs,reproducibility_package,"
                "scenario_id,issued_time,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d.id, d.combination_id, d.store_scope, d.horizon_start, d.horizon_end, _j(d.monthly_expected),
                 _j(d.baseline_evidence), d.evidence_tier, int(d.direct_evidence), d.availability_adjustment,
                 _j(d.seasonality_ref), _j(d.trend_ref), d.confidence, _j(d.uncertainty), _j(d.policy_versions),
                 d.calculation_version, _j(d.source_refs), _j(d.fact_refs), d.reproducibility_package, d.scenario_id,
                 d.issued_time, d.status))
        self._index_output("demand", d.id, d.combination_id, d.store_scope, d.calculation_version,
                           d.reproducibility_package, d.scenario_id, d.issued_time)
        return d

    def get_demand(self, did):
        r = self.conn.execute("SELECT * FROM demand_result WHERE id=?", (did,)).fetchone()
        if not r:
            return None
        return DemandResult(
            id=r["id"], store_scope=r["store_scope"], combination_id=r["combination_id"],
            horizon_start=r["horizon_start"], horizon_end=r["horizon_end"], monthly_expected=_d(r["monthly_expected"]),
            baseline_evidence=_d(r["baseline_evidence"]), evidence_tier=r["evidence_tier"],
            direct_evidence=bool(r["direct_evidence"]), availability_adjustment=r["availability_adjustment"],
            seasonality_ref=_d(r["seasonality_ref"]), trend_ref=_d(r["trend_ref"]), confidence=r["confidence"],
            uncertainty=_d(r["uncertainty"]), policy_versions=_l(r["policy_versions"]),
            calculation_version=r["calculation_version"], source_refs=_l(r["source_refs"]), fact_refs=_l(r["fact_refs"]),
            reproducibility_package=r["reproducibility_package"], scenario_id=r["scenario_id"],
            issued_time=r["issued_time"], status=r["status"])

    # ---- Forecast ----------------------------------------------------------
    def add_forecast(self, f: ForecastResult) -> ForecastResult:
        with self.conn:
            self.conn.execute(
                "INSERT INTO forecast_result(id,combination_id,store_scope,issue_date,horizon_start,horizon_end,"
                "total_expected,confidence,input_state_refs,policy_versions,calculation_version,lineage_refs,scenario_id,"
                "reproducibility_package,demand_result_id,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f.id, f.combination_id, f.store_scope, f.issue_date, f.horizon_start, f.horizon_end, f.total_expected,
                 f.confidence, _j(f.input_state_refs), _j(f.policy_versions), f.calculation_version, _j(f.lineage_refs),
                 f.scenario_id, f.reproducibility_package, f.demand_result_id, f.status))
            for m in f.months:
                self.conn.execute("INSERT INTO forecast_month(id,forecast_id,month,expected_retail,cumulative_expected,"
                                  "confidence,seq) VALUES(?,?,?,?,?,?,?)",
                                  (m.id, f.id, m.month, m.expected_retail, m.cumulative_expected, m.confidence, m.seq))
        self._index_output("forecast", f.id, f.combination_id, f.store_scope, f.calculation_version,
                           f.reproducibility_package, f.scenario_id, f.issue_date)
        return f

    def get_forecast(self, fid):
        r = self.conn.execute("SELECT * FROM forecast_result WHERE id=?", (fid,)).fetchone()
        if not r:
            return None
        months = [ForecastMonth(id=mr["id"], forecast_id=fid, month=mr["month"], expected_retail=mr["expected_retail"],
                                cumulative_expected=mr["cumulative_expected"], confidence=mr["confidence"], seq=mr["seq"])
                  for mr in self.conn.execute("SELECT * FROM forecast_month WHERE forecast_id=? ORDER BY seq",
                                              (fid,)).fetchall()]
        return ForecastResult(
            id=r["id"], store_scope=r["store_scope"], issue_date=r["issue_date"], combination_id=r["combination_id"],
            horizon_start=r["horizon_start"], horizon_end=r["horizon_end"], total_expected=r["total_expected"],
            confidence=r["confidence"], input_state_refs=_l(r["input_state_refs"]),
            policy_versions=_l(r["policy_versions"]), calculation_version=r["calculation_version"],
            lineage_refs=_l(r["lineage_refs"]), scenario_id=r["scenario_id"],
            reproducibility_package=r["reproducibility_package"], demand_result_id=r["demand_result_id"],
            status=r["status"], months=months)

    def forecasts_for(self, combination_id, scope):
        return [self.get_forecast(r["id"]) for r in self.conn.execute(
            "SELECT id FROM forecast_result WHERE combination_id=? AND store_scope=? ORDER BY issue_date,id",
            (combination_id, scope)).fetchall()]

    # ---- Desired coverage --------------------------------------------------
    def add_coverage(self, c: DesiredCoverageResolution) -> DesiredCoverageResolution:
        c.created_at = c.created_at or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO desired_coverage_resolution(id,combination_id,store_scope,policy_version,scope,"
                "effective_period,unit_contract,resolved_value,resolution_status,fallback_used,note,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.combination_id, c.store_scope, c.policy_version, _j(c.scope), _j(c.effective_period),
                 c.unit_contract, _j(c.resolved_value), c.resolution_status, int(c.fallback_used), c.note, c.created_at))
        return c

    # ---- Inventory plan ----------------------------------------------------
    def add_plan(self, p: InventoryPlanResult) -> InventoryPlanResult:
        p.issued_time = p.issued_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO inventory_plan_result(id,combination_id,store_scope,evaluated_start,evaluated_end,"
                "expected_demand,current_supply,future_supply,committed_supply,qualifying_supply,desired_ending_coverage,"
                "need,excess,planning_state,confidence,evidence,policy_versions,calculation_version,reproducibility_package,"
                "demand_result_id,scenario_id,issued_time,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.combination_id, p.store_scope, p.evaluated_start, p.evaluated_end, p.expected_demand,
                 p.current_supply, p.future_supply, p.committed_supply, p.qualifying_supply,
                 _j(p.desired_ending_coverage), p.need, p.excess, p.planning_state, p.confidence, _j(p.evidence),
                 _j(p.policy_versions), p.calculation_version, p.reproducibility_package, p.demand_result_id,
                 p.scenario_id, p.issued_time, p.status))
            for m in p.months:
                self.conn.execute("INSERT INTO inventory_plan_month(id,plan_id,month,expected_demand,cumulative_demand,"
                                  "cumulative_supply,shortage,excess,confidence,seq) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                  (m.id, p.id, m.month, m.expected_demand, m.cumulative_demand, m.cumulative_supply,
                                   m.shortage, m.excess, m.confidence, m.seq))
        self._index_output("inventory_plan", p.id, p.combination_id, p.store_scope, p.calculation_version,
                           p.reproducibility_package, p.scenario_id, p.issued_time)
        return p

    def get_plan(self, pid):
        r = self.conn.execute("SELECT * FROM inventory_plan_result WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        months = [InventoryPlanMonth(id=mr["id"], plan_id=pid, month=mr["month"], expected_demand=mr["expected_demand"],
                                     cumulative_demand=mr["cumulative_demand"], cumulative_supply=mr["cumulative_supply"],
                                     shortage=mr["shortage"], excess=mr["excess"], confidence=mr["confidence"],
                                     seq=mr["seq"])
                  for mr in self.conn.execute("SELECT * FROM inventory_plan_month WHERE plan_id=? ORDER BY seq",
                                              (pid,)).fetchall()]
        return InventoryPlanResult(
            id=r["id"], store_scope=r["store_scope"], planning_state=r["planning_state"],
            combination_id=r["combination_id"], evaluated_start=r["evaluated_start"], evaluated_end=r["evaluated_end"],
            expected_demand=r["expected_demand"], current_supply=r["current_supply"], future_supply=r["future_supply"],
            committed_supply=r["committed_supply"], qualifying_supply=r["qualifying_supply"],
            desired_ending_coverage=_d(r["desired_ending_coverage"]), need=r["need"], excess=r["excess"],
            confidence=r["confidence"], evidence=_d(r["evidence"]), policy_versions=_l(r["policy_versions"]),
            calculation_version=r["calculation_version"], reproducibility_package=r["reproducibility_package"],
            demand_result_id=r["demand_result_id"], scenario_id=r["scenario_id"], issued_time=r["issued_time"],
            status=r["status"], months=months)

    # ---- Portfolio ---------------------------------------------------------
    def add_portfolio(self, p: PortfolioPlanResult) -> PortfolioPlanResult:
        p.issued_time = p.issued_time or self._now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO portfolio_plan_result(id,store_scope,evaluated_start,evaluated_end,level,grouping_key,"
                "summary,plan_refs,monthly_demand,supply_by_state,need,excess,unresolved_quantity,confidence,timing_risk,"
                "calculation_version,issued_time,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.store_scope, p.evaluated_start, p.evaluated_end, p.level, p.grouping_key, _j(p.summary),
                 _j(p.plan_refs), _j(p.monthly_demand), _j(p.supply_by_state), p.need, p.excess, p.unresolved_quantity,
                 p.confidence, p.timing_risk, p.calculation_version, p.issued_time, p.status))
        self._index_output("portfolio", p.id, None, p.store_scope, p.calculation_version, None, None, p.issued_time)
        return p

    def get_portfolio(self, pid):
        r = self.conn.execute("SELECT * FROM portfolio_plan_result WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        return PortfolioPlanResult(
            id=r["id"], store_scope=r["store_scope"], level=r["level"], evaluated_start=r["evaluated_start"],
            evaluated_end=r["evaluated_end"], grouping_key=r["grouping_key"], summary=_d(r["summary"]),
            plan_refs=_l(r["plan_refs"]), monthly_demand=_d(r["monthly_demand"]), supply_by_state=_d(r["supply_by_state"]),
            need=r["need"], excess=r["excess"], unresolved_quantity=r["unresolved_quantity"], confidence=r["confidence"],
            timing_risk=r["timing_risk"], calculation_version=r["calculation_version"], issued_time=r["issued_time"],
            status=r["status"])

    # ---- issued-output index ----------------------------------------------
    def _index_output(self, output_type, output_id, combination_id, scope, calc_version, repro, scenario_id, issued):
        with self.conn:
            self.conn.execute(
                "INSERT INTO issued_planning_output(id,output_type,output_id,combination_id,store_scope,"
                "calculation_version,reproducibility_package,scenario_id,issued_time) VALUES(?,?,?,?,?,?,?,?,?)",
                (new_id("ipo"), output_type, output_id, combination_id, scope, calc_version, repro, scenario_id,
                 issued or self._now()))

    def issued_outputs(self, output_type=None):
        if output_type:
            rows = self.conn.execute("SELECT * FROM issued_planning_output WHERE output_type=? ORDER BY issued_time,id",
                                     (output_type,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM issued_planning_output ORDER BY issued_time,id").fetchall()
        return rows
