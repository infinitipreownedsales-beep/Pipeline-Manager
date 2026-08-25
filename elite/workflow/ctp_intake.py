"""Live multi-file CTP (Change-The-Production) intake, reconciliation and evaluation.

CTP = the OEM tells us which EXISTING production orders are still changeable, in operator-uploaded model files
(QX60 / QX65 / QX80, plus any others the OEM exposes). This module is a TEMPORARY, in-session eligibility
overlay — it does NOT ingest into the permanent pipeline, creates no future inventory, and touches no source
contract. It is pure/stdlib and isolated so the later Reynolds source-contract refactor can follow without
rework.

Flow:
  1. parse_ctp_file()  — read a CSV/TSV/XLSX CTP file into normalized rows (header-agnostic; flexible aliases).
  2. to_candidate()    — map a row to a CTP candidate (order#, VIN, current config, arrival).
  3. reconcile()       — match each candidate to the CURRENT pipeline by Order# then VIN; flag unmatched /
                         identity-mismatch; never create duplicate future inventory.
  4. evaluate()        — judge all candidates TOGETHER against the certified board and re-run the full horizon
                         after each proposed CHANGE (one change can alter another need). KEEP unless a proven
                         superior replacement exists. No synthetic diversification / nearest-code substitution /
                         colour preference — a CHANGE target must be a genuinely certified-short combination.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

KEEP = "KEEP"
CHANGE = "CHANGE"

# reconciliation status
MATCHED = "matched"
UNMATCHED = "unmatched"          # candidate not found in current pipeline — verify source alignment
CONFLICT = "conflict"           # order matched but VIN (or other identity) disagrees — surface both

# flexible source-column aliases → canonical candidate field (header-agnostic; case/space/punct-insensitive).
_ALIASES = {
    "order_number": ("order", "order#", "ordernumber", "orderno", "orderno", "moid", "manufacturerorderid",
                     "productionorder", "productionorderid", "ponumber", "po"),
    "vin": ("vin", "vinnumber", "serial", "fullvin"),
    "model": ("model", "modelline", "modelname", "carline"),
    "model_code": ("modelcode", "code", "ordercode", "optioncode"),
    "exterior": ("ext", "exterior", "exteriorcode", "exteriorcolor", "extcolor"),
    "interior": ("int", "interior", "interiorcode", "interiorcolor", "intcolor"),
    "trim": ("trim", "trimlevel", "grade"),
    "drivetrain": ("drivetrain", "drive", "driveline"),
    "description": ("description", "desc", "vehicle", "vehicledescription"),
    "arrival_month": ("productionmonth", "prodmonth", "arrivalmonth", "eta", "arrival", "buildmonth"),
    "editability": ("editability", "status", "ctpstatus", "changeable", "eligible", "eligibility"),
}


def _norm_header(h):
    return "".join(ch for ch in str(h or "").strip().lower() if ch.isalnum())


def parse_ctp_file(filename, data):
    """Parse one uploaded CTP file into a list of normalized-header dict rows. Supports CSV/TSV/TXT (stdlib csv)
    and XLSX (stdlib zipfile + ElementTree, first worksheet). Returns [] for an empty/unreadable file — never
    raises, never fabricates rows."""
    name = (filename or "").lower()
    try:
        if name.endswith(".xlsx"):
            return _parse_xlsx_rows(data)
        text = data.decode("utf-8", "ignore") if isinstance(data, (bytes, bytearray)) else str(data)
        delim = "\t" if (name.endswith(".tsv") or ("\t" in text.splitlines()[0] if text.splitlines() else False)) else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        if not rows:
            return []
        header = [_norm_header(h) for h in rows[0]]
        out = []
        for raw in rows[1:]:
            if not any(str(c).strip() for c in raw):
                continue
            out.append({header[i]: (str(raw[i]).strip() if i < len(raw) else "") for i in range(len(header))})
        return out
    except Exception:   # noqa: BLE001 — a bad file must never break the session
        return []


def _parse_xlsx_rows(data):
    """Minimal, stdlib-only XLSX → list-of-dict (first worksheet, first row = header)."""
    import zipfile
    from xml.etree import ElementTree as ET

    def local(tag):
        return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag

    def col_idx(ref):
        letters = "".join(c for c in (ref or "") if c.isalpha())
        idx = 0
        for c in letters:
            idx = idx * 26 + (ord(c.upper()) - 64)
        return idx - 1 if idx else 0

    payload = bytes(data) if isinstance(data, (bytes, bytearray)) else str(data).encode("utf-8", "ignore")
    zf = zipfile.ZipFile(io.BytesIO(payload))
    names = set(zf.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in list(sroot):
            if local(si.tag) == "si":
                shared.append("".join(t.text or "" for t in si.iter() if local(t.tag) == "t"))
    sheet_paths = sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    if not sheet_paths:
        return []
    sroot = ET.fromstring(zf.read(sheet_paths[0]))
    cells = {}
    maxrow = maxcol = 0
    for row in sroot.iter():
        if local(row.tag) != "row":
            continue
        for c in row:
            if local(c.tag) != "c":
                continue
            ref = c.get("r", "")
            rnum = int("".join(ch for ch in ref if ch.isdigit()) or 0)
            cidx = col_idx(ref)
            t = c.get("t", "")
            v = ""
            for child in c:
                if local(child.tag) == "v":
                    v = child.text or ""
                elif local(child.tag) == "is":
                    v = "".join(x.text or "" for x in child.iter() if local(x.tag) == "t")
            if t == "s" and v.isdigit() and int(v) < len(shared):
                v = shared[int(v)]
            cells[(rnum, cidx)] = v
            maxrow, maxcol = max(maxrow, rnum), max(maxcol, cidx)
    if maxrow < 1:
        return []
    rownums = sorted({r for (r, _c) in cells})
    header_row = rownums[0]
    header = [_norm_header(cells.get((header_row, c), "")) for c in range(maxcol + 1)]
    out = []
    for r in rownums[1:]:
        rec = {header[c]: str(cells.get((r, c), "")).strip() for c in range(maxcol + 1) if header[c]}
        if any(v for v in rec.values()):
            out.append(rec)
    return out


@dataclass
class Candidate:
    order_number: str = ""
    vin: str = ""
    model: str = ""
    model_code: str = ""
    exterior: str = ""
    interior: str = ""
    trim: str = ""
    drivetrain: str = ""
    description: str = ""
    arrival_month: str = ""
    editability: str = ""
    source_file: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def key(self):
        return (self.order_number or "").strip().upper() or (self.vin or "").strip().upper()


def to_candidate(row, *, source_file=""):
    """Map a normalized-header row to a Candidate via flexible aliases. Only real source values are copied —
    nothing is inferred. Returns None when neither an order# nor a VIN is present (cannot reconcile)."""
    def pick(field_name):
        for a in _ALIASES[field_name]:
            if a in row and str(row[a]).strip():
                return str(row[a]).strip()
        return ""
    c = Candidate(order_number=pick("order_number"), vin=pick("vin").upper(), model=pick("model"),
                  model_code=pick("model_code"), exterior=pick("exterior").upper(),
                  interior=pick("interior").upper(), trim=pick("trim"), drivetrain=pick("drivetrain"),
                  description=pick("description"), arrival_month=pick("arrival_month"),
                  editability=pick("editability"), source_file=source_file, raw=dict(row))
    return c if c.key else None


