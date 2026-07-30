/* PMRecords — the platform's immutable Business-Fact foundation.
   (Learning Engine Spec §1 standard object model, made executable.)

   Rule 14 — the platform holds exactly two persistent categories:
     • BUSINESS FACTS  — immutable, historical, auditable; record what is
       permanently true. Prediction Snapshot, Decision Record, Observation,
       and future Context / Approval / Business-Event records.
     • KNOWLEDGE       — interpretation derived from facts; recomputable,
       versioned forever, always replaceable. Error, Attribution, Learning
       Signal, Calibration, Forecast, Confidence, Risk. (Built in later layers.)
   This module is the ONE implementation the Business-Fact family inherits:
     • Identity            permanent, k-sortable objectId, independent of entity
     • Entity subject      one or more canonical entity references (§ subject)
     • Evidence            the facts a fact exists because of (§ about → evidence)
     • Immutable Facts      frozen fact block, structurally isolated under `facts`
     • Provenance          the auditor test — who/when/versions/config/rules/data
     • Integrity           factsHash + verify(): the immutable core is unaltered
     • Supersedes chains    corrections are new facts linked to the prior
     • Interpretations     append-only Knowledge attached to a fact (never edits it)
     • Events              append-only lifecycle of a recommendation (Decisions)
     • describe()          business-question answers for AI / executives / reporting

   It sits BELOW the engines and BESIDE the repository layer. Engines produce and
   read facts through it; it never ranks, chooses, or trusts (§0.3). It depends
   only on the Layer 1 repositories contract, so it is storage- and runtime-
   agnostic (§0.1, §0.2).

   Timeline is NOT an object here (or anywhere): it is a projection — "every
   Business Fact involving this entity" — served by forEntity() across the fact
   collections. It owns nothing and duplicates nothing.

   Exposes window.PMRecords. Inert on load. */
