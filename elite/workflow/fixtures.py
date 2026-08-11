"""Deterministic Phase 5 fixtures: a wired production/workflow stack + synthetic scenarios.

Synthetic dealership data only — no real manufacturer CPO/PPO policy, incentives, allowances, or
windows. Distinct proposer / approver / completer principals prove separation of authority.
"""
from __future__ import annotations

from ..newinv.fixtures import HORIZON, OTHER_SCOPE, SCOPE, Phase4
from .cpo import CpoService
from .ctp import CtpService
from .dealer_trade import DealerTradeService
from .integrate import IntegrateService
from .pipeline import PipelineService
from .ppo import PpoService
from .risk import IncomingRiskService, late_arrival, excessive_depth, model_year_transition_risk
from .sequential import SequentialPlanner
from .store import WorkflowStore

ALL_WF_CAPS = ["production.view", "production.propose", "production.approve", "production.execute",
               "cpo.propose", "cpo.approve", "ppo.propose", "ppo.approve", "dealer_trade.propose",
               "dealer_trade.approve", "dealer_trade.complete", "ctp.propose", "ctp.approve",
               "ctp.execute", "workflow.cancel", "workflow.supersede"]
PROPOSE_CAPS = [c for c in ALL_WF_CAPS if c.endswith(".propose") or c == "production.view"]
APPROVE_CAPS = [c for c in ALL_WF_CAPS if c.endswith(".approve")]
COMPLETE_CAPS = ["dealer_trade.complete", "production.execute", "ctp.execute"]


class Phase5:
    def __init__(self, db_path, *, seed=True):
        self.p4 = Phase4(db_path, seed=seed)                     # migrates v1-v4
        self.stack = self.p4.stack
        self.clock = self.stack.clock
        self.stack.db.migrate()                       # apply v5
        self.ni = self.p4.store
        self.supply = self.p4.supply
        self.planning = self.p4.planning
        self.policy = self.p4.policy
        self.gov = self.p4.gov
        self.plan_cv = self.p4.plan_cv
        self.wf = WorkflowStore(self.stack.db.conn, self.clock)
        self.pipeline = PipelineService(self.wf, self.clock)
        self.risk = IncomingRiskService(self.wf, self.clock)
        self.cpo = CpoService(self.wf, self.ni, self.supply, self.gov, self.clock)
        self.ppo = PpoService(self.wf, self.ni, self.supply, self.gov, self.clock)
        self.dt = DealerTradeService(self.wf, self.ni, self.supply, self.gov, self.clock)
        self.ctp = CtpService(self.wf, self.ni, self.supply, self.gov, self.clock)
        self.integrate = IntegrateService(self.ni, self.supply, self.planning, self.wf, self.plan_cv)
        self.sequential = SequentialPlanner(self.ni, self.supply, self.planning, self.wf, self.clock, self.plan_cv)
        if seed:
            self._principals()

    def _principal(self, meta_key, name, caps):
        pid = self.stack.metadata.get(meta_key)
        if pid is None:
            pid = self.stack.authn.register(name, "pw").id
            self.stack.metadata.put_if_absent(meta_key, pid)
            for cap in caps:
                self.stack.grant(pid, cap, "*")
        return pid

    def _principals(self):
        self.full = self._principal("wf_full_id", "Workflow Full", ALL_WF_CAPS)
        self.proposer = self._principal("wf_proposer_id", "Workflow Proposer", PROPOSE_CAPS)
        self.approver = self._principal("wf_approver_id", "Workflow Approver", APPROVE_CAPS)
        self.completer = self._principal("wf_completer_id", "Workflow Completer", COMPLETE_CAPS)

    def reopen(self):
        return Phase5(self.stack.db.path)

    def close(self):
        self.stack.close()

    # ---- builders reused from Phase 4 -------------------------------------
    def combination(self, **kw):
        return self.p4.combination(**kw)

    def need_combo(self, *, per_month=2, exterior_color="BLACK", **kw):
        """A combination with stable demand history, its issued Demand, and an issued Need plan."""
        c = self.p4.combination(exterior_color=exterior_color, **kw)
        months = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p4.seed_retail(c, {m: per_month for m in months})
        self.p4.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": per_month,
                                      "snapshot": "full"} for m in months])
        d = self.p4.issue_demand(c)
        plan = self.p4.issue_plan(c, d, coverage_target=2)
        return c, d, plan

    def plan(self, comb, demand, *, coverage_target=2):
        return self.p4.issue_plan(comb, demand, coverage_target=coverage_target)


