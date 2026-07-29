/* PMRecords — the platform's immutable business-record foundation.
   (Learning Engine Spec §1 standard object model, made executable.)

   This is the ONE implementation of everything every persistent business object
   in the platform inherits:
     • Identity            permanent, k-sortable objectId, independent of VIN (§0.5)
     • Immutable Facts     frozen at creation, never edited/regenerated (§0.4)
     • Provenance          the auditor test — who/when/versions/config/rules/data (§0.6)
     • Integrity           factsHash + verify(): facts are provably unaltered
     • Supersedes chains    corrections are new records linked to the prior (§0.4)
     • Mutable Interpretation append-only versions; conclusions evolve, never overwrite
     • Event history       append-only lifecycle/business events; history grows around facts
     • Self-description    describe(): every object answers the AI-legibility questions

   It sits BELOW the engines and BESIDE the repository layer. Engines produce and
   read records through it; it never ranks, chooses, trusts, or otherwise thinks
   (§0.3). It depends only on the Layer 1 repositories contract, so it is storage-
   and runtime-agnostic (§0.1, §0.2): the same code runs on localStorage, a DB, a
   worker, an API, or a test harness.

   The two concrete platform records live here because nothing owns them but the
   platform: Prediction Snapshots and Decision Records. Observations, Learning
   Signals, and Calibrations will be defined the same way in later layers.

   Exposes window.PMRecords. Inert on load. */
