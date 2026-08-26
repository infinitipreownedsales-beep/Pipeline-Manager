"""Future-supply identity: the 4-digit planning code (8421) and the reviewed 5-digit order code (84217) never
split or double-count in supply aggregation, and a CTP CHANGE only targets a combination that is GENUINELY
still short after incoming supply is netted.

These lock the two facts behind the 8421/84217 correction:
  * `build_supply` and `resolve_or_create_planning_combination` both key by the year-agnostic `dms_planning`
    identity (model, code4, ext, int), so every spelling of a QX60 LUXE AWD code collapses to ONE cohort and
    its incoming units are counted once — there is no separate 84217 / "unmapped" bucket to under-count;
  * the certified board's `short` already nets incoming supply, so the CTP evaluator never proposes a CHANGE to
    a combination whose shortage incoming already covers.
"""
import unittest

from elite.newinv.supply_bridge import build_supply
from elite.newinv.dms_cohort import INVENTORY_STATE_FIELD as LOC
from elite.workflow import ctp_intake as CTP


class TestNoSupplySplit(unittest.TestCase):
    def test_8421_and_84217_are_one_cohort(self):
        # same QX60 LUXE AWD config, different source model-code spellings + incoming/in-stock stages
        rows = [
            {"model_code": "84217", "model": "QX60", "ext": "YCF", "int": "K", LOC: "ONS", "eta": "2026-11"},
            {"model_code": "8421", "model": "QX60", "ext": "YCF", "int": "K", LOC: "SIT", "eta": "2026-11"},
            {"model_code": "84213", "model": "QX60", "ext": "YCF", "int": "K", LOC: "ONS", "eta": "2026-12"},
            {"model_code": "84217", "model": "QX60", "ext": "YCF", "int": "K", LOC: "DLR-INV", "dis": "10"},
        ]
        sup = build_supply(rows, current_month="2026-08")
        self.assertEqual(len(sup), 1)                                  # NO split
        cohort = next(iter(sup.values()))
        self.assertEqual(cohort.key, ("QX60", "8421", "YCF", "K"))
        self.assertEqual(cohort.current, 1)                            # one in-stock (DLR-INV)
        self.assertEqual(cohort.future, 3)                            # three incoming, counted ONCE (no double-count)

    def test_autograph_and_luxe_awd_stay_distinct(self):
        # the reviewed special case keeps AUTOGRAPH (84617 -> 8481) distinct from LUXE AWD (84217 -> 8421)
        rows = [
            {"model_code": "84617", "model": "QX60", "ext": "YCF", "int": "K", LOC: "ONS"},
            {"model_code": "84217", "model": "QX60", "ext": "YCF", "int": "K", LOC: "ONS"},
        ]
        sup = build_supply(rows, current_month="2026-08")
        self.assertEqual({k[1] for k in sup}, {"8481", "8421"})        # two distinct cohorts, never merged


class TestChangeRespectsIncoming(unittest.TestCase):
    """A CTP CHANGE targets a same-model SHORT combination. When incoming supply has covered that combination
    (short == 0), it is not a target and the order KEEPs — the exact behavior required so an already-incoming
    exact combination makes the CHANGE disappear."""

    def _eval(self, luxe_short):
        board = {
            "cA": {"canonical": "dms_planning|model=QX60|model_code=8481|exterior=GAT|interior=K",
                   "line": "84617 QX60 AUTOGRAPH AWD", "colors": "Mineral Black", "model": "QX60",
                   "excess": 2, "short": 0},
            "cB": {"canonical": "dms_planning|model=QX60|model_code=8421|exterior=YCF|interior=K",
                   "line": "84217 QX60 LUXE AWD", "colors": "Deep Emerald / Stone Gray", "model": "QX60",
                   "excess": 0, "short": luxe_short},
        }
        pipeline = [{"order_number": o, "vin": "", "combination_id": "cA",
                     "canonical": board["cA"]["canonical"], "model": "QX60", "arrival_month": "2026-12"}
                    for o in ("TK76338", "TK76339")]
        cands = [CTP.Candidate(order_number=o, vin="", model="QX60", model_code="84617", exterior="GAT",
                               interior="K", arrival_month="2026-12", source_file="f")
                 for o in ("TK76338", "TK76339")]
        recs = CTP.evaluate(CTP.reconcile(cands, pipeline), board, now="2026-08-25")
        return [r.decision_state for r in recs]

    def test_change_when_target_still_short(self):
        self.assertEqual(self._eval(luxe_short=2), [CTP.CHANGE, CTP.CHANGE])

    def test_no_change_when_incoming_covered_the_shortage(self):
        # incoming supply reduced the LUXE AWD need to 0 on the certified board -> it is not a CHANGE target
        self.assertEqual(self._eval(luxe_short=0), [CTP.KEEP, CTP.KEEP])


if __name__ == "__main__":
    unittest.main(verbosity=2)
