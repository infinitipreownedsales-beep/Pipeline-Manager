"""Acceptance 1, 2, 3: configuration + environment identity + secret hygiene."""
import os
import subprocess
import unittest

from elite.config import load_config
from elite.environment import Environment, resolve_environment
from elite.errors import ConfigurationError

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VALID_PROD = {"ELITE_ENV": "production", "ELITE_DB_PATH": "/tmp/x.db",
              "ELITE_AUTH_SECRET": "s"}


class TestConfigEnv(unittest.TestCase):
    def test_1_production_cannot_start_with_invalid_config(self):
        env = dict(VALID_PROD); del env["ELITE_AUTH_SECRET"]  # missing critical secret
        with self.assertRaises(ConfigurationError) as ctx:
            load_config(env)
        self.assertIn("ELITE_AUTH_SECRET", ctx.exception.technical_detail)
        # And a fully valid production config DOES start.
        cfg = load_config(VALID_PROD)
        self.assertIs(cfg.environment, Environment.PRODUCTION)

    def test_2_dev_and_prod_cannot_be_silently_confused(self):
        with self.assertRaises(ConfigurationError):   # unset -> refuse, no default
            resolve_environment({})
        with self.assertRaises(ConfigurationError):   # unknown -> refuse
            resolve_environment({"ELITE_ENV": "prod-ish"})
        self.assertIs(resolve_environment({"ELITE_ENV": "development"}), Environment.DEVELOPMENT)
        self.assertIs(resolve_environment({"ELITE_ENV": "production"}), Environment.PRODUCTION)
        self.assertNotEqual(Environment.DEVELOPMENT, Environment.PRODUCTION)

    def test_2b_no_hidden_default_turns_missing_config_into_policy(self):
        # A required field has no default; absence fails rather than inventing a value.
        env = dict(VALID_PROD); del env["ELITE_DB_PATH"]
        with self.assertRaises(ConfigurationError):
            load_config(env)

    def test_2c_secret_never_echoed(self):
        cfg = load_config(VALID_PROD)
        red = cfg.redacted()
        self.assertEqual(red["ELITE_AUTH_SECRET"], "***")
        self.assertNotIn("s", [v for k, v in red.items() if k == "ELITE_AUTH_SECRET"] and [])
        self.assertEqual(cfg.secret("ELITE_AUTH_SECRET"), "s")  # available internally only

    def test_3_no_production_secret_in_tracked_source(self):
        tracked = subprocess.check_output(
            ["git", "ls-files", "elite", "build", "pipeline_manager"], cwd=_REPO).decode().split()
        import re
        patterns = [re.compile(p) for p in (
            r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"(?i)(password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]")]
        offenders = []
        for path in tracked:
            full = os.path.join(_REPO, path)
            try:
                text = open(full, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for pat in patterns:
                if pat.search(text):
                    offenders.append((path, pat.pattern))
        self.assertEqual(offenders, [], f"possible secrets in tracked source: {offenders}")


if __name__ == "__main__":
    unittest.main()
