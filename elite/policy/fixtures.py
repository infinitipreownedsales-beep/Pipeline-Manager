"""Deterministic Phase 3 fixtures: a wired policy/versioning stack + synthetic
policy and version fixtures. Synthetic values only — no real incentives, rates,
write-downs, or windows."""
from __future__ import annotations

import datetime as _dt

from ..clock import to_utc_iso
from ..data.fixtures import Phase2
from ..ids import new_id
from .models import (CalculationFamily, CalculationVersion, ComparisonSpecificationVersion,
                     IdentityRuleVersion, ModelVersion, PolicyFamily, PolicyVersion)
from .store import PolicyStore

SCOPE = "store:HG"
TZ = "America/Chicago"


def local_date_to_utc(date_str, tz=TZ, end=False):
    """Convert a dealership-local date boundary to a UTC ISO instant."""
    from zoneinfo import ZoneInfo
    y, m, d = map(int, date_str.split("-"))
    t = _dt.time(23, 59, 59) if end else _dt.time(0, 0, 0)
    local = _dt.datetime(y, m, d, t.hour, t.minute, t.second, tzinfo=ZoneInfo(tz))
    return local.astimezone(_dt.timezone.utc).isoformat()


class Phase3:
    def __init__(self, db_path):
        self.p2 = Phase2(db_path)                 # migrates v1 + v2 + v3
        self.stack = self.p2.stack
        self.clock = self.stack.clock
        self.store = PolicyStore(self.stack.db.conn, self.clock)
        self.data = self.p2.store
        self.gov = self.stack.governor
        # owner principal (persisted id so reopen reuses it) with policy capabilities
        oid = self.stack.metadata.get("policy_owner_id")
        if oid is None:
            owner = self.stack.authn.register("Policy Owner", "pw")
            oid = owner.id
            self.stack.metadata.put_if_absent("policy_owner_id", oid)
            for cap in ("policy.propose", "policy.approve", "policy.activate", "scenario.override",
                        "probe.write"):
                self.stack.grant(oid, cap, "*")
        self.owner = oid
        # a limited principal WITHOUT scenario.override (negative tests)
        lid = self.stack.metadata.get("limited_id")
        if lid is None:
            lim = self.stack.authn.register("Limited User", "pw")
            lid = lim.id
            self.stack.metadata.put_if_absent("limited_id", lid)
            self.stack.grant(lid, "policy.propose", "*")
        self.limited = lid

    def reopen(self):
        return Phase3(self.stack.db.path)

    def close(self):
        self.stack.close()

    # ---- builders ----
    def family(self, category="FINANCIAL_ASSUMPTION", *, dims=None, default_resolution=None,
               name=None, approval_required=True):
        f = PolicyFamily(id=new_id("pf"), name=name or (category.lower()), category=category,
                         allowed_scope_dimensions=dims if dims is not None else ["store", "model", "model_year"],
                         default_resolution=default_resolution or {"mode": "unresolved"},
                         approval_required=approval_required)
        return self.store.add_family(f)

    def version(self, family_id, value, *, scope=None, lifecycle="ACTIVE", approval="approved",
                effective_start=None, effective_end=None, is_scenario=False, scenario_id=None,
                store_scope=SCOPE, version_number=1, start_inclusive=True, end_inclusive=False,
                revocation=None):
        v = PolicyVersion(id=new_id("pv"), family_id=family_id, version_number=version_number, value=value,
                          lifecycle_status=lifecycle, recorded_time=to_utc_iso(self.clock.now()),
                          scope=scope or {}, effective_start=effective_start, effective_end=effective_end,
                          start_inclusive=start_inclusive, end_inclusive=end_inclusive,
                          approval_state=approval, is_scenario=is_scenario, scenario_id=scenario_id,
                          store_scope=store_scope, revocation=revocation or {})
        return self.store.add_version(v)

    def calc_family(self, name="synthetic_calc"):
        return self.store.add_calc_family(CalculationFamily(id=new_id("cf"), name=name,
                                                            purpose="prove version resolution + reproducibility"))

    def calc_version(self, family_id, semver, *, lifecycle="registered", impl="rev", change=""):
        return self.store.add_calc_version(CalculationVersion(
            id=new_id("cv"), family_id=family_id, semver=semver, lifecycle_status=lifecycle,
            impl_revision=impl + "-" + semver, change_summary=change))

    def model_version(self, model_family="synthetic_model", version="1.0.0", *, status="registered"):
        return self.store.add_model_version(ModelVersion(
            id=new_id("mv"), model_family=model_family, version=version, status=status,
            purpose="prove registered-until-activated"))

    def identity_rule_version(self, rule_family="vehicle_identity", version="1.0.0", *,
                              status="registered", entity_types=None):
        return self.store.add_identity_rule_version(IdentityRuleVersion(
            id=new_id("irv"), rule_family=rule_family, version=version, status=status,
            entity_types=entity_types or ["vehicle"], rule_summary="synthetic identity rule",
            impl_revision="phase3"))

    def comparison_spec(self, version="1.0.0", *, status="registered"):
        return self.store.add_comparison_spec(ComparisonSpecificationVersion(
            id=new_id("csv"), version=version, status=status, prediction_type="synthetic_prediction",
            observation_type="synthetic_observation", subject_entity_type="vehicle",
            timing_rules={"window": "synthetic"}, matching_rules={"by": "subject"},
            unit_contract={"unit": "count"}))
