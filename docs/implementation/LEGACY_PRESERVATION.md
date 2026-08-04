# LEGACY PRESERVATION PACKAGE — Product A (Inventory Tool)

Durable preservation of the last stable operational Inventory Tool, so it can be
launched, inspected, and rolled back to at any time during Elite Pipeline work.

## Preserved reference (integrity)
- **Immutable tag:** `legacy-inventory-tool-1.0` → commit `3bf9162`
- **Protected branch (frozen):** `legacy/inventory-tool`
- **Commit SHA-1:** `3bf9162fb488518a4655ea768ae5ccd67362c88a`
- **Artifact:** `Pipeline-Manager.html` · **SHA-256** `bc8972b4187a6178a50fb778ea79e8c3c291faf11c3975f74713ed7abfc81de3`
- Build is reproducible: `python3 build/gen_pipeline_html.py` regenerates the same artifact bytes.

## Latest working artifact & source
- Artifact: `Pipeline-Manager.html` (single-file offline app, ~2.05 MB).
- Source revision: `3bf9162` (this repository); build sources under `build/`.

## Launch instructions
1. `python3 build/gen_pipeline_html.py` → writes `Pipeline-Manager.html`.
2. Open `Pipeline-Manager.html` in any modern browser (fully offline).
3. Paste the inventory export and the speed-to-sell (sales) export; optionally the
   preowned, incentives, fleet (DMS vehicles), and used-sold exports.
4. Results recompute live; working state persists in browser `localStorage`.

## Data location & backup
- Runtime data is browser-local (`localStorage`, 19 `pm_*` keys; see REPOSITORY_AUDIT).
- Backup method: browser export/copy of `localStorage`, or re-paste of the source
  CSVs. Canonical sample fixtures live at `pipeline_manager/sample_data/`.

## Known-correct outputs (launch/validation evidence, Phase 0 run)
- Build: `wrote Pipeline-Manager.html (2046 KB)`.
- Tests: `29/29 passed` (engine) + `10/10 passed` (loaner intel) = **39/39**.
- Headless render on sample data: `✓ recomputed — 116 inventory, 388 sales rows`, no page errors.

## Spec-designated known-correct behaviors / confirmed fixes (preserve)
| Behavior (spec kickoff §7) | Legacy status in Phase 0 |
|---|---|
| CPO moving-goalposts correction | **CONFIRMED FIXED** at `3bf9162` (`computeArrivalWindows` measures arrived units only). |
| Need monotonicity (added qualifying Supply cannot raise Need under unchanged inputs) | **CONFIRMED** for the fixed window path; demonstrated `+0/+4/+8/+16 → 12/9/9/9` (never rises). |
| C1 unit-pairing rule (prevent class-level overmatching) | **PARTIAL / UNVERIFIED** — related caps exist (`demo_vins_per_combo`, one-per-config caps, `loanerMatchUnit`); exact C1 rule per Segment 08 not located by name. Flag for Phase 1. |
| Service Loaner Last Checkout Mileage semantics | **PARTIAL** — loaner mileage via odometer / `mile_cap` / `loaner_miles` present; exact "Last Checkout Mileage" semantic per Segment 08 unverified. Flag for Phase 1. |
| Snapshot absence must not invent final retirement facts | **NOT PRESENT (honest absence)** — legacy has no retirement-fact synthesis, so it does not fabricate; to be implemented explicitly per spec in Phase 1. |

## Sample imports / test data
- `pipeline_manager/sample_data/inventory.csv`, `sales.csv`, `loaner_history.csv`.
- Representative real-format fixtures used during this session are documented in
  ARCHITECTURE.md / AUDIT.md.

## Rollback instructions
```
# Return the working tree to the preserved legacy app, without losing Elite work:
git checkout legacy/inventory-tool          # or: git checkout legacy-inventory-tool-1.0
python3 build/gen_pipeline_html.py          # rebuild the exact legacy artifact
# Verify integrity:
sha256sum Pipeline-Manager.html             # expect bc8972b4187a6178a50fb778ea79e8c3c291faf11c3975f74713ed7abfc81de3
```

## Screenshots / workflow evidence
- Not captured as image files in Phase 0 (headless render evidence recorded above).
  Visual capture can be added in a later phase if required for review.

## Secrets
- None embedded. Environment config is `config.json` (git-ignored); values are not preserved here.
