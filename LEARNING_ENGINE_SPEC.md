# Learning Engine — Step 6 Specification

Status: **Layer 1 (Repository) implemented, validated, pushed.** Layers 2–6 gated.
Scope: JS-only (no Python mirror). Valuation/retirement output must remain byte-identical after Step 6.

This is no longer a Pipeline Manager feature set — it is the foundation of a
**reusable dealership operating platform**. Every decision from here optimizes for
that outcome. The design rules in §0 are permanent and govern the whole project,
not just the Learning Engine.

The Learning Engine is a separate reusable business engine and the intended
**institutional memory** of the dealership. It observes what the other engines
predicted and what management recommended, records what reality did, and produces
*interpretations* of the gap. It never reaches into valuation or retirement logic,
and those engines never reach into it.

Governing rule:

> **Facts are written once and never touched again. Interpretation is layered on
> top and may be rewritten forever — but old interpretations are never destroyed.**

---

## 0. Platform-wide design rules (permanent)

These are not Learning-Engine conventions. They govern every engine, object, and
layer the platform ever grows.

### 0.1 The Repository is the platform contract — never synonymous with a backend
localStorage is *today's adapter*, nothing more. Every engine believes it is
talking to **business records**, never to browser storage. The platform is
expected to run against SQLite, PostgreSQL, SQL Server, cloud APIs, or a dealership
DMS; swapping the backend must change **zero** engine logic. If an engine would
have to change because the storage technology changed, the architecture is wrong.

### 0.2 Engines are runtime-agnostic
No engine may know whether it is running inside Pipeline Manager, inside another
dealership application, inside a background worker, inside an API, or inside an
automated test. **If any engine would need to change because the UI changed, the
architecture is wrong.** Engines depend on repository and data contracts only —
never on the DOM, the renderer, or a host application.

### 0.3 Separation of concerns (four roles, no overlap)
| Role | Responsibility | Must never |
|---|---|---|
| **Repositories** | persist: store / retrieve / append / query | make judgments |
| **Engines** | think: predict, evaluate, interpret, learn | render or persist directly |
| **Renderers** | display | compute business results |
| **Workflow coordinators** | orchestrate the above | embed engine or persistence logic |

A repository must **never** answer "which recommendation is best?", "what should
retire first?", or "which prediction should be trusted?". Those are engine
questions. Repositories answer only store / retrieve / append / query — nothing
more. Keeping judgment out of persistence is what lets the backend move freely.

### 0.4 Immutable objects are accounting entries, not database rows
Every immutable object (Prediction Snapshot, Recommendation Record, Observation,
Learning Signal, Calibration Recommendation, Interpretation) is a **permanent
historical record**: never edited, never overwritten, never deleted. If something
changes later, write a **new** record that references the prior one via a
`supersedes` link. History must read like a ledger — an append-only chain of
entries and corrections — so the Learning Engine can audit years of dealership
history and reconstruct exactly what was known at each point in time.

### 0.5 Permanent object identity, independent of VIN
Every immutable object receives a **globally unique, permanent object ID** that is
independent of the vehicle. A VIN identifies a *vehicle*; a Prediction Snapshot
identifies a *business decision* — different identities. One VIN accumulates many
snapshots, recommendations, observations, and signals over time; each gets its own
immutable `objectId`. Vehicle identity (VIN) is stored as a *relationship on* the
object, never *as* the object's identity.

### 0.6 Provenance completeness (the auditor test)
Every immutable fact must be able to answer: **who** created me, **when**, using
**which engine versions**, **which configuration**, **which business rules**, and
**which source data**. If an auditor cannot reconstruct *why* an object existed
from the object itself, the object model is incomplete and must be extended before
the object is allowed to persist.

### 0.7 Business-object heuristic (ask before creating any new persistent object)
Before introducing a new persistent object, ask: *"Is this a business object, or is
it merely information that belongs on another business object?"* If it has its own
**identity, history, provenance, relationships, and can be referenced independently**,
it deserves to be its own object. Otherwise it stays **embedded**. This is a core
project heuristic — it is how we decide, e.g., that Decision Context will eventually
graduate from embedded data to its own referenced object (§0.9).

### 0.8 AI-legibility (every object is self-describing)
Every immutable object must be understandable by an AI **without engine-specific
knowledge**. From its fields alone it must answer: *What am I? Why do I exist? Who
created me? What facts can never change? What interpretations changed over time?
What other objects am I related to? What business decision was made? What
ultimately happened?* The foundation's `describe()` assembles these answers from
standard fields only — no engine coupling. Design every new object so `describe()`
can answer all eight.

