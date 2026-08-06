"""Phase 10 — Operator Experience and Presentation Layer.

A server-rendered operator application (stdlib WSGI; no new dependencies) built strictly on the Phase 9
output slices and Phase 1-8 authoritative read models. It READS authoritative records and never recomputes
domain logic; every mutation routes through the governed Phase 1-9 services; browser/localStorage state is
never authoritative; below-UI authorization + scope are never bypassed.
"""
