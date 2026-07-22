import { recoveryPlan, expectedStrokes, isRecoveryLie } from "./recovery.js";

let fail = 0;
const ok = (n, c) => { console.log((c ? "PASS" : "FAIL") + " — " + n); if (!c) fail++; };

// a realistic bag: {k, carry, rel(0-100)}
const bag = [
  { k: "PW", carry: 115, rel: 80 }, { k: "9i", carry: 125, rel: 78 },
  { k: "8i", carry: 140, rel: 72 }, { k: "7i", carry: 152, rel: 70 },
  { k: "6i", carry: 165, rel: 62 }, { k: "3W", carry: 205, rel: 40 },
];
const ctx = { bag, wedgeDist: 100 };

// --- lie detection ---
ok("trees/deep/bunker trigger recovery", isRecoveryLie("TREES") && isRecoveryLie("DEEP") && isRecoveryLie("FBUNK"));
ok("fairway/tee do NOT trigger recovery", !isRecoveryLie("FW") && !isRecoveryLie("TEE"));

// --- THE REPORTED SCENARIO: in the trees, ~150 to the green ---
const plan = recoveryPlan(150, "TREES", ctx);
console.log("\ntrees @150 options:", plan.options.map(o => `${o.kind}:${o.club}(ev ${o.ev})`).join("  "), "\nbest:", plan.best.kind, plan.best.club, "\n");
ok("best play is NOT a straight attack (no 8-iron to green)", plan.best.kind !== "hero");
ok("best is punch-out or lay-up", ["punch", "layup"].includes(plan.best.kind));
ok("hero shot is offered but flagged low-probability", plan.hero && plan.hero.prob <= 25);
ok("hero shot has the worst expected value here", plan.hero.ev >= plan.best.ev);
ok("objective switched away from 'reach green'", /recover|position|wedge|out/i.test(plan.objective));
ok("recommendation carries a reason", typeof plan.best.reason === "string" && plan.best.reason.length > 0);

// --- lay-up to the favorite number is preferred when reachable ---
const layupCtx = { bag, wedgeDist: 105 };
const p2 = recoveryPlan(180, "DEEP", layupCtx);
ok("from deep rough at 180, lay-up to 105 wins on EV", p2.best.kind === "layup" && p2.best.leaves === 105);

// --- fairway bunker: escape objective, hero more viable than from trees ---
const pb = recoveryPlan(150, "FBUNK", ctx);
ok("fairway-bunker hero prob > trees hero prob", pb.hero.prob > plan.hero.prob);

// --- expected strokes model is monotonic & lie-aware ---
ok("closer = fewer expected strokes", expectedStrokes(80, "FW") < expectedStrokes(180, "FW"));
ok("a trees lie costs more than a fairway lie", expectedStrokes(150, "TREES") > expectedStrokes(150, "FW"));
ok("deep rough costs more than first cut", expectedStrokes(120, "DEEP") > expectedStrokes(120, "FIRST"));

// --- when nothing reaches, hero becomes a big advance, still risk-checked ---
const far = recoveryPlan(240, "TREES", ctx);
ok("very long trees shot: recover/lay-up beats hero", far.best.kind !== "hero");

console.log("\n" + (fail ? fail + " FAILED ❌" : "ALL PASS ✅"));
process.exit(fail ? 1 : 0);
