"""Local operator-app entrypoint: `PYTHONPATH=. python3 -m elite.ui.serve`.

Builds the operator application over the configured Elite store (`ELITE_DB_PATH`) and serves it with the
stdlib WSGI reference server for local dealership use. This is a convenience launcher only — no
production hardening, no live-source deployment (those are out of Phase 10 scope).
"""
from __future__ import annotations

import os

from .app import App, make_server


def build_app(db_path=None, environment=None):
    from ..govern.fixtures import Phase9
    db_path = db_path or os.environ.get("ELITE_DB_PATH", "elite.db")
    p9 = Phase9(db_path)
    return App(p9, environment=environment or os.environ.get("ELITE_ENV", "development"))


def main():
    app = build_app()
    host, port = "127.0.0.1", int(os.environ.get("ELITE_UI_PORT", "8010"))
    print(f"Elite Pipeline operator app on http://{host}:{port}/login  (env={app.environment})")
    make_server(app, host, port).serve_forever()


if __name__ == "__main__":
    main()
