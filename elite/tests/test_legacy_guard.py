"""Acceptance 21, 22: legacy tests still pass; no legacy application file changed."""
import os
import subprocess
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


class TestLegacyGuard(unittest.TestCase):
    def test_21_legacy_tests_still_pass(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        r1 = subprocess.run(["python3", "pipeline_manager/tests/test_engine.py"],
                            cwd=_REPO, env=env, capture_output=True, text=True)
        r2 = subprocess.run(["python3", "pipeline_manager/tests/test_loaner_intel.py"],
                            cwd=_REPO, env=env, capture_output=True, text=True)
        self.assertIn("passed", (r1.stdout + r1.stderr), r1.stderr)
        self.assertIn("passed", (r2.stdout + r2.stderr), r2.stderr)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)

    def test_22_no_legacy_application_file_changed(self):
        # No diff on any legacy application path between the protected legacy line and
        # the current working tree (Elite Pipeline work lives only under elite/ and docs/).
        diff = subprocess.run(
            ["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
            cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        changed = [l for l in diff.stdout.strip().splitlines() if l.strip()]
        self.assertEqual(changed, [], f"legacy application files changed: {changed}")

    def test_22b_legacy_ref_unmoved(self):
        rev = subprocess.run(["git", "rev-parse", "legacy/inventory-tool"],
                             cwd=_REPO, capture_output=True, text=True).stdout.strip()
        self.assertTrue(rev.startswith("3bf9162"), f"legacy ref moved to {rev}")


if __name__ == "__main__":
    unittest.main()
