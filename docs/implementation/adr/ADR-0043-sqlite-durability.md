# ADR-0043 — SQLite durability for the controlled pilot

## Status
Accepted (Phase 11).

## Context
A single-node pilot needs documented, tested durability without changing the platform architecture.

## Decision
Standardize foreign keys ON, WAL journal mode, `synchronous=NORMAL` (safe under WAL), and a busy timeout so
a briefly locked database waits rather than erroring. Provide executable integrity checks and startup
validation (migrations current + integrity ok + foreign keys enforced). Durability is not changed without
evidence and tests.

## Consequences
Concurrent reads work under WAL; a committed transaction survives restart; a corrupt store is detectable at
startup. Stricter `synchronous=FULL` remains available if a pilot host requires it.
