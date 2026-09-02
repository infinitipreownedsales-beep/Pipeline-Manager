"""PPO worked-portfolio orchestration — make Kyle's ACTUAL FIRM / PARTIAL / DENY drive the remaining portfolio,
and preserve the machine recommendation at the moment he acted.

This is glue over the EXISTING rails, not a second commitment ledger:
  * the machine recommendation math is the shared incremental evaluator (`operatorstd.opportunity` via
    `operatorstd.ppo_engine`) — unchanged;
  * a confirmed FIRM/PARTIAL becomes governed Committed Supply through the EXISTING `newinv` SupplyCommitment
    rail (see `commitment_units_for_offer` + the operator route), counted once by `supply.qualifying_supply`
    exactly like a CPO commitment;
  * reconciliation against authoritative Production Orders reuses the existing count-once semantics.

What this module adds is purely the disposable-state bookkeeping the live window needs:
  * Kyle's actual worked FIRM/PARTIAL quantities are consumed from certified Need BEFORE the remaining UNWORKED
    offers are evaluated, so firming one offer immediately changes the recommendations for the rest, and an
    override (DENY a recommended FIRM, or FIRM a recommended DENY) frees or consumes Need for later offers;
  * already-worked offers stay LOCKED to Kyle's recorded decision — a later recomputation never silently
    reassigns his confirmed unit;
  * the machine recommendation at the moment Kyle acted is preserved, so a later recomputation cannot rewrite
    history and make an override look like it matched Elite after the fact.
"""
from __future__ import annotations

from ..operatorstd import ppo_engine as ENGINE
from ..operatorstd import opportunity as OPP

WORKED_ACTIONS = ("FIRM", "PARTIAL", "DENY")


def _worked_qty(offer):
    """Committed shadow-supply units from Kyle's ACTUAL recorded decision (0 for DENY / unworked)."""
    act = (offer.get("operator_action") or "").upper()
    if act in ("FIRM", "PARTIAL"):
        try:
            return max(0, int(offer.get("operator_qty") or 0))
        except (TypeError, ValueError):
            return 0
    return 0


def _consumed_by_combination(offers, key_for_offer):
    """Sum Kyle's actual firmed quantities per certified combination key — the Need already consumed by worked
    decisions, folded into the disposable state before the remaining offers are judged."""
    consumed = {}
    for o in offers:
        if (o.get("operator_action") or "").upper() in ("FIRM", "PARTIAL"):
            key = key_for_offer(o)
            consumed[key] = consumed.get(key, 0) + _worked_qty(o)
    return consumed


def _disposable_positions(certified, consumed):
    """The certified positions with Kyle's actual worked commitments already consumed (owned += firmed). Uses the
    shared engine's certified->Position mapping so the math is identical to a normal evaluation."""
    positions, actionable = {}, {}
    for cert in certified:
        pos, act = ENGINE.position_for(cert)
        pos.owned += float(consumed.get(pos.combination_key, 0))   # actual worked FIRMs already committed
        positions[pos.combination_key] = pos
        actionable[pos.combination_key] = act
    return positions, actionable


def machine_recommendation_at(offers, certified, offer_id, *, key_for_offer):
    """The machine recommendation DISPLAYED for ONE offer at the moment Kyle acts on it — i.e. the portfolio
    verdict for that offer treated as still-unworked, against the disposable state of every OTHER already-worked
    offer (Kyle's actual decisions) plus the sequential solve over the other unworked offers. This is exactly
    what Kyle saw, and is PERSISTED so a later recomputation can never rewrite whether he followed or overrode
    Elite. Returns {recommendation, recommended_qty} or None if the offer is not found."""
    probe = [dict(o) for o in offers]
    found = False
    for o in probe:
        if str(o.get("id")) == str(offer_id):
            o.pop("operator_action", None)
            o.pop("operator_qty", None)
            found = True
    if not found:
        return None
    v = evaluate_window(probe, certified, key_for_offer=key_for_offer)["verdicts"].get(str(offer_id))
    if v is None:
        return None
    return {"recommendation": v.recommendation, "recommended_qty": v.recommended_qty}