@dataclass
class Reconciled:
    candidate: Candidate
    status: str
    pipeline: Optional[dict] = None      # matched pipeline row: {order_number, vin, combination_id, canonical, ...}
    conflict_detail: str = ""


def reconcile(candidates, pipeline_rows):
    """Match each candidate to the CURRENT pipeline by Order# (then VIN). `pipeline_rows` are dicts with
    order_number, vin, combination_id, canonical, model, arrival_month. Never creates pipeline rows; each
    candidate maps to at most one pipeline unit (count-once)."""
    by_order, by_vin = {}, {}
    for p in pipeline_rows or []:
        o = (p.get("order_number") or "").strip().upper()
        v = (p.get("vin") or "").strip().upper()
        if o:
            by_order.setdefault(o, p)
        if v:
            by_vin.setdefault(v, p)
    out = []
    for c in candidates:
        o, v = (c.order_number or "").strip().upper(), (c.vin or "").strip().upper()
        p = by_order.get(o) if o else None
        if p is not None:
            # order matched — check VIN agreement when both sides carry one
            pv = (p.get("vin") or "").strip().upper()
            if v and pv and v != pv:
                out.append(Reconciled(c, CONFLICT, p, f"CTP VIN {v} ≠ pipeline VIN {pv} for order {o}"))
            else:
                out.append(Reconciled(c, MATCHED, p))
            continue
        p = by_vin.get(v) if v else None
        if p is not None:
            out.append(Reconciled(c, MATCHED, p))
        else:
            out.append(Reconciled(c, UNMATCHED, None,
                                  "CTP candidate not found in current Pipeline — verify source alignment"))
    return out


