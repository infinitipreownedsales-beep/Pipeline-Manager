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

### Run the platform tests (Phase 1 through Phase 10)
```
PYTHONPATH=. python3 elite/tests/run_all.py
# focused BUG-CPO-002 regressions (Phase 4 synthetic + Phase 5 end-to-end CPO workflow):
PYTHONPATH=. python3 -m unittest elite.tests.test_phase4_bug_cpo_002 elite.tests.test_phase5_bug_cpo_002_e2e -v
# focused Service Loaner zero-mile-rented monitoring regression:
PYTHONPATH=. python3 -m unittest elite.tests.test_phase6_monitoring.TestZeroMileRegression -v
# focused Executive Demo Best Overall regression:
PYTHONPATH=. python3 -m unittest elite.tests.test_phase7_preference_bestoverall.TestBestOverallRegression -v
# focused learning-governance regression (Learning proposes; no change without approved Calibration):
PYTHONPATH=. python3 -m unittest elite.tests.test_phase8_learning_governance_regression -v
# focused governed-decision + authority-administration regressions:
PYTHONPATH=. python3 -m unittest elite.tests.test_phase9_governed_decision_regression \
    elite.tests.test_phase9_authority_admin_regression -v
# focused operator-workflow + presentation-integrity regressions (Phase 10):
PYTHONPATH=. python3 -m unittest elite.tests.test_phase10_operator_workflow_regression \
    elite.tests.test_phase10_presentation_integrity_regression -v
```

### Phase 2 — data/identity/facts (example)
```python
from elite.data.fixtures import Phase2
p = Phase2("/path/to/elite.db")          # migrates v1 + v2; registers example sources
batch = p.ingest_dms([{"stock_number":"N1","vin":"1GNSKBKC5FR000001","model":"qx80"}])
print(batch.validated_snapshot_type, batch.accepted_count)
# raw preserved + normalized separately inspectable:
obs = p.store.list_observations(batch.id)[0]
print(obs.raw_values, obs.normalized_values)
```
Inspect Phase 2 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT id,validated_snapshot_type,accepted_count,rejected_count FROM import_batch;"
sqlite3 "$ELITE_DB_PATH" "SELECT fact_type,status FROM business_fact;"
```

### Phase 3 — policy / calculation versioning (example)
```python
from elite.policy.fixtures import Phase3
from elite.policy import lifecycle
from elite.policy.resolution import resolve
p = Phase3("/path/to/elite.db")          # migrates v1 + v2 + v3; registers example principals
f = p.family(category="FINANCIAL_ASSUMPTION", dims=["store", "model"])
v = p.version(f.id, {"kind": "percentage", "value": 10, "denominator": "msrp"},
              scope={"store": "HG"}, lifecycle="ACTIVE", effective_start="2020-01-01T00:00:00+00:00")
r = resolve(p.store, f, subject_scope={"store": "HG"}, at_time="2026-06-01T00:00:00+00:00")
print(r.status, r.value)                 # RESOLVED {...}
```
Inspect Phase 3 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT category FROM policy_family;"
sqlite3 "$ELITE_DB_PATH" "SELECT lifecycle_status,is_scenario FROM policy_version;"
sqlite3 "$ELITE_DB_PATH" "SELECT target_type,action FROM version_activation_history;"
```

