/* Learning Engine — the platform's FIRST intelligence layer. (Slice 3: Error only.)

   A PRODUCER of Knowledge, never the owner of institutional memory (§0.19). It
   reads Business Facts (Prediction Snapshots + Observations) and writes Knowledge
   (Error records) through PMRecords. It NEVER touches valuation/retirement, never
   decides, never optimizes, never calibrates. Replace it tomorrow with a smarter
   model and not one Fact, Decision, Observation, or Knowledge record would need to
   change — because everything it produces is a standard platform Knowledge record.

   Slice 3 answers exactly one question, well:
     "Where did our understanding of reality differ from what reality became?"

   It is domain-blind. It compares two known values across a defined DIMENSION using
   a registered comparison spec; it does not know what a QX80, a resale price, or an
   allocation is. All domain meaning lives in the comparison registry (data), so the
   same engine serves new inventory, used, loaners, salespeople, pricing, and any
   future engine without change.

   Exposes window.LearningEngine. Inert on load — nothing runs until deriveErrors()
   is called. */
(function () {
  "use strict";

  var SELECTION_RULE = "operative-snapshot";     // which belief we compared, and why
  var SELECTION_RULE_VERSION = "1.0.0";

  /* Traverse "a.b.c"; undefined if any hop is missing. Domain-blind reader. */
  function getPath(obj, path) {
    if (obj == null || !path) return undefined;
    var parts = String(path).split("."), cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (cur == null || typeof cur !== "object") return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }

  /* When did this record's truth take effect? Observations may carry an observedAt
     (the truth may predate its recording); everything else uses createdAt. */
  function timeOf(rec) {
    if (rec && rec.facts && rec.facts.observedAt) {
      var t = Date.parse(rec.facts.observedAt);
      if (!isNaN(t)) return t;
    }
    return Date.parse(rec.createdAt);
  }

  /* Domain-blind gap: surprise, not just subtraction. Preserves expected, actual,
     signed size, magnitude, and direction over a named dimension. Numeric values
     yield a delta; anything else yields exact/mismatch. */
  function computeError(dimension, expected, actual) {
    if (typeof expected === "number" && typeof actual === "number") {
      var delta = actual - expected;
      return {
        dimension: dimension, expected: expected, actual: actual,
        delta: delta, magnitude: Math.abs(delta),
        direction: delta > 0 ? "under-predicted" : delta < 0 ? "over-predicted" : "exact"
      };
    }
    var same = JSON.stringify(expected) === JSON.stringify(actual);
    return {
      dimension: dimension, expected: expected, actual: actual,
      delta: null, magnitude: null, direction: same ? "exact" : "mismatch"
    };
  }

  function summarize(e) {
    if (e.direction === "exact") return "On " + e.dimension + ": prediction matched reality (" + JSON.stringify(e.expected) + ").";
    if (e.delta != null) return "On " + e.dimension + ": " + (e.delta > 0 ? "+" : "") + e.delta +
      " (" + e.direction + "; expected " + e.expected + ", actual " + e.actual + ").";
    return "On " + e.dimension + ": " + e.direction + " (expected " + JSON.stringify(e.expected) +
      ", actual " + JSON.stringify(e.actual) + ").";
  }

  /* ===================== Comparison registry =====================
     The ONLY domain-aware part, and it is DATA. A spec says: for observations of
     this kind, the belief lives at beliefPath in a snapshot's facts and the reality
     at realityPath in the observation's facts, compared over `dimension`. Adding a
     dimension or a new domain is a registry entry, never engine code. */
  var COMPARISONS = [];
  function registerComparison(spec) {
    if (!spec || !spec.observationKind || !spec.dimension || !spec.beliefPath || !spec.realityPath)
      throw new Error("registerComparison: observationKind, dimension, beliefPath, realityPath required");
    COMPARISONS.push(spec); return spec;
  }
  function comparisons() { return COMPARISONS.slice(); }

  /* ===================== Error derivation =====================
     Reads facts, writes Error Knowledge. Pure producer. */
  function ErrorEngine(repositories, opts) {
    opts = opts || {};
    if (!window.PMRecords) throw new Error("LearningEngine: PMRecords not loaded");
    var K = window.PMRecords.Knowledge(repositories, { clock: opts.clock, rng: opts.rng });
    var snapRepo = repositories.predictionSnapshots;
    var obsRepo = repositories.observations;
    var specs = opts.comparisons || COMPARISONS;
    // Error certainty of a clean measured gap is 1.0 (arithmetic on facts). A hook
    // is left for future data-quality reduction; NOTE this is Error certainty, a
    // DIFFERENT concept from the prediction's own confidence (preserved on the
    // snapshot) — the model keeps them separable for a future "expected confidence".
    var confidenceOf = opts.confidence || function () { return 1.0; };

    /* The operative belief for (entity, dimension) at the moment of an observation:
       a snapshot that shares an entity with the observation, provides beliefPath,
       and predates the observation. Among those, the head of the supersede chain.
       Exactly one head → resolved; zero → pending; more than one independent head
       → ambiguous, left UNRESOLVED (§0.21) rather than guessed. */
    function operative(obs, spec, allSnaps) {
      var obsTime = timeOf(obs), ent = {};
      (obs.subject || []).forEach(function (e) { ent[e.type + "|" + e.id] = true; });
      var cands = allSnaps.filter(function (s) {
        var shares = (s.subject || []).some(function (e) { return ent[e.type + "|" + e.id]; });
        return shares && getPath(s.facts, spec.beliefPath) !== undefined && timeOf(s) <= obsTime;
      });
      if (!cands.length) return { status: "pending" };
      var ids = {}; cands.forEach(function (c) { ids[c.id] = true; });
      var superseded = {}; cands.forEach(function (c) { if (c.supersedes && ids[c.supersedes]) superseded[c.supersedes] = true; });
      var heads = cands.filter(function (c) { return !superseded[c.id]; });
      if (heads.length === 1) return { status: "ok", snapshot: heads[0] };
      return { status: "ambiguous" };
    }

    /* Current (non-superseded) Error for a logical (observation, dimension) key. */
    function currentError(obsId, dimension) {
      var errs = K.byKind("error").filter(function (k) {
        var sel = k.finding.payload && k.finding.payload.selection;
        return sel && sel.observationId === obsId && k.finding.payload.dimension === dimension;
      });
      var ids = {}; errs.forEach(function (k) { ids[k.id] = true; });
      var sup = {}; errs.forEach(function (k) { if (k.supersedes && ids[k.supersedes]) sup[k.supersedes] = true; });
      var heads = errs.filter(function (k) { return !sup[k.id]; });
      return heads.length ? heads[heads.length - 1] : null;
    }

    return {
      /* Recognize every belief/reality gap the registry can express. Idempotent:
         a clean re-run over unchanged facts creates nothing; a changed operative
         belief supersedes the prior Error (never edits, never duplicates). */
      deriveErrors: function () {
        var result = { created: [], superseded: [], noop: 0, pending: 0, ambiguous: 0 };
        var allSnaps = snapRepo.list(), allObs = obsRepo.list();
        allObs.forEach(function (obs) {
          var okind = obs.facts.observation && obs.facts.observation.kind;
          specs.forEach(function (spec) {
            if (spec.observationKind !== okind) return;
            var reality = getPath(obs.facts, spec.realityPath);
            if (reality === undefined) return;
            var op = operative(obs, spec, allSnaps);
            if (op.status === "pending") { result.pending++; return; }
            if (op.status === "ambiguous") { result.ambiguous++; return; }
            var snap = op.snapshot;
            var belief = getPath(snap.facts, spec.beliefPath);
            var e = computeError(spec.dimension, belief, reality);
            var finding = {
              kind: "error",
              summary: summarize(e),
              confidence: confidenceOf(snap, obs, e),
              payload: {
                dimension: e.dimension, expected: e.expected, actual: e.actual,
                delta: e.delta, magnitude: e.magnitude, direction: e.direction,
                // Why these two records were compared — explicit, never hidden in code.
                selection: {
                  predictionSnapshotId: snap.id, observationId: obs.id,
                  rule: SELECTION_RULE, ruleVersion: SELECTION_RULE_VERSION
                }
              }
            };
            var head = currentError(obs.id, spec.dimension);
            var derive = {
              subject: snap.subject,
              evidence: [{ id: snap.id, role: "belief" }, { id: obs.id, role: "reality" }],
              finding: finding, derivedBy: "ErrorEngine"
            };
            if (head) {
              var p = head.finding.payload;
              var unchanged = p.selection.predictionSnapshotId === snap.id &&
                p.delta === e.delta &&
                JSON.stringify(p.expected) === JSON.stringify(e.expected) &&
                JSON.stringify(p.actual) === JSON.stringify(e.actual);
              if (unchanged) { result.noop++; return; }
              derive.supersedes = head.id;                 // operative belief/gap changed
              result.superseded.push(K.derive(derive));
              return;
            }
            result.created.push(K.derive(derive));
          });
        });
        return result;
      }
    };
  }

  /* Convenience: one-shot derivation with an explicit spec set. */
  function deriveErrors(repositories, opts) { return ErrorEngine(repositories, opts).deriveErrors(); }

  /* ===================== Attribution (Slice 4) =====================
     Answers only: "What factors are plausible contributors to the observed gap?"
     — never "who is responsible," never an action. Attribution is Knowledge only
     (kind:"attribution"); the producer creates NO Decisions, recommendations,
     valuation changes, accountability, or workflow.

     One Knowledge record PER FACTOR HYPOTHESIS. Competing explanations for one
     Error are SIBLINGS, never a hierarchy — each with independent identity,
     confidence, strength, evidence, and supersession history.

     Intentionally IMMATURE (no causal AI): the factor hypotheses are supplied by
     the caller; this slice only records them as proper Knowledge with correct
     relationships (evidence, competing siblings, supersession, aggregation-ready).
     The intelligence matures later via Learning Signals.

     Two independent measures, kept permanently separate:
       confidence — how likely this factor is actually contributing (0..1)
       strength   — IF true, how much of the gap it explains (0..1); never a hidden
                    confidence score.
     People may appear only as related entities/evidence, never as blame. */
  function AttributionEngine(repositories, opts) {
    opts = opts || {};
    if (!window.PMRecords) throw new Error("LearningEngine: PMRecords not loaded");
    var K = window.PMRecords.Knowledge(repositories, { clock: opts.clock, rng: opts.rng });
    var FACTORS = window.PMRecords.ATTRIBUTION_FACTORS;

    function num01(x) { return typeof x === "number" && x >= 0 && x <= 1; }

    return {
      /* Record one or more competing factor hypotheses for an Error. Each
         hypothesis: { factor, confidence, strength, support?:[{id,role}],
                       summary?, supersedes? }. Returns the created attribution
         Knowledge records (siblings). */
      attribute: function (errorId, hypotheses) {
        var err = K.get(errorId);
        if (!err || err.finding.kind !== "error")
          throw new Error("AttributionEngine.attribute: '" + errorId + "' is not an Error Knowledge record");
        hypotheses = hypotheses || [];
        var dimension = err.finding.payload && err.finding.payload.dimension;
        // inherit the Error's belief/reality evidence so the chain stays traceable
        var inherited = (err.evidence || []).filter(function (e) { return e.role === "belief" || e.role === "reality"; });
        var out = [];
        hypotheses.forEach(function (h) {
          if (!h || !h.factor) throw new Error("attribute: hypothesis.factor required");
          if (!FACTORS[h.factor]) throw new Error("attribute: unregistered factor '" + h.factor + "'");
          if (!num01(h.confidence)) throw new Error("attribute: confidence (0..1) required — how likely this factor contributed");
          if (!num01(h.strength)) throw new Error("attribute: strength (0..1) required — how much of the gap it explains if true");
          var support = (h.support || []).slice();
          var evidence = [{ id: errorId, role: "explains" }].concat(inherited, support);
          var finding = {
            kind: "attribution",
            summary: h.summary || ("Attribution: " + h.factor + " factor — confidence " + h.confidence +
              ", explains ~" + Math.round(h.strength * 100) + "% of the gap if true"),
            confidence: h.confidence,                 // is this factor actually contributing?
            payload: {
              factor: h.factor,
              strength: h.strength,                   // how much of the gap, if true (NOT confidence)
              errorId: errorId,
              dimension: dimension == null ? null : dimension
            }
          };
          out.push(K.derive({
            subject: err.subject, evidence: evidence, finding: finding,
            derivedBy: "AttributionEngine", supersedes: h.supersedes || null
          }));
        });
        return out;
      },
      /* Projection: current (non-superseded) attributions for an Error — the live
         set of competing hypotheses. */
      forError: function (errorId) {
        var all = K.byKind("attribution").filter(function (k) { return k.finding.payload.errorId === errorId; });
        var ids = {}; all.forEach(function (k) { ids[k.id] = true; });
        var sup = {}; all.forEach(function (k) { if (k.supersedes && ids[k.supersedes]) sup[k.supersedes] = true; });
        return all.filter(function (k) { return !sup[k.id]; });
      }
    };
  }

  window.LearningEngine = {
    ErrorEngine: ErrorEngine,
    deriveErrors: deriveErrors,
    computeError: computeError,
    registerComparison: registerComparison,
    comparisons: comparisons,
    AttributionEngine: AttributionEngine,
    SELECTION_RULE: SELECTION_RULE,
    SELECTION_RULE_VERSION: SELECTION_RULE_VERSION,
    util: { getPath: getPath }
  };
})();
