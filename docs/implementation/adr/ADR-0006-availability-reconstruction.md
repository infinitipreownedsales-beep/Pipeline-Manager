# ADR-0006 — Availability reconstruction

- **Status:** Accepted (Phase 4)
- **Owning segments:** 06 (Demand / availability)

## Decision
Sales and availability are interpreted **together**. Availability is reconstructed into month
buckets that distinguish `available_unsold`, `available_sold`, `unavailable`, `constrained`,
`stockout`, `unknown`, `conflicting`, and `partial` states, each with an exposure measure and a
confidence. Rules:
- "No availability" is not "zero demand" — the Demand rate denominator counts **calendar months
  available**, so unavailable/unknown/partial months are simply absent from the denominator and
  never dilute the rate.
- An available month with no sales (`available_unsold`) is distinct from an unavailable month with
  no sales (`unavailable`).
- A partial snapshot does not assert continuous availability: it yields a `partial` state with a
  recorded unresolved gap and contributes no exposure.
- A stockout is `stockout` with zero recorded retail and reduced (not zero) confidence — it never
  fabricates an exact lost-sales quantity.
- Unresolved gaps reduce confidence rather than fabricate continuity.

## Why
Trustworthy Demand requires honest exposure. Reading absence as zero demand, or inventing
continuity/lost-sales, would corrupt the baseline. Distinct availability states + an exposure
denominator are the smallest correct way to interpret history.

## Consequences
- Availability intervals are stored (`availability_interval`) with source/fact references and
  confidence; Demand reads exposure and gap signals from them.
- Depth informs constraint/stockout classification, not the base-rate denominator (which is
  calendar months available), keeping the rate a per-month sales rate rather than a turn rate.
