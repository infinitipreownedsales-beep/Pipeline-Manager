# Learning Engine — Step 6 Specification (FINAL, pre-implementation)

Status: **Approved in principle.** Implementation gated on final go-ahead.
Scope: JS-only (no Python mirror). Valuation/retirement output must remain byte-identical after Step 6.

The Learning Engine is a separate reusable business engine and the intended
**institutional memory** of the dealership. It observes what the other engines
predicted and what management recommended, records what reality did, and produces
*interpretations* of the gap. It never reaches into valuation or retirement logic,
and those engines never reach into it.

Governing rule:

> **Facts are written once and never touched again. Interpretation is layered on
> top and may be rewritten forever — but old interpretations are never destroyed.**

---

## 1. Standard object model (project-wide)

Every persistent business object in the platform follows the same four-part shape.
This is now the standard, not a Learning-Engine-only convention.

| Part | Mutability | Purpose |
|---|---|---|
| **Identity** | immutable | stable key (id, VIN, object type, created-at) |
| **Immutable Facts** | frozen at creation | what was true/decided at the moment; never edited |
| **Mutable Interpretation** | append-only versions | conclusions drawn later; evolves; never overwritten |
| **Metadata** | provenance | build/engine/config versions, generated-by, generated-on |

"Append-only versions" means a changed interpretation is written as a *new*
interpretation record referencing the prior one — the old one survives.

---

## 2. Layer stack

```
  LAYER 0  DECISION CONTEXT   (FACT — frozen)
  LAYER 1  PREDICTION         (FACT — immutable snapshot)
  LAYER 1b RECOMMENDATION     (FACT identity + lifecycle state history)
  LAYER 2  OBSERVATION        (FACT — append-only)
  ─────────── hard boundary: facts above, interpretation below ───────────
  LAYER 3  ERROR              (INTERPRETATION — typed, recomputable)
  LAYER 4  ATTRIBUTION        (INTERPRETATION — recomputable)
  LAYER 5  LEARNING SIGNAL    (INTERPRETATION — confidence + provenance)
  LAYER 6  CALIBRATION        (INTERPRETATION — recommendation only, approval-gated)
```

Nothing below the boundary may write anything above it. A learning re-run years
later, with a smarter model, must reproduce Layers 0–2 identically and only add
new interpretation records in Layers 3–6.

### LAYER 0 — Decision Context (FACT, frozen)
Photograph of the decision environment at commit time. No new business logic — a
read-only capture of state the other engines already computed:
vehicle identity/state (age, mileage, on-lot vs pipeline), market conditions
(base median, comp `n`, days-to-sell), attribute premiums applied (each with
premium, sample count, confidence), overall confidence, program/CTP/acquisition
context, historical demand metrics.

### LAYER 1 — Prediction Snapshot (FACT, immutable)
Verbatim record of what the engines predicted at commit time: projected resale
(base + each attribute premium breakdown), recommended retirement month and the
full scenario table, projected write-down / total contribution.
**Never regenerated or recomputed.** Analysis reads the stored snapshot; it never
re-runs the prediction.

Version stamps on every snapshot (Metadata):
- **Build ID** (correlates back to a specific release)
- Valuation Engine Version
- Retirement Engine Version
- Learning Engine Version
- Configuration Version

### LAYER 1b — Recommendation Record (FACT identity + lifecycle)
Distinct from the prediction. Prediction = "what did the engines predict?";
Recommendation = "what did the system recommend, and what did management do?".

Recommended vs Actual across: retirement month, write-down, acquisition path
(CPO/PPO/CTP/Dealer-Trade), CTP change.

**Lifecycle states (historical state, not workflow logic):**
`Generated → Presented → Accepted → Modified → Rejected → Executed → Cancelled`
State transitions are appended as history (each with timestamp + provenance), never
overwritten. This makes future analytics almost free: acceptance rate, most-
overridden recommendations, managers who consistently outperform the engine.

### LAYER 2 — Observation (FACT, append-only)
What actually happened: actual sale price, actual retirement month, actual
days-to-sell, actual acquisition path, actual CTP outcome. Only ever appended;
a late observation adds a record, it never rewrites Layers 0–1b.

---

### ▲ hard boundary ▲ — everything below is recomputable and versioned ▼

### LAYER 3 — Error (INTERPRETATION, typed)
Error = Observation − Prediction, classified by an **expandable Error Type
registry** (the single extension point, mirroring `_ATTR_PREMIUMS`):
`Market Shift · Execution Error · Unexpected Vehicle Condition · Pricing Decision ·
Retail Strategy · Data Quality · Timing Difference · Valuation Error · Unknown`.
Step 6 classifier is intentionally immature: `Unknown` + 1–2 trivial rules
(e.g. month-only difference ⇒ Timing Difference). The registry is the architecture;
the classifier evolves later.

### LAYER 4 — Attribution (INTERPRETATION)
Assigns each classified error to the responsible signal (AWD premium, seasonality,
base median, reconditioning estimate, …). Bridges a single vehicle's miss to a
cross-vehicle pattern. Fully recomputable.

