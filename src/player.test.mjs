import { dailyProfile, reliabilityFrom, sideProven } from "./player.js";
import { clubConfidence } from "./whisper.js";

let fail = 0;
const ok = (n, c) => { console.log((c ? "PASS" : "FAIL") + " — " + n); if (!c) fail++; };

// ---- fixtures ---------------------------------------------------------------
const profile = {
  carries: { PW: 115, "9i": 125, "7i": 140, "8i": 145, "3W": 190 },
  clubStats: {
    "7i": { n: 20, carry: 140, sd: 6,  side: { dir: "R", pct: 60, med: 8,  n: 9 } },
    "3W": { n: 12, carry: 190, sd: 13, side: { dir: "R", pct: 80, med: 18, n: 8 } }, // proven heavy miss
  },
};
// this round: 7i steady (fairway), 3W into trouble twice
const shots = [
  { c: "7i", from: 150, gain: 140, exp: 140, g: 0, end: "fairway", h: 1 },
  { c: "3W", from: 210, gain: 200, exp: 205, g: 0, end: "trees",   h: 1, dir: "R" },
  { c: "3W", from: 205, gain: 205, exp: 205, g: 0, end: "rough",   h: 2 },
];

// legacy definitions, copied verbatim from CaddieOS to prove equality --------
const famOf = c => (c.includes("52")||c.includes("½")||c.includes("¾"))?"52":(c.includes("chip")||c.includes("CHIP")||c.includes("bump"))?"chip":c.split(" ")[0];
const csKey = fm => fm === "52" ? "52m" : fm;
const cstat = fm => profile.clubStats ? profile.clubStats[csKey(fm)] : null;
const shotsOf = fm => shots.filter(s => famOf(s.c) === fm);
const legacyReliability = fm => {
  let score = clubConfidence(shotsOf(fm), cstat(fm)).score;
  const cs = cstat(fm), sidePct = sideProven(cs) ? cs.side.pct : null;
  if (sidePct != null && sidePct >= 72) score -= 8;
  return Math.max(0, Math.min(100, Math.round(score)));
};

const model = dailyProfile(profile, shots);

// (a) BEHAVIOR PRESERVED: model reliability === legacy reliability, per club ---
["7i", "3W", "PW", "9i", "8i"].forEach(fam => {
  ok(`reliability(${fam}) matches legacy exactly`, model[fam].reliability === legacyReliability(fam));
});

// (b) one bad shot does NOT move permanent ability -----------------------------
ok("longTerm carry is the permanent number, not moved by today's shots",
  model["3W"].longTerm.carry === 190 && model["7i"].longTerm.carry === 140);
ok("longTerm sd comes from permanent clubStats, untouched by round",
  model["3W"].longTerm.sd === 13 && model["7i"].longTerm.sd === 6);

// (c) today's form tracks round results (3W into trouble cools vs its own baseline)
const model3wClean = dailyProfile(profile, [{ c: "3W", from: 210, gain: 205, exp: 205, g: 0, end: "fairway", h: 1 }]);
ok("today's confidence drops after two poor 3W outcomes vs a clean one",
  model["3W"].today.confidence < model3wClean["3W"].today.confidence);
ok("permanent ability is separate from today's form (distinct fields present)",
  model["3W"].longTerm && model["3W"].today && model["3W"].longTerm.carry !== model["3W"].today.confidence);

// (d) warm-up seam: inert when absent, raises the start when present -----------
ok("no warm-up field when none supplied", model["7i"].warmup === null);
const warmGood = { "9i": [ { c: "9i", gain: 125, exp: 125, g: 1 }, { c: "9i", gain: 125, exp: 125, g: 1 }, { c: "9i", gain: 125, exp: 125, g: 1 } ] };
const withWarm = dailyProfile(profile, shots, { warmup: warmGood });
const noWarm = dailyProfile(profile, shots);
ok("warm-up marked as applied", withWarm["9i"].warmup && withWarm["9i"].warmup.n === 3);
ok("warm-up seeds a higher starting confidence for a club with no round shots yet",
  withWarm["9i"].confidence >= noWarm["9i"].confidence);
ok("warm-up does NOT change permanent ability",
  withWarm["9i"].longTerm.carry === noWarm["9i"].longTerm.carry);

// (e) reliabilityFrom is the isolated, testable blend --------------------------
ok("reliabilityFrom docks a proven heavy one-way miss by 8",
  reliabilityFrom(80, profile.clubStats["3W"]) === 72);
ok("reliabilityFrom leaves an unproven/mild miss alone",
  reliabilityFrom(80, profile.clubStats["7i"]) === 80);

console.log("\n" + (fail ? fail + " FAILED ❌" : "ALL PASS ✅"));
process.exit(fail ? 1 : 0);
