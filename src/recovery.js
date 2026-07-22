/*
 * recovery.js — Recovery Mode & the expected-value engine.
 *
 * When the lie makes a normal approach unrealistic (trees, straw, deep rough,
 * fairway bunker…), the objective changes from "reach the green" to "play the
 * shot with the lowest expected strokes to the hole." This module scores three
 * recovery options — safe punch-out, strategic lay-up to the player's best
 * number, and the hero shot — by expected value and recommends the best one.
 *
 * Pure and unit-testable: the UI hands in the player's bag (carry + reliability)
 * and favorite wedge number; nothing here touches React or storage.
 */

// Lies that flip the app into Recovery Mode.
export const TROUBLE_LIES = { TREES: 1, DEEP: 1, SAND: 1, FBUNK: 1, PINE: 1, HARD: 1 };
export function isRecoveryLie(lie) { return !!TROUBLE_LIES[lie]; }

// Baseline expected strokes to hole from a CLEAN lie at a given distance (yards).
// Amateur/bogey-golfer calibration — the shape matters more than the decimals:
// closer is fewer strokes, but there's diminishing return inside a wedge.
const ES_TABLE = [[0,2.0],[20,2.35],[40,2.5],[60,2.62],[80,2.72],[100,2.82],
  [120,2.92],[140,3.04],[160,3.18],[180,3.34],[200,3.52],[230,3.78],[260,4.05]];
function baseES(d) {
  if (d <= 0) return 2.0;
  for (let i = 0; i < ES_TABLE.length - 1; i++) {
    const [d0, e0] = ES_TABLE[i], [d1, e1] = ES_TABLE[i + 1];
    if (d <= d1) return e0 + (e1 - e0) * (d - d0) / (d1 - d0);
  }
  return 4.05 + (d - 260) * 0.012;
}
// Extra strokes the lie costs (severity of trouble).
const LIE_PENALTY = { FW: 0, TEE: 0, FIRST: 0.1, ROUGH: 0.25, DEEP: 0.6, SAND: 0.4, FBUNK: 0.4, TREES: 0.95, PINE: 0.4, HARD: 0.35 };
export function expectedStrokes(d, lie) { return +(baseES(Math.max(0, d)) + (LIE_PENALTY[lie] || 0)).toFixed(2); }

// How far the player can realistically advance the ball FORWARD from a lie.
const MAX_ADVANCE = { TREES: 95, DEEP: 120, SAND: 150, FBUNK: 165, PINE: 150, HARD: 175 };
// Base chance a hero (go-for-it) shot comes off, by lie.
const HERO_BASE = { TREES: 0.14, DEEP: 0.16, SAND: 0.45, FBUNK: 0.42, PINE: 0.3, HARD: 0.4 };

const clamp = (lo, hi, v) => Math.max(lo, Math.min(hi, v));

/**
 * recoveryPlan(rem, lie, ctx) -> { mode, objective, options[], best, hero }
 * ctx = { bag:[{k,carry,rel}], wedgeDist }  (rel is 0-100 club confidence)
 * options are ranked by expected value (lower = better); each carries a reason.
 */
