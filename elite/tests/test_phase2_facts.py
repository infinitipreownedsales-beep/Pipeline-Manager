"""Phase 2 acceptance — Business Fact invariants (items 25-30) + no-domain guard (38)."""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError
from elite.data.fixtures import GOOD_VIN, Phase2
from elite.data.models import SourceRegistry

SCOPE = "store:HG"


class TestPhase2Facts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase2(os.path.join(self.tmp, "elite.db"))
        self.dms = self.p.store.get_source("src_dms")
        self.feed = self.p.store.get_source("src_feed")

    def tearDown(self):
        self.p.close()

    def _fact(self, source=None, payload=None):
        return self.p.facts.create(source=source or self.dms, fact_type="vehicle_present",
                                   subject_type="vehicle", subject_id="veh_1",
                                   payload=payload or {"stock": "N1"}, scope=SCOPE, observation_refs=["obs_1"])

    def test_25_authoritative_source_creates_fact(self):
        f = self._fact()
        self.assertEqual(f.status, "current")
        self.assertEqual(f.source_authority, "src_dms")

    def test_26_unauthorized_source_facttype_cannot_create(self):
        with self.assertRaises(AuthorizationError):
            self._fact(source=self.feed)                     # feed not authoritative
        with self.assertRaises(AuthorizationError):
            self.p.facts.create(source=self.dms, fact_type="loaner_status", subject_type="vehicle",
                                subject_id="veh_1", payload={}, scope=SCOPE, observation_refs=[])

    def test_27_correction_preserves_original(self):
        orig = self._fact(payload={"mileage": 5})
        corrected = self.p.facts.correct(orig.id, {"mileage": 9})
        self.assertEqual(corrected.correction_of, orig.id)
        again = self.p.store.get_fact(orig.id)
        self.assertEqual(again.status, "superseded")
        self.assertEqual(again.payload, {"mileage": 5})       # original-as-known still inspectable

    def test_28_reversal_preserves_history(self):
        orig = self._fact()
        rev = self.p.facts.reverse(orig.id, reason="entered in error")
        self.assertEqual(rev.reversal_of, orig.id)
        self.assertEqual(self.p.store.get_fact(orig.id).status, "reversed")
        self.assertIsNotNone(self.p.store.get_fact(orig.id))   # not deleted

    def test_29_supersession_changes_projection_not_history(self):
        f1 = self._fact(payload={"v": "A"})
        f2 = self.p.facts.supersede(f1.id, {"v": "B"})
        current, conflict = self.p.facts.current("vehicle", "veh_1", "vehicle_present", SCOPE)
        self.assertIsNone(conflict)
        self.assertEqual(current.id, f2.id)                   # projection = latest current
        self.assertIsNotNone(self.p.store.get_fact(f1.id))    # history intact

    def test_30_conflicting_facts_conflict_unless_precedence(self):
        # second authoritative source for the same fact type + scope
        dms2 = self.p.store.add_source(SourceRegistry(
            id="src_dms2", name="Second DMS", authoritative_fact_types=["vehicle_present"], scope=SCOPE))
        self._fact()                                          # current from src_dms
        self.p.facts.create(source=dms2, fact_type="vehicle_present", subject_type="vehicle",
                            subject_id="veh_1", payload={"stock": "N1b"}, scope=SCOPE, observation_refs=["o2"])
        current, conflict = self.p.facts.current("vehicle", "veh_1", "vehicle_present", SCOPE)
        self.assertIsNone(current)
        self.assertTrue(conflict and conflict["conflict"])    # explicit conflict, no silent pick
        # with an approved precedence rule, projection resolves deterministically
        chosen, conflict2 = self.p.facts.current("vehicle", "veh_1", "vehicle_present", SCOPE,
                                                 precedence=["src_dms", "src_dms2"])
        self.assertIsNone(conflict2)
        self.assertEqual(chosen.source_authority, "src_dms")

    def test_38_no_domain_behavior_present(self):
        # No Demand/CPO/Loaner/Demo/CTP/Prediction/Learning behavior in the elite package.
        import elite.data.ingestion, elite.data.facts, elite.data.identity, elite.data.contracts
        forbidden = ("demand", "need", "forecast", "cpo", "ppo", "ctp", "loaner", "demo",
                     "predict", "learning", "replenish")
        for mod in (elite.data.ingestion, elite.data.facts, elite.data.identity, elite.data.contracts):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(f in low for f in forbidden),
                                 f"domain-looking symbol {name} in {mod.__name__}")


if __name__ == "__main__":
    unittest.main()
