"""Read-only bridge from the certified planner to the APPROVED Translation/Identity + Lineage governance.

The certified planner refuses a supply cohort with no exact same-code Speed-to-Sell history
(`no_accepted_demand_history`). This resolver lets that refusal FIRST consult the already-governed
demand-sharing relationships: when an APPROVED SAME_FAMILY_CROSS_GEN (or SUCCESSOR) record governs a
predecessor generation, its REAL predecessor cohorts are returned so the planner can issue at the existing
`lineage` evidence tier (never `exact`). Nothing here fabricates demand, relabels history, merges codes, or
approves anything — it only READS approved governance and existing cohorts.

Governance honored exactly:
  * a relationship must be APPROVED (a proposed/deferred/rejected review never shares) — else honest refusal;
  * borrowing is same commercial family (model+trim+drivetrain) across an OLDER generation only;
  * the current supply cohort keeps its current code/identity; predecessor history is supporting evidence;
  * colour (exterior/interior) is preserved — this is cross-GENERATION borrowing, never colour-level sharing.
"""
from __future__ import annotations

from .dms_identity import normalize_code


class LineageDemandResolver:
    """Resolve governed predecessor demand for a current supply cohort. `translation` is a TranslationStore and
    `lineage` a LineageStore, both read-only for the current scope."""

    def __init__(self, translation, lineage):
        self.tx = translation
        self.ln = lineage

    def resolve(self, key, demand_by_key):
        """For a supply cohort `key` = (model, code4, exterior, interior) that has no exact demand, return
        `(predecessors, note)`:
          * `predecessors` — the list of REAL predecessor CohortDemand objects an APPROVED relationship permits
            to support this cohort (empty when borrowing is not governed);
          * `note` — a dict describing the governance state (`status` + the exact missing/blocking review), so
            the planner can surface precisely which review is required instead of silently refusing.
        Never mutates anything; never fabricates a cohort."""
        model, code4_, ext, inte = key
        fam = self.tx.family_for_code(code4_)
        if fam is None:
            return [], {"status": "no_family", "code": code4_,
                        "detail": f"model code {code4_} has no approved commercial family yet — no borrowing."}
        rows = self.tx.variant_rows(fam, approved_only=True)
        cur_gen = next((r.generation_id for r in rows if normalize_code(fam.model, r.raw_code) == code4_), None)

        prop = self.ln.latest_for(f"cross_gen:{fam.as_str()}", "SAME_FAMILY_CROSS_GEN")
        if prop is None:
            return [], {"status": "no_relationship", "family": fam.as_str(),
                        "detail": f"no SAME_FAMILY_CROSS_GEN relationship exists for {fam.as_str()} "
                                  f"(single generation in the governed identity — no predecessor to borrow)."}
        if prop.status != "approved":
            return [], {"status": "not_approved", "family": fam.as_str(), "root_key": prop.root_key,
                        "review_status": prop.status,
                        "detail": f"a SAME_FAMILY_CROSS_GEN demand-sharing review for {fam.as_str()} exists but "
                                  f"is '{prop.status}', not approved — approve it to let the prior generation "
                                  f"support this cohort as lineage evidence."}

        # APPROVED: gather OLDER-generation predecessor planning keys for the SAME colour, then pull only the
        # predecessor cohorts that carry REAL history (present in demand_by_key). Codes stay distinct.
        pred_keys = set()
        for r in rows:
            pc = normalize_code(fam.model, r.raw_code)
            if pc and pc != code4_ and (cur_gen is None or str(r.generation_id) < str(cur_gen)):
                pred_keys.add((model, pc, ext, inte))
        predecessors = [demand_by_key[k] for k in pred_keys
                        if k in demand_by_key and demand_by_key[k].retail_by_month]
        if not predecessors:
            return [], {"status": "approved_no_history", "family": fam.as_str(), "root_key": prop.root_key,
                        "predecessor_keys": [list(k) for k in sorted(pred_keys)],
                        "detail": f"the relationship is approved, but the prior generation has no Speed-to-Sell "
                                  f"history for {ext}/{inte} — nothing real to borrow."}
        return predecessors, {"status": "approved_lineage", "family": fam.as_str(), "root_key": prop.root_key,
                              "predecessor_keys": [list(k) for k in sorted(pred_keys)]}
