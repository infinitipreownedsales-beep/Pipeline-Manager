# RUN INSTRUCTIONS

## Legacy Inventory Tool (Product A — unchanged)
```
python3 build/gen_pipeline_html.py           # -> Pipeline-Manager.html
# open Pipeline-Manager.html in a browser (offline)
python3 pipeline_manager/tests/test_engine.py
PYTHONPATH=. python3 pipeline_manager/tests/test_loaner_intel.py
```

## Elite Platform foundation (Phase 1)
Standard library only; no install step.

### Configuration (env; no secrets in source)
| Var | Required | Notes |
|---|---|---|
| `ELITE_ENV` | yes | one of `development` / `test` / `production` / `demo` |
| `ELITE_DB_PATH` | yes | path to the authoritative SQLite file |
| `ELITE_AUTH_SECRET` | yes (secret) | credential-hash pepper; provide via env/secret store |
| `ELITE_DEALERSHIP_TZ` | no | default `America/Chicago` (presentation only) |
| `ELITE_LOG_LEVEL` | no | default `INFO` |

Missing a required value is a **safe startup failure** (ConfigurationError); the
system never invents configuration.

### Bootstrap / migrate (example)
```python
from elite.db import Db
from elite.clock import SystemClock
db = Db("/path/to/elite.db", SystemClock())
db.migrate()          # applies pending migrations; tracked in migration_record
print("schema version:", db.version())
```

### Run the Phase 1 platform tests
```
PYTHONPATH=. python3 elite/tests/run_all.py
```

### Inspect the authoritative store
```
sqlite3 "$ELITE_DB_PATH" ".tables"
sqlite3 "$ELITE_DB_PATH" "SELECT * FROM migration_record;"
```

## Environment isolation
- Development and production are distinct `ELITE_ENV` values and cannot be silently
  confused; the resolved environment is stamped into `system_metadata` and appears in
  every structured log line.
- The Elite store (`ELITE_DB_PATH`, SQLite file) is independent of browser
  `localStorage`; clearing the browser does not affect authoritative records.
