/*
 * player.js — the Player Model data contract.
 *
 * One normalized, per-club view of the golfer that keeps PERMANENT ABILITY and
 * TODAY'S FORM separate, and exposes the blend the decision engine consumes.
 *
 *   dailyProfile(profile, shots, opts) -> { [fam]: clubModel }
 *
 * It composes the signals that already exist rather than inventing new math:
 *   - permanent ability  ← profile.carries / profile.clubStats (only ever set by import)
 *   - today's form       ← clubConfidence over this round's shots (recency + tournament
 *                          weighted, streak-capped — one bad shot can't rewrite a club)
 *   - warm-up (optional)  ← opts.warmup seeds today's starting point before Hole 1;
 *                          fully inert when absent.
 *
 * Pure and side-effect free: no React, no storage. The blended `reliability` is
 * defined to equal the app's prior reliability() exactly, so wiring it in changes
 * no behavior — it just gives every consumer one contract to read from.
 */
import { clubConfidence } from "./whisper.js";

// club family key (mirrors CaddieOS.famOf; kept tiny + local so this stays pure).
const famOf = c => {
  c = String(c || "");
  if (c.includes("52") || c.includes("½") || c.includes("¾")) return "52";
  if (c.includes("chip") || c.includes("CHIP") || c.includes("bump")) return "chip";
  return c.split(" ")[0];
};
const csKey = fam => (fam === "52" ? "52m" : fam);          // clubStats key for the 52° wedge
const clamp = (lo, hi, v) => Math.max(lo, Math.min(hi, v));

// A club must PROVE a one-way miss before it costs reliability (same rule as the app).
const SIDE_PROVEN = 5;
export function sideProven(stat) {
  return !!(stat && stat.side && (stat.side.n == null || stat.side.n >= SIDE_PROVEN));
}
// Reliability = today's outcome confidence, docked for a PROVEN heavy one-way miss.
// This is byte-for-byte the old reliability() definition, centralized.
export function reliabilityFrom(confidenceScore, stat) {
  const sidePct = sideProven(stat) ? stat.side.pct : null;
  const docked = confidenceScore - (sidePct != null && sidePct >= 72 ? 8 : 0);
  return clamp(0, 100, Math.round(docked));
}

/**
 * dailyProfile(profile, shots, opts?)
 *   profile : the persisted player profile ({carries, clubStats, w52, ...})
 *   shots   : this round's logged shots (rounds+live), chronological oldest→newest
 *   opts.warmup : optional { fam: [warmUpShot, ...] } — pre-round range shots (same
 *                 shape as logged shots) that seed today's starting form. Absent = no-op.
 *   opts.fams   : optional extra families to include (so clubs with no shots yet appear).
 *   opts.adj    : optional { fam: yds } — today's carry calibration (from live shots
 *                 coming up short/long). Kept SEPARATE: longTerm.carry is untouched,
 *                 today.carry / effCarry fold it in. Absent = no delta.
 *   opts.benched: optional [fam] — clubs benched for today. They stay in the model
 *                 (with benched:true + why) but are excluded from competitive execution.
 *
 * Returns { [fam]: {
 *   carry, sd,                       // permanent effective carry + dispersion
 *   effCarry,                        // TODAY's carry = permanent + today's calibration (adj)
 *   confidence, reliability, state, streak, n,   // TODAY's blended form
 *   benched, benchReason,            // benched-for-today flag (club STAYS in the model)
 *   longTerm: { carry, sd, n },      // permanent ability, isolated (never moved by a round)
 *   today:    { confidence, n, carry, adj },     // this round only, isolated
 *   warmup:   { n } | null,          // warm-up seed applied, if any
 * } }
 */
export function dailyProfile(profile, shots = [], opts = {}) {
  const carries = (profile && profile.carries) || {};
  const clubStats = (profile && profile.clubStats) || {};
  const warmup = opts.warmup || {};
  const adj = opts.adj || {};                        // today's carry calibration, kept separate
  const benched = new Set(opts.benched || []);       // clubs sat down for today (still modeled)

  // Every family we might be asked about: carries + the 52° wedge + anything hit +
  // warm-up + benched (they must NOT vanish) + caller extras.
  const fams = new Set(["52", ...Object.keys(carries), ...(opts.fams || [])]);
  (shots || []).forEach(s => { if (s && !s.pen) fams.add(famOf(s.c)); });
  Object.keys(warmup).forEach(f => fams.add(f));
  benched.forEach(f => fams.add(f));

  const model = {};
  fams.forEach(fam => {
    if (fam === "chip") return;
    const stat = clubStats[csKey(fam)] || null;
    const today = (shots || []).filter(s => s && famOf(s.c) === fam);
    const warm = warmup[fam] || [];                 // warm-up shots are the OLDEST (recency-weighted lower)
    const combined = warm.length ? [...warm, ...today] : today;

    const cc = clubConfidence(combined, stat);        // blended today's form (incl. warm-up seed)
    const todayOnly = warm.length ? clubConfidence(today, stat) : cc;
    const carry = carries[fam] != null ? carries[fam] : (stat ? stat.carry : null);
    const sd = stat ? stat.sd : null;
    // Today's carry calibration folds in HERE only — permanent ability is untouched.
    const delta = adj[fam] || 0;
    const effCarry = carry != null ? carry + delta : null;
    const isBenched = benched.has(fam);

    model[fam] = {
      carry, sd, effCarry,
      confidence: cc.score,
      reliability: reliabilityFrom(cc.score, stat),
      state: cc.state, streak: cc.streak, n: cc.n,
      benched: isBenched,
      benchReason: isBenched ? (cc.state === "cold" ? "cold today" : "benched for today") : null,
      longTerm: { carry, sd, n: stat ? stat.n : 0 },
      today: { confidence: todayOnly.score, n: today.length, carry: effCarry, adj: delta },
      warmup: warm.length ? { n: warm.length } : null,
    };
  });
  return model;
}
