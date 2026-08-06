"""Performance-baseline measurement for representative pilot workloads.

Measures wall-clock duration of representative operations and records each as an immutable
operational_metric with its environment, dataset size, and cold/warm flag. These are BASELINES (evidence
for where to look), not guarantees. Optimization guided by these metrics must never change an authoritative
result, and no caching that risks a stale authoritative display is introduced here — this module only
measures.
"""
from __future__ import annotations

import time


class PerformanceHarness:
    def __init__(self, ops_store, clock, environment="pilot"):
        self.ops, self.clock, self.environment = ops_store, clock, environment

    def measure(self, metric_key, fn, *, workload=None, dataset_size=None, cold=False, detail=None):
        t0 = time.perf_counter()
        result = fn()
        dur = round((time.perf_counter() - t0) * 1000, 3)
        self.ops.add_metric(metric_key, dur, workload=workload, dataset_size=dataset_size,
                            environment=self.environment, cold=cold, detail=detail)
        return result, dur

    def baseline_report(self):
        rows = self.ops.list_metrics()
        agg = {}
        for r in rows:
            k = r["metric_key"]
            a = agg.setdefault(k, {"count": 0, "min_ms": None, "max_ms": None, "total_ms": 0.0})
            d = r["duration_ms"] or 0.0
            a["count"] += 1
            a["min_ms"] = d if a["min_ms"] is None else min(a["min_ms"], d)
            a["max_ms"] = d if a["max_ms"] is None else max(a["max_ms"], d)
            a["total_ms"] += d
        for k, a in agg.items():
            a["avg_ms"] = round(a["total_ms"] / a["count"], 3) if a["count"] else None
        return agg

    def slow_queries(self, threshold_ms):
        """Return recorded metrics slower than a threshold (evidence for indexing decisions)."""
        return [r for r in self.ops.list_metrics() if (r["duration_ms"] or 0) > threshold_ms]