### 0.9 Contexts trend toward first-class objects (design open, don't build yet)
Every business decision occurs inside a business context (Market, Inventory, Demand,
Financial, Customer, Program, Competitive, Vehicle, Recommendation). Contexts are
embedded today, but the model must **not** be designed so every Decision Record
permanently duplicates hundreds of lines of context. Every record therefore carries
a `contextRefs:[]` array so contexts can later become their own immutable records
(a future **Context Engine / Context Registry**) that records merely reference.
Not implemented now — the model is only kept open for it.

### 0.10 Two persistent categories, and only two (Rule 14)
The platform holds exactly two kinds of persistent objects. Categorize by nature,
never by which engine created them.

| Category | Nature | Examples |
|---|---|---|
| **Business Fact** | immutable · historical · auditable · never rewritten/recalculated · never becomes smarter | Prediction Snapshot, Decision Record, Observation, future Context / Approval / Business-Event |
| **Knowledge** | interpretation derived from facts · recomputable · versioned forever · always replaceable | Error, Attribution, Learning Signal, Calibration, Forecast, Confidence, Risk |

Before creating any new persistent object: *"Is this a business fact?"* → Fact
family. Else *"Is this knowledge derived from facts?"* → Knowledge family. If
neither, it probably should not exist. Facts record **reality**; Knowledge records
**understanding**. This boundary outranks every engine boundary. `PMRecords`
currently mints the Business-Fact family (`category:"business-fact"`); Knowledge is
a separate, recomputable family introduced in the Error/Signal layers.

### 0.11 Every fact points at canonical Entities (not a VIN abstraction)
A fact's `subject` is a list of **entity references** `[{type,id}]`, not a vehicle
field. Today the entity is usually a vehicle; tomorrow it may be a customer,
salesperson, technician, repair order, purchase order, factory allocation, vendor,
store, region, or campaign. One fact may point at several. This removes future
coupling and lets the Timeline expand beyond a single VIN with no redesign.

### 0.12 Evidence, not links (`about → evidence`)
Every fact carries `evidence:[factId,…]` — *"I exist because of these other
facts."* This is deliberately framed as **evidence**, not generic relationships,
because Knowledge (Learning) consumes evidence. It is one of the most important
fields in the platform.

### 0.13 Observations record truths, not events
An Observation answers *"What became true?"* — not *"What happened?"*. Truths remain
(vehicle sold, write-down completed, mileage recorded); events happen. Lifecycle
**events** (on Decision Records) answer *"What happened to the recommendation?"*;
they are a separate timeline from Observation **truths**. Keep them permanently
apart so Observation never drifts into being another event log.

### 0.14 The Timeline is a projection, never an object
"Show me every Business Fact involving this entity" is a **query** across the fact
collections (`forEntity`), not a stored object. The Timeline owns nothing and
duplicates nothing. Guard every relationship against making that projection
impossible; if a design would, stop and surface it.

---

## 1. Standard object model (project-wide) — implemented as `PMRecords`

`build/records.js` (`window.PMRecords`) is the **one** executable implementation of
this model. Every persistent business object is minted through it and inherits:
identity, immutable facts, provenance, integrity (`factsHash`/`verify`), supersedes
chains, append-only **interpretations**, append-only **events**, and `describe()`.
`PMRecords` sits below the engines and beside the repository layer; it captures and
never thinks (§0.3). The concrete platform records (Prediction Snapshot, Decision
Record; later Observation, Learning Signal, Calibration) are thin `PMRecords`
compositions — no duplicated machinery.

Every persistent business object in the platform follows the same four-part shape.
This is now the standard, not a Learning-Engine-only convention.

Record shape (Business-Fact family):
```
{ id, objectType, category:"business-fact", createdAt,
  subject:[{type,id},…],   // canonical entity references (§0.11)
  evidence:[factId,…],     // facts this fact exists because of (§0.12)
  supersedes:null,         // correction chain (§0.4)
  facts:{…},               // the frozen fact block — structurally isolated
  interpretations:[],      // append-only Knowledge (§0.10)
  events:[],               // append-only recommendation lifecycle
  provenance:{…, factsHash} }
```

| Part | Mutability | Purpose |
|---|---|---|
| **Identity** | immutable | permanent `objectId` (independent of entity), object type, created-at (§0.5) |
| **Subject** | immutable | canonical entity references `[{type,id}]` — the Timeline join keys (§0.11) |
| **Evidence** | immutable | facts this fact exists because of (§0.12) |
| **Immutable Facts** | frozen, isolated under `facts` | what was true/decided; never edited (§0.4). Nested so the fact namespace can never collide with system fields and `appendVersion` can never touch it — immutability is **structural**, not conventional |
| **Mutable Interpretation** | append-only versions | Knowledge drawn later; evolves; never overwritten |
| **Event history** | append-only | recommendation lifecycle; grows around facts, never edits them |
| **Metadata / Provenance** | provenance | who/when/versions/config/rules/source data + `factsHash` over the whole immutable core — the auditor test (§0.6) |

