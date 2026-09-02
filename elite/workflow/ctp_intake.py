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

# business decision states — KEEP is a decision, never a fallback for unresolved data.
KEEP = "KEEP"
CHANGE = "CHANGE"
CANT_EVALUATE = "CANT_EVALUATE"

# reconciliation status
MATCHED = "matched"
UNMATCHED = "unmatched"          # no current pipeline unit matches
CONFLICT = "conflict"           # order# and VIN point to different pipeline units — surface both
AMBIGUOUS = "ambiguous"         # more than one possible pipeline match — cannot choose safely

# flexible source-column aliases → canonical candidate field (header-agnostic; case/space/punct-insensitive).
_ALIASES = {
    "order_number": ("order", "order#", "ordernumber", "orderno", "moid", "manufacturerorderid",
                     "productionorder", "productionorderid", "ponumber", "po"),
    "vin": ("vin", "vinnumber", "serial", "fullvin"),
    "model": ("model", "modelline", "modelname", "carline"),
    "model_code": ("modelcode", "ordercode", "optioncode"),
    "exterior": ("ext", "exterior", "exteriorcode", "extcolor"),
    "interior": ("int", "interior", "interiorcode", "intcolor"),
    "trim": ("trim", "trimlevel", "grade"),
    "drivetrain": ("drivetrain", "drive", "driveline"),
    "description": ("description", "desc", "vehicle", "vehicledescription"),
    "arrival_month": ("productionmonth", "prodmonth", "arrivalmonth", "eta", "arrival", "buildmonth"),
    "editability": ("editability", "status", "ctpstatus", "changeable", "eligible", "eligibility"),
    # combined OEM columns (parsed specially, raw preserved)
    "color_trim": ("colortrim", "colourtrim", "colorinterior", "exteriorinterior", "color", "colour"),
    "packages": ("packagesoptions", "packages", "options", "packageoptions"),
    "accessories": ("accessories", "accessory", "accessorysummary"),
}

_DRIVETRAINS = ("2WD", "4WD", "AWD", "FWD", "RWD")


def _split_model(model_value):
    """"84317 QX60 LUXE FWD" → (model_code, model, trim, drivetrain, description). Leading all-digit token is the
    model code; the remainder is the human description (model + trim + drivetrain). Nothing is guessed — only
    what the source states is used."""
    toks = str(model_value or "").split()
    if not toks:
        return "", "", "", "", ""
    code, rest = "", toks
    if toks[0].isdigit():
        code, rest = toks[0], toks[1:]
    desc = " ".join(rest)
    model = rest[0] if rest else ""
    trim = drivetrain = ""
    body = rest[1:]
    if body and body[-1].upper() in _DRIVETRAINS:
        drivetrain = body[-1].upper()
        body = body[:-1]
    trim = " ".join(body).strip()
    return code, model, trim, drivetrain, desc


def _split_color_trim(value):
    """"KAD-K Graphite Shadow / Stone Gray" → (ext_code, int_code, ext_name, int_name), raw preserved by caller.
    "XKJ-P 2T Radiant White / Saddle Brown" → ("XKJ","P","2T Radiant White","Saddle Brown"). Format is
    `<EXT>-<INT> <ExtName> / <IntName>`; missing parts return "" (never guessed)."""
    v = " ".join(str(value or "").split())
    if not v:
        return "", "", "", ""
    codes, _, names = v.partition(" ")
    ext_code, _, int_code = codes.partition("-")
    ext_name, int_name = "", ""
    if "/" in names:
        left, _, right = names.partition("/")
        ext_name, int_name = left.strip(), right.strip()
    else:
        ext_name = names.strip()
    return ext_code.strip().upper(), int_code.strip().upper(), ext_name, int_name


def _norm_header(h):
    return "".join(ch for ch in str(h or "").strip().lower() if ch.isalnum())


def _norm_order(o):
    """Canonical order-number key for matching — lossless normalization only: trim whitespace, drop an Excel
    leading-apostrophe text marker, uppercase, and strip hidden/punctuation noise while keeping alphanumerics
    and -_/. Never fuzzy (no character deletion until something matches)."""
    s = str(o or "").strip().upper()
    if s.startswith("'"):
        s = s[1:]
    return "".join(ch for ch in s if ch.isalnum() or ch in "-_/")


