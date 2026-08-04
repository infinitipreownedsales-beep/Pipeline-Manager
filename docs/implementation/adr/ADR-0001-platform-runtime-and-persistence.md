# ADR-0001 — Platform runtime and authoritative persistence

- **Status:** Accepted (Phase 1)
- **Owning segments:** 02 (Architecture RC1 contract), 04 (Data/persistence), 13 (NFR/portability)

## Decision
Implement the Phase 1 platform foundation in **Python 3 (standard library only)**
with **SQLite** as the authoritative durable store.

## Why
- **Smallest correct.** The repository already ships a tested Python backbone
  (`pipeline_manager/`). Python stdlib provides everything Phase 1 needs —
  `sqlite3` (durable ACID storage, transactions, triggers, optimistic concurrency),
  `hashlib`/`hmac` (credential hashing), `uuid`/`os.urandom` (IDs), `datetime`
  (UTC clock), `unittest` (deterministic harness) — with **zero new dependencies**.
- **No framework expansion / no microservices**, per the binding constraints.
- **Durable and not browser-local.** SQLite is an on-disk file that survives process
  restart and is independent of the 19 `pm_*` browser-local keys. This satisfies
  "browser localStorage must not become the new authoritative repository."
- **Replaceable.** All access goes through repository contracts (ABCs), so the store
  can be swapped later without touching callers.

## Consequences
- Authoritative records live in a single SQLite file at `ELITE_DB_PATH`.
- Concurrency is optimistic (version columns); idempotency via an idempotency table.
- A later phase may migrate to a networked database purely by providing new
  repository implementations behind the existing contracts.

## Non-goals
- No domain schemas (Demand/Supply/CPO/Loaner/Demo) in Phase 1.
- This is a **technical** choice; it does not become permanent business architecture.
