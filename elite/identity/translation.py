"""Translation & Identity — governed, source-backed mapping of raw source tokens to canonical Elite meaning,
commercial families, generation/planning segments, factory-option variants, and the preferred order version.

Approved design contract:
  Raw Identity -> Canonical Semantic Identity -> Commercial Family -> Generation/Planning Segment -> Variant
  -> Preferred Order Version.

Principles baked in here:
  * Raw observations are IMMUTABLE and never deleted; a preference chart is an effective-dated snapshot, so
    absence from a later chart is `not_seen_latest`, NEVER `discontinued` (that requires authoritative evidence).
  * Relations are governed and specific: SAME_AS (context-scoped value equivalence, e.g. interior `P` differs
    by model line), SAME_FAMILY_AS (distinct raw order identities = one commercial family; may SHARE demand as
    lineage, never as exact; may NOT cross drivetrain), VARIANT_OF_BASE (factory-option rows are variants, not
    separate demand families).
  * Commercial Family = franchise + model + trim + drivetrain. Generation is a Planning Segment UNDER the
    family: demand may roll up across segments (lineage), but supply is counted per segment and never crosses
    generations without an explicitly approved substitution.
  * Preferred Order Version resolves: Commercial Family -> BASE preference -> authoritative orderability ->
    exact raw ORDER identity. A `$0` / Pending-Changes row is orderability `unresolved` (not unavailable); a
    priced package is NEVER auto-substituted for a pending BASE. If no preferred BASE member is confirmed
    orderable, we surface "BASE preferred — orderability unresolved" rather than manufacture an order call.

Storage is governed JSON in the existing prefs store (no schema change, schema stays v12). Keys are
franchise/source-agnostic: a new source or franchise is onboarded by adding rows, never by editing code.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ValidationError

SEMANTIC_TYPES = ("model_code", "trim", "drivetrain", "exterior", "interior", "package")
SEEN_STATES = ("first_seen", "seen_latest", "seen_previously", "not_seen_latest", "unresolved", "discontinued")
ORDERABILITY = ("orderable", "unresolved", "discontinued")
APPROVAL = ("proposed", "approved", "retired")
RELATIONS = ("SAME_AS", "SAME_FAMILY_AS", "VARIANT_OF_BASE")


@dataclass(frozen=True)
class FamilyKey:
    """The commercial (demand) identity — franchise + model + trim + drivetrain. The raw order/model code is
    NEVER the permanent demand identity."""
    franchise: str
    model: str
    trim: str
    drivetrain: str

    def as_str(self) -> str:
        return f"{self.franchise}·{self.model}·{self.trim}·{self.drivetrain}"

    @staticmethod
    def parse(s: str) -> "FamilyKey":
        parts = (s or "").split("·")
        while len(parts) < 4:
            parts.append("")
        return FamilyKey(parts[0], parts[1], parts[2], parts[3])


@dataclass
class SemanticMapping:
    """A governed SAME_AS: one raw value on one axis -> a canonical token + display name. Context-scoped via
    `model_scope` because the same raw code can mean different things per model line (interior `P` = Sepia
    Brown on QX80 but Saddle Brown on QX60)."""
    source_system: str
    semantic_type: str
    raw_value: str
    canonical_token: str
    display_name: str
    model_scope: str = ""          # "" = applies to any model line; otherwise a specific model line
    approval: str = "proposed"
    proof_refs: tuple = ()
    active: bool = True

    def to_dict(self):
        return dict(source_system=self.source_system, semantic_type=self.semantic_type, raw_value=self.raw_value,
                    canonical_token=self.canonical_token, display_name=self.display_name,
                    model_scope=self.model_scope, approval=self.approval, proof_refs=list(self.proof_refs),
                    active=self.active)

    @staticmethod
    def from_dict(d):
        return SemanticMapping(d["source_system"], d["semantic_type"], d["raw_value"], d["canonical_token"],
                               d["display_name"], d.get("model_scope", ""), d.get("approval", "proposed"),
                               tuple(d.get("proof_refs", ())), d.get("active", True))


@dataclass
class VariantRow:
    """One observed orderable line from a preference chart: a raw order code + factory-option package within a
    family and generation, with its own seen-state, pricing and derived orderability. This is the atom the
    Preferred-Order policy resolves over."""
    family: FamilyKey
    raw_code: str
    generation_id: str             # e.g. "83" (prior gen) / "86" (new gen)
    package: str                   # BASE / PA1 / PA2 / SEA / DBI / TOW / TPA / combos
    is_base: bool
    seen_state: str = "seen_latest"
    priced: bool = False
    orderability: str = "unresolved"
    proof_refs: tuple = ()

    def to_dict(self):
        return dict(family=self.family.as_str(), raw_code=self.raw_code, generation_id=self.generation_id,
                    package=self.package, is_base=self.is_base, seen_state=self.seen_state, priced=self.priced,
                    orderability=self.orderability, proof_refs=list(self.proof_refs))

    @staticmethod
    def from_dict(d):
        return VariantRow(FamilyKey.parse(d["family"]), d["raw_code"], d["generation_id"], d["package"],
                          d["is_base"], d.get("seen_state", "seen_latest"), d.get("priced", False),
                          d.get("orderability", "unresolved"), tuple(d.get("proof_refs", ())))


@dataclass
class PreferredOrderPolicy:
    """Governed, user-maintainable ordering policy for a family (NOT hardcoded per model). Default is BASE."""
    family: FamilyKey
    prefer_package: str = "BASE"
    preferred_member: str = ""                 # explicit member raw_code override, "" = none
    prefer_generation: str = ""                # explicit generation preference, "" = newest orderable
    accepted_substitution: tuple = ()          # (raw_code, package) explicitly authorized (evidence-backed)

    def to_dict(self):
        return dict(family=self.family.as_str(), prefer_package=self.prefer_package,
                    preferred_member=self.preferred_member, prefer_generation=self.prefer_generation,
                    accepted_substitution=list(self.accepted_substitution))

    @staticmethod
    def from_dict(d):
        return PreferredOrderPolicy(FamilyKey.parse(d["family"]), d.get("prefer_package", "BASE"),
                                    d.get("preferred_member", ""), d.get("prefer_generation", ""),
                                    tuple(d.get("accepted_substitution", ())))


# --- pure policy helpers -------------------------------------------------------------------------------------
def derive_orderability(seen_state: str, priced: bool, explicit: str = "") -> str:
    """Orderability from an observation. A `$0` / Pending-Changes row (seen but not priced) is `unresolved`,
    NOT `discontinued`. `discontinued` only comes from authoritative evidence (an explicit override)."""
    if explicit in ORDERABILITY:
        return explicit
    if seen_state == "discontinued":
        return "discontinued"
    if seen_state == "seen_latest" and priced:
        return "orderable"
    return "unresolved"


def check_same_family_drivetrain(family: FamilyKey, member_drivetrain: str) -> None:
    """SAME_FAMILY_AS may not cross drivetrain. Crossing 2WD<->4WD is a different commercial family and needs a
    separate, explicitly-approved substitution relationship — never a silent family merge."""
    if member_drivetrain and member_drivetrain != family.drivetrain:
        raise ValidationError(
            message="SAME FAMILY AS cannot cross drivetrain — that is a different commercial family.",
            technical_detail=f"member drivetrain {member_drivetrain!r} != family {family.drivetrain!r}")


def demand_evidence_tier(source_raw_code: str, target_raw_code: str, same_family: bool) -> str:
    """Evidence tier when `target` uses `source`'s demand history. A member's OWN history is `exact`; history
    borrowed from another member of the same family is `lineage` (never automatically exact); anything else
    does not transfer."""
    if source_raw_code == target_raw_code:
        return "exact"
    if same_family:
        return "lineage"
    return "none"


def _gen_rank(gid: str):
    d = "".join(ch for ch in str(gid) if ch.isdigit())
    return (1, int(d)) if d else (0, str(gid))


def resolve_preferred_order(rows, policy: PreferredOrderPolicy) -> dict:
    """Resolve the family's ORDER identity: Commercial Family -> BASE preference -> authoritative orderability
    -> exact raw ORDER identity. Never auto-substitutes a priced package for a pending BASE; if no preferred
    BASE member is confirmed orderable, returns an `unresolved` status carrying the honest candidate list."""
    rows = list(rows)
    orderable = [r for r in rows if r.orderability == "orderable"]
    # (1) an explicitly authorized package substitution (evidence-backed) wins, if that exact row is orderable
    if policy.accepted_substitution:
        rc, pk = policy.accepted_substitution
        for r in orderable:
            if r.raw_code == rc and r.package == pk:
                return _order(r, "authorized_substitution")
    # (2) the preferred BASE variant, only where authoritative orderability confirms it
    base_orderable = [r for r in orderable if r.is_base and r.package == policy.prefer_package]
    if base_orderable:
        return _order(_pick(base_orderable, policy), "base_preferred")
    # (3) nothing preferred is confirmed orderable -> surface, do not manufacture an order
    return {"status": "unresolved",
            "message": f"{policy.prefer_package} preferred — orderability unresolved",
            "family": policy.family.as_str(),
            "candidates": [{"raw_code": r.raw_code, "generation": r.generation_id, "package": r.package,
                            "orderability": r.orderability, "seen_state": r.seen_state} for r in rows]}


def _pick(rows, policy):
    if policy.preferred_member:
        for r in rows:
            if r.raw_code == policy.preferred_member:
                return r
    if policy.prefer_generation:
        g = [r for r in rows if r.generation_id == policy.prefer_generation]
        if g:
            rows = g
    return sorted(rows, key=lambda r: (_gen_rank(r.generation_id), r.raw_code))[-1]   # newest generation


def _order(r, reason):
    return {"status": "order", "raw_code": r.raw_code, "package": r.package, "generation": r.generation_id,
            "family": r.family.as_str(), "reason": reason}


# --- governed store (JSON in the prefs store; no schema change) ---------------------------------------------
class TranslationStore:
    """Store-scoped governed persistence for the translation & identity layer. Franchise/source-agnostic: the
    key of a mapping is (source_system, semantic_type, raw_value[, model_scope]) — nothing model-specific is
    baked into logic. Raw observations are append-only and never mutated destructively."""

    K_SEM = "xlat_semantic"
    K_ROWS = "xlat_variant_rows"
    K_POLICY = "xlat_policy"
    K_OBS = "xlat_observation"

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self.scope = scope
        self._sk = f"scope::{scope}"

    def _get(self, key, default):
        return self.prefs.get_pref(self._sk, key, default=default)

    def _put(self, key, value):
        self.prefs.set_pref(self._sk, key, value)

    # ---- immutable raw observations ----
    def record_observation(self, source_system, semantic_type, raw_value, *, as_of, proof_ref="",
                           seen_state="seen_latest"):
        """Record (or refresh the last-seen of) an immutable raw observation. Never deletes or rewrites an
        existing raw value — only updates first/last-seen and seen-state."""
        obs = self._get(self.K_OBS, []) or []
        for o in obs:
            if (o["source_system"], o["semantic_type"], o["raw_value"]) == (source_system, semantic_type, raw_value):
                o["last_seen"] = as_of
                o["seen_state"] = seen_state
                if proof_ref and proof_ref not in o.get("proof_refs", []):
                    o.setdefault("proof_refs", []).append(proof_ref)
                self._put(self.K_OBS, obs)
                return o
        rec = {"source_system": source_system, "semantic_type": semantic_type, "raw_value": raw_value,
               "first_seen": as_of, "last_seen": as_of, "seen_state": "first_seen",
               "proof_refs": [proof_ref] if proof_ref else []}
        obs.append(rec)
        self._put(self.K_OBS, obs)
        return rec

    def observations(self):
        return list(self._get(self.K_OBS, []) or [])

    def mark_not_seen_latest(self, keep_source_type_values):
        """Mark observations absent from the latest chart as `not_seen_latest` (NEVER discontinued). Absence is
        not evidence of discontinuation. `keep_source_type_values` is the set of (source, type, raw) seen now."""
        obs = self._get(self.K_OBS, []) or []
        for o in obs:
            if (o["source_system"], o["semantic_type"], o["raw_value"]) not in keep_source_type_values \
                    and o["seen_state"] not in ("discontinued",):
                o["seen_state"] = "not_seen_latest"
        self._put(self.K_OBS, obs)

    # ---- SAME_AS semantic mappings ----
    def upsert_semantic(self, m: SemanticMapping):
        rows = self._get(self.K_SEM, []) or []
        for i, r in enumerate(rows):
            if (r["source_system"], r["semantic_type"], r["raw_value"], r.get("model_scope", "")) == \
                    (m.source_system, m.semantic_type, m.raw_value, m.model_scope):
                rows[i] = m.to_dict()
                self._put(self.K_SEM, rows)
                return
        rows.append(m.to_dict())
        self._put(self.K_SEM, rows)

    def semantic_mappings(self):
        return [SemanticMapping.from_dict(d) for d in (self._get(self.K_SEM, []) or [])]

    def approve_semantic(self, source_system, semantic_type, raw_value, model_scope=""):
        rows = self._get(self.K_SEM, []) or []
        for r in rows:
            if (r["source_system"], r["semantic_type"], r["raw_value"], r.get("model_scope", "")) == \
                    (source_system, semantic_type, raw_value, model_scope):
                r["approval"] = "approved"
                self._put(self.K_SEM, rows)
                return True
        return False

    def translate(self, source_system, semantic_type, raw_value, *, model=""):
        """Return the canonical (token, display_name) for a raw value, honouring APPROVED, ACTIVE mappings and
        context scope (a model-scoped mapping wins for that model; a scope-less mapping is the fallback). None
        when unresolved — the caller surfaces it rather than guessing."""
        best = None
        for m in self.semantic_mappings():
            if not (m.active and m.approval == "approved"):
                continue
            if m.source_system != source_system or m.semantic_type != semantic_type or m.raw_value != raw_value:
                continue
            if m.model_scope and m.model_scope != model:
                continue
            if m.model_scope and m.model_scope == model:
                return (m.canonical_token, m.display_name)       # exact context match wins immediately
            if not m.model_scope:
                best = (m.canonical_token, m.display_name)        # scope-less fallback
        return best

    def unresolved_translations(self):
        """Raw observations with no APPROVED active SAME_AS mapping — the Data-Health resolution queue."""
        approved = {(m.source_system, m.semantic_type, m.raw_value)
                    for m in self.semantic_mappings() if m.active and m.approval == "approved"}
        return [o for o in self.observations()
                if (o["source_system"], o["semantic_type"], o["raw_value"]) not in approved]

    # ---- variant rows (family + generation + package) ----
    def add_variant_row(self, row: VariantRow):
        rows = self._get(self.K_ROWS, []) or []
        key = (row.family.as_str(), row.raw_code, row.generation_id, row.package)
        for i, d in enumerate(rows):
            if (d["family"], d["raw_code"], d["generation_id"], d["package"]) == key:
                rows[i] = row.to_dict()          # idempotent: refresh, never duplicate a chart row
                self._put(self.K_ROWS, rows)
                return
        rows.append(row.to_dict())
        self._put(self.K_ROWS, rows)

    def variant_rows(self, family: FamilyKey = None):
        rows = [VariantRow.from_dict(d) for d in (self._get(self.K_ROWS, []) or [])]
        return [r for r in rows if family is None or r.family.as_str() == family.as_str()]

    def segments(self, family: FamilyKey):
        """Distinct generation/planning segments observed for a family (each keeps its own supply accounting)."""
        return sorted({r.generation_id for r in self.variant_rows(family)}, key=_gen_rank)

    # ---- preferred-order policy ----
    def set_policy(self, policy: PreferredOrderPolicy):
        pols = self._get(self.K_POLICY, {}) or {}
        pols[policy.family.as_str()] = policy.to_dict()
        self._put(self.K_POLICY, pols)

    def policy(self, family: FamilyKey) -> PreferredOrderPolicy:
        pols = self._get(self.K_POLICY, {}) or {}
        d = pols.get(family.as_str())
        return PreferredOrderPolicy.from_dict(d) if d else PreferredOrderPolicy(family=family)

    def resolve_order(self, family: FamilyKey) -> dict:
        return resolve_preferred_order(self.variant_rows(family), self.policy(family))
