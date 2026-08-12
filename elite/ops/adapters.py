"""Source adapter layer over Phase 2 ingestion.

An adapter turns a real-source payload (delimited file, spreadsheet export, JSON payload, or a governed
manual input) into the Phase 2 CANONICAL ingestion contract: a list of plain-dict rows + preserved raw
text + the ingestion parameters (source, scope, entity kind, fact type, snapshot claim, effective time).

Adapters ONLY parse. They never write domain results, never resolve identity, and never compute Demand /
Need / economics — that is the job of Phase 2 ingestion and the Phase 4-9 domains. Source-specific parsing
stays strictly separate from domain interpretation. Schema detection is explicit; an unsupported or
structurally invalid payload fails safely (ValidationError) at the VALIDATING stage. Encoding, delimiter,
date, decimal, currency, and blank-value handling are deterministic. Every produced row keeps its original
source location (file line) for traceability. The adapter version is recorded on every import run.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field

from ..errors import ValidationError
from .contracts import SourceContract

ADAPTER_VERSION = 1     # bump when a transform changes; prior import history is preserved


@dataclass
class AdapterResult:
    contract_key: str
    adapter_key: str
    adapter_version: int
    rows: list                       # list[dict[str, str]] — canonical Phase 2 rows
    raw_text: str                    # preserved raw source text (never discarded)
    row_locations: dict = field(default_factory=dict)   # row index -> {"line": n}
    transforms: list = field(default_factory=list)      # documented, testable transforms applied
    detected_schema: dict = field(default_factory=dict) # {"header": [...], "extra": [...]}
    stock_identity: bool = True      # False -> stock_number is not an identity/dedup key for this source

    def ingest_kwargs(self, *, source_id, scope, entity_kind, fact_type, claimed_snapshot,
                      effective_time=None, correlation_id=None, correction_of=None):
        return dict(source_id=source_id, profile_version=1, rows=self.rows, raw_text=self.raw_text,
                    scope=scope, entity_kind=entity_kind, fact_type=fact_type or None,
                    claimed_snapshot=claimed_snapshot, effective_time=effective_time,
                    correlation_id=correlation_id, correction_of=correction_of,
                    stock_identity=self.stock_identity)


def _decode(payload) -> str:
    """Deterministic decoding. Accepts str or bytes; bytes must be UTF-8 (BOM tolerated). Invalid
    encoding fails safely rather than silently mangling data."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        for enc in ("utf-8-sig", "utf-8"):
            try:
                return bytes(payload).decode(enc)
            except UnicodeDecodeError:
                continue
        raise ValidationError(message="The file is not valid UTF-8 text.",
                              technical_detail="invalid_encoding: could not decode payload as UTF-8")
    raise ValidationError(technical_detail=f"unsupported payload type {type(payload).__name__}")


_CURRENCY = str.maketrans("", "", "$,")


def _clean_numeric(value, numeric_fields, key):
    """Deterministic currency/decimal cleanup for declared numeric fields ONLY. Blank stays blank and
    '0' stays '0' — the adapter never coerces blank->zero or missing->zero (Phase 2 owns sentinels)."""
    if key not in numeric_fields or not isinstance(value, str):
        return value
    v = value.strip()
    if v == "":
        return value
    cleaned = v.translate(_CURRENCY)
    return cleaned


def _detect_and_check(header, contract: SourceContract):
    header_set = set(header)
    known = set(contract.required_fields) | set(contract.optional_fields) | set(contract.identity_keys)
    missing = [f for f in contract.required_fields if f not in header_set]
    if missing:
        raise ValidationError(message="The file is missing a required column.",
                              technical_detail=f"missing_required_column: {sorted(missing)}")
    if header and header_set.isdisjoint(known):
        raise ValidationError(message="The file schema is not recognized for this source.",
                              technical_detail=f"unsupported_schema: header={header}")
    extra = [h for h in header if h not in known]
    return {"header": list(header), "extra": extra}


