"""Config-key construction and value coercion.

The atomic unit of the whole engine is the *config key*:

    Model | 4-digit Code | Ext | Int      e.g.  QX80|8381|QBE|D

Every inventory unit and every sale is reduced to one of these keys before any
math happens.  All the fiddly, learned-the-hard-way normalisation lives here so
that inventory and sales resolve to *identical* keys.

Nothing in this module keeps state; every function is pure.  That is deliberate:
the whole reason we are porting away from Excel is that the app must recompute
everything from the raw inputs on every run, with no stale caches.
"""

from __future__ import annotations

import math

# Model line from the first two digits of the (4- or 5-digit) model code.
#   83 -> QX80, 84 -> QX60, 85/81/82 -> QX65
# Legacy QX50 (81xx) and QX55 (82xx) roll up to QX65 at the *model* level only
# (see the Legacy Program note in reports.py / the brief §18).
_PREFIX_TO_MODEL = {
    "83": "QX80",
    "84": "QX60",
    "85": "QX65",
    "81": "QX65",
    "82": "QX65",
}


def xround(value, digits: int = 0):
    """Round half *away from zero*, matching Excel's ROUND (not Python's
    banker's rounding).  Every rounding step in the engine mirrors a workbook
    ROUND, so 6.5 must become 7 and 200.5 must become 201.
    """
    if value is None:
        return None
    factor = 10 ** digits
    scaled = float(value) * factor
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    result = rounded / factor
    return int(result) if digits <= 0 else result


def coerce_num(value, default=0.0):
    """Coerce a value that *may* have arrived as text into a float.

    Dealer exports routinely deliver numeric fields as strings ("49"), often
    with thousands separators or stray whitespace ("1,234 ").  Comparing those
    as text silently breaks every threshold in the engine, so everything is
    forced through here before it is used in arithmetic.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    if s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default


def coerce_int(value, default=0):
    return int(round(coerce_num(value, default)))


def digits_only(value) -> str:
    """Return the code as a clean digit string (handles ints and float-ish text)."""
    if value is None:
        return ""
    if isinstance(value, float):
        value = int(value)
    return "".join(ch for ch in str(value).strip() if ch.isdigit())


def model_from_code(code) -> str:
    """Map a model code (4- or 5-digit) to its model line, or "" if unknown."""
    d = digits_only(code)
    return _PREFIX_TO_MODEL.get(d[:2], "") if len(d) >= 2 else ""


def code4(code) -> str:
    """Reduce a raw model code to its 4-digit matching form.

    Inventory codes are 5-digit; the 5th digit is the model year (7=2027,
    6=2026, 5=2025).  Sales codes are already 4-digit.  We drop the year digit
    so an inventory unit and its sales history share one key.
    """
    d = digits_only(code)
    return d[:4] if len(d) >= 4 else d


def model_year_from_code(code):
    """2020 + the 5th (model-year) digit of a 5-digit inventory code, else None."""
    d = digits_only(code)
    if len(d) == 5 and d[4].isdigit():
        return 2020 + int(d[4])
    return None


def normalize_code(model: str, raw_code) -> str:
    """Apply the two learned code re-maps, then reduce to 4 digits.

    * QX80 Sport codes 834x consolidate to 8381 (the Sport 4WD engine base).
    * QX60 8461 (Autograph FWD, discontinued) folds into 8481 (Autograph AWD).

    Both re-maps are keyed off the *raw* code prefix exactly like the workbook,
    so a 5-digit 83416 and a 4-digit 8341 both land on 8381.
    """
    d = digits_only(raw_code)
    if model == "QX80" and d[:3] == "834":
        return "8381"
    if model == "QX60" and d[:4] == "8461":
        return "8481"
    return code4(raw_code)


def normalize_int(model: str, code: str, ext: str, interior: str) -> str:
    """QX80 Sport (8381) consolidates the G and D interiors into a single D key."""
    interior = (interior or "").strip()
    if model == "QX80" and code == "8381" and interior in ("G", "D"):
        return "D"
    return interior


def build_key(model: str, raw_code, ext, interior) -> str:
    """Build the canonical `Model|Code|Ext|Int` key, or "" if it can't resolve."""
    if not model:
        return ""
    code = normalize_code(model, raw_code)
    ext = (str(ext).strip() if ext is not None else "")
    interior = normalize_int(model, code, ext, interior)
    if not code:
        return ""
    return f"{model}|{code}|{ext}|{interior}"


def key_from_sales_code(raw_code, ext, interior) -> str:
    """Build a key from a sales-report row (model derived from the code)."""
    return build_key(model_from_code(raw_code), raw_code, ext, interior)
