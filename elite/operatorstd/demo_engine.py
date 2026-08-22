"""Executive-Demo three-pool decision engine (item 9).

The Demo program must optimise the dealership's FINANCIAL outcome — not executive convenience and not "give
someone a free car". Executive assignment happens AFTER Elite has chosen the economically correct Demo pool.

Elite evaluates three candidate pools and returns one of three physical-first calls:

  A. USE NOW          — the best actual on-ground VIN/stock to put into Demo service now.
  B. WAIT FOR INCOMING — a known inbound VIN/stock is superior; names the exact VIN/stock + timing.
  C. ORDER FOR DEMO    — neither current nor committed-incoming is best; a future order (combination-level,
                         because it is genuinely unbuilt).

Rules:
  * Physical-first (CORE LAW): pools A and B are resolved to actual VIN/stock via the shared physical selector;
    only pool C terminates at a combination.
  * Committed VINs (Service-Loaner active fleet + committed Demo) are excluded — count-once.
  * FAIL CLOSED ON ECONOMICS. Demo-specific economics are NOT imported from Service Loaner. When a governed Demo
    incremental-value model is not available (no `score`), Elite lists the physically-eligible candidates per
    pool but returns an UNRESOLVED call naming the EXACT business-policy gap — it never fabricates an economic
    pick and never forces current stock just because it is present.
  * No fake heuristics: no oldest-wins, no diversification, no executive-preference weighting (item 14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import physical as PHY
from . import supply as SUP

USE_NOW = "USE NOW"
WAIT_FOR_INCOMING = "WAIT FOR INCOMING"
ORDER_FOR_DEMO = "ORDER FOR DEMO"
UNRESOLVED = "UNRESOLVED — DEMO ECONOMICS NOT GOVERNED"

# The exact Demo economic inputs a governed model must provide before Elite can rank pools (item 9).
DEMO_ECONOMICS_INPUTS = ("New Retail opportunity cost", "certified combination coverage", "aging / DTS",
                         "actual Demo program economics", "expected Demo tenure", "incoming timing",
                         "expected exit basis / value", "Preowned front-end exit economics",
                         "replacement / replenishment / CPO consequences")


@dataclass
class DemoDecision:
    call: str                                   # USE_NOW / WAIT_FOR_INCOMING / ORDER_FOR_DEMO / UNRESOLVED
    unit: object = None                         # chosen NormalizedSupply (A/B) — carries VIN/stock/timing
    order_combination: Optional[str] = None     # combination label for pool C
    current_pool: list = field(default_factory=list)
    incoming_pool: list = field(default_factory=list)
    order_available: bool = False
    economics_gap: tuple = ()                    # non-empty ⇒ UNRESOLVED: the exact missing Demo policy inputs
    why: str = ""


def decide(need: PHY.Need, *, current, incoming, order_available=False, committed_vins=frozenset(),
           score=None) -> DemoDecision:
    """Evaluate the three pools for one Demo need.

    current  / incoming : lists of NormalizedSupply (physical on-ground / known-inbound units for the need).
    order_available     : whether a future order could satisfy the need (pool C).
    score               : governed Demo economics score(NormalizedSupply)->number (higher=better). REQUIRED to
                          rank; when absent Elite fails closed on the economic call and names the gap.

    Physical eligibility (VIN/stock known, not committed) is resolved by the shared selector; the economic pick
    among eligible units is the caller's governed economics, never a fabricated preference."""
    cur_res = PHY.choose(need, current, committed_vins=committed_vins, score=score)
    inc_res = PHY.choose(need, incoming, committed_vins=committed_vins, score=score)
    cur_units = cur_res.units if cur_res.level == PHY.VIN else []
    inc_units = inc_res.units if inc_res.level == PHY.VIN else []

    # fail closed on economics: we can enumerate the physical pools, but not rank them, without a Demo model
    if score is None and (cur_units or inc_units):
        return DemoDecision(call=UNRESOLVED, current_pool=cur_units, incoming_pool=inc_units,
                            order_available=order_available, economics_gap=DEMO_ECONOMICS_INPUTS,
                            why="physically-eligible Demo candidates found, but the Demo incremental-value model "
                                "is not governed — Elite will not fabricate an economic pick (SL economics are "
                                "not applicable to Demo). Provide the Demo economic policy to rank these.")

    best_cur = cur_units[0] if cur_units else None
    best_inc = inc_units[0] if inc_units else None

    def val(u):
        return float(score(u)) if (u is not None and score is not None) else None

    # with governed economics: choose the best pool on real value; timing never overrides economics
    if best_cur is not None or best_inc is not None:
        vc, vi = val(best_cur), val(best_inc)
        if best_inc is not None and (best_cur is None or (vi is not None and vc is not None and vi > vc)):
            return DemoDecision(call=WAIT_FOR_INCOMING, unit=best_inc, current_pool=cur_units,
                                incoming_pool=inc_units, order_available=order_available,
                                why="a known incoming unit is the economically better Demo than current stock")
        return DemoDecision(call=USE_NOW, unit=best_cur, current_pool=cur_units, incoming_pool=inc_units,
                            order_available=order_available,
                            why="the best on-ground unit is the economically correct Demo now")

    # no physical unit anywhere → order only when genuinely unbuilt (combination-level is correct here)
    if order_available:
        return DemoDecision(call=ORDER_FOR_DEMO, order_combination=need.label or need.combination_id,
                            order_available=True,
                            why="no current or committed-incoming physical unit is available/superior — order "
                                "for Demo (genuinely unbuilt)")
    return DemoDecision(call=UNRESOLVED, order_available=False, economics_gap=(),
                        why="no physical Demo candidate exists and no order path is available for this need")
