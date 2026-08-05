"""Learning Signal — a domain-aware pattern across Errors + Attributions.

A single Error does not establish a stable Signal. Minimum-evidence requirements resolve through policy;
sample size is visible; recurrence must be demonstrated before support. Signals stay domain-specific
unless an approved cross-domain interpretation exists. Conflicting evidence stays visible; data-quality
weakness reduces confidence. A Learning Signal has NO operational effect and is not escalated
automatically. History is append-preserving.
"""
from __future__ import annotations


class LearningSignalService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def observe(self, owning_domain, *, subject_or_cohort, error_refs, attribution_refs=None, pattern_type,
                direction=None, magnitude=None, min_sample=3, min_recurrence=2, data_quality_conditions=None,
                proposed_review_area=None, conflicting=False, evidence_window=None):
        """Create/assess a Learning Signal. Support requires sample_size >= min_sample AND recurrence >=
        min_recurrence AND no conflicting evidence AND acceptable data quality. Otherwise the Signal is
        MONITORING / INSUFFICIENT_EVIDENCE / CONFLICTING. Never escalates on its own."""
        sample_size = len(error_refs)
        recurrence = sample_size                     # each error ref is a recurrence of the pattern
        dq = data_quality_conditions or {}
        weak_dq = bool(dq.get("weak"))
        if conflicting:
            status, confidence, stability = "CONFLICTING", "low", "unstable"
        elif sample_size < min_sample or recurrence < min_recurrence:
            status, confidence, stability = "INSUFFICIENT_EVIDENCE", "low", "unstable"
        elif weak_dq:
            status, confidence, stability = "MONITORING", "low", "provisional"
        else:
            status, confidence, stability = "SUPPORTED", "medium", "stable"
        return self.store.add_learning_signal(
            owning_domain, subject_or_cohort=subject_or_cohort, error_refs=error_refs,
            attribution_refs=attribution_refs, pattern_type=pattern_type, evidence_window=evidence_window,
            sample_size=sample_size, recurrence=recurrence, direction=direction, magnitude=magnitude,
            confidence=confidence, stability=stability, data_quality_conditions=dq,
            proposed_review_area=proposed_review_area, status=status)

    def escalate(self, signal):
        """Only a SUPPORTED Signal may be escalated to Calibration (an explicit human/governed step)."""
        if signal["status"] != "SUPPORTED":
            return None
        self.store.set_learning_signal(signal["id"], signal["version"], status="ESCALATED_TO_CALIBRATION")
        return self.store.get_learning_signal(signal["id"])
