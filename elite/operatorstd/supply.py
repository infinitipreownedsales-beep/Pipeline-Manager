"""Normalized supply representation — SOURCE and AVAILABILITY are SEPARATE dimensions (item 4 / item 5).

Provenance (where a unit comes from) must never smuggle in a timing assumption, and timing must never rewrite
provenance. A Dealer Trade stays a Dealer Trade even though it arrives near-immediately; Supplemental stays
Supplemental whether it is Ground Stock or a Production-Month unit.

SOURCE        — Current Inventory · Production Order · CPO · PPO · Supplemental · Dealer Trade · other governed.
AVAILABILITY  — On Ground · Near Immediate · Known ETA · Production Month · Future/unresolved.

Timing rules baked in (governed, item 5):
  * Supplemental GROUND STOCK  → NEAR_IMMEDIATE (physically at INFINITI's processing centre, ready to ship).
  * Supplemental PRODUCTION MONTH → PRODUCTION_MONTH, resolved through the SAME governed production-month →
    expected-availability logic the planning bridge already uses (elite.newinv.supply_bridge month parsing).
  * Dealer Trade → NEAR_IMMEDIATE (a completed dealer trade normally arrives within roughly the next week).
  * DMS source stage maps: DLR-INV → ON_GROUND, NNA-INV → NEAR_IMMEDIATE (stateside, awaiting ship — the same
    "ground stock" physical situation), SIT → KNOWN_ETA (on the water), ONS → PRODUCTION_MONTH/FUTURE.

There are NO artificial preference bonuses here: Supplemental and Dealer Trade get their edge ONLY from real
timing/economics, never from a source bonus (item 5 / item 14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---- SOURCE (provenance) ----
CURRENT_INVENTORY = "Current Inventory"
PRODUCTION_ORDER = "Production Order"
CPO = "CPO"
PPO = "PPO"
SUPPLEMENTAL = "Supplemental"
DEALER_TRADE = "Dealer Trade"
OTHER = "Other"
SOURCES = (CURRENT_INVENTORY, PRODUCTION_ORDER, CPO, PPO, SUPPLEMENTAL, DEALER_TRADE, OTHER)

# ---- AVAILABILITY (timing) ----  ordered soonest → latest for tie-break ONLY (never a preference bonus)
ON_GROUND = "On Ground"
NEAR_IMMEDIATE = "Near Immediate"
KNOWN_ETA = "Known ETA"
PRODUCTION_MONTH = "Production Month"
FUTURE = "Future"
AVAILABILITY = (ON_GROUND, NEAR_IMMEDIATE, KNOWN_ETA, PRODUCTION_MONTH, FUTURE)
_AVAIL_RANK = {a: i for i, a in enumerate(AVAILABILITY)}

# DMS source-stage → availability (mirrors elite.newinv.dms_cohort stages; provenance stays Current Inventory)
_DMS_STAGE_AVAIL = {"DLR-INV": ON_GROUND, "NNA-INV": NEAR_IMMEDIATE, "SIT": KNOWN_ETA, "ONS": PRODUCTION_MONTH}


def _month_str(v):
    """'YYYY-MM' from a production_month ('YYYY-MM'/'YYYYMM') or an ETA date; None if unparseable. Mirrors
    elite.newinv.supply_bridge._month_str so timing math is identical across the two layers."""
    d = "".join(ch for ch in str(v or "").strip() if ch.isdigit())
    if len(d) >= 6:
        y, m = d[:4], d[4:6]
        if 1 <= int(m) <= 12:
            return f"{y}-{m}"
    return None


@dataclass
class NormalizedSupply:
    """One supply row with provenance and timing kept orthogonal. `vin`/`stock` are present whenever the
    physical unit is known; a genuinely unbuilt/unassigned future order carries neither (combination-level)."""
    source: str
    availability: str
    combination_id: Optional[str] = None
    vin: Optional[str] = None
    stock: Optional[str] = None
    model_code: Optional[str] = None
    arrival_month: Optional[str] = None            # 'YYYY-MM' when timing is month-bucketed
    expected_available_date: Optional[str] = None  # explicit date when known (ETA)
    timing_confidence: str = "medium"
    provenance_detail: str = ""                    # e.g. "GROUND STOCK" / "PRODUCTION MONTH 2026-11"
    age_days: Optional[int] = None
    ref: Optional[str] = None                      # opaque back-reference to the underlying row/id
    extra: dict = field(default_factory=dict)

    @property
    def is_physical(self) -> bool:
        """True when Elite knows the actual vehicle (VIN, or a stock number). Combination-only rows are False."""
        return bool((self.vin or "").strip() or (self.stock or "").strip())

    @property
    def timing_rank(self) -> int:
        return _AVAIL_RANK.get(self.availability, len(AVAILABILITY))


def classify_availability(source, *, dms_stage=None, ground_stock=None, production_month=None,
                          eta=None, on_ground=None) -> str:
    """Pure timing classification. `source` is one of SOURCES; the keyword evidence is whatever the caller has.
    Never returns a preference — only the honest availability bucket. Precedence: explicit on-ground →
    Dealer-Trade near-immediate → Supplemental ground-stock near-immediate → DMS stage → month → ETA → future."""
    if on_ground:
        return ON_GROUND
    if dms_stage:
        mapped = _DMS_STAGE_AVAIL.get(str(dms_stage).strip().upper())
        if mapped:
            # a stage-mapped month/eta may still refine within its bucket, but the stage decides the bucket
            return mapped
    if source == DEALER_TRADE:
        return NEAR_IMMEDIATE                       # completed trade ≈ within the week
    if source == SUPPLEMENTAL:
        if ground_stock:
            return NEAR_IMMEDIATE                    # stateside, ready to ship
        if _month_str(production_month):
            return PRODUCTION_MONTH
        return FUTURE
    if _month_str(production_month):
        return PRODUCTION_MONTH
    if eta:
        return KNOWN_ETA
    return FUTURE


def normalize_supplemental(*, combination_id=None, vin=None, stock=None, model_code=None, ground_stock=False,
                           production_month=None, ref=None) -> NormalizedSupply:
    """A Supplemental offer normalized. Provenance stays Supplemental; GROUND STOCK vs PRODUCTION MONTH X only
    changes AVAILABILITY (item 8). No source bonus is applied anywhere."""
    avail = classify_availability(SUPPLEMENTAL, ground_stock=ground_stock, production_month=production_month)
    if ground_stock:
        detail = "GROUND STOCK"
    elif _month_str(production_month):
        detail = f"PRODUCTION MONTH {_month_str(production_month)}"
    else:
        detail = "PRODUCTION MONTH (unspecified)"
    return NormalizedSupply(source=SUPPLEMENTAL, availability=avail, combination_id=combination_id, vin=vin,
                            stock=stock, model_code=model_code, arrival_month=_month_str(production_month),
                            provenance_detail=detail, ref=ref)


def normalize_dealer_trade(*, combination_id=None, vin=None, stock=None, model_code=None, counterparty="",
                           ref=None) -> NormalizedSupply:
    """A Dealer-Trade opportunity normalized. Provenance stays Dealer Trade; availability is Near Immediate
    because a completed trade normally arrives within roughly a week (item 5). No source bonus."""
    return NormalizedSupply(source=DEALER_TRADE, availability=NEAR_IMMEDIATE, combination_id=combination_id,
                            vin=vin, stock=stock, model_code=model_code,
                            provenance_detail=(f"DEALER TRADE · {counterparty}".strip(" ·")), ref=ref)


def normalize_dms_row(row, *, combination_id=None) -> NormalizedSupply:
    """Normalize a DMS inventory row (location stage decides availability; provenance is Current Inventory).
    Ground/near-immediate/eta/production-month all come from the SAME stage rules the planning bridge uses."""
    from ..newinv.dms_cohort import dms_source_stage
    stage = dms_source_stage(row)
    avail = classify_availability(CURRENT_INVENTORY, dms_stage=stage,
                                  production_month=row.get("production_month"), eta=row.get("eta"))
    age = None
    try:
        age = int(str(row.get("dis")).strip()) if str(row.get("dis") or "").strip() else None
    except (TypeError, ValueError):
        age = None
    return NormalizedSupply(source=CURRENT_INVENTORY, availability=avail, combination_id=combination_id,
                            vin=(row.get("vin") or None), stock=(row.get("stock_number") or None),
                            model_code=(row.get("model_code") or None),
                            arrival_month=_month_str(row.get("production_month")) or _month_str(row.get("eta")),
                            expected_available_date=(row.get("eta") or None), age_days=age,
                            provenance_detail=stage, ref=(row.get("stock_number") or row.get("vin") or None))


def sort_by_timing(rows):
    """Soonest-available first, stable. This is a display/tie-break ordering ONLY — it is NOT a preference
    weighting and never overrides economics; the evaluator makes the actual decision on real numbers."""
    return sorted(rows, key=lambda r: (r.timing_rank, r.arrival_month or "9999-99"))
