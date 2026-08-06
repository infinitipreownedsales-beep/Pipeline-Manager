# ADR-0039 — Accessibility and usability baseline

- **Status:** Accepted (Phase 10)
- **Owning segments:** 10 (User Experience)

## Decision
The application meets a baseline accessibility bar: semantic landmarks (`banner`/`navigation`/`main`) and
headings; a `<label>` for every form control; primary actions as real keyboard-focusable `<button>`
elements with a visible `:focus` outline; status conveyed by a text glyph + label (never color alone);
responsive layouts; clear `role="alert"` validation/permission errors; and usable empty and failure
states with a way back. No single universal red/yellow/green score is used to replace domain truth.

## Why
Dealership operators use this at pace on desktop (primary) and mobile. Status that depends on color
alone, unlabeled forms, or non-focusable actions would exclude users and slow decisions. A text-first,
semantic baseline keeps the tool usable and honest (a colored dot never stands in for the real domain
state).

## Consequences
- Status badges always carry a glyph + label; the inbox/detail assert non-color status (test 97).
- Empty and failure states render usable messages (tests 99, 100); forms carry labels (test 98).
