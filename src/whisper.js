/*
 * whisper.js — the caddie's voice.
 *
 * Pure, side-effect-free translation from the engine's real numbers into plain
 * human sentences. The UI computes a `state` from the live engine/stats and hands
 * it here; this file never touches React, storage, or the DOM, so the voice can be
 * unit-tested in isolation and stays consistent everywhere.
 *
 * Structure of a whisper:  CLUB (2 words) -> WHY (one sentence, their data)
 *                          -> TARGET + FEEL (one sentence, the player's own words).
 * Max ~35 words. Warm, confident, brief. Never prints a raw stat.
 */

// ---- club name in human words ---------------------------------------------
export function humanClub(fam, chip) {
  if (chip === "CHIP") return "Chip";
  if (fam === "52" || (chip && chip.startsWith("52"))) {
    if (chip === "52½") return "52, half";
    if (chip === "52¾") return "52, three-quarter";
    if (chip === "52FS") return "52, full";
    return "52 wedge";
  }
  const named = { Dr: "Driver", PW: "Pitching wedge", GW: "Gap wedge", SW: "Sand wedge", LW: "Lob wedge" };
  if (named[fam]) return named[fam];
  const m = String(fam || "").match(/^(\d{1,2})([iwh])$/i);
  if (m) return `${m[1]}-${ {i:"iron", w:"wood", h:"hybrid"}[m[2].toLowerCase()] }`;
  return fam || "—";
}

// short spoken reference to the club inside a sentence ("your 7", "the wedge")
function shortRef(fam) {
  if (fam === "52") return "wedge";
  if (fam === "Dr") return "driver";
  const m = String(fam || "").match(/^(\d{1,2})[iwh]$/i);
  return m ? `${m[1]}` : "club";
}

// ---- the WHY line: one sentence, drawn from this player's data -------------
// Priority order matters — the most decision-relevant truth wins.
function whyLine(s) {
  const ref = shortRef(s.fam);
  if (s.adj) // live recalibration: club has been carrying short today
    return `you've been coming up short with it, so we're playing it at ${s.eff} today`;
  if (s.shaky || (s.stat && s.stat.sd >= 12))
    return `your ${ref} is spraying a bit lately — smooth pass, favor the fat side`;
  if (s.cold)
    return `it hasn't quite shown up today, so stay smooth and commit`;
  if (s.hot || (s.conf != null && s.conf >= 85))
    return `this is your club right now — trust it`;
  if (s.stat && Math.abs(s.stat.avg) <= 4 && s.stat.n >= 4)
    return `your ${ref} has been dead-on today`;
  if (s.stat && s.stat.avg <= -6)
    return `you've been leaking a bit short with it — swing it easy, not hard`;
  return `it's the right number for the ${humanClub(s.fam, s.chip).toLowerCase()}`;
}

// ---- the aim half of the target line: hazards first, then the player's miss -
function aimPhrase(s) {
  const h = s.hole || {};
  if (h.dzL === "water") return "anything left is wet — favor center-right and we're happy";
  if (h.dzR === "water") return "anything right is wet — favor center-left and we're happy";
  if (s.side && s.side.dir === "R" && s.side.pct >= 60) return "favor the left edge — your miss lives right";
  if (s.side && s.side.dir === "L" && s.side.pct >= 60) return "favor the right edge — your miss lives left";
  if (h.favor) return `favor the ${h.favor} — that's the line the hole gives you`;
  if (s.shaky) return "aim at the fat side and give yourself room";
  if (h.dzL) return `keep it away from the ${h.dzL} left — middle is plenty`;
  if (h.dzR) return `keep it away from the ${h.dzR} right — middle is plenty`;
  return "middle of the green, nothing cute";
}

// A saved "feel" is the player's own swing cue. Fall back to a quiet universal one.
function feelPhrase(s) {
  const f = (s.feel || "").trim();
  if (f) return f.replace(/[.]+$/, "");
  return "smooth and committed";
}

