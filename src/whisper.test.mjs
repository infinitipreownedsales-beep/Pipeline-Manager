import { whisper, humanClub, teeWhisper, puttWhisper, benchWhisper } from "./whisper.js";

let fail = 0;
const ok = (name, cond) => { console.log((cond ? "PASS" : "FAIL") + " — " + name); if (!cond) fail++; };
const joined = w => w.lines.join(" ");

// --- club humanization ---
ok("8i -> 8-iron", humanClub("8i", "8i") === "8-iron");
ok("Dr -> Driver", humanClub("Dr", "Dr") === "Driver");
ok("PW -> Pitching wedge", humanClub("PW", "PW") === "Pitching wedge");
ok("52FS -> 52, full", humanClub("52", "52FS") === "52, full");
ok("3W -> 3-wood", humanClub("3W", "3W") === "3-wood");

// --- the brief's translation examples ---
// dispersion ±14 -> "spraying"
const spray = whisper({ fam: "7i", chip: "7i", stat: { n: 8, avg: 0, sd: 14 }, feel: "Smooth 74" });
ok("dispersion 14 -> 'spraying' language", /spraying/.test(joined(spray)) && !/14/.test(joined(spray)));

// avg -9 / live recal -> "playing it at 130 today"
const recal = whisper({ fam: "7i", chip: "7i", adj: -10, eff: 130, feel: "Smooth 74" });
ok("live recal -> 'playing it at 130 today'", /playing it at 130 today/.test(joined(recal)));

// miss bias R -> favor left edge
const missR = whisper({ fam: "7i", chip: "7i", side: { dir: "R", pct: 67 }, stat: { n: 5, avg: 0, sd: 6 } });
ok("miss right -> 'favor the left edge'", /favor the left edge/i.test(joined(missR)) && /miss lives right/.test(joined(missR)));

// confidence 91 -> trust it
const conf = whisper({ fam: "8i", chip: "8i", conf: 91 });
ok("confidence 91 -> 'trust it'", /trust it/.test(joined(conf)));

// hazard water left -> center-right
const wet = whisper({ fam: "PW", chip: "PW", hole: { dzL: "water" }, conf: 80 });
ok("water left -> 'left is wet' + center-right", /left is wet/.test(joined(wet)) && /center-right/.test(joined(wet)));

// --- structure rules ---
ok("returns a club string", typeof conf.club === "string" && conf.club.length > 0);
ok("returns 1-2 lines", conf.lines.length >= 1 && conf.lines.length <= 2);
ok("no raw stat numbers leak into normal whisper", !/\b\d{2,}\b/.test(joined(spray)) || /130/.test(joined(recal)));
ok("word budget <= 35", whisper({ fam: "7i", chip: "7i", side: { dir: "R", pct: 67 }, stat: { n: 8, avg: -7, sd: 13 }, feel: "Stand closer and swing within yourself, glove logo down" }).words <= 35);

// --- uses the player's own saved feel verbatim ---
const feely = whisper({ fam: "9i", chip: "9i", conf: 88, feel: "Trust the number" });
ok("player's feel appears verbatim", /Trust the number/.test(joined(feely)));

// --- can't-reach / advance voice (the 450-yard bug) ---
const far = whisper({ fam: "3W", chip: "3W", reach: false, leaves: 296, feel: "Smooth and left edge" });
ok("unreachable -> names the long club, not an iron to the green", far.club === "3-wood");
ok("unreachable -> says advance + leaves a number", /advance/i.test(joined(far)) && /296/.test(joined(far)));
ok("unreachable -> never says 'middle of the green'", !/middle of the green/i.test(joined(far)));
const midLay = whisper({ fam: "8i", chip: "8i", reach: false, leaves: 40 });
ok("short lay-up still frames as advance", /advance/i.test(joined(midLay)) && /40/.test(joined(midLay)));
// a reachable shot should still talk about the green
const reachable = whisper({ fam: "8i", chip: "8i", reach: true, conf: 80 });
ok("reachable shot -> greens language, not advance", /middle of the green/i.test(joined(reachable)) && !/advance/i.test(joined(reachable)));

// --- inside 35 switches to conversion voice ---
const near = whisper({ fam: "chip", chip: "CHIP", i35: true });
ok("inside 35 -> conversion language, no full-swing club", /commit/.test(joined(near)) && /two putts/.test(joined(near)));

// --- ancillary voices ---
ok("tee whisper mentions distance + a line", /150/.test(teeWhisper({ y: 150, hz: "water left" }, 150)));
ok("tee whisper reacts to water", /safe line/i.test(teeWhisper({ y: 150, hz: "water left" }, 150)));
ok("putt whisper: back of the cup", /back of the cup/i.test(puttWhisper(0)));
ok("bench whisper asks to route around", /route around/.test(benchWhisper("9i")));

// every line should start capitalized and be short
const allLines = [...spray.lines, ...missR.lines, ...wet.lines];
ok("lines are capitalized", allLines.every(l => /^[A-Z0-9]/.test(l)));
ok("lines are sentence-length (<= 22 words each)", allLines.every(l => l.split(/\s+/).length <= 22));

console.log("\n" + (fail ? fail + " FAILED ❌" : "ALL PASS ✅"));
process.exit(fail ? 1 : 0);
