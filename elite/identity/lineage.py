"""Governed demand-lineage & root-issue layer — the Translation/Identity closure governance.

Deterministic IDENTITY (this order code = QX80 LUXE 2WD; this colour code = Radiant White) auto-resolves in the
translation store. This module governs the relationships that CHANGE HOW COMMERCIAL DEMAND EVIDENCE IS SHARED —
those are never auto-activated; each is one root-level review with an explicit "why", provenance and Proof:

  * SAME_FAMILY_CROSS_GEN — the same commercial family across two generations (83317 vs 86317, both QX80 LUXE
    2WD). The identity is auto-resolved; sharing Speed-to-Sell history across generations is review-gated.
  * SUCCESSOR — a predecessor configuration became unavailable and a continuing configuration succeeds it
    (QX60 AUTOGRAPH FWD -> AWD). Histories stay SEPARATE; the predecessor may support the successor ONLY after
    approval; it is never encoded as FWD == AWD.
  * PACKAGE_SHARING — sharing demand across package variants (BASE / TPA / SEA / ...) of one family. Raw variant
    histories stay distinct; family history is supporting evidence only through the approved relationship.

Rejections/deferrals are remembered (never re-prompted) and reopen — referencing the prior decision — only when
materially new authoritative evidence appears. Everything is logged. Storage is governed JSON in the prefs
store (no schema change, schema stays v12). Real data only: no synthetic demand is created here — this layer
governs whether real observed histories may be shared, and records the Proof of what real data is involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..ids import new_id

KINDS = ("SAME_FAMILY_CROSS_GEN", "SUCCESSOR", "PACKAGE_SHARING")
STATUSES = ("proposed", "approved", "rejected", "deferred")

# review-queue categories surfaced to the operator
CAT_CONFLICT = "conflict"            # authoritative sources disagree — human judgment required
CAT_DEMAND_LINEAGE = "demand_lineage"  # identity known; approval would change how demand evidence is shared
CAT_UNKNOWN = "unknown"              # available authoritative evidence cannot determine the answer


@dataclass
class LineageProposal:
    id: str
    kind: str
    root_key: str                    # the stable root this decision is about (fix once -> propagate)
    from_ref: str                    # predecessor / older-gen / variant family+code
    to_ref: str                      # successor / newer-gen / base family
    why: str                         # human explanation: what changes if approved
    evidence: dict = field(default_factory=dict)   # real-data proof: observation counts, charts, codes
    status: str = "proposed"
    actor: str = ""
    at: str = ""
    reason: str = ""                 # operator's reason on reject/defer
    supersedes: str = ""             # prior decision id this reopen references
    version: int = 1

    def to_dict(self):
        return dict(id=self.id, kind=self.kind, root_key=self.root_key, from_ref=self.from_ref, to_ref=self.to_ref,
                    why=self.why, evidence=self.evidence, status=self.status, actor=self.actor, at=self.at,
                    reason=self.reason, supersedes=self.supersedes, version=self.version)

    @staticmethod
    def from_dict(d):
        return LineageProposal(d["id"], d["kind"], d["root_key"], d.get("from_ref", ""), d.get("to_ref", ""),
                               d.get("why", ""), d.get("evidence", {}) or {}, d.get("status", "proposed"),
                               d.get("actor", ""), d.get("at", ""), d.get("reason", ""), d.get("supersedes", ""),
                               int(d.get("version", 1)))


class LineageStore:
    """Store-scoped governed persistence for demand-lineage relationships (JSON in the prefs store)."""
    KEY = "xlat_lineage"
    K_AUDIT = "xlat_lineage_audit"

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self.scope = scope
        self._sk = f"scope::{scope}"

    def _rows(self):
        return self.prefs.get_pref(self._sk, self.KEY, default=[]) or []

    def _put(self, rows):
        self.prefs.set_pref(self._sk, self.KEY, rows)

    def _audit(self, actor, at, action, target, before=None, after=None):
        log = self.prefs.get_pref(self._sk, self.K_AUDIT, default=[]) or []
        log.append({"at": at, "actor": actor or "system", "action": action, "target": target,
                    "before": before, "after": after})
        self.prefs.set_pref(self._sk, self.K_AUDIT, log)

    def audit_log(self):
        return list(self.prefs.get_pref(self._sk, self.K_AUDIT, default=[]) or [])

    def all(self):
        return [LineageProposal.from_dict(d) for d in self._rows()]

    def by_root(self, root_key, kind=None):
        return [p for p in self.all() if p.root_key == root_key and (kind is None or p.kind == kind)]

    def latest_for(self, root_key, kind):
        """The most recent (highest version) decision for a (root_key, kind), or None."""
        cands = self.by_root(root_key, kind)
        return max(cands, key=lambda p: p.version) if cands else None

    def open_reviews(self):
        """Proposals still needing a human decision (proposed) — the active demand-lineage review queue.
        Rejected/deferred/approved are NOT here (rejection memory: never re-prompted)."""
        return [p for p in self.all() if p.status == "proposed"]

    def propose(self, *, kind, root_key, from_ref, to_ref, why, evidence, actor="system", at="",
                only_if_absent=True):
        """Create a review proposal. INSERT-IF-ABSENT on (root_key, kind): never re-creates a proposal that has
        ANY prior decision (proposed/approved/rejected/deferred) — that is the rejection/dedup memory. Use
        `reopen` to raise a new review when materially new evidence appears. Returns the proposal or None."""
        if kind not in KINDS:
            raise ValueError(f"unknown lineage kind {kind!r}")
        if only_if_absent and self.latest_for(root_key, kind) is not None:
            return None
        p = LineageProposal(new_id("lin"), kind, root_key, from_ref, to_ref, why, dict(evidence or {}),
                            "proposed", actor, at)
        rows = self._rows() + [p.to_dict()]
        self._put(rows)
        self._audit(actor, at, "lineage.propose", f"{kind}:{root_key}", after={"from": from_ref, "to": to_ref})
        return p

    def _set_status(self, proposal_id, status, *, actor, at, reason=""):
        rows = self._rows()
        for d in rows:
            if d["id"] == proposal_id:
                before = d.get("status")
                d["status"], d["actor"], d["at"] = status, actor, at
                if reason:
                    d["reason"] = reason
                self._put(rows)
                self._audit(actor, at, f"lineage.{status}", f"{d['kind']}:{d['root_key']}",
                            before={"status": before}, after={"status": status, "reason": reason})
                return LineageProposal.from_dict(d)
        return None

    def approve(self, proposal_id, *, actor, at):
        return self._set_status(proposal_id, "approved", actor=actor, at=at)

    def reject(self, proposal_id, *, actor, at, reason=""):
        return self._set_status(proposal_id, "rejected", actor=actor, at=at, reason=reason)

    def defer(self, proposal_id, *, actor, at, reason=""):
        return self._set_status(proposal_id, "deferred", actor=actor, at=at, reason=reason)

    def reopen(self, root_key, kind, *, new_evidence, why, from_ref="", to_ref="", actor="system", at=""):
        """Raise a NEW review event for a (root_key, kind) whose prior decision was rejected/deferred, ONLY when
        materially new authoritative evidence appears. The new proposal references the prior decision
        (`supersedes`); the prior record is preserved (nothing hidden). Returns the new proposal, or None if
        there is no prior decision or the evidence is not materially new (identical to the prior evidence)."""
        prior = self.latest_for(root_key, kind)
        if prior is None or prior.status not in ("rejected", "deferred"):
            return None
        if dict(new_evidence or {}) == dict(prior.evidence or {}):
            return None                                   # not materially new -> do not re-prompt
        p = LineageProposal(new_id("lin"), kind, root_key, from_ref or prior.from_ref, to_ref or prior.to_ref,
                            why, dict(new_evidence or {}), "proposed", actor, at, supersedes=prior.id,
                            version=prior.version + 1)
        rows = self._rows() + [p.to_dict()]
        self._put(rows)
        self._audit(actor, at, "lineage.reopen", f"{kind}:{root_key}",
                    before={"prior": prior.id, "prior_status": prior.status}, after={"new": p.id})
        return p


# --- candidate detection (pure; over the translation store's APPROVED variant identity) --------------------
def detect_cross_generation_candidates(translation_store):
    """Families whose APPROVED identity spans more than one generation segment — each is a candidate
    SAME_FAMILY_CROSS_GEN demand-sharing review (identity already auto-resolved; sharing history is the
    review). Returns dicts carrying the real Proof (the exact codes + generations)."""
    fams = {}
    for r in translation_store.variant_rows(approved_only=True):
        fams.setdefault(r.family.as_str(), {}).setdefault(r.generation_id, set()).add(r.raw_code)
    out = []
    for fam, gens in fams.items():
        if len(gens) > 1:
            ordered = sorted(gens.items())            # by generation id ascending (older first)
            older = ", ".join(sorted(ordered[0][1]))
            newer = ", ".join(sorted(ordered[-1][1]))
            out.append({"root_key": f"cross_gen:{fam}", "family": fam,
                        "generations": {g: sorted(cs) for g, cs in ordered},
                        "older_codes": older, "newer_codes": newer})
    return out


def detect_package_candidates(translation_store):
    """Families with more than one package variant in their APPROVED identity — each is a candidate
    PACKAGE_SHARING demand-sharing review. Raw variant histories stay distinct until approved."""
    fams = {}
    for r in translation_store.variant_rows(approved_only=True):
        fams.setdefault(r.family.as_str(), set()).add(r.package)
    return [{"root_key": f"pkg:{fam}", "family": fam, "packages": sorted(pkgs)}
            for fam, pkgs in fams.items() if len(pkgs) > 1]


def ensure_lineage_proposals(translation_store, lineage_store, *, actor="system", at=""):
    """Surface the review-gated demand-sharing relationships implied by the (already auto-resolved) identity, as
    governed PROPOSALS — never auto-approved. Insert-if-absent, so a re-run adds nothing new and never
    re-prompts a rejected/deferred relationship. Returns the count of newly-proposed reviews."""
    n = 0
    for c in detect_cross_generation_candidates(translation_store):
        why = (f"{c['family'].split('·', 1)[-1].replace('·', ' ')} appears in two generations "
               f"(codes {c['older_codes']} and {c['newer_codes']}). The identity is the same and already "
               f"resolved; APPROVING lets the older generation's Speed-to-Sell history support the newer "
               f"generation. It does not merge them — each generation's real history stays separate. Requires "
               f"your review because it changes how demand evidence is shared.")
        if lineage_store.propose(kind="SAME_FAMILY_CROSS_GEN", root_key=c["root_key"], from_ref=c["older_codes"],
                                 to_ref=c["newer_codes"], why=why,
                                 evidence={"family": c["family"], "generations": c["generations"],
                                           "source": "reviewed Order Preference chart"}, actor=actor, at=at):
            n += 1
    for c in detect_package_candidates(translation_store):
        why = (f"{c['family'].split('·', 1)[-1].replace('·', ' ')} has package variants {', '.join(c['packages'])}. "
               f"Each variant's real Speed-to-Sell history stays distinct; APPROVING lets the family history be "
               f"used as supporting evidence across packages through the governed relationship. Requires your "
               f"review because it changes how demand evidence is shared.")
        if lineage_store.propose(kind="PACKAGE_SHARING", root_key=c["root_key"], from_ref=", ".join(c["packages"]),
                                 to_ref="BASE", why=why,
                                 evidence={"family": c["family"], "packages": c["packages"],
                                           "source": "reviewed Order Preference chart"}, actor=actor, at=at):
            n += 1
    return n


def root_issues(translation_store, lineage_store, *, description_conflicts=()):
    """The operator-facing ROOT review queue: one item per underlying identity problem, regardless of how many
    observations/VINs it affects (cross-source deduped). Auto-resolved deterministic facts are NOT here — they
    live in change history. Returns a dict:
        {"count": N, "issues": [ ... ]} where each issue carries category / why / affected / sources / examples.
    Categories: conflict (sources disagree), demand_lineage (approval changes sharing), unknown (evidence can't
    determine). Real-data only — nothing here fabricates a mapping or a demand number."""
    issues = []

    # (1) authoritative-source conflicts (e.g. DMS Description vs canonical family) — one per root, caller-supplied
    for c in description_conflicts or ():
        issues.append({"category": CAT_CONFLICT, "root_key": c.get("root_key", ""),
                       "title": c.get("title", ""), "why": c.get("why", ""),
                       "affected": int(c.get("affected", 0) or 0), "sources": list(c.get("sources", [])),
                       "examples": list(c.get("examples", []))})

    # (2) demand-lineage — open (proposed) governed relationships
    for p in lineage_store.open_reviews():
        issues.append({"category": CAT_DEMAND_LINEAGE, "root_key": p.root_key, "kind": p.kind,
                       "title": f"{p.kind.replace('_', ' ').title()} — {p.from_ref} → {p.to_ref}",
                       "why": p.why, "affected": 0, "sources": [p.evidence.get("source", "")],
                       "examples": [], "proposal_id": p.id})

    # (3) genuinely-unknown — unresolved observations grouped by (type, raw), cross-source deduped. A concept is
    #     resolved once ANY approved mapping exists for (type, raw) regardless of source (matching the display
    #     resolver's any-source fallback) — so one governed decision clears the root across every source (item 11).
    approved_concepts = {(m.semantic_type, m.raw_value)
                         for m in translation_store.semantic_mappings() if m.active and m.approval == "approved"}
    grouped = {}
    for o in translation_store.unresolved_translations():
        key = (o["semantic_type"], o["raw_value"])
        if key in approved_concepts:
            continue
        g = grouped.setdefault(key, {"sources": set(), "count": 0})
        g["sources"].add(o["source_system"])
        g["count"] += 1
    for (stype, raw), g in sorted(grouped.items()):
        issues.append({"category": CAT_UNKNOWN, "root_key": f"unknown:{stype}:{raw}",
                       "title": f"{stype} '{raw}' — no authoritative mapping",
                       "why": (f"'{raw}' is observed but no reviewed chart / governed mapping determines its "
                               f"human meaning. Name it once here and every observation across sources resolves. "
                               f"Elite will not guess."),
                       "affected": g["count"], "sources": sorted(g["sources"]),
                       "examples": [raw], "semantic_type": stype, "raw_value": raw})
    return {"count": len(issues), "issues": issues}
