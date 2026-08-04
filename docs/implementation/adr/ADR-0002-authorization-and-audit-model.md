# ADR-0002 — Authentication / authorization / audit model

- **Status:** Accepted (Phase 1)
- **Owning segments:** 11 (Governance, Authorization, Audit), 13 (Security)

## Decision
Keep **authentication, authorization, and audit** as three separate concerns, and
bind every governed authoritative write to its Audit Event **atomically**.

- **Authentication** (`auth.py`) proves identity only (salted + peppered PBKDF2).
  The pepper comes from configuration (`ELITE_AUTH_SECRET`, env), never source.
  Authentication success confers **no** authority.
- **Authorization** (`authz.py`) is an authoritative decision from
  Principal + Capability + Authority + Scope + **effective grant state**. It is a
  pure function callable **below the UI**; UI visibility is not the security boundary.
  Job titles are never hardcoded as permanent authority — authority is grant state,
  revocable and effective-checked.
- **Audit** (`audit.py`) is an **append-only** Audit Event log, distinct from
  Business Facts and Actual Events. Append-only is enforced **at the database level**
  by `BEFORE UPDATE`/`BEFORE DELETE` triggers, so an ordinary repository operation
  cannot modify history.
- **Governed actions** (`governance.py`) run the business write **and** the audit
  append inside one transaction. If the required audit write fails, the whole
  transaction rolls back — a governed action can never be reported successful
  without its Audit Event.

## Why
- The binding constraints require authn/authz separation, sub-UI enforcement, audit
  distinctness, and that a required audit failure prevents unsafe success.
- A single-transaction bind is the smallest correct way to guarantee the
  "no success without audit" contract without a distributed protocol.

## Consequences
- Revocation and scope are first-class; positive and negative authorization paths
  are tested.
- Correlation IDs flow through errors and logs; technical detail is never exposed to
  users and never logged as a secret.

## Non-goals
- No SSO/OAuth/session-server in Phase 1 (deployment is currently local/offline). The
  authentication mechanism is the minimum for the current deployment model and can be
  replaced behind the same interfaces.
