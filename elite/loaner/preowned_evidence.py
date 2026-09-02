"""Source-backed preowned-market evidence for Service Loaner.

This module is intentionally READ ONLY. It does not manufacture economic values and
does not call the certified Ideal Mix optimizer. It answers a narrower question:

    What does this dealership's accepted preowned-sales history say about the resale
    absorption of the models physically present in the active Service Loaner fleet?

Active-fleet model identity comes from the latest completed authoritative
Service-Loaner snapshot. Historical demand comes from the latest completed
retail_history schema-v3 batch. Only accepted observations are used.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import statistics

# A model-year needs at least this many usable Days-to-Sell observations before its absorption is shown as
# a defensible comparison rather than an under-sampled hint.
MIN_MODEL_YEAR_DTS = 8


@dataclass(frozen=True)
class DtsDistribution:
    """Shape of the historical Days-to-Sell sample (source values only; nothing invented)."""
    count: int
    minimum: float | None
    p25: float | None
    median: float | None
    p75: float | None
    maximum: float | None


def _distribution(values):
    vals = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))
    if not vals:
        return DtsDistribution(0, None, None, None, None, None)
    med = float(statistics.median(vals))
    if len(vals) >= 2:
        q1, _q2, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    else:
        q1 = q3 = float(vals[0])
    return DtsDistribution(len(vals), float(vals[0]), float(q1), med, float(q3), float(vals[-1]))


@dataclass(frozen=True)
class ModelEvidence:
    model: str
    active_units: int
    sales_count: int
    numeric_dts_count: int
    median_dts: float | None
    distribution: DtsDistribution | None = None


@dataclass(frozen=True)
class ModelYearEvidence:
    model: str
    year: int
    sales_count: int
    numeric_dts_count: int
    median_dts: float | None
    defensible: bool = False


@dataclass(frozen=True)
class PreownedEvidence:
    retail_received_at: str | None
    models: tuple[ModelEvidence, ...]
    retail_history_loaded: bool
    fleet_models_resolved: bool
    model_years: tuple[ModelYearEvidence, ...] = ()


def _json(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def summarize_model_sales(rows, active_models):
    """Pure USED-market summarizer used by production and regression tests.

    `rows` are normalized/enriched retail-history dictionaries.
    `active_models` maps canonical model name -> active fleet unit count.
    Explicit NEW deliveries are identity evidence only and never historical preowned
    sales / turn observations. Legacy rows without a New/Used flag remain eligible.
    """
    sales = Counter()
    dts = defaultdict(list)

    for row in rows:
        if str(row.get("_sale_kind") or "").strip().upper() == "NEW":
            continue
        model = row.get("model")
        if not isinstance(model, str):
            continue
        model = model.strip().upper()
        if model not in active_models:
            continue

        sales[model] += 1
        value = row.get("days_to_sell")
        # bool is an int subclass; do not accept it as DTS evidence.
        if isinstance(value, int) and not isinstance(value, bool):
            dts[model].append(value)

    out = []
    for model in sorted(active_models):
        values = dts.get(model, [])
        out.append(ModelEvidence(
            model=model,
            active_units=int(active_models[model]),
            sales_count=int(sales.get(model, 0)),
            numeric_dts_count=len(values),
            median_dts=(float(statistics.median(values)) if values else None),
            distribution=_distribution(values),
        ))
    return tuple(out)


def summarize_model_year_sales(rows, active_models, *, min_sample=MIN_MODEL_YEAR_DTS):
    """Historical USED resale absorption grouped by (model, year), restricted to active-fleet models.

    `defensible` marks a model-year whose usable USED DTS sample meets the minimum.
    Explicit NEW deliveries are excluded; legacy rows without a condition flag remain eligible.
    """
    sales = Counter()
    dts = defaultdict(list)
    for row in rows:
        if str(row.get("_sale_kind") or "").strip().upper() == "NEW":
            continue
        model = row.get("model")
        year = row.get("year")
        if not isinstance(model, str):
            continue
        model = model.strip().upper()
        if model not in active_models or not isinstance(year, int) or isinstance(year, bool):
            continue
        key = (model, year)
        sales[key] += 1
        value = row.get("days_to_sell")
        if isinstance(value, int) and not isinstance(value, bool):
            dts[key].append(value)
    out = []
    for key in sorted(sales, key=lambda k: (k[0], -k[1])):
        values = dts.get(key, [])
        out.append(ModelYearEvidence(
            model=key[0], year=key[1], sales_count=int(sales[key]), numeric_dts_count=len(values),
            median_dts=(float(statistics.median(values)) if values else None),
            defensible=len(values) >= min_sample))
    return tuple(out)


def active_fleet_models(conn, scope):
    """(vin -> MODEL) for the authoritative active Service-Loaner fleet, from the latest completed loaner
    snapshot. Read-only; returns {} when unavailable."""
    active_vins = {r[0] for r in conn.execute(
        "SELECT vin FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        "AND active_fleet_presence=1 AND vin IS NOT NULL", (scope,)).fetchall()}
    if not active_vins:
        return {}
    batch = conn.execute(
        "SELECT id FROM import_batch WHERE source_id='src_p11_service_loaner_fleet' AND store_scope=? "
        "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC LIMIT 1", (scope,)).fetchone()
    out = {}
    if batch:
        for obs in conn.execute("SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                                "AND acceptance_status='accepted'", (batch[0],)).fetchall():
            raw = _json(obs[0])
            vin = str(raw.get("vin") or "").strip().upper()
            model = raw.get("model")
            if vin in active_vins and isinstance(model, str) and model.strip():
                out[vin] = model.strip().upper()
    return out


# Governed allowlist of AUTHORITATIVE model-year headers for the Service-Loaner fleet export. Explicit only —
# a bare, unrelated "year" column is deliberately NOT accepted for this contract (it could be a snapshot/order
# year), so an unrelated year-like field can never be silently read as the model year. Extend this list only
# when a header is governed as authoritative for THIS source.
MODEL_YEAR_SOURCE_HEADERS = ("model_year", "Model Year", "Model_Year", "MY", "modelYear")


def _norm_model_year(v):
    """A source cell -> a 4-digit model year, or None when it does not cleanly represent one (fail closed).
    Accepts an integer-like '2026' or a float-like '2026.0'; rejects '26', '20260', '20xx', '2026-QX60'."""
    s = str(v or "").strip()
    if not s:
        return None
    head = s.split(".")[0].strip()          # '2026.0' -> '2026'; '2026' unchanged
    return head if (head.isdigit() and len(head) == 4) else None


def active_fleet_model_years(conn, scope):
    """(resolved: {vin: 'YYYY'}, conflicts: {vin: reason}) for the authoritative active fleet.

    GOVERNED / FAIL-CLOSED:
      * canonical MODEL_YEAR_SOURCE_HEADERS remain the global allowlist;
      * legacy raw `year` is accepted only for a real completed import_run of the governed
        service_loaner_fleet.csv adapter. Direct/synthetic/uncontracted `year` remains non-authoritative;
      * values must normalize to one four-digit year and conflicts fail closed;
      * MY is never inferred from VIN structure or model code.

    The legacy allowance exists only to read already-accepted production observations created before the
    Service Loaner contract gained the `year` -> `model_year` header alias.
    """
    active_vins = {r[0] for r in conn.execute(
        "SELECT vin FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        "AND active_fleet_presence=1 AND vin IS NOT NULL", (scope,)).fetchall()}
    resolved, conflicts = {}, {}
    if not active_vins:
        return resolved, conflicts

    batch = conn.execute(
        "SELECT id FROM import_batch WHERE source_id='src_p11_service_loaner_fleet' AND store_scope=? "
        "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC LIMIT 1", (scope,)).fetchone()

    legacy_year_allowed = False
    if batch:
        try:
            legacy_year_allowed = bool(conn.execute(
                "SELECT 1 FROM import_run WHERE import_batch_id=? "
                "AND source_id='src_p11_service_loaner_fleet' "
                "AND source_contract='service_loaner_fleet' "
                "AND adapter_key='service_loaner_fleet.csv' "
                "AND accepted_count>0 AND state IN ('COMPLETED','COMPLETED_WITH_WARNINGS') LIMIT 1",
                (batch[0],)
            ).fetchone())
        except Exception:
            legacy_year_allowed = False

    source_headers = tuple(MODEL_YEAR_SOURCE_HEADERS) + (("year",) if legacy_year_allowed else ())

    for obs in (conn.execute("SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                             "AND acceptance_status='accepted'", (batch[0],)).fetchall() if batch else []):
        raw = _json(obs[0])
        vin = str(raw.get("vin") or "").strip().upper()
        if vin not in active_vins:
            continue
        present = {k: raw.get(k) for k in source_headers if str(raw.get(k) or "").strip() != ""}
        if not present:
            continue
        norm = {k: _norm_model_year(v) for k, v in present.items()}
        malformed = [k for k, nv in norm.items() if nv is None]
        distinct = {nv for nv in norm.values() if nv is not None}
        if malformed:
            conflicts[vin] = f"malformed model-year value in column(s) {sorted(malformed)}"
        elif len(distinct) > 1:
            conflicts[vin] = f"conflicting model-year columns {sorted(present)} = {sorted(distinct)}"
        elif len(distinct) == 1:
            resolved[vin] = next(iter(distinct))

    still_unknown = active_vins - set(resolved) - set(conflicts)
    if still_unknown:
        _resolve_my_from_inventory(conn, scope, still_unknown, resolved, conflicts)
    return resolved, conflicts



def _id_match_keys(*values):
    """Cross-source identifier match keys for a physical unit: each raw identifier UPPER-cased, plus its last-8
    (the DMS 'serial'/short-stock form, e.g. VIN 5N1AL1HU8TC348756 -> TC348756). This joins a loaner's full VIN
    to a DMS inventory row that only carries Serial/Stock# — never decodes model year from VIN structure."""
    keys = set()
    for v in values:
        s = str(v or "").strip().upper()
        if not s:
            continue
        keys.add(s)
        if len(s) >= 8:
            keys.add(s[-8:])
    return keys


