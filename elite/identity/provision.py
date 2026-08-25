"""Capability provisioning for the identity-governance surface.

`identity.govern` was introduced after the pilot database was provisioned, so principals granted their capability
bundle earlier (e.g. Kyle's live GSM/admin principal) never received it — the governed Translation bootstrap then
fails closed with "Not permitted". This backfills the grant through the NORMAL grant mechanism, idempotently, and
without weakening the wall: only principals who ALREADY hold governance authority (the `authority.grant`
capability — the manager/admin designation) receive `identity.govern`; ordinary view-only users never do.
Safe to run on every startup (a no-op once granted).
"""
from __future__ import annotations

ANCHOR = "authority.grant"      # the capability that designates a governance-authorized manager/admin
CAPABILITY = "identity.govern"

# In a single-operator pilot the sole operator IS the store's authority (they already self-approve governed
# Decisions in this store under the explicit pilot exception, holding decision.approve). Any ONE of these
# store-operating-authority capabilities designates that operator — a pure view-only user (workspace.view only)
# holds none of them, so this stays least-privilege and never turns a viewer into an admin.
PILOT_OPERATOR_ANCHORS = ("authority.grant", "decision.approve", "execution.authorize")


def ensure_identity_governance_grants(stack, *, anchor=ANCHOR, capability=CAPABILITY):
    """Grant `capability` at each scope where a principal already holds `anchor` but lacks `capability`.
    Returns the list of (principal_id, scope) newly granted. Uses stack.grant (the same governed path as every
    other grant); never revokes or widens an existing grant."""
    conn = stack.db.conn
    try:
        rows = conn.execute(
            "SELECT DISTINCT principal_id, scope FROM capability_grant WHERE capability=? AND active=1",
            (anchor,)).fetchall()
    except Exception:   # noqa: BLE001 — a missing/older schema must never block startup
        return []
    granted = []
    for r in rows:
        pid, scope = r["principal_id"], r["scope"]
        try:
            if stack.authz.decide(pid, capability, scope).allowed:
                continue
            stack.grant(pid, capability, scope, authority="system:identity-provision")
            granted.append((pid, scope))
        except Exception:   # noqa: BLE001 — one principal's provisioning failure must not abort the rest
            continue
    return granted


def ensure_single_operator_identity_govern(stack, *, scope, capability=CAPABILITY, anchors=PILOT_OPERATOR_ANCHORS):
    """Single-operator-pilot least-privilege backfill: grant `capability` AT THE PILOT STORE SCOPE to each
    principal who already holds a store-operating-authority capability (see PILOT_OPERATOR_ANCHORS) at that
    scope (or at `*`). This lets the sole operator initialize/reconcile their OWN store's reviewed-chart
    dictionary without any wildcard/global admin authority: the grant is scoped to exactly this store and to
    exactly the `identity.govern` capability. Idempotent (skips principals already allowed); never revokes or
    widens an existing grant. Returns the list of (principal_id, scope) newly granted.

    Only call this when ELITE_SINGLE_OPERATOR_PILOT is enabled — it encodes the pilot's authority model
    (one operator is the store's authority), and must not run for multi-user stores."""
    conn = stack.db.conn
    placeholders = ",".join("?" * len(anchors))
    try:
        rows = conn.execute(
            f"SELECT DISTINCT principal_id FROM capability_grant "
            f"WHERE capability IN ({placeholders}) AND active=1 AND (scope=? OR scope='*')",
            (*anchors, scope)).fetchall()
    except Exception:   # noqa: BLE001 — a missing/older schema must never block startup
        return []
    granted = []
    for r in rows:
        pid = r["principal_id"]
        try:
            if stack.authz.decide(pid, capability, scope).allowed:
                continue                                     # already governs this store — nothing to do
            stack.grant(pid, capability, scope, authority="system:single-operator-pilot")
            granted.append((pid, scope))
        except Exception:   # noqa: BLE001 — one principal's provisioning failure must not abort the rest
            continue
    return granted


def bootstrap_reviewed_translation(prefs, scope, *, actor="system:translation-bootstrap"):
    """Automatic store initialization of the repo-governed reviewed-chart dictionary (item 2B): a normal
    deployed store must NOT silently start with the reviewed INFINITI colour/model-line codes unresolved while
    the rest of the app expects the governed dictionary to exist. Idempotent, provenance-preserving, and safe:

      * seeds the reviewed QX60/QX65/QX80 raw observations + the reviewed colour/model-line SAME_AS mappings
        (approved) + the deterministic family/variant IDENTITY of an exact order code (auto-resolved, audited);
      * surfaces the review-gated demand-SHARING relationships (cross-generation SAME FAMILY, package sharing)
        as governed proposals — never auto-approved;
      * insert-if-absent everywhere — a re-run adds no duplicates and never reverts an operator's
        approve/edit/retire, a rejection, or a more-specific operator mapping;
      * writes governed JSON prefs only — no schema change (stays v12), no touch to the permanent inventory DB.

    This activates the human COLOUR/model-line/identity dictionary out-of-the-box; unknown/unreviewed codes stay
    honestly unresolved and are never auto-approved. Returns the seed counts, or {} on any failure (bootstrap
    must never block startup)."""
    try:
        from .translation import TranslationStore
        from . import seed_infiniti as SEED
        from .lineage import LineageStore, ensure_lineage_proposals
        store = TranslationStore(prefs, scope)
        counts = SEED.seed(store, actor=actor)
        # Surface the review-gated demand-sharing relationships implied by the auto-resolved identity as governed
        # PROPOSALS (never auto-approved; insert-if-absent so a rejected relationship is not re-prompted).
        counts["lineage_proposed"] = ensure_lineage_proposals(store, LineageStore(prefs, scope), actor=actor)
        return counts
    except Exception:   # noqa: BLE001
        return {}
