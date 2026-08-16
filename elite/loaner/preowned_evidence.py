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


@dataclass(frozen=True)
class ModelEvidence:
    model: str
    active_units: int
    sales_count: int
    numeric_dts_count: int
    median_dts: float | None


@dataclass(frozen=True)
class PreownedEvidence:
    retail_received_at: str | None
    models: tuple[ModelEvidence, ...]
    retail_history_loaded: bool
    fleet_models_resolved: bool


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
        ))
    return tuple(out)


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
    )
