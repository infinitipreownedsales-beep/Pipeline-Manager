"""Observability helpers: safe operational logging, VIN masking, and secret/PII scrubbing.

Operational logs are diagnostics, not an ungoverned data copy. They must never contain secrets, tokens,
session IDs, raw customer personal information, or full source rows. VINs are masked to their last 6
characters where they must appear at all.
"""
from __future__ import annotations

import re

from ..logging_ import StructuredLogger, _scrub

_SECRET_HINTS = ("secret", "password", "passwd", "token", "authorization", "api_key", "apikey",
                 "pepper", "credential", "cookie", "session")
_PII_HINTS = ("customer", "first_name", "last_name", "email", "phone", "address", "ssn", "dob")
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{11})([A-HJ-NPR-Z0-9]{6})\b")


def mask_vin(vin):
    """Show only the last 6 characters of a VIN (the sequential unit portion), e.g. ***…000123."""
    if not isinstance(vin, str) or len(vin) < 6:
        return "***"
    return "***" + vin[-6:]


def mask_text(text):
    """Mask any embedded 17-char VIN in a free-text string."""
    if not isinstance(text, str):
        return text
    return _VIN_RE.sub(lambda m: "***" + m.group(2), text)


def safe_log_fields(fields):
    """Return a copy safe to write to an ordinary operational log: secrets redacted, PII dropped,
    VINs masked, and no full raw row retained."""
    out = {}
    for k, v in (fields or {}).items():
        lk = k.lower()
        if any(h in lk for h in _SECRET_HINTS):
            out[k] = "***"
            continue
        if any(h in lk for h in _PII_HINTS):
            out[k] = "<omitted>"
            continue
        if lk in ("raw_values", "raw_row", "row", "payload", "rows"):
            out[k] = "<not logged>"           # never copy a raw source row into a log
            continue
        if lk in ("vin",) and isinstance(v, str):
            out[k] = mask_vin(v)
            continue
        out[k] = mask_text(v) if isinstance(v, str) else _scrub(v)
    return out


def contains_unsafe(record_text):
    """True if a would-be log line still contains an obvious secret marker or an unmasked VIN.
    Used to REJECT unsafe log content rather than emit it."""
    if not isinstance(record_text, str):
        record_text = str(record_text)
    low = record_text.lower()
    if any(h in low for h in ("secret=", "password=", "token=", "pepper=", "authorization:")):
        return True
    if _VIN_RE.search(record_text):
        return True
    return False


class OperationalLogger:
    """Wraps the Phase 1 StructuredLogger and applies operational safety (masking/scrub, unsafe-content
    rejection) before anything is emitted. Logging failure never propagates into a governed action."""

    def __init__(self, environment, revision="pilot", stream=None):
        self._log = StructuredLogger(environment, revision)
        if stream is not None:
            self._log.stream = stream

    def op(self, component, action, result="ok", correlation_id=None, scope=None, actor=None,
           duration_ms=None, **fields):
        try:
            safe = safe_log_fields(fields)
            self._log.info(action, result=result, correlation_id=correlation_id,
                           component=component, scope=scope, actor=actor, duration_ms=duration_ms, **safe)
        except Exception:
            # logging must never corrupt or fail a governed action
            return

    def op_error(self, component, action, error_category, correlation_id=None, scope=None, **fields):
        try:
            safe = safe_log_fields(fields)
            self._log.error(action, error_category=error_category, correlation_id=correlation_id,
                            component=component, scope=scope, **safe)
        except Exception:
            return
