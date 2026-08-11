"""Deterministic Phase 2 fixtures: a wired data stack + synthetic source/identity
payloads. Synthetic dealership data only — no confidential production data.
"""
from __future__ import annotations

import json

from ..fixtures import Stack
from ..ids import new_id
from .facts import FactService
from .ingestion import IngestionService
from .models import FieldSpec, SchemaProfile, SourceRegistry
from .store import DataStore

SCOPE = "store:HG"

VEHICLE_FIELDS = [
    FieldSpec("stock_number", required=True, kind="text", meaning="dealer stock number"),
    FieldSpec("vin", required=False, kind="vin", meaning="vehicle identification number"),
    FieldSpec("model", required=True, kind="upper", meaning="model line"),
    FieldSpec("production_month", required=False, kind="month", meaning="production month"),
    FieldSpec("mileage", required=False, kind="int", meaning="odometer"),
]


class Phase2:
    """Phase 1 platform + Phase 2 data/identity/facts, with sources registered."""

    def __init__(self, db_path, *, runtime=None):
        # runtime=None -> deterministic test defaults (tests/fixtures); a RuntimeConfig -> real
        # pepper + real clock + real environment for the production/pilot launcher.
        self.stack = (Stack(db_path) if runtime is None else
                      Stack(db_path, environment=runtime.environment, pepper=runtime.pepper,
                            clock=runtime.clock))                 # migrates v1 + v2
        self.store = DataStore(self.stack.db.conn, self.stack.clock)
        self.facts = FactService(self.store, self.stack.clock)
        self.ingestion = IngestionService(self.store, self.facts, self.stack.clock)
        self.clock = self.stack.clock
        # Register sources/profiles once; idempotent so a restart (reopen) is safe.
        if self.store.get_source("src_dms") is None:
            self.store.add_source(SourceRegistry(
                id="src_dms", name="DMS Vehicle Export", owner="dealership", source_type="dms",
                supported_profiles=["prof_dms_v1"], authoritative_fact_types=["vehicle_present"], scope=SCOPE))
            self.store.add_profile(SchemaProfile(id="prof_dms_v1", source_id="src_dms", version=1,
                                                 fields=VEHICLE_FIELDS, snapshot_capable=True,
                                                 full_snapshot_requirements={}))
        if self.store.get_source("src_feed") is None:
            self.store.add_source(SourceRegistry(
                id="src_feed", name="Ad-hoc Feed", owner="third_party", source_type="feed",
                supported_profiles=["prof_feed_v1"], authoritative_fact_types=[], scope=SCOPE))
            self.store.add_profile(SchemaProfile(id="prof_feed_v1", source_id="src_feed", version=1,
                                                 fields=VEHICLE_FIELDS, snapshot_capable=False))
        self.dms = self.store.get_source("src_dms")
        self.feed = self.store.get_source("src_feed")

    def reopen(self):
        return Phase2(self.stack.db.path)

    def close(self):
        self.stack.close()

    def ingest_dms(self, rows, **kw):
        raw = kw.pop("raw_text", None) or json.dumps(rows, sort_keys=True)
        return self.ingestion.ingest(source_id="src_dms", profile_version=1, rows=rows, raw_text=raw,
                                     scope=SCOPE, entity_kind="vehicle", fact_type="vehicle_present", **kw)


# ---- source payload fixtures (21 cases) -----------------------------------
GOOD_VIN = "1GNSKBKC5FR000001"      # valid-shape synthetic VIN


def source_cases():
    """Return {case_name: (rows, claimed_snapshot)}. Synthetic."""
    base = {"stock_number": "N1", "vin": GOOD_VIN, "model": "qx80",
            "production_month": "2026-03", "mileage": "5"}

    def row(**over):
        r = dict(base); r.update(over); return r
    return {
        "valid_expected": ([row()], "partial"),
        "harmless_extra_field": ([row(color="black")], "partial"),
        "missing_optional_field": ([{k: v for k, v in row().items() if k != "mileage"}], "partial"),
        "missing_required_field": ([{k: v for k, v in row().items() if k != "stock_number"}], "partial"),
        "renamed_required_field": ([{("stk" if k == "stock_number" else k): v for k, v in row().items()}], "partial"),
        "invalid_date": ([row(production_month="13/40/2026")], "partial"),
        "invalid_numeric": ([row(mileage="abc")], "partial"),
        "explicit_zero": ([row(mileage="0")], "partial"),
        "blank": ([row(mileage="")], "partial"),
        "na": ([row(mileage="N/A")], "partial"),
        "duplicate_row": ([row(), row()], "partial"),
        "conflicting_duplicate": ([row(mileage="5"), row(mileage="9")], "partial"),
        "malformed_vin": ([row(vin="XYZ")], "partial"),
        "placeholder_vin": ([row(vin="00000000000000000")], "partial"),
        "valid_full_snapshot": ([row()], "full"),
        "partial_snapshot": ([row()], "partial"),
    }
