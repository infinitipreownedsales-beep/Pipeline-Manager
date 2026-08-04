"""Typed financial-assumption + configuration validation.

Financial assumptions are POLICY records, never hardcoded constants. Each carries a
typed, unit-validated value. A percentage must name its denominator/semantic. Zero is
a valid value; blank/missing never silently becomes zero. Technical configuration is a
separate category and must not act as business policy.
"""
from __future__ import annotations

from ..errors import ValidationError

KINDS = ("currency", "percentage", "duration", "rate", "mileage", "count", "bool",
         "enum", "date", "date_range", "payload")
_DURATION_UNITS = {"days", "weeks", "months", "years"}
_MILEAGE_UNITS = {"mi", "km"}


def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValidationError(technical_detail=f"{name} must be numeric (got {type(v).__name__}); "
                                               "blank/missing is not zero")
    return v


def validate_assumption(kind: str, value) -> dict:
    """Return a normalized assumption dict or raise ValidationError."""
    if kind not in KINDS:
        raise ValidationError(technical_detail=f"unknown assumption kind {kind!r}")
    if not isinstance(value, dict):
        raise ValidationError(technical_detail="assumption value must be a typed object")

    if kind == "currency":
        _num(value.get("amount"), "amount")               # 0 is valid
        if not value.get("currency"):
            raise ValidationError(technical_detail="currency assumption requires a currency code")
        return {"kind": kind, "amount": value["amount"], "currency": value["currency"]}
    if kind == "percentage":
        _num(value.get("value"), "value")
        if not value.get("denominator"):                  # denominator/semantic REQUIRED
            raise ValidationError(message="Percentage must identify its denominator.",
                                  technical_detail="percentage assumption missing 'denominator'")
        return {"kind": kind, "value": value["value"], "denominator": value["denominator"]}
    if kind == "duration":
        _num(value.get("value"), "value")
        if value.get("unit") not in _DURATION_UNITS:
            raise ValidationError(technical_detail=f"unsupported duration unit {value.get('unit')!r}")
        return {"kind": kind, "value": value["value"], "unit": value["unit"]}
    if kind == "mileage":
        _num(value.get("value"), "value")
        if value.get("unit") not in _MILEAGE_UNITS:
            raise ValidationError(technical_detail=f"unsupported mileage unit {value.get('unit')!r}")
        return {"kind": kind, "value": value["value"], "unit": value["unit"]}
    if kind == "rate":
        _num(value.get("value"), "value")
        if not value.get("per"):
            raise ValidationError(technical_detail="rate assumption requires a 'per' basis")
        return {"kind": kind, "value": value["value"], "per": value["per"]}
    if kind == "count":
        v = value.get("value")
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValidationError(technical_detail="count must be an integer")
        return {"kind": kind, "value": v}
    if kind == "bool":
        if not isinstance(value.get("value"), bool):
            raise ValidationError(technical_detail="bool assumption requires a boolean")
        return {"kind": kind, "value": value["value"]}
    if kind == "enum":
        allowed = value.get("allowed") or []
        if value.get("value") not in allowed:
            raise ValidationError(technical_detail="enum value not in allowed set")
        return {"kind": kind, "value": value["value"], "allowed": allowed}
    if kind == "date":
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value.get("value", ""))):
            raise ValidationError(technical_detail="date assumption must be YYYY-MM-DD")
        return {"kind": kind, "value": value["value"]}
    if kind == "date_range":
        if not value.get("start") or not value.get("end"):
            raise ValidationError(technical_detail="date_range requires start and end")
        return {"kind": kind, "start": value["start"], "end": value["end"]}
    return {"kind": "payload", "payload": value.get("payload", value)}
