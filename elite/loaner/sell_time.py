"""Post-loaner sell-time and exit-value estimation from the dealership's own used-car history.

Learned, never guessed. The estimate uses the MOST SPECIFIC comparison the sample supports — (model, model
year, trim, drivetrain) — and BROADENS intelligently (drop drivetrain, then trim, then model year, then
model) only when the narrower cohort is too thin. Missing fields on a comparison target simply skip the
levels that need them; they never block the estimate. Evidence quality (sample size, breadth) is reported as
confidence — it never fabricates precision from a tiny sample, and it does not auto-reject a decision merely
because one input is thin.

Release backsolve: latest prudent release = final-sale deadline − expected sell time − process buffer days.
The deadline is measured from the ACTUAL Service-Loaner in-service date, and 240 days is TOTAL-TO-RETAIL,
never Service-Loaner tenure.
"""
from __future__ import annotations

import datetime as _dt
import statistics

MIN_SAMPLE = 5                     # narrowest cohort must have >= this many usable observations to be "defensible"
_STRONG, _MODERATE, _THIN = "strong", "moderate", "thin"


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _norm(v):
    return str(v or "").strip().upper()


def _dts(row):
    d = _num(row.get("days_to_sell"))
    return d if (d is not None and d >= 0) else None


def _confidence(n):
    if n >= 4 * MIN_SAMPLE:
        return _STRONG
    if n >= MIN_SAMPLE:
        return _MODERATE
    return _THIN


def estimate_sell_time(rows, *, model, model_year=None, trim=None, drivetrain=None):
    """Estimate expected post-loaner days-to-sell for a target vehicle from historical used sales `rows`.

    Returns {days, n, basis, confidence} using the narrowest cohort with a defensible sample, broadening when
    thin; when even the broadest (model) cohort is below MIN_SAMPLE it still returns the best available with
    confidence='thin' (never None while ANY model sample exists), or None when there is no model history at
    all. Never fabricates precision."""
    model = _norm(model)
    # Post-loaner sell time is a USED-market fact. Explicit NEW deliveries in
    # the combined Reynolds lifecycle are identity history, not preowned turn.
    # Legacy used-only exports with no flag remain eligible.
    base = [
        r for r in (rows or [])
        if _norm(r.get("_sale_kind")) != "NEW"
        and _norm(r.get("model")) == model
        and _dts(r) is not None
    ]
    if not base:
        return None
    my = str(model_year or "").strip()
    trim = _norm(trim)
    dtv = _norm(drivetrain)

    def cohort(pred):
        return [_dts(r) for r in base if pred(r)]

    levels = []
    if my and trim and dtv:
        levels.append(("model+MY+trim+drivetrain",
                       lambda r: str(r.get("year") or "").strip() == my and _norm(r.get("trim")) == trim
                       and _norm(r.get("drivetrain")) == dtv))
    if my and trim:
        levels.append(("model+MY+trim",
                       lambda r: str(r.get("year") or "").strip() == my and _norm(r.get("trim")) == trim))
    if my:
        levels.append(("model+MY", lambda r: str(r.get("year") or "").strip() == my))
    if trim:
        levels.append(("model+trim", lambda r: _norm(r.get("trim")) == trim))
    levels.append(("model", lambda r: True))

    best_broad = None
    for label, pred in levels:
        vals = cohort(pred)
        if len(vals) >= MIN_SAMPLE:
            return {"days": round(statistics.median(vals), 1), "n": len(vals), "basis": label,
                    "confidence": _confidence(len(vals))}
        if best_broad is None and vals:
            best_broad = {"days": round(statistics.median(vals), 1), "n": len(vals), "basis": label + " (thin)",
                          "confidence": _THIN}
    # nothing met the sample gate; fall back to the model cohort (always non-empty here) as thin evidence
    allv = cohort(lambda r: True)
    return {"days": round(statistics.median(allv), 1), "n": len(allv), "basis": "model (thin)",
            "confidence": _THIN}


def _add_days(date_str, days):
    d = _dt.date.fromisoformat(str(date_str)[:10])
    return d + _dt.timedelta(days=int(round(days)))


def latest_prudent_release(*, in_service_date, total_to_retail_days, expected_sell_time_days, process_buffer_days):
    """Backsolve the latest prudent Service-Loaner release date from the final-sale deadline.

    deadline       = in_service_date + total_to_retail_days   (240 = TOTAL-TO-RETAIL, not SL tenure)
    release_by     = deadline − expected_sell_time − process_buffer
    Returns {deadline, release_by} as ISO dates, or None when a required input is missing (fails closed —
    never invents a pull date)."""
    if not in_service_date or total_to_retail_days is None or expected_sell_time_days is None \
            or process_buffer_days is None:
        return None
    try:
        deadline = _add_days(in_service_date, total_to_retail_days)
        release_by = deadline - _dt.timedelta(days=int(round(expected_sell_time_days))
                                              + int(round(process_buffer_days)))
    except (ValueError, TypeError):
        return None
    return {"deadline": deadline.isoformat(), "release_by": release_by.isoformat(),
            "total_to_retail_days": int(total_to_retail_days),
            "expected_sell_time_days": round(expected_sell_time_days, 1),
            "process_buffer_days": int(process_buffer_days)}


def release_signal(today, release_by, *, due_window_days=14):
    """The OPERATIONAL keep-vs-release signal for an active loaner from its latest-prudent-release date. This
    is the unambiguous, timing-only half of the KEEP/PULL decision — the full economic KEEP/PULL/SWAP net is
    gated on the write-down accounting basis and is NOT decided here.

      KEEP_RUNWAY     — comfortably before the release-by date
      RELEASE_DUE     — within the due window of release-by (act soon to protect the deadline)
      RELEASE_OVERDUE — past release-by; the total-to-retail deadline is at risk
      UNKNOWN         — the backsolve could not be computed (missing authoritative input)
    """
    if not release_by or not today:
        return {"signal": "UNKNOWN", "days_to_release": None}
    try:
        d = (_dt.date.fromisoformat(str(release_by)[:10]) - _dt.date.fromisoformat(str(today)[:10])).days
    except (ValueError, TypeError):
        return {"signal": "UNKNOWN", "days_to_release": None}
    if d < 0:
        sig = "RELEASE_OVERDUE"
    elif d <= due_window_days:
        sig = "RELEASE_DUE"
    else:
        sig = "KEEP_RUNWAY"
    return {"signal": sig, "days_to_release": d}