@dataclass
class Verdict:
    reconciled: Reconciled
    recommendation: str                  # KEEP / CHANGE
    proposed_combination: Optional[str] = None      # canonical of the CHANGE target (a certified-short combo)
    proposed_label: str = ""
    why: str = ""
    proof: dict = field(default_factory=dict)


def _model_of(label):
    return (label or "").split(" ", 1)[0]


def evaluate(reconciled, board):
    """Judge all reconciled candidates TOGETHER, sequentially against a DISPOSABLE copy of the certified board,
    re-running the full horizon after each accepted CHANGE (one change alters another need).

    `board` is a dict keyed by combination_id → {"canonical", "label", "model", "excess", "short"} where
    `excess` is the certified over-supply on that combination and `short` the certified acquire-now need. A CTP
    order currently scheduled to an EXCESS combination is a CHANGE candidate: it is re-specified to a
    genuinely-SHORT combination OF THE SAME MODEL LINE (never a fabricated/nearest target, never a colour
    preference). The proof is the full-horizon coverage effect: source excess −1, target short −1. Everything
    else KEEPs (no proven superior replacement)."""
    # disposable planning state
    state = {cid: {"excess": int(b.get("excess", 0) or 0), "short": int(b.get("short", 0) or 0),
                   "canonical": b.get("canonical", cid), "label": b.get("label", ""), "model": b.get("model", "")}
             for cid, b in (board or {}).items()}
    # short targets grouped by model line, strongest need first (deterministic; economics via `short` magnitude)
    def short_targets(model):
        return sorted([(cid, st) for cid, st in state.items()
                       if st["short"] > 0 and (st["model"] or _model_of(st["label"])) == model],
                      key=lambda t: (-t[1]["short"], t[1]["canonical"]))

    verdicts = []
    # evaluate matched candidates in a stable order; unmatched/conflict cannot be evaluated (surfaced as-is)
    for rc in reconciled:
        if rc.status != MATCHED or rc.pipeline is None:
            verdicts.append(Verdict(rc, KEEP, why=(rc.conflict_detail or
                            "not reconciled to the current pipeline — cannot evaluate a change"),
                                    proof={"reconciliation": rc.status}))
            continue
        cid = rc.pipeline.get("combination_id")
        src = state.get(cid)
        model = (rc.pipeline.get("model") or (_model_of(src["label"]) if src else "")).upper() or \
            (rc.candidate.model or "").upper()
        if src is None or src["excess"] <= 0:
            verdicts.append(Verdict(rc, KEEP,
                            why="current configuration is not over-supplied — no proven superior change",
                            proof={"current_excess": (src["excess"] if src else 0)}))
            continue
        targets = short_targets(model)
        if not targets:
            verdicts.append(Verdict(rc, KEEP,
                            why="over-supplied here, but no certified-short target of the same model exists to "
                                "re-specify into — Elite will not fabricate a target",
                            proof={"current_excess": src["excess"], "candidate_targets": 0}))
            continue
        # proven superior replacement: move this one unit excess→short. Re-run the horizon (mutate state).
        tcid, tgt = targets[0]
        before = {"source_excess": src["excess"], "target_short": tgt["short"]}
        src["excess"] -= 1
        tgt["short"] -= 1
        verdicts.append(Verdict(rc, CHANGE, proposed_combination=tgt["canonical"], proposed_label=tgt["label"],
                        why=(f"current configuration is over-supplied and {tgt['label']} is certified short; "
                             f"re-specifying this incoming order covers a real need and reduces excess "
                             f"(full-horizon net improvement)."),
                        proof={"source_combination": src["canonical"], "target_combination": tgt["canonical"],
                               "before": before,
                               "after": {"source_excess": src["excess"], "target_short": tgt["short"]}}))
    return verdicts


def summarize(reconciled, verdicts):
    """Session headline counts for the UI."""
    return {"candidates": len(reconciled),
            "matched": sum(1 for r in reconciled if r.status == MATCHED),
            "unmatched": sum(1 for r in reconciled if r.status == UNMATCHED),
            "conflict": sum(1 for r in reconciled if r.status == CONFLICT),
            "keep": sum(1 for v in verdicts if v.recommendation == KEEP),
            "change": sum(1 for v in verdicts if v.recommendation == CHANGE)}