def _looks_like_html(text):
    head = (text or "")[:4096].lower()
    return ("<table" in text.lower()) or ("<tr" in head) or head.lstrip().startswith("<!doctype html") \
        or head.lstrip().startswith("<html") or ("</td>" in head)


def parse_ctp_file(filename, data):
    """Parse one uploaded CTP file into a list of normalized-header dict rows. Detects the format by CONTENT
    signature (not just extension), so an OEM export saved as `.xls` that is really an HTML table still parses:
      * ZIP signature (PK) / .xlsx → stdlib XLSX;
      * HTML table markup (common for OEM `.xls` exports) → stdlib HTML-table parse;
      * otherwise CSV/TSV.
    Returns [] for an empty/unreadable file — never raises, never fabricates rows."""
    try:
        is_bytes = isinstance(data, (bytes, bytearray))
        # XLSX / zip by magic bytes or extension
        if (is_bytes and bytes(data[:2]) == b"PK") or (filename or "").lower().endswith(".xlsx"):
            return _parse_xlsx_rows(data)
        text = data.decode("utf-8", "ignore") if is_bytes else str(data)
        if _looks_like_html(text):
            return _parse_html_table(text)
        delim = "\t" if ((filename or "").lower().endswith(".tsv")
                         or ("\t" in text.splitlines()[0] if text.splitlines() else False)) else ","
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


