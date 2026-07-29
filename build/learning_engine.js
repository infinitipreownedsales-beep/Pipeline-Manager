/* Learning Engine — Step 6. The dealership's institutional memory.
   (Learning Engine Spec, Layers 2+.)

   Storage-agnostic AND runtime-agnostic (§0.1, §0.2): this engine depends only on
   a `repositories` object (the persistence contract from Layer 1) and on plain
   data handed to it by whoever committed a decision. It knows nothing about the
   DOM, the renderer, localStorage, or the host application, so it runs unchanged
   inside Pipeline Manager, another app, a worker, an API, or a test harness.

   It CAPTURES facts; it never computes them (§0.3). A Prediction Snapshot is a
   pure record of what the valuation/retirement engines already produced — the
   service adds identity, provenance, and integrity, and persists. It introduces
   no valuation or retirement logic, so engine output stays byte-identical.

   Exposes window.LearningEngine. Inert on load: nothing runs until a caller
   constructs a service and commits a decision. */
(function () {
  "use strict";

  /* Version stamps travel with the code (Q4, §0.6). Hand-bumped per release so a
     snapshot correlates back to exactly what produced it. */
  var VERSIONS = {
    buildId: "pm-2026.07",
    valuationEngineVersion: "1.0.0",
    retirementEngineVersion: "1.0.0",
    learningEngineVersion: "1.0.0",
    configurationVersion: "1.0.0",
    businessRulesVersion: "1.0.0"   // R2: rules can change independently of engine code
  };

  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }

  /* FNV-1a 32-bit hex — deterministic, dependency-free. Used for source-data
     digests (§0.6 "which source data") and facts tamper-evidence (R4). */
  function hash(str) {
    var h = 0x811c9dc5; str = String(str == null ? "" : str);
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ("00000000" + h.toString(16)).slice(-8);
  }

  /* ULID-style k-sortable id (R1): 10-char Crockford-base32 time prefix + random
     suffix. Lexicographically sortable by creation time, so the snapshot ledger
     orders itself without a separate sort key and indexes cleanly in a future DB.
     Dependency-free; time/rng injectable for deterministic tests. */
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

  /* ===================== PredictionSnapshotService (Layer 2) =====================
     Captures a committed management decision as a permanent, immutable snapshot.
     Constructed with the repositories set; time/rng/versions injectable. */
  function PredictionSnapshotService(repositories, opts) {
    opts = opts || {};
    if (!repositories || !repositories.predictionSnapshots)
      throw new Error("PredictionSnapshotService: repositories.predictionSnapshots required");
    var repo = repositories.predictionSnapshots;
    var clock = opts.clock || function () { return new Date(); };
    var rng = opts.rng || Math.random;
    var versions = opts.versions || VERSIONS;

    function digestSources(sources) {
      var d = {};
      if (!sources) return d;
      if (sources.inventory != null) d.inventoryDigest = hash(sources.inventory);
      if (sources.history != null) d.historyDigest = hash(sources.history);
      if (sources.digests) Object.keys(sources.digests).forEach(function (k) { d[k] = sources.digests[k]; });
      return d;
    }

    return {
      versions: versions,

      /* Capture (never compute) a committed decision as a permanent snapshot.
         `decision` carries only data the engines already produced:
           { subject, decisionContext, prediction, sources?, committedBy?, supersedes? }
         Returns the persisted, deep-frozen record. */
      commit: function (decision) {
        if (!decision || !decision.prediction)
          throw new Error("PredictionSnapshotService.commit: decision.prediction required");
        var now = clock();
        var ms = (now && now.getTime) ? now.getTime() : Date.now();
        var iso = (now && now.toISOString) ? now.toISOString() : new Date(ms).toISOString();

        // R5: facts are a pure copy of engine output — never reshaped or re-derived.
        var facts = {
          subject: clone(decision.subject) || {},
          decisionContext: clone(decision.decisionContext) || {},
          prediction: clone(decision.prediction)
        };

        var record = {
          // Identity (§0.5): permanent objectId, independent of VIN.
          id: "psnap-" + ulid(ms, rng),
          objectType: "PredictionSnapshot",
          createdAt: iso,
          supersedes: decision.supersedes || null,   // ledger chain (§0.4)
          // Immutable facts
          subject: facts.subject,                     // VIN lives here as a relationship
          decisionContext: facts.decisionContext,
          prediction: facts.prediction,
          // Mutable interpretation — empty at creation; Errors/Attribution attach later
          interpretations: [],
          // Metadata / provenance (§0.6 — the auditor test)
          provenance: {
            createdBy: decision.committedBy || "PredictionSnapshotService",
            createdAt: iso,
            buildId: versions.buildId,
            valuationEngineVersion: versions.valuationEngineVersion,
            retirementEngineVersion: versions.retirementEngineVersion,
            learningEngineVersion: versions.learningEngineVersion,
            configurationVersion: versions.configurationVersion,
            businessRulesVersion: versions.businessRulesVersion,
            sourceData: digestSources(decision.sources)
          }
        };
        // R4: tamper-evidence over the fact block.
        record.provenance.factsHash = hash(JSON.stringify(facts));
        return repo.save(deepFreeze(record));
      },

      /* Prove a stored snapshot's facts were not altered out-of-band. */
      verify: function (snapshot) {
        if (!snapshot || !snapshot.provenance) return false;
        var facts = {
          subject: snapshot.subject,
          decisionContext: snapshot.decisionContext,
          prediction: snapshot.prediction
        };
        return snapshot.provenance.factsHash === hash(JSON.stringify(facts));
      },

      /* Query (retrieval + deterministic ordering, no judgment): every snapshot
         for a VIN, oldest→newest. Ordering is free because ids are k-sortable. */
      forVin: function (vin) {
        return repo.list(function (r) { return r.subject && r.subject.vin === vin; })
          .sort(function (a, b) { return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; });
      }
    };
  }

  window.LearningEngine = {
    VERSIONS: VERSIONS,
    PredictionSnapshotService: PredictionSnapshotService,
    util: { hash: hash, ulid: ulid, deepFreeze: deepFreeze }
  };
})();
