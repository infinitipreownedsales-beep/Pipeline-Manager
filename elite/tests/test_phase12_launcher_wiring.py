"""Phase 12 launcher-wiring regression.

Proves that the ACTUAL shipped launcher — `elite.ui.serve.build_app` (what `python -m elite.ui.serve`
runs) — constructs the same fully-wired Phase 12 application proven by the live-execution regression, over
the configured ELITE_DB_PATH, WITHOUT seeding:

  * opens a v12 database in place without reseeding or recreating it (no synthetic principals/grants/jobs);
  * constructs the Phase 12-wired app with a REAL live executor attached (registry bound to Phase 5-7);
  * invokes an ACTUAL Executive Demo executor through the UI (state changes once — the real domain method);
  * never uses the domain-reference fallback when a real binding exists;
  * preserves idempotency (replay) and restart durability;
  * leaves the permanent database schema at v12.
"""
import os
import tempfile
import unittest

from elite.db import connect, current_version
from elite.ops.fixtures import RestartedStore
from elite.release.fixtures import SCOPE
from elite.release.models import CAPS
from elite.ui.fixtures import Client
from elite.ui.serve import build_app

LAUNCH_CAPS = [
    "workspace.view", "workspace.review", "decision.issue", "decision.approve", "execution.authorize",
    CAPS["EXECUTE_LIVE"], CAPS["SHADOW_SET"], "domain.execute",
    "executive_demo.retirement.propose", "executive_demo.retirement.approve",
    "executive_demo.retirement.execute", "executive_demo.return_to_retail.confirm",
]


class TestLauncherWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "elite.db")

    def test_launcher_is_phase12_wired_without_seeding(self):
        os.environ["ELITE_SINGLE_OPERATOR_PILOT"] = "1"
        app = build_app(db_path=self.db, environment="pilot")

        # 1. opens a v12 database WITHOUT seeding: zero synthetic principals / grants / scheduled jobs
        conn = app.stack.db.conn
        self.assertEqual(current_version(conn), 12)
        self.assertEqual(conn.execute("SELECT COUNT(*) c FROM principal").fetchone()["c"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) c FROM capability_grant").fetchone()["c"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) c FROM scheduled_job").fetchone()["c"], 0)
        # no dealership domain records either
        self.assertEqual(conn.execute("SELECT COUNT(*) c FROM executive_demo_unit").fetchone()["c"], 0)

        # 2. Phase 12-wired: a REAL live executor is attached, bound to the actual Phase 5-7 registry
        self.assertIsNotNone(getattr(app, "live_executor", None))
        self.assertTrue(app.live_executor.registry.has("executive_demo.retirement.execute"))
        self.assertFalse(app.live_executor.registry.is_synthetic("executive_demo.retirement.execute"))
        self.assertTrue(app.single_operator_pilot)

        p = app._pilot_stack
        # a real operator (no synthetic seeding — created explicitly like a real bootstrap)
        kyle = app.stack.authn.register("Kyle (pilot)", "pw").id
        for cap in LAUNCH_CAPS:
            app.stack.grant(kyle, cap, SCOPE)
        # enable live execution for the domain (governed shadow-mode change)
        p.shadow.set_mode(principal=kyle, scope=SCOPE, domain="executive_demo", mode="EXECUTION_PILOT",
                          reason="pilot execution enabled")

        # a real ACTIVE unit advanced to RETIREMENT_APPROVED via the real Phase 7 lifecycle
        unit = p.p7.make_active("1HGCM82633AB00001", scope=SCOPE)
        p.p7.retirement.propose(kyle, SCOPE, unit)
        unit = p.p7.store.get_unit(unit.id)
        p.p7.retirement.approve(kyle, SCOPE, unit)

        # a governed Decision, approved under the single-operator pilot exception, all through the UI
        item = p.p9.item(domain="executive_demo", rec="rec_launch", scope=SCOPE)
        tok = app.login(kyle, "pw", SCOPE)
        c = Client(app, tok)
        self.assertEqual(c.post("/item/" + item["id"] + "/decide",
                                {"disposition": "ACCEPT", "selected_action": "retire",
                                 "alternatives": "retire,hold", "_idem": "lw-d1"}).status, 303)
        dec = p.p9.store.decisions_for_item(item["id"])[0]
        self.assertEqual(c.post("/approval/" + dec["id"] + "/approve", {"_idem": "lw-a1"}).status, 303)

        # 3-4. bind the REAL executor and authorize execution THROUGH THE UI on the launcher's app;
        # the real domain method runs (state changes once) — NOT the domain-reference fallback
        def real_call(principal, sc):
            cur = p.p7.store.get_unit(unit.id)
            if cur.membership_state != "RETIREMENT_APPROVED":
                return cur.retirement_event or ("edrev_" + unit.id)
            p.p7.retirement.execute(principal, sc, cur, disposition="new_retail")
            return p.p7.store.get_unit(unit.id).retirement_event or ("edrev_" + unit.id)
        app.live_executor.bind(dec["id"], domain="executive_demo",
                               action="executive_demo.retirement.execute", real_call=real_call,
                               expected_action="retire")
        self.assertTrue(app.live_executor.has_binding(dec["id"]))
        self.assertEqual(c.post("/execution/" + dec["id"] + "/authorize", {"_idem": "lw-x1"}).status, 303)
        # the ACTUAL executor ran (the fallback would never change domain state)
        self.assertEqual(p.p7.store.get_unit(unit.id).membership_state, "RETURNED_TO_NEW_RETAIL")
        self.assertTrue(p.p9.store.execauths_for(dec["id"]))

        # 5. never uses the fallback when a real binding exists (no synthetic domain_exec:: reference)
        ea = p.p9.store.execauths_for(dec["id"])[-1]
        self.assertNotIn("domain_exec::", ea["domain_execution_ref"] or "")

        # 6. idempotency — replay does not duplicate
        state1 = p.p7.store.get_unit(unit.id).membership_state
        c.post("/execution/" + dec["id"] + "/authorize", {"_idem": "lw-x1"})
        self.assertEqual(p.p7.store.get_unit(unit.id).membership_state, state1)

        # 7. restart durability + schema stays at v12
        execs = conn.execute("SELECT COUNT(*) c FROM execution_authorization").fetchone()["c"]
        q = RestartedStore(app.stack.db.path, app.stack.clock)
        try:
            self.assertEqual(q.table_count("execution_authorization"), execs)
        finally:
            q.close()
        self.assertEqual(current_version(connect(self.db)), 12)

    def test_relaunch_opens_in_place_without_reset(self):
        # first launch creates v12 + system scaffolding; a real principal is added
        app1 = build_app(db_path=self.db)
        kyle = app1.stack.authn.register("Kyle (pilot)", "pw").id
        v1 = current_version(app1.stack.db.conn)
        # second launch (the shipped command run again) opens the SAME file in place — no reset, no reseed
        app2 = build_app(db_path=self.db)
        conn2 = app2.stack.db.conn
        self.assertEqual(current_version(conn2), v1)                       # still v12
        self.assertEqual(current_version(conn2), 12)
        # the real principal persists and is not duplicated; no synthetic principals introduced
        names = [r["display_name"] for r in conn2.execute("SELECT display_name FROM principal")]
        self.assertEqual(names, ["Kyle (pilot)"])                         # exactly the one real account


if __name__ == "__main__":
    unittest.main()
