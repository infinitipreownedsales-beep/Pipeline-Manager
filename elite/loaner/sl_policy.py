"""Governed Service-Loaner POLICY — the dealership inputs Elite cannot derive for itself.

DISTINCT, UNIT-EXPLICIT policies. They live in different dimensions and are NEVER mixed:

  * WRITE-DOWN: a governed MONTHLY RATE (%/month, default 1.25%) applied to the vehicle's original authoritative
    INVOICE (never ICV/MSRP), accruing every day in the program (no cap, daily-prorated). Feeds the DOLLAR
    carrying economics. ICV and Velocity are SEPARATE program benefits.
  * PROTECTION BUFFER (DAYS): a time reserve protecting the 240-day total-to-retail deadline. Feeds the
    RELEASE-TIMING backsolve (latest prudent release = 240 − learned post-loaner DTS − recon − buffer days).
    It is a day count and MUST NEVER be added to dollar economics.

Store-scoped, governed (actor + timestamp recorded), append-history via prefs; schema unchanged. Saving is
the EXPLICIT apply — a scenario what-if is passed at call time and never written here.
"""
from __future__ import annotations

# Governed AUTHORITATIVE write-down policy (Kyle, 2026):
#   basis   = original authoritative vehicle INVOICE (never ICV / MSRP / estimate)
#   rate    = 1.25% of invoice PER MONTH while the vehicle remains in Service Loaner
#   cap     = none — the write-down keeps accruing every month it stays in the program
# 1.25% is a governed DEFAULT that brings historical/current SL economics active; a more-specific
# effective-dated entry always wins and is never overwritten by the default.
DEFAULT_WRITEDOWN_MONTHLY_RATE = 1.25
DAYS_PER_MONTH = 30.4375                               # average calendar month, for daily proration


def _norm_model(m):
    return (m or "").upper().strip()


def _to_num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def cumulative_writedown(*, invoice, monthly_rate, tenure_days):
    """Cumulative Service-Loaner write-down in DOLLARS.

    basis = original authoritative INVOICE (never ICV/MSRP/estimate); rate = %/month; NO cap; accrues for
    every day in the program via DAILY PRORATION. Daily proration is a PLANNING ASSUMPTION (exact partial-
    month accounting is not yet confirmed) and is labelled as such in the explanation — it never blocks a
    decision. FAILS CLOSED (None) when the authoritative invoice is missing — it is never substituted.

    Returns (dollars, explanation, is_planning_assumption)."""
    if invoice is None:
        return None, "missing authoritative invoice — write-down fails closed (never MSRP/ICV/estimate)", False
    if monthly_rate is None or tenure_days is None:
        return None, "write-down needs a governed monthly rate and a tenure", False
    daily_rate = float(monthly_rate) / 100.0 / DAYS_PER_MONTH
    dollars = int(round(float(invoice) * daily_rate * float(tenure_days)))
    months = float(tenure_days) / DAYS_PER_MONTH
    expl = (f"{monthly_rate:g}%/mo × invoice ${int(invoice):,} × {float(tenure_days):.0f}d "
            f"(~{months:.1f} mo, daily-prorated — planning assumption) = ${dollars:,}")
    return dollars, expl, True


class SLPolicyStore:
    KEY = "sl_economic_policy"

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self._sk = f"scope::{scope}"

    def _doc(self):
        d = self.prefs.get_pref(self._sk, self.KEY, default={}) or {}
        d.setdefault("writedown_rate", [])            # [{effective_month, rate (%/mo), actor, at}] — governed
        d.setdefault("invoice_by_vin", {})            # vin -> authoritative original invoice $
        d.setdefault("protection_buffer_days", None)  # DAYS (release-timing), not dollars
        d.setdefault("projected_tenure_months", None)  # projected loaner-program tenure (months)
        d.setdefault("history", [])
        return d

    # ---- projected program tenure (MONTHS) — used to turn a MONTHLY write-down rate into a cumulative $ ----
    def projected_tenure_months(self):
        v = self._doc()["projected_tenure_months"]
        return None if v is None else int(v)

    def set_projected_tenure_months(self, months, *, actor, at):
        n = _to_num(months)
        if n is None or n <= 0:
            raise ValueError("projected tenure must be a positive whole number of months")
        d = self._doc()
        d["projected_tenure_months"] = int(round(n))
        d["history"].append({"kind": "projected_tenure_months", "months": int(round(n)), "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return int(round(n))

    # ---- governed MONTHLY write-down RATE (%/mo of invoice; effective-dated; 1.25% default) ------------
    def writedown_monthly_rate(self, month=None):
        """(rate %/month, source) applicable at `month`. The most-recent governed effective-dated entry wins;
        otherwise the governed DEFAULT 1.25% brings economics active (never overwriting a specific value)."""
        entries = sorted((e for e in self._doc()["writedown_rate"] if e.get("rate") is not None),
                         key=lambda e: e.get("effective_month", ""))
        applicable = None
        for e in entries:
            if month is None or (e.get("effective_month", "") <= month):
                applicable = e
        if applicable is not None:
            return float(applicable["rate"]), f"governed {float(applicable['rate']):g}%/mo (eff {applicable.get('effective_month','')})"
        return DEFAULT_WRITEDOWN_MONTHLY_RATE, f"default {DEFAULT_WRITEDOWN_MONTHLY_RATE:g}%/mo"

    def writedown_rate_entries(self):
        return list(self._doc()["writedown_rate"])

    def set_writedown_rate(self, rate, *, effective_month, actor, at):
        n = _to_num(rate)
        if n is None or n < 0:
            raise ValueError("write-down rate must be a non-negative percent per month")
        if n > 100:
            raise ValueError("a monthly write-down rate cannot exceed 100%")
        d = self._doc()
        d["writedown_rate"].append({"effective_month": (effective_month or "").strip(), "rate": round(n, 4),
                                    "actor": actor, "at": at})
        d["history"].append({"kind": "writedown_rate", "rate": round(n, 4), "effective_month": effective_month,
                             "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return round(n, 4)

    # ---- per-VIN authoritative original INVOICE (the write-down basis) --------------------------------
    def invoice_for_vin(self, vin):
        v = self._doc()["invoice_by_vin"].get((vin or "").strip().upper())
        return None if v is None else int(v)

    def set_invoice(self, vin, amount, *, actor, at):
        n = _to_num(amount)
        if n is None or n < 0:
            raise ValueError("invoice must be a non-negative dollar amount")
        d = self._doc()
        d["invoice_by_vin"][(vin or "").strip().upper()] = int(round(n))
        d["history"].append({"kind": "invoice", "vin": (vin or "").strip().upper(), "amount": int(round(n)),
                             "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return int(round(n))

    def all_invoices(self):
        return {k: int(v) for k, v in self._doc()["invoice_by_vin"].items() if v is not None}

    # ---- protection buffer (DAYS — release-timing only; NEVER dollars) --------------------------------
    def protection_buffer_days(self):
        v = self._doc()["protection_buffer_days"]
        return None if v is None else int(v)

    def set_protection_buffer_days(self, days, *, actor, at):
        n = _to_num(days)
        if n is None or n < 0:
            raise ValueError("protection buffer must be a whole number of DAYS (0 or more)")
        d = self._doc()
        d["protection_buffer_days"] = int(round(n))
        d["history"].append({"kind": "protection_buffer_days", "days": int(round(n)), "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return int(round(n))

    def history(self):
        return list(self._doc()["history"])
