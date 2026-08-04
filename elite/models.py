"""Platform record types. Narrow by design — no domain schemas in Phase 1.

Three record families are kept conceptually distinct (they must not be merged):
  * Audit Event  — the governance trail of who did what (this file: AuditEvent).
  * Business Fact — authoritative domain records (later phases).
  * Actual Event — observed real-world occurrences (later phases).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Principal:
    id: str
    display_name: str
    active: bool = True
    version: int = 1
    created_at: Optional[str] = None


@dataclass
class CapabilityGrant:
    """An authority to exercise a Capability within a Scope. Not a job title —
    authority is granted state, revocable, and effective-checked."""
    id: str
    principal_id: str
    capability: str          # e.g. "audit.read", "principal.grant"
    authority: str           # source of authority (e.g. "system", "owner")
    scope: str               # e.g. "store:HERRIN_GEAR" or "*"
    active: bool = True
    version: int = 1
    granted_at: Optional[str] = None
    revoked_at: Optional[str] = None

    def effective(self) -> bool:
        return self.active and self.revoked_at is None


@dataclass
class AuditEvent:
    id: str
    actor: str
    action: str
    environment: str
    occurred_at: str
    result: str                       # "success" | "denied" | "error"
    target_ref: Optional[str] = None
    scope: Optional[str] = None
    correlation_id: Optional[str] = None
    delegated_actor: Optional[str] = None
    prior_ref: Optional[str] = None
    resulting_ref: Optional[str] = None


@dataclass
class PersistenceProbe:
    id: str
    note: str = ""
    created_at: Optional[str] = None