`describe()` answers business questions (§0.8, Rule 12) via each type's
**descriptor**; the foundation reads no type-specific field itself, so every fact
is self-describing for AI and executives alike (Rule 13).

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

### LAYER 1b — Decision Record (PLATFORM object, not a Learning-Engine object)
Recommendation Records were **promoted to platform-wide Decision Records**. A
Decision Record is emitted by *any* engine (Demand, Supply, Valuation, Service
Loaner, …) with the **same immutable structure**; the Learning Engine, Reporting
Engine, and future AI consume them. Nothing owns them but the platform.

Prediction = "what did the engines predict?"; Decision = "what did an engine
recommend, and what did management do?". The recommendation never changes; history
(events, interpretations) grows around it.

**Typed envelope (the permanent platform contract):** `recommendation:{ kind,
summary, payload }`, where `kind` is a registry (e.g. `loaner-retirement`,
`ctp-adjustment`, `acquisition`, `trade`, `pricing`, `write-down`, `factory-order`,
`demand`, `inventory`). Reporting/Learning/AI read `kind`+`summary` generically and
only interpret `payload` for kinds they understand — one model, engine-specific
detail, still analyzable.

**Lifecycle as append-only events (historical events, not mutable state):**
`Generated · Presented · Viewed · Accepted · Modified · Rejected · Executed ·
Cancelled · Expired · Superseded` — a canonical registry; unknown types are
rejected so the vocabulary never drifts. Every event carries `actor`+`at`, so
approval history, multi-user approvals, and confidence changes are all just events.
Enables acceptance rate, most-overridden recommendations, managers who outperform
the engine — for free.

**Relationships & references (model open, unused in Step 6):** `supersedes`
(corrections), `relationships:{parentId, dependsOn, alternativesTo, bundleId}`,
`basedOn:[snapshotId,…]` (links to the Prediction Snapshots a decision rests on),
and `contextRefs:[]` (§0.9). Parent/child, dependencies, alternatives, bundles,
expiration, and versioning are all expressible via references + events — no future
redesign, no behavior built now.

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

1. **Repository abstraction** (interfaces + localStorage adapter + JSON export/import) — ✅ DONE (`build/repository.js`, commit `4b257cf`)
2. **Immutable Prediction Snapshot** — ✅ DONE, then refactored onto the shared `PMRecords` foundation (`build/records.js`)
3. **`PMRecords` foundation + platform Decision Record** (typed envelope, lifecycle events, `describe()`) — ✅ DONE (`build/records.js`)
3b. **Foundation refactor** — Business-Fact family (Rule 14), `facts:{}` isolation + structural immutability, canonical entity `subject`, `evidence`, business-question descriptors, unified `forEntity` — ✅ DONE (`build/records.js`, `build/repository.js`)
4. **Observation Store** ("What became true?", append-only truths, typed-kind registry, entity subject, evidence) — ◀ next; a `PMRecords` composition on `repositories.observations`
5. **Error Engine** (typed registry + immature classifier) — Learning Engine *thinking* (reintroduces `learning_engine.js`)
6. **Learning Signal Engine** (confidence + provenance, non-destructive versions)
7. **Calibration Recommendation surface** (recommendation-only, approval-gated)

> Note: `build/learning_engine.js` (from the Layer 2 commit) was removed in the
> refactor — there is no Learning *thinking* code yet. The Learning Engine returns
> in step 5 (Error Engine) as a consumer of platform records, cleanly separated
> from the platform record foundation.

Guarantee: valuation and retirement output remain byte-identical throughout Step 6.
The Learning Engine only observes; it changes no prediction until an approved
calibration exists, which is out of scope for this step.

## 7. Out of scope for Step 6 (design-ready, not built)
Automatic calibration application; weighting/decay math (weights fixed at 1.0);
Bayesian updates; rolling accuracy windows; dealer/regional adjustments; technician
quality; auction performance; wholesale-vs-retail split; recommendation-adoption
scoring; confidence decay; event bus. Data structures must not preclude any of these.

---

## 8. Layer 2 — Prediction Snapshot (concrete design)

A Prediction Snapshot is a permanent accounting entry (§0.4) recording, verbatim,
what the engines predicted at the moment a management decision was committed (Q1).
It is written once through `repositories.predictionSnapshots` and never edited,
overwritten, or deleted.

