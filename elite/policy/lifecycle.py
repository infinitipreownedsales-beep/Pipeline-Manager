"""Governed policy lifecycle transitions.

Each action authorizes below the UI, validates the legal transition, persists
atomically with an Audit Event (Phase 1 Governor), preserves correlation id,
rejects stale concurrency, and is idempotent when retried. Approval never
auto-activates a future-effective version.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..errors import ConcurrencyError, ValidationError
from ..ids import new_id
from .models import TRANSITIONS, PolicyVersion


def _transition(gov, store, *, principal, capability, scope, version_id, expected_version,
                action, target_status, correlation_id=None, idempotency_key=None,
                updates=None, guard=None):
    def business(conn):
        cur = store.get_version(version_id)
        if cur is None:
            raise ValidationError(technical_detail="policy version not found")
        if target_status not in TRANSITIONS.get(cur.lifecycle_status, set()):
            raise ValidationError(message="That lifecycle change is not allowed.",
                                  technical_detail=f"illegal transition {cur.lifecycle_status}->{target_status}")
        if guard:
            guard(cur)
        sets = {"lifecycle_status": target_status}
        if updates:
            sets.update(updates(cur))
        cols = ",".join(f"{k}=?" for k in sets)
        params = list(sets.values()) + [version_id, expected_version]
        c = conn.execute(f"UPDATE policy_version SET {cols},version=version+1 WHERE id=? AND version=?", params)
        if c.rowcount == 0:
            raise ConcurrencyError(technical_detail=f"policy version {version_id} stale")
        return target_status, version_id
    return gov.perform(principal_id=principal, capability=capability, scope=scope, action=action,
                       business_fn=business, target_ref=version_id, correlation_id=correlation_id,
                       idempotency_key=idempotency_key)


def propose(gov, store, principal, scope, vid, expected_version, **kw):
    return _transition(gov, store, principal=principal, capability="policy.propose", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.propose",
                       target_status="PROPOSED", **kw)


def approve(gov, store, principal, scope, vid, expected_version, *, clock, **kw):
    # Approve records approval but never activates; future-effective stays scheduled/approved.
    def upd(cur):
        return {"approval_state": "approved", "approving_principal": principal,
                "approved_time": to_utc_iso(clock.now())}
    return _transition(gov, store, principal=principal, capability="policy.approve", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.approve",
                       target_status="APPROVED", updates=upd, **kw)


def schedule(gov, store, principal, scope, vid, expected_version, *, activation_time, **kw):
    return _transition(gov, store, principal=principal, capability="policy.approve", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.schedule",
                       target_status="SCHEDULED", updates=lambda c: {"scheduled_activation": activation_time}, **kw)


def activate(gov, store, principal, scope, vid, expected_version, *, clock, **kw):
    now = to_utc_iso(clock.now())

    def guard(cur):
        if cur.effective_start and cur.effective_start > now:
            raise ValidationError(message="Not yet effective.",
                                  technical_detail=f"effective_start {cur.effective_start} is in the future")
    return _transition(gov, store, principal=principal, capability="policy.activate", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.activate",
                       target_status="ACTIVE", guard=guard, **kw)


def reject(gov, store, principal, scope, vid, expected_version, *, reason="", **kw):
    return _transition(gov, store, principal=principal, capability="policy.approve", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.reject",
                       target_status="REJECTED", updates=lambda c: {"reason": reason}, **kw)


def withdraw(gov, store, principal, scope, vid, expected_version, *, reason="", **kw):
    return _transition(gov, store, principal=principal, capability="policy.propose", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.withdraw",
                       target_status="WITHDRAWN", updates=lambda c: {"reason": reason}, **kw)


def revoke(gov, store, principal, scope, vid, expected_version, *, revocation, **kw):
    return _transition(gov, store, principal=principal, capability="policy.activate", scope=scope,
                       version_id=vid, expected_version=expected_version, action="policy.revoke",
                       target_status="REVOKED", updates=lambda c: {"revocation": json.dumps(revocation)}, **kw)


def correct(gov, store, principal, scope, orig_id, new_value, *, clock, **kw):
    """Create a new corrective version (preserving the immutable original) and mark the
    original CORRECTED via a governed transition."""
    orig = store.get_version(orig_id)
    if orig is None:
        raise ValidationError(technical_detail="original policy version not found")
    new = store.add_version(PolicyVersion(
        id=new_id("pv"), family_id=orig.family_id, version_number=orig.version_number + 1, value=new_value,
        lifecycle_status="DRAFT", recorded_time=to_utc_iso(clock.now()), scope=orig.scope,
        effective_start=orig.effective_start, effective_end=orig.effective_end, correction_of=orig.id,
        store_scope=orig.store_scope, provenance={"corrects": orig.id}))
    _transition(gov, store, principal=principal, capability="policy.approve", scope=scope, version_id=orig.id,
                expected_version=orig.version, action="policy.correct", target_status="CORRECTED",
                updates=lambda c: {"superseded_by": new.id}, **kw)
    return new


def supersede(gov, store, principal, scope, orig_id, new_version_obj, **kw):
    """Mark an ACTIVE version SUPERSEDED by a new version (new must already exist)."""
    orig = store.get_version(orig_id)
    return _transition(gov, store, principal=principal, capability="policy.activate", scope=scope,
                       version_id=orig_id, expected_version=orig.version, action="policy.supersede",
                       target_status="SUPERSEDED", updates=lambda c: {"superseded_by": new_version_obj.id}, **kw)
