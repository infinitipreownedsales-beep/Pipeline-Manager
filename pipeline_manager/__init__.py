"""Elite Pipeline Manager — a deterministic new-car ordering engine.

Ported out of Excel for one reason: it must recompute everything from the two
dealer exports on every run, with no stale state.  See engine.run().
"""

from .config import Settings
from .engine import run

__all__ = ["Settings", "run"]
__version__ = "1.0.0"
