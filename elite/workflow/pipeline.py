"""Production pipeline projection + ETA/arrival-window + editability + model-year transition.

Projections come from accepted Production Order + Business Fact records. Production Order identity
is stable through status changes; pre-VIN and later-VIN linkage do not create duplicate supply;
conflicting source states remain explicit; cancelled/invalid/superseded orders do not emit
qualifying Future Supply. ETA precision never exceeds source evidence; a range crossing months
never silently selects the favorable month; unknown ETA never becomes confident qualifying supply.
Editability is operational truth and never changes Demand.
"""
from __future__ import annotations

from ..ids import new_id
from ..newinv.models import FutureSupply
from .models import EditabilityResult, EtaRecord, IncomingRisk, ModelYearTransition, ProductionPipeline

_INACTIVE_ORDER = {"cancelled", "invalid", "superseded"}


class PipelineService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def project(self, production_order_id, combination_id, scope, *, order_status="open",
                production_status="planned", allocation_status=None, vin_status="pending",
                eta_start=None, eta_end=None, arrival_month=None, fact_refs=None, conflict=None,
                confidence="medium", identity_refs=None):
        """Add/refresh the current pipeline projection for an order (supersedes any prior current
        row for that order — prior-as-known is preserved)."""
        for prior in self.store.pipeline_for_order(production_order_id, current_only=True):
            self.store.supersede_pipeline(prior.id)
        p = ProductionPipeline(
            id=new_id("pp"), store_scope=scope, production_order_id=production_order_id,
            combination_id=combination_id, order_status=order_status, production_status=production_status,
            allocation_status=allocation_status, vin_status=vin_status, eta_start=eta_start, eta_end=eta_end,
            arrival_month=arrival_month, fact_refs=list(fact_refs or []), conflict=conflict, confidence=confidence,
            identity_refs=identity_refs or {"production_order_id": production_order_id})
        return self.store.add_pipeline(p)

    def link_vin(self, production_order_id, vin, vehicle_unit_id=None):
        """Record VIN linkage on the SAME order (no duplicate pipeline / supply)."""
        cur = self.store.pipeline_for_order(production_order_id, current_only=True)
        if not cur:
            return None
        p = cur[0]
        idrefs = dict(p.identity_refs or {})
        idrefs.update({"vin": vin, "vehicle_unit_id": vehicle_unit_id})
        return self.project(production_order_id, p.combination_id, p.store_scope, order_status=p.order_status,
                            production_status=p.production_status, allocation_status=p.allocation_status,
                            vin_status="linked", eta_start=p.eta_start, eta_end=p.eta_end,
                            arrival_month=p.arrival_month, fact_refs=p.fact_refs, confidence=p.confidence,
                            identity_refs=idrefs)

    # ---- ETA ---------------------------------------------------------------
    def record_eta(self, production_order_id, precision, *, eta_start=None, eta_end=None, arrival_month=None,
                   confidence="medium", stale=False, conflicting=False, source_refs=None):
        prior = self.store.eta_history_for(production_order_id)
        e = EtaRecord(id=new_id("eta"), precision=precision, production_order_id=production_order_id,
                      eta_start=eta_start, eta_end=eta_end, arrival_month=arrival_month, confidence=confidence,
                      stale=stale, conflicting=conflicting, supersedes=prior[-1].id if prior else None,
                      source_refs=list(source_refs or []))
        return self.store.add_eta(e)

    @staticmethod
    def interpret_eta(eta: EtaRecord):
        """Map an ETA record to (arrival_month, confidence, eligible-for-qualifying). Precision is
        never upgraded; a cross-month range takes the CONSERVATIVE (later) month, never the
        favorable earlier one; unknown/conflicting is not eligible as confident supply."""
        if eta is None or eta.precision in ("unresolved",) or (eta.arrival_month is None and eta.eta_end is None
                                                               and eta.eta_start is None):
            return None, "unknown", False
        if eta.conflicting or eta.precision == "conflicting":
            return None, "conflicting", False
        conf = eta.confidence
        eligible = True
        if eta.stale or eta.precision == "stale":
            conf, eligible = "low", False        # staleness requires review, not confident supply
        if eta.precision == "exact":
            return (eta.arrival_month or (eta.eta_start or "")[:7]), conf, eligible
        if eta.precision == "month":
            return eta.arrival_month, conf, eligible
        if eta.precision == "range":
            # conservative: the LATER month bound, never the favorable earlier month
            end = (eta.eta_end or "")[:7] or eta.arrival_month
            start = (eta.eta_start or "")[:7]
            months_span = bool(start and end and start != end)
            return end, ("medium" if months_span else conf), eligible
        return eta.arrival_month, conf, eligible

    def emit_future_supply(self, nistore, pipeline: ProductionPipeline, eta: EtaRecord):
        """Emit a Phase 4 Future Supply from a current pipeline, honoring ETA eligibility. Returns
        the FutureSupply, or None when the order is inactive or the ETA is not confident."""
        if pipeline.order_status in _INACTIVE_ORDER or pipeline.production_status in _INACTIVE_ORDER:
            return None
        arrival_month, conf, eligible = self.interpret_eta(eta)
        if not eligible:
            return None                          # unknown/conflicting/stale ETA -> not qualifying
        fs = FutureSupply(
            id=new_id("fsup"), store_scope=pipeline.store_scope, production_order_id=pipeline.production_order_id,
            combination_id=pipeline.combination_id, production_state=pipeline.production_status,
            arrival_month=arrival_month, timing_confidence=conf,
            identity_linkage={"production_order_id": pipeline.production_order_id,
                              "vehicle_unit_id": (pipeline.identity_refs or {}).get("vehicle_unit_id")})
        return nistore.add_future_supply(fs)

    # ---- editability -------------------------------------------------------
    def assess_editability(self, production_order_id, scope, editability_state, *, editable_dimensions=None,
                           cutoff=None, confidence="medium", unresolved_conditions=None, policy_refs=None):
        return self.store.add_editability(EditabilityResult(
            id=new_id("edit"), editability_state=editability_state, production_order_id=production_order_id,
            store_scope=scope, editable_dimensions=list(editable_dimensions or []), cutoff=cutoff,
            confidence=confidence, unresolved_conditions=list(unresolved_conditions or []),
            policy_refs=list(policy_refs or [])))

    @staticmethod
    def is_executably_editable(editability: EditabilityResult) -> bool:
        """Only an editable / conditionally-editable order may receive an executable CTP. Unknown
        never becomes editable; locked / past_cutoff / conflicting cannot execute."""
        return bool(editability) and editability.editability_state in ("editable", "conditionally_editable")

    # ---- model-year transition --------------------------------------------
    def model_year_transition(self, scope, model, *, outgoing_model_year, incoming_model_year, overlap=None,
                              lineage_status="unspecified", arrival_risk="unknown", constrained_incoming=False,
                              transition_window=None, policy_refs=None, confidence="medium"):
        return self.store.add_model_year_transition(ModelYearTransition(
            id=new_id("myt"), store_scope=scope, model=model, outgoing_model_year=outgoing_model_year,
            incoming_model_year=incoming_model_year, overlap=overlap, lineage_status=lineage_status,
            arrival_risk=arrival_risk, constrained_incoming=constrained_incoming,
            transition_window=transition_window or {}, policy_refs=list(policy_refs or []), confidence=confidence))
