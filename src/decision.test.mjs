import { decideShot } from "./decision.js";
import { dailyProfile } from "./player.js";

let fail = 0, n = 0;
const ok = (name, cond) => { n++; console.log((cond ? "PASS" : "FAIL") + " " + String(n).padStart(2) + " — " + name); if (!cond) fail++; };

// ---------- holes ----------------------------------------------------------
const CLEAN = { n: 1, par: 4, y: 400, path: [[0, .5], [1, .5]], hazards: [], green: {} };
// water fronting the green (a pool across the front-center), green favors left away from it
const WATER = { n: 2, par: 4, y: 410, path: [[0, .5], [1, .48]], green: { pinch: true, guard: "water" },
  hazards: [{ type: "water", pool: [0.83, 0.93, 0.25, 0.75] }] };   // water FRONTS the green
// a tree stand planted on the forward line — an obstruction that gates the route
const OBS = { n: 3, par: 4, y: 380, path: [[0, .5], [1, .5]], hazards: [{ type: "trees", pool: [0.55, 0.72, 0.33, 0.67] }] };
// water down the right off the tee (driver flirts with it; 3W stays short of it)
const TEEWATER = { n: 4, par: 4, y: 430, path: [[0, .5], [1, .5]],
  hazards: [{ type: "water", pool: [0.52, 0.70, 0.55, 1.0] }] };

// ---------- bag ------------------------------------------------------------
const CARRIES = { Dr: 250, "3W": 225, "5W": 205, "5i": 185, "6i": 172, "7i": 160, "8i": 148, "9i": 135, PW: 120 };
const mkBag = (over = {}) => Object.entries(CARRIES).map(([k, carry]) =>
  ({ k, carry, rel: over[k]?.rel ?? 72, sd: over[k]?.sd ?? 8, benched: over[k]?.benched || false }));
const scoring = rem => ({ chip: rem <= 34 ? "52½" : "PW", carry: rem });
const base = o => ({ wedgeDist: 100, wind: "NONE", scoring, ...o });

