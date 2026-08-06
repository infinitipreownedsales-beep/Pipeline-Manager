"""Operational configuration for the controlled pilot.

Explicit environment configuration with SAFE DEFAULTS, startup validation, and secret hygiene. No secret
is ever read from source control (secrets come from the environment, via the Phase 1 Config). Invalid
configuration fails clearly. The resolved configuration is visible in safe diagnostics WITHOUT exposing
secrets. Environment-specific configuration never changes domain logic — it only changes where files live,
how large an upload may be, how long a session lasts, and whether pilot mode is on.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..errors import ConfigurationError
from .models import ALLOWED_EXTENSIONS, DEFAULT_MAX_UPLOAD_BYTES

# name -> (default, kind). required operational fields have safe non-secret defaults suitable for a pilot.
OPS_FIELDS = {
    "ELITE_BIND_HOST": ("127.0.0.1", str),          # loopback default; a non-loopback bind must be explicit
    "ELITE_UI_PORT": (8010, int),
    "ELITE_DEALERSHIP_TZ": ("America/Chicago", str),
    "ELITE_UPLOAD_DIR": ("./pilot/uploads", str),
    "ELITE_RAW_RETENTION_DIR": ("./pilot/raw", str),
    "ELITE_QUARANTINE_DIR": ("./pilot/quarantine", str),
    "ELITE_BACKUP_DIR": ("./pilot/backups", str),
    "ELITE_LOG_DIR": ("./pilot/logs", str),
    "ELITE_SESSION_EXPIRY_SECONDS": (3600, int),
    "ELITE_MAX_UPLOAD_BYTES": (DEFAULT_MAX_UPLOAD_BYTES, int),
    "ELITE_STALE_THRESHOLD_SECONDS": (172800, int),  # 48h default stale threshold
    "ELITE_PILOT_MODE": (True, bool),
}

# hosts that are safe without extra confirmation; anything else requires ELITE_ALLOW_NONLOOPBACK=1
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _coerce(kind, raw):
    if kind is bool:
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if kind is int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise ConfigurationError(message="Invalid configuration value.",
                                     technical_detail=f"expected int, got {raw!r}")
    return raw


@dataclass(frozen=True)
class OpsConfig:
    values: dict = field(default_factory=dict)

    def get(self, name):
        return self.values.get(name)

    @property
    def bind_host(self):
        return self.values["ELITE_BIND_HOST"]

    @property
    def port(self):
        return self.values["ELITE_UI_PORT"]

    @property
    def pilot_mode(self):
        return self.values["ELITE_PILOT_MODE"]

    @property
    def max_upload_bytes(self):
        return self.values["ELITE_MAX_UPLOAD_BYTES"]

    @property
    def session_expiry_seconds(self):
        return self.values["ELITE_SESSION_EXPIRY_SECONDS"]

    def redacted(self):
        """Diagnostics-safe view. No secret keys are present in OPS_FIELDS at all, so this is the full
        operational config; any accidental secret-looking key is masked defensively."""
        out = {}
        for k, v in self.values.items():
            out[k] = "***" if any(s in k.lower() for s in ("secret", "password", "token", "pepper")) else v
        return out

    def directories(self):
        return [self.values[k] for k in
                ("ELITE_UPLOAD_DIR", "ELITE_RAW_RETENTION_DIR", "ELITE_QUARANTINE_DIR",
                 "ELITE_BACKUP_DIR", "ELITE_LOG_DIR")]


def load_ops_config(env=None):
    env = os.environ if env is None else env
    values = {}
    for name, (default, kind) in OPS_FIELDS.items():
        raw = env.get(name)
        values[name] = default if raw is None or str(raw).strip() == "" else _coerce(kind, raw)
    # clear, early validation
    if values["ELITE_UI_PORT"] <= 0 or values["ELITE_UI_PORT"] > 65535:
        raise ConfigurationError(message="Invalid port.", technical_detail="ELITE_UI_PORT out of range")
    if values["ELITE_MAX_UPLOAD_BYTES"] <= 0:
        raise ConfigurationError(message="Invalid max upload size.",
                                 technical_detail="ELITE_MAX_UPLOAD_BYTES must be positive")
    host = values["ELITE_BIND_HOST"]
    if host not in _LOOPBACK:
        allow = str(env.get("ELITE_ALLOW_NONLOOPBACK", "")).strip().lower() in ("1", "true", "yes", "on")
        if not allow:
            raise ConfigurationError(
                message="A non-loopback bind host requires explicit confirmation.",
                technical_detail=f"unsafe_host_binding: {host} requires ELITE_ALLOW_NONLOOPBACK=1")
    values.setdefault("ELITE_ALLOWED_EXTENSIONS", sorted(ALLOWED_EXTENSIONS))
    return OpsConfig(values=values)
