"""Phase 11 — Operational Hardening, Real-Source Integration, and Controlled Pilot Readiness.

This package hardens the working Phase 10 application for a controlled dealership pilot ALONGSIDE the
legacy tool. It adds an adapter layer over Phase 2 ingestion, import orchestration, freshness,
operational reconciliation, scheduling, restart/failure recovery, durability, backup/restore, health
checks, observability, performance baselines, security hardening, configuration, pilot mode, a
non-authoritative parallel-run comparison, and operator feedback.

Binding rule: NOTHING here holds business truth. Source data is evidence, not automatically truth; raw
source stays preserved in the Phase 2 records; import success is not acceptance, acceptance is not
reconciliation, reconciliation is not automatic business action; no cutover occurs in Phase 11.
"""
