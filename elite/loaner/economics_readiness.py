"""Phase-4 economic READINESS — a precise, honest account of which authoritative inputs the Service-Loaner
economic placement ranking needs, and which are still missing. It computes NO economics and fabricates
nothing; it only reports whether the certified economic engine can run yet, so the operator surfaces can

  * stop labelling the Retail-harm fallback as the economically "best" placement, and
  * replace the stale "coverage incomplete" warning with the ACTUAL remaining gates.

Required authoritative inputs for a total-dealership Service-Loaner placement ranking:
  - effective-dated ICV coverage over the active fleet lifecycle;
  - effective-dated Velocity terms (incl. day / mileage caps) over the same;
  - dealership used-market evidence (resale / post-loaner DTS) with a defensible sample;
  - governed write-down policy / amounts;
  - governed protection / risk buffer.
When any is missing the ranking stays gated (Undetermined) — never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass

# Governed prefs that WOULD carry the remaining economic policy inputs (not yet populated in the pilot).
_WRITEDOWN_KEY = "sl_writedown_policy"
_BUFFER_KEY = "sl_protection_buffer"


@dataclass(frozen=True)
class Gate:
    key: str
    label: str
    present: bool
    detail: str


def assess_gates(*, icv_complete, velocity_complete, used_evidence_defensible, writedown_present,
                 buffer_present, icv_detail="", velocity_detail="", used_detail=""):
    """Pure: turn the availability of each authoritative input into an ordered gate list."""
    return [
        Gate("icv", "Effective-dated ICV coverage", bool(icv_complete),
             icv_detail or ("complete" if icv_complete else "incomplete over the active fleet lifecycle")),
        Gate("velocity", "Effective-dated Velocity terms", bool(velocity_complete),
             velocity_detail or ("complete" if velocity_complete else "incomplete over the active fleet lifecycle")),
        Gate("used_evidence", "Dealership used-market evidence (resale / post-loaner DTS)",
             bool(used_evidence_defensible),
             used_detail or ("defensible sample present" if used_evidence_defensible
                             else "no defensible used-sale sample for the active models yet")),
        Gate("writedown", "Governed write-down policy / amounts", bool(writedown_present),
             "recorded" if writedown_present else "no governed write-down policy input exists yet"),
        Gate("buffer", "Governed protection / risk buffer", bool(buffer_present),
             "recorded" if buffer_present else "no governed protection-buffer input exists yet"),
    ]


def ready(gates):
    return bool(gates) and all(g.present for g in gates)


def missing(gates):
    return [g for g in gates if not g.present]


def _coverage_state(app, scope):
    """(icv_complete, velocity_complete, icv_detail, velocity_detail) from effective-dated Program Inputs,
    assessed over the active fleet's lifecycle. Reuses the certified coverage assessment; invents nothing."""
    from .program_inputs import ProgramInputsStore, coverage
    from .intelligence import build_intelligence
    from ..clock import to_utc_iso
    store = ProgramInputsStore(app.prefs, scope)
    cur = to_utc_iso(app.stack.clock.now())[:7]
    try:
        intel = build_intelligence(app.stack.db.conn, scope, app.prefs, app.stack.clock)
        months = [u.in_service_date[:7] for u in intel.units if u.in_service_date]
        earliest = min(months) if months else None
        models = tuple(m for m, _ in intel.composition)
    except Exception:   # noqa: BLE001
        earliest, models = None, ()

    def one(kind):
        cov = coverage(store, kind, earliest, cur, models=models)
        return cov["status"] == "complete", cov["status"]

    icv_ok, icv_st = one("icv")
    vel_ok, vel_st = one("velocity")
    return icv_ok, vel_ok, icv_st, vel_st


def _used_evidence_defensible(app, scope):
    try:
        from .preowned_evidence import build_preowned_evidence
        pe = build_preowned_evidence(app.stack.db.conn, scope)
        return any(getattr(c, "defensible", False) for m in getattr(pe, "models", []) for c in getattr(m, "resale_years", []))
    except Exception:   # noqa: BLE001
        return False


def phase4_gates(app, scope):
    """Live Phase-4 readiness gates for this store."""
    icv_ok, vel_ok, icv_st, vel_st = _coverage_state(app, scope)
    used_ok = _used_evidence_defensible(app, scope)
    try:
        wd = bool(app.prefs.get_pref(f"scope::{scope}", _WRITEDOWN_KEY, default=None))
        buf = bool(app.prefs.get_pref(f"scope::{scope}", _BUFFER_KEY, default=None))
    except Exception:   # noqa: BLE001
        wd, buf = False, False
    return assess_gates(icv_complete=icv_ok, velocity_complete=vel_ok, used_evidence_defensible=used_ok,
                        writedown_present=wd, buffer_present=buf,
                        icv_detail=f"ICV coverage {icv_st}", velocity_detail=f"Velocity coverage {vel_st}")