def _resolve_my_from_inventory(conn, scope, want_vins, resolved, conflicts):
    """Fill active-loaner MY from retained authoritative DMS inventory lifecycle evidence.

    Match only governed physical identifiers (VIN / Serial / Stock# and last-8 forms) and read only explicit
    MODEL_YEAR_SOURCE_HEADERS. Never infer MY from VIN structure or model code. Conflicts fail closed.
    """
    if not want_vins:
        return

    idx = inventory_lifecycle_index(conn, scope)
    for wv in list(want_vins):
        years = set()
        for key in _id_match_keys(wv):
            rec = idx.get(key)
            if rec:
                years.update(rec.get("model_years") or ())

        if len(years) == 1:
            resolved[wv] = next(iter(years))
            want_vins.discard(wv)
        elif len(years) > 1:
            conflicts[wv] = f"model year ambiguous across retained inventory lifecycle {sorted(years)}"
            want_vins.discard(wv)



def latest_retail_rows(conn, scope):
    """(normalized rows, received_at) for the latest completed retail_history schema>=3 batch, or ([], None)."""
    batch = conn.execute(
        "SELECT id, received_at FROM import_batch WHERE source_id='src_p11_retail_history' AND store_scope=? "
        "AND schema_profile_version>=3 AND lifecycle_status='completed' "
        "ORDER BY received_at DESC, id DESC LIMIT 1", (scope,)).fetchone()
    if not batch:
        return [], None
    idmap = new_retail_identity_index(conn, scope)          # VIN-keyed authoritative identity from New-Retail lifecycle
    rows = []
    for o in conn.execute(
            "SELECT normalized_values, raw_values FROM source_observation "
            "WHERE import_batch_id=? AND acceptance_status='accepted'", (batch[0],)).fetchall():
        row = _json(o[0])
        raw = _json(o[1])
        # Authoritative ORIGINAL MSRP: the Reynolds retail-history export carries it, but it was omitted from
        # earlier schema profiles, so for already-loaded batches it survives only in the retained RAW row.
        # Surface it (never mutating the raw record) so the market/value rail can normalize each sale into an
        # observed retention ratio. Newer imports carry 'msrp' in normalized_values directly.
        if _retail_msrp(row) is None:
            rm = _retail_msrp(raw)
            if rm is not None:
                row = {**row, "msrp": rm}
        # The combined Reynolds Retail History carries BOTH new and used deliveries. Surface the New/Used flag from
        # the raw row (an undeclared extra column, so it is not in normalized_values) so the USED-market pricing
        # cohorts can exclude NEW sales (which transact at ~MSRP and would fabricate ~100% retention). Absent flag
        # -> '' (a legacy used-only export), treated as USED downstream; NEW rows stay usable for identity only.
        row = {**row, "_sale_kind": _sale_kind(raw) or _sale_kind(_json(o[0]))}
        rows.append(_bridge_identity_by_vin(row, idmap))
    return rows, batch[1]