def _apply_header_aliases(header, contract: SourceContract):
    """Map real source headers to canonical field names via the contract's declared aliases. Unmapped
    headers pass through unchanged; original values are preserved (raw_text keeps the source verbatim)."""
    aliases = getattr(contract, "header_aliases", None) or {}
    if not aliases:
        return list(header)
    return [aliases.get(h, aliases.get(h.strip() if isinstance(h, str) else h, h)) for h in header]


def _stock_identity(contract: SourceContract):
    return getattr(contract, "stock_number_is_identity", True)


def parse_delimited(payload, contract: SourceContract, *, delimiter=None):
    text = _decode(payload)
    delim = delimiter or ("\t" if contract.file_kind == "tsv" else ",")
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        all_rows = list(reader)
    except csv.Error as e:
        raise ValidationError(message="The file could not be parsed.",
                              technical_detail=f"malformed_delimited: {e}")
    if not all_rows:
        raise ValidationError(message="The file is empty.", technical_detail="empty_file")
    header = _apply_header_aliases([h.strip() for h in all_rows[0]], contract)
    detected = _detect_and_check(header, contract)
    numeric_fields = set(contract.units.keys())
    rows, locations, malformed = [], {}, 0
    for line_no, raw in enumerate(all_rows[1:], start=2):
        if len(raw) != len(header):
            malformed += 1
            continue                         # column-count mismatch: malformed row, excluded + counted
        rec = {header[i]: _clean_numeric(raw[i].strip() if isinstance(raw[i], str) else raw[i],
                                         numeric_fields, header[i])
               for i in range(len(header))}
        idx = len(rows)
        rows[idx:idx] = [rec]
        locations[idx] = {"line": line_no}
    data_lines = len(all_rows) - 1
    if data_lines > 0 and malformed == data_lines:
        raise ValidationError(message="The file rows do not match the header (malformed delimiter).",
                              technical_detail="malformed_delimiter: all data rows mismatched header width")
    transforms = ["strip_whitespace", "currency_decimal_cleanup(declared numeric fields)"]
    if malformed:
        transforms.append(f"excluded_malformed_rows={malformed}")
    return AdapterResult(contract_key=contract.key,
                         adapter_key=f"{contract.key}.{contract.file_kind}",
                         adapter_version=ADAPTER_VERSION, rows=rows, raw_text=text,
                         row_locations=locations, transforms=transforms, detected_schema=detected,
                         stock_identity=_stock_identity(contract))


def parse_json(payload, contract: SourceContract):
    text = _decode(payload)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(message="The JSON payload is not valid.",
                              technical_detail=f"invalid_json: {e}")
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValidationError(message="The JSON payload must be an array of records.",
                              technical_detail="unsupported_schema: json is not a list of objects")
    header = []
    for r in data:
        for k in r.keys():
            if k not in header:
                header.append(k)
    header = _apply_header_aliases(header, contract)
    detected = _detect_and_check(header, contract)
    aliases = getattr(contract, "header_aliases", None) or {}
    numeric_fields = set(contract.units.keys())
    rows, locations = [], {}
    for i, r in enumerate(data):
        rec = {aliases.get(k, k): _clean_numeric(str(v) if v is not None else "", numeric_fields,
                                                 aliases.get(k, k)) for k, v in r.items()}
        rows.append(rec)
        locations[i] = {"line": i + 1}
    return AdapterResult(contract_key=contract.key, adapter_key=f"{contract.key}.json",
                         adapter_version=ADAPTER_VERSION, rows=rows, raw_text=text,
                         row_locations=locations, transforms=["json_object_to_row"],
                         detected_schema=detected, stock_identity=_stock_identity(contract))


