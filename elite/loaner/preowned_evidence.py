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
    rows = [_json(o[0]) for o in conn.execute(
        "SELECT normalized_values FROM source_observation WHERE import_batch_id=? AND acceptance_status='accepted'",
        (batch[0],)).fetchall()]
    return rows, batch[1]


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