# ---------------------------------------------------------------------------
# 50 dealership-representative synthetic scenarios.
# ---------------------------------------------------------------------------
SCENARIO_NAMES = [
    "editable_order", "locked_order", "conditionally_editable", "unknown_editability", "exact_eta",
    "eta_range_within_month", "eta_range_crossing_months", "stale_eta", "revised_eta", "conflicting_eta",
    "outgoing_model_year", "incoming_model_year", "overlapping_model_years", "approved_lineage",
    "unsupported_lineage", "late_outgoing_unit", "low_risk_incoming", "late_arrival_risk", "excessive_depth_risk",
    "duplicate_commitment_risk", "cpo_proposal", "approved_cpo", "replayed_cpo_approval", "cancelled_cpo",
    "cpo_already_represented", "ppo_proposal", "approved_ppo", "rejected_ppo", "dealer_trade_proposal",
    "dealer_trade_request_sent", "dealer_trade_accepted_incomplete", "dealer_trade_completed",
    "dealer_trade_rejected", "dealer_trade_expired", "dealer_trade_failed", "dealer_trade_received_recon",
    "ctp_excess_to_need", "ctp_not_editable", "ctp_rejected", "ctp_accepted", "ctp_replay",
    "sequential_two_action", "sequential_becomes_unnecessary", "identity_conflict", "stale_approval",
    "unauthorized_approval", "audit_failure", "changed_commitment_new_output", "scenario_workflow_isolated",
    "completed_to_current",
]


