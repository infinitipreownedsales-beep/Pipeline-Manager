"""Shared incremental supply-opportunity evaluator (item 6 / item 7).

PPO, Supplemental and Dealer Trade all ask the SAME question:

    Given everything already owned and committed, should the dealership add THIS specific supply opportunity?

So they share one evaluator instead of duplicating certified demand/supply logic per domain (item 17). The
evaluator is:

  * SEQUENTIAL against a DISPOSABLE planning state — accepting one offered vehicle can eliminate the need for
    another, so a 40-vehicle PPO is solved offer-by-offer, each FIRM folded into the running state before the
    next offer is judged. Offers are NEVER judged independently against the same opening inventory (item 7).
  * ACTIONABILITY-PRESERVING — a shortage that only appears beyond the actionable lead-time checkpoint does NOT
    justify acquiring today (item 6). The caller marks such an offer `actionable=False`.
  * EVIDENCE-HONEST — REVIEW is returned ONLY when evidence is genuinely insufficient (unknown demand or
    unknown orderability), never as a soft default.
  * FREE OF FAKE HEURISTICS — no source bonus, no "take it because INFINITI offered it", no diversification or
    staggering (item 14). A FIRM happens only because real, within-horizon certified demand is short.

The decision is made BEFORE the operator records anything (item 7 / item 13): manufacturer offer → Elite
evaluates → Elite recommends → operator confirms/overrides. The machine recommendation is preserved so an
operator override is always explicitly identifiable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

FIRM = "FIRM"
DENY = "DENY"
REVIEW = "REVIEW"


@dataclass
class Position:
    """The certified position for one combination need, at the decision moment. `demand` is the certified (and
    any governed additive) retail requirement WITHIN the actionable horizon; `owned` is current on-ground plus
    all authoritative incoming/committed already counted toward this combination. Shadow commitments accepted
    during the sequential solve are folded into `owned` on the disposable copy — never on the caller's data."""
    combination_key: str
    demand: float = 0.0
    owned: float = 0.0
    demand_known: bool = True
    label: str = ""

    @property
    def gap(self) -> float:
        return self.demand - self.owned


@dataclass
class Offer:
    """One offered supply opportunity to judge. `quantity` may be >1 (a single PPO line can offer several).
    `supply` is the NormalizedSupply (source + availability + physical vin/stock). `orderable` is current
    orderability/allocation evidence: True/False known, None = unknown (drives REVIEW). `actionable` is whether
    the lead-time checkpoint for this need has arrived (False → a purely-future shortage, do not acquire now)."""
    id: str
    combination_key: str
    quantity: int = 1
    supply: object = None
    orderable: Optional[bool] = True
    actionable: bool = True
    label: str = ""


@dataclass
class Verdict:
    offer_id: str
    recommendation: str                 # FIRM / DENY / REVIEW
    recommended_qty: int
    why: str
    before_gap: float
    after_gap: float
    combination_key: str
    source: str = ""
    availability: str = ""
    physical: bool = False
    vin: Optional[str] = None
    stock: Optional[str] = None
    label: str = ""

    def to_dict(self):
        return dict(offer_id=self.offer_id, recommendation=self.recommendation,
                    recommended_qty=self.recommended_qty, why=self.why, before_gap=self.before_gap,
                    after_gap=self.after_gap, combination_key=self.combination_key, source=self.source,
                    availability=self.availability, physical=self.physical, vin=self.vin, stock=self.stock,
                    label=self.label)


@dataclass
class PortfolioResult:
    verdicts: list = field(default_factory=list)
    firm: int = 0
    deny: int = 0
    review: int = 0
    offered: int = 0

    @property
    def summary(self) -> str:
        return f"{self.offered} OFFERED · FIRM {self.firm} · DENY {self.deny}" + (
            f" · REVIEW {self.review}" if self.review else "")

    @property
    def queue(self):
        """The executable queue — the FIRM verdicts, in evaluation order."""
        return [v for v in self.verdicts if v.recommendation == FIRM]


def _supply_bits(offer: Offer):
    s = offer.supply
    if s is None:
        return "", "", False, None, None
    return (getattr(s, "source", "") or "", getattr(s, "availability", "") or "",
            bool(getattr(s, "is_physical", False)), getattr(s, "vin", None), getattr(s, "stock", None))


