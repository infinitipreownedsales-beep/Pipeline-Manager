"""Normalization + distinct value semantics + VIN identity rules.

Blank, zero, false, missing, unknown, not-applicable, invalid, unresolved, and
conflicting are ALL distinct and must never collapse into one another. Raw values
are preserved verbatim; normalized values are computed alongside, never replacing
the raw.
"""
from __future__ import annotations

import enum
import re


class Special(enum.Enum):
    MISSING = "missing"        # field/column absent
    BLANK = "blank"            # present but empty
    NA = "not_applicable"      # explicit N/A
    UNKNOWN = "unknown"        # explicit unknown
    INVALID = "invalid"        # present but fails type/format rule
    UNRESOLVED = "unresolved"  # identity not resolved
    CONFLICTING = "conflicting"


def is_special(v) -> bool:
    return isinstance(v, Special)


def encode(v):
    """JSON-safe encoding that keeps specials distinct from real values (incl. 0/False)."""
    if isinstance(v, Special):
        return {"__special__": v.value}
    return v


def decode(v):
    if isinstance(v, dict) and "__special__" in v:
        return Special(v["__special__"])
    return v


_NA = {"n/a", "na", "n.a.", "not applicable"}
_UNK = {"unknown", "unk", "?", "tbd"}


def normalize_scalar(raw, kind: str = "text"):
    """Return the normalized value for a raw cell. `raw` is None when the column is
    absent. Distinct sentinels are returned for missing/blank/na/unknown/invalid."""
    if raw is None:
        return Special.MISSING
    s = str(raw).strip()
    if s == "":
        return Special.BLANK
    low = s.lower()
    if low in _NA:
        return Special.NA
    if low in _UNK:
        return Special.UNKNOWN
    if kind == "int":
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)           # explicit "0" -> 0, distinct from BLANK
        return Special.INVALID
    if kind == "number":
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return Special.INVALID
    if kind == "bool":
        if low in ("true", "1", "yes", "y"):
            return True
        if low in ("false", "0", "no", "n"):
            return False           # explicit False, distinct from BLANK/MISSING
        return Special.INVALID
    if kind == "month":
        if re.fullmatch(r"\d{4}-\d{2}", s):
            y, m = map(int, s.split("-"))
            if 1 <= m <= 12:
                return s
        m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
        if m and 1 <= int(m.group(1)) <= 12:
            return f"{m.group(2)}-{int(m.group(1)):02d}"
        return Special.INVALID
    if kind == "date":
        iso = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s|T|$)", s)
        if iso:
            date_part = iso.group(1)
            y, m, d = map(int, date_part.split("-"))
            if 1 <= m <= 12 and 1 <= d <= 31:
                return date_part
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
            return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        return Special.INVALID
    if kind == "upper":
        return s.upper()
    if kind == "vin":
        return normalize_vin(s)
    return s


# ---- VIN identity ---------------------------------------------------------
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")   # excludes I, O, Q
_PLACEHOLDERS = {"", "PENDING", "NOVIN", "NO VIN", "TBD", "N/A", "NA", "UNKNOWN"}


def normalize_vin(s: str) -> str:
    return re.sub(r"\s+", "", str(s)).upper()


def vin_status(raw) -> str:
    """'valid' | 'placeholder' | 'invalid'. Only 'valid' may establish/support a
    trusted Vehicle Unit identity."""
    if raw is None:
        return "invalid"
    s = normalize_vin(str(raw))
    if s in _PLACEHOLDERS:
        return "placeholder"
    if len(set(s)) <= 1:            # all-same-char, e.g. 00000000000000000
        return "placeholder"
    if _VIN_RE.match(s):
        return "valid"
    return "invalid"
