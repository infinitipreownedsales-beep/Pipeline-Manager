"""Phase 10 operator view functions. `register(app)` wires every screen's routes."""
from __future__ import annotations


def register(app):
    from . import auth, decision, domains, govern, inbox, operator, queues, search
    for module in (auth, operator, inbox, decision, queues, domains, govern, search):
        module.register(app)
