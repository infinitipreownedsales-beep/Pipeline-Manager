"""Version activation + rollback with append-preserving history.

Activating a Calculation/Model version records an activation-history row; rolling back
NEVER erases the rolled-back version — it marks it 'rolled_back' and records a
rollback-history row pointing at the version restored to service. History is the record
of what was active when, so a later change is always traceable.
"""
from __future__ import annotations


def activate_calc_version(store, vid, expected_version, *, actor, detail=""):
    """Mark a Calculation Version 'active' and append an activation-history row."""
    cv = store.set_calc_version_status(vid, expected_version, "active")
    store.record_activation("calculation_version", vid, "activate", actor, detail)
    return cv


def rollback_calc_version(store, *, from_id, from_expected, to_id, actor, reason=""):
    """Roll back FROM a version TO a prior one, preserving both.

    The rolled-back version is marked 'rolled_back' (not deleted); the restored version
    is re-activated; a rollback-history row records the transition."""
    store.set_calc_version_status(from_id, from_expected, "rolled_back")
    to_cv = store.get_calc_version(to_id)
    if to_cv is not None:
        store.set_calc_version_status(to_id, to_cv.version, "active")
        store.record_activation("calculation_version", to_id, "reactivate", actor,
                                f"rollback from {from_id}")
    store.record_rollback("calculation_version", from_id, to_id, actor, reason)
    return store.get_calc_version(to_id)


def activate_model_version(store, mid, *, actor, when=None, detail=""):
    """Activate a Model Version and record activation history."""
    m = store.activate_model_version(mid, when or store.clock.now())
    store.record_activation("model_version", mid, "activate", actor, detail)
    return m
