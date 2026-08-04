"""Configuration loading and validation.

- A declared schema of fields (name, type, required, secret, default-allowed).
- Critical/required fields missing => safe startup failure (ConfigurationError).
- Secrets are read only from the environment, never from tracked source, and are
  never echoed by `redacted()`.
- No hidden default may convert missing configuration into business policy:
  required fields have NO default; only explicitly non-critical fields may default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .environment import Environment, resolve_environment
from .errors import ConfigurationError


@dataclass(frozen=True)
class Field:
    name: str          # env var name
    type: type = str
    required: bool = True
    secret: bool = False
    default: object = None      # only honored when required is False


# Minimal platform schema. Domain config is intentionally out of scope for Phase 1.
SCHEMA = [
    Field("ELITE_ENV", str, required=True),
    Field("ELITE_DB_PATH", str, required=True),          # authoritative store location
    Field("ELITE_DEALERSHIP_TZ", str, required=False, default="America/Chicago"),
    Field("ELITE_AUTH_SECRET", str, required=True, secret=True),  # pepper for credential hashing
    Field("ELITE_LOG_LEVEL", str, required=False, default="INFO"),
]


def _coerce(field: Field, raw: str):
    if field.type is bool:
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if field.type is int:
        try:
            return int(raw)
        except ValueError:
            raise ConfigurationError(
                message="Invalid configuration value.",
                technical_detail=f"{field.name} must be an integer.")
    return raw


@dataclass(frozen=True)
class Config:
    environment: Environment
    values: dict            # non-secret values only
    _secrets: dict          # secret values, never exposed by redacted()

    def get(self, name: str):
        if name in self.values:
            return self.values[name]
        if name in self._secrets:
            return self._secrets[name]
        raise ConfigurationError(message="Unknown configuration key.",
                                 technical_detail=f"{name} is not declared.")

    def secret(self, name: str) -> str:
        if name not in self._secrets:
            raise ConfigurationError(message="Unknown secret.",
                                     technical_detail=f"{name} is not a declared secret.")
        return self._secrets[name]

    def redacted(self) -> dict:
        """Log/diagnostics-safe view: environment + non-secret values; secrets shown
        only as the marker '***' so their presence is known but value is never leaked."""
        out = {"ELITE_ENV": self.environment.value}
        out.update(self.values)
        for f in SCHEMA:
            if f.secret:
                out[f.name] = "***" if f.name in self._secrets else "<unset>"
        return out


def load_config(env: dict | None = None) -> Config:
    env = os.environ if env is None else env
    environment = resolve_environment(env)
    values, secrets, missing = {}, {}, []
    for f in SCHEMA:
        if f.name == "ELITE_ENV":
            continue
        raw = env.get(f.name)
        if raw is None or str(raw).strip() == "":
            if f.required:
                missing.append(f.name)
            elif f.default is not None:
                values[f.name] = f.default
            continue
        coerced = _coerce(f, raw)
        (secrets if f.secret else values)[f.name] = coerced
    if missing:
        # Safe startup failure — never fabricate business policy from absence.
        raise ConfigurationError(
            message="The system is not configured to start.",
            technical_detail="Missing critical configuration: " + ", ".join(sorted(missing)))
    return Config(environment=environment, values=values, _secrets=secrets)
