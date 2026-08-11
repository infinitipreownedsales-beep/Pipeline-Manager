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


def build_app(db_path=None, environment=None):
    """Build the operator application for local dealership use.

    Constructs the SAME fully-wired Phase 12 stack proven by the live-execution regression — the real
    Phase 5-7 executor registry + `LiveExecutionService` attached to the operator app — but with seeding
    OFF: no fixtures, no synthetic principals or records. Opens the configured `ELITE_DB_PATH` in place and
    applies only pending migrations (a no-op at v12); it never recreates, reseeds, or resets the database.
    `ELITE_SINGLE_OPERATOR_PILOT=1` enables the explicit self-approval pilot exception (unset for multi-user).
    """
    from ..release.fixtures import Phase12
    db_path = db_path or os.environ.get("ELITE_DB_PATH", "elite.db")
    pilot = Phase12(db_path, seed=False)          # migrates v1..v12 in place; wires the real live executor
    app = pilot.app
    app.environment = environment or os.environ.get("ELITE_ENV", "development")
    app.single_operator_pilot = _truthy(os.environ.get("ELITE_SINGLE_OPERATOR_PILOT"))
    app._pilot_stack = pilot                      # keep the wired stack (live executor + services) referenced
    return app


def main():
    app = build_app()
    host, port = "127.0.0.1", int(os.environ.get("ELITE_UI_PORT", "8010"))
    print(f"Elite Pipeline operator app on http://{host}:{port}/login  (env={app.environment})")
    make_server(app, host, port).serve_forever()


if __name__ == "__main__":
    main()
