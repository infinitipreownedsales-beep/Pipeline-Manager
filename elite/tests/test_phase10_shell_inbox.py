"""Phase 10 acceptance — application shell + context (1-8), Decision Inbox (9-12),
recommendation detail + Raw History (13-19)."""
import os
import tempfile
import unittest

from elite.ui.fixtures import OTHER_SCOPE, Phase10
from elite.workflow.fixtures import SCOPE


class TestPhase10ShellInbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase10(self.dbp)
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    # ---- shell + context (1-8) --------------------------------------------
    def test_01_shell_renders(self):
        r = self.full.get("/")
        self.assertEqual(r.status, 200)
        self.assertIn("Elite Pipeline", r.body)
        self.assertIn('role="banner"', r.body)          # semantic shell
        self.assertIn('role="navigation"', r.body)

    def test_02_authenticated_principal_shown(self):
        self.assertIn("Operator Full", self.full.get("/").body)

    def test_03_scope_shown(self):
        self.assertIn("store:HG", self.full.get("/").body)

    def test_04_unauthorized_navigation_rejected(self):
        unauth = self.p.login(self.p.op_unauth)
        self.assertEqual(unauth.get("/").status, 403)

    def test_05_out_of_scope_not_exposed(self):
        # operator holds grants only at store:WEST; signing into store:HG exposes nothing
        oos = self.p.login(self.p.op_otherscope, scope=SCOPE)
        self.assertEqual(oos.get("/").status, 403)

    def test_06_revoked_authority_rejected(self):
        rid = self.p.stack.authn.register("TempOp", "pw").id
        g = self.p.stack.grant(rid, "workspace.view", "*")
        c = self.p.login(rid)
        self.assertEqual(c.get("/").status, 200)
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        self.assertEqual(c.get("/").status, 403)          # revoked -> immediately rejected

    def test_07_freshness_visible(self):
        self.assertIn("Fresh as of", self.full.get("/").body)

    def test_08_stale_does_not_look_current(self):
        body = self.full.get("/").body
        self.assertIn("Stale", body)                      # the stale seeded item is flagged

    # ---- Decision Inbox (9-12) --------------------------------------------
    def test_09_counts_reconcile(self):
        items = self.p.p9.store.all_items(scope=SCOPE)
        # every workspace state count appears in the reconciling summary
        counts = {}
        for it in items:
            counts[it["workspace_state"]] = counts.get(it["workspace_state"], 0) + 1
        body = self.full.get("/").body
        for state, n in counts.items():
            self.assertIn(f"{state}: {n}", body)

    def test_10_filters(self):
        r = self.full.get("/", domain="service_loaner")
        self.assertIn("service_loaner", r.body)
        self.assertNotIn("executive_demo", _rows_only(r.body))   # filtered out of the table

    def test_11_scenario_items_distinct(self):
        self.assertIn("Scenario", self.full.get("/").body)       # scenario badge present

    def test_12_stale_items_distinct(self):
        r = self.full.get("/item/" + self.p.stale_item["id"])
        self.assertIn("Stale", r.body)

    # ---- recommendation detail (13-19) ------------------------------------
    def test_13_14_15_16_detail_call_why_proof_rawhistory(self):
        r = self.full.get("/item/" + self.p.ni_item["id"])
        self.assertEqual(r.status, 200)
        for section in ("Call", "Why", "Proof", "Raw History"):
            self.assertIn(section, r.body)

    def test_17_missing_explanation_unknown(self):
        r = self.full.get("/item/" + self.p.fresh_item["id"])
        self.assertIn("unknown", r.body.lower())          # not invented

    def test_18_historical_and_current_distinguishable(self):
        self.p.p9.workspace.revise(self.p.fresh_item, new_recommendation_ref="rec_fresh_v2", reason="updated")
        r = self.full.get("/item/" + self.p.fresh_item["id"])
        self.assertIn("rec_fresh_v2", r.body)             # current
        self.assertIn("Recommendation revised", r.body)   # historical revision in Raw History
        self.assertIn("rec_fresh", r.body)                # prior ref preserved

    def test_19_official_and_scenario_distinguishable(self):
        official = self.full.get("/item/" + self.p.ni_item["id"]).body
        scenario = self.full.get("/item/" + self.p.scenario_item["id"]).body
        self.assertIn("Official", official)
        self.assertIn("Scenario", scenario)


def _rows_only(body):
    return body.split("<tbody>", 1)[-1] if "<tbody>" in body else body


if __name__ == "__main__":
    unittest.main()