(function () {
  "use strict";

  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }

  /* FNV-1a 32-bit hex — deterministic, dependency-free. Source-data digests and
     facts tamper-evidence. */
  function hash(str) {
    var h = 0x811c9dc5; str = String(str == null ? "" : str);
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ("00000000" + h.toString(16)).slice(-8);
  }

  /* ULID-style k-sortable id: 10-char Crockford-base32 time prefix + random
     suffix. Lexicographically sortable by creation time; DB-index friendly. */
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

  /* Canonical, platform-wide lifecycle events (registry / extension point, R-B).
     Engine-specific events may be registered; unknown types are rejected so the
     event vocabulary can never drift silently. */
  var LIFECYCLE_EVENTS = {
    Generated: true, Presented: true, Viewed: true, Accepted: true, Modified: true,
    Rejected: true, Executed: true, Cancelled: true, Expired: true, Superseded: true
  };
  var TERMINAL_EVENTS = { Executed: true, Cancelled: true, Rejected: true, Expired: true, Superseded: true };
  function registerLifecycleEvent(type) { LIFECYCLE_EVENTS[type] = true; }

  /* Decision-kind registry (typed envelope, R-A). Seeded with the platform's
     known recommendation kinds; extendable so any engine can emit decisions
     without a new object type. */
  var DECISION_KINDS = {};
  ["loaner-retirement", "ctp-adjustment", "acquisition", "trade", "pricing",
   "write-down", "factory-order", "demand", "inventory"].forEach(function (k) { DECISION_KINDS[k] = true; });
  function registerDecisionKind(kind) { DECISION_KINDS[kind] = true; }

  /* ===================== foundation() =====================
     Composes a repository (persistence, Layer 1) with the standard object model
     into the common service surface every platform record shares. Concrete record
     services (snapshots, decisions, …) call this and add only domain-specific
     shaping and queries. */
  function foundation(repositories, collectionKey, opts) {
    opts = opts || {};
    var repo = repositories && repositories[collectionKey];
    if (!repo) throw new Error("PMRecords.foundation: repositories." + collectionKey + " required");
    var type = opts.type || "Record";
    var idPrefix = opts.idPrefix || "rec";
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

    /* Mint a fully-formed immutable record from a fact block. `facts` is the
       object of fact fields to spread at top level; it is copied verbatim
       (capture, not compute — R5) and hashed for tamper-evidence. Not persisted. */
    function mint(facts, meta) {
      meta = meta || {};
      var now = clock();
      var ms = (now && now.getTime) ? now.getTime() : Date.now();
      var iso = (now && now.toISOString) ? now.toISOString() : new Date(ms).toISOString();
      var factCopy = clone(facts) || {};

      var record = {
        // Identity (§0.5)
        id: idPrefix + "-" + ulid(ms, rng),
        objectType: type,
        createdAt: iso,
        supersedes: meta.supersedes || null,   // ledger chain (§0.4)
        // Mutable, append-only histories (empty at creation)
        interpretations: [],
        events: [],
        // Metadata / provenance (§0.6)
        provenance: {
          createdBy: meta.createdBy || (type + "Service"),
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
      // Spread immutable facts at top level, then hash them.
      Object.keys(factCopy).forEach(function (k) { record[k] = factCopy[k]; });
      record.provenance.factsHash = hash(JSON.stringify(factCopy));
      record._factKeys = Object.keys(factCopy);   // which top-level keys are facts (for verify/describe)
      return record;
    }

    function factBlock(rec) {
      var keys = rec._factKeys || [];
      var f = {}; keys.forEach(function (k) { f[k] = rec[k]; });
      return f;
    }

    return {
      type: type,
      collection: collectionKey,
      versions: versions,

      mint: function (facts, meta) { return deepFreeze(mint(facts, meta)); },

      /* Mint + persist. Returns the saved record. */
      create: function (facts, meta) { return repo.save(deepFreeze(mint(facts, meta))); },

      get: function (id) { return repo.getById(id); },
      list: function (pred) { return repo.list(pred); },
      count: function () { return repo.count(); },

      /* Prove facts were not altered out-of-band. */
      verify: function (rec) {
        if (!rec || !rec.provenance) return false;
        return rec.provenance.factsHash === hash(JSON.stringify(factBlock(rec)));
      },

      /* Append a lifecycle/business event — non-destructive (§0.4). Unknown event
         types are rejected so the vocabulary never drifts silently (R-B). */
      appendEvent: function (id, event) {
        event = event || {};
        if (!event.type || !LIFECYCLE_EVENTS[event.type])
          throw new Error(type + ".appendEvent: unknown event type '" + event.type + "' (register it first)");
        if (!event.at) event.at = (clock().toISOString ? clock().toISOString() : new Date().toISOString());
        return repo.appendVersion(id, event, "events");
      },

      /* Append an interpretation version — non-destructive; earlier versions
         are never destroyed. */
      appendInterpretation: function (id, entry) { return repo.appendVersion(id, entry || {}, "interpretations"); },

      /* Follow the supersedes chain oldest→newest for a record. */
      history: function (id) {
        var chain = [], seen = {}, cur = repo.getById(id);
        while (cur && !seen[cur.id]) { chain.unshift(cur); seen[cur.id] = true; cur = cur.supersedes ? repo.getById(cur.supersedes) : null; }
        return chain;
      },

      /* AI-legibility (spec §"Future AI Compatibility"): answer the standard
         questions from standard fields alone — no engine-specific knowledge. */
      describe: function (rec) {
        if (!rec) return null;
        var terminal = null;
        (rec.events || []).forEach(function (e) { if (TERMINAL_EVENTS[e.type]) terminal = e; });
        return {
          whatAmI: rec.objectType,
          whyDoIExist: (rec.recommendation && rec.recommendation.summary) || null,
          whoCreatedMe: rec.provenance && rec.provenance.createdBy,
          when: rec.createdAt,
          immutableFactKeys: rec._factKeys || [],
          interpretationsOverTime: (rec.interpretations || []).length,
          eventsOverTime: (rec.events || []).length,
          relatedObjects: {
            supersedes: rec.supersedes || null,
            basedOn: rec.basedOn || [],
            contextRefs: rec.contextRefs || [],
            relationships: rec.relationships || null
          },
          whatDecisionWasMade: rec.recommendation ? { kind: rec.recommendation.kind, summary: rec.recommendation.summary } : null,
          whatUltimatelyHappened: terminal ? { type: terminal.type, at: terminal.at } : null
        };
      }
    };
  }

  /* ===================== PredictionSnapshotService (Layer 2, refactored) =====
     Captures what the valuation/retirement engines produced at decision-commit
     time (Q1). Same record shape as before + the uniform interpretations/events
     logs every platform object now inherits (Decision 2). */
  function PredictionSnapshotService(repositories, opts) {
    var base = foundation(repositories, "predictionSnapshots",
      Object.assign({ type: "PredictionSnapshot", idPrefix: "psnap" }, opts || {}));
    return Object.assign({}, base, {
      commit: function (decision) {
        if (!decision || !decision.prediction)
          throw new Error("PredictionSnapshotService.commit: decision.prediction required");
        var facts = {
          subject: decision.subject || {},              // VIN lives here as a relationship
          decisionContext: decision.decisionContext || {},
          contextRefs: decision.contextRefs || [],      // future external Context records
          prediction: decision.prediction               // pure copy of engine output (R5)
        };
        return base.create(facts, {
          createdBy: decision.committedBy || "PredictionSnapshotService",
          sources: decision.sources, supersedes: decision.supersedes
        });
      },
      forVin: function (vin) {
        return base.list(function (r) { return r.subject && r.subject.vin === vin; })
          .sort(function (a, b) { return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; });
      }
    });
  }

  /* ===================== DecisionRecordService (Layer 3, platform object) =====
     A Decision Record is a platform object every engine emits with the same
     immutable structure. The recommendation never changes; history (events,
     interpretations) grows around it. */
  function DecisionRecordService(repositories, opts) {
    var base = foundation(repositories, "decisions",
      Object.assign({ type: "DecisionRecord", idPrefix: "dec" }, opts || {}));
    return Object.assign({}, base, {
      /* Record a recommendation. `decision`:
           { origin:{engine,engineVersion}, recommendation:{kind,summary,payload},
             rationale:{why,assumptions,confidence}, context, contextRefs, basedOn,
             relationships, sources, committedBy, supersedes } */
      record: function (decision) {
        decision = decision || {};
        var rec = decision.recommendation || {};
        if (!rec.kind) throw new Error("DecisionRecordService.record: recommendation.kind required");
        if (!DECISION_KINDS[rec.kind]) throw new Error("DecisionRecordService.record: unregistered kind '" + rec.kind + "'");
        var facts = {
          origin: decision.origin || {},                                  // which engine produced it
          recommendation: { kind: rec.kind, summary: rec.summary || "", payload: rec.payload || {} }, // typed envelope
          rationale: decision.rationale || { why: "", assumptions: [], confidence: null },
          context: decision.context || {},                                // embedded for now
          contextRefs: decision.contextRefs || [],                        // future external Context records
          basedOn: decision.basedOn || [],                                // e.g. prediction snapshot ids
          relationships: decision.relationships ||
            { parentId: null, dependsOn: [], alternativesTo: [], bundleId: null }
        };
        var saved = base.create(facts, {
          createdBy: decision.committedBy || (facts.origin.engine || "DecisionRecordService"),
          sources: decision.sources, supersedes: decision.supersedes
        });
        return saved;
      },
      forVin: function (vin) {
        return base.list(function (r) {
          return (r.context && r.context.vin === vin) ||
                 (r.recommendation && r.recommendation.payload && r.recommendation.payload.vin === vin);
        }).sort(function (a, b) { return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; });
      },
      forEngine: function (engine) {
        return base.list(function (r) { return r.origin && r.origin.engine === engine; })
          .sort(function (a, b) { return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; });
      }
    });
  }

  window.PMRecords = {
    foundation: foundation,
    PredictionSnapshotService: PredictionSnapshotService,
    DecisionRecordService: DecisionRecordService,
    DEFAULT_VERSIONS: DEFAULT_VERSIONS,
    LIFECYCLE_EVENTS: LIFECYCLE_EVENTS,
    DECISION_KINDS: DECISION_KINDS,
    registerLifecycleEvent: registerLifecycleEvent,
    registerDecisionKind: registerDecisionKind,
    util: { hash: hash, ulid: ulid, deepFreeze: deepFreeze }
  };
})();
