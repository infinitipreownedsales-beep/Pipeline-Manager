"""Authentication foundation — identity proof ONLY.

Authentication answers "is this Principal who they claim to be" and nothing about
what they may do. Credentials are salted + peppered PBKDF2 hashes; the pepper comes
from configuration (env), never source. Authentication success does NOT imply any
authority — authorization is a separate concern (authz.py).
"""
from __future__ import annotations

import hashlib
import hmac
import os

from .errors import AuthenticationError
from .ids import principal_id as _new_principal_id
from .models import Principal

_ITERATIONS = 120_000


def _hash(secret: str, salt: str, pepper: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", (secret + pepper).encode(), bytes.fromhex(salt), _ITERATIONS)
    return dk.hex()


class Authenticator:
    def __init__(self, principals, pepper: str):
        self.principals = principals   # PrincipalRepository
        self._pepper = pepper

    def register(self, display_name: str, secret: str) -> Principal:
        salt = os.urandom(16).hex()
        p = Principal(id=_new_principal_id(), display_name=display_name)
        return self.principals.add(p, _hash(secret, salt, self._pepper), salt)

    def authenticate(self, principal_id: str, secret: str) -> Principal:
        creds = self.principals.credentials(principal_id)
        # Constant-ish path: always compute a hash to reduce trivial timing signal.
        if creds is None:
            _hash(secret, "00" * 16, self._pepper)
            raise AuthenticationError(technical_detail="unknown principal")
        if not creds["active"]:
            raise AuthenticationError(message="This account is not active.",
                                      technical_detail="inactive principal")
        candidate = _hash(secret, creds["secret_salt"], self._pepper)
        if not hmac.compare_digest(candidate, creds["secret_hash"]):
            raise AuthenticationError(technical_detail="bad secret")
        return self.principals.get(principal_id)
