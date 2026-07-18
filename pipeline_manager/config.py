"""Settings and dealer control-state.

The two dealer *exports* (inventory + sales) are the data.  Everything a human
turns to steer the engine — the order month, the mode, allocations, the
suppress / demote / override lists, the demo roster, aged-unit brakes — is
control-state, kept here and (optionally) overridden by a `config.json`.

Defaults reproduce the state the source workbook shipped in, so running the app
against the sample exports reproduces the workbook's numbers.  None of this is
hidden or cached: it is read fresh, in full, on every run.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ROSTER_PATH = os.path.join(_PKG_DIR, "roster_default.json")

MONTH_NAMES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
               "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

VALID_MODES = ("CPO", "PPO", "MID-MONTH")


def month_num(name) -> int:
    """Accept a 1..12 int or a 3-letter month name -> 1..12."""
    if isinstance(name, int):
        return name
    s = str(name).strip().upper()[:3]
    return MONTH_NAMES.index(s) + 1 if s in MONTH_NAMES else 1


def load_roster() -> list[dict]:
    with open(ROSTER_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class Settings:
    # --- the two knobs a user changes most (brief §17) --------------------- #
    order_month: int = 9                 # month you PLACE the order (1..12)
    mode: str = "CPO"                    # CPO | PPO | MID-MONTH

    # --- allocation per model (order-priority BUILD/alt cutover) ----------- #
    allocations: dict = field(default_factory=lambda: {"QX80": 50, "QX60": 100, "QX65": 100})

    # --- production -> arrival lead per model, in months (brief §9/§12) ----- #
    # "auto" derives a continuous, trend-weighted lead from each unit's
    # production month and arrival date; a number pins it manually.
    cpo_windows: dict = field(default_factory=lambda: {"QX80": "auto", "QX60": "auto", "QX65": "auto"})
    min_cpo_window: float = 1.0          # a factory order can't arrive the month you place it
    order_lead_pad: float = 0.0          # extra order->production months to add to the auto lead
    lead_halflife: float = 6.0           # months; recency half-life for trend-weighting

    # --- control lists ----------------------------------------------------- #
    # Suppress forces NEED=0 immediately (discontinued combos). 8461 is always
    # suppressed in code; add {code,ext,int} entries here for more.
    suppress: list = field(default_factory=list)
    # Demote keeps a slow combo visible but ranks it last and zeroes NEED
    # unless it proves through (R90 >= prove_bar). Blank field = wildcard.
    demote: list = field(default_factory=lambda: [{"model": "", "ext": "", "int": "N"}])
    # Manual overrides force units onto a combo (loaner adds, etc.).
    overrides: list = field(default_factory=lambda: [{"key": "QX60|8411|QBE|K", "qty": 8}])
    # Demo units (out of sellable inventory). Prefix-matched against Stock#.
    demo_stocks: list = field(default_factory=lambda: ["N15106", "N15118", "N15126", "N15145"])
    # Optional demo-start dates (YYYY-MM-DD) for exact age; absent -> fall back
    # to days-in-stock. Keyed by the demo Stock# prefix.
    demo_starts: dict = field(default_factory=lambda: {
        "N15106": "2026-05-08", "N15118": "2026-04-29",
        "N15126": "2026-05-07", "N15145": "2026-06-07",
    })
    # Aged-unit brakes that persist after a unit leaves the lot (brief §11).
    aged_memory: list = field(default_factory=list)
    # Outbound dealer trades — a trade out is a sale out the other door. Each
    # entry {date, code (or model+code), ext, int, days} grades that config's
    # speed to enter/exit inventory exactly like a showroom sale (a 15-day trade
    # reads fast; a 115-day trade reads slow). Empty by default; add via the app.
    trades: list = field(default_factory=list)

    # --- tunable thresholds (brief §7/§14/§15/§17) ------------------------- #
    prove_bar: int = 2                   # R90 needed for a demoted combo to surface
    swap_threshold: int = 90             # demo age (days) before flagging a swap
    # Anticipate demos re-entering inventory: a returning demo is added to the
    # arrival projection at its expected return month and held as slow-moving
    # (used, higher-mileage) stock, so ordering doesn't replace a unit that's
    # coming back and doesn't assume it resells at full pace.
    anticipate_demo_returns: bool = True
    # --- executive demo board (which combos to put execs into) ------------- #
    demo_pick_max_dts: int = 45          # a demo gains miles: it must still turn fast
    demo_pick_min_total: int = 2         # at least two sales ever — never a one-off
    demo_pick_min_r180: int = 2          # two sales in 180d = repeat demand, not a whim
    demo_picks_per_model: int = 3        # top combos to surface per model
    demo_vins_per_combo: int = 2         # candidate VINs to offer per combo
    rate_cap: float = 5.0                # no config sells more than ~5/month
    paperweight_dts: int = 90            # DTS veto: >90 days can never earn a base
    wholesale_min_age: int = 60          # a unit must be older than MAX(this, DTS)
    stall_days: int = 120                # units this old are "stalled" in projection
    aged_days: int = 60                  # on-lot units older than this are "aged"

    roster: list = field(default_factory=load_roster)

    @classmethod
    def load(cls, path: str | None) -> "Settings":
        s = cls()
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for k, v in data.items():
                if k == "order_month":
                    s.order_month = month_num(v)
                elif hasattr(s, k):
                    setattr(s, k, v)
        s.order_month = month_num(s.order_month)
        s.mode = str(s.mode).strip().upper()
        if s.mode not in VALID_MODES:
            s.mode = "CPO"
        return s

    def window_setting(self, model: str):
        """Raw window setting for a model: the string "auto" or a number."""
        return self.cpo_windows.get(model, "auto")
