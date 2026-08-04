# PHASE 1 TRACEABILITY — platform foundation → specification

Maps each Phase 1 platform capability to its owning specification segment and the
requirement family it serves. Exact requirement-ID binding against the canonical
DOCX is a review step (families named here; IDs to be confirmed in review — the
DOCX is authoritative, see `requirement_index.json`).

| Phase 1 capability | Module(s) | Owning segment | Families | Acceptance tests |
|---|---|---|---|---|
| Environment identity (explicit, no default) | `environment.py` | 02, 13 | ARCH, NFR, CONST | 2, 2b |
| Config load + validation + safe startup failure | `config.py` | 05, 13 | POL, CAL, NFR, SEC | 1, 2b, 2c, 3 |
| Secret hygiene (env-only, redaction) | `config.py`, `logging_.py` | 13 | SEC, NFR | 3, 18b |
| Stable internal identifiers | `ids.py` | 04 | DATA, DM, IDRULE | 4 |
| Controlled UTC clock + dealership presentation | `clock.py` | 05, 12 | CAL, DT, UX | 5 |
| Typed error foundation + correlation IDs | `errors.py` | 13 | ERR, NFR, SEC | 19 |
| Durable persistence (SQLite) + restart survival | `db.py`, `repositories.py` | 04, 13 | DATA, NFR | 6, 7, 8, 20 |
| Schema migration foundation | `db.py` (`migrate`) | 04 | DATA, TRANS | 20 |
| Idempotency | `repositories.py`, `governance.py` | 04, 02 | DATA, ARCH | 9 |
| Optimistic concurrency / versioned writes | `repositories.py` | 04 | DATA | 10 |
| Repository contracts (replaceable persistence) | `repositories.py`, `audit.py` | 02, 04 | ARCH, DATA | 8 |
| Authentication foundation | `auth.py` | 11, 13 | GOV, AUTH, SEC | (authn≠authz) |
| Authorization (Principal/Capability/Authority/Scope) | `authz.py` | 11 | GOV, AUTH | 11, 12, 13, 14 |
| Append-only Audit Events (distinct record family) | `audit.py`, `db.py` | 11 | AUDIT, GOV | 15, 17, 18 |
| Governed action: atomic business + audit | `governance.py` | 11 | GOV, AUDIT | 15, 16 |
| Structured logging (distinct from audit) | `logging_.py` | 13 | NFR, SEC | 18, 18b |
| Deterministic test + fixture foundation | `fixtures.py`, `tests/` | 14 | TEST, GATE | all |
| Legacy preservation invariants | `tests/test_legacy_guard.py` | 15 | DELIVERY, GATE | 21, 22, 22b |

## Notes
- Records kept conceptually distinct per spec: **Audit Event** ≠ **Business Fact** ≠
  **Actual Event** (`models.py` documents the boundary; only Audit Event is
  implemented in Phase 1).
- No domain business rule (Demand/Supply/CPO/PPO/CTP/Loaner/Demo/Learning) was
  implemented or modified in Phase 1.