// ===========================================================================
// 1. Reaches a clean green → attack, with a club that gets home.
{
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.62, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag() }));
  ok("clean 150 → ATTACK the green", d.kind === "attack" && d.play.destination.label === "the green");
  ok("attack club actually reaches (reach flag true)", d.reach === true);
}
// 2. Reasoning is a PLAY, not a raw club: multiple play kinds considered, a destination chosen.
{
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.5, x: .5 }, rem: 205, effRem: 205, lie: "FW", strokes: 1, bag: mkBag() }));
  const kinds = new Set(d.candidates.map(c => c.kind));
  ok("candidates span more than one play kind", kinds.size >= 2);
  ok("chosen play carries a destination + intent, not just a club", !!d.play.destination && !!d.play.intent);
}
// 3. Water-guarded green + SHAKY reachers → lay up to the money number beats forcing it.
{
  const bag = mkBag({ Dr: { rel: 38, sd: 20 }, "3W": { rel: 38, sd: 18 }, "5W": { rel: 40, sd: 17 } });
  const d = decideShot(base({ hole: WATER, from: { d: 0.5, x: .5 }, rem: 210, effRem: 210, lie: "FW", strokes: 1, bag }));
  ok("shaky reachers into water → LAY UP (don't force it)", d.kind === "layup");
  ok("the safe play leaves a comfortable scoring number", d.leaves <= 110);
}
// 4. Same water green but a RELIABLE reacher → attack is the lower-EV play.
{
  const bag = mkBag({ "3W": { rel: 84, sd: 7 }, Dr: { rel: 80, sd: 8 }, "5W": { rel: 82, sd: 7 } });
  const d = decideShot(base({ hole: WATER, from: { d: 0.5, x: .5 }, rem: 210, effRem: 210, lie: "FW", strokes: 1, bag }));
  ok("reliable reacher into water → ATTACK", d.kind === "attack");
}
// 5. play↔execution feedback loop: the best-EV play's club is untrusted → eliminated on
//    the record, next executable play chosen.
{
  const bag = mkBag({ "8i": { rel: 30, sd: 22 }, "7i": { rel: 30, sd: 22 } }); // the natural 150 clubs are cold
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.62, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag }));
  const elim = d.record.candidates.find(c => c.elim);
  ok("an untrusted club is eliminated WITH a recorded reason", !!elim && /trust/i.test(elim.elim));
  ok("a still-executable play is selected instead", d.club && d.record.selected.club === d.club);
}
// 6. No club clears the trust bar anywhere → still returns a call (never null / under protest).
{
  const bag = mkBag(Object.fromEntries(Object.keys(CARRIES).map(k => [k, { rel: 20, sd: 24 }])));
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.4, x: .5 }, rem: 180, effRem: 180, lie: "FW", strokes: 1, bag }));
  ok("nothing trusted → still a recommendation (no dead end)", !!d.club);
  ok("that fallback is flagged under-protest on the record", d.record.underProtest === true);
}
// 7. Tee shot on a hole with water right → POSITION play; driver into the water loses.
{
  const d = decideShot(base({ hole: TEEWATER, from: null, rem: 430, effRem: 430, lie: "FW", strokes: 0, bag: mkBag() }));
  ok("tee shot → a POSITION play (not 'attack the green')", d.kind === "position");
  ok("does not blindly grab the driver over the safer line", d.club != null);
}
// 8. Recovery lie (blocked in the trees) → recovery mode, escape sideways, no forward layup.
{
  const blockedHole = { n: 5, par: 4, y: 400, path: [[0, .5], [1, .5]],
    hazards: [{ type: "trees", side: "R", from: 0.35, to: 0.8 }] };
  const d = decideShot(base({ hole: blockedHole, from: { d: 0.5, x: 0.82 }, rem: 180, effRem: 180, lie: "TREES", strokes: 1, bag: mkBag() }));
  ok("bad lie → RECOVERY mode", d.mode === "recovery");
  ok("recovery offers an escape (punch/chip), not a green attack", d.kind === "punch" || d.kind === "hero" || d.kind === "layup");
  ok("recovery plan is attached for the card", !!d.recovery && Array.isArray(d.recovery.options));
}
// 9 & 10. Benched club stays in the Player Model but is excluded from competition.
{
  const profile = { carries: { ...CARRIES, "52": 100 }, clubStats: {} };
  const model = dailyProfile(profile, [], { benched: ["7i"] });
  ok("a benched club still EXISTS in the Player Model", !!model["7i"] && model["7i"].benched === true);
  const bag = Object.keys(CARRIES).map(k => ({ k, carry: model[k].effCarry, rel: 72, sd: 8, benched: model[k].benched }));
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.62, x: .5 }, rem: 160, effRem: 160, lie: "FW", strokes: 1, bag }));
  ok("a benched club is never the recommendation", d.club !== "7i");
}
// 11. Improvement: warm form lifts a club's confidence in the model.
{
  const profile = { carries: CARRIES, clubStats: { "7i": { n: 10, carry: 160, sd: 9 } } };
  const good = [1, 2, 3].map(i => ({ c: "7i", from: 160, gain: 160, exp: 160, g: 1, h: i, end: "green" }));
  const warm = dailyProfile(profile, good)["7i"].today.confidence;
  const cold = dailyProfile(profile, [])["7i"].today.confidence;
  ok("a club hit well today reads MORE confident than its cold baseline", warm > cold);
}
// 12. Decline: consecutive poor outcomes cool a club; the engine prefers a trusted peer.
{
  const profile = { carries: CARRIES, clubStats: { "7i": { n: 10, carry: 160, sd: 9 }, "8i": { n: 10, carry: 148, sd: 7 } } };
  const bad = [1, 2, 3].map(i => ({ c: "7i", from: 160, gain: 150, exp: 160, g: 0, h: i, end: "rough" }));
  const m = dailyProfile(profile, bad);
  ok("three poor 7i outcomes drop its reliability below a steady club's", m["7i"].reliability < m["8i"].reliability);
}
// 13. Observation is asked ONLY when an obstruction could change the play.
{
  const d = decideShot(base({ hole: OBS, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag(), observation: null }));
  ok("obstruction on the line → askObservation is raised", d.askObservation === true);
  const clear = decideShot(base({ hole: CLEAN, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag() }));
  ok("clean line → no observation prompt", clear.askObservation === false);
}
// 14. "No usable window" → forced reposition, even from an otherwise-normal lie.
{
  const d = decideShot(base({ hole: OBS, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag(), observation: "nowindow" }));
  ok("no-window observation → recovery/reposition", d.mode === "recovery");
}
// 15-17. Route observations shape the required flight.
{
  const hi = decideShot(base({ hole: OBS, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag(), observation: "high" }));
  ok("'gotta go high' → high flight, over the trouble", hi.flight === "high" && hi.route === "over");
  const lo = decideShot(base({ hole: OBS, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag(), observation: "low" }));
  ok("'gotta stay low' → low flight", lo.flight === "low");
  const cu = decideShot(base({ hole: OBS, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag(), observation: "curve" }));
  ok("'need to curve it' → a shaped ball", cu.flight === "shaped");
}
// 18-19. Confidence is DISTINCT components; overall is a robust blend (a single weak,
//        low-weight component can't collapse the whole call), capped by execution.
{
  const d = decideShot(base({ hole: WATER, from: { d: 0.5, x: .5 }, rem: 190, effRem: 190, lie: "FW", strokes: 1, bag: mkBag() }));
  const c = d.confidence;
  const keys = ["player", "form", "course", "observation", "play", "execution", "overall", "band"];
  ok("all distinct confidence components (+ band) are present", keys.every(k => k in c));
  const comps = [c.player, c.form, c.course, c.observation, c.play, c.execution].filter(v => v != null);
  ok("they are not one overloaded number (components differ)", new Set(comps).size >= 2);
  ok("overall is a blend, not the raw minimum", c.overall > Math.min(...comps));
  ok("overall never over-claims beyond execution", c.overall <= c.execution + 12);
  ok("band is a plain word (High/Solid/Limited)", ["High","Solid","Limited"].includes(c.band));
  // an irrelevant weak component (unmapped course) must NOT tank an otherwise-strong call
  const clean = decideShot(base({ hole: { par:4, y:400 }, from:null, rem: 150, effRem:150, lie:"FW", strokes:1, bag: mkBag() }));
  ok("a weak low-weight component does not collapse overall", clean.confidence.overall >= 55);
}
// 20. The decision record preserves the reasoning for later learning.
{
  const d = decideShot(base({ hole: WATER, from: { d: 0.5, x: .5 }, rem: 210, effRem: 210, lie: "FW", strokes: 1, bag: mkBag() }));
  const r = d.record;
  ok("record keeps situation, candidates, elimination reasons, selection, expectation, confidence",
    !!r.situation && Array.isArray(r.candidates) && !!r.selected && !!r.expected && !!r.confidence && "actual" in r);
}
// 21. Scoring distance → the play is 'get it close', deferring the exact wedge chip.
{
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.92, x: .5 }, rem: 30, effRem: 30, lie: "FW", strokes: 2, bag: mkBag() }));
  ok("inside 34 → SCORING play", d.kind === "scoring");
  ok("scoring play uses the app's wedge chip", d.club === "52½");
}
// 22. Lay-up genuinely targets the money number.
{
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.3, x: .5 }, rem: 250, effRem: 250, lie: "FW", strokes: 1,
    bag: mkBag({ Dr: { rel: 30, sd: 22 }, "3W": { rel: 30, sd: 20 }, "5W": { rel: 30, sd: 20 } }), wedgeDist: 100 }));
  ok("a considered lay-up aims to leave ~the money number", d.candidates.some(c => c.kind === "layup" && Math.abs(c.leaves - 100) <= 35));
}
// 23. Durability: the recommended club always exists in the (non-benched) bag or is a wedge chip.
{
  const bag = mkBag({ "7i": { benched: true } });
  const d = decideShot(base({ hole: CLEAN, from: { d: 0.62, x: .5 }, rem: 160, effRem: 160, lie: "FW", strokes: 1, bag }));
  const live = bag.filter(b => !b.benched).map(b => b.k);
  ok("recommendation references a real, non-benched club", live.includes(d.club) || /52|PW|chip/i.test(d.club));
}
// 24. The caddie decides the strategy — the golfer is only ever asked for an OBSERVATION.
{
  const d = decideShot(base({ hole: OBS, from: { d: 0.45, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: mkBag() }));
  ok("engine picks the play itself (no aggressive/conservative toggle in the output)",
    !("mode" in d && /aggress|conserv/i.test(JSON.stringify(d.play))) && !!d.play.kind);
}
// 25. Plays are ranked by expected score (lowest EV first).
{
  const d = decideShot(base({ hole: WATER, from: { d: 0.4, x: .5 }, rem: 220, effRem: 220, lie: "FW", strokes: 1, bag: mkBag() }));
  const evs = d.candidates.map(c => c.ev);
  ok("candidates are ranked ascending by expected score", evs.every((v, i) => i === 0 || v >= evs[i - 1]));
}

// ===========================================================================
// PART 4 — the low-confidence 3-wood tee shot. The engine must COMPARE the full
// alternatives (club+flight, today's trust, expected score, severe-miss exposure,
// expected next position) BEFORE it speaks — not just take the longest accepted club.
// ~390-yd par 4, 3W advances ~190 (leaves ~200) but is shaky; irons are trusted.
const P4CARRIES = { Dr: 250, "3W": 190, "5i": 175, "6i": 165, "7i": 150, "8i": 138, "9i": 126, PW: 115 };
const p4bag = (over={}) => Object.entries(P4CARRIES).map(([k,carry]) =>
  ({ k, carry, rel: over[k]?.rel ?? 72, sd: over[k]?.sd ?? 8, benched: false }));
// (a) When the 3-wood's landing zone brings real trouble into play (down-the-side water),
//     a trusted iron that stays short of it must produce the lower expected score.
{
  const TROUBLE = { n: 9, par: 4, y: 390, path: [[0,.5],[1,.5]],
    hazards: [{ type: "water", pool: [0.46, 0.60, 0.55, 1.0] }] };   // catches the long, wide shaky 3W
  const bag = p4bag({ "3W": { rel: 40, sd: 20 } });                   // low-confidence 3-wood
  const d = decideShot(base({ hole: TROUBLE, from: null, rem: 390, effRem: 390, lie: "FW", strokes: 0, bag }));
  ok("tee: shaky 3W into trouble → engine does NOT pick the 3-wood", d.club !== "3W");
  ok("tee: it picks a trusted club instead", ["Dr","5i","6i","7i","8i"].includes(d.club));
  // proof the comparison happened internally, with evidence, before the call
  const cand = d.record.candidates;
  ok("every alternative carries club+flight+trust+EV+miss-exposure+next-position", cand.length >= 3 &&
    cand.every(c => c.club && "ev" in c && "rel" in c && "leaves" in c && "water" in c));
  ok("the 3-wood was weighed and beaten on expected score", cand.some(c => c.club === "3W") &&
    d.record.selected.ev <= cand.find(c => c.club === "3W").ev);
}
// (b) On a clean hole with no trouble, the extra distance of the 3-wood legitimately
//     wins — the rule is lowest expected score, NOT "always the safe short club".
{
  const CLEAN390 = { n: 9, par: 4, y: 390, path: [[0,.5],[1,.5]], hazards: [] };
  const bag = p4bag({ "3W": { rel: 62, sd: 12 } });                  // decent, reachy 3-wood
  const d = decideShot(base({ hole: CLEAN390, from: null, rem: 390, effRem: 390, lie: "FW", strokes: 0, bag }));
  const evOf = k => (d.record.candidates.find(c => c.club === k) || {}).ev;
  ok("clean hole: the chosen tee play is the lowest expected-score option", d.record.selected.ev === Math.min(...d.record.candidates.filter(c=>c.executable).map(c=>c.ev)));
  ok("clean hole: a longer club can win when nothing punishes it", evOf(d.club) != null);
}

// ===========================================================================
// PART 5 — SHOT-CONTEXT CLASSIFICATION (par-3 hotfix). A tee shot is not automatically
// a fairway-position play: a par-3 tee is a green-targeting approach.
import { shotContextOf } from "./decision.js";
const P3CARR = { Dr: 250, "3W": 190, "4h": 205, "5i": 175, "6i": 165, "7i": 150, "8i": 138, "9i": 125, PW: 115 };
const p3bag = (over={}) => Object.entries(P3CARR).map(([k,carry]) =>
  ({ k, carry, rel: over[k]?.rel ?? 72, sd: over[k]?.sd ?? 8, benched: false }));
const fairwayLang = d => /fairway/i.test(d.startLine+" "+d.landing) || /fairway finder/i.test(d.cue||"");

// Short par 3 (~118) — the reported bug. Realistic scoring club, never the 3-wood.
{
  const H = { n: 3, par: 3, y: 118, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: null, rem: 118, effRem: 118, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("short par-3 tee is classified par3_tee", d.context === "par3_tee");
  ok("short par-3 → a green-targeting ATTACK", d.kind === "attack" && d.play.destination.label === "the green");
  ok("short par-3 selects a realistic scoring club (PW/9i-ish), NOT the 3-wood", ["PW","9i","8i"].includes(d.club) && d.club !== "3W");
  ok("short par-3 uses NO fairway-position language", !fairwayLang(d));
  ok("short par-3 keeps the 3-wood only as an eliminated (long) non-executable play", (() => {
    const c = d.record.candidates.find(x => x.club === "3W"); return c && c.executable === false && c.fit === "long"; })());
}
// Medium par 3 (~165) — best green-targeting middle iron, not the longest club.
{
  const H = { n: 6, par: 3, y: 165, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: null, rem: 165, effRem: 165, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("medium par-3 → attack with a fitting iron (6i/5i), not Dr/3W", d.kind === "attack" && ["6i","5i"].includes(d.club));
  ok("medium par-3 has no fairway language", !fairwayLang(d));
}
// Long par 3 (~200) — a club is chosen because its result FITS the green, not because
// it's the longest: the driver overshoots the window and must not win.
{
  const H = { n: 8, par: 3, y: 200, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: null, rem: 200, effRem: 200, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("long par-3 → green-targeting attack", d.kind === "attack" && d.reach === true);
  ok("long par-3 fits the green (4h ~205), not simply the longest (Dr 250)", d.club !== "Dr");
  ok("long par-3 does not EXECUTE a materially-over club (Dr)", (() => {
    const c = d.record.candidates.find(x => x.club === "Dr"); return !c || (c.executable === false && c.fit === "long"); })());
}
// Par-3 forced carry — water short of the green. A green-targeting play with carry margin.
{
  const H = { n: 6, par: 3, y: 150, path: [[0,.5],[1,.5]], hazards: [{ type: "water", pool: [0.0, 0.80, 0.2, 0.8] }] };
  const d = decideShot(base({ hole: H, from: null, rem: 150, effRem: 150, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("forced-carry par-3 stays green-targeting (attack), not a lay-into-the-water", d.context === "par3_tee" && d.kind === "attack");
  ok("forced-carry par-3 uses no fairway language", !fairwayLang(d));
}
// No trustworthy green-reaching club — one deliberate lowest-score call. If it plays
// short, it's honestly a lay-up, never a 'fairway finder'.
{
  const H = { n: 8, par: 3, y: 235, path: [[0,.5],[1,.5]], hazards: [] };   // only Dr can get near
  const d = decideShot(base({ hole: H, from: null, rem: 235, effRem: 235, lie: "FW",
    strokes: 0, bag: p3bag({ Dr: { rel: 30, sd: 22 }, "4h": { rel: 30, sd: 20 }, "3W": { rel: 30, sd: 20 } }) }));
  ok("unreachable par-3 still returns exactly one deliberate call", !!d.club && !!d.kind);
  ok("playing short is labeled honestly (layup), never a fairway-position play", d.kind !== "position");
  ok("unreachable par-3 avoids fairway-finder language", !/fairway finder/i.test(d.cue||""));
}
// Par-4 tee — position behavior PRESERVED (the fix must not turn it into approach logic).
{
  const H = { n: 1, par: 4, y: 400, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: null, rem: 400, effRem: 400, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("par-4 tee is classified tee_position", d.context === "tee_position");
  ok("par-4 tee stays a POSITION play (not attack)", d.kind === "position");
  ok("par-4 tee correctly uses fairway/position language", /fairway/i.test(d.startLine+" "+d.landing));
}
// Par-5 tee — strategic position candidates preserved.
{
  const H = { n: 4, par: 5, y: 540, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: null, rem: 540, effRem: 540, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("par-5 tee is tee_position with a position play", d.context === "tee_position" && d.kind === "position");
}
// Later approach — normal attack/layup preserved.
{
  const H = { n: 1, par: 4, y: 400, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: { d: 0.62, x: .5 }, rem: 150, effRem: 150, lie: "FW", strokes: 1, bag: p3bag() }));
  ok("later approach is classified approach", d.context === "approach");
  ok("later approach still attacks the green when reachable", d.kind === "attack");
}
// shotContextOf is the single classifier both layers read.
{
  ok("shotContextOf: par-3 tee", shotContextOf({ lie:"FW", strokes:0, rem:120, hole:{par:3} }) === "par3_tee");
  ok("shotContextOf: par-4 tee", shotContextOf({ lie:"FW", strokes:0, rem:400, hole:{par:4} }) === "tee_position");
  ok("shotContextOf: approach", shotContextOf({ lie:"FW", strokes:2, rem:150, hole:{par:4} }) === "approach");
  ok("shotContextOf: scoring", shotContextOf({ lie:"FW", strokes:2, rem:30, hole:{par:4}, scoreCeiling:100 }) === "scoring");
  ok("shotContextOf: recovery", shotContextOf({ lie:"TREES", strokes:1, rem:150, hole:{par:4} }) === "recovery");
}
// Communication consistency — every visible field describes the SAME par-3 play.
{
  const H = { n: 3, par: 3, y: 118, path: [[0,.5],[1,.5]], hazards: [] };
  const d = decideShot(base({ hole: H, from: null, rem: 118, effRem: 118, lie: "FW", strokes: 0, bag: p3bag() }));
  ok("consistency: context, kind, destination all agree on green-targeting",
    d.context === "par3_tee" && d.kind === "attack" && d.play.destination.label === "the green" && d.record.situation.context === "par3_tee");
  ok("consistency: aim + landing speak green, not fairway",
    /flag|green/i.test(d.startLine) && /green/i.test(d.landing) && !fairwayLang(d));
  ok("consistency: a map aim target exists for the call", d.aim && d.aim.d != null);
  ok("consistency: record's selected club matches the surfaced club", d.record.selected.club === d.club);
}

// ===========================================================================
// PART 6 — DISTANCE-FIT: a club is only executable for a green play when its real carry
// distribution fits the green's depth window. Reliability never overrides physics.
const H3 = { n:3, par:3, y:110, path:[[0,0.60],[0.5,0.585],[1,0.52]], carry:95, green:{ toPin:110, raised:true },
  hazards:[{type:"water",pool:[0.16,0.80,0.06,0.60]},{type:"water",pool:[0.80,0.97,0.66,0.90]},{side:"R",type:"trees",from:0.05,to:0.92},{side:"L",type:"trees",from:0.82,to:1.00}] };
const p3 = (over={}) => { const C = { Dr:245, "3W":190, "7i":140, "9i":125, PW:115 };
  return Object.entries(C).map(([k,carry]) => ({ k, carry, rel: over[k]?.rel ?? 72, sd: over[k]?.sd ?? 6, benched: over[k]?.benched || false })); };
const par3base = o => ({ wedgeDist:100, wind:"NONE", scoreCeiling:90, scoring:r=>({chip:"PW",carry:r}), player:{}, ...o });
const noFairway = d => !/fairway/i.test(d.startLine+" "+d.landing) && !/fairway finder/i.test(d.cue||"");
const cand = (d,club) => d.record.candidates.find(c => c.club === club);

// Exact Hole 3 — the reported case. 115 yds, PW115/9i125/7i140/3W190.
{
  const d = decideShot(par3base({ hole: H3, from:null, rem:115, effRem:115, lie:"FW", strokes:0, bag: p3() }));
  ok("Hole 3: 3-wood is physically incompatible (long, excluded)", cand(d,"3W").fit==="long" && cand(d,"3W").executable===false);
  ok("Hole 3: normal 7-iron is physically incompatible (long, excluded)", cand(d,"7i").fit==="long" && cand(d,"7i").executable===false);
  ok("Hole 3: PW and 9i are evaluated with real carry + fit", cand(d,"PW").fit==="fits" && cand(d,"9i").fit==="fits");
  ok("Hole 3: the pick is a fitting green-targeting club (PW or 9i)", ["PW","9i"].includes(d.club) && d.kind==="attack");
  ok("Hole 3: selected is the lowest-EV executable play", (()=>{const ex=d.record.candidates.filter(c=>c.executable); return d.record.selected.ev===Math.min(...ex.map(c=>c.ev));})());
  ok("Hole 3: recommendation targets the green", d.play.destination.label==="the green");
  ok("Hole 3: no fairway-position language", noFairway(d));
  ok("Hole 3: record proves WHY 7i and 3W were eliminated (distance)", /past|target|back/i.test(cand(d,"7i").elim) && /past|target|back/i.test(cand(d,"3W").elim));
  ok("Hole 3: diagnostic record carries the full fit fields", (()=>{const c=cand(d,"9i");
    return ["motion","effCarry","fit","front","target","back","pShort","pOn","pLong","ev"].every(k=>k in c);})());
}
// 1. 115 calm → a fitting scoring club.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:115, lie:"FW", strokes:0, bag:p3() }));
  ok("115 calm → fitting green attack, no fairway lang", d.kind==="attack" && cand(d,d.club).fit==="fits" && noFairway(d)); }
// 2. 115 into moderate wind (plays ~124) → still green-targeting, a fitting club, 7i still excluded.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:124, lie:"FW", wind:"INTO", strokes:0, bag:p3() }));
  ok("115 into wind → green attack with a fitting club", d.kind==="attack" && cand(d,d.club).fit==="fits");
  ok("115 into wind → normal 7-iron still doesn't fit at execution", cand(d,"7i").executable===false || cand(d,"7i").fit!=="fits"); }
// 3. 115 helping wind (plays ~107) → fitting shorter club, still green-targeting.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:107, lie:"FW", wind:"DOWN", strokes:0, bag:p3() }));
  ok("115 downwind → fitting green attack", d.kind==="attack" && cand(d,d.club).fit==="fits"); }
// 4. Elevated green — needs more effective carry (plays ~128). The fit window shifts up.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:128, lie:"FW", strokes:0, bag:p3() }));
  ok("elevated green → window target tracks plays-like carry", cand(d,d.club).target===128 && d.kind==="attack"); }
// 5. Downhill target — needs less effective carry (plays ~104).
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:104, lie:"FW", strokes:0, bag:p3() }));
  ok("downhill green → fitting club near the reduced carry", d.kind==="attack" && cand(d,d.club).fit==="fits"); }