def build_all_scenarios(p):
    """Construct all 50 scenarios; returns {name: handle}. Proves fixture completeness."""
    out = {}
    edit = p.pipeline.assess_editability
    # editability (1-4)
    o = "po_edit"
    out["editable_order"] = edit(o, SCOPE, "editable", editable_dimensions=["exterior_color"], cutoff="2026-09-01")
    out["locked_order"] = edit("po_lock", SCOPE, "locked")
    out["conditionally_editable"] = edit("po_cond", SCOPE, "conditionally_editable",
                                         unresolved_conditions=["allocation_pending"])
    out["unknown_editability"] = edit("po_unk", SCOPE, "unknown")
    # ETA (5-10)
    out["exact_eta"] = p.pipeline.record_eta("po_e1", "exact", eta_start="2026-10-12", arrival_month="2026-10")
    out["eta_range_within_month"] = p.pipeline.record_eta("po_e2", "range", eta_start="2026-10-05",
                                                          eta_end="2026-10-20", arrival_month="2026-10")
    out["eta_range_crossing_months"] = p.pipeline.record_eta("po_e3", "range", eta_start="2026-10-20",
                                                            eta_end="2026-11-08")
    out["stale_eta"] = p.pipeline.record_eta("po_e4", "month", arrival_month="2026-09", stale=True)
    p.pipeline.record_eta("po_e5", "month", arrival_month="2026-10")
    out["revised_eta"] = p.pipeline.record_eta("po_e5", "month", arrival_month="2026-11")   # revision preserves prior
    out["conflicting_eta"] = p.pipeline.record_eta("po_e6", "conflicting", conflicting=True)
    # model-year (11-15)
    out["outgoing_model_year"] = p.combination(model="QX80", model_year="2025", exterior_color="OUT")
    out["incoming_model_year"] = p.combination(model="QX80", model_year="2026", exterior_color="OUT")
    out["overlapping_model_years"] = p.pipeline.model_year_transition(SCOPE, "QX80", outgoing_model_year="2025",
                                                                     incoming_model_year="2026", overlap="2026-08..2026-11")
    a = p.combination(model="QX55", model_year="2025", exterior_color="LIN")
    b = p.combination(model="QX55", model_year="2026", exterior_color="LIN")
    out["approved_lineage"] = p.p4.combos.link_lineage(a.id, b.id, "new_model_year")
    oldg = p.combination(model="QX55", model_year="2022", exterior_color="GEN")
    newg = p.combination(model="QX55", model_year="2026", exterior_color="GEN2")
    out["unsupported_lineage"] = {"old": oldg, "new": newg}   # deliberately NOT linked
    # risk (16-20)
    out["late_outgoing_unit"] = p.pipeline.project("po_late_out", out["outgoing_model_year"].id, SCOPE,
                                                   order_status="open", arrival_month="2027-01")
    lowc = p.combination(exterior_color="LOWR")
    out["low_risk_incoming"] = p.risk.assess(subject_kind="future_supply", subject_ref="po_low",
                                             combination_id=lowc.id, scope=SCOPE, reasons=[])
    out["late_arrival_risk"] = p.risk.assess(subject_kind="future_supply", subject_ref="po_lar",
                                            combination_id=lowc.id, scope=SCOPE,
                                            reasons=[late_arrival("2027-03", "2026-12")])
    out["excessive_depth_risk"] = p.risk.assess(subject_kind="future_supply", subject_ref="po_dep",
                                               combination_id=lowc.id, scope=SCOPE, reasons=[excessive_depth(9, 3)])
    out["duplicate_commitment_risk"] = p.risk.assess(subject_kind="proposed_action", subject_ref="po_dup",
                                                    combination_id=lowc.id, scope=SCOPE,
                                                    reasons=[model_year_transition_risk()])
    # CPO (21-25)
    c1, d1, _ = p.need_combo(exterior_color="CPO1")
    out["cpo_proposal"] = p.cpo.propose(p.proposer, SCOPE, production_order_id="po_cpo1", combination_id=c1.id,
                                        arrival_month="2026-10")
    c2, d2, _ = p.need_combo(exterior_color="CPO2")
    w2 = p.cpo.propose(p.approver if False else p.full, SCOPE, production_order_id="po_cpo2", combination_id=c2.id,
                       arrival_month="2026-10")
    out["approved_cpo"] = p.cpo.approve(p.full, SCOPE, w2)
    c3, d3, _ = p.need_combo(exterior_color="CPO3")
    w3 = p.cpo.propose(p.full, SCOPE, production_order_id="po_cpo3", combination_id=c3.id, arrival_month="2026-10")
    p.cpo.approve(p.full, SCOPE, w3)
    out["replayed_cpo_approval"] = p.cpo.approve(p.full, SCOPE, p.wf.get_workflow(w3.id))   # idempotent replay
    c4, d4, _ = p.need_combo(exterior_color="CPO4")
    w4 = p.cpo.propose(p.full, SCOPE, production_order_id="po_cpo4", combination_id=c4.id, arrival_month="2026-10")
    p.cpo.approve(p.full, SCOPE, w4)
    out["cancelled_cpo"] = p.cpo.cancel(p.full, SCOPE, p.wf.get_workflow(w4.id),
                                        commitment_ref=p.cpo.commitment_ref(w4.id))
    c5, d5, _ = p.need_combo(exterior_color="CPO5")
    p.p4.seed_future(c5, [{"production_order_id": "po_cpo5", "arrival_month": "2026-10"}])   # already in future supply
    w5 = p.cpo.propose(p.full, SCOPE, production_order_id="po_cpo5", combination_id=c5.id, arrival_month="2026-10")
    out["cpo_already_represented"] = p.cpo.approve(p.full, SCOPE, w5)
    # PPO (26-28)
    c6, d6, _ = p.need_combo(exterior_color="PPO1")
    out["ppo_proposal"] = p.ppo.propose(p.full, SCOPE, order_or_unit_id="po_ppo1", combination_id=c6.id,
                                        arrival_month="2026-10")
    w7 = p.ppo.propose(p.full, SCOPE, order_or_unit_id="po_ppo2", combination_id=c6.id, arrival_month="2026-10")
    out["approved_ppo"] = p.ppo.approve(p.full, SCOPE, w7)
    w8 = p.ppo.propose(p.full, SCOPE, order_or_unit_id="po_ppo3", combination_id=c6.id, arrival_month="2026-10")
    out["rejected_ppo"] = p.ppo.reject(p.full, SCOPE, w8)
    # Dealer Trade (29-36)
    c9, d9, _ = p.need_combo(exterior_color="DT1")
    out["dealer_trade_proposal"] = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt1", combination_id=c9.id,
                                               arrival_month="2026-10")
    w10 = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt2", combination_id=c9.id, arrival_month="2026-10")
    out["dealer_trade_request_sent"] = p.dt.send_request(p.full, SCOPE, w10)
    w11 = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt3", combination_id=c9.id, arrival_month="2026-10")
    p.dt.send_request(p.full, SCOPE, p.wf.get_workflow(w11.id))
    out["dealer_trade_accepted_incomplete"] = p.dt.accept(p.full, SCOPE, p.wf.get_workflow(w11.id))
    w12 = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt4", combination_id=c9.id, arrival_month="2026-10")
    p.dt.send_request(p.full, SCOPE, p.wf.get_workflow(w12.id))
    p.dt.accept(p.full, SCOPE, p.wf.get_workflow(w12.id))
    out["dealer_trade_completed"] = p.dt.complete(p.full, SCOPE, p.wf.get_workflow(w12.id), received_unit_id="vu_dt4")
    w13 = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt5", combination_id=c9.id, arrival_month="2026-10")
    out["dealer_trade_rejected"] = p.dt.terminate(p.full, SCOPE, w13, to_status="REJECTED")
    w14 = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt6", combination_id=c9.id, arrival_month="2026-10")
    out["dealer_trade_expired"] = p.dt.terminate(p.full, SCOPE, w14, to_status="EXPIRED")
    w15 = p.dt.propose(p.full, SCOPE, unit_identity="vu_dt7", combination_id=c9.id, arrival_month="2026-10")
    p.dt.send_request(p.full, SCOPE, p.wf.get_workflow(w15.id))
    p.dt.accept(p.full, SCOPE, p.wf.get_workflow(w15.id))
    out["dealer_trade_failed"] = p.dt.terminate(p.full, SCOPE, p.wf.get_workflow(w15.id), to_status="FAILED")
    out["dealer_trade_received_recon"] = out["dealer_trade_completed"]
    # CTP (37-41)
    src, sd, _ = p.need_combo(exterior_color="CTPSRC")   # excess side
    dst, dd, _ = p.need_combo(exterior_color="CTPDST")   # need side
    p.p4.seed_future(src, [{"production_order_id": "po_ctp1", "arrival_month": "2026-10"}])
    ed = p.pipeline.assess_editability("po_ctp1", SCOPE, "editable", editable_dimensions=["exterior_color"])
    wctp = p.ctp.propose(p.full, SCOPE, production_order_id="po_ctp1", original_combination_id=src.id,
                         proposed_combination_id=dst.id, editability=ed, changes={"exterior_color": ("CTPSRC", "CTPDST")})
    out["ctp_excess_to_need"] = wctp
    locked = p.pipeline.assess_editability("po_locked", SCOPE, "locked")
    out["ctp_not_editable"] = {"editability": locked, "src": src, "dst": dst}
    wctp_r = p.ctp.propose(p.full, SCOPE, production_order_id="po_ctp2", original_combination_id=src.id,
                           proposed_combination_id=dst.id, editability=ed)
    out["ctp_rejected"] = p.ctp.reject(p.full, SCOPE, wctp_r)
    p.p4.seed_future(src, [{"production_order_id": "po_ctp3", "arrival_month": "2026-10"}])
    wctp_a = p.ctp.propose(p.full, SCOPE, production_order_id="po_ctp3", original_combination_id=src.id,
                           proposed_combination_id=dst.id, editability=ed)
    p.ctp.approve(p.full, SCOPE, p.wf.get_workflow(wctp_a.id))
    out["ctp_accepted"] = p.ctp.execute(p.full, SCOPE, p.wf.get_workflow(wctp_a.id), proposed_combination_id=dst.id,
                                        arrival_month="2026-10")
    out["ctp_replay"] = p.ctp.execute(p.full, SCOPE, p.wf.get_workflow(wctp_a.id), proposed_combination_id=dst.id,
                                      arrival_month="2026-10")   # idempotent replay
    # sequential (42-43)
    cseq, dseq, _ = p.need_combo(exterior_color="SEQ")
    out["sequential_two_action"] = p.sequential.run(
        SCOPE, [{"action_ref": "a1", "combination_id": cseq.id, "unit_id": "u1", "arrival_month": "2026-09"},
                {"action_ref": "a2", "combination_id": cseq.id, "unit_id": "u2", "arrival_month": "2026-09"}],
        demand_by_combo={cseq.id: dseq}, coverage_by_combo={cseq.id: 0})
    cseq2, dseq2, _ = p.need_combo(exterior_color="SEQ2", per_month=1)
    out["sequential_becomes_unnecessary"] = p.sequential.run(
        SCOPE, [{"action_ref": "b1", "combination_id": cseq2.id, "unit_id": "v1", "arrival_month": "2026-09"}] * 1
        + [{"action_ref": "b2", "combination_id": cseq2.id, "unit_id": "v2", "arrival_month": "2026-09"}],
        demand_by_combo={cseq2.id: dseq2}, coverage_by_combo={cseq2.id: 0})
    # governance/edge (44-49)
    out["identity_conflict"] = p.combination(exterior_color="IDC")
    cst, dst2, _ = p.need_combo(exterior_color="STALE")
    out["stale_approval"] = p.cpo.propose(p.full, SCOPE, production_order_id="po_stale", combination_id=cst.id,
                                          arrival_month="2026-10")
    cua, dua, _ = p.need_combo(exterior_color="UAUTH")
    out["unauthorized_approval"] = p.cpo.propose(p.proposer, SCOPE, production_order_id="po_uauth",
                                                 combination_id=cua.id, arrival_month="2026-10")
    caf, daf, _ = p.need_combo(exterior_color="AUDF")
    out["audit_failure"] = (caf, p.cpo.propose(p.full, SCOPE, production_order_id="po_audf", combination_id=caf.id,
                                               arrival_month="2026-10"))
    ccn, dcn, _ = p.need_combo(exterior_color="CHGC")
    wcn = p.cpo.propose(p.full, SCOPE, production_order_id="po_chg", combination_id=ccn.id, arrival_month="2026-09")
    p.cpo.approve(p.full, SCOPE, wcn)
    out["changed_commitment_new_output"] = p.integrate.reissue_plan(dcn, SCOPE, coverage_target=2, workflow_id=wcn.id,
                                                                    causing_action="cpo.approve")
    cis, dis, _ = p.need_combo(exterior_color="SCIS")
    out["scenario_workflow_isolated"] = p.cpo.propose(p.full, SCOPE, production_order_id="po_scn",
                                                      combination_id=cis.id, arrival_month="2026-10",
                                                      scenario_id="scn_wf")
    # completion to current (50)
    ccc, dcc, _ = p.need_combo(exterior_color="C2C")
    wcc = p.cpo.propose(p.full, SCOPE, production_order_id="po_c2c", combination_id=ccc.id, arrival_month="2026-10")
    p.cpo.approve(p.full, SCOPE, wcc)
    out["completed_to_current"] = p.cpo.complete(p.full, SCOPE, p.wf.get_workflow(wcc.id), received_unit_id="vu_c2c",
                                                 commitment_ref=p.cpo.commitment_ref(wcc.id))
    return out