/**
 * whisper(state) -> { club, lines: string[], words }
 * `lines` is 2 short sentences (WHY, then TARGET+FEEL) unless it's a scoring shot.
 */
export function whisper(s) {
  const club = humanClub(s.fam, s.chip);

  // Inside 35: the game changes to conversion language, not a full-swing club call.
  if (s.i35) {
    return {
      club: s.chip === "CHIP" ? "Chip it" : club,
      lines: ["One look, then commit.", "On the green first try — two putts is the miss. Nothing cute."],
      words: 14,
    };
  }

  // Can't reach the target with the longest club: this is a lay-up, not a green shot.
  // Say so plainly and give the number we'll leave — never pretend it reaches the green.
  if (s.reach === false) {
    const why = s.shaky ? "that's more than you carry — and this one's been wild, so no hero swing"
              : s.leaves >= 190 ? "that's well past what you carry — no sense forcing it"
              : "you can't quite get home from here, and that's fine";
    let target = s.shaky
      ? `Aim at the widest part and just advance it — about ${s.leaves} left.`
      : `Advance it smooth and center — leaves about ${s.leaves}. ${cap(feelPhrase(s))}.`;
    let lines = [cap(why) + ".", target];
    if (wordCount(lines) > 35) { target = `Advance it — about ${s.leaves} left.`; lines = [cap(why) + ".", target]; }
    return { club, lines, words: wordCount(lines) };
  }

  const why = whyLine(s);
  let target = `${cap(aimPhrase(s))}. ${cap(feelPhrase(s))}.`;
  let lines = [cap(why) + ".", target];

  // Word budget ~35: if over, drop the feel clause first.
  if (wordCount(lines) > 35) {
    target = `${cap(aimPhrase(s))}.`;
    lines = [cap(why) + ".", target];
  }
  return { club, lines, words: wordCount(lines) };
}

// One-line whisper for stepping to a tee (shown before the first swing of a hole).
export function teeWhisper(hole, yards) {
  const y = yards || (hole && hole.y) || null;
  const hz = hole && hole.hz ? hole.hz.toLowerCase() : "";
  const favor = hole && hole.favor;
  let tail = "Fairway finder — smooth and center.";
  if (favor) tail = `Favor the ${favor} and let the hole's shape work.`;
  else if (/water|creek|pond|lake/.test(hz)) tail = "Trouble's in play — take the safe line, not the hero one.";
  else if (/\bob\b|out of bounds/.test(hz)) tail = "OB lurking — aim at the fat side and breathe.";
  else if (/dogleg|bend/.test(hz)) tail = "Position over power — set up the next one.";
  return y ? `${y} to the middle. ${tail}` : tail;
}

// The putting whisper.
export function puttWhisper(putts) {
  if (putts === 0) return "Back of the cup. Two putts wins here.";
  if (putts === 1) return "This one to save it — smooth pace, back of the cup.";
  return "Just get it there. Move on clean.";
}

// A gentle bench prompt when a club has gone cold (Yes/No handled by the UI).
export function benchWhisper(fam) {
  return `Your ${shortRef(fam)} hasn't shown up today. Want me to route around it?`;
}

// ===================== CLUB CONFIDENCE ENGINE =====================
// Judges a club's current form from OUTCOMES (where the ball ended + direction),
// not from a stock distance the on-course flow can't capture. This is the fix for
// hot/cold: a 3-wood that keeps ending in the rough cools even though every one of
// those shots was hit from a bad lie (which the old clean-lie stat filter excluded).
const TROUBLE = new Set(["rough", "deep", "bunker", "trees", "water"]);