export function recoveryPlan(rem, lie, ctx) {
  const bag = (ctx.bag || []).filter(c => c.carry > 0).slice().sort((a, b) => a.carry - b.carry);
  const wedge = ctx.wedgeDist || 100;
  const relOf = k => { const c = bag.find(x => x.k === k); return c ? c.rel : 60; };
  const mostReliable = pool => pool.slice().sort((a, b) => b.rel - a.rel)[0];
  // Location context (from the ball placed on the map): which side, and blocked?
  const side = ctx.side || null;                    // "left" | "right" | "center"
  const blocked = !!ctx.blocked;                    // trees/obstruction on the line
  const escapeDir = side === "right" ? "left" : side === "left" ? "right" : "the open side";
  // Blocked view means you can only chip sideways back into play — no forward layup.
  const maxAdv = blocked ? 55 : (MAX_ADVANCE[lie] || 130);
  const opts = [];

  // ── Option 1: Safe punch-out — steadiest club, back to the short grass ──
  const punchPool = bag.filter(c => c.carry >= 105 && c.carry <= 165);
  const pClub = mostReliable(punchPool.length ? punchPool : bag) || bag[bag.length - 1];
  if (pClub) {
    const adv = clamp(20, maxAdv, Math.round(pClub.carry * 0.6));   // low punch ≈ 60% carry
    const leaves = Math.max(8, rem - adv);
    const ev = +(1 + 0.9 * expectedStrokes(leaves, "FW") + 0.1 * expectedStrokes(leaves, "ROUGH")).toFixed(2);
    opts.push({ kind: "punch", label: blocked ? `Chip out ${escapeDir}` : `Punch out ${escapeDir}`, club: pClub.k, leaves, ev,
      reason: `Steadiest club, ${escapeDir} into the open — ${leaves} left from a clean lie.` });
  }

  // ── Option 2: Strategic lay-up — leave your best scoring number ──
  const needed = rem - wedge;
  if (!blocked && needed >= 30 && needed <= maxAdv) {
    const lClub = mostReliable(bag.filter(c => c.carry >= needed - 8 && c.carry <= needed + 25)) ||
                  bag.find(c => c.carry >= needed) || bag[bag.length - 1];
    if (lClub) {
      const ev = +(1 + expectedStrokes(wedge, "FW")).toFixed(2);
      opts.push({ kind: "layup", label: `Lay up to ${wedge}`, club: lClub.k, leaves: wedge, ev,
        reason: `Advance to your money number — you score best from about ${wedge}.` });
    }
  }

  // ── Option 3: Hero shot — go for it, if there's a window ──
  const reachClub = bag.find(c => c.carry >= rem - 6);
  const heroClub = reachClub || bag[bag.length - 1];
  let hero = null;
  if (heroClub) {
    const confF = clamp(0.35, 1, relOf(heroClub.k) / 100 + 0.15);
    const clearF = lie === "TREES" ? 0.55 : lie === "PINE" ? 0.8 : 1;   // blocked view hurts
    const p = clamp(0.04, 0.9, (HERO_BASE[lie] || 0.3) * confF * clearF * (reachClub ? 1 : 0.7));
    // success → near the green; failure → still in trouble, worse off
    const good = expectedStrokes(reachClub ? 12 : Math.max(8, rem - heroClub.carry), reachClub ? "FW" : lie);
    const bad = expectedStrokes(Math.round(rem * 0.7), "TREES") + 0.3;
    const ev = +(1 + p * good + (1 - p) * bad).toFixed(2);
    hero = { kind: "hero", label: reachClub ? "Go for it" : "Take it on", club: heroClub.k, leaves: reachClub ? 0 : Math.max(8, rem - heroClub.carry),
      prob: Math.round(p * 100), ev, reason: `Only ~${Math.round(p * 100)}% comes off from here — high risk.` };
    opts.push(hero);
  }

  opts.sort((a, b) => a.ev - b.ev);
  const best = opts[0] || null;
  // Name the objective FIRST — the plain-English goal for this exact spot, using
  // the location context (side/blocked) when we have it, distance when we don't.
  const sideNote = blocked ? ` — you're blocked ${side === "center" ? "" : side + " "}by trees`
    : side && side !== "center" ? ` — ${side} of the fairway` : "";
  let objective;
  if (blocked) objective = "Get Back in Position";
  else if (lie === "SAND" || lie === "FBUNK") objective = "Escape the Sand";
  else if (rem <= 40) objective = "Get It Out and Up";
  else if (best && best.kind === "layup") objective = `Attack from ${wedge} Yards`;
  else if (best && best.kind === "hero") objective = "Take the Hero Line";
  else objective = "Advance Safely";
  return { mode: "recovery", objective, sideNote, side, blocked, options: opts, best, hero };
}
