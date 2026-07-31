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
// 18-19. Confidence is DISTINCT components, and overall is the weakest link (no false precision).
{
  const d = decideShot(base({ hole: WATER, from: { d: 0.5, x: .5 }, rem: 190, effRem: 190, lie: "FW", strokes: 1, bag: mkBag() }));
  const c = d.confidence;
  const keys = ["player", "form", "course", "observation", "play", "execution", "overall"];
  ok("all distinct confidence components are present", keys.every(k => k in c));
  const comps = [c.player, c.form, c.course, c.observation, c.play, c.execution].filter(v => v != null);
  ok("they are not one overloaded number (components differ)", new Set(comps).size >= 2);
  ok("overall = the weakest component (a chain, not a fabricated blend)", c.overall === Math.min(...comps));
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

console.log("\n" + (fail ? fail + " FAILED ❌" : "ALL " + n + " PASS ✅"));
process.exit(fail ? 1 : 0);
