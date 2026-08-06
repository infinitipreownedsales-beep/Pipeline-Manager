"""Phase 10 operator view functions. `register(app)` wires every screen's routes."""
from __future__ import annotations


def register(app):
    from . import auth, decision, domains, govern, inbox, queues, search
    for module in (auth, inbox, decision, queues, domains, govern, search):
        module.register(app)
