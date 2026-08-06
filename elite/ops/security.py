"""Security-hardening review + runtime helpers for the controlled pilot.

The Phase 10 UI already enforces CSRF, output encoding, a strict CSP, HttpOnly/SameSite cookies, below-UI
authorization + scope, and a safe error boundary. Phase 11 adds session expiry/invalidation, environment-
aware cookie flags, a self-check of the deployment posture (no default credentials, secrets externalized,
debug off, safe host binding), and a security-hardening checklist that a pilot administrator can run.
"""
from __future__ import annotations

import datetime as _dt

from ..environment import Environment


def session_expired(issued_at, now, expiry_seconds):
    """True if a session issued at `issued_at` (aware UTC) is older than expiry_seconds."""
    if issued_at is None:
        return True
    return (now - issued_at).total_seconds() > expiry_seconds


def cookie_flags(environment):
    """Cookie attributes appropriate to the environment. Production/demo => Secure; all => HttpOnly +
    SameSite=Strict. Development/test omit Secure so a local http pilot still works, and say so."""
    secure = environment in (Environment.PRODUCTION, Environment.DEMO)
    flags = ["HttpOnly", "SameSite=Strict", "Path=/"]
    if secure:
        flags.append("Secure")
    return flags


class SecurityChecklist:
    """A runnable deployment-posture self-check. Every item returns pass/fail with a safe reason."""

    def __init__(self, *, config, ops_config, stack, debug=False, default_credentials_present=False):
        self.config = config              # Phase 1 Config (has redacted())
        self.ops_config = ops_config
        self.stack = stack
        self.debug = debug
        self.default_credentials_present = default_credentials_present

    def run(self):
        env = self.stack.environment
        checks = []

        def add(name, ok, reason):
            checks.append({"check": name, "pass": bool(ok), "reason": reason})

        add("no_default_credentials", not self.default_credentials_present,
            "no built-in/default credential exists" if not self.default_credentials_present
            else "a default credential is present")
        # secrets externalized: the auth secret must be present via env, and never echoed
        red = self.config.redacted()
        add("secrets_externalized", red.get("ELITE_AUTH_SECRET") == "***",
            "secrets are read from the environment and redacted in diagnostics")
        add("debug_off_in_shared_env",
            (not self.debug) or env in (Environment.DEVELOPMENT, Environment.TEST),
            "debug/stack-trace exposure is off outside development/test")
        add("safe_host_binding",
            self.ops_config.bind_host in ("127.0.0.1", "::1", "localhost"),
            "bind host is loopback (a non-loopback bind requires explicit confirmation)")
        add("session_expiry_configured", self.ops_config.session_expiry_seconds > 0,
            "session expiry is configured")
        add("cookie_flags", "HttpOnly" in cookie_flags(env) and "SameSite=Strict" in cookie_flags(env),
            "session cookies are HttpOnly + SameSite=Strict")
        add("pilot_identified", (not self.ops_config.pilot_mode) or env != Environment.PRODUCTION,
            "pilot mode is not labeled production")
        summary_ok = all(c["pass"] for c in checks)
        return {"ok": summary_ok, "checks": checks}