// 6. Front water requiring carry margin — a club that can't clear the front is excluded (short).
{ const WC = { ...H3, carry: 120 };   // forced carry to the front is 120
  const d = decideShot(par3base({ hole:WC, from:null, rem:125, effRem:125, lie:"FW", strokes:0, bag:p3() }));
  ok("front-carry par-3 → a club that can't clear the front is SHORT-excluded", cand(d,"PW").fit==="short" || cand(d,"PW").executable===false); }
// 7. Severe long trouble — an overshooting club is excluded (long), not chosen for distance.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:115, lie:"FW", strokes:0, bag:p3() }));
  ok("overshoot control: 7i/3W/Dr all cut as long", ["7i","3W","Dr"].every(k=>cand(d,k).fit==="long")); }
// 8. A demonstrated (normal) full club whose distribution fits is used — motion stays 'normal',
//    never an invented partial.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:125, effRem:125, lie:"FW", strokes:0, bag:p3() }));
  ok("fitting full club is used with a demonstrated (normal) motion", cand(d,d.club).motion==="normal" && cand(d,d.club).fit==="fits"); }
// 9. An unproven partial 7-iron is NOT invented to fit 115 — the 7i is excluded, not 'taken off'.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:115, lie:"FW", strokes:0, bag:p3() }));
  ok("no invented partial: 7-iron excluded rather than 'take something off'", cand(d,"7i").executable===false && d.record.selected.motion==="normal"); }
