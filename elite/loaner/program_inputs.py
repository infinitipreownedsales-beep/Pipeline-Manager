"""Effective-dated Service-Loaner program inputs (ICV / Velocity).

Permanent semantic rule: recorded_at is NOT effective_month. A value entered today may legitimately have become
effective months earlier. Each entry preserves separately: effective_month, value, model, trim/scope, actor,
recorded_at, and provenance. Storage is append-only — a newer value supersedes PROSPECTIVELY by its effective
month and never rewrites a prior period, so the economic layer can later retrieve the value that applied during
any lifecycle period.

Two hard correctness rules:
  * UNKNOWN != $0 — a missing/unset value is `None` (unresolved), never materialized as 0. Only an explicitly
    entered authoritative zero is stored as 0.
  * Never fabricate a historical value; coverage is reported honestly (complete / incomplete + missing periods).
This module represents inputs only; it does not change any Phase-4 calculation semantics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..ids import new_id

KINDS = ("icv", "velocity")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def valid_month(m) -> bool:
    if not (isinstance(m, str) and _MONTH_RE.match(m)):
        return False
    try:
        mm = int(m[5:7])
    except ValueError:
        return False
    return 1 <= mm <= 12


def _midx(m):
    return int(m[:4]) * 12 + (int(m[5:7]) - 1)


def _from_midx(i):
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def prev_month(m):
    return _from_midx(_midx(m) - 1)


def parse_value(v):
    """Blank/None -> None (UNRESOLVED). An explicit number (including 0) -> int. Never coerces missing to 0."""
    s = ("" if v is None else str(v)).strip().replace(",", "")
    if s == "":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ProgramEntry:
    id: str
    kind: str
    effective_month: str
    model: str
    trim: str                # scope; "" = applies to all trims of the model
    value: int | None        # None = UNRESOLVED (never rendered as $0); 0 only if explicitly entered
    actor: str
    recorded_at: str
    provenance: str = ""
    day_cap: int | None = None
    mile_cap: int | None = None
    model_year: str = ""     # MY like "2026"; "" = applies to all model years (ICV/Velocity can differ by MY)
    status: str = "active"   # active | retired — retired entries never resolve as authoritative truth
    correction_of: str = ""  # lineage: the entry this one supersedes/corrects

    def to_dict(self):
        return dict(id=self.id, kind=self.kind, effective_month=self.effective_month, model=self.model,
                    trim=self.trim, value=self.value, actor=self.actor, recorded_at=self.recorded_at,
                    provenance=self.provenance, day_cap=self.day_cap, mile_cap=self.mile_cap,
                    model_year=self.model_year, status=self.status, correction_of=self.correction_of)

    @staticmethod
    def from_dict(d):
        return ProgramEntry(d["id"], d["kind"], d["effective_month"], d.get("model", ""), d.get("trim", ""),
                            d.get("value"), d.get("actor", ""), d.get("recorded_at", ""),
                            d.get("provenance", ""), d.get("day_cap"), d.get("mile_cap"),
                            d.get("model_year", ""), d.get("status", "active"), d.get("correction_of", ""))


class ProgramInputsStore:
    """Append-only, store-scoped effective-dated program inputs (governed JSON in the prefs store; no schema
    change). Reads migrate any legacy `icv_program` / `velocity_program` rows once (non-destructively)."""

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self.scope = scope
        self._sk = f"scope::{scope}"

    def _key(self, kind):
        return f"program_{kind}"

    def _legacy_key(self, kind):
        return {"icv": "icv_program", "velocity": "velocity_program"}[kind]

    def _raw(self, kind):
        return self.prefs.get_pref(self._sk, self._key(kind), default=None)

    def entries(self, kind):
        if kind not in KINDS:
            return []
        raw = self._raw(kind)
        if raw is None:
            raw = self._migrate_legacy(kind)
        return [ProgramEntry.from_dict(d) for d in (raw or [])]

    def _migrate_legacy(self, kind):
        """Import legacy rows once. A legacy amount of 0 is AMBIGUOUS (the old form materialized blanks as 0),
        so it is imported as UNRESOLVED (value=None) with a provenance note to re-enter — never silently kept
        as an authoritative $0. Positive legacy amounts are preserved."""
        legacy = self.prefs.get_pref(self._sk, self._legacy_key(kind), default=[]) or []
        out = []
        for p in legacy:
            amt = p.get("amount")
            val = amt if isinstance(amt, (int, float)) and amt > 0 else None
            prov = "legacy import" if val is not None else "legacy ambiguous zero — re-enter to confirm"
            out.append(ProgramEntry(new_id("pgm"), kind, p.get("eff", "") or "", (p.get("model") or "").upper(),
                                    p.get("trim", "") or "", (int(val) if val is not None else None),
                                    "", "", prov,
                                    p.get("day_cap") if kind == "velocity" else None,
                                    p.get("mile_cap") if kind == "velocity" else None).to_dict())
        self.prefs.set_pref(self._sk, self._key(kind), out)     # persist the migrated form (idempotent)
        return out

    def add(self, kind, *, effective_month, model, value, actor, recorded_at, trim="", provenance="",
            day_cap=None, mile_cap=None, model_year="", correction_of=""):
        """Append a governed effective-dated entry. `value` None is allowed (records UNRESOLVED coverage).
        Never rewrites a prior entry."""
        if kind not in KINDS:
            raise ValueError(f"unknown program kind {kind!r}")
        if not valid_month(effective_month):
            raise ValueError(f"invalid effective_month {effective_month!r}")
        e = ProgramEntry(new_id("pgm"), kind, effective_month, (model or "").upper(), (trim or "").strip(),
                         value, actor, recorded_at, provenance,
                         day_cap if kind == "velocity" else None, mile_cap if kind == "velocity" else None,
                         (model_year or "").strip(), "active", correction_of)
        rows = [x.to_dict() for x in self.entries(kind)]
        rows.append(e.to_dict())
        self.prefs.set_pref(self._sk, self._key(kind), rows)
        return e

    def retire(self, kind, entry_id, *, actor, at):
        """Retire an erroneous entry from active resolution — PRESERVED (status=retired), never deleted; a
        retired entry never resolves as authoritative program truth."""
        rows = [x.to_dict() for x in self.entries(kind)]
        for r in rows:
            if r["id"] == entry_id and r.get("status", "active") != "retired":
                r["status"] = "retired"
                r["provenance"] = (r.get("provenance") or "") + f" · retired by {actor} {at[:10]}"
                self.prefs.set_pref(self._sk, self._key(kind), rows)
                return True
        return False

    def correct(self, kind, entry_id, *, actor, recorded_at, **fields):
        """Governed correction/supersession: retire the original and add a replacement that keeps a lineage
        (correction_of). Corrected fields default to the original's values; the original is preserved."""
        orig = next((e for e in self.entries(kind) if e.id == entry_id), None)
        if orig is None:
            return None
        self.retire(kind, entry_id, actor=actor, at=recorded_at)
        base = dict(effective_month=orig.effective_month, model=orig.model, trim=orig.trim, value=orig.value,
                    provenance=orig.provenance, model_year=orig.model_year,
                    day_cap=orig.day_cap, mile_cap=orig.mile_cap)
        base.update({k: v for k, v in fields.items() if v is not None or k == "value"})
        return self.add(kind, actor=actor, recorded_at=recorded_at, correction_of=entry_id, **base)

    def active_entries(self, kind):
        return [e for e in self.entries(kind) if e.status == "active"]

    def applicable(self, kind, model, month, *, trim="", model_year=""):
        """The entry whose value applied to (model, model_year, trim) at `month`: the latest effective_month
        <= month with a non-None value, among ACTIVE (non-retired) entries, scope-matching. A more specific
        entry (matching model_year and/or trim) wins over a broader all-MY / all-trim entry. None = unresolved."""
        model = (model or "").upper()
        my = (model_year or "").strip()
        trim = (trim or "").strip()
        cands = [e for e in self.active_entries(kind)
                 if e.model == model and e.value is not None and valid_month(e.effective_month)
                 and _midx(e.effective_month) <= _midx(month)
                 and (e.model_year == "" or e.model_year == my)
                 and (e.trim == "" or e.trim == trim)]
        if not cands:
            return None
        # order: latest effective month, then most specific (model-year match, then trim match), then recency
        cands.sort(key=lambda e: (_midx(e.effective_month), e.model_year != "", e.trim != "", e.recorded_at))
        return cands[-1]


