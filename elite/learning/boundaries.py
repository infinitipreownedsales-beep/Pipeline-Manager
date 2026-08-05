"""Cross-domain learning boundaries — domain ownership for learning records.

Learning stays domain-aware. A Learning Signal owned by one domain cannot directly mutate another
domain's behavior; New Inventory forecast Error must not alter Service Loaner economics; a Service
Loaner resale outcome must not alter New Inventory Demand; an Executive Demo outcome must not redefine
Service Loaner rules. Cross-domain evidence may support a Calibration Proposal ONLY when the
relationship is explicit and approved. No universal ranker / single global learning score exists.
"""
from __future__ import annotations

from ..errors import ValidationError

LEARNING_DOMAINS = (
    "new_inventory_forecasting", "production_workflow_timing", "cpo_ppo", "dealer_trade", "ctp",
    "service_loaner", "executive_demo",
)


def assert_same_domain(signal_domain, target_domain, *, approved_cross_domain=False):
    """A Learning Signal may inform a Calibration target in another domain only under an explicit,
    approved cross-domain relationship. Otherwise a cross-domain application is rejected."""
    if signal_domain == target_domain:
        return True
    if approved_cross_domain:
        return True
    raise ValidationError(
        message="A learning signal cannot change another domain automatically.",
        technical_detail=f"cross-domain application {signal_domain}->{target_domain} without approved relationship")
