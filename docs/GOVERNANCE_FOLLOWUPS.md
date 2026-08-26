# Governance follow-ups (required)

## GD-1 — Silent global drivetrain-crossing normalization `QX60 8461 → 8481`

**Status:** open — required follow-on. **Do not fold into a CTP acceptance block.**

**Defect.** `elite/newinv/dms_identity.py::normalize_code` contains a hardcoded legacy rule:

```python
if model == "QX60" and d[:4] == "8461":
    return "8481"
```

ported "verbatim in meaning" from the legacy Speed-to-Sell engine and described as
*"QX60 8461 (Autograph FWD, discontinued) folds into 8481."* Because the planning demand cohort
key is `(model, code4, ext, int)` via `normalize_code` (`demand_bridge.py`), this **merges raw
codes across drivetrain at the cohort-key level, before any governance runs** — a discontinued
Autograph **FWD** (`8461x`) collapses into the Autograph **AWD** cohort (`8481`) and its demand is
counted as **exact** AWD demand.

**Why it is a governance violation.** Elite's own contract forbids exactly this:

- `identity/lineage.py`: `SUCCESSOR` — *"(QX60 AUTOGRAPH FWD → AWD). Histories stay SEPARATE; the
  predecessor may support the successor ONLY after approval; it is never encoded as FWD == AWD."*
- `identity/translation.py::check_same_family_drivetrain`: *"SAME FAMILY AS cannot cross
  drivetrain … never a silent family merge."*
- `identity/translation.py::demand_evidence_tier`: borrowed history is at most `lineage`, *"never
  automatically exact."*

`normalize_code` bypasses all of it: no review, no separate histories, no `lineage` downgrade.

**Scope note / why not fixed opportunistically.** `code4(84617) == 8461`, so the *current* 2027
Autograph **AWD** shares the `8461` prefix. A naive deletion of the rule would re-key the current
AWD to `8461`, colliding it with any historical FWD `8461x` under a different label — the merge
persists. The correct fix keeps raw histories distinct and routes any predecessor→successor
support through the reviewed `SUCCESSOR` lineage (same-drivetrain cross-gen via
`SAME_FAMILY_CROSS_GEN`); it needs the real raw codes and a governance decision, not a one-line
edit.

**Required correction.**
1. Remove the silent drivetrain-crossing normalization from the certified planning demand path;
   preserve each raw code's history distinctly.
2. Route predecessor/successor (and cross-generation) demand sharing through the reviewed lineage
   layer only, at `lineage` evidence tier — never a silent cohort-key merge, never `exact`.
3. Add a regression asserting no drivetrain-crossing raw codes share a planning cohort without an
   approved lineage relationship.

**Live note (2026-08-26).** For the specific CTP cohort under acceptance, the dealership audit found
`QX60|8461|XKJ|P = 0` sales and the real `8481|XKJ|P` history is the prior **AWD** `84816`
Autograph cohort (both AWD → same drivetrain). So this defect did **not** inflate that particular
cohort — but it remains a real global defect and must be corrected independently of CTP acceptance.