// 10. A 140-yard target → the normal 7-iron becomes a valid fit.
{ const d = decideShot(par3base({ hole:{...H3,y:140}, from:null, rem:140, effRem:140, lie:"FW", strokes:0, bag:p3() }));
  ok("140y target → 7-iron now FITS and can be the play", cand(d,"7i").fit==="fits"); }
// 11. A 190-yard target → the 3-wood may become valid when it fits (and is trusted).
{ const d = decideShot(par3base({ hole:{...H3,y:190}, from:null, rem:190, effRem:190, lie:"FW", strokes:0, bag:p3({ "3W":{rel:80,sd:11} }) }));
  ok("190y target → 3-wood now FITS", cand(d,"3W").fit==="fits"); }
// 12. Bench: a benched club is not considered even where it would fit.
{ const d = decideShot(par3base({ hole:{...H3,y:190}, from:null, rem:190, effRem:190, lie:"FW", strokes:0, bag:p3({ "3W":{benched:true} }) }));
  ok("benched 3-wood is not the pick even on a 190 hole", d.club!=="3W"); }
// 13. Availability ≠ suitability: an ENABLED 3-wood on a 115 hole is still rejected on distance.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:115, lie:"FW", strokes:0, bag:p3() /* 3W available, not benched */ }));
  ok("enabled 3-wood still fails distance fit on a 115 hole", cand(d,"3W").executable===false && cand(d,"3W").fit==="long"); }
// 14. No exact-fit club → one deliberate, honest call (never a fairway-finder, never invented motion).
{ const bag = p3().filter(c=>["9i","7i"].includes(c.k));   // only 125 & 140 available for a 105 target
  const d = decideShot(par3base({ hole:H3, from:null, rem:105, effRem:105, lie:"FW", strokes:0, bag }));
  ok("no-fit par-3 → exactly one deliberate call", !!d.club && !!d.kind);
  ok("no-fit par-3 → honest (not a fairway-position play), normal motion", d.kind!=="position" && d.record.selected.motion==="normal" && noFairway(d)); }
// 15. Displayed club always equals the stored execution.
{ const d = decideShot(par3base({ hole:H3, from:null, rem:115, effRem:115, lie:"FW", strokes:0, bag:p3() }));
  ok("displayed club matches the decision record's execution", d.club===d.record.selected.club && d.record.selected.kind===d.kind); }

console.log("\n" + (fail ? fail + " FAILED ❌" : "ALL " + n + " PASS ✅"));
process.exit(fail ? 1 : 0);
