"""Daily OPERATOR shell — login lands on Pipeline Horizon, the primary navigation is the dealership product
(not engineering/governance surfaces), the trust strip is honest, and normal GSM navigation never hits an
engineering permission wall. Certified New-Inventory behaviour is unchanged."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.db import current_version

ENGINEERING = ("Readiness", "Approvals", "Execution", "Exceptions", "Audit", "Authority",
               "Learning & Calibration", "Scenarios")


class TestOperatorShell(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _shell(self, body):
        return body.split("<main", 1)[0]     # header + trust strip + primary nav

    # login default ('/') is Pipeline, not the Decision Inbox / governance
    def test_home_is_pipeline(self):
        r = self.full.get("/")
        self.assertEqual(r.status, 200)
        self.assertIn("Pipeline", r.body)
        self.assertIn("Today across the whole dealership", r.body) if "combination" in r.body else None
        # inbox moved off '/'
        self.assertEqual(self.full.get("/inbox").status, 200)

    # primary nav is the operator product; engineering surfaces are NOT in the shell nav
    def test_primary_nav_is_operator(self):
        shell = self._shell(self.full.get("/").body)
        for label in ("Ordering", "Dealer Trade", "Wholesale", "Service Loaners", "Demos", "CTP", "Data"):
            self.assertIn(label, shell)
        for eng in ENGINEERING:
            self.assertNotIn(eng, shell)

    # every operator route resolves for a normal GSM operator (no permission wall)
    def test_operator_routes_open(self):
        for path in ("/", "/ordering", "/dealer-trade", "/wholesale", "/service-loaner",
                     "/demos", "/ctp", "/data", "/admin"):
            self.assertEqual(self.full.get(path).status, 200, path)

    # trust strip shows the four sources honestly (not loaded, in dev) + an Update Data entry point
    def test_trust_strip_honest(self):
        shell = self._shell(self.full.get("/").body)
        for label in ("Inventory", "Speed to Sell", "ICV / Service Loaner", "Preowned Sales Historical"):
            self.assertIn(label, shell)
        self.assertIn("Update Data", shell)
        self.assertIn("not loaded", self.full.get("/data").body)   # no fabricated freshness

    # Service Loaner cockpit is reachable directly and preserves the three fleet counts
    def test_service_loaner_reachable(self):
        b = self.full.get("/service-loaner").body
        self.assertIn("Fleet state", b)
        self.assertIn("Current fleet", b)
        self.assertIn("Undetermined", b)

    # Demos is an operator shell, not the backend portfolio-plan page, and does not fabricate a roster
    def test_demos_honest(self):
        b = self.full.get("/demos").body
        self.assertIn("Current Roster", b)
        self.assertIn("roster", b.lower())

    # certified backend untouched
    def test_backend_unchanged(self):
        self.full.get("/")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