def entry_status(entry, current_month):
    """retired / current / historical / future / unresolved — relative to the current month (presentation)."""
    if getattr(entry, "status", "active") == "retired":
        return "retired"
    if entry.value is None:
        return "unresolved"
    if not valid_month(entry.effective_month):
        return "unresolved"
    if _midx(entry.effective_month) > _midx(current_month):
        return "future"
    return "current" if _midx(entry.effective_month) == _midx(current_month) else "historical"


def resolve_for_unit(store, kind, *, model, in_service_date, model_year="", trim=""):
    """Resolve the program terms that apply to a PHYSICAL unit — driven by the unit's authoritative IN-SERVICE
    date, never today's date. The in-service month selects the applicable effective period; a later program
    term does not retroactively rewrite an earlier vehicle's applicable program. Returns
    {"status": resolved|unresolved, "reason"?, "entry"?}. Never fabricates a date or a value."""
    if not in_service_date or not isinstance(in_service_date, str) or len(in_service_date) < 7:
        return {"status": "unresolved", "reason": "no authoritative in-service date"}
    month = in_service_date[:7]
    if not valid_month(month):
        return {"status": "unresolved", "reason": "in-service date is not a valid month"}
    e = store.applicable(kind, model, month, trim=trim, model_year=model_year)
    if e is None:
        return {"status": "unresolved", "reason": f"no applicable {kind} value at in-service month {month}"}
    return {"status": "resolved", "in_service_month": month, "entry": e}


def coverage(store, kind, earliest_active_month, current_month, *, models=()):
    """Read-only coverage of the active fleet's lifecycle by program history for `kind`:
        {"status": complete|incomplete|unknown, "earliest": <month|None>, "missing": [start, end] | []}.
    `earliest_active_month` is the earliest in-service month across the active fleet; `models` optionally scopes
    to the active fleet's models. Reports honestly — never claims coverage that does not exist."""
    have = [e for e in store.active_entries(kind)
            if e.value is not None and valid_month(e.effective_month) and (not models or e.model in models)]
    if not earliest_active_month or not valid_month(earliest_active_month):
        return {"status": "unknown", "earliest": None, "missing": [],
                "reason": "no authoritative active in-service dates"}
    if not have:
        return {"status": "incomplete", "earliest": earliest_active_month,
                "missing": [earliest_active_month, current_month], "reason": "no program values recorded"}
    earliest_program = min(_midx(e.effective_month) for e in have)
    if earliest_program <= _midx(earliest_active_month):
        return {"status": "complete", "earliest": earliest_active_month, "missing": []}
    return {"status": "incomplete", "earliest": earliest_active_month,
            "missing": [earliest_active_month, prev_month(_from_midx(earliest_program))],
            "reason": "program history starts after the earliest active in-service month"}
