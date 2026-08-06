# ADR-0035 — Operator presentation architecture (stdlib WSGI)

- **Status:** Accepted (Phase 10)
- **Owning segments:** 10 (User Experience)

## Decision
The operator application is a server-rendered Python app built on the standard library only (`wsgiref`,
`html`, `http.cookies`, `secrets`, `urllib.parse`) — no third-party web framework and no new
dependencies, consistent with the whole Elite build. `App` is a plain WSGI callable with an in-process
`handle()` for socket-free testing; a small `Router`, server-side sessions, a CSRF check, and a safe
error boundary are the entire framework. HTML is rendered by explicit helpers with output encoding; all
CSS is inline and self-hosted under a strict `default-src 'self'` CSP; there is no client-side JavaScript.

## Why
The platform is stdlib + SQLite with no framework by design. A minimal WSGI app keeps that invariant,
stays trivially testable at the route level, and avoids a broad framework rewrite. Server rendering keeps
all logic on the authoritative side and makes it structurally hard for the browser to become a second
source of truth.

## Consequences
- Every screen and mutation is a testable view function driven in-process by `ui.fixtures.Client`.
- No JS means no duplicated backend logic in the browser (ADR-0036) and a smaller attack surface.
- Richer interactivity and full visual design are deferred beyond Phase 10 by contract.