### LAYER 5 — Learning Signal (INTERPRETATION, confidence + provenance)
A statistical statement with a trust level, never an instruction:
> "94% confident the AWD premium is overstated by ~$650 (n=31)"

Every signal carries provenance (auditable conclusion):
- Generated By (engine + version)
- Generated On (timestamp)
- Engine Version
- Inputs Used
- Confidence

**Signals never disappear.** If a later recalculation disagrees, a *new* signal is
created referencing the prior one; the previous signal is preserved so history shows
how understanding evolved.

**Time-awareness (design-only):** the model carries observation timestamps and a
`weight` field so future weighted/decayed learning is possible. Weighting is NOT
implemented now — every weight = 1.0 this phase. We only guarantee we haven't
precluded it.

### LAYER 6 — Calibration (INTERPRETATION, recommendation-only)
Turns high-confidence signals into *proposed* adjustments to the attribute-premium
registry. The Learning Engine produces a recommendation; it never applies it. The
Valuation Engine consumes only an *approved* calibration. Approval is a separate
event with a human in the loop. Two engines communicating through an approval gate,
never a direct write.

---

## 3. Architectural boundaries

### Repository Layer (new boundary)
Business engines never know where persistence lives. Every engine talks to a
**repository interface**, not to storage technology.

```
Business Engine  ──►  Repository Interface  ──►  Storage Adapter
                        (contract)                (localStorage today;
                                                   SQLite/Postgres/Cloud later)
```

The Learning Engine communicates with repositories (`PredictionSnapshotRepository`,
`RecommendationRepository`, `ObservationRepository`, `InterpretationRepository`),
each exposing a technology-neutral contract (e.g. `save`, `getById`, `list`,
`appendVersion`). The first adapter writes to localStorage. Moving to a database
later must not change any engine — only the adapter behind the interface.

Storage keys for the localStorage adapter (business records, not cache):
`pm_prediction_snapshots`, `pm_recommendation_records`, `pm_observations`,
`pm_interpretations`. A JSON export/import path preserves records across a browser
wipe (immutable history a cache-clear can destroy is not immutable history).

### Engine independence
- Learning Engine never knows how valuation works — it reads stored snapshots and
  observations; it never calls `_retailAt` / `_retireTiming`.
- Valuation Engine never knows how learning works — it reads an approved calibration
  *table* (data), not learning code.
- Contract between them is two data structures (snapshot in, approved calibration
  out), never a function call. Both independently testable with fixtures.

### Event-readiness (design-only, not implemented)
The Learning Engine is designed to become event-driven without rework. Future
events (not built now): `PredictionCommitted`, `RecommendationAccepted`,
`RecommendationRejected`, `VehicleRetired`, `VehicleSold`, `ObservationImported`,
`CalibrationApproved`. Nothing in Step 6 may preclude future subscribers.

---

## 4. Historical vs Hindcast (confidence classes)

Two confidence classes must never be mixed in reporting:
- **Historical Prediction** — a true immutable snapshot captured at commit time.
- **Hindcast Estimate** — a recomputation for records that predate the snapshot
  store (legacy `loanerOutcomes` path), explicitly labeled as a compatibility path.

Every report labels each figure with its class. Hindcast is a lower confidence class
and is never presented as historical fact.

---

## 5. Decisions (locked)

| # | Decision |
|---|---|
| Q1 | Snapshot created only when a management decision is **committed**. Exploration predictions are temporary. |
| Q2 | localStorage today, behind a Repository interface designed for later DB migration. Engines talk to repositories, not storage. |
| Q3 | Hindcast kept only as an explicitly labeled compatibility path; never mixed with historical snapshots in reporting. |
| Q4 | Explicit version constants + **Build ID** on every snapshot (Build ID, Valuation/Retirement/Learning Engine Versions, Configuration Version). |
| Q5 | JS-only. No Python mirror. |
| Q6 | Error Type registry + `Unknown` + 1–2 trivial rules. Classifier intentionally immature. |

---

## 6. Implementation order (gated — validate after each layer)

Do not move to the next layer until the previous passes architecture verification.

1. **Repository abstraction** (interfaces + localStorage adapter + JSON export/import)
2. **Immutable Prediction Snapshot** (Layer 0 context + Layer 1 snapshot, version-stamped)
3. **Recommendation Record** (Layer 1b, with lifecycle state history)
4. **Observation Store** (Layer 2, append-only)
5. **Error Engine** (Layer 3, typed registry + immature classifier)
6. **Learning Signal Engine** (Layer 5, confidence + provenance, non-destructive versions)
7. **Calibration Recommendation surface** (Layer 6, recommendation-only, approval-gated)

Guarantee: valuation and retirement output remain byte-identical throughout Step 6.
The Learning Engine only observes; it changes no prediction until an approved
calibration exists, which is out of scope for this step.

## 7. Out of scope for Step 6 (design-ready, not built)
Automatic calibration application; weighting/decay math (weights fixed at 1.0);
Bayesian updates; rolling accuracy windows; dealer/regional adjustments; technician
quality; auction performance; wholesale-vs-retail split; recommendation-adoption
scoring; confidence decay; event bus. Data structures must not preclude any of these.