# New/Used indicator headers on the combined Reynolds Retail History (undeclared extras kept in raw). The value is
# the row's condition ('New' / 'Used' / 'N' / 'U' / 'Pre-Owned' / 'Certified'); only an explicit NEW is excluded.
_NEWUSED_HEADERS = ("_sale_kind", "new_used", "New/Used", "New / Used", "NewUsed", "New Used", "NEW/USED",
                    "N/U", "NU", "Sale Type", "sale_type", "Deal Type", "Vehicle Type", "Inventory Type",
                    "Stock Type", "Condition", "New or Used", "New/Used Indicator")


def _sale_kind(row):
    """'NEW' / 'USED' / '' from a retail-history row's New/Used indicator (checked against the tolerant header
    allowlist). Only an EXPLICIT new indicator returns 'NEW'; anything else (used, pre-owned, certified, blank,
    absent, or ambiguous) is NOT treated as new — so a legacy used-only export with no indicator stays USED."""
    for k in _NEWUSED_HEADERS:
        if k in row:
            s = str(row.get(k) or "").strip().upper()
            if not s or s in ("N/A", "NA", "NONE", "NULL"):
                continue
            if s in ("NEW",) or s == "N" or s.startswith("NEW"):
                return "NEW"
            if s[0] in ("U", "P", "C") or s.startswith("USED") or s.startswith("PRE"):
                return "USED"
    return ""


