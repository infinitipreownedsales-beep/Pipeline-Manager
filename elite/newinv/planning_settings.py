"""Target Days Supply — the single plainly-named, dealer-customizable inventory objective.

This is NOT a branded posture, composite score, or Lean/Balanced/Broad abstraction. It states, in plain
days, how much inventory the dealer wishes to carry. Changing it changes the amount of inventory desired;
it does NOT change how the engine decides velocity / breadth / depth / aging response / model-year
allocation / replenishment — those remain engine decisions driven by evidence. Herrin-Gear INFINITI
default = 60. A dealer may later set a different value; this is deliberately a simple explicit setting, not
a settings framework.
"""
from __future__ import annotations

DEFAULT_TARGET_DAYS_SUPPLY = 60
_META_KEY = "target_days_supply"


def resolve_target_days_supply(metadata_store=None, *, default=DEFAULT_TARGET_DAYS_SUPPLY):
    """The dealer's Target Days Supply: an explicit override in the metadata store if set, else the default."""
    if metadata_store is not None:
        try:
            v = metadata_store.get(_META_KEY)
            if v is not None:
                return int(str(v).strip())
        except Exception:   # noqa: BLE001 - a missing/erroring store falls back to the default
            pass
    return int(default)


def set_target_days_supply(metadata_store, value):
    """Set the dealer's Target Days Supply (explicit, plainly named). Idempotent per value."""
    metadata_store.put(_META_KEY, str(int(value)))
