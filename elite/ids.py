"""Stable internal identifier generation.

IDs are opaque, collision-resistant, and (once assigned) stable across
persistence and reload — the stored value never changes on read. Prefixes make
record kind visible in logs without leaking data.
"""
from __future__ import annotations

import os
import time


def _b32(n: int, size: int) -> str:
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"  # Crockford-ish, no i/l/o/u
    s = []
    for _ in range(size):
        s.append(alphabet[n & 31])
        n >>= 5
    return "".join(reversed(s))


def new_id(prefix: str) -> str:
    """Time-ordered, random-tailed identifier. Monotonic-ish by creation time so
    IDs sort roughly by age; randomness prevents collisions."""
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(8), "big")
    return f"{prefix}_{_b32(ms, 10)}{_b32(rand, 13)}"


# Convenience typed factories (kind is visible in the identifier).
def principal_id() -> str: return new_id("prn")
def grant_id() -> str: return new_id("grt")
def audit_id() -> str: return new_id("aud")
def probe_id() -> str: return new_id("prb")
