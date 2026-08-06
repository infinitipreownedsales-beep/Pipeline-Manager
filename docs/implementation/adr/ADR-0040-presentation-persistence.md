# ADR-0040 — Presentation-state persistence (non-authoritative)

- **Status:** Accepted (Phase 10)
- **Owning segments:** 10 (User Experience)

## Decision
Only presentation state that materially improves operator use is persisted — saved filters, preferred
store view, column visibility, sort preference, dismissed hints, last selected domain — in dedicated
server-side tables (migration v10). These records are explicitly NON-authoritative: they hold no
business state, deleting any of them changes no Decision, approval, execution, policy, identity, supply,
Demand, Need, Economic Call, or governance state, and they carry no immutability triggers (they are
freely deletable, the opposite of every authoritative table). No authoritative state is ever stored in
browser localStorage.

## Why
Operator convenience (remembered filters/sort) is worth persisting, but it must never be able to alter or
be mistaken for authoritative truth. Isolating it in clearly non-authoritative, freely-deletable tables —
and keeping the browser holding nothing but an opaque session token — makes that separation structural.

## Consequences
- Deleting a preference leaves all business records unchanged and the app fully functional (test 92).
- Preferences survive restart (test 108); migration v10 is rerun-safe (test 109).
- Browser localStorage is never authoritative (test 91).
