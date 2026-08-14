"""Service Loaner ECONOMIC Ideal Mix — proves the fleet law never blindly fills a quantity with
economically inferior units, distinguishes required from ideal, rotates IN/OUT instead of blindly growing,
and that monthly placement requirements are temporary and do not corrupt future economic learning."""
import unittest

from elite.loaner.ideal_mix import UnitEcon, optimize_ideal_mix
from elite.loaner import placement_settings as PS


def held(id_, net, identity=""):
    # keep_value - exit_value = net (positive = keeping is economically better than exiting)
    return UnitEcon(id=id_, identity=identity or id_, keep_value=net, exit_value=0.0)


def cand(id_, net, identity=""):
    return UnitEcon(id=id_, identity=identity or id_, in_value=net, opportunity_cost=0.0)


class _Meta:
    def __init__(self): self.d = {}
    def put(self, k, v): self.d[k] = v
    def get(self, k): return self.d.get(k)


class TestIdealMixEconomics(unittest.TestCase):
    # 1 + 2. does NOT fill a fixed quantity with inferior candidates; stops at the economically defensible count
    def test_stops_at_economically_defensible(self):
        cands = [cand(f"c{i}", net) for i, net in enumerate([500, 400, 300, 220, 150, -40, -90])]
        res = optimize_ideal_mix([], cands, operational_target=7)
        self.assertEqual(res.economic_fleet_count, 5)          # only 5 of 7 make economic sense
        self.assertEqual(len(res.by_action("IN")), 5)
        self.assertNotIn("c5", {d["id"] for d in res.by_action("IN")})  # negative-net not forced in

    # 3. the remaining fleet gap becomes a future stocking need, not a forced bad entry
    def test_gap_is_future_stocking_need(self):
        cands = [cand(f"c{i}", net) for i, net in enumerate([500, 400, 300, -10, -20])]
        res = optimize_ideal_mix([], cands, operational_target=7)
        self.assertEqual(res.economic_fleet_count, 3)
        self.assertEqual(res.future_stocking_need, 4)
        self.assertIn("future stocking need", res.note)

    # 4. target 20: IN/HOLD/OUT optimizes toward the best 20 rather than merely adding units
    def test_optimize_toward_best_target(self):
        cur = [held(f"h{i}", net) for i, net in enumerate([300, 280, 260, 240, 30, 20])]  # 6 held; last two weak
        cands = [cand("x1", 500), cand("x2", 450)]                                        # two strong adds
        res = optimize_ideal_mix(cur, cands, operational_target=6)
        # strong candidates displace the two weakest held; fleet stays at 6
        self.assertEqual(res.recommended_fleet_count, 6)
        self.assertEqual({d["id"] for d in res.by_action("IN")}, {"x1", "x2"})
        self.assertTrue(any(d["id"] in ("h4", "h5") for d in res.by_action("OUT")))
        self.assertTrue(res.swaps)                              # OUT/IN pairing surfaced

    # 5. current fleet 20 + required 2 -> OUT 2 + IN 2 (rotation), not blind growth to 22
    def test_required_rotates_not_grows(self):
        cur = [held(f"h{i}", 200 - i) for i in range(20)]      # 20 held, h19 weakest
        cands = [cand("x1", 400), cand("x2", 380)]             # 2 strong adds
        res = optimize_ideal_mix(cur, cands, operational_target=20, required_placements=2)
        self.assertEqual(res.recommended_fleet_count, 20)      # stays at 20
        self.assertFalse(res.growth)
        self.assertEqual(len(res.by_action("IN")), 2)
        self.assertEqual(len(res.by_action("OUT")), 2)

    # 6 + 7. required forces economically weaker #6/#7, clearly labelled objective-driven (not ideal)
    def test_required_labels_objective_driven(self):
        cands = ([cand(f"c{i}", net) for i, net in enumerate([500, 400, 300, 220, 150])]   # 5 economic
                 + [cand("weak6", -30), cand("weak7", -60)])                                # only weak extras
        res = optimize_ideal_mix([], cands, operational_target=7, required_placements=7)
        self.assertEqual(res.economic_fleet_count, 5)          # economic optimum unchanged
        ins = {d["id"]: d for d in res.by_action("IN")}
        self.assertEqual(len(ins), 7)                          # requirement met
        self.assertTrue(ins["weak6"]["objective_driven"])      # weak ones flagged objective-driven
        self.assertTrue(ins["weak7"]["objective_driven"])
        self.assertFalse(ins["c0"]["objective_driven"])        # economic ones NOT relabelled
        self.assertEqual(set(res.objective_driven_ins), {"weak6", "weak7"})

    # 8. monthly requirement is temporary — a set month does not apply to another month
    def test_requirement_expires(self):
        meta = _Meta()
        PS.set_requirement(meta, effective_month="2026-08", required=7, reason="OEM push")
        self.assertIsNotNone(PS.resolve(meta, "2026-08"))
        self.assertIsNone(PS.resolve(meta, "2026-09"))         # not inherited into September
        PS.clear_requirement(meta)
        self.assertIsNone(PS.resolve(meta, "2026-08"))

    # 9 + 10. ranking is total-economics, never youngest/newest/first-seen; duplicates counted once
    def test_ranking_is_economic_and_dedup(self):
        # c_dup is the strongest but appears twice (duplicate id); must be counted once, chosen on economics
        cands = [cand("c_dup", 900), cand("c_old", 800), cand("c_dup", 900), cand("c_mid", 500)]
        res = optimize_ideal_mix([], cands, operational_target=2)
        picked = [d["id"] for d in sorted(res.by_action("IN"), key=lambda d: -d["net"])]
        self.assertEqual(picked, ["c_dup", "c_old"])           # by economics, not order/age
        self.assertEqual(len(res.by_action("IN")), 2)          # duplicate did not inflate the selection
        self.assertEqual(sum(1 for d in res.by_action("IN") if d["id"] == "c_dup"), 1)  # counted once

    # 11. loaner objective needs stay separate from retail demand (opportunity cost is an INPUT, not demand)
    def test_opportunity_cost_is_input_not_demand(self):
        # a scarce retail combination (high opportunity cost) can make an otherwise-attractive placement net-negative
        cands = [cand("scarce", 0), UnitEcon(id="scarce", identity="scarce", in_value=300, opportunity_cost=800)]
        res = optimize_ideal_mix([], [UnitEcon(id="scarce", in_value=300, opportunity_cost=800)],
                                 operational_target=3)
        self.assertEqual(res.economic_fleet_count, 0)          # net -500 -> not placed as a loaner
        self.assertEqual(res.future_stocking_need, 3)

    # 12. no fabricated future stocking demand without economic/operational evidence
    def test_no_fabricated_need_when_healthy(self):
        cands = [cand(f"c{i}", 300 - 10 * i) for i in range(5)]  # 5 healthy positive-net
        res = optimize_ideal_mix([], cands, operational_target=5)
        self.assertEqual(res.economic_fleet_count, 5)
        self.assertEqual(res.future_stocking_need, 0)           # target met economically -> no invented need
        self.assertEqual(res.note, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
