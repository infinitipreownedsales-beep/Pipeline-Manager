"""Local operator-app entrypoint: `PYTHONPATH=. python3 -m elite.ui.serve`.

Builds the operator application over the configured Elite store (`ELITE_DB_PATH`) and serves it with the
stdlib WSGI reference server for local dealership use. This is a convenience launcher only — no
production hardening, no live-source deployment (those are out of Phase 10 scope).
"""
from __future__ import annotations

import os

from .app import make_server


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def build_app(db_path=None):
    """Build the operator application for local dealership use.

    Constructs the SAME fully-wired Phase 12 stack proven by the live-execution regression — the real
    Phase 5-7 executor registry + `LiveExecutionService` attached to the operator app — but with seeding
    OFF and REAL runtime configuration threaded into the base Stack: the credential pepper from
    `ELITE_AUTH_SECRET`, a real system clock, and the explicit `ELITE_ENV` environment (never the fixture
    defaults `test-pepper` / FixedClock / TEST). Opens the configured `ELITE_DB_PATH` in place and applies
    only pending migrations (a no-op at v12); it never recreates, reseeds, or resets the database.
    `ELITE_SINGLE_OPERATOR_PILOT=1` enables the explicit self-approval pilot exception (unset for multi-user).
    """
    from ..release.fixtures import Phase12
    from ..fixtures import RuntimeConfig
    from ..environment import resolve_environment, resolve_pilot_scope, resolve_revision
    from ..clock import SystemClock
    from ..errors import ConfigurationError
    env = os.environ
    db_path = db_path or env.get("ELITE_DB_PATH", "elite.db")
    # Fail closed: never fall back to the test pepper for a real runtime.
    pepper = (env.get("ELITE_AUTH_SECRET") or "").strip()
    if not pepper:
        raise ConfigurationError(
            message="The operator application is not configured to start.",
            technical_detail="ELITE_AUTH_SECRET is required; refusing to start with a test credential pepper.")
    # Fail closed on the store scope too: the real runtime resolves ELITE_PILOT_SCOPE (no store:HG fallback).
    pilot_scope = resolve_pilot_scope(env)
    environment = resolve_environment(env)
    # Technical build/release identity for logs: ELITE_REVISION if set, else the environment value
    # (e.g. "pilot") — never the fixture "test" default.
    revision = resolve_revision(env, environment=environment)
    runtime = RuntimeConfig(pepper=pepper, clock=SystemClock(), environment=environment,
                            pilot_scope=pilot_scope, revision=revision)
    pilot = Phase12(db_path, seed=False, runtime=runtime)   # real pepper/clock/environment; no seeding
    app = pilot.app
    app.environment = runtime.environment.value            # authoritative runtime identity (e.g. "pilot")
    app.pilot_scope = runtime.pilot_scope                   # authoritative store scope for login/authorization
    app.single_operator_pilot = _truthy(env.get("ELITE_SINGLE_OPERATOR_PILOT"))
    app._pilot_stack = pilot                               # keep the wired stack (live executor + services) referenced
    app._p11 = getattr(pilot, "p11", None)                 # Phase 11 ops stack (import orchestrator) for Data uploads
    return app


def main():
    app = build_app()
    host, port = "127.0.0.1", int(os.environ.get("ELITE_UI_PORT", "8010"))
    print(f"Elite Pipeline operator app on http://{host}:{port}/login  (env={app.environment})")
    make_server(app, host, port).serve_forever()


if __name__ == "__main__":
    main()
