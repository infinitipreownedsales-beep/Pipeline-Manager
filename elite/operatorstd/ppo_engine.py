"""PPO decision engine bridge (item 7).

Turns the CERTIFIED per-combination inventory decision + the operator's entered offer set into an evaluated,
recommendation-first portfolio, using the shared incremental supply-opportunity evaluator. This is the piece
that flips PPO from a recording form into a decision engine: manufacturer offer → Elite evaluates → Elite
recommends → operator confirms/overrides.

Pure and stdlib-only: the UI reads the DB and hands this function plain dicts; nothing here touches the DB.

Mapping from a combination's certified decision to a Position:
  * acquire_units > 0                → an ACTIONABLE now-need. demand = acquire_units, actionable = True.
  * acquire_units == 0, future gap   → a future shortage NOT yet actionable. demand = gap, actionable = False
                                       (the evaluator denies "do not acquire today", preserving lead-time).
  * otherwise (covered / excess)     → demand = 0 (the evaluator denies "would create/extend excess").
The sequential solve then lets an accepted offer reduce the remaining actionable need for later offers of the
same combination, so a 40-line PPO is solved as a portfolio, never 40 independent judgments.
"""
from __future__ import annotations

from . import opportunity as OPP
from . import supply as SUP


def position_for(cert: dict) -> tuple:
    """(Position, actionable) for one combination's certified decision dict. `cert` carries the whole-vehicle
    decision fields already computed by the planning runner: acquire_units, arrived_excess, incoming_excess and
    whether a future (post-horizon) coverage gap exists."""
    key = cert.get("key") or cert.get("combination_id") or cert.get("label") or ""
    label = cert.get("label") or key
    acquire = int(cert.get("acquire_units", 0) or 0)
    future_gap = int(cert.get("future_gap", 0) or 0)
    if acquire > 0:
        return OPP.Position(key, demand=acquire, owned=0, demand_known=True, label=label), True
    if future_gap > 0 and int(cert.get("arrived_excess", 0) or 0) <= 0 \
            and int(cert.get("incoming_excess", 0) or 0) <= 0:
        return OPP.Position(key, demand=future_gap, owned=0, demand_known=True, label=label), False
    return OPP.Position(key, demand=0, owned=0, demand_known=True, label=label), False


def evaluate(offer_records, certified, *, key_for_offer=None) -> OPP.PortfolioResult:
    """Evaluate a whole PPO window.

    offer_records : list of stored offer dicts, each with at least {id, combo}; optional quantity, vin, stock,
                    ground_stock, production_month, orderable, external (True → orderability unknown → REVIEW).
    certified     : list of certified decision dicts (see position_for); the actionable/future context per
                    combination. Combinations with no certified row default to demand 0 (nothing short).
    key_for_offer : callable(offer)->combination key matching a certified `key`; defaults to offer['combo'].

    Returns the shared PortfolioResult (sequential, disposable state). Each verdict already carries the source,
    availability, physical/vin/stock and machine recommendation for a recommendation-first render + override."""
    key_for_offer = key_for_offer or (lambda o: o.get("key") or o.get("combo") or "")
    positions, actionable = {}, {}
    for cert in certified:
        pos, act = position_for(cert)
        positions[pos.combination_key] = pos
        actionable[pos.combination_key] = act

    offers = []
    for rec in offer_records:
        key = key_for_offer(rec)
        # supply provenance/timing for the offered unit (PPO units are usually physically known & pre-produced)
        if rec.get("ground_stock") or rec.get("production_month"):
            sup = SUP.normalize_supplemental(combination_id=key, vin=rec.get("vin"), stock=rec.get("stock"),
                                             ground_stock=bool(rec.get("ground_stock")),
                                             production_month=rec.get("production_month"))
        else:
            avail = SUP.NEAR_IMMEDIATE if (rec.get("vin") or rec.get("stock")) else SUP.PRODUCTION_MONTH
            sup = SUP.NormalizedSupply(source=SUP.PPO, availability=avail, combination_id=key,
                                       vin=rec.get("vin"), stock=rec.get("stock"))
        orderable = None if rec.get("external") else rec.get("orderable", True)
        offers.append(OPP.Offer(id=str(rec.get("id") or rec.get("combo")), combination_key=key,
                                quantity=int(rec.get("quantity", 1) or 1), supply=sup, orderable=orderable,
                                actionable=actionable.get(key, True), label=rec.get("combo", key)))
    # solve soonest-timing-first for a stable executable queue (display order only; no preference bonus)
    return OPP.evaluate_portfolio(offers, positions,
                                  sort_offers=lambda os: sorted(os, key=lambda o: getattr(o.supply, "timing_rank", 9)))
