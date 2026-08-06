# ADR-0044 — Backup and restore

## Status
Accepted (Phase 11).

## Context
The pilot needs consistent, verifiable backups and a proven restore path — without automating a destructive
production restore.

## Decision
Use SQLite's online backup API for a transactionally consistent copy; timestamp, content-hash, and
integrity-verify each backup; record metadata (schema version + authoritative counts). Restore validation
copies a backup aside, confirms it starts, the migration version matches, and counts reproduce. Retention
marks old backups expired (record preserved); backups never replace raw source-file retention. Phase 11
automates no destructive production restore — restore is a manual, reviewed action.

## Consequences
A backup is provably restorable; a failed backup raises a visible alert; historical records and migrations
are preserved across a restore.
