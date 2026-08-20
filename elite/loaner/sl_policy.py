"""Governed Service-Loaner economic POLICY — the only two economic inputs Elite cannot derive for itself and
that are genuinely dealership policy: the per-model write-down (value the store books as lost over the loaner
program) and a flat protection / risk buffer. Everything else in the economics is derived from authoritative
evidence (effective-dated ICV / Velocity, preowned resale / gross / DTS, certified Retail coverage).

Store-scoped, governed (actor + timestamp recorded), append-history via prefs; schema unchanged. Saving a
value is the EXPLICIT apply — there is no implicit or scenario write here. A scenario what-if is passed
separately at call time and NEVER persisted through this store (see unit_econ.build_placement_econ).
"""
from __future__ import annotations


def _norm_model(m):
    return (m or "").upper().strip()


def _to_int(v):
    try:
        n = int(round(float(str(v).replace(",", "").replace("$", "").strip())))
    except (TypeError, ValueError):
        return None
    return n


class SLPolicyStore:
    KEY = "sl_economic_policy"

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self._sk = f"scope::{scope}"

    def _doc(self):
        d = self.prefs.get_pref(self._sk, self.KEY, default={}) or {}
        d.setdefault("writedown", {})
        d.setdefault("buffer", None)
        d.setdefault("history", [])
        return d

    # ---- per-model write-down (value lost over the program; a real 0 is allowed, blank stays unknown) ----
    def writedown(self, model):
        """The governed write-down for a model, or None when the dealership has not set one (UNKNOWN — never
        silently zero)."""
        v = self._doc()["writedown"].get(_norm_model(model))
        return None if v is None else int(v)

    def all_writedowns(self):
        return {k: int(v) for k, v in self._doc()["writedown"].items() if v is not None}

    def set_writedown(self, model, amount, *, actor, at):
        n = _to_int(amount)
        if n is None or n < 0:
            raise ValueError("write-down must be a whole dollar amount (0 or more)")
        d = self._doc()
        d["writedown"][_norm_model(model)] = n
        d["history"].append({"kind": "writedown", "model": _norm_model(model), "amount": n,
                             "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return n

    def clear_writedown(self, model):
        d = self._doc()
        if _norm_model(model) in d["writedown"]:
            del d["writedown"][_norm_model(model)]
            self.prefs.set_pref(self._sk, self.KEY, d)
            return True
        return False

    # ---- flat protection / risk buffer ----
    def buffer(self):
        v = self._doc()["buffer"]
        return None if v is None else int(v)

    def set_buffer(self, amount, *, actor, at):
        n = _to_int(amount)
        if n is None or n < 0:
            raise ValueError("protection buffer must be a whole dollar amount (0 or more)")
        d = self._doc()
        d["buffer"] = n
        d["history"].append({"kind": "buffer", "amount": n, "actor": actor, "at": at})
        self.prefs.set_pref(self._sk, self.KEY, d)
        return n

    def history(self):
        return list(self._doc()["history"])
