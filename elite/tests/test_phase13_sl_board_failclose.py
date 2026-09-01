"""Block-1 closeout: Service Loaner board fails closed on an unresolved target, and no render-time profiling.

Two production defects fixed:
  1. _best_add_card raised RuntimeError when the governed Service Loaner target was unset, which 500-ed the whole
     /service-loaner page. It must render, fail closed VISIBLY (target unresolved, no ADD command), and never
     fabricate a target / ADD requirement / candidates / economics.
  2. The /service-loaner route wrote a cProfile dump to a hardcoded C:\\Code\\Pipeline-Manager\\SL_PROFILE.txt on
     every render — a production side effect (and it dirties the working tree, which blocks updateelite). Removed.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.ids import new_id
from elite.loaner.loaner_cockpit import MetaPrefs, set_desired_fleet

_PROFILE_ARTIFACT = "C:\\Code\\Pipeline-Manager\\SL_PROFILE.txt"


class TestBoardFailClose(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _unit(self, tag, isd="2025-11-01", miles="3000"):
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "accepted_in_service_date,in_service_date_authority,last_checkout_mileage,created_at,version)"
            " VALUES(?,?,?,?,1,?,?,?,?,1)",
            (new_id("slu"), f"5N1AZ2CS0PC9{tag:05d}", SCOPE, "ACTIVE_AVAILABLE", isd,
             "verified" if isd else "snapshot", miles, "2026-01-01"))
        self.conn.commit()

    # ---- Defect 1: unresolved target must render, not crash ----
    def test_unresolved_target_renders_fail_closed_not_crash(self):
        for i in range(3):
            self._unit(i)                                    # units present, but NO governed target set
        b = self.full.get("/service-loaner").body
        self.assertNotIn("Something went wrong", b)          # no 500
        self.assertIn("Service Loaner - Manager Action", b)  # board still renders
        self.assertIn("Target unresolved", b)                # fail closed VISIBLY
        self.assertIn("PULL NOW", b)                         # governed PULL evidence still shown
        self.assertNotIn("Add required", b)                  # never fabricate an ADD requirement without a target

    def test_empty_store_renders_fail_closed(self):
        b = self.full.get("/service-loaner").body            # no units, no target
        self.assertNotIn("Something went wrong", b)
        self.assertIn("Service Loaner - Manager Action", b)
        self.assertIn("Target unresolved", b)

    def test_resolved_target_still_renders_full_board(self):
        for i in range(4):
            self._unit(i)
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), 3)   # governed target present
        b = self.full.get("/service-loaner").body
        self.assertNotIn("Something went wrong", b)
        self.assertIn("Service Loaner - Manager Action", b)
        self.assertIn("Target 3", b)                         # live behavior unchanged when the target is set
        self.assertNotIn("Target unresolved", b)

    # ---- Defect 2: no render-time profiling side effect ----
    def test_no_profiling_file_written_on_render(self):
        if os.path.exists(_PROFILE_ARTIFACT):
            os.remove(_PROFILE_ARTIFACT)
        for i in range(2):
            self._unit(i)
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), 2)
        self.full.get("/service-loaner")
        self.assertFalse(os.path.exists(_PROFILE_ARTIFACT))  # route must not write the hardcoded profile file

    def test_route_source_has_no_profiling(self):
        import elite.ui.views.domains as d
        with open(d.__file__, encoding="utf-8") as _f:
            src = _f.read()
        self.assertNotIn("SL_PROFILE", src)
        self.assertNotIn("cProfile", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