### Phase 4 — New Inventory planning (example)
```python
from elite.newinv.fixtures import Phase4, SCOPE, AT
from elite.newinv.output import build_slice
p = Phase4("/path/to/elite.db")                 # migrates v1..v4; wires the domain services
c = p.combination(model="QX80", exterior_color="BLACK")
p.seed_retail(c, {"2025-09": 2, "2025-10": 2, "2025-11": 2, "2025-12": 2, "2026-01": 2, "2026-02": 2})
p.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2, "snapshot": "full"}
                        for m in ["2025-09","2025-10","2025-11","2025-12","2026-01","2026-02"]])
d = p.issue_demand(c)                            # Demand is supply-blind
plan = p.issue_plan(c, d, coverage_target=2)    # Need/Excess (monotone in qualifying supply)
print(build_slice(p.store, plan.id)["call"])    # first operational output slice
```
Inspect Phase 4 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT model,canonical_identity FROM sellable_combination;"
sqlite3 "$ELITE_DB_PATH" "SELECT planning_state,need,excess,qualifying_supply FROM inventory_plan_result;"
sqlite3 "$ELITE_DB_PATH" "SELECT output_type,calculation_version FROM issued_planning_output;"
```

### Phase 5 — production / supply workflows (example)
```python
from elite.workflow.fixtures import Phase5, SCOPE
p = Phase5("/path/to/elite.db")               # migrates v1..v5; wires workflow services + principals
c, d, plan = p.need_combo(exterior_color="BLACK")     # Phase 4 Demand + Need (need > 0)
w = p.cpo.propose(p.full, SCOPE, production_order_id="po1", combination_id=c.id, arrival_month="2026-10")
r = p.cpo.approve(p.full, SCOPE, p.wf.get_workflow(w.id))     # governed; one Committed Supply
print(r["outcome"])                            # COMMITMENT_CREATED
print(p.p4.issue_plan(c, d, coverage_target=2).need)          # Need decreased by exactly one
```
Inspect Phase 5 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT workflow_type,lifecycle_status FROM supply_workflow;"
sqlite3 "$ELITE_DB_PATH" "SELECT outcome,prior_qualifying,new_qualifying FROM commitment_reconciliation_result;"
sqlite3 "$ELITE_DB_PATH" "SELECT from_status,to_status,action FROM supply_workflow_transition;"
```

### Phase 6 — Service Loaner domain (example)
```python
from elite.loaner.fixtures import Phase6
from elite.loaner.output import build_unit_slice
p = Phase6("/path/to/elite.db")               # migrates v1..v6; wires SL services + principals
b = p.snapshot.ingest_fleet([{"vin": "1GNSKBKC5FR000001", "rental_status": "rented",
                              "in_service_date": "2025-01-01", "checkout_mileage": "0"}], snapshot_type="full")
print(p.snapshot.reconcile(b, [{"vin": "1GNSKBKC5FR000001", "rental_status": "rented"}]))   # membership by VIN
u = p.store.unit_for_vin("1GNSKBKC5FR000001", "store:HG")
p.dating.record_mileage(u, "0")
print(p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30).prompt)   # zero-mile-rented alert
```
Inspect Phase 6 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT membership_state,current_rental_state FROM service_loaner_unit;"
sqlite3 "$ELITE_DB_PATH" "SELECT rule,status,prompt FROM service_loaner_monitoring_alert;"
sqlite3 "$ELITE_DB_PATH" "SELECT confirming_principal,confirmed_at FROM used_cars_receipt;"
```

### Phase 7 — Executive Demo domain (example)
```python
from elite.execdemo.fixtures import Phase7
from elite.execdemo.output import build_unit_slice, portfolio_slice
from elite.workflow.fixtures import SCOPE
p = Phase7("/path/to/elite.db")               # migrates v1..v7; wires Executive Demo services + principals
c, plan = p.nr_plan(position="need")          # a New Retail combination in Need (Phase 4 plan)
u = p.candidate_unit("1HGCM82633A100001", c.id)
p.p4.seed_current(c, [{"vehicle_unit_id": u.vehicle_unit_id, "state": "available_unsold",
                      "identity_status": "resolved"}])
p.units.propose_designation(p.full, SCOPE, u)
p.units.approve_designation(p.full, SCOPE, p.store.get_unit(u.id))
p.units.execute_designation(p.full, SCOPE, p.store.get_unit(u.id))   # membership + removes NR supply once
# Best Overall over the full objective (not cheapest / not highest-benefit):
bp = p.portfolio.best_overall(SCOPE, required_size=p.portfolio.current_active(SCOPE) + 1, candidates=[
    {"vehicle_unit_id": "cheap", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
     "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}},
    {"vehicle_unit_id": "fit", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 4},
     "executive_demo_benefit": {"value": 6}, "portfolio_fit": {"value": 12}}])
print(portfolio_slice(bp)["best_overall"]["pick"]["vehicle_unit_id"])   # -> "fit"
```
Inspect Phase 7 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT membership_state,active_fleet_supply_ref FROM executive_demo_unit;"
sqlite3 "$ELITE_DB_PATH" "SELECT outcome,supply_ref FROM executive_demo_reconciliation_result;"
sqlite3 "$ELITE_DB_PATH" "SELECT need,selected,best_overall FROM executive_demo_portfolio_plan;"
sqlite3 "$ELITE_DB_PATH" "SELECT confirming_principal,confirmed_at FROM executive_demo_used_cars_receipt;"
```

