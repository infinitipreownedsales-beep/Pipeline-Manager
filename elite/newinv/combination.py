"""Sellable Combination canonicalization + identity + lineage.

A Sellable Combination represents a REAL orderable and sellable configuration. Its canonical
identity is built only from independently-selectable, demand-material dimensions — standard
trim *content* never becomes a separate demand dimension. Model year may be dropped only under
an approved immateriality rule. Two different interiors remain distinguishable when reliable
evidence exists. Corrections preserve the prior identity; cross-store combinations never merge
without an approved aggregation rule (they are always scoped).
"""
from __future__ import annotations

from ..data.normalize import Special
from ..errors import ValidationError
from ..ids import new_id
from .models import CombinationLineage, SellableCombination

# Dimensions that participate in canonical identity, in order. Interior color is included
# because it is independently selectable and can be demand-material.
IDENTITY_DIMS = ("franchise", "model", "model_year", "trim", "drivetrain",
                 "exterior_color", "interior_color")


def _norm(v):
    """Normalize an attribute value for identity. Unknown remains unknown (never blank=known)."""
    if v is None:
        return "∅"
    if isinstance(v, Special):
        return f"«{v.name.lower()}»"           # unknown/blank/na stay distinct, never collapse to a value
    s = str(v).strip()
    return s.upper() if s else "∅"


def canonical_identity(attrs: dict, *, model_year_material: bool = True) -> str:
    """Build the canonical identity string from demand-material dimensions.

    `model_year_material=False` (an approved immateriality rule) drops model year only."""
    if not attrs.get("model"):
        raise ValidationError(message="A sellable combination requires a model.",
                              technical_detail="missing model in combination attributes")
    parts = []
    for dim in IDENTITY_DIMS:
        if dim == "model_year" and not model_year_material:
            parts.append("model_year=*")
            continue
        parts.append(f"{dim}={_norm(attrs.get(dim))}")
    return "|".join(parts)


class CombinationService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def resolve_or_create(self, attrs: dict, scope, *, model_year_material=True, source_ref=None,
                          quality_status="ok"):
        """Return the canonical combination for these attributes in this scope, creating it if
        new. Identity dedups within scope only — the same config in another store is distinct."""
        ident = canonical_identity(attrs, model_year_material=model_year_material)
        existing = self.store.find_combination_by_identity(ident, scope)
        if existing is not None:
            if source_ref:
                self.store.add_combination_alias(existing.id, "source", source_ref, scope, source_ref)
            return existing
        c = SellableCombination(
            id=new_id("comb"), store_scope=scope, model=str(attrs["model"]).upper(),
            canonical_identity=ident, franchise=attrs.get("franchise", "") or "",
            model_year=None if not model_year_material else _text(attrs.get("model_year")),
            trim=_text(attrs.get("trim")), drivetrain=_text(attrs.get("drivetrain")),
            exterior_color=_text(attrs.get("exterior_color")), interior_color=_text(attrs.get("interior_color")),
            source_refs=[source_ref] if source_ref else [], quality_status=quality_status,
            lineage_metadata={"model_year_material": model_year_material})
        self.store.add_combination(c)
        if source_ref:
            self.store.add_combination_alias(c.id, "source", source_ref, scope, source_ref)
        return c

    def correct(self, combination_id, new_attrs: dict, scope, *, model_year_material=True, source_ref=None):
        """Create a corrected combination (new identity) and mark the original corrected,
        preserving the prior identity history (never overwritten)."""
        orig = self.store.get_combination(combination_id)
        if orig is None:
            raise ValidationError(technical_detail="combination not found")
        ident = canonical_identity(new_attrs, model_year_material=model_year_material)
        corrected = SellableCombination(
            id=new_id("comb"), store_scope=scope, model=str(new_attrs["model"]).upper(), canonical_identity=ident,
            franchise=new_attrs.get("franchise", "") or "", model_year=_text(new_attrs.get("model_year")),
            trim=_text(new_attrs.get("trim")), drivetrain=_text(new_attrs.get("drivetrain")),
            exterior_color=_text(new_attrs.get("exterior_color")), interior_color=_text(new_attrs.get("interior_color")),
            source_refs=[source_ref] if source_ref else [], correction_of=orig.id,
            lineage_metadata={"corrects": orig.id, "model_year_material": model_year_material})
        self.store.add_combination(corrected)
        self.store.set_combination_status(orig.id, orig.version, "corrected",
                                          corrected_at=self.store._now())
        # preserve prior aliases as history + link forward
        self.store.add_combination_alias(corrected.id, "correction_of", orig.id, scope, source_ref)
        return corrected

    def link_lineage(self, from_id, to_id, relationship, *, comparability="comparable",
                     approved_rule_ref=None, evidence_refs=None):
        """Record an explicit, versioned lineage relationship. A materially-changed generation
        must supply an approved comparability rule to be treated as comparable."""
        if relationship == "generation_change" and comparability == "comparable" and not approved_rule_ref:
            raise ValidationError(
                message="A generation change needs an approved comparability rule to inherit history.",
                technical_detail="generation_change marked comparable without approved_rule_ref")
        return self.store.add_lineage(CombinationLineage(
            id=new_id("lin"), from_combination_id=from_id, to_combination_id=to_id, relationship=relationship,
            comparability=comparability, approved_rule_ref=approved_rule_ref, evidence_refs=list(evidence_refs or [])))


def _text(v):
    if v is None or isinstance(v, Special):
        return None
    s = str(v).strip()
    return s or None
