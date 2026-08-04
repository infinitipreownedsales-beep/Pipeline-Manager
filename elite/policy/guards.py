"""Creation-time guards: scope-dimension validation + typed value validation.

A Policy Family declares which scope dimensions it permits; an unsupported dimension
is rejected. Financial-assumption families validate the typed value (unit/denominator).
Technical configuration is a distinct category and is never treated as business policy.
"""
from __future__ import annotations

from ..errors import ValidationError
from .assumptions import validate_assumption

TECHNICAL_CATEGORIES = {"CALCULATION_CONFIGURATION"}


def validate_scope(family, scope: dict):
    allowed = set(family.allowed_scope_dimensions or [])
    for dim in (scope or {}):
        if dim not in allowed:
            raise ValidationError(message="Unsupported scope dimension.",
                                  technical_detail=f"{dim!r} not permitted by family {family.id} "
                                                   f"(allowed: {sorted(allowed)})")


def validate_value(family, value: dict):
    if family.category == "FINANCIAL_ASSUMPTION":
        if not isinstance(value, dict) or "kind" not in value:
            raise ValidationError(technical_detail="financial assumption requires a typed {kind, ...} value")
        return validate_assumption(value["kind"], value)
    return value


def is_business_policy(family) -> bool:
    """Technical configuration does not act as business policy."""
    return family.category not in TECHNICAL_CATEGORIES