(function () {
  "use strict";

  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }

  /* FNV-1a 32-bit hex — deterministic, dependency-free. */
  function hash(str) {
    var h = 0x811c9dc5; str = String(str == null ? "" : str);
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ("00000000" + h.toString(16)).slice(-8);
  }

  /* ULID-style k-sortable id: time prefix + random suffix; DB-index friendly. */
  var CROCK = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  function ulid(time, rng) {
    time = (time == null ? Date.now() : time);
    var t = "", n = time;
    for (var i = 0; i < 10; i++) { t = CROCK[n % 32] + t; n = Math.floor(n / 32); }
    var r = "", rand = (rng || Math.random);
    for (var j = 0; j < 16; j++) { r += CROCK[Math.floor(rand() * 32)]; }
    return t + r;
  }

  function deepFreeze(o) {
    if (o && typeof o === "object") {
      Object.keys(o).forEach(function (k) { deepFreeze(o[k]); });
      Object.freeze(o);
    }
    return o;
  }

  /* Version stamps travel with the code (Q4, §0.6). Hand-bumped per release. */
  var DEFAULT_VERSIONS = {
    buildId: "pm-2026.07",
    valuationEngineVersion: "1.0.0",
    retirementEngineVersion: "1.0.0",
    learningEngineVersion: "1.0.0",
    configurationVersion: "1.0.0",
    businessRulesVersion: "1.0.0"
  };

  /* Canonical, platform-wide lifecycle events for recommendations (registry).
     Observations are NOT events — they are truths (a separate timeline). */
  var LIFECYCLE_EVENTS = {
    Generated: true, Presented: true, Viewed: true, Accepted: true, Modified: true,
    Rejected: true, Executed: true, Cancelled: true, Expired: true, Superseded: true
  };
  var TERMINAL_EVENTS = { Executed: true, Cancelled: true, Rejected: true, Expired: true, Superseded: true };
  function registerLifecycleEvent(type) { LIFECYCLE_EVENTS[type] = true; }

  /* Decision-kind registry (typed envelope). Extendable so any engine emits
     decisions without a new object type. */
  var DECISION_KINDS = {};
  ["loaner-retirement", "ctp-adjustment", "acquisition", "trade", "pricing",
   "write-down", "factory-order", "demand", "inventory"].forEach(function (k) { DECISION_KINDS[k] = true; });
  function registerDecisionKind(kind) { DECISION_KINDS[kind] = true; }

  /* Observation-kind registry — TRUTHS that became real (§0.13), not events.
     Each names something that is now permanently true of an entity. Extendable. */
  var OBSERVATION_KINDS = {};
  ["retailed", "wholesaled", "retired", "exported", "transferred", "written-off",
   "sent-to-auction", "write-down-completed", "certification-completed",
   "reconditioning-completed", "mileage-recorded", "sale-price-recorded",
   "actual-gross-recorded", "actual-days-to-sale-recorded",
   "actual-retirement-month-recorded", "actual-acquisition-path-recorded"
  ].forEach(function (k) { OBSERVATION_KINDS[k] = true; });
  function registerObservationKind(kind) { OBSERVATION_KINDS[kind] = true; }

  /* Knowledge-kind registry (Rule 14). A kind exists only if it answers a distinct
     business question — the registry keeps Knowledge from becoming a dumping ground.
     Seeded with the understanding kinds the Learning Engine will produce later. */
  var KNOWLEDGE_KINDS = {};
  ["error", "attribution", "learning-signal"].forEach(function (k) { KNOWLEDGE_KINDS[k] = true; });
  function registerKnowledgeKind(kind) { KNOWLEDGE_KINDS[kind] = true; }

  /* Attribution factor-type registry — VOCABULARY only (engines interpret, this
     family never judges). Intentionally small and general; dealer-specific
     intelligence emerges through evidence and Learning Signals, not hardcoded
     categories. `external-factor` is deliberately NOT seeded (future, not required)
     — add it via registerAttributionFactor when a feed provides it. */
  var ATTRIBUTION_FACTORS = {};
  ["configuration", "timing", "pricing", "incentive", "process", "decision", "data-quality"]
    .forEach(function (f) { ATTRIBUTION_FACTORS[f] = true; });
  function registerAttributionFactor(factor) { ATTRIBUTION_FACTORS[factor] = true; }

  var byId = function (a, b) { return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; };

  /* ===================== foundation() =====================
     Composes a repository (persistence) with the standard object model into the
     shared surface every Business Fact inherits. Concrete fact registries call
     this and add only the business verb that mints their fact (capture / record /
     observe) and any fact-specific helpers.

     opts:
       type       business object name (e.g. "Prediction Snapshot")
       idPrefix   objectId prefix (e.g. "psnap")
       category   "business-fact" (default) — Rule 14
       descriptor business-question answerers (purpose/decision/truth/outcome/
                  confidence); describe() stays generic and never reads
                  implementation details itself (Rule 12, 13). */
  function foundation(repositories, collectionKey, opts) {
    opts = opts || {};
    var repo = repositories && repositories[collectionKey];
    if (!repo) throw new Error("PMRecords.foundation: repositories." + collectionKey + " required");
    var type = opts.type || "Record";
    var idPrefix = opts.idPrefix || "rec";
    var category = opts.category || "business-fact";
    var payloadKey = opts.payloadKey || "facts";   // "facts" (fact family) | "finding" (knowledge)
    var descriptor = opts.descriptor || {};
    var versions = opts.versions || DEFAULT_VERSIONS;
    var clock = opts.clock || function () { return new Date(); };
    var rng = opts.rng || Math.random;

    /* Evidence entries are role-typed (§0.12): "I exist because of this record, in
       this capacity." A bare id normalizes to {id, role:null}; nothing is lost. */
    function normalizeEvidence(ev) {
      return (ev || []).map(function (e) {
        if (e != null && typeof e === "object") return { id: e.id, role: ("role" in e ? e.role : null) };
        return { id: e, role: null };
      });
    }

    function digestSources(sources) {
      var d = {};
      if (!sources) return d;
      if (sources.inventory != null) d.inventoryDigest = hash(sources.inventory);
      if (sources.history != null) d.historyDigest = hash(sources.history);
      if (sources.digests) Object.keys(sources.digests).forEach(function (k) { d[k] = sources.digests[k]; });
      return d;
    }

    /* The immutable core is everything that can never change: the entity
       references, the role-typed evidence, the supersedes link, and the payload
       block (named per family via payloadKey). Hashed as one unit, so tampering
       with any of it is detectable. */
    function coreOf(input, supersedes) {
      var core = {
        subject: clone(input.subject) || [],              // canonical entity references
        evidence: normalizeEvidence(input.evidence),      // role-typed {id, role}
        supersedes: supersedes || null                    // correction chain
      };
      core[payloadKey] = clone(input.payload) || {};      // the frozen payload block
      return core;
    }

    function mint(input, meta) {
      meta = meta || {};
      var now = clock();
      var ms = (now && now.getTime) ? now.getTime() : Date.now();
      var iso = (now && now.toISOString) ? now.toISOString() : new Date(ms).toISOString();
      var core = coreOf(input, meta.supersedes);
      var record = {
        // Identity
        id: idPrefix + "-" + ulid(ms, rng),
        objectType: type,
        category: category,                       // Rule 14 family
        createdAt: iso,
        // Immutable core (mirrored at top level for ergonomic reads)
        subject: core.subject,
        evidence: core.evidence,
        supersedes: core.supersedes,
        // Append-only histories (empty at creation)
        interpretations: [],                      // Knowledge attaches here
        events: [],                               // recommendation lifecycle
        // Metadata / provenance (§0.6)
        provenance: {
          createdBy: meta.createdBy || type,
          createdAt: iso,
          buildId: versions.buildId,
          valuationEngineVersion: versions.valuationEngineVersion,
          retirementEngineVersion: versions.retirementEngineVersion,
          learningEngineVersion: versions.learningEngineVersion,
          configurationVersion: versions.configurationVersion,
          businessRulesVersion: versions.businessRulesVersion,
          sourceData: digestSources(meta.sources)
        }
      };
      record[payloadKey] = core[payloadKey];      // frozen payload under its family name
      record.provenance.factsHash = hash(JSON.stringify(core));
      return record;
    }

    function coreFromRecord(rec) {
      var core = { subject: rec.subject, evidence: rec.evidence, supersedes: rec.supersedes };
      core[payloadKey] = rec[payloadKey];
      return core;
    }

    var api = {
      type: type,
      category: category,
      collection: collectionKey,
      versions: versions,

      mint: function (input, meta) { return deepFreeze(mint(input, meta)); },
      create: function (input, meta) { return repo.save(deepFreeze(mint(input, meta))); },

      get: function (id) { return repo.getById(id); },
      list: function (pred) { return repo.list(pred); },
      count: function () { return repo.count(); },

      /* Prove the immutable core was not altered out-of-band. */
      verify: function (rec) {
        if (!rec || !rec.provenance) return false;
        return rec.provenance.factsHash === hash(JSON.stringify(coreFromRecord(rec)));
      },

      /* Timeline projection: every fact in this collection referencing an entity.
         One implementation, any entity type — no per-object VIN lookups. */
      forEntity: function (entityType, entityId) {
        return repo.list(function (r) {
          return (r.subject || []).some(function (e) { return e.type === entityType && e.id === entityId; });
        }).sort(byId);
      },
      forVehicle: function (vin) { return api.forEntity("vehicle", vin); },

      /* Evidence projection (reverse of `evidence`): every record in this
         collection that cites `id` as evidence — "what rests on this record?".
         The second Timeline hop (§0.14): Knowledge derived from a fact. */
      forEvidence: function (id) {
        return repo.list(function (r) {
          return (r.evidence || []).some(function (e) { return e.id === id; });
        }).sort(byId);
      },

      /* Append Knowledge (interpretation) — non-destructive; never edits facts. */
      appendInterpretation: function (id, entry) { return repo.appendVersion(id, entry || {}, "interpretations"); },

      /* Append a recommendation lifecycle event — non-destructive; unknown types
         rejected so the vocabulary never drifts. */
      appendEvent: function (id, event) {
        event = event || {};
        if (!event.type || !LIFECYCLE_EVENTS[event.type])
          throw new Error(type + ".appendEvent: unknown event type '" + event.type + "'");
        if (!event.at) event.at = (clock().toISOString ? clock().toISOString() : new Date().toISOString());
        return repo.appendVersion(id, event, "events");
      },

      /* Follow the supersedes chain oldest→newest. */
      history: function (id) {
        var chain = [], seen = {}, cur = repo.getById(id);
        while (cur && !seen[cur.id]) { chain.unshift(cur); seen[cur.id] = true; cur = cur.supersedes ? repo.getById(cur.supersedes) : null; }
        return chain;
      },

      /* AI-legibility (Rule 13) + explainability (Rule 12): answers are business
         questions, produced by the type's descriptor — describe() itself reads no
         implementation-specific field. */
      describe: function (rec) {
        if (!rec) return null;
        function ask(fn) { try { return fn ? fn(rec) : null; } catch (e) { return null; } }
        return {
          whatAmI: rec.objectType,
          category: rec.category,
          whyDoIExist: ask(descriptor.purpose),
          whoCreatedMe: rec.provenance && rec.provenance.createdBy,
          when: rec.createdAt,
          entities: rec.subject || [],
          evidence: rec.evidence || [],
          immutablePayload: Object.keys(rec[payloadKey] || {}),
          understandingOverTime: (rec.interpretations || []).length,
          businessEvents: (rec.events || []).length,
          supersedes: rec.supersedes || null,
          whatDecisionWasMade: ask(descriptor.decision),
          whatBecameTrue: ask(descriptor.truth),
          whatUltimatelyHappened: ask(descriptor.outcome),
          howTrustworthy: ask(descriptor.confidence)
        };
      },

      _terminalEvent: function (rec) {
        var t = null; (rec.events || []).forEach(function (e) { if (TERMINAL_EVENTS[e.type]) t = e; });
        return t ? { type: t.type, at: t.at, actor: t.actor || null } : null;
      }
    };
    return api;
  }

  function entityRefs(input) {
    if (Array.isArray(input.subject)) return input.subject;
    if (input.vin) return [{ type: "vehicle", id: input.vin }];
    return [];
  }

  /* ============ Prediction Snapshots — "What did we believe would happen?" ====
     A Business Fact captured at decision-commit time. Pure copy of engine output
     (capture, never compute). */
  function PredictionSnapshots(repositories, opts) {
    var base = foundation(repositories, "predictionSnapshots", Object.assign({
      type: "Prediction Snapshot", idPrefix: "psnap",
      descriptor: {
        purpose: function () { return "Records what the engines believed would happen for this vehicle at the moment a decision was committed."; },
        confidence: function (r) { return r.facts.prediction ? r.facts.prediction.overallConfidence : null; }
      }
    }, opts || {}));
    return Object.assign({}, base, {
      capture: function (prediction) {
        if (!prediction || !prediction.prediction)
          throw new Error("PredictionSnapshots.capture: prediction.prediction required");
        var facts = {
          vehicle: prediction.vehicle || {},                                  // descriptive (model/year/trim)
          context: prediction.context || prediction.decisionContext || {},    // decision environment
          contextRefs: prediction.contextRefs || [],                          // future Context records
          prediction: prediction.prediction                                   // engine output, verbatim
        };
        return base.create(
          { subject: entityRefs(prediction), evidence: prediction.evidence || [], payload: facts },
          { createdBy: prediction.committedBy || "Prediction Snapshot", sources: prediction.sources, supersedes: prediction.supersedes });
      }
    });
  }

  /* ============ Decision Records — "What decision did we make?" ===============
     Platform Business Fact any engine emits with one immutable structure. The
     recommendation never changes; lifecycle events and Knowledge grow around it. */
  function DecisionRecords(repositories, opts) {
    var base = foundation(repositories, "decisions", Object.assign({
      type: "Decision Record", idPrefix: "dec",
      descriptor: {
        purpose: function (r) { return r.facts.recommendation ? r.facts.recommendation.summary : null; },
        decision: function (r) { return r.facts.recommendation ? { kind: r.facts.recommendation.kind, summary: r.facts.recommendation.summary } : null; },
        outcome: function (r) { return base._terminalEvent(r); },
        confidence: function (r) { return r.facts.rationale ? r.facts.rationale.confidence : null; }
      }
    }, opts || {}));
    return Object.assign({}, base, {
      record: function (decision) {
        decision = decision || {};
        var rec = decision.recommendation || {};
        if (!rec.kind) throw new Error("DecisionRecords.record: recommendation.kind required");
        if (!DECISION_KINDS[rec.kind]) throw new Error("DecisionRecords.record: unregistered kind '" + rec.kind + "'");
        var facts = {
          origin: decision.origin || {},
          recommendation: { kind: rec.kind, summary: rec.summary || "", payload: rec.payload || {} },
          rationale: decision.rationale || { why: "", assumptions: [], confidence: null },
          context: decision.context || {},
          contextRefs: decision.contextRefs || [],
          relationships: decision.relationships || { parentId: null, dependsOn: [], alternativesTo: [], bundleId: null }
        };
        return base.create(
          { subject: entityRefs(decision), evidence: decision.evidence || decision.basedOn || [], payload: facts },
          { createdBy: decision.committedBy || (facts.origin.engine || "Decision Record"), sources: decision.sources, supersedes: decision.supersedes });
      },
      forEngine: function (engine) {
        return base.list(function (r) { return r.facts.origin && r.facts.origin.engine === engine; }).sort(byId);
      }
    });
  }

  /* ============ Observations — "What became true?" ==========================
     A Business Fact recording a truth that became real for an entity. NOT an
     event, NOT a recommendation, NOT learning (§0.13). Append-only: a late
     observation is a new record; a correction is a superseding observation —
     never an edit and never a lifecycle event. Observations do not pre-link to
     predictions or decisions; Learning correlates them by entity via the Timeline
     projection. Their `evidence` therefore cites source facts only when one truth
     literally rests on another (e.g. gross recorded rests on sale-price recorded),
     not the recommendation they happen to fulfill. */
  function Observations(repositories, opts) {
    var base = foundation(repositories, "observations", Object.assign({
      type: "Observation", idPrefix: "obs",
      descriptor: {
        purpose: function () { return "Records what actually became true for this entity."; },
        truth: function (r) { return r.facts.observation ? { kind: r.facts.observation.kind, summary: r.facts.observation.summary } : null; }
      }
    }, opts || {}));
    return Object.assign({}, base, {
      observe: function (observation) {
        observation = observation || {};
        var o = observation.observation || {};
        if (!o.kind) throw new Error("Observations.observe: observation.kind required");
        if (!OBSERVATION_KINDS[o.kind]) throw new Error("Observations.observe: unregistered kind '" + o.kind + "'");
        var facts = {
          observation: { kind: o.kind, summary: o.summary || "", payload: o.payload || {} },
          observedAt: observation.observedAt || null   // when the truth became real (may predate recording)
        };
        return base.create(
          { subject: entityRefs(observation), evidence: observation.evidence || [], payload: facts },
          { createdBy: observation.recordedBy || "Observation", sources: observation.sources, supersedes: observation.supersedes });
      },
      /* Truths are not events: block the lifecycle-event path structurally so an
         Observation can never drift into an event log (§0.13). Correct via a new
         superseding observation instead. */
      appendEvent: function () { throw new Error("Observations are truths, not events; record a superseding observation to correct."); }
    });
  }

  /* ============ Knowledge — "What does the system understand?" ===============
     The Knowledge family (Rule 14): interpretation DERIVED from Business Facts.
     Unlike a Fact, a Knowledge record can be wrong, updated, superseded, or
     recomputed — but each version is itself immutable; understanding evolves by
     SUPERSEDING, never by editing. This slice is only the container; the Learning/
     Forecast/Risk engines that PRODUCE Knowledge come later and are never its owner
     (Business Facts → engines → Knowledge → Decision proposals → Decisions).

     Payload lives under `finding` (payloadKey). The typed envelope is
     `finding:{ kind, summary, confidence, payload }`:
       - kind        a registered Knowledge kind (distinct business question)
       - summary     plain-English understanding (explainability, Rule 12)
       - confidence  MANDATORY, 0..1 — DESCRIPTIVE only. It states how strongly the
                     system believes something; it never changes valuation, pricing,
                     allocation, or any decision. Acting on Knowledge requires a
                     separate Decision Record (kind:"calibration") to be approved.
       - payload     kind-specific detail (effect size, sample count, basis, …)
     Evidence is directional (§0.12): Knowledge points at the facts / prior knowledge
     that support it. Facts never point back — reverse lookup is the forEvidence
     projection, never a stored dependency. */
  function Knowledge(repositories, opts) {
    var base = foundation(repositories, "knowledge", Object.assign({
      type: "Knowledge Record", idPrefix: "know", category: "knowledge", payloadKey: "finding",
      descriptor: {
        purpose: function (r) { return r.finding ? r.finding.summary : null; },
        confidence: function (r) { return r.finding ? r.finding.confidence : null; }
      }
    }, opts || {}));
    return Object.assign({}, base, {
      /* Persist a derived piece of understanding. `knowledge`:
           { subject, evidence:[{id,role}], finding:{kind,summary,confidence,payload},
             derivedBy?, sources?, supersedes? }
         This is capture only — no inference, ranking, or optimization happens here. */
      derive: function (knowledge) {
        knowledge = knowledge || {};
        var f = knowledge.finding || {};
        if (!f.kind) throw new Error("Knowledge.derive: finding.kind required");
        if (!KNOWLEDGE_KINDS[f.kind]) throw new Error("Knowledge.derive: unregistered kind '" + f.kind + "'");
        if (typeof f.confidence !== "number" || f.confidence < 0 || f.confidence > 1)
          throw new Error("Knowledge.derive: finding.confidence (0..1) is required and descriptive");
        var finding = { kind: f.kind, summary: f.summary || "", confidence: f.confidence, payload: f.payload || {} };
        return base.create(
          { subject: entityRefs(knowledge), evidence: knowledge.evidence || [], payload: finding },
          { createdBy: knowledge.derivedBy || "Knowledge", sources: knowledge.sources, supersedes: knowledge.supersedes });
      },
      byKind: function (kind) { return base.list(function (r) { return r.finding && r.finding.kind === kind; }).sort(byId); },
      /* Knowledge has no recommendation lifecycle; it evolves by superseding. */
      appendEvent: function () { throw new Error("Knowledge evolves by superseding, not lifecycle events."); }
    });
  }

  window.PMRecords = {
    foundation: foundation,
    PredictionSnapshots: PredictionSnapshots,
    DecisionRecords: DecisionRecords,
    Observations: Observations,
    Knowledge: Knowledge,
    DEFAULT_VERSIONS: DEFAULT_VERSIONS,
    LIFECYCLE_EVENTS: LIFECYCLE_EVENTS,
    DECISION_KINDS: DECISION_KINDS,
    OBSERVATION_KINDS: OBSERVATION_KINDS,
    KNOWLEDGE_KINDS: KNOWLEDGE_KINDS,
    ATTRIBUTION_FACTORS: ATTRIBUTION_FACTORS,
    registerLifecycleEvent: registerLifecycleEvent,
    registerDecisionKind: registerDecisionKind,
    registerObservationKind: registerObservationKind,
    registerKnowledgeKind: registerKnowledgeKind,
    registerAttributionFactor: registerAttributionFactor,
    util: { hash: hash, ulid: ulid, deepFreeze: deepFreeze }
  };
})();