def _parse_html_table(text):
    """Parse an HTML document/table (the natural format of many OEM `.xls` exports) into normalized-header dict
    rows. Uses the stdlib HTML parser; takes the widest table (most columns) as the data table; first row with
    cells is the header. Cell text is whitespace-collapsed and HTML entities are decoded. No source text lost —
    every column is preserved under its normalized header key."""
    from html.parser import HTMLParser

    class _T(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tables = []      # list of tables; each a list of rows; each row a list of cell strings
            self._row = None
            self._cell = None
            self._buf = []

        def handle_starttag(self, tag, attrs):
            t = tag.lower()
            if t == "table":
                self.tables.append([])
            elif t == "tr":
                self._row = []
            elif t in ("td", "th"):
                self._cell = []
                self._buf = []

        def handle_data(self, d):
            if self._cell is not None:
                self._buf.append(d)

        def handle_endtag(self, tag):
            t = tag.lower()
            if t in ("td", "th") and self._cell is not None:
                self._row.append(" ".join("".join(self._buf).split()))
                self._cell = None
            elif t == "tr" and self._row is not None:
                if self.tables:
                    self.tables[-1].append(self._row)
                self._row = None
            elif t == "br" and self._cell is not None:
                self._buf.append(" ")

    p = _T()
    p.feed(text)
    tables = [t for t in p.tables if any(r for r in t)]
    if not tables:
        return []
    table = max(tables, key=lambda t: max((len(r) for r in t), default=0))   # widest = the data table
    data_rows = [r for r in table if any(str(c).strip() for c in r)]
    if not data_rows:
        return []
    header = [_norm_header(h) for h in data_rows[0]]
    out = []
    for raw in data_rows[1:]:
        if not any(str(c).strip() for c in raw):
            continue
        out.append({header[i]: (str(raw[i]).strip() if i < len(raw) else "") for i in range(len(header))})
    return out


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
    exterior_name: str = ""
    interior_name: str = ""
    trim: str = ""
    drivetrain: str = ""
    description: str = ""
    packages: str = ""
    accessories: str = ""
    arrival_month: str = ""
    editability: str = ""
    color_trim_raw: str = ""
    source_file: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def key(self):
        return (self.order_number or "").strip().upper() or (self.vin or "").strip().upper()


def _valid_order_signature(order):
    """A real OEM order number (e.g. `TK76329`) is a single alphanumeric token — no spaces, no `=`, not a
    legend/footer marker (`*`, `C=Customer Order`). Reusable, not hard-coded to `TK`: it rejects obvious
    non-order text while accepting any compact alphanumeric order id."""
    o = str(order or "").strip()
    if not o or o.startswith("*") or "=" in o or " " in o or "\t" in o:
        return False
    if not any(ch.isdigit() for ch in o):        # a real order id carries digits; pure words are legend text
        return False
    return 2 <= len(o) <= 20 and all(ch.isalnum() or ch in "-_/" for ch in o)


def _is_legend_row(row):
    """Detect a legend / footer / note row (e.g. "* C=Customer Order") so it never becomes a Candidate."""
    joined = " ".join(str(v) for v in row.values()).strip().lower()
    if not joined:
        return True
    return joined.startswith("*") or "=customerorder" in joined.replace(" ", "") \
        or joined.startswith("legend") or joined.startswith("note")


def to_candidate(row, *, source_file=""):
    """Map a normalized-header row to a Candidate — but ONLY when the row carries a genuine vehicle-order
    signature: a valid Order # (or VIN) AND vehicle-identity evidence (model or model code). Legend/footer/note
    rows (e.g. "* C=Customer Order") are rejected so they never inflate the candidate count, enter reconciliation
    or receive a recommendation. Raw source is always preserved on the Candidate. Returns None for a non-order
    row. Nothing is inferred — the OEM 'Model' and 'Color/Trim' columns are split into their real parts."""
    if _is_legend_row(row):
        return None

    def pick(field_name):
        for a in _ALIASES[field_name]:
            if a in row and str(row[a]).strip():
                return str(row[a]).strip()
        return ""

    order_number, vin = pick("order_number"), pick("vin").upper()

    model = pick("model")
    model_code = pick("model_code")
    trim, drivetrain, description = pick("trim"), pick("drivetrain"), pick("description")
    # a Model column that carries the order code + human words ("84317 QX60 LUXE FWD")
    if model and (model_code == "" or trim == "" or drivetrain == ""):
        m_code, m_model, m_trim, m_drive, m_desc = _split_model(model)
        model_code = model_code or m_code
        if m_code or len(model.split()) > 1:
            model = m_model or model
            description = description or m_desc
            trim = trim or m_trim
            drivetrain = drivetrain or m_drive

    # qualification: a reconciliation key AND vehicle identity — else this is not a vehicle order
    has_key = _valid_order_signature(order_number) or (len(vin) >= 8 and vin.isalnum())
    has_vehicle = bool(model or model_code)
    if not (has_key and has_vehicle):
        return None

    exterior, interior = pick("exterior").upper(), pick("interior").upper()
    exterior_name = interior_name = ""
    color_trim_raw = pick("color_trim")
    if color_trim_raw and (not exterior or not interior):
        ec, ic, en, iname = _split_color_trim(color_trim_raw)
        exterior, interior = exterior or ec, interior or ic
        exterior_name, interior_name = en, iname

    return Candidate(order_number=order_number, vin=vin, model=model, model_code=model_code,
                     exterior=exterior, interior=interior, exterior_name=exterior_name, interior_name=interior_name,
                     trim=trim, drivetrain=drivetrain, description=description, packages=pick("packages"),
                     accessories=pick("accessories"), arrival_month=pick("arrival_month"),
                     editability=pick("editability"), color_trim_raw=color_trim_raw, source_file=source_file,
                     raw=dict(row))


@dataclass
class Reconciled:
    candidate: Candidate
    status: str                          # MATCHED / UNMATCHED / CONFLICT / AMBIGUOUS
    pipeline: Optional[dict] = None      # matched pipeline row (only when MATCHED)
    detail: str = ""                     # plain-English reconciliation detail
    match_method: str = ""               # "order#" / "vin" — for proof/audit
    audit: dict = field(default_factory=dict)


def reconcile(candidates, pipeline_rows):
    """Match each candidate to the CURRENT pipeline. Match-key hierarchy: (1) exact normalized Order #,
    (2) exact VIN; when both exist they must resolve to the SAME pipeline unit. Never fuzzy-matches on model/
    colour/ETA, never creates pipeline rows. Ambiguity (an order# or VIN mapping to more than one pipeline unit)
    is AMBIGUOUS, not a guess. Every result carries the attempted keys for proof/audit."""
    by_order, by_vin = {}, {}
    for p in pipeline_rows or []:
        o = _norm_order(p.get("order_number"))
        v = (p.get("vin") or "").strip().upper()
        if o:
            by_order.setdefault(o, []).append(p)
        if v:
            by_vin.setdefault(v, []).append(p)
    out = []
    for c in candidates:
        o, v = _norm_order(c.order_number), (c.vin or "").strip().upper()
        audit = {"ctp_order": c.order_number, "ctp_order_normalized": o, "ctp_vin": v or "none",
                 "pipeline_units": len(pipeline_rows or [])}
        po, pv = by_order.get(o, []), by_vin.get(v, []) if v else []
        audit["order_match_count"], audit["vin_match_count"] = len(po), len(pv)
        if o and len(po) > 1:
            out.append(Reconciled(c, AMBIGUOUS, None, f"more than one Pipeline unit matches order {c.order_number}",
                                  audit=audit))
            continue
        if v and len(pv) > 1:
            out.append(Reconciled(c, AMBIGUOUS, None, f"more than one Pipeline unit matches VIN {v}", audit=audit))
            continue
        p_order = po[0] if po else None
        p_vin = pv[0] if pv else None
        if p_order is not None and p_vin is not None and p_order is not p_vin:
            out.append(Reconciled(c, CONFLICT, None,
                       f"the CTP file and Pipeline disagree on this unit (order {c.order_number} and VIN {v} "
                       f"point to different Pipeline units)", audit=audit))
            continue
        if p_order is not None:
            pv_of = (p_order.get("vin") or "").strip().upper()
            if v and pv_of and v != pv_of:
                out.append(Reconciled(c, CONFLICT, None,
                           f"the CTP file and Pipeline disagree on the VIN for order {c.order_number} "
                           f"(CTP {v} vs Pipeline {pv_of})", audit={**audit, "pipeline_vin": pv_of}))
                continue
            out.append(Reconciled(c, MATCHED, p_order, "matched by order #", "order#", audit))
            continue
        if p_vin is not None:
            out.append(Reconciled(c, MATCHED, p_vin, "matched by VIN", "vin", audit))
            continue
        out.append(Reconciled(c, UNMATCHED, None,
                   f"{c.order_number or v} is not in the Pipeline file currently loaded", audit=audit))
    return out


@dataclass
class Recommendation:
    """One order's decision (spec 03 contract). KEEP/CHANGE are business decisions reached only after a matched,
    evaluable order; any reconciliation or essential-fact gap is CANT_EVALUATE — never a silent KEEP."""
    decision_state: str                  # KEEP | CHANGE | CANT_EVALUATE
    order_number: str = ""
    vin: str = ""
    reconciliation: str = ""
    current_line: str = ""               # "QX60 LUXE FWD"
    current_colors: str = ""             # "Graphite Shadow / Stone Gray"
    current_codes: str = ""              # "84317 • KAD-K"
    proposed_line: str = ""
    proposed_colors: str = ""
    reason_plain: str = ""
    operator_action_plain: str = ""
    blocking_reason: str = ""
    proof: dict = field(default_factory=dict)
    source_provenance: dict = field(default_factory=dict)
    evaluation_timestamp: str = ""
    candidate: Optional[Candidate] = None
    proposed_combination_id: str = ""    # the target combination for a CHANGE (so the operator can reject it)
    rejected_targets: list = field(default_factory=list)   # OEM 'not available' marks for THIS order/context
    confirmed: bool = False              # this CHANGE is an operator-confirmed OEM execution (locked)


def _model_of(label):
    return (label or "").split(" ", 1)[0]


def _norm_trim(v):
    """Normalized GOVERNED trim identity for the same-trim rule: upper-cased, whitespace-collapsed, or '' when
    absent. Trim MUST be resolved by the caller from the governed model-code family / translation identity (the
    Candidate's authoritative trim or the board target's governed trim) — it is NEVER positionally sliced out of
    a free-text description, which would read 'AUTO' out of 'QX60 AUTOGRAPH AWD SUV AUTO' and drop every real
    AUTOGRAPH alternative. '' means unresolved and the same-trim rule GATES rather than guessing."""
    return " ".join(str(v or "").split()).upper()


def order_key(order_number, vin):
    """Stable per-order/context key (normalized Order #, else VIN). It keys the 'Not available configuration'
    store so each mark keeps its provenance — which order first hit the OEM rejection — but that provenance no
    longer scopes applicability: a Production Restriction excludes the configuration for the whole active CTP
    session for that model (see `evaluate`), not just the order that happened to be edited."""
    return _norm_order(order_number) or (vin or "").strip().upper()


def human_build(candidate):
    """(line, colors, codes) for a candidate's current build, from the source's OWN human wording (exterior/
    interior equally first-class). "QX60 LUXE FWD" / "Graphite Shadow / Stone Gray" / "84317 • KAD-K"."""
    line = " ".join(x for x in (candidate.model, candidate.trim, candidate.drivetrain) if x)
    ext, it = candidate.exterior_name or candidate.exterior, candidate.interior_name or candidate.interior
    colors = " / ".join(x for x in (ext, it) if x)
    code = candidate.model_code
    cc = "-".join(x for x in (candidate.exterior, candidate.interior) if x)
    codes = " • ".join(x for x in (code, cc) if x)
    return line, colors, codes


def evaluate(reconciled, board, *, now="", infeasible=None, confirmed=None, session_rules=None):
    """Turn reconciled candidates into business Recommendations via the state machine:
        PARSED → RECONCILED → EVALUABLE → KEEP | CHANGE   (any earlier gap → CANT_EVALUATE)

    `board` is keyed by combination_id → {canonical, line, colors, model, excess, short}: `excess` the certified
    over-supply, `short` the certified need. Only a MATCHED order with the essentials (a board position for its
    combination AND known arrival timing) is EVALUABLE. Evaluated together, sequentially, against a disposable
    copy of the board so the horizon re-runs after each CHANGE. CHANGE re-specifies the slot to a genuinely
    certified-short combination OF THE SAME MODEL — never fabricated, never nearest-code, never colour
    preference. KEEP only after a completed evaluation found no superior target.

    `infeasible` is the operator's 'Not available configuration' feedback, keyed by order_key(order#, VIN) →
    list of records {target, target_canonical, reason, note, at}. Applicability is SESSION-scoped, not
    order-scoped: the union of every marked configuration (by governed canonical build identity — the board
    combination_id and its canonical) is excluded from the feasible candidate set of EVERY remaining unconfirmed
    order of that model, so a configuration the OEM rejected on one order is never re-recommended on the next.
    The evaluator then returns the next-best certified-short target, or KEEP (best available outcome) once every
    superior alternative is session-excluded. Each mark keeps its order provenance for the history trail, but
    that provenance does not narrow where the exclusion applies. The board itself is never mutated by a mark —
    the change was never executed — so the sequence simply re-runs.

    `confirmed` is the operator's executed-change lock, keyed by order_key → {target, at, actor}. A confirmed
    order is a FIXED execution constraint for the rest of the session: it is applied to the working board FIRST
    (source excess −1, target short −1), it is never re-optimized or reassigned, a later OEM rejection cannot
    undo it, and every other order evaluates against that post-confirmation state. The certified board rows are
    never mutated — only this in-memory working copy is.

    `session_rules` is a SEPARATE, broader OEM production rule Elite LEARNED this session (distinct from the exact
    configuration exclusions in `infeasible`). The one modelled here is {"same_trim_only": {"active": True, ...}}:
    when active, a CHANGE target must carry the SAME governed trim as the order's current build — the evaluator
    still optimizes freely within that trim (model code / exterior / interior), only cross-trim targets are
    removed. It is session/model-scoped, cleared by reset / clear-session, and never permanent product logic."""
    infeasible = infeasible or {}
    confirmed = confirmed or {}
    session_rules = session_rules or {}
    same_trim_only = bool((session_rules.get("same_trim_only") or {}).get("active"))
    state = {cid: {"excess": int(b.get("excess", 0) or 0), "short": int(b.get("short", 0) or 0),
                   "canonical": b.get("canonical", cid), "line": b.get("line", ""), "colors": b.get("colors", ""),
                   "model": (b.get("model") or _model_of(b.get("line", ""))).upper(),
                   "trim": _norm_trim(b.get("trim", "")),    # AUTHORITATIVE governed trim supplied by the caller
                   # supply-only: real supply, NO accepted demand basis (Need/Excess not asserted). The order's
                   # own unit is redirectable to a real governed shortage, but its build is never called "needed".
                   "supply_only": bool(b.get("supply_only")),
                   "color_complete": bool(b.get("color_complete", True))}   # both colour dims resolved (or gate)
             for cid, b in (board or {}).items()}            # (model-code family / translation) — never line-sliced

    def short_targets(model):
        return sorted([(cid, st) for cid, st in state.items() if st["short"] > 0 and st["model"] == model],
                      key=lambda t: (-t[1]["short"], t[1]["canonical"]))

    # PRE-PASS: apply every confirmed (locked) execution to the working board before any decision, so both the
    # confirmed order and all other orders evaluate against the post-confirmation state. Certified board rows are
    # untouched — this only decrements the in-memory working copy.
    locked = {}                                     # order_key -> {"target": tcid, "source_cid": scid}
    for rc in reconciled:
        if rc.status != MATCHED or rc.pipeline is None:
            continue
        okey = order_key(rc.candidate.order_number, rc.candidate.vin)
        conf = confirmed.get(okey)
        if not conf or okey in locked:
            continue
        scid = rc.pipeline.get("combination_id")
        spos = state.get(scid)
        if spos is None:
            continue                                # can't place the confirmed consumption without a board source
        tcid = conf.get("target")
        spos["excess"] -= 1                          # source combination stays reduced by the committed unit
        tgt = state.get(tcid)
        if tgt:
            tgt["short"] -= 1                        # confirmed target stays increased (its shortage consumed)
        locked[okey] = {"target": tcid, "source_cid": scid}

    # SESSION-level Production-Restriction exclusions. An OEM 'Not available configuration' mark is a
    # session/model/configuration exclusion, NOT an order-specific one: once a configuration is marked
    # unavailable on ANY order, it is unavailable for the whole active CTP session for that model. Build the
    # union of every mark across all orders, keyed by the governed canonical build identity (the board
    # combination_id AND its canonical form — the same normalization CTP planning uses). This set is applied to
    # every remaining unconfirmed order's candidate pool below. Per-order provenance (which order first caused
    # the OEM rejection) is preserved separately for the history trail; it does not scope applicability.
    session_banned = set()                          # match keys: combination_id and canonical build identity
    _banned_cfg = set()                             # distinct configurations, for honest counts
    for _marks in infeasible.values():
        for _m in (_marks or []):
            t, tc = _m.get("target"), _m.get("target_canonical")
            if t:
                session_banned.add(t)
            if tc:
                session_banned.add(tc)
            key = t or tc
            if key:
                _banned_cfg.add(key)
    session_ban_count = len(_banned_cfg)

    recs = []
    for rc in reconciled:
        c = rc.candidate
        line, colors, codes = human_build(c)
        prov = {"source_file": c.source_file, "reconciliation": rc.status, "match_method": rc.match_method,
                "audit": rc.audit}
        base = dict(order_number=c.order_number, vin=c.vin, reconciliation=rc.status, current_line=line,
                    current_colors=colors, current_codes=codes, source_provenance=prov,
                    evaluation_timestamp=now, candidate=c)

        # --- gate 1: reconciliation must be a clean single MATCH ---
        if rc.status != MATCHED or rc.pipeline is None:
            reason = {UNMATCHED: f"Can't evaluate — {rc.detail}.",
                      CONFLICT: f"Can't evaluate — {rc.detail}.",
                      AMBIGUOUS: f"Can't evaluate — {rc.detail}."}.get(rc.status, "Can't evaluate — unresolved.")
            recs.append(Recommendation(decision_state=CANT_EVALUATE, blocking_reason=rc.detail,
                        reason_plain=reason,
                        operator_action_plain="Update Pipeline or verify this order number.",
                        proof={"reconciliation": rc.status, **rc.audit}, **base))
            continue

        cid = rc.pipeline.get("combination_id")
        pos = state.get(cid)
        # --- gate 2: essential facts to compare the future position ---
        if pos is None:
            recs.append(Recommendation(decision_state=CANT_EVALUATE,
                        blocking_reason="no certified supply/demand position for this combination",
                        reason_plain="Can't evaluate — Elite doesn't have a current supply/demand position for "
                                     "this build yet.",
                        operator_action_plain="Refresh the plan / inventory, then re-check.",
                        proof={"combination_id": cid}, **base))
            continue
        if not (c.arrival_month or rc.pipeline.get("arrival_month")):
            recs.append(Recommendation(decision_state=CANT_EVALUATE,
                        blocking_reason="arrival timing missing",
                        reason_plain="Can't evaluate — arrival timing is missing, so Elite can't test the future "
                                     "inventory position.",
                        operator_action_plain="Add the production/ETA month for this order.",
                        proof={"combination_id": cid}, **base))
            continue

        # --- EVALUABLE ---
        okey = order_key(c.order_number, c.vin)
        # a CONFIRMED (locked) execution is fixed: emit its committed CHANGE as-is, never re-optimized and never
        # reassigned by a later OEM rejection. Its board consumption was already applied in the pre-pass.
        lk = locked.get(okey)
        if lk is not None:
            tgt = state.get(lk["target"], {})
            recs.append(Recommendation(decision_state=CHANGE, confirmed=True,
                        proposed_line=tgt.get("line", ""), proposed_colors=tgt.get("colors", ""),
                        proposed_combination_id=lk["target"],
                        reason_plain="Confirmed changed. This order's OEM change is executed and locked for this "
                                     "session; Elite holds the source and target position accordingly.",
                        operator_action_plain=f"{c.order_number or c.vin} is confirmed changed — no further action.",
                        proof={"confirmed": True, "source_combination": pos["canonical"],
                               "target_combination": tgt.get("canonical", lk["target"])}, **base))
            continue

        # 'Not available' feedback is a SESSION-level exclusion: a configuration marked unavailable on ANY order
        # is removed from the candidate pool of EVERY remaining unconfirmed order of this model (matched by the
        # governed canonical build identity — combination_id and its canonical). The board is unchanged; we
        # simply skip session-banned targets when choosing the next-best. `rejected` retains only THIS order's
        # own marks, so the per-order history trail still shows which order first caused each OEM rejection.
        rejected = list(infeasible.get(okey, []) or [])
        model = pos["model"] or (c.model or "").upper()
        # source trim comes from the AUTHORITATIVE governed identity: the source combination's governed board trim
        # (resolved from the model-code family, the same way target trims are — so they compare apples-to-apples),
        # falling back to the order's Candidate trim only if the board lacks it. Never a positional slice of the
        # display line (which would read 'AUTO' out of 'QX60 AUTOGRAPH AWD SUV AUTO').
        source_trim = pos.get("trim", "") or _norm_trim(getattr(c, "trim", ""))
        # same-trim rule is active but the governed trim can't be established -> GATE, never guess a trim.
        if same_trim_only and not source_trim:
            recs.append(Recommendation(decision_state=CANT_EVALUATE,
                        blocking_reason="governed trim unresolved for the same-trim rule",
                        reason_plain="Can't evaluate — the same-trim-only OEM rule is active, but Elite can't "
                                     "establish this order's governed trim from its model code. It won't guess a "
                                     "trim from the description.",
                        operator_action_plain="Confirm this order's model code / trim mapping, then re-check.",
                        proof={"same_trim_only": True, "current_combination": pos["canonical"],
                               "source_trim": ""}, **base))
            continue
        # A CHANGE redirects one redirectable unit from the source to a genuinely certified-short target. The
        # source is redirectable when it has certified excess OR when it is a SUPPLY-ONLY build (real supply, no
        # demand basis): that order's unit can be re-specified toward a real, demand-backed governed shortage.
        supply_only = bool(pos.get("supply_only"))
        all_targets = short_targets(model) if (pos["excess"] > 0 or supply_only) else []

        # Two INDEPENDENT session restrictions, applied together:
        #   (1) exact-configuration exclusion — the governed build was OEM-rejected (session_banned);
        #   (2) same-trim-only — a broader LEARNED production rule: a CHANGE target must carry the same governed
        #       trim as the order's current build (cross-trim swaps are not permitted this CTP). Within-trim
        #       optimization (model code / exterior / interior) is untouched.
        def _eligible_target(tcid, st):
            if tcid in session_banned or st.get("canonical") in session_banned:
                return False                                  # (1) exact configuration rejected
            if same_trim_only and source_trim and st.get("trim", "") != source_trim:
                return False                                  # (2) cross-trim target removed by the learned rule
            if not st.get("color_complete", True):
                return False                                  # (3) incomplete config (missing exterior/interior
                                                              #     identity) — gate, never present a partial change
            return True
        eligible = [(tcid, st) for tcid, st in all_targets if _eligible_target(tcid, st)]
        cross_trim_blocked = bool(same_trim_only and source_trim and all_targets and not eligible
                                  and any(st.get("trim", "") != source_trim for _t, st in all_targets))
        if (pos["excess"] <= 0 and not supply_only) or not eligible:
            exhausted = bool(all_targets and not eligible)   # had superior targets, but all restricted away
            if supply_only:
                # Never call a no-demand-basis build "needed"; keep it only because nothing better is governed-short.
                reason = ("Keep it — this build has no established demand basis, but no eligible alternative has a "
                          "stronger governed Need position. Leave the existing order unchanged rather than "
                          "inventing demand.")
            elif pos["excess"] <= 0:
                reason = ("Keep it. By arrival this build is still at or below its needed supply, and no eligible "
                          "alternative improves the future position.")
            elif cross_trim_blocked:
                reason = (f"Keep it — best available outcome. This CTP session is same-trim only (a learned OEM "
                          f"rule), so only another {source_trim} configuration could be substituted, and none is "
                          f"available or superior.")
            elif exhausted:
                reason = ("Keep it — best available outcome. Every superior configuration for this slot was marked "
                          "not available by the OEM.")
            else:
                reason = "Keep it. Elite found no better proven use of this production slot."
            recs.append(Recommendation(decision_state=KEEP, reason_plain=reason,
                        operator_action_plain=f"Leave {c.order_number or c.vin} exactly as it is.",
                        proof={"current_combination": pos["canonical"], "current_excess": pos["excess"],
                               "eligible_targets": len(eligible), "targets_marked_unavailable": session_ban_count,
                               "same_trim_only": same_trim_only, "source_trim": source_trim,
                               "best_available_after_exhaustion": exhausted},
                        rejected_targets=rejected, **base))
            continue

        # proven superior replacement: re-specify one unit → a certified-short target; re-run the horizon.
        tcid, tgt = eligible[0]
        before = {"source_excess": pos["excess"], "target_short": tgt["short"]}
        if not supply_only:
            pos["excess"] -= 1                            # a demand-certified excess source loses one surplus unit
        tgt["short"] -= 1                                 # the certified shortage is consumed (both source kinds)
        if supply_only:
            change_reason = (f"Change it to {tgt['colors'] or tgt['line']}. This build has no established demand "
                             f"basis; {tgt['colors'] or tgt['line']} has a governed shortage supported by "
                             f"accepted demand evidence.")
        else:
            change_reason = (f"Change it to {tgt['colors'] or tgt['line']}. Elite projects enough "
                             f"{colors or line} supply by arrival, while {tgt['colors'] or tgt['line']} "
                             f"remains short.")
        recs.append(Recommendation(decision_state=CHANGE, proposed_line=tgt["line"], proposed_colors=tgt["colors"],
                    proposed_combination_id=tcid,
                    reason_plain=change_reason,
                    operator_action_plain=(f"In the Infiniti CTP portal, change {c.order_number or c.vin} to "
                                           f"{tgt['line']} {tgt['colors']}".strip()),
                    proof={"source_combination": pos["canonical"], "target_combination": tgt["canonical"],
                           "before": before, "after": {"source_excess": pos["excess"], "target_short": tgt["short"]},
                           "targets_marked_unavailable": session_ban_count,
                           "same_trim_only": same_trim_only, "source_trim": source_trim},
                    rejected_targets=rejected, **base))
    return recs


def summarize(recommendations):
    """Business-language session counts for the top summary. KEEP/CHANGE only count evaluated orders; unresolved
    orders count as 'need attention', never KEEP."""
    keep = sum(1 for r in recommendations if r.decision_state == KEEP)
    change = sum(1 for r in recommendations if r.decision_state == CHANGE)
    attention = sum(1 for r in recommendations if r.decision_state == CANT_EVALUATE)
    return {"orders": len(recommendations), "ready": keep + change, "keep": keep, "change": change,
            "attention": attention}
