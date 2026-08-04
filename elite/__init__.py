"""Elite Pipeline — platform foundation (Phase 1).

Smallest authoritative platform primitives for later domain implementation.
Standard-library only; SQLite is the durable authoritative store. This package
is NEW and does not touch the preserved legacy application (`pipeline_manager/`,
`build/`, `Pipeline-Manager.html`).

Layering (business logic stays out of presentation; persistence sits behind
repository contracts; authn and authz are separate; audit is distinct from
business/actual events):

    environment / config        -> explicit identity, validated config, safe failure
    ids / clock                 -> stable identifiers, controlled UTC time
    errors                      -> typed error foundation
    logging_                    -> structured technical logs (NOT audit)
    db / migrations             -> connection + tracked schema migrations
    repositories                -> contracts + SQLite implementations
    auth                        -> authentication (identity proof only)
    authz                       -> authorization (Principal/Capability/Authority/Scope)
    audit                       -> append-only Audit Events
    governance                  -> governed action: business write + audit, atomically
    fixtures                    -> deterministic fixture loading
"""

__all__ = ["REVISION"]

# Best-effort revision stamp for logs/audit (not a business fact).
def _revision() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=__path__[0],
            stderr=subprocess.DEVNULL, timeout=5).decode().strip() or "unknown"
    except Exception:
        return "unknown"


REVISION = _revision()