def parse_manual(rows, contract: SourceContract):
    """Governed manual operator input where no automated source exists. Rows are already dicts; the
    adapter still validates the schema and preserves the input verbatim as raw text."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValidationError(technical_detail="manual input must be a list of dict rows")
    header = []
    for r in rows:
        for k in r.keys():
            if k not in header:
                header.append(k)
    detected = _detect_and_check(header, contract)
    raw = json.dumps(rows, sort_keys=True)
    canon = [{k: (str(v) if v is not None else "") for k, v in r.items()} for r in rows]
    locations = {i: {"line": i + 1} for i in range(len(canon))}
    return AdapterResult(contract_key=contract.key, adapter_key=f"{contract.key}.manual",
                         adapter_version=ADAPTER_VERSION, rows=canon, raw_text=raw,
                         row_locations=locations, transforms=["manual_governed_input"],
                         detected_schema=detected, stock_identity=_stock_identity(contract))


# ---- XLSX (stdlib-only: zipfile + ElementTree; read-only, deterministic) --------------------------
def _xl_local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def _xl_col_index(ref):
    letters = "".join(c for c in (ref or "") if c.isalpha())
    idx = 0
    for c in letters:
        idx = idx * 26 + (ord(c.upper()) - 64)
    return idx - 1 if idx else 0


def _xl_num_text(v):
    """Deterministic text for a numeric cell: integral -> no decimal; else shortest round-trippable float."""
    if v is None:
        return ""
    s = str(v).strip()
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f == int(f) else repr(f)


def parse_xlsx(payload, contract: SourceContract, *, sheet=None):
    """Deterministically parse a real .xlsx workbook using only the standard library. Reads shared strings,
    resolves the requested worksheet (contract.sheet, else first), and produces rectangular canonical rows.
    A non-workbook / corrupt file fails safely at VALIDATING (never a crash)."""
    import zipfile
    from xml.etree import ElementTree as ET
    if isinstance(payload, str):
        payload = payload.encode("utf-8", "ignore")
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(payload)))
    except (zipfile.BadZipFile, Exception) as e:   # noqa: BLE001 - any container failure is a safe reject
        raise ValidationError(message="The workbook could not be read.",
                              technical_detail=f"not_a_valid_xlsx: {type(e).__name__}: {e}")
    names = set(zf.namelist())

    shared = []
    if "xl/sharedStrings.xml" in names:
        sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in list(sroot):
            if _xl_local(si.tag) != "si":
                continue
            shared.append("".join(t.text or "" for t in si.iter() if _xl_local(t.tag) == "t"))

    sheets = []
    if "xl/workbook.xml" in names:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        for el in wb.iter():
            if _xl_local(el.tag) == "sheet":
                rid = next((v for k, v in el.attrib.items() if _xl_local(k) == "id"), None)
                sheets.append((el.get("name"), rid))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")):
            rels[rel.get("Id")] = rel.get("Target")

    want = sheet or getattr(contract, "sheet", "") or ""
    chosen = next((s for s in sheets if s[0] == want), None) if want else None
    if chosen is None and sheets:
        chosen = sheets[0]
    path = None
    if chosen is not None and chosen[1] in rels:
        tgt = rels[chosen[1]].lstrip("/")
        path = tgt if tgt in names else ("xl/" + tgt if ("xl/" + tgt) in names else None)
    if path is None:
        cands = sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        path = cands[0] if cands else None
    if path is None:
        raise ValidationError(message="The workbook has no worksheet.",
                              technical_detail="no_worksheet_found")

    sroot = ET.fromstring(zf.read(path))
    grid = []
    for row in sroot.iter():
        if _xl_local(row.tag) != "row":
            continue
        cells, maxc = {}, -1
        for ci_default, c in enumerate(list(row)):
            if _xl_local(c.tag) != "c":
                continue
            ref = c.get("r")
            ci = _xl_col_index(ref) if ref else ci_default
            t = c.get("t")
            vtext, istext = None, None
            for ch in c:
                lt = _xl_local(ch.tag)
                if lt == "v":
                    vtext = ch.text
                elif lt == "is":
                    istext = "".join(tt.text or "" for tt in ch.iter() if _xl_local(tt.tag) == "t")
            if t == "s":
                try:
                    val = shared[int(vtext)] if vtext is not None else ""
                except (ValueError, IndexError):
                    val = ""
            elif t == "inlineStr":
                val = istext or ""
            elif t == "str":
                val = vtext or ""
            elif t == "b":
                val = "TRUE" if vtext == "1" else "FALSE"
            else:
                val = _xl_num_text(vtext) if vtext is not None else ""
            cells[ci] = val
            maxc = max(maxc, ci)
        grid.append([cells.get(i, "") for i in range(maxc + 1)])

    if not grid or not any(any(str(c).strip() for c in r) for r in grid):
        raise ValidationError(message="The workbook is empty.", technical_detail="empty_workbook")
    header = _apply_header_aliases([h.strip() if isinstance(h, str) else h for h in grid[0]], contract)
    detected = _detect_and_check(header, contract)
    numeric_fields = set(contract.units.keys())
    width = len(header)
    rows, locations, malformed = [], {}, 0
    for line_no, raw in enumerate(grid[1:], start=2):
        if not any(str(c).strip() for c in raw):
            continue                                      # skip fully-blank trailing rows
        if len(raw) < width:
            raw = raw + [""] * (width - len(raw))
        elif len(raw) > width:
            if any(str(x).strip() for x in raw[width:]):
                malformed += 1
                continue
            raw = raw[:width]
        rec = {header[i]: _clean_numeric(raw[i].strip() if isinstance(raw[i], str) else raw[i],
                                         numeric_fields, header[i]) for i in range(width)}
        idx = len(rows)
        rows[idx:idx] = [rec]
        locations[idx] = {"line": line_no}
    data_lines = sum(1 for r in grid[1:] if any(str(c).strip() for c in r))
    if data_lines > 0 and malformed == data_lines:
        raise ValidationError(message="The workbook rows do not match the header.",
                              technical_detail="malformed_workbook: all rows mismatched header width")
    raw_text = "\n".join("\t".join(str(c) for c in r) for r in grid)   # deterministic lineage rendering
    transforms = ["xlsx_parse(zipfile+xml)", "header_alias", "strip_whitespace",
                  "currency_decimal_cleanup(declared numeric fields)"]
    if malformed:
        transforms.append(f"excluded_malformed_rows={malformed}")
    return AdapterResult(contract_key=contract.key, adapter_key=f"{contract.key}.xlsx",
                         adapter_version=ADAPTER_VERSION, rows=rows, raw_text=raw_text,
                         row_locations=locations, transforms=transforms, detected_schema=detected,
                         stock_identity=_stock_identity(contract))


def run_adapter(contract: SourceContract, payload, *, file_kind=None):
    """Dispatch to the correct parser for the contract's declared file kind (or an override)."""
    kind = file_kind or contract.file_kind
    if kind in ("csv", "tsv", "txt", "spreadsheet_export"):
        delim = "\t" if kind == "tsv" else None
        result = parse_delimited(payload, contract, delimiter=delim)
    elif kind == "xlsx":
        result = parse_xlsx(payload, contract)
    elif kind == "json":
        result = parse_json(payload, contract)
    elif kind == "manual":
        result = parse_manual(payload, contract)
    else:
        raise ValidationError(message="Unsupported file type for this source.",
                              technical_detail=f"unsupported_file_kind: {kind}")
    # Lifecycle-dependent Serial: this phase never classifies it (order number vs VIN suffix cannot be
    # proven from the row alone), so every row carries serial_semantic="unknown" and Serial is preserved
    # verbatim — no identity is created from it.
    if getattr(contract, "serial_lifecycle", False):
        for rec in result.rows:
            rec["serial_semantic"] = "unknown"
        if "serial_semantic" not in result.transforms:
            result.transforms.append("serial_semantic=unknown(deferred classification)")
    return result
