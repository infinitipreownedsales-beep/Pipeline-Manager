/* Repository Layer — the platform's ONE persistence boundary.
   (Learning Engine Spec, Layer 1.)

   Business engines never touch storage technology. They talk to repositories,
   which expose a technology-neutral contract (save / getById / list / all /
   count / appendVersion). A repository is backed by a StorageAdapter: today the
   adapter writes to localStorage; tomorrow it may write to SQLite, PostgreSQL,
   or the cloud. Swapping the adapter never changes a single line of engine logic.

   This module defines ONLY the abstraction. Record schemas (Prediction Snapshot,
   Recommendation Record, Observation, Interpretation) arrive in later layers; the
   repositories here are schema-agnostic. They enforce the fact-vs-interpretation
   contract that the whole platform depends on:
     - facts are written once and never modified or regenerated;
     - interpretations/state are appended as new versions, never overwritten.

   Exposes window.PMRepo. Nothing here runs on load or writes to storage; a live
   repository exists only once an engine asks for one. */
(function () {
  "use strict";

  /* Repositories hand out deep copies so stored state can never be mutated by a
     caller through a shared reference — the backbone of both immutability and
     deterministic reads. */
  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }

  /* ===================== Storage adapters =====================
     An adapter is a namespaced collection store. Its entire contract:
       read(collection)            -> array of records (never null)
       write(collection, records)  -> void
       collections()               -> array of known collection names
     Everything above the adapter is storage-technology agnostic. To add a new
     backend (SQLite, Postgres, cloud) you implement these three methods; no
     engine, repository, or spec above this line changes. */

  /* In-memory adapter: no DOM, no localStorage. Lets the engines run and be
     tested deterministically off-browser, and is the reference backend for
     proving engine/storage independence. */
  function MemoryAdapter() {
    var mem = {};
    return {
      kind: "memory",
      read: function (c) { return mem[c] ? clone(mem[c]) : []; },
      write: function (c, recs) { mem[c] = clone(recs); },
      collections: function () { return Object.keys(mem); }
    };
  }

  /* localStorage adapter: today's production backend. Records are business
     records, not cache — an index key lets export/import round-trip every
     collection so history survives a browser wipe. */
  function LocalStorageAdapter(opts) {
    opts = opts || {};
    var prefix = opts.prefix || "pm_repo_";
    var store = opts.store || (typeof localStorage !== "undefined" ? localStorage : null);
    if (!store) throw new Error("LocalStorageAdapter: no localStorage available");
    var indexKey = prefix + "__collections__";
    function idx() { try { return JSON.parse(store.getItem(indexKey)) || []; } catch (e) { return []; } }
    function remember(c) {
      var i = idx();
      if (i.indexOf(c) < 0) { i.push(c); store.setItem(indexKey, JSON.stringify(i)); }
    }
    return {
      kind: "localStorage",
      read: function (c) { try { return JSON.parse(store.getItem(prefix + c)) || []; } catch (e) { return []; } },
      write: function (c, recs) { store.setItem(prefix + c, JSON.stringify(recs)); remember(c); },
      collections: function () { return idx(); }
    };
  }

  /* ===================== Repository =====================
     Schema-agnostic store for records that follow the standard object model
       { id, ...immutableFacts, interpretations:[...], meta:{...} }
     The repository requires only a non-empty `id` (Identity); it never inspects
     the fact payload, so it serves every business object the same way. */
  function Repository(adapter, collection, opts) {
    opts = opts || {};
    var immutableFacts = opts.immutableFacts !== false; // default: facts written once
    function load() { return adapter.read(collection); }
    function persist(recs) { adapter.write(collection, recs); }
    function findIndex(recs, id) { for (var i = 0; i < recs.length; i++) if (recs[i].id === id) return i; return -1; }

    return {
      collection: collection,
      immutableFacts: immutableFacts,

      /* Write a NEW record. Facts are written once: re-saving an existing id in
         an immutable repository is a contract violation, because facts are never
         regenerated. Mutable collections (immutableFacts:false) may replace. */
      save: function (record) {
        if (record == null || record.id == null || record.id === "")
          throw new Error(collection + ".save: record needs a non-empty id");
        var recs = load(), at = findIndex(recs, record.id);
        if (at >= 0) {
          if (immutableFacts)
            throw new Error(collection + ".save: id '" + record.id + "' already exists; facts are immutable");
          recs[at] = clone(record);
        } else {
          recs.push(clone(record));
        }
        persist(recs);
        return clone(record);
      },

      getById: function (id) { var recs = load(), i = findIndex(recs, id); return i < 0 ? null : clone(recs[i]); },
      list: function (pred) { var recs = load(); return (pred ? recs.filter(pred) : recs).map(clone); },
      all: function () { return load().map(clone); },
      count: function () { return load().length; },
      has: function (id) { return findIndex(load(), id) >= 0; },

      /* Append a version to a named log on an existing record WITHOUT touching
         its facts. Interpretations evolve forever and lifecycle state accretes;
         earlier versions are never destroyed. arrayKey selects the log
         ("interpretations" by default; e.g. "states" for lifecycle history).
         Each entry is stamped with a monotonic version number. */
      appendVersion: function (id, entry, arrayKey) {
        var key = arrayKey || "interpretations";
        var recs = load(), i = findIndex(recs, id);
        if (i < 0) throw new Error(collection + ".appendVersion: no record '" + id + "'");
        var rec = recs[i];
        // Structural immutability: only append-log arrays may grow. Refuse to
        // overwrite any existing non-array field (facts, subject, provenance, …).
        if (key in rec && !Array.isArray(rec[key]))
          throw new Error(collection + ".appendVersion: '" + key + "' is immutable, not an append log");
        if (!Array.isArray(rec[key])) rec[key] = [];
        var v = clone(entry) || {};
        v.version = rec[key].length + 1;
        rec[key].push(v);
        persist(recs);
        return clone(rec);
      }
    };
  }

  /* ===================== The persistence boundary =====================
     Wires the named repositories the Learning Engine talks to. An engine
     receives this object and never learns which adapter backs it. Absent an
     explicit adapter, prefer localStorage in a browser, memory otherwise. */
  function createRepositories(adapter) {
    adapter = adapter || (typeof localStorage !== "undefined" ? LocalStorageAdapter() : MemoryAdapter());

    var predictionSnapshots = Repository(adapter, "prediction_snapshots", { immutableFacts: true });
    var decisions = Repository(adapter, "decisions", { immutableFacts: true });   // platform Decision Records
    var observations = Repository(adapter, "observations", { immutableFacts: true });
    var interpretations = Repository(adapter, "interpretations", { immutableFacts: true });

    /* Export every collection as one JSON document — business records that
       outlive the browser. */
    function exportJSON(pretty) {
      var dump = { _format: "pm-repo/v1", collections: {} };
      adapter.collections().forEach(function (c) { dump.collections[c] = adapter.read(c); });
      return JSON.stringify(dump, pretty === false ? undefined : null, pretty === false ? undefined : 2);
    }

    /* Load records back. mode "merge" (default) appends only ids not already
       present, so re-importing can never fork a fact; "replace" overwrites. */
    function importJSON(json, mode) {
      var data = (typeof json === "string") ? JSON.parse(json) : json;
      var cols = (data && data.collections) || {};
      Object.keys(cols).forEach(function (c) {
        if (mode === "replace") { adapter.write(c, cols[c]); return; }
        var existing = adapter.read(c), seen = {};
        existing.forEach(function (r) { seen[r.id] = true; });
        cols[c].forEach(function (r) { if (!seen[r.id]) existing.push(r); });
        adapter.write(c, existing);
      });
    }

    return {
      adapter: adapter,
      predictionSnapshots: predictionSnapshots,
      decisions: decisions,
      observations: observations,
      interpretations: interpretations,
      exportJSON: exportJSON,
      importJSON: importJSON
    };
  }

  /* Convenience id generator. Identity is meaningful where possible (e.g. a
     snapshot keyed by VIN + decision time); this is only a fallback. Not
     deterministic by nature, so callers that need reproducibility supply ids. */
  var _seq = 0;
  function uid(prefix) { _seq += 1; return (prefix || "id") + "-" + Date.now().toString(36) + "-" + _seq; }

  window.PMRepo = {
    MemoryAdapter: MemoryAdapter,
    LocalStorageAdapter: LocalStorageAdapter,
    Repository: Repository,
    createRepositories: createRepositories,
    uid: uid
  };
})();
