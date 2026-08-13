"""Reusable Data-Quality Exception / Acknowledgement pattern (derived, fingerprint-stable).

A data-quality exception is DERIVED (recomputed each run from immutable source observations) — it never
deletes source evidence, never mutates an import, and never hides future materially-changed evidence. Each
exception carries a `fingerprint` over its material evidence: an acknowledged fingerprint stays suppressed
so an unchanged condition does not repeatedly nag; if the evidence materially changes the fingerprint
changes, so a new/changed exception resurfaces. Acknowledgements are the only thing persisted (a small
key set, e.g. in system_metadata) — the exceptions themselves are always recomputable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

ACK_PREFIX = "dq_ack:"   # metadata key namespace for acknowledged fingerprints


@dataclass(frozen=True)
class DataQualityException:
    kind: str                 # e.g. "duplicate_conflicting" | "duplicate_identical"
    subject: str              # the thing the exception is about (e.g. a VIN)
    fingerprint: str          # stable while material evidence is unchanged; changes when evidence changes
    detail: str               # human-readable, user-visible message
    severity: str = "warning"  # "info" | "warning"
    evidence: tuple = field(default_factory=tuple)   # provenance (source rows/refs), never mutated


def fingerprint(kind: str, subject: str, material) -> str:
    """Stable fingerprint over the material evidence. `material` is any JSON-serializable structure that
    captures exactly what would make this a DIFFERENT/CHANGED exception (month, cohort, DTS, model text, …)."""
    blob = json.dumps({"kind": kind, "subject": subject, "material": material}, sort_keys=True,
                      separators=(",", ":"))
    return "dq:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def make_exception(kind, subject, material, detail, *, severity="warning", evidence=()):
    return DataQualityException(kind=kind, subject=subject,
                                fingerprint=fingerprint(kind, subject, material),
                                detail=detail, severity=severity, evidence=tuple(evidence))


def filter_unacknowledged(exceptions, is_acknowledged):
    """Return only the exceptions whose fingerprint is not acknowledged. `is_acknowledged(fp)->bool`.
    A materially-changed exception has a new fingerprint, so it is (correctly) not acknowledged."""
    return [e for e in exceptions if not is_acknowledged(e.fingerprint)]


def metadata_ack_lookup(metadata_store):
    """Adapt a key/value metadata store (get(key)->value|None) into an is_acknowledged(fingerprint) callable."""
    def _is_ack(fp):
        try:
            return metadata_store.get(ACK_PREFIX + fp) is not None
        except Exception:   # noqa: BLE001 - a missing/erroring store means "not acknowledged" (fail-open to surface)
            return False
    return _is_ack


def acknowledge(metadata_store, fingerprint_value):
    """Persist an acknowledgement (idempotent). Never touches source evidence or the original import."""
    metadata_store.put_if_absent(ACK_PREFIX + fingerprint_value, "acknowledged")
