# ADR-0041 — Source adapters over Phase 2 ingestion

## Status
Accepted (Phase 11).

## Context
The controlled pilot must accept realistically structured dealership source files (delimited exports,
spreadsheet exports as CSV, stable JSON, and governed manual inputs where no automated source exists)
without adding a second business-logic layer or fabricating source access.

## Decision
Add a thin adapter layer (`elite/ops/adapters.py`) that ONLY parses a payload into the Phase 2 canonical
ingestion contract (`rows` + preserved `raw_text` + ingestion parameters). Adapters never write domain
results, resolve identity, or compute domain math — Phase 2 ingestion and the Phase 4-9 domains own that.
Schema detection is explicit; unsupported schema, missing required column, invalid encoding, and fully
malformed delimiters fail safely (`ValidationError`). Encoding/delimiter/date/decimal/currency/blank
handling is deterministic; blank is never coerced to zero (Phase 2 owns the sentinels). Every row keeps its
source line for traceability; the adapter version is recorded on every import run.

## Consequences
Source-specific parsing stays separate from domain interpretation; real-source irregularities surface as
visible validation outcomes, never hidden fixes. A corrected adapter bumps its version and preserves prior
import history.