# Used-ledger model-number values that are NOT a real DMS model code (the real Reynolds used export writes these
# where a new car would carry its model number). They must never become a market-comparability identity.
_CODE_SENTINELS = {"", "BLANK", "TRUCK", "NONE", "N/A", "NA", "UNKNOWN", "USED"}


def _is_real_code(v):
    """A value is a usable DMS model code only if it is non-blank, not a known non-code sentinel, and carries a
    digit (real Infiniti model codes are numeric like 84615). 'BLANK'/'TRUCK' etc. are NOT codes."""
    s = str(v or "").strip().upper()
    return bool(s) and s not in _CODE_SENTINELS and any(ch.isdigit() for ch in s)


def _model_line(s):
    """The governed COMMERCIAL MODEL LINE token from a free-text model/description (e.g. 'QX60 2.0T AWD SEN' ->
    'QX60', 'QX60' -> 'QX60'). Used ONLY to validate that two rows are the same commercial model — it never
    infers a trim or a model code. Falls back to the first token when no model-line token is recognized."""
    up = str(s or "").upper().replace("-", " ")
    for tok in up.split():
        if 3 <= len(tok) <= 4 and tok[0] == "Q" and tok.isalnum() and any(c.isdigit() for c in tok):
            return tok                                       # QX60, QX80, Q50, ...
    toks = up.split()
    return toks[0] if toks else ""


