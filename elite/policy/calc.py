"""Synthetic calculation + reproducibility.

NO domain formula lives here — only minimal synthetic functions whose BEHAVIOR is
keyed to a Calculation Version, used to prove that (a) a behavior change requires a
distinct version, and (b) a preserved reproducibility package replays to the same
result while a current recalculation under a new version does not rewrite the prior
issued result.
"""
from __future__ import annotations

import hashlib
import json

from ..clock import to_utc_iso
from ..errors import DependencyError
from ..ids import new_id
from .models import ReproducibilityPackage

# Synthetic behaviors keyed by semantic version. Each is deterministic.
_BEHAVIORS = {
    "1.0.0": lambda inputs, rate: {"result": inputs["a"] + rate},
    "2.0.0": lambda inputs, rate: {"result": inputs["a"] * rate},   # different BEHAVIOR -> distinct version
}


def output_checksum(output) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest()


def run(calc_version, inputs: dict, policy_value: dict):
    fn = _BEHAVIORS.get(calc_version.semver)
    if fn is None:
        raise DependencyError(technical_detail=f"no synthetic behavior for calc version {calc_version.semver}")
    rate = policy_value.get("value", policy_value.get("rate", 0))
    return fn(inputs, rate)


def issue_result(store, *, clock, calc_version, inputs, policy_versions, policy_value,
                 identity_rule_version=None, model_version=None, comparison_spec=None,
                 scenario_id=None, dealership_tz="America/Chicago", implementation_revision="phase3"):
    """Run the calc and preserve a reproducibility package pinning every version + input.
    Returns (output, package)."""
    output = run(calc_version, inputs, policy_value)
    pkg = store.add_reproducibility(ReproducibilityPackage(
        id=new_id("rep"),
        refs={"calculation_version": calc_version.id, "calc_semver": calc_version.semver,
              "policy_versions": list(policy_versions), "policy_value": policy_value, "inputs": inputs,
              "identity_rule_version": identity_rule_version, "model_version": model_version,
              "comparison_specification_version": comparison_spec, "scenario": scenario_id},
        dealership_tz=dealership_tz, calculation_timestamp=to_utc_iso(clock.now()),
        implementation_revision=implementation_revision, output_reference=output_checksum(output)))
    return output, pkg


def replay(store, package_id):
    """Recompute from the preserved package + inputs. Must reproduce the same output."""
    pkg = store.get_reproducibility(package_id)
    if pkg is None:
        raise DependencyError(technical_detail="reproducibility package not found")
    calc_version = store.get_calc_version(pkg.refs["calculation_version"])
    output = run(calc_version, pkg.refs["inputs"], pkg.refs["policy_value"])
    return output, (output_checksum(output) == pkg.output_reference)
