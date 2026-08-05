"""Operational learning + calibration output slices.

The smallest REAL outputs (from stored records) for issued Predictions, pending Observations,
Pairings, Error review, Attribution review, the Learning Signal queue, the Calibration Proposal queue,
Calibration validation comparison, scheduled activation, rollback history, and a domain learning
summary. Each exposes expected-vs-actual, confidence/uncertainty, evidence, sample size + recurrence,
versions, and a Raw History path. Not the full Phase 10 UX.
"""
from __future__ import annotations

import json


def prediction_slice(store, prediction_id):
    p = store.get_prediction(prediction_id)
    if p is None:
        return None
    return {"call": ("SCENARIO PREDICTION" if p.scenario_id else "OFFICIAL PREDICTION"),
            "prediction_id": p.id, "prediction_type": p.prediction_type, "owning_domain": p.owning_domain,
            "subject": (p.subject_entity_type, p.subject_entity_id), "predicted": p.predicted_payload,
            "unit_contract": p.unit_contract, "confidence": p.confidence, "uncertainty": p.uncertainty,
            "resolution_status": p.resolution_status, "observation_contract": p.observation_contract,
            "versions": {"policy": p.policy_versions, "calculation": p.calculation_version,
                         "model": p.model_version, "identity_rule": p.identity_rule_version,
                         "comparison_spec": p.comparison_spec_version},
            "reproducibility_package": p.reproducibility_package,
            "corrections": [dict(r) for r in store.prediction_corrections(p.id)],
            "raw_history_path": f"prediction/{p.id}"}


def pending_observations(store, prediction_ids):
    out = []
    for pid in prediction_ids:
        for pr in store.pairings_for_prediction(pid):
            if pr.pairing_status == "PENDING_OBSERVATION":
                out.append({"prediction_id": pid, "pairing_id": pr.id, "status": pr.pairing_status,
                            "reason": pr.reason})
    return out


def pairing_slice(store, pairing_id):
    pr = store.get_pairing(pairing_id)
    if pr is None:
        return None
    return {"pairing_id": pr.id, "prediction_id": pr.prediction_id, "observation_id": pr.observation_id,
            "pairing_status": pr.pairing_status, "comparison_spec_version": pr.comparison_spec_version,
            "unit_compatible": pr.unit_compatible, "completeness": pr.completeness, "confidence": pr.confidence,
            "matching_evidence": pr.matching_evidence, "reason": pr.reason,
            "raw_history_path": f"prediction_observation_pairing/{pr.id}"}


def error_slice(store, error_id):
    e = store.get_error(error_id)
    if e is None:
        return None
    return {"error_id": e.id, "pairing_id": e.pairing_id, "expected": e.expected_value, "actual": e.actual_value,
            "signed_error": e.signed_error, "absolute_error": e.absolute_error, "percentage_error": e.percentage_error,
            "timing_error": e.timing_error, "classification": e.classification, "materiality": e.materiality,
            "confidence": e.confidence, "resolution_status": e.resolution_status,
            "comparison_spec_version": e.comparison_spec_version, "calculation_version": e.calculation_version,
            "reproducibility_package": e.reproducibility_package, "raw_history_path": f"prediction_error/{e.id}"}


def attribution_slice(store, error_id):
    rows = store.attributions_for_error(error_id)
    return [{"attribution_id": a["id"], "factor": a["proposed_factor"], "category": a["factor_category"],
             "status": a["status"], "confidence": a["confidence"], "evidence_strength": a["evidence_strength"],
             "source": a["source"],
             "evidence": [{"kind": ev["evidence_kind"], "supports": bool(ev["supports"]),
                           "description": ev["description"]} for ev in store.evidence_for_attribution(a["id"])],
             "raw_history_path": f"attribution/{a['id']}"} for a in rows]


def learning_signal_queue(store, owning_domain, *, status=None):
    return [{"learning_signal_id": s["id"], "owning_domain": s["owning_domain"], "pattern_type": s["pattern_type"],
             "sample_size": s["sample_size"], "recurrence": s["recurrence"], "confidence": s["confidence"],
             "stability": s["stability"], "status": s["status"], "proposed_review_area": s["proposed_review_area"],
             "raw_history_path": f"learning_signal/{s['id']}"} for s in store.signals_in_domain(owning_domain,
                                                                                                 status=status)]


def calibration_queue(store, review_state):
    return [{"calibration_id": c["id"], "target_type": c["target_type"], "review_state": c["review_state"],
             "approval_state": c["approval_state"], "affected_domains": json.loads(c["affected_domains"] or "[]"),
             "current_version": c["current_version"], "activation_ref": c["activation_ref"],
             "raw_history_path": f"calibration_proposal/{c['id']}"} for c in store.calibrations_in_state(review_state)]


def validation_comparison(store, validation_run_id):
    return {"validation_run_id": validation_run_id,
            "results": [{"cohort": r["cohort"], "current_error": r["current_error"],
                         "proposed_error": r["proposed_error"], "delta": r["delta"], "direction": r["direction"],
                         "material": bool(r["material"])} for r in store.validation_results(validation_run_id)],
            "hypothetical": True}


def scheduled_activations(store):
    rows = store.conn.execute("SELECT * FROM calibration_activation WHERE scheduled=1 ORDER BY activated_at").fetchall()
    return [{"activation_id": r["id"], "calibration_id": r["calibration_proposal_id"], "kind": r["activated_version_kind"],
             "version_ref": r["activated_version_ref"], "effective_start": r["effective_start"]} for r in rows]


def rollback_history(store, calibration_proposal_id):
    return [{"rollback_id": r["id"], "restored_version_ref": r["restored_version_ref"], "reason": r["reason"],
             "effective_start": r["effective_start"]} for r in store.rollback_for(calibration_proposal_id)]


def domain_learning_summary(store, owning_domain):
    signals = store.signals_in_domain(owning_domain)
    by_status = {}
    for s in signals:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
    return {"owning_domain": owning_domain, "signal_count": len(signals), "by_status": by_status,
            "predictions": len(store.predictions_where(owning_domain=owning_domain)),
            "raw_history_path": f"learning_issued_output?domain={owning_domain}"}
