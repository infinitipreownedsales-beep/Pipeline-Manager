"""Governed MARKET-COMPARABILITY lineage for used TRANSACTION-PRICE evidence.

This is deliberately SEPARATE from every other relationship in Elite:
  * NOT demand lineage (identity/lineage.py — Speed-to-Sell demand sharing);
  * NOT planning normalization (newinv/dms_identity.normalize_code — 8461→8481 / 834x→8381 planning folds);
  * NOT package sharing; NOT inventory-family normalization.
None of those relationships are reused here. This module answers ONE question for the used-price market rail:

    May a CURRENT market configuration borrow OBSERVED USED-TRANSACTION evidence from an explicitly-approved
    PREDECESSOR configuration whose DMS model code changed across model years while its commercial identity
    (model + trim + drivetrain) stayed the same?

Each relationship is EXPLICIT and APPROVED, transcribed from authoritative product + store New-Car history — the
same transcription-governed pattern identity/seed_infiniti uses for reviewed charts. Direct (one-hop) only: NO
chained or inferred lineage, NO automatic reuse, real reviewed product facts only. Provenance is carried so the
market rail can state exactly which approved predecessor supplied the evidence.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketLineage:
    model: str                 # commercial model line (e.g. "QX60")
    trim: str                  # governed trim (e.g. "AUTOGRAPH")
    drivetrain: str            # governed drivetrain (e.g. "AWD")
    current_code4: str         # current 4-digit config code (raw code4 of the current order code)
    predecessor_code4: str     # approved predecessor 4-digit config code
    current_order_code: str    # authoritative current order code (provenance)
    predecessor_order_code: str  # authoritative predecessor order code (provenance)
    proof: str                 # authoritative evidence this relationship is transcribed from
    approved: bool = True      # explicit approval flag (an unapproved row is never used)


# EXPLICIT APPROVED market-comparability predecessors — BOUNDED, transcribed from authoritative evidence.
#
# QX60 AUTOGRAPH AWD: the configuration's DMS model code changed across model years —
#   2026 QX60 AUTOGRAPH AWD = 84816  (code4 8481)
#   2027 QX60 AUTOGRAPH AWD = 84617  (code4 8461)
# 84617 = QX60 AUTOGRAPH AWD is governed in identity/seed_infiniti (2027 reviewed Order Preference chart). The
# 2026 predecessor (84816 → 8481) is proven by authoritative store New-Car history and current product evidence.
# Therefore the 2027 config (8461) may borrow OBSERVED USED-TRANSACTION evidence from its 2026 predecessor (8481)
# — for the market/value rail only, never for demand/planning/inventory identity.
APPROVED_MARKET_LINEAGE = (
    MarketLineage(model="QX60", trim="AUTOGRAPH", drivetrain="AWD",
                  current_code4="8461", predecessor_code4="8481",
                  current_order_code="84617", predecessor_order_code="84816",
                  proof="2027 QX60 AUTOGRAPH AWD (84617/8461) succeeds 2026 QX60 AUTOGRAPH AWD (84816/8481) — "
                        "authoritative store New-Car history + reviewed product chart"),
)


def market_predecessors(model, code4):
    """Approved predecessor 4-digit config code(s) whose used-TRANSACTION evidence a current (model, code4) may
    borrow. DIRECT (one-hop) only — no chaining, no inference. Same model required; the trim/drivetrain identity
    is carried by the explicit approved relationship (both sides are the same governed family). Returns a tuple
    (possibly empty). Deduplicated, order-preserving."""
    m = (model or "").strip().upper()
    c = str(code4 or "").strip()
    if not m or not c:
        return ()
    out = []
    for r in APPROVED_MARKET_LINEAGE:
        if r.approved and (r.model or "").upper() == m and r.current_code4 == c and r.predecessor_code4 not in out:
            out.append(r.predecessor_code4)
    return tuple(out)