// 0..1 quality of a single shot for the club that hit it. null = not a struck shot.
export function outcomeScore(s) {
  if (!s || s.pen) return null;
  if (s.g || s.end === "green") return 1;
  if (s.end === "fairway") return 0.85;
  if (s.end === "first") return 0.65;
  if (s.end === "rough") return 0.4;
  if (s.end === "deep") return 0.25;
  if (s.end === "bunker") return 0.2;
  if (s.end === "trees") return 0.15;
  if (s.end === "water") return 0;
  // No ending lie recorded: fall back to distance deviation if we have it.
  if (s.exp != null && s.gain != null) { const e = s.gain - s.exp; return e <= -15 ? 0.25 : Math.abs(e) <= 8 ? 0.85 : 0.55; }
  return 0.6;
}
function isPoor(s) {
  if (!s || s.pen) return false;
  if (s.end && TROUBLE.has(s.end)) return true;
  if (s.g || s.end === "green" || s.end === "fairway") return false;
  if (s.exp != null && s.gain != null) return (s.gain - s.exp) <= -15;
  return false;
}
function describeShot(s) {
  if (s.pen) return "penalty";
  const dir = s.dir === "L" ? "left" : s.dir === "R" ? "right"
    : (s.exp != null && s.gain != null && s.gain < s.exp - 6) ? "short"
    : (s.exp != null && s.gain != null && s.gain > s.exp + 6) ? "long" : "on line";
  const end = s.g ? "green" : (s.end || "");
  return end ? `${dir}, ${end}` : dir;
}
const clampN = (lo, hi, v) => Math.max(lo, Math.min(hi, v));

/**
 * clubConfidence(clubShots, stat) -> { score 0-100, state, streak, reasons[], n }
 * clubShots: this club's shots, chronological (oldest→newest). stat: the practice
 * clubStats entry (or null). Recent shots and tournament shots are weighted heavier.
 */
export function clubConfidence(clubShots, stat) {
  const mine = (clubShots || []).filter(s => s && !s.pen);
  // Base from practice dispersion — a supplement, not the driver, once rounds exist.
  let base = 58;
  if (stat && stat.sd != null) base = clampN(30, 92, Math.round(96 - stat.sd * 3));
  if (!mine.length) return { score: base, state: base < 40 ? "cold" : base >= 70 ? "hot" : "steady", streak: 0, reasons: [], n: 0 };

  // Recency- and tournament-weighted average outcome (on-course performance).
  const N = mine.length; let wsum = 0, w = 0;
  mine.forEach((s, i) => {
    const q = outcomeScore(s); if (q == null) return;
    const rw = Math.pow(0.8, N - 1 - i);   // recent shots dominate
    const tw = s.tourn ? 1.6 : 1;          // tournament shots weigh more
    wsum += q * rw * tw; w += rw * tw;
  });
  const onCourse = w ? (wsum / w) * 100 : null;
  let score = onCourse == null ? base : Math.round(base * 0.3 + onCourse * 0.7);   // on-course primary

  // Consecutive poor outcomes -> cool hard (the 2-3-in-a-row failure pattern).
  let streak = 0;
  for (let i = mine.length - 1; i >= 0; i--) { if (isPoor(mine[i])) streak++; else break; }
  if (streak >= 2) score -= Math.min(48, (streak - 1) * 22 + 12);
  // Consecutive good outcomes -> warm back up (never permanently cold).
  let good = 0;
  for (let i = mine.length - 1; i >= 0; i--) { const q = outcomeScore(mine[i]); if (q != null && q >= 0.8) good++; else break; }
  if (good >= 2) score += Math.min(16, good * 5);

  score = clampN(0, 100, Math.round(score));
  const state = score < 40 ? "cold" : score >= 70 ? "hot" : "steady";
  const reasons = mine.slice(-3).map(describeShot);
  return { score, state, streak, reasons, n: mine.length };
}

// ---- small helpers ---------------------------------------------------------
function cap(t) { t = String(t || ""); return t.charAt(0).toUpperCase() + t.slice(1); }
function wordCount(lines) { return lines.join(" ").trim().split(/\s+/).filter(Boolean).length; }
