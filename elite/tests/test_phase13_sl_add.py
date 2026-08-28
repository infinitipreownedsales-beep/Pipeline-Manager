"""BEST UNITS TO ADD TO SERVICE LOANER NOW — the operator's add-placement decision (live-shaped).

Proves the bounded ADD engine (elite.loaner.sl_add) runs the SETTLED transaction-price economics over physical
New-Retail SURPLUS VINs, framed as "place this VIN into Service Loaner instead of leaving it New Retail":

  * only over-stocked (EXCESS) units are ranked; SHORTAGE is protected out; COVERED is deferred (not guessed);
  * net = expected front-end gross at release (used selling price − adjusted basis, write-down counted ONCE)
    + ICV (incremental, earned by placing) + Velocity (contingent on the 240-day rule) − Retail opportunity
    cost ($0 for a genuine surplus unit);
  * MSRP is never substituted for the transaction rail;
  * FAIL-CLOSED: a physical surplus unit missing any authoritative term is BLOCKED with the exact field — never
    fabricated into the ranking to reach the requested count.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_add import rank_add_candidates, DEFAULT_ADD_TARGET
from elite.loaner.placement import EXCESS, COVERED, SHORTAGE
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore
from elite.newinv.dms_identity import dms_planning_identity

MODEL = "QX80"
CODE = "8331"
TODAY = "2026-08-27"


def _vin(tag):
    return ("5N1AZ" + "".join(ch for ch in tag if ch.isalnum())).ljust(17, "0")[:17]


def _unit(stock, tag, *, code=CODE, ext="QBE", inte="G", dis=10, msrp="70000", invoice="65000", year="2026",
          trim="LUXE 2WD", drivetrain="4WD"):
    row = {"stock_number": stock, "vin": _vin(tag), "model_code": code, "exterior": ext, "interior": inte,
           "dis": dis, "status": "Deal Open", "location": "DLR-INV", "year": year, "model": MODEL,
           "trim": trim, "drivetrain": drivetrain, "msrp": msrp}
    if invoice is not None:
        row["invoice"] = invoice
    return row


def _harm(mapping):
    idx = {}
    for (code, ext, inte), state in mapping.items():
        ident = dms_planning_identity({"model_code": code, "exterior": ext, "interior": inte})
        idx[ident] = {"state": state, "excess": 2 if state == EXCESS else 0,
                      "acquire": 2 if state == SHORTAGE else 0}
    return idx


def _priced_rows(model=MODEL, code=CODE, my=2026, ages=range(10, 22), per=6):
    """Observed used transaction rows for the same governed model code across lifecycle ages, so the settled
    transaction rail (_market_price PRIMARY) resolves an expected selling price at the release age."""
    out = []
    for a in ages:
        t = my * 12 + a
        y, m = t // 12, t % 12 + 1
        for k in range(per):
            out.append({"model": model, "model_number": code, "year": str(my),
                        "sold_date": f"{y:04d}-{m:02d}-15", "price": str(52000 - 300 * a + (k - 3) * 150),
                        "days_to_sell": "45"})
    return out


def _inv_rows(rows):
    return list(rows)


class TestAddRanking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        # NOTE: no projected_tenure_months is set — the ADD hold is DERIVED from the governed release backsolve
        # (total-to-retail − learned sell time − protection buffer), so a fixed tenure input is not required.
        pol.set_protection_buffer_days(15, actor="k", at="t")          # governed process/protection buffer (days)
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        pis.add("icv", effective_month="2026-01", model=MODEL, model_year="2026", value=6000, actor="k",
                recorded_at="t")
        pis.add("velocity", effective_month="2026-01", model=MODEL, model_year="2026", value=2000, day_cap=240,
                mile_cap=10000, actor="k", recorded_at="t")

    def tearDown(self):
        self.p.close()

    def _run(self, rows, harm, *, n=None, committed=frozenset()):
        priced = _priced_rows()
        with patch("elite.loaner.sl_add.read_new_retail_units", return_value=rows), \
             patch("elite.loaner.sl_add.certified_harm_index", return_value=harm), \
             patch("elite.loaner.sl_add._retail_rows", return_value=priced), \
             patch("elite.loaner.sl_add._inventory_rows", return_value=_inv_rows(rows)):
            return rank_add_candidates(self.app, SCOPE, n=n, today=TODAY, committed_vins=committed)

    def test_ranks_excess_and_protects_short_defers_covered(self):
        rows = [_unit("A1", "A1", invoice="65000"),                       # EXCESS, ready
                _unit("B2", "B2", invoice="60000"),                       # EXCESS, ready (lower basis -> higher net)
                _unit("S9", "S9", code="8481", ext="GAT", inte="D"),      # SHORTAGE -> protected
                _unit("C7", "C7", code="8361", ext="XKD", inte="A")]      # COVERED -> deferred
        harm = _harm({(CODE, "QBE", "G"): EXCESS, ("8481", "GAT", "D"): SHORTAGE, ("8361", "XKD", "A"): COVERED})
        res = self._run(rows, harm, n=4)
        stocks = [c.stock for c in res["ready"]]
        self.assertEqual(set(stocks), {"A1", "B2"})                       # only the two EXCESS units are ranked
        self.assertEqual(res["ready"][0].stock, "B2")                     # lower invoice basis -> higher net, ranked first
        self.assertGreater(res["ready"][0].add_net, res["ready"][1].add_net)
        self.assertEqual(res["protected"], 1)                             # SHORTAGE protected
        self.assertEqual(res["covered_deferred"], 1)                      # COVERED deferred, not guessed

    def test_net_uses_settled_rail_no_double_count(self):
        rows = [_unit("A1", "A1", invoice="65000")]
        res = self._run(rows, _harm({(CODE, "QBE", "G"): EXCESS}), n=1)
        c = res["ready"][0]
        # adjusted basis = invoice − write-down (write-down counted ONCE, embedded in the basis)
        self.assertEqual(round(c.adjusted_basis, 2), round(c.invoice - c.write_down, 2))
        # front-end gross = expected used price − adjusted basis (recon 0); NOT price − basis − write-down again
        self.assertEqual(round(c.front_end_gross, 2), round(c.expected_used_price - c.adjusted_basis, 2))
        # total net = front gross + ICV + Velocity(preserved) − retail opportunity cost(0)
        vel = c.velocity if c.velocity_preserved else 0
        self.assertEqual(round(c.add_net, 2), round(c.front_end_gross + c.icv + vel - c.retail_opportunity_cost, 2))
        self.assertEqual(c.icv, 6000)                                     # ICV earned by placing (incremental)
        self.assertEqual(c.retail_opportunity_cost, 0)                    # EXCESS surplus -> no retail harm

    def test_blocked_missing_invoice_is_named_never_fabricated(self):
        rows = [_unit("A1", "A1", invoice="65000"),                       # ready
                _unit("N2", "N2", invoice=None)]                          # EXCESS surplus but NO invoice -> BLOCKED
        res = self._run(rows, _harm({(CODE, "QBE", "G"): EXCESS}), n=4)
        self.assertEqual([c.stock for c in res["ready"]], ["A1"])         # only the evaluable unit is ready
        self.assertEqual(len(res["blocked"]), 1)
        b = res["blocked"][0]
        self.assertEqual(b.stock, "N2")
        self.assertIn("invoice", b.missing.lower())                       # exact missing field named
        # fail-closed: never fabricates N2 into the ranking to reach 4
        self.assertNotIn("N2", [c.stock for c in res["ready"]])

    def test_default_target_is_four_and_adjustable(self):
        rows = [_unit(f"U{i}", f"U{i}", invoice=str(64000 - i * 500)) for i in range(6)]
        harm = _harm({(CODE, "QBE", "G"): EXCESS})
        res4 = self._run(rows, harm, n=None)                              # no n -> default target
        self.assertEqual(res4["requested"], DEFAULT_ADD_TARGET)
        self.assertEqual(len(res4["ready"]), 4)                           # top 4
        self.assertEqual(len(res4["backups"]), 2)                        # remaining surplus as backups
        res6 = self._run(rows, harm, n=6)
        self.assertEqual(len(res6["ready"]), 6)                           # operator-adjustable up

    def test_hold_is_derived_from_release_backsolve_not_fixed_tenure(self):
        # no projected_tenure_months is set anywhere; the hold must still resolve from the governed backsolve:
        #   release_by = today + total_to_retail(240) − sell_time(45) − buffer(15) = today + 180
        rows = [_unit("A1", "A1", invoice="65000")]
        res = self._run(rows, _harm({(CODE, "QBE", "G"): EXCESS}), n=1)
        self.assertEqual(len(res["ready"]), 1)                            # resolves WITHOUT a fixed tenure input
        c = res["ready"][0]
        self.assertEqual(c.hold_days, 240 - 45 - 15)                      # derived, not hardwired
        self.assertEqual(c.release_by, "2027-02-23")                      # today (2026-08-27) + 180 days
        # write-down accrues over exactly the derived hold, and Velocity is preserved (final sale inside 240)
        self.assertTrue(c.velocity_preserved)

    def test_missing_protection_buffer_blocks_with_named_field(self):
        # an UNSET governed buffer (None) -> the release backsolve cannot resolve -> BLOCKED on THAT exact input
        with patch.object(SLPolicyStore, "protection_buffer_days", return_value=None):
            rows = [_unit("A1", "A1", invoice="65000")]
            res = self._run(rows, _harm({(CODE, "QBE", "G"): EXCESS}), n=4)
        self.assertEqual(res["ready"], [])
        self.assertEqual(len(res["blocked"]), 1)
        self.assertIn("buffer", res["blocked"][0].missing.lower())        # names the protection/process buffer

    def test_missing_sell_time_evidence_blocks_with_named_field(self):
        # no resale history for the model -> estimate_sell_time returns None -> BLOCKED on sell-time evidence
        rows = [_unit("A1", "A1", invoice="65000")]
        with patch("elite.loaner.sl_add.read_new_retail_units", return_value=rows), \
             patch("elite.loaner.sl_add.certified_harm_index",
                   return_value=_harm({(CODE, "QBE", "G"): EXCESS})), \
             patch("elite.loaner.sl_add._retail_rows", return_value=[]), \
             patch("elite.loaner.sl_add._inventory_rows", return_value=rows):
            res = rank_add_candidates(self.app, SCOPE, n=4, today=TODAY)
        self.assertEqual(res["ready"], [])
        self.assertEqual(len(res["blocked"]), 1)
        self.assertIn("sell-time", res["blocked"][0].missing.lower())     # names the missing sell-time evidence

    def test_invoice_consumed_from_source_inv_field_without_vin(self):
        # The real pipeline_summary row shape: NO full VIN (serial/stock only), invoice carried on the row under
        # the governed `inv` field (DMS "Inv" column). The unit must resolve READY reading invoice from `inv` —
        # no per-VIN override, no invented VIN, no manual entry.
        row = {"stock_number": "Q26029", "serial": "430938", "model_code": CODE, "exterior": "QBE",
               "interior": "G", "dis": 12, "status": "Deal Open", "location": "DLR-INV", "year": "2026",
               "model": MODEL, "trim": "SPORT 4WD", "drivetrain": "4WD", "msrp": "72,000", "inv": "63,500"}
        res = self._run([row], _harm({(CODE, "QBE", "G"): EXCESS}), n=4)
        self.assertEqual(len(res["ready"]), 1)                            # resolves from source data we already have
        self.assertEqual(res["blocked"], [])                             # no longer blocked on authoritative invoice
        c = res["ready"][0]
        self.assertEqual(c.invoice, 63500)                               # read from `inv`, not MSRP (72,000)
        self.assertFalse(c.vin_authoritative)                            # serial-only source; no VIN invented
        self.assertEqual(c.serial, "430938")
        self.assertEqual(round(c.adjusted_basis, 2), round(63500 - c.write_down, 2))

    def test_committed_vin_excluded(self):
        rows = [_unit("A1", "A1", invoice="65000")]
        committed = frozenset({_vin("A1")})
        res = self._run(rows, _harm({(CODE, "QBE", "G"): EXCESS}), n=4, committed=committed)
        self.assertEqual(res["ready"], [])                                # already committed -> not eligible
        self.assertEqual(res["eligible"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
