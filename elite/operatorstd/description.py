"""Governed vehicle description — the ONE place raw INFINITI codes become human language.

Rules (item 2 / item 3 of the operator-intelligence standard):
  * Codes are preserved for machine precision; human language is ADDED, never substituted destructively.
  * Every human token comes from the governed Translation & Identity store (approved SAME_AS mappings and
    approved family/variant interpretations). There is NO independent per-domain dictionary here.
  * Unknown codes FAIL HONESTLY — we surface the code with an explicit "(unmapped)" marker and set an
    `unresolved` flag; we NEVER guess a trim, drivetrain, or colour name.
  * Colour names are only ever taken from authoritative/governed evidence. The DMS inventory feed carries the
    exterior/interior CODE only (`ext` / `int`); the human colour name lives in the governed store.

Preferred operator presentation:  "Radiant White (QBE) / Graphite (G)"   (name leads, code in parens)
Dealer-facing presentation:       "2027 QX80 LUXE 2WD — Radiant White / Graphite"   (names only; codes optional)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# The order portal is where the governed colour/model-line vocabulary was seeded; DMS inventory reuses the same
# manufacturer codes, so description resolves against the portal vocabulary via the any-source fallback.
DEFAULT_SOURCE = "NNA_ORDER_PORTAL"
UNMAPPED = "(unmapped)"


@dataclass
class Described:
    """The resolved description of one vehicle/combination. Carries both codes and human language plus honest
    per-axis unresolved flags, so a caller can render exactly the presentation its surface calls for."""
    model: str = ""
    trim: str = ""
    drivetrain: str = ""
    model_year: str = ""
    model_code: str = ""
    exterior_code: str = ""
    interior_code: str = ""
    exterior_name: str = ""
    interior_name: str = ""
    unresolved: tuple = ()            # axes with no governed evidence: any of model/trim/drivetrain/exterior/interior
    description_conflict: bool = False  # DMS Description model disagrees with canonical model → one review (item 6)
    proof: dict = field(default_factory=dict)

    # ---- presentations -------------------------------------------------------------------------------------
    @property
    def has_family(self) -> bool:
        return bool(self.model and self.trim and self.drivetrain)

    def _vehicle(self, *, clean=False) -> str:
        """Human model/trim/drivetrain with year when known: "2027 QX80 LUXE 2WD". In operator mode an unmapped
        model_code surfaces the code with an explicit marker (never a guessed trim); in dealer mode (clean=True)
        that internal-code noise is omitted — another dealer only ever sees governed human language."""
        parts = []
        if self.model_year:
            parts.append(str(self.model_year))
        if self.model:
            parts.append(self.model)
        if self.trim:
            parts.append(self.trim)
        if self.drivetrain:
            parts.append(self.drivetrain)
        core = " ".join(parts)
        if clean:
            return core or (self.model or "—")
        if not self.model and self.model_code:
            core = f"{core} [{self.model_code}]".strip()
        if ("trim" in self.unresolved or "drivetrain" in self.unresolved) and self.model_code:
            core = f"{core} [{self.model_code} {UNMAPPED}]"
        return core or (f"[{self.model_code}]" if self.model_code else "—")

    @property
    def vehicle(self) -> str:
        return self._vehicle(clean=False)

    def _colour(self, code, name, *, with_code, drop_unmapped):
        if name and code:
            return f"{name} ({code})" if with_code else name
        if code and not drop_unmapped:
            return f"{code} {UNMAPPED}"
        return ""

    def colours(self, *, with_code=True, drop_unmapped=False) -> str:
        """"Radiant White (QBE) / Graphite (G)" — operator form. Dealer form (with_code=False) drops the codes;
        drop_unmapped additionally hides any code with no governed name (so a dealer never sees "QBE (unmapped)").
        A missing code shows nothing — never a fabricated colour."""
        ext = self._colour(self.exterior_code, self.exterior_name, with_code=with_code, drop_unmapped=drop_unmapped)
        it = self._colour(self.interior_code, self.interior_name, with_code=with_code, drop_unmapped=drop_unmapped)
        if ext and it:
            return f"{ext} / {it}"
        return ext or it or ""

    @property
    def operator(self) -> str:
        """Full operator line: "2027 QX80 LUXE 2WD — Radiant White (QBE) / Graphite (G)"."""
        c = self.colours(with_code=True)
        return f"{self.vehicle} — {c}" if c else self.vehicle

    @property
    def dealer(self) -> str:
        """Dealer-facing line: names lead, no codes, no internal-code noise (item 12). Human colours only when
        governed. "2027 QX80 LUXE 2WD — Radiant White / Graphite"."""
        veh = self._vehicle(clean=True)
        c = self.colours(with_code=False, drop_unmapped=True)
        return f"{veh} — {c}" if c else veh

    @property
    def codes(self) -> str:
        """Compact machine form kept available secondarily: "86317 QBE/G"."""
        col = "/".join(x for x in (self.exterior_code, self.interior_code) if x)
        return " ".join(x for x in (self.model_code, col) if x)


# Drivetrain tokens a DMS Description may carry, in canonical human form.
_DRIVETRAINS = ("2WD", "4WD", "AWD", "FWD", "RWD")


def parse_dms_description(desc, *, model=""):
    """Parse a DMS `Description` (e.g. "QX80 LUXE 2WD") into (trim, drivetrain, agrees_with_model).

    Model number remains king: this reads the source's OWN human wording for a physical VIN — it never decodes
    a model code and never overrides the canonical model. `agrees_with_model` is True only when the description
    leads with the canonical model line, so a caller can auto-resolve on agreement and raise ONE conflict review
    on disagreement (item 6). Returns ("", "", False) when nothing usable is present — never a guess."""
    d = " ".join(str(desc or "").split())
    if not d:
        return "", "", False
    toks = d.split(" ")
    desc_model = toks[0].upper()
    agrees = (not model) or (desc_model == str(model).strip().upper())
    drivetrain = ""
    body = toks[1:]
    if body and body[-1].upper() in _DRIVETRAINS:
        drivetrain = body[-1].upper()
        body = body[:-1]
    trim = " ".join(body).strip()
    return trim, drivetrain, agrees


def describe(store, *, model="", trim="", drivetrain="", model_year="", model_code="",
             exterior_code="", interior_code="", source_description="", source_system=DEFAULT_SOURCE) -> Described:
    """Build a Described from whatever a source row carries, resolving human language from the governed
    TranslationStore. `store` is an identity.translation.TranslationStore (or None → codes-only, all unresolved).

    Family resolution: if trim/drivetrain are not supplied but a model_code is, resolve the governed commercial
    family for that code (approved variant interpretation). For a physical VIN the DMS Description supplies
    trim/drivetrain when it agrees with the canonical model (item 6). Colour resolution uses the governed display
    resolver scoped to the resolved model. Nothing is guessed; every gap is flagged in `.unresolved`."""
    model = (model or "").strip()
    trim = (trim or "").strip()
    drivetrain = (drivetrain or "").strip()
    model_year = str(model_year or "").strip()
    model_code = (model_code or "").strip()
    exterior_code = (exterior_code or "").strip()
    interior_code = (interior_code or "").strip()
    unresolved = []
    proof = {}
    description_conflict = False

    # ---- physical VIN: the DMS Description is the authoritative human trim/drivetrain, used ONLY when it agrees
    #      with the canonical model (model number stays king). Disagreement is surfaced, never silently chosen. ----
    if source_description and (not trim or not drivetrain):
        s_trim, s_drive, agrees = parse_dms_description(source_description, model=model or model_code[:2])
        if agrees:
            trim = trim or s_trim
            drivetrain = drivetrain or s_drive
            if s_trim or s_drive:
                proof["dms_description"] = source_description
        else:
            description_conflict = True         # DMS Description model disagrees with canonical — one review

    # ---- model / trim / drivetrain from the governed family (only where not already supplied) ----
    if (not model or not trim or not drivetrain) and model_code and store is not None:
        fam = store.family_for_code(model_code)
        if fam is not None:
            model = model or fam.model
            trim = trim or fam.trim
            drivetrain = drivetrain or fam.drivetrain
            proof["family"] = fam.as_str()
    # model may also be recoverable from the model_code's first-two-digit model-line mapping
    if not model and model_code and store is not None:
        ml = store.resolve_display("model_code", model_code[:2], source_system=source_system)
        if ml:
            model = ml[1]
            proof["model_line"] = model_code[:2]
    if not model:
        unresolved.append("model")
    if not trim:
        unresolved.append("trim")
    if not drivetrain:
        unresolved.append("drivetrain")

    # ---- colours from the governed display resolver, scoped to the resolved model ----
    exterior_name = interior_name = ""
    if exterior_code:
        r = store.resolve_display("exterior", exterior_code, model=model, source_system=source_system) if store else None
        if r:
            exterior_name = r[1]
            proof["exterior"] = exterior_code
        else:
            unresolved.append("exterior")
    if interior_code:
        r = store.resolve_display("interior", interior_code, model=model, source_system=source_system) if store else None
        if r:
            interior_name = r[1]
            proof["interior"] = interior_code
        else:
            unresolved.append("interior")

    if description_conflict:
        proof["description_conflict"] = source_description
    return Described(model=model, trim=trim, drivetrain=drivetrain, model_year=model_year, model_code=model_code,
                     exterior_code=exterior_code, interior_code=interior_code, exterior_name=exterior_name,
                     interior_name=interior_name, unresolved=tuple(unresolved), proof=proof,
                     description_conflict=description_conflict)


def describe_row(store, row, *, source_system=DEFAULT_SOURCE) -> Described:
    """Convenience: describe a DMS/inventory-style dict row (keys model, model_year, model_code, ext/exterior,
    int/interior, trim, drivetrain, description). Franchise/source-agnostic aliases mirror
    identity.ingest.IDENTITY_COLUMNS."""
    def g(*keys):
        for k in keys:
            v = row.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""
    return describe(store,
                    model=g("model"), trim=g("trim", "trim_level", "trim_desc"),
                    drivetrain=g("drivetrain", "drive"), model_year=g("model_year", "year", "my"),
                    model_code=g("model_code"),
                    exterior_code=g("exterior", "exterior_code", "ext", "exterior_color"),
                    interior_code=g("interior", "interior_code", "int", "interior_color"),
                    source_description=g("description", "Description", "desc"),
                    source_system=source_system)
