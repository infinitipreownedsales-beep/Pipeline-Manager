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
  let tail = "Fairway finder — smooth and center.";
  if (/water|creek|pond|lake/.test(hz)) tail = "Trouble's in play — take the safe line, not the hero one.";
  else if (/ob|out of bounds/.test(hz)) tail = "OB lurking — aim at the fat side and breathe.";
  else if (/dogleg/.test(hz)) tail = "Position over power — set up the next one.";
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

// ---- small helpers ---------------------------------------------------------
function cap(t) { t = String(t || ""); return t.charAt(0).toUpperCase() + t.slice(1); }
function wordCount(lines) { return lines.join(" ").trim().split(/\s+/).filter(Boolean).length; }
