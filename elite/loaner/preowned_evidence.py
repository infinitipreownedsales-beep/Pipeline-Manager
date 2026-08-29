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
    """Pure summarizer used by production and regression tests.

    `rows` are normalized retail-history dictionaries.
    `active_models` maps canonical model name -> active fleet unit count.
    """
    sales = Counter()
    dts = defaultdict(list)

    for row in rows:
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
    """Historical resale absorption grouped by (model, year), restricted to models present in the active
    fleet. `defensible` marks a model-year whose usable DTS sample meets the minimum. Read-only; no economics."""
    sales = Counter()
    dts = defaultdict(list)
    for row in rows:
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
    """(resolved: {vin: 'YYYY'}, conflicts: {vin: reason}) for the authoritative active fleet, from the latest
    completed loaner snapshot. GOVERNED and FAIL-CLOSED:

      * only MODEL_YEAR_SOURCE_HEADERS are read — an unrelated 'year'-like column never matches;
      * a value must normalise to exactly one 4-digit year; a malformed candidate FAILS CLOSED;
      * two candidate columns disagreeing FAILS CLOSED (ambiguity is never silently resolved);
      * MY is never inferred from a VIN or a model code.

    A conflicted/malformed unit is absent from `resolved` (stays UNKNOWN downstream) and named in `conflicts`
    for data-health. Read-only."""
    active_vins = {r[0] for r in conn.execute(
        "SELECT vin FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        "AND active_fleet_presence=1 AND vin IS NOT NULL", (scope,)).fetchall()}
    resolved, conflicts = {}, {}
    if not active_vins:
        return resolved, conflicts
    batch = conn.execute(
        "SELECT id FROM import_batch WHERE source_id='src_p11_service_loaner_fleet' AND store_scope=? "
        "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC LIMIT 1", (scope,)).fetchone()
    for obs in (conn.execute("SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                             "AND acceptance_status='accepted'", (batch[0],)).fetchall() if batch else []):
        raw = _json(obs[0])
        vin = str(raw.get("vin") or "").strip().upper()
        if vin not in active_vins:
            continue
        present = {k: raw.get(k) for k in MODEL_YEAR_SOURCE_HEADERS if str(raw.get(k) or "").strip() != ""}
        if not present:
            continue                                     # MY genuinely absent -> stays UNKNOWN (honest)
        norm = {k: _norm_model_year(v) for k, v in present.items()}
        malformed = [k for k, nv in norm.items() if nv is None]
        distinct = {nv for nv in norm.values() if nv is not None}
        if malformed:
            conflicts[vin] = f"malformed model-year value in column(s) {sorted(malformed)}"
        elif len(distinct) > 1:
            conflicts[vin] = f"conflicting model-year columns {sorted(present)} = {sorted(distinct)}"
        elif len(distinct) == 1:
            resolved[vin] = next(iter(distinct))

    # Source-connection fallback: for active VINs whose model year is still UNKNOWN (the loaner fleet export
    # carries no model-year column), resolve it from another authoritative source ALREADY loaded that carries a
    # governed model-year column keyed by VIN — the DMS inventory / pipeline export. Same governed normalization,
    # still FAIL-CLOSED, still never inferred from the VIN or a model code. Only an exact VIN match contributes.
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
    """Fill in model years for `want_vins` from the latest completed DMS inventory snapshot (pipeline summary,
    then current), using the governed model-year headers only. The pipeline export carries NO full VIN column —
    it identifies a physical unit by Serial / Stock# — so the join matches on ANY available identifier (vin /
    serial / stock_number) and its last-8 form. Model year is never inferred from VIN structure; only an exact
    source identifier join contributes. Mutates `resolved` / `conflicts`."""
    for source_id in ("src_p11_new_inventory_pipeline_summary", "src_p11_new_inventory_current"):
        if not want_vins:
            return
        batch = conn.execute(
            "SELECT id FROM import_batch WHERE source_id=? AND store_scope=? AND lifecycle_status='completed' "
            "ORDER BY received_at DESC, id DESC LIMIT 1", (source_id, scope)).fetchone()
        if not batch:
            continue
        key_to_my = {}                                   # identifier match-key -> set of MYs seen for it
        for obs in conn.execute("SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                                "AND acceptance_status='accepted'", (batch[0],)).fetchall():
            raw = _json(obs[0])
            present = {k: raw.get(k) for k in MODEL_YEAR_SOURCE_HEADERS if str(raw.get(k) or "").strip() != ""}
            if not present:
                continue
            norm = {nv for nv in (_norm_model_year(v) for v in present.values()) if nv is not None}
            if len(norm) != 1:
                continue                                 # malformed / self-conflicting row -> skip (honest)
            my = next(iter(norm))
            for key in _id_match_keys(raw.get("vin"), raw.get("serial"), raw.get("stock_number")):
                key_to_my.setdefault(key, set()).add(my)
        for wv in list(want_vins):
            cand = set()
            for key in _id_match_keys(wv):
                cand |= key_to_my.get(key, set())
            if len(cand) == 1:
                resolved[wv] = next(iter(cand))
                want_vins.discard(wv)
            elif len(cand) > 1:
                conflicts[wv] = f"model year ambiguous across matched inventory rows {sorted(cand)}"
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
        # Authoritative ORIGINAL MSRP: the Reynolds retail-history export carries it, but it was omitted from
        # earlier schema profiles, so for already-loaded batches it survives only in the retained RAW row.
        # Surface it (never mutating the raw record) so the market/value rail can normalize each sale into an
        # observed retention ratio. Newer imports carry 'msrp' in normalized_values directly.
        if _retail_msrp(row) is None:
            rm = _retail_msrp(_json(o[1]))
            if rm is not None:
                row = {**row, "msrp": rm}
        rows.append(_bridge_identity_by_vin(row, idmap))
    return rows, batch[1]


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
    is applied. Raw import history is never mutated (this is a read-time normalized-evidence bridge)."""
    have_code = _is_real_code(row.get("model_number")) or _is_real_code(row.get("model_code"))
    have_msrp = _retail_msrp(row) is not None
    if have_code and have_msrp:
        return row                                          # preserve any valid code / MSRP already present
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
    # trim or a model code from that text.
    if not have_code and code:
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
    if not have_code and code:
        out["model_number"] = code
        out["model_number_source"] = prov
    if not have_msrp and hit.get("msrp") is not None:
        out["msrp"] = hit["msrp"]
        out["msrp_source"] = prov
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


def build_preowned_evidence(conn, scope):
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
        "SELECT normalized_values FROM source_observation "
        "WHERE import_batch_id=? AND acceptance_status='accepted'",
        (retail_batch[0],),
    ).fetchall():
        rows.append(_json(obs[0]))

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


def inventory_lifecycle_facts(conn, scope, vin):
    """This physical unit's authoritative (MSRP, model_code) recovered from the FULL inventory/pipeline
    lifecycle — every completed business-date snapshot, newest first, not only the latest New-Retail snapshot.

    A Service Loaner that has moved out of New-Retail inventory is absent from today's snapshot, but its MSRP was
    retained when it was new inventory (the pipeline summary is a per-business-date longitudinal-memory source).
    The join uses the same governed VIN/Serial/Stock linkage (value + last-8) used to resolve model year — never
    a VIN structural decode, never a manual entry. Returns (msrp, model_code); either is None when no retained
    snapshot carried this unit with that field."""
    keys = _id_match_keys(vin)
    if not keys:
        return None, None
    for source_id in ("src_p11_new_inventory_pipeline_summary", "src_p11_new_inventory_current"):
        for batch in conn.execute(
                "SELECT id FROM import_batch WHERE source_id=? AND store_scope=? "
                "AND lifecycle_status='completed' ORDER BY received_at DESC, id DESC",
                (source_id, scope)).fetchall():
            for obs in conn.execute(
                    "SELECT raw_values FROM source_observation WHERE import_batch_id=? "
                    "AND acceptance_status='accepted'", (batch[0],)).fetchall():
                raw = _json(obs[0])
                if keys & _id_match_keys(raw.get("vin"), raw.get("serial"), raw.get("stock_number")):
                    msrp = _msrp_num(raw.get("msrp"))
                    code = str(raw.get("model_code") or "").strip().upper() or None
                    if msrp is not None or code is not None:
                        return msrp, code
    return None, None
