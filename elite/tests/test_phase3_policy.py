"""Phase 3 acceptance — Policy taxonomy, effective dating, lifecycle, deterministic
resolution, typed assumptions, and timezone boundaries (items 1-31).

Synthetic values only — no real incentives, allowances, write-downs, or windows.
"""
import os
import sqlite3
import tempfile
import unittest

from elite.errors import ValidationError
from elite.policy import guards, lifecycle
from elite.policy.assumptions import validate_assumption
from elite.policy.fixtures import Phase3, local_date_to_utc
from elite.policy.resolution import CONFLICTING, RESOLVED, UNRESOLVED, resolve

SCOPE = "store:HG"
PAST_S = "2020-01-01T00:00:00+00:00"
PAST_E = "2021-01-01T00:00:00+00:00"
IN_PAST = "2020-06-01T00:00:00+00:00"
NOW = "2026-06-01T00:00:00+00:00"
FUTURE = "2030-01-01T00:00:00+00:00"
PCT_A = {"kind": "percentage", "value": 10, "denominator": "msrp"}
PCT_B = {"kind": "percentage", "value": 20, "denominator": "msrp"}


class TestPhase3Policy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase3(self.dbp)

    def tearDown(self):
        self.p.close()

    def _v(self, vid):
        return self.p.store.get_version(vid)

    # ---- persistence across restart (append-preserving durable store) ----
    def test_01_policy_family_survives_restart(self):
        f = self.p.family()
        self.p.close()
        p2 = Phase3(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_family(f.id))
        self.assertEqual(p2.store.get_family(f.id).category, f.category)

    def test_02_policy_version_survives_restart(self):
        f = self.p.family()
        v = self.p.version(f.id, PCT_A, scope={"store": "HG"})
        self.p.close()
        p2 = Phase3(self.dbp)
        self.addCleanup(p2.close)
        self.assertEqual(p2.store.get_version(v.id).value, PCT_A)

    # ---- immutability + append-only (enforced by triggers) ----
    def test_03_version_value_is_immutable(self):
        f = self.p.family()
        v = self.p.version(f.id, PCT_A)
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("UPDATE policy_version SET value=? WHERE id=?",
                                          ('{"kind":"percentage","value":99}', v.id))
        self.assertEqual(self._v(v.id).value, PCT_A)   # unchanged

    def test_04_version_cannot_be_deleted(self):
        f = self.p.family()
        v = self.p.version(f.id, PCT_A)
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("DELETE FROM policy_version WHERE id=?", (v.id,))
        self.assertIsNotNone(self._v(v.id))

    # ---- non-resolving lifecycle states ----
    def test_05_draft_does_not_resolve(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="DRAFT")
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, UNRESOLVED)

    def test_06_proposed_does_not_resolve(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="PROPOSED")
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, UNRESOLVED)

    def test_13_rejected_never_resolves(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="REJECTED")
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW).status, UNRESOLVED)
        # not even as historical
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW,
                                 historical=True).status, UNRESOLVED)

    def test_14_withdrawn_never_resolves(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="WITHDRAWN")
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW).status, UNRESOLVED)
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW,
                                 historical=True).status, UNRESOLVED)

    # ---- approval / scheduling / activation timing ----
    def test_07_approval_never_auto_activates_future_version(self):
        f = self.p.family()
        v = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="DRAFT", effective_start=FUTURE)
        lifecycle.propose(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id, self._v(v.id).version)
        lifecycle.approve(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id, self._v(v.id).version,
                          clock=self.p.clock)
        self.assertEqual(self._v(v.id).lifecycle_status, "APPROVED")     # NOT ACTIVE
        self.assertEqual(self._v(v.id).approval_state, "approved")
        lifecycle.schedule(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id, self._v(v.id).version,
                           activation_time=FUTURE)
        self.assertEqual(self._v(v.id).lifecycle_status, "SCHEDULED")
        # scheduled-but-future does not resolve as current at NOW
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW).status,
                         UNRESOLVED)

    def test_08_activation_rejected_before_effective_time(self):
        f = self.p.family()
        future = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="APPROVED", effective_start=FUTURE)
        with self.assertRaises(ValidationError):
            lifecycle.activate(self.p.gov, self.p.store, self.p.owner, SCOPE, future.id,
                               self._v(future.id).version, clock=self.p.clock)
        # a version already effective activates
        ready = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="APPROVED", effective_start=PAST_S)
        lifecycle.activate(self.p.gov, self.p.store, self.p.owner, SCOPE, ready.id,
                           self._v(ready.id).version, clock=self.p.clock)
        self.assertEqual(self._v(ready.id).lifecycle_status, "ACTIVE")

    # ---- expiration: not current, still historical ----
    def test_09_expired_has_no_current_resolution(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="EXPIRED",
                       effective_start=PAST_S, effective_end=PAST_E)
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW).status,
                         UNRESOLVED)

    def test_10_expired_still_resolves_historically(self):
        f = self.p.family()
        v = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="EXPIRED",
                           effective_start=PAST_S, effective_end=PAST_E)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=IN_PAST, historical=True)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.version.id, v.id)

    def test_11_superseded_version_remains_inspectable(self):
        f = self.p.family()
        old = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        new = self.p.version(f.id, PCT_B, scope={"store": "HG"}, lifecycle="ACTIVE",
                             effective_start=NOW, version_number=2)
        lifecycle.supersede(self.p.gov, self.p.store, self.p.owner, SCOPE, old.id, new)
        self.assertEqual(self._v(old.id).lifecycle_status, "SUPERSEDED")
        self.assertEqual(self._v(old.id).value, PCT_A)              # original-as-known preserved
        self.assertEqual(self._v(old.id).superseded_by, new.id)

    def test_12_revoked_does_not_resolve(self):
        f = self.p.family()
        v = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        lifecycle.revoke(self.p.gov, self.p.store, self.p.owner, SCOPE, v.id, self._v(v.id).version,
                         revocation={"effective_at": NOW, "reason": "synthetic"})
        self.assertEqual(self._v(v.id).lifecycle_status, "REVOKED")
        self.assertEqual(resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW).status,
                         UNRESOLVED)

    def test_15_correction_preserves_original(self):
        f = self.p.family()
        orig = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="DRAFT")
        new = lifecycle.correct(self.p.gov, self.p.store, self.p.owner, SCOPE, orig.id, PCT_B,
                                clock=self.p.clock)
        self.assertEqual(self._v(orig.id).lifecycle_status, "CORRECTED")
        self.assertEqual(self._v(orig.id).value, PCT_A)            # original unchanged
        self.assertEqual(new.correction_of, orig.id)
        self.assertEqual(new.value, PCT_B)

    # ---- scope specificity + isolation ----
    def test_16_more_specific_scope_overrides_broader(self):
        f = self.p.family(dims=["store", "model"])
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        self.p.version(f.id, PCT_B, scope={"store": "HG", "model": "QX80"}, lifecycle="ACTIVE",
                       effective_start=PAST_S, version_number=2)
        r = resolve(self.p.store, f, subject_scope={"store": "HG", "model": "QX80"}, at_time=NOW)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.value, PCT_B)                           # the more specific one

    def test_17_scope_does_not_leak_across_stores(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        r = resolve(self.p.store, f, subject_scope={"store": "OTHER"}, at_time=NOW)
        self.assertEqual(r.status, UNRESOLVED)                     # HG policy never applies to OTHER

    def test_18_unsupported_scope_dimension_rejected(self):
        f = self.p.family(dims=["store", "model"])
        guards.validate_scope(f, {"store": "HG", "model": "QX80"})   # ok
        with self.assertRaises(ValidationError):
            guards.validate_scope(f, {"store": "HG", "franchise": "X"})

    # ---- deterministic conflict handling ----
    def test_19_latest_recorded_does_not_auto_win(self):
        f = self.p.family()
        older = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        newer = self.p.version(f.id, PCT_B, scope={"store": "HG"}, lifecycle="ACTIVE",
                               effective_start=PAST_S, version_number=2)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, CONFLICTING)                    # newer did NOT silently win
        # an approved precedence naming the OLDER value wins — proving recency is not the rule
        r2 = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW, precedence=[older.id])
        self.assertEqual(r2.value, PCT_A)

    def test_20_equally_applicable_conflict_is_explicit(self):
        f = self.p.family()
        a = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="ACTIVE", effective_start=PAST_S)
        b = self.p.version(f.id, PCT_B, scope={"store": "HG"}, lifecycle="ACTIVE",
                           effective_start=PAST_S, version_number=2)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, CONFLICTING)
        self.assertEqual(set(r.candidates), {a.id, b.id})          # no silent pick

    # ---- fallback: only what the family declares ----
    def test_21_approved_fallback_used_only_when_declared(self):
        f = self.p.family()
        bv = self.p.version(f.id, PCT_A, scope={"store": "ELSEWHERE"}, lifecycle="ACTIVE",
                            effective_start=PAST_S)
        f.default_resolution = {"mode": "broad_fallback", "version_id": bv.id}
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, RESOLVED)
        self.assertTrue(r.fallback_used)
        self.assertEqual(r.value, PCT_A)

    def test_22_no_applicable_and_no_fallback_is_unresolved(self):
        f = self.p.family(default_resolution={"mode": "unresolved"})
        self.p.version(f.id, PCT_A, scope={"store": "ELSEWHERE"}, lifecycle="ACTIVE", effective_start=PAST_S)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, UNRESOLVED)
        self.assertFalse(r.fallback_used)                          # system never invents a value

    # ---- category separation + typed assumptions ----
    def test_23_technical_config_is_not_business_policy(self):
        tech = self.p.family(category="CALCULATION_CONFIGURATION")
        biz = self.p.family(category="FINANCIAL_ASSUMPTION")
        self.assertFalse(guards.is_business_policy(tech))
        self.assertTrue(guards.is_business_policy(biz))

    def test_24_assumption_type_and_unit_validated(self):
        self.assertEqual(validate_assumption("duration", {"value": 30, "unit": "days"})["unit"], "days")
        with self.assertRaises(ValidationError):
            validate_assumption("duration", {"value": 30, "unit": "fortnights"})
        with self.assertRaises(ValidationError):
            validate_assumption("currency", {"amount": 100})       # missing currency code

    def test_25_zero_is_a_valid_assumption_value(self):
        out = validate_assumption("currency", {"amount": 0, "currency": "USD"})
        self.assertEqual(out["amount"], 0)

    def test_26_blank_is_not_silently_zero(self):
        with self.assertRaises(ValidationError):
            validate_assumption("currency", {"amount": "", "currency": "USD"})
        with self.assertRaises(ValidationError):
            validate_assumption("currency", {"currency": "USD"})   # missing amount

    def test_27_percentage_requires_denominator(self):
        with self.assertRaises(ValidationError):
            validate_assumption("percentage", {"value": 10})

    # ---- timezone effective-date boundary ----
    def test_28_dealership_tz_date_boundary_maps_to_utc(self):
        start = local_date_to_utc("2026-03-15", end=False)
        end = local_date_to_utc("2026-03-15", end=True)
        self.assertTrue(start.endswith("+00:00"))
        self.assertIn("2026-03-15T05:00:00", start)                 # CDT midnight -> 05:00 UTC
        self.assertLess(start, end)

    # ---- historical vs current answers never rewrite each other ----
    def test_29_historical_retains_the_version_in_force_then(self):
        f = self.p.family()
        old = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="EXPIRED",
                             effective_start=PAST_S, effective_end=PAST_E)
        self.p.version(f.id, PCT_B, scope={"store": "HG"}, lifecycle="ACTIVE",
                       effective_start=NOW, version_number=2)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=IN_PAST, historical=True)
        self.assertEqual(r.version.id, old.id)

    def test_30_current_uses_the_newer_effective_version(self):
        f = self.p.family()
        self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="EXPIRED",
                       effective_start=PAST_S, effective_end=PAST_E)
        new = self.p.version(f.id, PCT_B, scope={"store": "HG"}, lifecycle="ACTIVE",
                             effective_start=NOW, version_number=2)
        r = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        self.assertEqual(r.status, RESOLVED)
        self.assertEqual(r.version.id, new.id)

    def test_31_current_recompute_does_not_rewrite_history(self):
        f = self.p.family()
        old = self.p.version(f.id, PCT_A, scope={"store": "HG"}, lifecycle="EXPIRED",
                             effective_start=PAST_S, effective_end=PAST_E)
        new = self.p.version(f.id, PCT_B, scope={"store": "HG"}, lifecycle="ACTIVE",
                             effective_start=NOW, version_number=2)
        cur = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=NOW)
        hist = resolve(self.p.store, f, subject_scope={"store": "HG"}, at_time=IN_PAST, historical=True)
        self.assertEqual(cur.version.id, new.id)
        self.assertEqual(hist.version.id, old.id)                  # history answer is stable


if __name__ == "__main__":
    unittest.main()
