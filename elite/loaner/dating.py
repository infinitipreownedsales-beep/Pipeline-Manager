"""In-service-date authority + Last Checkout Mileage.

Verified authoritative in-service date controls tenure-based eligibility. File import date never
substitutes for in-service date; first observed presence never silently becomes the in-service date
unless an approved fallback permits it; conflicting dates stay unresolved or follow approved
precedence; corrections preserve prior-as-known. Last Checkout Mileage: zero is a valid explicit
value, distinct from blank and missing; invalid mileage never becomes authoritative; later values
supersede current use without erasing history; it is not the current odometer, and unrecorded
mileage is never inferred.
"""
from __future__ import annotations

from ..data.normalize import Special, normalize_scalar
from ..ids import new_id
from .models import CheckoutMileage, InServiceDateResolution


class DatingService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def resolve_in_service_date(self, unit, candidates, *, allow_first_presence_fallback=False,
                                import_date=None):
        """`candidates`: [{value, source, authority}] where authority in
        verified/reported/import/first_presence. A verified value wins; import date never
        substitutes; first-presence is used only under an approved fallback; conflicting verified
        values stay unresolved unless a precedence is given."""
        verified = [c for c in candidates if c.get("authority") == "verified" and c.get("value")]
        distinct_verified = {c["value"] for c in verified}
        accepted, authority, conflict = None, "unverified", None
        if len(distinct_verified) == 1:
            accepted, authority = next(iter(distinct_verified)), "verified"
        elif len(distinct_verified) > 1:
            authority, conflict = "unresolved", "conflicting verified in-service dates"
        else:
            fp = [c for c in candidates if c.get("authority") == "first_presence" and c.get("value")]
            if allow_first_presence_fallback and fp:
                accepted, authority = fp[0]["value"], "fallback"
            # import date is NEVER accepted as the in-service date
        r = self.store.add_in_service_resolution(InServiceDateResolution(
            id=new_id("slisd"), service_loaner_unit_id=unit.id, candidate_values=candidates,
            source=",".join(sorted({c.get("source", "") for c in candidates})), authority_level=authority,
            accepted_value=accepted, conflict_state=conflict,
            evidence={"import_date_ignored": import_date, "fallback": allow_first_presence_fallback}))
        if accepted:
            with self.store.conn:
                self.store.set_unit_field(self.store.conn, unit.id, accepted_in_service_date=accepted,
                                          in_service_date_authority=authority)
        return r

    def correct_in_service_date(self, unit, new_value, *, source="correction"):
        """Corrected in-service date preserves prior resolutions (append) and updates current use."""
        r = self.store.add_in_service_resolution(InServiceDateResolution(
            id=new_id("slisd"), service_loaner_unit_id=unit.id,
            candidate_values=[{"value": new_value, "source": source, "authority": "verified"}],
            source=source, authority_level="verified", accepted_value=new_value,
            correction_of=(self.store.in_service_resolutions(unit.id)[-1].id
                           if self.store.in_service_resolutions(unit.id) else None)))
        with self.store.conn:
            self.store.set_unit_field(self.store.conn, unit.id, accepted_in_service_date=new_value,
                                      in_service_date_authority="verified")
        return r

    # ---- Last Checkout Mileage --------------------------------------------
    def record_mileage(self, unit, raw_value, *, snapshot_ref=None, source="snapshot"):
        """Record Last Checkout Mileage with distinct value semantics. `raw_value` is the raw source
        cell (None = column missing)."""
        norm = normalize_scalar(raw_value, kind="int")
        if isinstance(norm, Special):
            kind = {"missing": "missing", "blank": "blank"}.get(norm.value, "invalid")
            value = None
        elif isinstance(norm, int):
            kind, value = ("zero" if norm == 0 else "value"), norm
        else:
            kind, value = "invalid", None
        return self.store.add_mileage(CheckoutMileage(
            id=new_id("slm"), service_loaner_unit_id=unit.id, value_kind=kind, value=value,
            snapshot_ref=snapshot_ref, source=source,
            provenance={"raw": raw_value, "snapshot": snapshot_ref}))

    @staticmethod
    def is_authoritative_zero(mileage: CheckoutMileage) -> bool:
        """Only an explicit accepted zero counts as a zero checkout mileage (never blank/missing/
        invalid)."""
        return bool(mileage) and mileage.value_kind == "zero"
