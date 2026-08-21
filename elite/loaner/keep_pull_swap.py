"""KEEP vs PULL vs SWAP — total-dealership economic comparison for a Service-Loaner slot.

§16 resolved (Kyle): cumulative Service-Loaner write-down REDUCES the vehicle's economic/book basis — it is
NOT a period cost that disappears. So:

    adjusted_basis   = original_invoice − cumulative_service_loaner_write_down
    front_end_gross  = expected_used_selling_price − adjusted_basis − recon        (FRONT-END ONLY)

AUTHORITATIVE PREOWNED PROFIT RULE: every preowned profit figure here is FRONT-END gross only. Backend / F&I
income is NEVER estimated into expected used gross and NEVER influences KEEP/PULL/SWAP. Gross is computed as
price − adjusted_basis − recon by construction, so no backend term can leak in.

ICV and Velocity are SEPARATE program benefits, added once (no double counting). More write-down lowers the
basis and can raise exit gross, but KEEP is NOT automatically best: market depreciation of the selling price,
Velocity forfeited past the 240-day deadline, longer sell-time, Retail opportunity cost, or a superior SWAP
candidate can overwhelm the basis benefit. This module decides nothing about accounting — it only combines
the components Kyle has now made authoritative.
"""
from __future__ import annotations

from .sl_policy import cumulative_writedown


def expected_front_end_gross(*, used_price, adjusted_basis, recon=0):
    """Front-end used gross = selling price − adjusted basis − recon. None when price is unknown (fail closed).
    Backend / F&I is never included."""
    if used_price is None or adjusted_basis is None:
        return None
    return round(float(used_price) - float(adjusted_basis) - float(recon or 0), 2)


def _velocity(benefit, preserved):
    return float(benefit or 0) if preserved else 0.0


def compare_actions(*, invoice, monthly_rate, tenure_days_now, keep_extra_days,
                    used_price_now, used_price_future, recon=0,
                    velocity_contingent=0, velocity_preserved_now=True, velocity_preserved_future=True,
                    icv_earned=0, icv_clawback_if_pull=0,
                    retail_opportunity_cost=0, swap_candidate_net=None):
    """Total-dealership net of each action for this slot, computed INCREMENTALLY FROM THE DECISION MOMENT.

    Only future / action-dependent differences drive the choice:
      * cumulative write-down ALREADY earned is embedded in the current adjusted basis (counted once, never a
        separate profit line); future incremental write-down under KEEP lowers the future basis (counted once);
      * ICV already earned is SUNK and COMMON — it is NOT added to any action net (so KEEP cannot "re-earn" it);
        it is shown in Proof for lifecycle context. `icv_clawback_if_pull` handles the rare case where pulling
        now would forfeit an otherwise-earned ICV;
      * Velocity is CONTINGENT on retailing within the 240-day deadline, so it enters each action net only when
        that action preserves it.

    Actions:
      PULL  — release now, retail the used unit:  front_gross(now) + Velocity(now, contingent) − icv_clawback
      KEEP  — hold longer, then exit:             front_gross(future, lower basis) + Velocity(future, contingent)
      SWAP  — PULL now AND place the best candidate into the slot: PULL + swap_candidate_net
    Retail opportunity cost is a property of the slot (occupied either way) and is reported for transparency,
    not added asymmetrically. Missing invoice/price gates the affected action rather than fabricating a value.
    """
    missing = []
    if invoice is None:
        missing.append("invoice")
    if monthly_rate is None or tenure_days_now is None:
        missing.append("tenure/rate")

    def basis(extra):
        if invoice is None:
            return None, None
        wd, _e, _pa = cumulative_writedown(invoice=invoice, monthly_rate=monthly_rate,
                                           tenure_days=(tenure_days_now or 0) + extra)
        return (None, None) if wd is None else (round(float(invoice) - wd, 2), wd)

    basis_now, wd_now = basis(0)
    basis_future, wd_future = basis(max(0, keep_extra_days or 0))

    g_now = expected_front_end_gross(used_price=used_price_now, adjusted_basis=basis_now, recon=recon)
    g_future = expected_front_end_gross(used_price=used_price_future, adjusted_basis=basis_future, recon=recon)

    nets = {}
    if g_now is not None:
        nets["PULL"] = round(g_now + _velocity(velocity_contingent, velocity_preserved_now)
                             - float(icv_clawback_if_pull or 0), 2)
    else:
        missing.append("used_price_now")
    if g_future is not None:
        nets["KEEP"] = round(g_future + _velocity(velocity_contingent, velocity_preserved_future), 2)
    else:
        missing.append("used_price_future")
    if "PULL" in nets and swap_candidate_net is not None:
        nets["SWAP"] = round(nets["PULL"] + float(swap_candidate_net), 2)

    best = max(nets, key=lambda k: nets[k]) if nets else None
    components = {
        "adjusted_basis_now": basis_now, "adjusted_basis_future": basis_future,
        "cumulative_write_down_now": wd_now, "cumulative_write_down_future": wd_future,
        "front_end_gross_now": g_now, "front_end_gross_future": g_future,
        "velocity_now": _velocity(velocity_contingent, velocity_preserved_now),
        "velocity_future": _velocity(velocity_contingent, velocity_preserved_future),
        "icv_earned_sunk": float(icv_earned or 0),          # lifecycle context only (not in the action delta)
        "retail_opportunity_cost": float(retail_opportunity_cost or 0),
    }
    return {"nets": nets, "best": best, "components": components, "missing": missing}
