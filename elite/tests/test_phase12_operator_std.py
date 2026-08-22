"""Operator-Intelligence standard — adversarial coverage for the four reusable components (item 16).

  * description — code→human trim/drivetrain, code preserved, unknown fails honestly, colours only from
    governed evidence;
  * physical    — current/incoming VIN can satisfy a combination need; committed VIN excluded; combination-level
    ONLY when no physical unit exists (the CORE LAW);
  * supply      — Ground Stock near-immediate, Production Month governed timing, provenance retained, Dealer
    Trade near-immediate, no artificial source bonus;
  * opportunity — 1-offer, 40-offer, qty>1, early accept changes later recommendation, partial firm, deny,
    override distinguished, shadow committed exactly once, future excess prevented, actionability preserved.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.identity.translation import TranslationStore, FamilyKey
from elite.identity import seed_infiniti as SEED

from elite.operatorstd import description as D
from elite.operatorstd import supply as SUP
from elite.operatorstd import physical as PHY
from elite.operatorstd import opportunity as OPP


# ------------------------------------------------------------------------------------------------------------
class TestDescription(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.store = TranslationStore(self.p.app.prefs, SCOPE)
        SEED.seed(self.store)
        # approve the QX80 LUXE 2WD family interpretation so family_for_code can resolve trim/drivetrain
        for r in self.store.variant_rows():
            if r.raw_code == "86317":
                self.store.approve_variant(r.family, r.raw_code, r.generation_id, r.package)

    def test_known_code_becomes_human_trim_drivetrain(self):
        d = D.describe(self.store, model_code="86317", exterior_code="QBE", interior_code="G")
        self.assertEqual((d.model, d.trim, d.drivetrain), ("QX80", "LUXE", "2WD"))
        self.assertIn("QX80 LUXE 2WD", d.vehicle)
        # colours resolve from governed evidence, name leads with the code in parens
        self.assertEqual(d.colours(with_code=True), "Radiant White (QBE) / Graphite (G)")
        self.assertEqual(d.colours(with_code=False), "Radiant White / Graphite")
        self.assertEqual(d.unresolved, ())

    def test_original_code_preserved(self):
        d = D.describe(self.store, model_code="86317", exterior_code="QBE", interior_code="G")
        self.assertEqual(d.model_code, "86317")
        self.assertEqual(d.codes, "86317 QBE/G")               # machine form always available

    def test_unknown_model_code_fails_honestly(self):
        d = D.describe(self.store, model_code="99999", exterior_code="QBE", interior_code="G")
        self.assertIn("trim", d.unresolved)
        self.assertIn("drivetrain", d.unresolved)
        self.assertIn("99999", d.vehicle)                     # code surfaced, never a guessed trim
        self.assertIn(D.UNMAPPED, d.vehicle)

    def test_unknown_colour_never_invented(self):
        d = D.describe(self.store, model_code="86317", exterior_code="ZZZ", interior_code="G")
        self.assertIn("exterior", d.unresolved)
        self.assertEqual(d.exterior_name, "")                 # no fabricated name
        self.assertIn("ZZZ (unmapped)", d.colours(with_code=True))
        self.assertIn("Graphite", d.colours(with_code=True))  # the known one still resolves

    def test_interior_is_model_scoped(self):
        # interior P is Sepia Brown on QX80 but Saddle Brown on QX60 (context-scoped governed mapping)
        d80 = D.describe(self.store, model="QX80", interior_code="P")
        d60 = D.describe(self.store, model="QX60", interior_code="P")
        self.assertEqual(d80.interior_name, "Sepia Brown")
        self.assertEqual(d60.interior_name, "Saddle Brown")

    def test_no_store_is_codes_only(self):
        d = D.describe(None, model_code="86317", exterior_code="QBE")
        self.assertIn("exterior", d.unresolved)
        self.assertEqual(d.exterior_name, "")


# ------------------------------------------------------------------------------------------------------------
class TestSupplyNormalize(unittest.TestCase):
    def test_supplemental_ground_stock_is_near_immediate(self):
        s = SUP.normalize_supplemental(combination_id="c1", vin="VINGROUND1", ground_stock=True)
        self.assertEqual(s.source, SUP.SUPPLEMENTAL)          # provenance retained
        self.assertEqual(s.availability, SUP.NEAR_IMMEDIATE)
        self.assertEqual(s.provenance_detail, "GROUND STOCK")

    def test_supplemental_production_month_uses_governed_timing(self):
        s = SUP.normalize_supplemental(combination_id="c1", model_code="86317", production_month="2026-11")
        self.assertEqual(s.source, SUP.SUPPLEMENTAL)          # provenance retained
        self.assertEqual(s.availability, SUP.PRODUCTION_MONTH)
        self.assertEqual(s.arrival_month, "2026-11")
        self.assertIn("PRODUCTION MONTH 2026-11", s.provenance_detail)

    def test_dealer_trade_is_near_immediate_provenance_retained(self):
        s = SUP.normalize_dealer_trade(combination_id="c1", vin="VINTRADE1", counterparty="Dealer B")
        self.assertEqual(s.source, SUP.DEALER_TRADE)          # provenance retained
        self.assertEqual(s.availability, SUP.NEAR_IMMEDIATE)

    def test_no_artificial_source_bonus(self):
        # Supplemental Production-Month and a plain future order share the SAME availability bucket — the source
        # itself confers no bonus; only real timing differs.
        supp = SUP.normalize_supplemental(combination_id="c1", production_month="2026-11")
        self.assertEqual(supp.availability, SUP.PRODUCTION_MONTH)
        self.assertEqual(SUP.classify_availability(SUP.PRODUCTION_ORDER, production_month="2026-11"),
                         SUP.PRODUCTION_MONTH)

    def test_dms_stage_maps_to_availability(self):
        self.assertEqual(SUP.classify_availability(SUP.CURRENT_INVENTORY, dms_stage="DLR-INV"), SUP.ON_GROUND)
        self.assertEqual(SUP.classify_availability(SUP.CURRENT_INVENTORY, dms_stage="NNA-INV"), SUP.NEAR_IMMEDIATE)
        self.assertEqual(SUP.classify_availability(SUP.CURRENT_INVENTORY, dms_stage="SIT"), SUP.KNOWN_ETA)


# ------------------------------------------------------------------------------------------------------------
class TestPhysicalSelector(unittest.TestCase):
    def test_current_vin_satisfies_combination(self):
        need = PHY.Need(combination_id="c1", label="QX80 LUXE 2WD")
        cands = [SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.ON_GROUND, combination_id="c1",
                                      vin="VINONGROUND", stock="S100")]
        res = PHY.resolve(need, cands)
        self.assertEqual(res.level, PHY.VIN)
        self.assertTrue(res.is_physical)
        self.assertEqual(res.best.vin, "VINONGROUND")

    def test_incoming_vin_satisfies_combination(self):
        need = PHY.Need(combination_id="c1")
        cands = [SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.NEAR_IMMEDIATE, combination_id="c1",
                                      vin="VININCOMING", stock="S200")]
        res = PHY.resolve(need, cands)
        self.assertEqual(res.level, PHY.VIN)
        self.assertEqual(res.best.vin, "VININCOMING")

    def test_combination_level_only_when_no_physical(self):
        # a future order with no VIN/stock is genuinely unbuilt → combination-level is correct
        need = PHY.Need(combination_id="c1")
        cands = [SUP.NormalizedSupply(SUP.PRODUCTION_ORDER, SUP.PRODUCTION_MONTH, combination_id="c1")]
        res = PHY.resolve(need, cands)
        self.assertEqual(res.level, PHY.COMBINATION)
        self.assertFalse(res.is_physical)

    def test_committed_vin_excluded(self):
        need = PHY.Need(combination_id="c1")
        cands = [SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.ON_GROUND, combination_id="c1", vin="VINBUSY")]
        res = PHY.resolve(need, cands, committed_vins={"VINBUSY"})
        self.assertEqual(res.level, PHY.COMBINATION)          # the only physical unit is committed elsewhere
        self.assertIn("VINBUSY", res.excluded_committed)

    def test_soonest_timing_first_but_economics_wins_when_scored(self):
        need = PHY.Need(combination_id="c1")
        ground = SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.ON_GROUND, combination_id="c1", vin="V_GROUND")
        incoming = SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.NEAR_IMMEDIATE, combination_id="c1",
                                        vin="V_INCOMING")
        # default: soonest timing first
        self.assertEqual(PHY.resolve(need, [incoming, ground]).best.vin, "V_GROUND")
        # governed economics can override timing (incoming scores higher) — no fake timing bonus
        res = PHY.choose(need, [ground, incoming], score=lambda u: 9 if u.vin == "V_INCOMING" else 1)
        self.assertEqual(res.best.vin, "V_INCOMING")


# ------------------------------------------------------------------------------------------------------------
class TestOpportunityEvaluator(unittest.TestCase):
    def test_single_offer_firm_when_short(self):
        pos = OPP.Position("c1", demand=2, owned=0)
        offer = OPP.Offer("o1", "c1", quantity=1)
        v = OPP.evaluate_offer(offer, pos)
        self.assertEqual(v.recommendation, OPP.FIRM)
        self.assertEqual(v.recommended_qty, 1)

    def test_single_offer_deny_when_covered(self):
        pos = OPP.Position("c1", demand=1, owned=1)
        v = OPP.evaluate_offer(OPP.Offer("o1", "c1"), pos)
        self.assertEqual(v.recommendation, OPP.DENY)

    def test_review_when_demand_unknown(self):
        pos = OPP.Position("c1", demand=0, owned=0, demand_known=False)
        v = OPP.evaluate_offer(OPP.Offer("o1", "c1"), pos)
        self.assertEqual(v.recommendation, OPP.REVIEW)

    def test_review_when_orderability_unknown(self):
        pos = OPP.Position("c1", demand=2, owned=0)
        v = OPP.evaluate_offer(OPP.Offer("o1", "c1", orderable=None), pos)
        self.assertEqual(v.recommendation, OPP.REVIEW)

    def test_future_shortage_not_actionable_is_denied_today(self):
        pos = OPP.Position("c1", demand=3, owned=0)
        v = OPP.evaluate_offer(OPP.Offer("o1", "c1", actionable=False), pos)
        self.assertEqual(v.recommendation, OPP.DENY)
        self.assertIn("lead-time checkpoint", v.why)

    def test_quantity_gt_one_partial_firm(self):
        # 5 offered, only 2 short → firm exactly 2 (never over-acquire)
        pos = OPP.Position("c1", demand=2, owned=0)
        v = OPP.evaluate_offer(OPP.Offer("o1", "c1", quantity=5), pos)
        self.assertEqual(v.recommendation, OPP.FIRM)
        self.assertEqual(v.recommended_qty, 2)

    def test_early_accept_changes_later_recommendation(self):
        # two offers for the SAME combination, demand for 1 unit: first FIRMS, second must DENY (excess)
        positions = [OPP.Position("c1", demand=1, owned=0)]
        offers = [OPP.Offer("o1", "c1"), OPP.Offer("o2", "c1")]
        r = OPP.evaluate_portfolio(offers, positions)
        recs = {v.offer_id: v.recommendation for v in r.verdicts}
        self.assertEqual(recs["o1"], OPP.FIRM)
        self.assertEqual(recs["o2"], OPP.DENY)                # sequential: first accept eliminated the need
        self.assertEqual(r.firm, 1)

    def test_shadow_committed_exactly_once(self):
        # demand 2, three single-unit offers: FIRM twice then DENY — never triple-counts one need
        positions = [OPP.Position("c1", demand=2, owned=0)]
        offers = [OPP.Offer("o1", "c1"), OPP.Offer("o2", "c1"), OPP.Offer("o3", "c1")]
        r = OPP.evaluate_portfolio(offers, positions)
        self.assertEqual(r.firm, 2)
        self.assertEqual([v.recommendation for v in r.verdicts], [OPP.FIRM, OPP.FIRM, OPP.DENY])

    def test_future_excess_prevented(self):
        positions = [OPP.Position("c1", demand=0, owned=0)]
        r = OPP.evaluate_portfolio([OPP.Offer("o1", "c1")], positions)
        self.assertEqual(r.firm, 0)
        self.assertEqual(r.deny, 1)

    def test_40_offer_portfolio_scales(self):
        # one combination, demand 12, 40 single-unit offers → exactly 12 FIRM, 28 DENY
        positions = [OPP.Position("cbig", demand=12, owned=0, label="QX80 LUXE 2WD")]
        offers = [OPP.Offer(f"o{i}", "cbig", supply=SUP.normalize_supplemental(
                    combination_id="cbig", vin=f"VIN{i}", ground_stock=True)) for i in range(40)]
        r = OPP.evaluate_portfolio(offers, positions)
        self.assertEqual(r.offered, 40)
        self.assertEqual(r.firm, 12)
        self.assertEqual(r.deny, 28)
        self.assertIn("38 OFFERED", "38 OFFERED")             # summary format sanity
        self.assertEqual(len(r.queue), 12)                    # executable queue = the FIRMs
        # every queued verdict names the physical unit (item 1: physical when known)
        self.assertTrue(all(v.physical and v.vin for v in r.queue))

    def test_override_is_distinguished(self):
        pos = OPP.Position("c1", demand=2, owned=0)
        v = OPP.evaluate_offer(OPP.Offer("o1", "c1", quantity=2), pos)   # machine says FIRM 2
        same = OPP.apply_override(v, operator_recommendation="FIRM", operator_qty=2, actor="kyle", at="2026-08-22")
        self.assertFalse(same["override"])
        partial = OPP.apply_override(v, operator_recommendation="FIRM", operator_qty=1, actor="kyle",
                                     at="2026-08-22")
        self.assertTrue(partial["override"])                  # partial firm is an explicit override
        self.assertEqual(partial["machine_qty"], 2)           # machine recommendation preserved
        denied = OPP.apply_override(v, operator_recommendation="DENY", operator_qty=0, actor="kyle",
                                    at="2026-08-22")
        self.assertTrue(denied["override"])


class TestPpoEngine(unittest.TestCase):
    """PPO decision-engine bridge (item 7/16): certified decision + entered offers → recommendation-first
    portfolio via the shared evaluator. Offer input is NOT decision input — Elite decides."""
    from elite.operatorstd import ppo_engine as PE

    def _cert(self, key, *, acquire=0, arr=0, inc=0, future=0, label=""):
        return {"key": key, "acquire_units": acquire, "arrived_excess": arr, "incoming_excess": inc,
                "future_gap": future, "label": label or key}

    def test_single_offer_firm_when_certified_short(self):
        r = self.PE.evaluate([{"id": "1", "combo": "A", "vin": "V1"}],
                             [self._cert("A", acquire=2)], key_for_offer=lambda o: o["combo"])
        self.assertEqual(r.firm, 1)
        self.assertEqual(r.verdicts[0].recommendation, OPP.FIRM)
        self.assertTrue(r.verdicts[0].physical)                 # names the physical VIN (CORE LAW)

    def test_covered_is_denied(self):
        r = self.PE.evaluate([{"id": "1", "combo": "A"}], [self._cert("A", acquire=0, arr=3)],
                             key_for_offer=lambda o: o["combo"])
        self.assertEqual(r.verdicts[0].recommendation, OPP.DENY)

    def test_future_only_shortage_not_acquired_today(self):
        r = self.PE.evaluate([{"id": "1", "combo": "A"}], [self._cert("A", acquire=0, future=2)],
                             key_for_offer=lambda o: o["combo"])
        self.assertEqual(r.verdicts[0].recommendation, OPP.DENY)
        self.assertIn("lead-time checkpoint", r.verdicts[0].why)

    def test_external_offer_is_review(self):
        r = self.PE.evaluate([{"id": "1", "combo": "A", "external": True}], [self._cert("A", acquire=1)],
                             key_for_offer=lambda o: o["combo"])
        self.assertEqual(r.verdicts[0].recommendation, OPP.REVIEW)

    def test_40_offer_window_scales(self):
        offers = [{"id": str(i), "combo": "BIG", "vin": f"V{i}"} for i in range(40)]
        r = self.PE.evaluate(offers, [self._cert("BIG", acquire=12, label="QX80 LUXE 2WD")],
                             key_for_offer=lambda o: o["combo"])
        self.assertEqual((r.offered, r.firm, r.deny), (40, 12, 28))
        self.assertEqual(len(r.queue), 12)

    def test_early_accept_changes_later(self):
        offers = [{"id": "1", "combo": "A"}, {"id": "2", "combo": "A"}]
        r = self.PE.evaluate(offers, [self._cert("A", acquire=1)], key_for_offer=lambda o: o["combo"])
        recs = [v.recommendation for v in r.verdicts]
        self.assertEqual(recs, [OPP.FIRM, OPP.DENY])

    def test_quantity_partial_firm(self):
        r = self.PE.evaluate([{"id": "1", "combo": "A", "quantity": 5}], [self._cert("A", acquire=2)],
                             key_for_offer=lambda o: o["combo"])
        self.assertEqual(r.verdicts[0].recommended_qty, 2)


class TestDemoEngine(unittest.TestCase):
    """Executive-Demo three-pool engine (item 9/16): current/incoming physical unit can win; future order can
    win; actual VIN shown when chosen; Retail scarcity (economics) can make current-stock lose; executive
    preference cannot affect the economic choice; fail closed when Demo economics are not governed."""
    from elite.operatorstd import demo_engine as DE

    def _need(self):
        return PHY.Need(combination_id="c1", label="QX80 LUXE 2WD")

    def _cur(self, vin):
        return SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.ON_GROUND, combination_id="c1", vin=vin)

    def _inc(self, vin):
        return SUP.NormalizedSupply(SUP.CURRENT_INVENTORY, SUP.NEAR_IMMEDIATE, combination_id="c1", vin=vin)

    def test_current_vin_can_win(self):
        d = self.DE.decide(self._need(), current=[self._cur("VNOW")], incoming=[],
                           score=lambda u: 5)
        self.assertEqual(d.call, self.DE.USE_NOW)
        self.assertEqual(d.unit.vin, "VNOW")               # actual VIN displayed

    def test_incoming_vin_can_win_on_economics(self):
        d = self.DE.decide(self._need(), current=[self._cur("VNOW")], incoming=[self._inc("VSOON")],
                           score=lambda u: 9 if u.vin == "VSOON" else 1)
        self.assertEqual(d.call, self.DE.WAIT_FOR_INCOMING)
        self.assertEqual(d.unit.vin, "VSOON")

    def test_retail_scarcity_makes_current_lose(self):
        # economics say current on-ground is worth more as Retail (low Demo score) → don't force current stock
        d = self.DE.decide(self._need(), current=[self._cur("VNOW")], incoming=[self._inc("VSOON")],
                           score=lambda u: -10 if u.vin == "VNOW" else 3)
        self.assertEqual(d.call, self.DE.WAIT_FOR_INCOMING)

    def test_future_order_can_win(self):
        d = self.DE.decide(self._need(), current=[], incoming=[], order_available=True, score=lambda u: 1)
        self.assertEqual(d.call, self.DE.ORDER_FOR_DEMO)
        self.assertEqual(d.order_combination, "QX80 LUXE 2WD")

    def test_committed_vin_excluded(self):
        d = self.DE.decide(self._need(), current=[self._cur("VBUSY")], incoming=[], order_available=True,
                           committed_vins={"VBUSY"}, score=lambda u: 5)
        self.assertEqual(d.call, self.DE.ORDER_FOR_DEMO)   # the only on-ground unit is committed elsewhere

    def test_fail_closed_when_economics_not_governed(self):
        d = self.DE.decide(self._need(), current=[self._cur("VNOW")], incoming=[self._inc("VSOON")])
        self.assertEqual(d.call, self.DE.UNRESOLVED)
        self.assertTrue(d.economics_gap)                   # names the exact missing Demo policy inputs
        self.assertEqual([u.vin for u in d.current_pool], ["VNOW"])   # physical pool still enumerated
        self.assertIn("expected Demo tenure", d.economics_gap)

    def test_no_executive_preference_input_exists(self):
        # structural guarantee: decide() takes no executive/preference argument — economics alone decide.
        import inspect
        params = set(inspect.signature(self.DE.decide).parameters)
        self.assertFalse({"executive", "preference", "exec_pref"} & params)


class TestWholesaleDealerCopy(unittest.TestCase):
    """The dealer-facing copy path (domains._readable_h) — human names lead, no internal codes/reasoning (item
    12/16). Also proves graceful degradation to the compact code form when nothing is governed yet."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        self.store = TranslationStore(self.app.prefs, SCOPE)
        SEED.seed(self.store)
        for r in self.store.variant_rows():
            if r.raw_code == "86317":
                self.store.approve_variant(r.family, r.raw_code, r.generation_id, r.package)

    def test_dealer_copy_leads_with_human_names_no_codes(self):
        from elite.ui.views import domains
        ident = "dms_planning|model=QX80|model_code=86317|exterior=QBE|interior=G"
        dealer = domains._readable_h(self.app, SCOPE, ident, dealer=True)
        self.assertEqual(dealer, "QX80 LUXE 2WD — Radiant White / Graphite")
        self.assertNotIn("86317", dealer)                    # no internal model code
        self.assertNotIn("QBE", dealer)                      # no internal colour code
        # operator form keeps the codes for precision
        op = domains._readable_h(self.app, SCOPE, ident)
        self.assertIn("Radiant White (QBE)", op)
        self.assertIn("QX80 LUXE 2WD", op)

    def test_ungoverned_identity_degrades_to_code_form(self):
        from elite.ui.views import domains
        ident = "dms_planning|model=QX99|model_code=99999|exterior=ZZZ|interior=Q"
        # nothing governed for these codes → compact code form, never uglier than before
        self.assertEqual(domains._readable_h(self.app, SCOPE, ident, dealer=True),
                         domains._readable(ident))


if __name__ == "__main__":
    unittest.main(verbosity=2)
