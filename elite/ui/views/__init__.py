"""Phase 10 operator view functions. `register(app)` wires every screen's routes."""
from __future__ import annotations


def register(app):
    from . import auth, decision, domains, govern, inbox, operator, queues, search, translation, program_inputs
    for module in (auth, operator, inbox, decision, queues, domains, govern, search, translation, program_inputs):
        module.register(app)
