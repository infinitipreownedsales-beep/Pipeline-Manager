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
    var descriptor = opts.descriptor || {};
    var versions = opts.versions || DEFAULT_VERSIONS;
    var clock = opts.clock || function () { return new Date(); };
    var rng = opts.rng || Math.random;

    function digestSources(sources) {
      var d = {};
      if (!sources) return d;
      if (sources.inventory != null) d.inventoryDigest = hash(sources.inventory);
      if (sources.history != null) d.historyDigest = hash(sources.history);
      if (sources.digests) Object.keys(sources.digests).forEach(function (k) { d[k] = sources.digests[k]; });
      return d;
    }

    /* The immutable core is everything that can never change: the entity
       references, the evidence, the supersedes link, and the fact block. It is
       hashed as one unit, so tampering with any of it is detectable. */
    function coreOf(input, supersedes) {
      return {
        subject: clone(input.subject) || [],     // canonical entity references
        evidence: clone(input.evidence) || [],   // facts this fact exists because of
        supersedes: supersedes || null,          // correction chain
        facts: clone(input.facts) || {}          // the frozen fact block
      };
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
        facts: core.facts,
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
      record.provenance.factsHash = hash(JSON.stringify(core));
      return record;
    }

    function coreFromRecord(rec) {
      return { subject: rec.subject, evidence: rec.evidence, supersedes: rec.supersedes, facts: rec.facts };
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
          immutableFacts: Object.keys(rec.facts || {}),
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
          { subject: entityRefs(prediction), evidence: prediction.evidence || [], facts: facts },
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
          { subject: entityRefs(decision), evidence: decision.evidence || decision.basedOn || [], facts: facts },
          { createdBy: decision.committedBy || (facts.origin.engine || "Decision Record"), sources: decision.sources, supersedes: decision.supersedes });
      },
      forEngine: function (engine) {
        return base.list(function (r) { return r.facts.origin && r.facts.origin.engine === engine; }).sort(byId);
      }
    });
  }

  window.PMRecords = {
    foundation: foundation,
    PredictionSnapshots: PredictionSnapshots,
    DecisionRecords: DecisionRecords,
    DEFAULT_VERSIONS: DEFAULT_VERSIONS,
    LIFECYCLE_EVENTS: LIFECYCLE_EVENTS,
    DECISION_KINDS: DECISION_KINDS,
    registerLifecycleEvent: registerLifecycleEvent,
    registerDecisionKind: registerDecisionKind,
    util: { hash: hash, ulid: ulid, deepFreeze: deepFreeze }
  };
})();