def new_retail_identity_index(conn, scope):
    """VIN-keyed authoritative IDENTITY for used-ledger rows that carry no usable model code, recovered from the
    dealership's historical NEW-car records that DO carry it:

      * HISTORICAL NEW-CAR SALES (the DMS sales ledger's own coded rows) — the original NEW sale of a VIN carries
        the authoritative Model Number, while its later USED resale carries BLANK/TRUCK. All completed
        retail_history batches are scanned (the new sale predates the used resale, in an earlier batch);
      * the new-inventory pipeline snapshots (model_code + original MSRP) and Speed-to-Sell (VIN + model_code) —
        additional coverage.

    Returns {id_key: {"model_code", "msrp", "model", "source"}}. Keys are the raw identifiers and their last-8
    (via _id_match_keys) so the index can be built from any source; the BRIDGE itself matches on the EXACT FULL
    VIN only (see _bridge_identity_by_vin) — never fuzzy. IDENTITY ONLY: never a new sale's price/cost/date.
    Newest record wins per key; read-only (raw import history is never mutated)."""
    index = {}

    def _add(keys, code, msrp, model, source):
        for k in keys:
            cur = index.get(k)
            if cur is None:
                index[k] = {"model_code": code, "msrp": msrp, "model": model, "source": source}
            else:                                           # fill gaps without overwriting a newer record's fields
                if cur.get("model_code") is None and code is not None:
                    cur["model_code"], cur["model"], cur["source"] = code, (model or cur.get("model")), source
                if cur.get("msrp") is None and msrp is not None:
                    cur["msrp"] = msrp

    # (1) Historical NEW-CAR SALES — the authoritative bridge source (VIN + Model Number + model line).
    for batch in conn.execute(
            "SELECT id FROM import_batch WHERE source_id='src_p11_retail_history' AND store_scope=? "
            "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC", (scope,)).fetchall():
        for o in conn.execute("SELECT normalized_values, raw_values FROM source_observation "
                              "WHERE import_batch_id=? AND acceptance_status='accepted'", (batch[0],)).fetchall():
            norm, raw = _json(o[0]), _json(o[1])
            code = norm.get("model_number")
            if not _is_real_code(code):
                code = raw.get("model_number") or raw.get("Model Number")
            vin = norm.get("vin") or raw.get("vin") or raw.get("VIN")
            if not _is_real_code(code) or not vin:
                continue
            model = str(norm.get("model") or raw.get("model") or raw.get("Model") or "").strip()
            _add(_id_match_keys(vin), str(code).strip().upper(), _retail_msrp(raw), model,
                 "authoritative New-Car sales history")
    # (2) New-inventory pipeline snapshots (model_code + MSRP) and (3) Speed-to-Sell (VIN + model_code).
    for source_id in ("src_p11_new_inventory_pipeline_summary", "src_p11_new_inventory_current"):
        for batch in conn.execute(
                "SELECT id FROM import_batch WHERE source_id=? AND store_scope=? AND lifecycle_status='completed' "
                "ORDER BY received_at DESC, id DESC", (source_id, scope)).fetchall():
            for obs in conn.execute("SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                                    "AND acceptance_status='accepted'", (batch[0],)).fetchall():
                raw = _json(obs[0])
                code = str(raw.get("model_code")).strip().upper() if _is_real_code(raw.get("model_code")) else None
                msrp = _msrp_num(raw.get("msrp"))
                if code is None and msrp is None:
                    continue
                _add(_id_match_keys(raw.get("vin"), raw.get("serial"), raw.get("stock_number")), code, msrp,
                     str(raw.get("model") or "").strip(), "original New Retail VIN lifecycle record")
    for batch in conn.execute(
            "SELECT id FROM import_batch WHERE source_id='src_p11_speed_to_sell' AND store_scope=? "
            "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC", (scope,)).fetchall():
        for obs in conn.execute("SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                                "AND acceptance_status='accepted'", (batch[0],)).fetchall():
            raw = _json(obs[0])
            if _is_real_code(raw.get("model_code")):
                _add(_id_match_keys(raw.get("vin"), raw.get("serial"), raw.get("stock_number")),
                     str(raw.get("model_code")).strip().upper(), None, str(raw.get("model") or "").strip(),
                     "original New Retail VIN lifecycle record")
    return index


def _bridge_identity_by_vin(row, idmap):
    """If a used-ledger row's model_number/model_code is absent or a non-code sentinel (BLANK/TRUCK/…), recover
    the authoritative model code — and original MSRP where the used row lacks it — from the SAME FULL VIN's
    historical New-Car record. STRICT: EXACT full-VIN match only (never fuzzy, never last-8 for the bridge
    decision), never inferred from trim text / MSRP / price / normalize_code. The used sale date, used
    transaction price, used VIN and used model year are left exactly as the used ledger recorded them. If the
    New-Car source reports a DIFFERENT commercial model than the used row, the conflict is surfaced and NO bridge
    is applied. Raw import history is never mutated (this is a read-time normalized-evidence bridge).

    It ALSO stamps the VIN-authoritative ORIGINAL NEW MSRP as `_orig_msrp` — the retention denominator — even when
    the used row already carries its own MSRP field, because in the combined Reynolds ledger a used row's MSRP is
    unreliable (often == its Vehicle Price). Only the exact same-VIN New/lifecycle MSRP is authoritative here."""
    have_code = _is_real_code(row.get("model_number")) or _is_real_code(row.get("model_code"))
    vin = str(row.get("vin") or "").strip().upper()
    if not vin:
        return row
    hit = idmap.get(vin)                                    # EXACT full-VIN match only
    if hit is None:
        return row
    code = hit.get("model_code")
    # (8) model cross-check: compare the governed COMMERCIAL MODEL LINE (e.g. QX60), NOT the whole free-text
    # model/description. A New-Car identity like "QX60 2.0T AWD SEN" is still commercially QX60 and must match a
    # used "QX60" row. The hit's commercial model comes from the governed code prefix (model_from_code); the used
    # side is reduced to its model-line token. This normalization ONLY validates same-model — it never infers a
    # trim or a model code from that text. On conflict, NOTHING is bridged (neither identity nor original MSRP).
    if code:
        from ..newinv.dms_identity import model_from_code
        used_line = _model_line(row.get("model"))
        new_line = (model_from_code(code) or "").upper() or _model_line(hit.get("model"))
        if used_line and new_line and used_line != new_line:
            out = dict(row)
            out["model_number_conflict"] = (f"used ledger says {used_line} but New-Car history says {new_line} "
                                            f"for VIN {vin} (code {code}) — not bridged")
            return out
    out = dict(row)
    prov = f"historical used transaction VIN matched to original New sale VIN; model code {code} from " \
           f"authoritative New-Car history."
    have_msrp = _retail_msrp(row) is not None
    if hit.get("msrp") is not None:
        out["_orig_msrp"] = hit["msrp"]                     # VIN-authoritative original NEW MSRP (retention denom)
        out.setdefault("msrp_source", prov)
    if not have_code and code:
        out["model_number"] = code
        out["model_number_source"] = prov
    if not have_msrp and hit.get("msrp") is not None:
        out["msrp"] = hit["msrp"]                           # display MSRP fill only when the used row lacks one
    return out


_MSRP_HEADERS = ("msrp", "MSRP", "Msrp", "list_price", "List Price", "ListPrice", "List_Price")


def _retail_msrp(row):
    """Authoritative original MSRP from a retail-history row (normalized or raw), tolerant of the header
    spellings a real DMS export uses. Returns a positive float or None — never a manufactured value."""
    for k in _MSRP_HEADERS:
        if k in row:
            s = str(row.get(k) or "").replace(",", "").replace("$", "").strip()
            try:
                v = float(s) if s else None
            except ValueError:
                v = None
            if v is not None and v > 0:
                return v
    return None


def build_preowned_evidence(conn, scope, *, retail_rows=None, retail_received_at=None):
    """Build model-level historical resale evidence for the active Service Loaner fleet."""

    active_vins = {
        r[0] for r in conn.execute(
            "SELECT vin FROM service_loaner_unit "
            "WHERE store_scope=? AND superseded_by IS NULL "
            "AND active_fleet_presence=1 AND vin IS NOT NULL",
            (scope,),
        ).fetchall()
    }

    if not active_vins:
        return PreownedEvidence(
            retail_received_at=None,
            models=(),
            retail_history_loaded=False,
            fleet_models_resolved=False,
        )

    loaner_batch = conn.execute(
        "SELECT id FROM import_batch "
        "WHERE source_id='src_p11_service_loaner_fleet' "
        "AND store_scope=? AND lifecycle_status='completed' "
        "ORDER BY received_at DESC, id DESC LIMIT 1",
        (scope,),
    ).fetchone()

    active_models = Counter()
    if loaner_batch:
        observations = conn.execute(
            "SELECT raw_values FROM source_observation "
            "WHERE import_batch_id=? AND acceptance_status='accepted'",
            (loaner_batch[0],),
        ).fetchall()

        for obs in observations:
            raw = _json(obs[0])
            vin = str(raw.get("vin") or "").strip().upper()
            if vin not in active_vins:
                continue
            model = raw.get("model")
            if isinstance(model, str) and model.strip():
                active_models[model.strip().upper()] += 1

    if not active_models:
        return PreownedEvidence(
            retail_received_at=None,
            models=(),
            retail_history_loaded=False,
            fleet_models_resolved=False,
        )

    # Reuse an already-loaded combined Reynolds lifecycle when supplied by the
    # intelligence layer. This keeps the New/Used classification and avoids a
    # second 28k-row history read on the Service Loaner page.
    if retail_rows is not None:
        rows = list(retail_rows)
        return PreownedEvidence(
            retail_received_at=retail_received_at,
            models=summarize_model_sales(rows, active_models),
            retail_history_loaded=(retail_received_at is not None),
            fleet_models_resolved=True,
            model_years=summarize_model_year_sales(rows, active_models),
        )

    retail_batch = conn.execute(
        "SELECT id, received_at FROM import_batch "
        "WHERE source_id='src_p11_retail_history' "
        "AND store_scope=? AND schema_profile_version>=3 "
        "AND lifecycle_status='completed' "
        "ORDER BY received_at DESC, id DESC LIMIT 1",
        (scope,),
    ).fetchone()

    if not retail_batch:
        return PreownedEvidence(
            retail_received_at=None,
            models=summarize_model_sales([], active_models),
            retail_history_loaded=False,
            fleet_models_resolved=True,
        )

    rows = []
    for obs in conn.execute(
        "SELECT normalized_values, raw_values FROM source_observation "
        "WHERE import_batch_id=? AND acceptance_status='accepted'",
        (retail_batch[0],),
    ).fetchall():
        row = _json(obs[0])
        raw = _json(obs[1])
        # New/Used is retained in raw history on older batches. Restore it at
        # read time so explicit NEW deliveries cannot masquerade as preowned
        # sales/turn evidence. Raw observations remain immutable.
        row = {**row, "_sale_kind": _sale_kind(raw) or _sale_kind(row)}
        rows.append(row)

    return PreownedEvidence(
        retail_received_at=retail_batch[1],
        models=summarize_model_sales(rows, active_models),
        retail_history_loaded=True,
        fleet_models_resolved=True,
        model_years=summarize_model_year_sales(rows, active_models),
    )


def _msrp_num(v):
    s = str(v if v is not None else "").replace(",", "").replace("$", "").strip()
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _build_inventory_lifecycle_index_uncached(conn, scope):
    """SPRINT 4 BULK INVENTORY LIFECYCLE INDEX.

    Scan retained accepted New-Retail inventory/pipeline observations once for the whole scope and index them by
    the same governed VIN/Serial/Stock linkage used by the existing per-unit lifecycle lookup.

    MSRP/model-code precedence is preserved from the prior implementation:
      pipeline-summary before current; newest completed batch before older; first qualifying matching row wins.

    Model year remains governed by MODEL_YEAR_SOURCE_HEADERS only. A malformed/self-conflicting row contributes
    no MY; distinct years across retained matched rows remain distinct so the caller can fail closed.
    """
    facts_by_key = {}
    years_by_key = {}

    for source_rank, source_id in enumerate(
            ("src_p11_new_inventory_pipeline_summary", "src_p11_new_inventory_current")):
        batches = conn.execute(
            "SELECT id FROM import_batch WHERE source_id=? AND store_scope=? "
            "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC",
            (source_id, scope)).fetchall()

        for batch_rank, batch in enumerate(batches):
            observations = conn.execute(
                "SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                "AND acceptance_status='accepted'", (batch[0],)).fetchall()

            for row_rank, obs in enumerate(observations):
                raw = _json(obs[0])
                keys = _id_match_keys(raw.get("vin"), raw.get("serial"), raw.get("stock_number"))
                if not keys:
                    continue

                present = {
                    k: raw.get(k) for k in MODEL_YEAR_SOURCE_HEADERS
                    if str(raw.get(k) or "").strip() != ""
                }
                if present:
                    normed = [_norm_model_year(v) for v in present.values()]
                    if all(v is not None for v in normed):
                        distinct = set(normed)
                        if len(distinct) == 1:
                            my = next(iter(distinct))
                            for key in keys:
                                years_by_key.setdefault(key, set()).add(my)

                msrp = _msrp_num(raw.get("msrp"))
                code = str(raw.get("model_code") or "").strip().upper() or None
                if msrp is None and code is None:
                    continue

                rank = (source_rank, batch_rank, row_rank)
                for key in keys:
                    if key not in facts_by_key:
                        facts_by_key[key] = {
                            "msrp": msrp,
                            "model_code": code,
                            "_rank": rank,
                        }

    out = {}
    for key in set(facts_by_key) | set(years_by_key):
        fact = facts_by_key.get(key) or {}
        out[key] = {
            "msrp": fact.get("msrp"),
            "model_code": fact.get("model_code"),
            "model_years": tuple(sorted(years_by_key.get(key, set()))),
            "_rank": fact.get("_rank"),
        }
    return out


def inventory_lifecycle_facts(conn, scope, vin):
    """Authoritative (MSRP, model_code) for one physical unit via the bulk retained lifecycle index.

    Public contract is unchanged. The expensive historical scan moved to one scope-wide cached build.
    """
    keys = _id_match_keys(vin)
    if not keys:
        return None, None

    idx = inventory_lifecycle_index(conn, scope)
    candidates = []
    seen = set()
    for key in keys:
        rec = idx.get(key)
        if not rec:
            continue
        marker = (rec.get("_rank"), rec.get("msrp"), rec.get("model_code"))
        if marker in seen:
            continue
        seen.add(marker)
        if rec.get("msrp") is not None or rec.get("model_code") is not None:
            candidates.append(rec)

    if not candidates:
        return None, None

    best = min(
        candidates,
        key=lambda r: r.get("_rank") if r.get("_rank") is not None else (999999, 999999, 999999)
    )
    return best.get("msrp"), best.get("model_code")


# SERVICE LOANER RUNTIME EVIDENCE CACHE
# Pure/read-only accepted-source evidence was being rebuilt many times in one request.
# Cache by store + latest completed import epoch; new accepted imports invalidate immediately.
import time as _pe_time

_PE_RUNTIME_CACHE = {}
_PE_RUNTIME_TTL = 120.0
_PE_UNCACHED_NEW_RETAIL_IDENTITY_INDEX = new_retail_identity_index
_PE_UNCACHED_LATEST_RETAIL_ROWS = latest_retail_rows
_PE_UNCACHED_INVENTORY_LIFECYCLE_FACTS = inventory_lifecycle_facts


def _pe_import_epoch(conn, scope):
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(received_at),'') FROM import_batch "
            "WHERE store_scope=? AND lifecycle_status='completed'", (scope,)
        ).fetchone()
        return str(row[0] or "") if row else ""
    except Exception:
        return ""


def _pe_db_main(conn):
    """The main database file path — part of the cache key so a cached value can never bleed across distinct
    connections/databases that happen to share a scope and import epoch (isolated temp DBs in tests). In the
    live runtime the main database path is constant, so this contributes nothing new to production keys."""
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
        return next((str(r[2] or "") for r in rows if str(r[1] or "") == "main"), "")
    except Exception:
        return ""


def _pe_cached(name, conn, scope, extra, loader):
    now = _pe_time.monotonic()
    key = (name, _pe_db_main(conn), str(scope), _pe_import_epoch(conn, scope), extra)
    hit = _PE_RUNTIME_CACHE.get(key)
    if hit is not None and now - hit[0] <= _PE_RUNTIME_TTL:
        return hit[1]
    value = loader()
    if len(_PE_RUNTIME_CACHE) > 128:
        _PE_RUNTIME_CACHE.clear()
    _PE_RUNTIME_CACHE[key] = (now, value)
    return value

def _inventory_lifecycle_cache_identity(conn, scope):
    """Stable identity/fingerprint for retained DMS inventory lifecycle evidence."""
    try:
        db_rows = conn.execute("PRAGMA database_list").fetchall()
        db_main = next((str(r[2] or "") for r in db_rows if str(r[1] or "") == "main"), "")
    except Exception:
        db_main = ""
    try:
        rows = conn.execute(
            "SELECT source_id, COUNT(*), COALESCE(MAX(received_at),''), COALESCE(MAX(id),'') "
            "FROM import_batch WHERE source_id IN (?,?) AND store_scope=? AND lifecycle_status='completed' "
            "GROUP BY source_id ORDER BY source_id",
            ("src_p11_new_inventory_pipeline_summary", "src_p11_new_inventory_current", scope)
        ).fetchall()
        fingerprint = tuple(tuple(r) for r in rows)
    except Exception:
        fingerprint = ()
    return repr((db_main, fingerprint))


def inventory_lifecycle_index(conn, scope):
    """Cached whole-scope retained lifecycle index with source-specific invalidation."""
    extra = _inventory_lifecycle_cache_identity(conn, scope)
    return _pe_cached(
        "inventory_lifecycle_index", conn, scope, extra,
        lambda: _build_inventory_lifecycle_index_uncached(conn, scope)
    )



def new_retail_identity_index(conn, scope):
    value = _pe_cached(
        "new_retail_identity_index", conn, scope, "",
        lambda: _PE_UNCACHED_NEW_RETAIL_IDENTITY_INDEX(conn, scope)
    )
    return dict(value)


def latest_retail_rows(conn, scope):
    value = _pe_cached(
        "latest_retail_rows", conn, scope, "",
        lambda: _PE_UNCACHED_LATEST_RETAIL_ROWS(conn, scope)
    )
    rows, received_at = value
    return list(rows), received_at


def inventory_lifecycle_facts(conn, scope, *args, **kwargs):
    extra = repr(args) + "|" + repr(sorted(kwargs.items()))
    return _pe_cached(
        "inventory_lifecycle_facts", conn, scope, extra,
        lambda: _PE_UNCACHED_INVENTORY_LIFECYCLE_FACTS(conn, scope, *args, **kwargs)
    )
