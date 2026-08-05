"""Phase 5 acceptance — editability, model-year transition, Incoming Risk (items 11-17)."""
import os
import tempfile
import unittest

from elite.workflow.fixtures import SCOPE, Phase5
from elite.workflow.pipeline import PipelineService
from elite.workflow.risk import excessive_depth, late_arrival


class TestPhase5EditMytRisk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_11_editability_separately_inspectable_from_demand(self):
        e = self.p.pipeline.assess_editability("po1", SCOPE, "editable", editable_dimensions=["exterior_color"])
        got = self.p.wf.editability_for("po1")
        self.assertEqual(got.editability_state, "editable")
        self.assertEqual(got.editable_dimensions, ["exterior_color"])
        # editability is its own record; it does not appear in Demand inputs (Demand is supply/edit blind)
        import inspect
        from elite.newinv.demand import DemandService
        self.assertNotIn("editability", inspect.signature(DemandService.issue).parameters)

    def test_12_locked_order_cannot_receive_executable_ctp(self):
        locked = self.p.pipeline.assess_editability("po_lock", SCOPE, "locked")
        self.assertFalse(PipelineService.is_executably_editable(locked))

    def test_13_unknown_editability_does_not_become_editable(self):
        unk = self.p.pipeline.assess_editability("po_unk", SCOPE, "unknown")
        self.assertFalse(PipelineService.is_executably_editable(unk))

    def test_14_model_year_transition_preserves_identity(self):
        out = self.p.combination(model="QX80", model_year="2025", exterior_color="BLACK")
        inc = self.p.combination(model="QX80", model_year="2026", exterior_color="BLACK")
        self.assertNotEqual(out.id, inc.id)                        # separate model-year identity
        myt = self.p.pipeline.model_year_transition(SCOPE, "QX80", outgoing_model_year="2025",
                                                    incoming_model_year="2026")
        self.assertEqual((myt.outgoing_model_year, myt.incoming_model_year), ("2025", "2026"))

    def test_15_unsupported_lineage_does_not_transfer_demand(self):
        # No approved lineage -> inherit not allowed -> Demand estimate, inherited numbers not used.
        newgen = self.p.combination(model="QX55", model_year="2026", exterior_color="GEN")
        inherited = {"retail_by_month": {"2025-03": 9}, "exposure_months": 1, "sample_size": 9,
                     "relationship": "generation_change", "source_combination": "old_gen"}
        d = self.p.p4.demand.issue(newgen, SCOPE, ["2026-09", "2026-10"], retail_by_month={}, exposure_months=0,
                                   inherited=inherited, inherit_allowed=False,
                                   calculation_version=self.p.p4.demand_cv)
        self.assertEqual(d.evidence_tier, "estimate")
        self.assertEqual(set(d.monthly_expected.values()), {0.0})

    def test_16_incoming_risk_explains_component_reasons(self):
        r = self.p.risk.assess(subject_kind="future_supply", subject_ref="po1", combination_id="c1", scope=SCOPE,
                               reasons=[late_arrival("2027-03", "2026-12"), excessive_depth(9, 3)])
        factors = {x["factor"] for x in r.reasons}
        self.assertIn("arrival_after_window", factors)
        self.assertIn("excessive_depth", factors)
        self.assertEqual(r.classification, "high")                 # derived from worst component

    def test_17_risk_not_only_opaque_score(self):
        r = self.p.risk.assess(subject_kind="future_supply", subject_ref="po2", combination_id="c1", scope=SCOPE,
                               reasons=[excessive_depth(9, 3)])
        stored = self.p.wf.get_risk(r.id)
        self.assertTrue(stored.reasons)                            # component reasons present
        self.assertTrue(all("detail" in x for x in stored.reasons))  # each reason explained, not one score


if __name__ == "__main__":
    unittest.main()
