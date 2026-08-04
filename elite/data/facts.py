"""Business Fact service.

A Source Observation is not a Business Fact. Only accepted observations under valid
SOURCE authority (fact-type + scope specific) may create authoritative facts. Facts
are append-preserving: corrections/supersessions/reversals never overwrite or delete
the original. Current-state projection deterministically selects the applicable fact.
"""
from __future__ import annotations

from ..errors import AuthorizationError, ValidationError
from ..ids import new_id
from .models import BusinessFact


class FactService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def create(self, *, source, fact_type, subject_type, subject_id, payload, scope,
               observation_refs, effective_time=None, quality_status="ok", provenance=None):
        # Source authority is fact-type AND scope specific.
        if not source.is_authoritative(fact_type, scope):
            raise AuthorizationError(
                message="This source cannot record that fact.",
                technical_detail=f"source {source.id} not authoritative for {fact_type}@{scope}")
        f = BusinessFact(id=new_id("fact"), fact_type=fact_type, subject_entity_type=subject_type,
                         subject_entity_id=subject_id, payload=payload, recorded_time=None, status="current",
                         effective_time=effective_time, observation_refs=list(observation_refs or []),
                         source_authority=source.id, quality_status=quality_status, store_scope=scope,
                         provenance=provenance or {"source": source.id})
        return self.store.add_fact(f)

    def correct(self, fact_id, new_payload, *, observation_refs=None, quality_status="ok"):
        """Create a NEW fact (correction_of=original); the original is preserved and marked
        superseded. Original-as-known remains inspectable."""
        orig = self.store.get_fact(fact_id)
        if orig is None:
            raise ValidationError(technical_detail="fact not found")
        src = self.store.get_source(orig.source_authority)
        corrected = BusinessFact(id=new_id("fact"), fact_type=orig.fact_type,
                                 subject_entity_type=orig.subject_entity_type, subject_entity_id=orig.subject_entity_id,
                                 payload=new_payload, recorded_time=None, status="current",
                                 effective_time=orig.effective_time, observation_refs=list(observation_refs or []),
                                 source_authority=orig.source_authority, quality_status=quality_status,
                                 correction_of=orig.id, store_scope=orig.store_scope,
                                 provenance={"corrects": orig.id})
        self.store.add_fact(corrected)
        self.store.set_fact_status(orig.id, orig.version, "superseded", superseded_by=corrected.id)
        return corrected

    def supersede(self, fact_id, new_fact_payload, *, observation_refs=None):
        return self.correct(fact_id, new_fact_payload, observation_refs=observation_refs)

    def reverse(self, fact_id, *, reason=""):
        """Record a reversal that negates the business effect WITHOUT deleting the prior
        fact. The reversal is its own record referencing the reversed fact."""
        orig = self.store.get_fact(fact_id)
        if orig is None:
            raise ValidationError(technical_detail="fact not found")
        rev = BusinessFact(id=new_id("fact"), fact_type=orig.fact_type,
                           subject_entity_type=orig.subject_entity_type, subject_entity_id=orig.subject_entity_id,
                           payload={"reversed": True, "reason": reason}, recorded_time=None, status="reversed",
                           effective_time=orig.effective_time, observation_refs=list(orig.observation_refs),
                           source_authority=orig.source_authority, reversal_of=orig.id, store_scope=orig.store_scope,
                           provenance={"reverses": orig.id})
        self.store.add_fact(rev)
        self.store.set_fact_status(orig.id, orig.version, "reversed")
        return rev

    def current(self, subject_type, subject_id, fact_type, scope, *, precedence=None):
        """Deterministic current-state projection. Returns (fact_or_None, conflict_info).

        Selects among status='current' facts. Multiple current facts from different
        source authorities are a CONFLICT unless an approved precedence rule resolves
        them. Determinism: order by (effective_time, recorded_time, id)."""
        currents = self.store.facts_for(subject_type, subject_id, fact_type, scope, only_current=True)
        if not currents:
            return None, None
        if len(currents) == 1:
            return currents[0], None
        authorities = {f.source_authority for f in currents}
        if len(authorities) > 1 and precedence:
            ranked = sorted(currents, key=lambda f: precedence.index(f.source_authority)
                            if f.source_authority in precedence else len(precedence))
            if ranked and (len(precedence) and ranked[0].source_authority in precedence):
                return ranked[0], None
        if len(authorities) > 1:
            return None, {"conflict": True, "facts": [f.id for f in currents], "authorities": sorted(authorities)}
        chosen = sorted(currents, key=lambda f: (f.effective_time or "", f.recorded_time, f.id))[-1]
        return chosen, None
