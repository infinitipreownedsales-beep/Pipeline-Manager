"""Physical-unit selection — the CORE LAW (item 1).

  Combination-level intelligence decides WHAT type of inventory the dealership needs.
  VIN-level intelligence decides WHICH actual vehicle should fulfil that need whenever a physical vehicle exists.

Therefore a recommendation must NOT terminate at a combination when Elite already knows the physical vehicles
that satisfy it. Only a genuinely unbuilt / unassigned future order terminates at combination level.

This is ONE reusable selector for every domain (Demo, Service Loaner, PPO, Supplemental, Dealer Trade,
Retail) — not a separate implementation per domain (item 17). It is pure: it takes a need, a list of candidate
NormalizedSupply rows, and the authoritative committed-VIN exclusion set, and returns a resolution. It applies
NO fake heuristics — no oldest-wins, no diversification, no source bonus (item 14); ordering is soonest-timing
for display only, and the caller's economics make the final call among physical units.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .supply import sort_by_timing

# resolution levels
VIN = "vin"                  # a physical unit (VIN/stock) fulfils the need — the required terminal when one exists
COMBINATION = "combination"  # no physical unit exists/known — genuinely unbuilt/unassigned future order only


@dataclass
class Need:
    """What the dealership needs (combination-level). `combination_id` is the strong key; model_code/family are
    fallbacks so a need expressed either way still matches physical candidates."""
    combination_id: Optional[str] = None
    model_code: Optional[str] = None
    family: Optional[str] = None
    label: str = ""


@dataclass
class Resolution:
    level: str                                   # VIN or COMBINATION
    units: list = field(default_factory=list)    # NormalizedSupply rows (physical), soonest-timing first
    excluded_committed: list = field(default_factory=list)  # VINs dropped because already committed elsewhere
    reason: str = ""

    @property
    def is_physical(self) -> bool:
        return self.level == VIN and bool(self.units)

    @property
    def best(self):
        return self.units[0] if self.units else None


def _matches(need: Need, cand) -> bool:
    if need.combination_id and cand.combination_id:
        return need.combination_id == cand.combination_id
    if need.combination_id and not cand.combination_id:
        return False
    if need.model_code and cand.model_code:
        return str(need.model_code).strip() == str(cand.model_code).strip()
    # nothing to match on → cannot claim this candidate fulfils the need
    return False


def resolve(need: Need, candidates, *, committed_vins=frozenset()) -> Resolution:
    """Apply the CORE LAW. Returns a VIN-level Resolution listing every physical unit that fulfils `need`
    (excluding any VIN already committed to another purpose), or a COMBINATION-level Resolution ONLY when no
    physical unit exists/is known.

    `committed_vins` is the authoritative count-once exclusion set (elite.ordering.cross_domain.committed_vins:
    Service-Loaner active fleet + committed Demo). A committed VIN is never offered as free supply."""
    committed = {str(v).strip().upper() for v in (committed_vins or set())}
    matches = [c for c in candidates if _matches(need, c)]
    physical, excluded = [], []
    for c in matches:
        if c.is_physical:
            v = (c.vin or "").strip().upper()
            if v and v in committed:
                excluded.append(v)
                continue
            physical.append(c)
    if physical:
        units = sort_by_timing(physical)
        return Resolution(level=VIN, units=units, excluded_committed=sorted(set(excluded)),
                          reason=f"{len(units)} physical unit(s) known — recommend the actual VIN/stock, "
                                 f"not the combination")
    return Resolution(level=COMBINATION, units=[], excluded_committed=sorted(set(excluded)),
                      reason="no physical unit exists or is known — genuinely unbuilt/unassigned future order; "
                             "combination-level recommendation is correct here")


def choose(need: Need, candidates, *, committed_vins=frozenset(), score=None) -> Resolution:
    """Like resolve(), but when an economic `score(NormalizedSupply) -> number` (higher = better) is supplied,
    the physical units are ordered by real economics first, timing only as a tie-break. `score` must come from
    the caller's governed economics — this layer never invents one, so with no score the ordering is timing-only
    (display), never a fabricated preference."""
    res = resolve(need, candidates, committed_vins=committed_vins)
    if res.level == VIN and score is not None and res.units:
        res.units = sorted(res.units, key=lambda u: (-float(score(u)), u.timing_rank, u.arrival_month or "9999-99"))
        res.reason += " (ordered by governed economics)"
    return res