def evaluate_offer(offer: Offer, pos: Position) -> Verdict:
    """Judge ONE offer against ONE position (pure; no state mutation). This is the single decision rule shared
    by every domain. Quantity-aware: FIRM recommends only up to the real shortage, never more."""
    src, avail, physical, vin, stock = _supply_bits(offer)
    before = pos.gap
    qty = max(1, int(offer.quantity or 1))

    def v(rec, rq, why, after):
        return Verdict(offer.id, rec, rq, why, round(before, 2), round(after, 2), pos.combination_key,
                       source=src, availability=avail, physical=physical, vin=vin, stock=stock,
                       label=offer.label or pos.label)

    # (1) genuinely insufficient evidence → REVIEW (never a soft default)
    if not pos.demand_known:
        return v(REVIEW, 0, "certified demand for this combination is unresolved — cannot decide; resolve demand "
                            "evidence first", before)
    if offer.orderable is None:
        return v(REVIEW, 0, "orderability / allocation evidence is unknown for this offer — cannot confirm it is "
                            "actually acquirable", before)
    if offer.orderable is False:
        return v(DENY, 0, "not currently orderable / allocation not available", before)

    # (2) a shortage that is only future (checkpoint not reached) does not justify acquiring today
    if before > 0 and not offer.actionable:
        return v(DENY, 0, f"a shortage exists only beyond the actionable lead-time checkpoint (gap {before:+.1f}); "
                          f"do not acquire today", before)

    # (3) no within-horizon shortage → adding this unit creates/extends excess
    if before <= 0:
        return v(DENY, 0, f"already covered (gap {before:+.1f}); adding this unit would create/extend excess", before)

    # (4) real, actionable shortage → FIRM up to the shortage, quantity-aware
    take = min(qty, int(math.ceil(before)))
    after = before - take
    return v(FIRM, take, f"covers a real within-horizon shortage (gap {before:+.1f}); firm {take} of {qty} offered"
                         + (f" — {avail.lower()}" if avail else ""), after)


def evaluate_portfolio(offers, positions, *, sort_offers=None) -> PortfolioResult:
    """Solve a whole offered set SEQUENTIALLY against a disposable planning state. `positions` is a dict or list
    of Position; a disposable copy of `owned` is mutated as FIRMs are accepted, so later offers recompute — a
    single opening inventory is never re-used across independent judgments (item 7).

    `sort_offers` optionally orders the offers before solving (e.g. soonest-timing first for a stable queue); it
    is a display/traversal order only and introduces no preference bonus. Returns a PortfolioResult carrying the
    per-offer machine recommendations (preserved for override comparison) and the FIRM/DENY/REVIEW summary."""
    pos_map = {}
    src = positions.values() if isinstance(positions, dict) else positions
    for p in src:
        pos_map[p.combination_key] = Position(p.combination_key, float(p.demand), float(p.owned),
                                              p.demand_known, p.label)   # disposable copy
    ordered = list(offers)
    if sort_offers is not None:
        ordered = sort_offers(ordered)

    result = PortfolioResult(offered=sum(max(1, int(o.quantity or 1)) for o in ordered))
    for offer in ordered:
        # A combination with NO certified position has UNKNOWN demand — never assume zero. An unknown-demand
        # position returns REVIEW (evidence-honest), never a false "already covered" DENY.
        pos = pos_map.get(offer.combination_key) or Position(offer.combination_key, 0.0, 0.0, False, offer.label)
        pos_map.setdefault(offer.combination_key, pos)
        verdict = evaluate_offer(offer, pos)
        if verdict.recommendation == FIRM and verdict.recommended_qty > 0:
            pos.owned += verdict.recommended_qty        # fold the FIRM into the disposable state (shadow commit)
            result.firm += verdict.recommended_qty
        elif verdict.recommendation == DENY:
            result.deny += max(1, int(offer.quantity or 1))
        elif verdict.recommendation == REVIEW:
            result.review += max(1, int(offer.quantity or 1))
        result.verdicts.append(verdict)
    return result


def apply_override(verdict: Verdict, *, operator_recommendation, operator_qty, actor, at, note="") -> dict:
    """Record the operator's actual execution against a preserved machine recommendation (item 7 / item 13).
    The original machine call is never overwritten; an override is explicitly flagged so it is auditable."""
    machine = verdict.recommendation
    machine_qty = verdict.recommended_qty
    op = (operator_recommendation or machine).upper()
    oq = int(operator_qty if operator_qty is not None else machine_qty)
    overridden = (op != machine) or (oq != machine_qty)
    return {"offer_id": verdict.offer_id, "machine_recommendation": machine, "machine_qty": machine_qty,
            "operator_recommendation": op, "operator_qty": oq, "override": overridden,
            "actor": actor, "at": at, "note": note, "combination_key": verdict.combination_key}
