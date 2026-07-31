/*
 * geometry.js — pure hole geometry the decision engine reasons over.
 *
 * A hole is a bending corridor: a normalized centerline `path` of [d,x] points
 * (d=0 tee → 1 green, x=0 left → 1 right) plus structured `hazards` (side bands
 * {side,type,from,to} and positioned pools {type,pool:[d0,d1,x0,x1]}). These
 * helpers read a spot on that corridor. They were the map's local helpers in
 * CaddieOS; lifted here so BOTH the map and the decision engine read one source
 * of truth. Pure — no React, no storage, no DOM.
 */

// centerX(path, d) — the fairway centerline x at fractional distance d.
export const centerX = (path, d) => {
  const p = Array.isArray(path) && path.length >= 2 ? path : [[0, .5], [1, .5]];
  for (let i = 0; i < p.length - 1; i++) {
    const [d0, x0] = p[i], [d1, x1] = p[i + 1];
    if (d <= d1 || i === p.length - 2) { const t = Math.max(0, Math.min(1, (d - d0) / ((d1 - d0) || 1))); return x0 + (x1 - x0) * t; }
  }
  return p[p.length - 1][1];
};

// holeContext(h, d, x) — which side of the fairway a ball at (d,x) sits on, and
// whether trees on that side block the line forward.
export function holeContext(h, d, x) {
  const cx = centerX(h && h.path, d);
  const dx = x - cx;                                  // + = right of center, − = left
  const side = dx < -0.09 ? "left" : dx > 0.09 ? "right" : "center";
  const off = Math.abs(dx) > 0.14;                    // meaningfully off the short grass
  let blocked = false;
  const haz = Array.isArray(h && h.hazards) ? h.hazards : [];
  if (off) {
    const sd = side === "left" ? "L" : side === "right" ? "R" : null;
    blocked = haz.some(z => z.type === "trees" && z.side === sd && (z.from ?? 0) <= d + 0.03 && (z.to ?? 1) >= d - 0.03);
  }
  return { side, blocked, off };
}

// lieAt(h, d, x) — the LIE a ball at (d,x) sits in, read from structured hazards.
export function lieAt(h, d, x) {
  const { side, off } = holeContext(h, d, x);
  const haz = Array.isArray(h && h.hazards) ? h.hazards : [];
  const sd = side === "left" ? "L" : side === "right" ? "R" : null;
  const covers = type => haz.some(z => {
    if (z.type !== type) return false;
    if (Array.isArray(z.pool)) {
      const [d0, d1, x0, x1] = z.pool;
      return d >= Math.min(d0, d1) && d <= Math.max(d0, d1) && x >= Math.min(x0, x1) && x <= Math.max(x0, x1);
    }
    return z.side === sd && (z.from ?? 0) <= d && (z.to ?? 1) >= d;
  });
  if (off && covers("trees")) return { lie: "TREES", label: "Recovery" };
  if (covers("sand")) return { lie: "FBUNK", label: "Bunker" };
  if (off) return { lie: "ROUGH", label: "Rough" };
  return { lie: "FW", label: "Fairway" };
}

// The raw ground type at a spot, ignoring the "off the fairway?" gate — used by the
// exposure sampler so a pool of water/sand in the middle of the corridor still counts.
export function groundAt(h, d, x) {
  const haz = Array.isArray(h && h.hazards) ? h.hazards : [];
  const cx = centerX(h && h.path, d);
  const side = x < cx - 0.09 ? "left" : x > cx + 0.09 ? "right" : "center";
  const sd = side === "left" ? "L" : side === "right" ? "R" : null;
  const off = Math.abs(x - cx) > 0.14;
  const hit = type => haz.some(z => {
    if (z.type !== type) return false;
    if (Array.isArray(z.pool)) {
      const [d0, d1, x0, x1] = z.pool;
      return d >= Math.min(d0, d1) && d <= Math.max(d0, d1) && x >= Math.min(x0, x1) && x <= Math.max(x0, x1);
    }
    return z.side === sd && (z.from ?? 0) <= d && (z.to ?? 1) >= d;
  });
  if (hit("water")) return "water";
  if (hit("sand")) return "sand";
  if (off && hit("trees")) return "trees";
  if (off) return "rough";
  return "fairway";
}

const clamp01 = v => Math.max(0, Math.min(1, v));

/**
 * exposure(h, d, x, sdD, sdX) -> { fairway, rough, sand, trees, water, blocked }
 * Sample a small dispersion grid centred on the intended landing (d,x) and read
 * what fraction of that scatter finds each ground type. sdD / sdX are the shot's
 * normalized dispersion (fraction of hole length / width). This is how a candidate
 * play "sees" the hazards it flirts with — the honest cost of an aggressive line.
 */
export function exposure(h, d, x, sdD = 0.05, sdX = 0.06) {
  const buckets = { fairway: 0, rough: 0, sand: 0, trees: 0, water: 0 };
  // 5×5 grid at ±1.4σ, weighted by a separable Gaussian — cheap and stable.
  const steps = [-1.4, -0.7, 0, 0.7, 1.4];
  const gw = z => Math.exp(-0.5 * z * z);
  let total = 0, blockedW = 0;
  steps.forEach(zd => steps.forEach(zx => {
    const w = gw(zd) * gw(zx);
    const dd = clamp01(d + zd * sdD), xx = clamp01(x + zx * sdX);
    const g = groundAt(h, dd, xx);
    buckets[g] += w; total += w;
    if (g === "trees") blockedW += w;
  }));
  const norm = k => total ? +(buckets[k] / total).toFixed(3) : 0;
  return {
    fairway: norm("fairway"), rough: norm("rough"), sand: norm("sand"),
    trees: norm("trees"), water: norm("water"),
    blocked: total ? +(blockedW / total).toFixed(3) : 0,
  };
}

// remainingYards(h, d) — yards from a spot at fractional d to the green.
export function remainingYards(h, d) {
  const y = (h && h.y) || 0;
  return Math.max(0, Math.round((1 - d) * y));
}

// dAfterCarry(h, dFrom, carryYds) — where a carry of `carryYds` from dFrom lands (d).
export function dAfterCarry(h, dFrom, carryYds) {
  const y = (h && h.y) || 1;
  return clamp01(dFrom + carryYds / y);
}