### 8.1 Record shape (standard object model, §1)
```
{
  // ── Identity (§0.5) ─────────────────────────────────────────────
  id:        "psnap-<ULID>",     // permanent objectId, independent of VIN
  objectType:"PredictionSnapshot",
  createdAt: "2026-07-29T…Z",    // wall-clock capture time
  supersedes:null,               // objectId of a prior snapshot this corrects (ledger chain, §0.4)

  // ── Immutable Facts ─────────────────────────────────────────────
  subject: { vin:"…", model:"QX60", modelYear:2026, trim:"…" },   // VIN is a relationship, not identity
  decisionContext: { ageMonths, mileage, position:"on-lot|pipeline",
                     baseRetailMedian, compN, dtsMedian,
                     programContext, ctpState, acquisitionPath,
                     demandWindow:{…} },                           // Layer 0 photograph
  prediction: {
    projectedResale, breakdown:[ {name, premium, n, confidence}, … ],  // base + each attribute premium
    recommendedRetirementMonth, scenarioTable:[…],                     // from _retireTiming
    projectedWriteDown, projectedTotalContribution,
    overallConfidence
  },

  // ── Mutable Interpretation (added later, never at creation) ──────
  interpretations: [],           // Errors/Attribution attach here in Layers 5–6, non-destructively

  // ── Metadata / Provenance (§0.6 — the auditor test) ─────────────
  provenance: {
    createdBy:      "PredictionSnapshotService",
    createdAt:      "2026-07-29T…Z",
    buildId:        "…",         // correlates to a release
    valuationEngineVersion:  "…",
    retirementEngineVersion: "…",
    learningEngineVersion:   "…",
    configurationVersion:    "…",
    businessRulesVersion:    "…", // NEW — the rule set in force (see recommendation R2)
    sourceData: { inventoryDigest:"…", historyDigest:"…" }  // NEW — what data produced it (R3)
  }
}
```

### 8.2 Ledger semantics
- `save()` on the immutable `predictionSnapshots` repo already rejects re-writing an
  existing `id` (Layer 1). A "change" is a **new** snapshot whose `supersedes` points
  at the prior objectId — never an edit. Reading the chain reconstructs history.
- Nothing deletes. Export/import (Layer 1) carries the full ledger.

### 8.3 What Layer 2 builds
A thin `PredictionSnapshotService` (engine-side, storage-agnostic) that:
1. accepts a committed decision + the already-computed prediction/context (it does
   **not** recompute — it captures what the engines produced);
2. mints a permanent `objectId`, stamps provenance/versions, freezes facts;
3. calls `repositories.predictionSnapshots.save(record)`.

The service is a **capture**, not a calculation — it introduces no valuation or
retirement logic (§0.3), so New Retail and valuation output stay byte-identical.
Wiring a "Commit Decision" UI trigger is a later, separate concern; Layer 2 delivers
the service + record contract and is validated headlessly.

### 8.4 Recommendations (surfaced pre-code, per standing policy)

- **R1 — Object IDs use ULID-style sortable identifiers, not random UUIDs.**
  Rationale: a snapshot ledger is time-ordered; a lexicographically-sortable,
  timestamp-prefixed id keeps the ledger naturally ordered without a separate sort
  key and eases future DB indexing. A tiny self-contained generator (no dependency)
  gives k-sortable ids offline. *Recommend adopt.*

- **R2 — Add `businessRulesVersion` to provenance** (beyond the spec's engine/config
  versions). Rationale: your §0.6 auditor test explicitly asks "using which business
  rules?" — engine version answers *how the code computed*, but suppression/demote/
  override/eligibility rules can change independently of engine code. Without this,
  two identical-engine snapshots could be irreproducible. *Recommend adopt.*

- **R3 — Add a `sourceData` digest** (hash/fingerprint of the inventory + history
  feeds that fed the prediction). Rationale: the auditor test asks "using which
  source data?"; a digest lets the Learning Engine detect when a later re-derivation
  used different inputs, without storing the whole feed. *Recommend adopt.*

- **R4 — Freeze facts with a deep-frozen capture + a `factsHash`.** Rationale:
  belt-and-suspenders immutability — a stored `factsHash` lets any later reader
  *prove* a fact block was not tampered with out-of-band (e.g. a hand-edited
  localStorage blob). Cheap, and it makes "facts never change" verifiable, not just
  asserted. *Recommend adopt (small).* 

- **R5 — Keep the snapshot's `prediction` a pure copy of engine output; never let
  the service reshape or re-derive it.** Rationale: enforces §0.3 (capture, not
  compute) and guarantees byte-identical valuation. *Recommend adopt (invariant).*

These recommendations extend provenance/identity only; none add business logic to
the repository or change any engine's computation.