def evaluate_window(offers, certified, *, key_for_offer):
    """Evaluate a PPO window with Kyle's ACTUAL worked decisions governing the remaining portfolio state.

    Worked FIRM/PARTIAL are consumed from Need first; UNWORKED offers are then evaluated against that disposable
    state (so firming one immediately changes the rest). Worked offers are returned LOCKED to their recorded
    decision, carrying the PRESERVED machine recommendation (from persisted audit) so an override stays visible.

    Returns {verdicts: {offer_id: Verdict}, worked: {offer_id: {...}}, counts: {...}}."""
    consumed = _consumed_by_combination(offers, key_for_offer)
    positions, _actionable = _disposable_positions(certified, consumed)
    worked = [o for o in offers if (o.get("operator_action") or "").upper() in WORKED_ACTIONS]
    unworked = [o for o in offers if (o.get("operator_action") or "").upper() not in WORKED_ACTIONS]

    # UNWORKED offers see the disposable state AFTER Kyle's actual worked commitments (Need already consumed).
    # The math is the shared evaluator; only the opening `owned` differs (seeded from worked FIRM/PARTIAL).
    verdicts = {}
    disposable = OPP.evaluate_portfolio(
        [OPP.Offer(id=str(o.get("id") or o.get("combo")), combination_key=key_for_offer(o),
                   quantity=int(o.get("quantity", 1) or 1),
                   orderable=(None if o.get("external") else o.get("orderable", True)),
                   actionable=_actionable.get(key_for_offer(o), True), label=o.get("combo", key_for_offer(o)),
                   supply=_supply_for(o, key_for_offer(o)))
         for o in unworked],
        positions,
        sort_offers=lambda os: sorted(os, key=lambda x: getattr(x.supply, "timing_rank", 9)))
    for v in disposable.verdicts:
        verdicts[v.offer_id] = v

    worked_summary = {}
    firmed = denied = review = 0
    for o in worked:
        oid = str(o.get("id"))
        act = (o.get("operator_action") or "").upper()
        aqty = _worked_qty(o)
        rec = {"recommendation": o.get("recommended_action") or "", "recommended_qty": o.get("recommended_qty", "")}
        override = bool(o.get("override")) if o.get("override") is not None else (
            bool(rec["recommendation"]) and (rec["recommendation"] != act or int(rec["recommended_qty"] or 0) != aqty))
        worked_summary[oid] = {"action": act, "qty": aqty, "recommendation": rec["recommendation"],
                               "recommended_qty": rec["recommended_qty"], "override": override,
                               "at": o.get("recorded_at", "")}
        if act in ("FIRM", "PARTIAL"):
            firmed += aqty
        else:
            denied += max(1, int(o.get("quantity", 1) or 1))

    for v in verdicts.values():
        if v.recommendation == OPP.REVIEW:
            review += 1
    counts = {"offered": sum(max(1, int(o.get("quantity", 1) or 1)) for o in offers),
              "firmed": firmed, "denied": denied, "review": review,
              "unworked": sum(max(1, int(o.get("quantity", 1) or 1)) for o in unworked)}
    summary = (f"Offered {counts['offered']} · Firmed {counts['firmed']} · Denied {counts['denied']}"
               + (f" · Review {counts['review']}" if counts['review'] else "")
               + (f" · Unworked {counts['unworked']}" if counts['unworked'] else ""))
    return {"verdicts": verdicts, "worked": worked_summary, "counts": counts, "summary": summary}


def _supply_for(offer, key):
    from ..operatorstd import supply as SUP
    avail = SUP.NEAR_IMMEDIATE if (offer.get("vin") or offer.get("stock")) else SUP.PRODUCTION_MONTH
    return SUP.NormalizedSupply(source=SUP.PPO, availability=avail, combination_id=key,
                                vin=offer.get("vin"), stock=offer.get("stock"))


def commitment_units_for_offer(offer, combination_key, qty):
    """The governed Committed-Supply unit identities for `qty` firmed units of one offer — reusing the EXISTING
    SupplyCommitment rail. Honest identity level: a VIN names the physical unit (count-once against a later
    Production Order that carries the same VIN); otherwise the commitment is combination-level and each unit
    gets a stable per-offer id (never a fabricated VIN/order number). Deterministic + idempotent per offer."""
    units = []
    vin = (offer.get("vin") or "").strip().upper()
    for i in range(max(0, int(qty or 0))):
        if vin and i == 0:
            units.append({"unit_or_order_id": vin, "unit_identity_kind": "vehicle_unit"})
        else:
            suffix = f":{i}" if (qty > 1 or not vin) else ""
            units.append({"unit_or_order_id": f"ppo:{offer.get('id')}{suffix}",
                          "unit_identity_kind": "combination"})
    return units
