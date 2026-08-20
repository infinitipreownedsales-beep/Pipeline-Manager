"""Governed Service-Loaner POLICY — the dealership inputs Elite cannot derive for itself.

TWO DISTINCT, UNIT-EXPLICIT policies. They live in different dimensions and are NEVER mixed:

  * WRITE-DOWN (dollars, or a percentage that resolves to dollars against a named basis): the value the store
    books as lost over the loaner program. Feeds the DOLLAR economics of a placement.
  * PROTECTION BUFFER (DAYS): a time reserve protecting the 240-day total-to-retail deadline. Feeds the
    RELEASE-TIMING backsolve (latest prudent release = 240 − learned post-loaner DTS − recon − buffer days).
    It is a day count and MUST NEVER be added to dollar economics.

Store-scoped, governed (actor + timestamp recorded), append-history via prefs; schema unchanged. Saving is
the EXPLICIT apply — a scenario what-if is passed at call time and never written here.
"""
from __future__ import annotations


def _norm_model(m):
    return (m or "").upper().strip()


def _to_num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


class SLPolicyStore:
    KEY = "sl_economic_policy"
    WRITEDOWN_KINDS = ("amount", "percent_icv")

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self._sk = f"scope::{scope}"

    def _doc(self):
        d = self.prefs.get_pref(self._sk, self.KEY, default={}) or {}
        d.setdefault("writedown", {})                 # model -> {"kind": amount|percent_icv, "value": N}
        d.setdefault("protection_buffer_days", None)  # DAYS (release-timing), not dollars
        d.setdefault("projected_tenure_months", None)  # projected loaner-program tenure (months) for % write-down
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

    # ---- per-model write-down (unit-explicit: a dollar AMOUNT, or a PERCENT of ICV) --------------------
    def writedown_spec(self, model):
        """The governed write-down spec for a model, or None (UNKNOWN — never silently zero). A spec is
        {'kind': 'amount'|'percent_icv', 'value': float}."""
        s = self._doc()["writedown"].get(_norm_model(model))
        return dict(s) if s else None

    def all_writedowns(self):
        return {k: dict(v) for k, v in self._doc()["writedown"].items() if v}

    def set_writedown(self, model, value, *, kind="amount", actor, at):
        if kind not in self.WRITEDOWN_KINDS:
            raise ValueError("write-down kind must be 'amount' (dollars) or 'percent_icv' (percentage of ICV)")
        n = _to_num(value)
        if n is None or n < 0:
            raise ValueError("write-down must be a non-negative number")
        if kind == "percent_icv" and n > 100:
            raise ValueError("a write-down percentage cannot exceed 100%")
        spec = {"kind": kind, "value": (int(round(n)) if kind == "amount" else round(n, 2))}
        d = self._doc()
        d["writedown"][_norm_model(model)] = spec
        d["history"].append({"kind": "writedown", "model": _norm_model(model), **spec, "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return spec

    def resolve_writedown_dollars(self, model, *, icv, spec=None, tenure_months=None):
        """Resolve a write-down spec to CUMULATIVE DOLLARS. 'amount' is a flat one-time dollar result (used
        directly). 'percent_icv' is a MONTHLY write-down RATE: cumulative $ = monthly_rate% × ICV × tenure
        (months) — so a longer tenure loses more value. Needs both the unit's ICV and a projected tenure;
        returns (None, reason) when either is unavailable (never guessed). Returns (dollars, explanation)."""
        spec = spec or self.writedown_spec(model)
        if not spec:
            return None, "no governed write-down policy for this model"
        if spec["kind"] == "amount":
            return int(spec["value"]), f"${int(spec['value']):,} (flat, one-time)"
        if icv is None:
            return None, "monthly write-down is a percent of ICV but ICV is unknown for this unit"
        months = tenure_months if tenure_months is not None else self.projected_tenure_months()
        if months is None:
            return None, "monthly write-down needs a projected program tenure (months) — not set"
        months = int(months)
        dollars = int(round(spec["value"] / 100.0 * float(icv) * months))
        return dollars, (f"{spec['value']:g}%/mo × ICV ${int(icv):,} × {months} mo = ${dollars:,}")

    def clear_writedown(self, model):
        d = self._doc()
        if _norm_model(model) in d["writedown"]:
            del d["writedown"][_norm_model(model)]
            self.prefs.set_pref(self._sk, self.KEY, d)
            return True
        return False

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