### Phase 8 — learning + calibration (example)
```python
from elite.learning.fixtures import Phase8
from elite.learning import output
p = Phase8("/path/to/elite.db")               # migrates v1..v8; wires learning services + principals
pred, obs, pair, err = p.chain(predicted=10, actual=4)   # Prediction->Observation->Pairing->Error
print(pair.pairing_status, err.signed_error, err.materiality)   # PAIRED -6.0 material/immaterial
# Learning proposes; nothing changes until an authorized activation:
cal = p.calibration.propose(p.proposer, "store:HG", target_type="calculation_version",
                            target_family=p.calc_target_family, proposed_change={"semver": "2.0.0"},
                            affected_domains=["new_inventory_forecasting"])
# ... start_review -> require_validation -> mark_validated -> approve -> activate (each governed, audited)
```
Inspect Phase 8 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT prediction_type,resolution_status,calculation_version FROM prediction;"
sqlite3 "$ELITE_DB_PATH" "SELECT pairing_status,comparison_spec_version FROM prediction_observation_pairing;"
sqlite3 "$ELITE_DB_PATH" "SELECT signed_error,materiality,resolution_status FROM prediction_error;"
sqlite3 "$ELITE_DB_PATH" "SELECT review_state,target_type,activation_ref FROM calibration_proposal;"
sqlite3 "$ELITE_DB_PATH" "SELECT activated_version_kind,scheduled FROM calibration_activation;"
```

### Phase 9 — governance + operational control (example)
```python
from elite.govern.fixtures import Phase9
from elite.govern import output
p = Phase9("/path/to/elite.db")               # migrates v1..v9; wires governance services + principals
it = p.item(domain="new_inventory", rec="rec_1")         # a workspace item REFERENCING a domain rec
r = p.decisions.issue(p.decider, "store:HG", it, disposition="ACCEPT", selected_action="order")
a = p.approvals.approve(p.approver, "store:HG", r["decision"])["approval"]   # distinct authority
e = p.execution.authorize(p.executor, "store:HG", r["decision"], a, execution_capability="ni.execute",
                          expected_action="order", domain_execute_fn=lambda conn: "domain_exec_ref")
p.execution.complete(p.executor, "store:HG", e["execution"], domain_completion_ref="done")
print(p.execution.reconcile(r["decision"]))              # COMPLETED
print(output.decision_inbox(p.store)[0]["call"])         # workspace summary state
```
Inspect Phase 9 records:
```
sqlite3 "$ELITE_DB_PATH" "SELECT workspace_state,recommendation_ref,decision_ref FROM decision_workspace_item;"
sqlite3 "$ELITE_DB_PATH" "SELECT disposition,override,scenario_id FROM governed_decision;"
sqlite3 "$ELITE_DB_PATH" "SELECT outcome FROM decision_execution_reconciliation;"
sqlite3 "$ELITE_DB_PATH" "SELECT classification,blockers FROM domain_readiness_assessment;"
sqlite3 "$ELITE_DB_PATH" "SELECT delegator,delegate,capability,active FROM authority_delegation;"
```

### Phase 10 — operator experience + presentation layer (example)
The operator application is a server-rendered stdlib WSGI app (`wsgiref`; **no new dependencies**). It
reads the authoritative Phase 1-9 records and never recomputes domain logic; every mutation routes
through the governed services.

Serve it locally:
```
export ELITE_ENV=development
export ELITE_DB_PATH=/path/to/elite.db
PYTHONPATH=. python3 -m elite.ui.serve            # serves the operator app on http://127.0.0.1:8010
# then open http://127.0.0.1:8010/login  (sign in with an operator id + password + store scope)
```
Drive it in-process (no socket) — the same routes and services the browser uses:
```python
from elite.ui.fixtures import Phase10
p = Phase10("/path/to/elite.db")                  # migrates v1..v10; builds the App over Phase 9
c = p.login(p.op_full)                            # in-process client (auto-injects the CSRF token)
print(c.get("/").status)                          # 200 — Decision Inbox (counts reconcile to source)
print(c.get("/new-inventory").status)             # 200 — domain workspace (numbers read from Phase 4)
# a below-UI unauthorized operator is refused regardless of navigation visibility:
print(p.login(p.op_unauth).get("/").status)       # 403
```
Presentation state is non-authoritative (migration v10) — deleting it changes no business record:
```
sqlite3 "$ELITE_DB_PATH" "DELETE FROM operator_view_preference;"   # no Decision/Need/Supply effect
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
