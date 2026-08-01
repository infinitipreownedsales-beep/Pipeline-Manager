import { useState, useEffect, useRef } from "react";
import { whisper, humanClub, teeWhisper, puttWhisper, benchWhisper, clubConfidence } from "./whisper.js";
import { MAPPED } from "./holes/index.js";
import { recoveryPlan, isRecoveryLie } from "./recovery.js";
import { dailyProfile, reliabilityFrom } from "./player.js";
import { centerX, holeContext, lieAt } from "./geometry.js";
import { decideShot } from "./decision.js";

// Visible build/version stamp — shown in the header so the running tool is identifiable.
const BUILD = "v12 · clean caddie";
// CADDIE OS v10 — DYNAMIC ROUND ENGINE
// Every shot logs the club actually used (tap to change, layups tappable).
// Hot/cold detection per club · one-tap bench from the alert ·
// live carry recalibration when a club runs consistently short.

const DEF_PROFILE = {
  name:"Kyle",
  carries:{ "PW":115,"9i":125,"7i":140,"8i":145,"3W":190 },
  w52:{ half:[60,64], tq:[80,84], fs:[85,90] },
  cues:{ full:"SMOOTH 74 — controlled is straight", wedge:"Rotation sets distance — hands passive" },
  feels:{ "52":"Rotation sets distance — hands passive, glove logo down","PW":"Smooth 74 + full finish — never decelerate","9i":"Smooth 74 — trust the number","7i":"Smooth 74 — stand closer","8i":"Smooth 74 — stand closer, fairway lie only","3W":"Left edge, full commit — or step off","CHIP":"One look · commit · land it and let it run","PUTT":"Back of cup — two-putt ceiling" }
};
// Persisted-shape version. Bump when the stored profile/live shape changes; the loader
// tolerates older data (missing fields fall back to defaults).
const SCHEMA = 2;
// A clean first-use player: no clubs, no history, no cues/feels — but the engine-safe
// scaffolding (wedge windows) kept so the app never crashes on an empty profile.
const CLEAN_PROFILE = { name:"", carries:{}, clubStats:{}, w52:DEF_PROFILE.w52, cues:DEF_PROFILE.cues, feels:{}, schemaV:SCHEMA };

const BP_HOLES = [
 {n:1,par:4,y:360,tgt:5,gap:false,r3:null,star:false,vibe:"Opening statement. Tight corridor, water breathing on the left — but this hole folds to three smooth swings. Set the tone: unhurried, left-center, rotation wedge to the middle.",hz:"Water LEFT full length · elevated green",cue:"Two smooth 7-irons, ¾ wedge, two putts.",plan:[{c:"7i",a:"Left-center corridor",t:"Smooth 74, stand closer. Corridor first, distance second."},{c:"7i",a:"Left-center advance",t:"Same swing again. Leaves 80y — a number you own."},{c:"52° ¾",a:"CENTER green",t:"80–84 window. Glove logo down, rotation stops the club."}]},
 {n:2,par:4,y:381,carry:191,carryLabel:"the creek",tgt:5,gap:false,r3:null,star:false,vibe:"The gut check. One committed 3W over the creek is the whole hole — everything after is routine. You've cleared it before. Left edge, full send, then back to smooth.",hz:"MUST CARRY creek 191y · water L · pond R of green",cue:"One committed swing, then smooth home.",plan:[{c:"3W",a:"LEFT EDGE — full commit",t:"Governor suspended for ONE swing. Right bias 22–42y, so left edge. Step off if not 100% in."},{c:"9i",a:"Center advance",t:"Back to smooth 74. Leaves 66y."},{c:"52° firm ½",a:"Center-LEFT",t:"Mid-gap number: firm half, one pick, zero doubt. Pond right — never right."}]},
 {n:3,par:3,y:110,tgt:4,gap:true,r3:null,star:false,vibe:"The island of discipline. 110 yards of pure temptation to reach for the 52 — don't. PW smooth to dead center, take your two putts, walk off smiling.",hz:"🔴 GAP 110y · water surrounds",cue:"PW smooth dead center — the 112 was a flyer.",plan:[{c:"PW",a:"CENTER — never the flag",t:"115 carry = 5 past center = safe. Long-center beats short-wet by two strokes. Full finish."}]},
 {n:4,par:5,y:516,tgt:6,gap:true,r3:"3-PUTT",star:false,vibe:"The long march. Water owns the right for 516 yards — so you never look right. Four disciplined shots, PW long-center, and redemption on the green where R3 leaked three putts.",hz:"Water RIGHT all hole · 3W banned · 🔴 gap approach",cue:"Never right, PW long-center, no 3-putt this time.",plan:[{c:"7i",a:"CENTER — never right",t:"Stand closer, smooth 74. Left rough is a friend here."},{c:"7i",a:"Center-left",t:"Identical swing. →236y."},{c:"8i",a:"Center-left",t:"Fairway lie only (rough → 9i). Leaves 91y."},{c:"PW",a:"CENTER — never flag",t:"🔴 Gap zone. PW finishes long-center — that IS the plan, not a miss."}]},
 {n:5,par:4,y:374,tgt:5,gap:true,r3:null,star:false,vibe:"Thread the needle, cash the gap. Tight trees force patience, then the PW gap protocol turns 109 awkward yards into 6-feet-past-center routine.",hz:"Trees tight · water front-left of green · 🔴 gap approach",cue:"9i, 7i, PW long-center — gap covered when you aim center.",plan:[{c:"9i",a:"Center corridor",t:"125 into the neck. Nothing fancy."},{c:"7i",a:"Center-left",t:"Leaves 109y."},{c:"PW",a:"Center-LEFT",t:"🔴 Gap. 115 carry = 6 past center. Water front-left — center-left aim only."}]},
 {n:6,par:3,y:150,carry:145,carryLabel:"the water",tgt:4,gap:false,r3:null,star:false,vibe:"The commitment test. All carry, all water, and the ONLY bad miss is short. Long is rough. Free your swing — this is the one green where over is applauded.",hz:"Water fronts — full carry ~145y · over back = SAFE",cue:"Commit through it — the only bad miss is short.",plan:[{c:"8i",a:"Center green — COMMIT",t:"Governor suspended. Full through-swing, finish high. Over back = safe rough."}]},
 {n:7,par:5,y:483,tgt:6,gap:false,r3:"3-PUTT",star:false,vibe:"The corridor test. Dogleg RIGHT into a tight tree-walled chute that bends gently the rest of the way home. Nobody cuts this corner and survives — position, position, position, then your best number: 88, full smooth. Two putts this time.",hz:"Trees LEFT and RIGHT — walls · dogleg RIGHT, never cut the corner · narrow corridor after the turn · uphill green",cue:"Three smooth shots, full-smooth wedge — two putts, not three.",plan:[{c:"7i",a:"CENTER — never cut right",t:"Smooth 74 to the corner. Short of the turn is fine; through the trees is not."},{c:"7i",a:"Dead center of the corridor",t:"Tree walls both sides — corridor discipline, one target. →203y."},{c:"PW",a:"Center corridor",t:"Leaves 88y — the sweetest number in the bag."},{c:"52° FS",a:"CENTER green",t:"85–90 confirmed. Uphill green — firm first putt, back of cup."}]},
 {n:8,par:4,y:328,tgt:5,gap:false,r3:null,star:false,vibe:"The clean machine. Three numbers that all exist: 7i, 9i, half rotation. No hero shots available, none needed. This is what the system looks like when it hums.",hz:"Trees tight · 9i off tee banned (short of fairway)",cue:"7i, 9i, half rotation — three numbers that all exist.",plan:[{c:"7i",a:"Left-center fairway",t:"9i doesn't reach the fairway — 7i every time."},{c:"9i",a:"Center",t:"Leaves 63y."},{c:"52° ½",a:"CENTER",t:"60–64 confirmed. Rotation only."}]},
 {n:9,par:4,y:323,tgt:5,gap:false,r3:null,star:false,vibe:"The vigilance hole. OB left, and the new pull-draw would love to visit. Center, never left, provisional out loud on any doubt — then a stock ¾ wedge closes the front nine.",hz:"OB LEFT — provisional immediately · pull-draw watch",cue:"Center never left — say provisional out loud on doubt.",plan:[{c:"9i",a:"CENTER — never left",t:"Residual right-miss helps here. If it starts left, provisional NOW."},{c:"PW",a:"Center",t:"Leaves 83y."},{c:"52° ¾",a:"Center, bias right",t:"80–84 confirmed. OB left = right-of-center is correct here only."}]},
 {n:10,par:5,y:471,tgt:5,gap:false,r3:"CHUNK",star:true,vibe:"Redemption row, part one. R3's chunks lived here — today the fix is one word: closer. Full setup on every iron and this par 5 hands you a half-wedge birdie look.",hz:"Houses L · trees R · 3-shot rule",cue:"Stand closer on every iron — the chunks lived here.",plan:[{c:"7i",a:"Center, aim left",t:"STAND CLOSER. Extra second at address — that's the whole fix."},{c:"8i",a:"Center",t:"Fairway lie only. →186y."},{c:"9i",a:"Center",t:"Leaves 61y."},{c:"52° ½",a:"CENTER",t:"Confirmed half. On in one, birdie putt at back-of-cup pace."}]},
 {n:11,par:4,y:289,tgt:4,gap:false,r3:null,star:true,vibe:"The gift. 289 yards, benign green, and the best birdie look on the property. One more club than pride wants — 8i smooth finishes center while 7i finishes short. Take the gift.",hz:"Houses LEFT · right side safe",cue:"One more club, smooth — GIR lives long, not short.",plan:[{c:"7i",a:"Center, right bias ok",t:"Right is the safe side. Smooth 74."},{c:"8i",a:"CENTER green",t:"149y = 8i, NOT 7i. The GIR lives at the number, not below it."}]},
 {n:12,par:4,y:349,tgt:5,gap:false,r3:null,star:false,vibe:"The rule keeper. One club is banned on shot two and one club is blessed — 9i only, forever. The rule already paid for itself once. Honor it and this hole is a formality.",hz:"Road L (road lie) · water front-left green · 8i BANNED shot 2",cue:"9i only on two — the rule already paid for itself.",plan:[{c:"7i",a:"Center fairway",t:"Road left is a road lie, not a disaster."},{c:"9i ONLY",a:"Center-left",t:"NEVER 8i here — water history. Leaves 84y."},{c:"52° ¾",a:"Center-LEFT",t:"¾ ceiling, confirmed. Water front-left."}]},
 {n:13,par:3,y:179,tgt:4,gap:false,r3:"3-PUTT",star:false,vibe:"The corridor of patience. Trees swallow anything high, so this par 3 is played as two low, smart shots. 8i to the zone, bump it on, and bury the 3-putt ghost.",hz:"Trees both sides ALL hole · high loft BANNED",cue:"On the green first try, two putts, four, walk.",plan:[{c:"8i",a:"Center landing zone",t:"145 → 34y from pin. Two-shot par 3 by design."},{c:"PW bump",a:"Center pin — LOW",t:"INSIDE 35: hood face, punch under everything. One look, commit, ON in one."}]},
 {n:14,par:4,y:278,tgt:4,gap:false,r3:"CHUNK",star:true,vibe:"Redemption row, part two — and this one owes you. 278 yards of birdie chance that chunks stole in R3. Stand closer, take one more club, collect the debt.",hz:"Trees both sides · uphill",cue:"Stand closer, one more club — this hole owes you.",plan:[{c:"7i",a:"Center fairway",t:"Full setup. The chunk was setup drift, nothing more."},{c:"8i",a:"CENTER green",t:"138y = 8i finishing past center. Uphill kills it soft. Downhill birdie putt back."}]},
 {n:15,par:5,y:504,tgt:6,gap:false,r3:null,star:false,vibe:"The water gauntlet. 504 yards where right does not exist. Three identical swings, three identical aims — monotony is the weapon. Then rotation sets the wedge.",hz:"Water RIGHT entire length · 3W banned",cue:"Same swing, same aim, three times — then rotation sets the wedge.",plan:[{c:"7i",a:"Center-LEFT — never right",t:"Water owns the right. Left rough = safe."},{c:"7i",a:"Center-LEFT",t:"→224y. Same swing."},{c:"7i",a:"Center-LEFT",t:"Leaves 84y. Same swing."},{c:"52° ¾",a:"CENTER — never right",t:"84y confirmed. Center, two putts, escape with your 6."}]},
 {n:16,par:4,y:329,tgt:5,gap:false,r3:null,star:false,vibe:"The green that took four putts once — never again. Half rotation to the middle, then FIRM. Uphill lags die early here; back-of-cup is the minimum, not the goal.",hz:"Trees · PW BANNED on approach (4-putt history)",cue:"Half rotation, center, firm first putt.",plan:[{c:"7i",a:"Center fairway",t:"Uphill hole. Smooth 74."},{c:"9i",a:"Center",t:"Leaves 64y."},{c:"52° ½",a:"CENTER — not PW",t:"Half ceiling. Uphill — hold the finish one extra beat."}]},
 {n:17,par:3,y:164,tgt:4,gap:false,r3:null,star:false,vibe:"Your proven ground. This exact two-shot plan already made par — the only hole with a receipt. 8i to the zone, chip it close, tap in. Run the rerun.",hz:"Trees surround · small green",cue:"You've already parred this exact plan — run it again.",plan:[{c:"8i",a:"Landing zone center",t:"145 → 19y from pin. 9i misses the zone — 8i is the club."},{c:"PW chip",a:"Center pin — low run",t:"INSIDE 35: the R1 par shot. Hood face, run it to the hole."}]},
 {n:18,par:4,y:311,tgt:4,gap:false,r3:null,star:true,vibe:"The closer. Uphill, dogleg, and a conversion waiting inside 35 — the exact skill this phase is built on. Finish the way champions practice: on in one, two putts, sign it.",hz:"Dogleg RIGHT — never cut · trees · uphill green",cue:"On the green first try — finish the way the phase demands.",plan:[{c:"7i",a:"Center-LEFT",t:"Never cut the dogleg."},{c:"8i",a:"Center",t:"Fairway lie only. Leaves 26y."},{c:"PW chip",a:"Center pin",t:"INSIDE 35: land the front third, let it climb the hill."}]},
];

// PATRICK FARMS — tournament course. No hand-written book: the CADDIE ENGINE
// generates every plan from the player's live carries, windows, and form.
const PF_HOLES=[
 {n:1,par:5,y:529,tgt:6,gap:false,r3:null,star:false,vibe:"Opening par 5 with water pinching BOTH sides of the landing zone — the pond left and the lake right want the same careless swing. Thread the middle in pieces; the hole gives a wedge finish to patience.",hz:"Water LEFT and water RIGHT in the landing zone · railroad beyond right · bunkers at the green",cue:"Water both sides — the middle is the only friend."},
 {n:2,par:4,y:304,tgt:4,gap:false,r3:null,star:true,vibe:"The gift of the front nine. Short, straight, tree-lined — and a creek sneaks across just short of the green. Position, wedge over the creek, birdie look.",hz:"Tree-lined both sides · creek crosses just SHORT of the green — carry it or lay back",cue:"Short hole, full discipline — the creek eats the greedy."},
 {n:3,par:4,y:442,tgt:5,gap:false,r3:null,star:false,vibe:"Long and honest. A gully cuts the fairway up ahead — advance in pieces, take the crossing out of play, and a bogey here beats most of the field.",hz:"Trees both sides · eroded creek/gully crosses the fairway mid-hole",cue:"Three pieces, no hero carry over the gully."},
 {n:4,par:3,y:189,tgt:4,gap:false,r3:null,star:false,vibe:"Long par 3 guarded by a bunker dead-center short of the green with a creek before it. Everything short is trouble — the play is committed and LONG of the sand.",hz:"Bunker front-CENTER short of green · creek crossing before it · miss long-center",dzR:null,cue:"Over the sand or short of the creek — never between."},
 {n:5,par:4,y:424,tgt:5,gap:false,r3:null,star:false,vibe:"Long par 4 bending gently with heavy trees right and creek crossings lurking. Favor the left half all day and let three smooth swings do the work.",hz:"Heavy trees RIGHT · creek crossings mid-hole · open bail LEFT",dzR:"trees",cue:"Left half of everything — the right side is a forest."},
 {n:6,par:4,y:357,tgt:5,gap:false,r3:null,star:false,vibe:"A ditch cuts the fairway mid-hole and houses stand guard right. Lay short of the ditch, hop it, wedge on — boring golf, beautiful scorecard.",hz:"Ditch/gully crossing MID-hole · houses RIGHT · scattered trees left",dzR:"houses",cue:"Short of the ditch, over the ditch, on — three, simple."},
 {n:7,par:5,y:500,tgt:6,gap:false,r3:null,star:false,vibe:"A spine of tall pines splits the left side the whole way. Stay right of the tree line, stack three smooth advances, and the wedge window opens.",hz:"Tree spine LEFT-center full length · fairway favors the right half",dzL:"trees",cue:"Right of the pines every swing — never flirt with the spine."},
 {n:8,par:3,y:188,tgt:4,gap:false,r3:null,star:false,vibe:"Another long one-shotter. Bunker right of the green, trees left — center-green is the only target that respects both. Two putts and walk.",hz:"Greenside bunker RIGHT · trees LEFT · long narrow green",dzR:"sand",cue:"Dead center — the edges are both taken."},
 {n:9,par:4,y:436,tgt:5,gap:false,r3:null,star:false,vibe:"The lake owns the entire left side and the green sits right on its bank. NEVER left — right rough is your best friend on the whole property. Close the nine dry.",hz:"LAKE LEFT entire hole — green sits on the water · bunkers right of green · houses right",dzL:"water",cue:"Never left. Never left. Never left.",},
 {n:10,par:4,y:455,tgt:5,gap:false,r3:null,star:false,vibe:"Two ponds stacked down the left with the highway beyond. Long two-shotter — center-right advances, take the 5 with a smile.",hz:"Water LEFT (two ponds) mid-hole · highway beyond left · bunker left of green",dzL:"water",cue:"Center-right, twice, then center green."},
 {n:11,par:3,y:177,tgt:4,gap:false,r3:null,star:false,vibe:"Uphill one-shotter to a crowned green, railroad trees left. Club up for the hill, commit, center.",hz:"Uphill · trees/railroad LEFT · crowned green sheds misses",dzL:"trees",cue:"One more club for the hill — center or long-center."},
 {n:12,par:4,y:397,tgt:5,gap:false,r3:null,star:false,vibe:"Dark wall of woods tight down the left, and a creek slides across JUST short of the green. Right-center off the tee, then respect the creek number.",hz:"Dense woods LEFT — tight · creek crosses ~45y short of green · houses right",dzL:"trees",cue:"Right-center, then know the creek number cold."},
 {n:13,par:5,y:518,tgt:6,gap:false,r3:null,star:false,vibe:"Straightaway three-shotter, trees left, houses right. Nothing tricky — just the same smooth swing three times and a confirmed wedge window.",hz:"Tree line LEFT · houses RIGHT · long and open",dzL:"trees",cue:"Same swing, same aim, three times."},
 {n:14,par:4,y:385,tgt:5,gap:false,r3:null,star:false,vibe:"Dogleg LEFT at the end with two bunkers guarding the front of a tucked green — and waste ground right. Position to the corner; never cut the trees left.",hz:"Dogleg LEFT — never cut · bunkers FRONT of green · waste/dirt RIGHT",dzR:"waste",cue:"To the corner first — the green only opens from the fairway."},
 {n:15,par:4,y:350,tgt:5,gap:false,r3:null,star:true,vibe:"Island clusters of trees sit IN the fairway both sides — a slalom hole. Thread the middle gap twice and it's a flip wedge in.",hz:"Tree clusters IN the fairway both sides · road left · thread the middle",cue:"Slalom — middle gap, middle gap, wedge."},
 {n:16,par:3,y:175,tgt:4,gap:false,r3:null,star:false,vibe:"Uphill par 3 with a pot bunker short-center of the green. The hill kills short shots — one more club and commit past the sand.",hz:"Uphill · bunker short-CENTER of green · miss long-center",cue:"Past the sand — the hill already defends short."},
 {n:17,par:4,y:418,tgt:5,gap:false,r3:null,star:false,vibe:"Long, straight, dense trees left and a bunker right of the green. Center-right advances, center green, take your 5 and march to the closer.",hz:"Dense trees LEFT · greenside bunker RIGHT",dzL:"trees",cue:"Center-right all the way home."},
 {n:18,par:5,y:540,tgt:6,gap:false,r3:null,star:false,vibe:"The 540-yard closer. Wide open by this course's standards until a pond guards beyond-left of the green. Three advances, wedge to center, sign a good card.",hz:"Long · pond beyond-LEFT of green · trees scattered both sides",dzL:"water",cue:"Patience for 500 yards, precision for the last 40."},
];

const COURSES={
 bp:{name:"Bay Pointe CC",holes:BP_HOLES},
 pf:{name:"Patrick Farms GC",holes:PF_HOLES},
 ...MAPPED,   // real holes mapped from Shot Scope, one file per hole in ./holes
};

// CADDIE PLANNER — generates the hole plan from the PLAYER's live data
const genPlan=(hole,P,bench=[])=>{
 const E2=engine(P,bench);const steps=[];let rem=hole.y;let g=0;
 const aim=hole.dzL&&hole.dzR?"CENTER — trouble both sides":hole.dzL?"Center-RIGHT — away from the "+hole.dzL:hole.dzR?"Center-LEFT — away from the "+hole.dzR:"Center";
 while(rem>0&&g++<7){
  const r=E2.rec(rem);
  if(!r)break;
  if(r.zone==="adv"){
   const opts=E2.layup(rem)||[];
   const pick=opts.find(o=>o.r&&o.r.zone==="ok")||opts[0];
   if(pick){steps.push({c:pick.k,a:aim,t:"Position "+pick.carry+"y → leaves "+pick.rem+"y ("+pick.r.club+")."});rem=pick.rem;continue;}
   steps.push({c:r.chip,a:aim,t:r.note});rem=rem-E2.chipCarry(r.chip);continue;
  }
  steps.push({c:r.chip==="CHIP"?"PW chip":r.club.split(" —")[0],a:hole.dzL==="water"?"CENTER green — never left":hole.dzR==="water"?"CENTER green — never right":"CENTER green",t:r.note});
  rem=0;
 }
 return steps.length?steps:[{c:"7i",a:aim,t:"Advance and reassess."}];
};

// ---------- DYNAMIC LAYER ----------
const bookChipOf=(c,P)=>{if(!c)return null;if(c.includes("bump")||c.includes("chip"))return "CHIP";if(c.includes("3W"))return P.carries["3W"]!==undefined?"3W":null;if(c.includes("½"))return "52½";if(c.includes("¾"))return "52¾";if(c.includes("FS"))return "52FS";const k=c.split(" ")[0];return P.carries[k]!==undefined?k:null;};
const famOf = c => (c.includes("52")||c.includes("½")||c.includes("¾"))?"52":(c.includes("chip")||c.includes("CHIP")||c.includes("bump"))?"chip":c.split(" ")[0];

// Per-club form from this round's logged shots → {cold:[], hot:[], adj:{fam:yds}}
const clubFlags = (shots=[],fams=["52"]) => {
  const out={cold:[],hot:[],adj:{}};
  fams.forEach(f=>{
    const mine=shots.filter(x=>famOf(x.c)===f&&!x.p&&(!x.lie||x.lie==="FW")&&(x.g||x.from>x.exp+8));
    if(mine.length<2) return;
    const last2=mine.slice(-2);
    const errOf=x=>x.g?0:(x.gain-x.exp);
    if(last2.every(x=>!x.g&&errOf(x)<=-15)) out.cold.push(f);
    else if(last2.every(x=>x.g||Math.abs(errOf(x))<=8)) out.hot.push(f);
    if(f!=="52"){
      const errs=mine.filter(x=>!x.g).slice(-3).map(errOf);
      if(errs.length>=3){const m=errs.reduce((a,b)=>a+b,0)/errs.length;
        if(m<=-8) out.adj[f]=Math.max(-20,Math.round(m/5)*5);}
    }
  });
  return out;
};

const engine = (P, bench=[], adj={}) => {
  const W=P.w52, out=k=>bench.includes(k);
  const eff=k=>(P.carries[k]||0)+(adj[k]||0);
  const chipCarry=ch=>ch==="52½"?Math.round((W.half[0]+W.half[1])/2):ch==="52¾"?Math.round((W.tq[0]+W.tq[1])/2):ch==="52FS"?Math.round((W.fs[0]+W.fs[1])/2):ch==="CHIP"?25:eff(ch);
  const tag=k=>adj[k]?` (live cal ${adj[k]}y → ${eff(k)})`:"";
  const rec=(y)=>{
    if(!y||y<=0) return null;
    if(y<=34) return {club:"PW chip / bump",chip:"CHIP",zone:"i35",cue:"ONE LOOK — COMMIT",note:"One look · commit · ball ON the green first try · two-putt ceiling.",color:"#0a84ff"};
    if(y<=W.fs[1]&&!out("52")){
      if(y<W.half[0]) return {club:"Firm chip / held ½",chip:"52½",zone:"warn",cue:"ON IN ONE",note:"Below the half floor — land it on, take two putts.",color:"#ff9f0a"};
      if(y<=W.half[1]) return {club:"52° HALF",chip:"52½",zone:"ok",cue:P.cues.wedge,note:`Confirmed ${W.half[0]}–${W.half[1]}y. Glove logo down, body stops the club.`,color:"#30d158"};
      if(y<W.tq[0]) return {club:"Firm ½ or soft ¾",chip:"52¾",zone:"warn",cue:"PICK ONE — COMMIT",note:"Mid gap. One rotation, full commitment, center green.",color:"#ff9f0a"};
      if(y<=W.tq[1]) return {club:"52° THREE-QUARTER",chip:"52¾",zone:"ok",cue:P.cues.wedge,note:`Confirmed ${W.tq[0]}–${W.tq[1]}y. Rotation sets it.`,color:"#30d158"};
      return {club:"52° FULL SMOOTH",chip:"52FS",zone:"ok",cue:P.cues.full,note:`${W.fs[0]}–${W.fs[1]}y. Never book the 52 past ${W.fs[1]}.`,color:"#30d158"};
    }
    const appr=Object.keys(P.carries).filter(k=>!out(k)&&eff(k)<=168).sort((a,b)=>eff(a)-eff(b));
    const gc=appr[0];
    if(y<=W.fs[1]&&out("52")) return {club:(gc||"wedge")+" soft — CENTER",chip:gc||"CHIP",zone:"warn",cue:"52 IS BENCHED",note:"Wedge is cold. Shortest club, softer motion, fat of the green.",color:"#ff9f0a"};
    if(gc&&y<=eff(gc)) return {club:gc+" smooth — CENTER",chip:gc,zone:"gap",cue:"LONG-CENTER BEATS SHORT",note:`🔴 Gap zone. ${gc}${tag(gc)} finishes long-center — that is the plan. Never the flag.`,color:"#ff453a"};
    const live=appr;
    const fit=live.find(k=>eff(k)>=y&&eff(k)-y<=18);
    if(fit) return {club:fit+" smooth",chip:fit,zone:"ok",cue:"ONE MORE CLUB — SMOOTH",note:`${eff(fit)}y carry${tag(fit)} finishes at/past center. ${fit==="8i"?"Fairway lie only (rough → 9i).":"Stand closer, full setup."}`,color:"#30d158"};
    const max=live[live.length-1];
    if(max&&y<=eff(max)+8) return {club:max+" smooth",chip:max,zone:"ok",cue:"SMOOTH — STAND CLOSER",note:`Biggest trusted club${tag(max)}. Center green, accept a touch short.`,color:"#30d158"};
    if(max&&y<=eff(max)+25) return {club:max+" smooth (short ok)",chip:max,zone:"warn",cue:"ADVANCE — DON'T FORCE",note:"Beyond the windows. Smooth the biggest trusted club; short-center is fine.",color:"#ff9f0a"};
    if(max) return {club:max+" — advance",chip:max,zone:"adv",cue:"POSITION SHOT — SMOOTH",note:`Too far to attack. Advance ~${eff(max)}y with a smooth swing and re-plan — the book's sequence has this covered.`,color:"#5b8def"};
    return null;
  };
  const layup=(y)=>Object.keys(P.carries).filter(k=>!out(k)&&eff(k)<=168).sort((a,b)=>eff(a)-eff(b)).map(k=>{
    const rem=y-eff(k); if(rem<20) return null;
    const r=rec(rem); if(!r) return null;
    return {k,carry:eff(k),rem,r,s:r.zone==="ok"?0:r.zone==="i35"?1:r.zone==="warn"?2:3};
  }).filter(Boolean).sort((a,b)=>a.s-b.s||a.rem-b.rem).slice(0,2);
  // pick(y): the club decision for the WHOLE bag (driver/woods included), used by
  // the whisper flow. Short scoring distances use the wedge windows; everything
  // else takes enough club to reach, and flags reach=false when nothing gets home.
  // rel(fam) -> 0..100 reliability from the player's dispersion / direction /
  // consistency data (supplied by the caller). Defaults to "trusted" when we have
  // no data yet, so a fresh bag still works.
  const pick=(y,rel)=>{
    const R=k=>rel?rel(k):70, SHAKY=55;
    const bag=Object.keys(P.carries).filter(k=>!out(k)).sort((a,b)=>eff(a)-eff(b));
    if(!y||y<=0) return {chip:bag[0]||"7i",fam:bag[0]||"7i",reach:false,leaves:0,carry:0,shaky:false};
    if(y<=34){ const r=rec(y); return {chip:r.chip,fam:"chip",reach:true,leaves:0,carry:chipCarry(r.chip),shaky:false}; }
    if(y<=W.fs[1]&&!out("52")){ const r=rec(y); return {chip:r.chip,fam:"52",reach:true,leaves:0,carry:chipCarry(r.chip),shaky:R("52")<SHAKY}; }
    if(!bag.length) return {chip:"7i",fam:"7i",reach:false,leaves:y,carry:0,shaky:false};
    // Clubs that get to the number within a sensible window (not wildly over).
    const window=bag.filter(k=>eff(k)>=y-6&&eff(k)<=y+18);
    if(window.length){
      // Prefer the most reliable club that does the job; tie-break to less club.
      const k=window.slice().sort((a,b)=>(R(b)-R(a))||(eff(a)-eff(b)))[0];
      return {chip:k,fam:k,reach:true,leaves:Math.max(0,y-eff(k)),carry:eff(k),shaky:R(k)<SHAKY};
    }
    // Gap (no club lands near the number): take just enough club.
    const reachK=bag.filter(k=>eff(k)>=y-6);
    if(reachK.length){ const k=reachK[0];
      return {chip:k,fam:k,reach:true,leaves:Math.max(0,y-eff(k)),carry:eff(k),shaky:R(k)<SHAKY}; }
    // Can't get home with anything -> longest club to advance (flag if it's wild).
    const k=bag[bag.length-1];
    return {chip:k,fam:k,reach:false,leaves:y-eff(k),carry:eff(k),shaky:R(k)<SHAKY};
  };
  return {rec,layup,chipCarry,eff,pick};
};

const store = {
  async get(k){try{const r=await window.storage.get(k);return r?JSON.parse(r.value):null;}catch(e){return null;}},
  async set(k,v){try{await window.storage.set(k,JSON.stringify(v));}catch(e){}}
};

// ================= SC4 PRO / LAUNCH-MONITOR IMPORTER =================
// Upload a CSV → we auto-detect the columns, recognize the clubs, drop bad data
// and duplicates, and derive stock carries + reliability. The golfer never has to
// think "what format is this?" — they plug in their data and the caddie learns.
// NOTE: SC4 Pro exports include side-carry tracing and spin axis (left/right spin),
// so we DO learn each club's miss side — preferring measured offline yards, falling
// back to spin-axis direction. If a file has neither, we simply omit side (never
// invent one).
const IMP_FIELDS={
  club:["club","club type","clubtype","club name","selected club"],
  carry:["carry","carry distance","carry dist"],
  total:["total","total distance","distance","swing distance","dist"],
  ball:["ball speed","ballspeed","ball","bs"],
  clubspd:["club speed","clubspeed","club head speed","swing speed","chs"],
  smash:["smash","smash factor","efficiency"],
  spin:["spin","spin rate","backspin","total spin"],
  side:["side","side carry","side total","side distance","offline","off line","lateral","l/r","curve","carry side"],
  axis:["spin axis","spinaxis","side spin","sidespin","side angle","launch direction","horizontal launch","direction","axis"],
  date:["date","time","timestamp","datetime","date/time","shot time"]
};
const impNorm=h=>String(h||"").replace(/^﻿/,"").toLowerCase().replace(/[()]/g," ").replace(/[_\-]/g," ")
  .replace(/\b(yd|yds|yards|yard|mph|rpm|deg|degrees|ft|feet|m)\b/g," ")
  .replace(/[^a-z0-9 /]/g," ").replace(/\s+/g," ").trim();
function impLoftWedge(deg){
  if(deg>=44&&deg<=48) return "PW";
  if(deg>=49&&deg<=53) return {money:true};   // the 52° scoring-wedge family (w52)
  if(deg>=54&&deg<=57) return "SW";
  if(deg>=58&&deg<=64) return "LW";
  return null;
}
function impRecognizeClub(raw){
  if(raw==null) return null;
  let s=String(raw).trim().toLowerCase().replace(/°/g,"").replace(/\s+/g," ");
  s=s.replace(/\s*-.*$/,"").trim();   // SC4 tags clubs like "9i - " / "GW - " — drop the tag
  if(!s) return null;
  const a={"driver":"Dr","dr":"Dr","d":"Dr","1w":"Dr","1 wood":"Dr","3 wood":"3W","3w":"3W",
    "5 wood":"5W","5w":"5W","7 wood":"7W","7w":"7W","pw":"PW","pitching wedge":"PW",
    "gw":"52m","gap wedge":"52m","aw":"52m","a":"52m","approach":"52m",
    "sw":"SW","sand wedge":"SW","lw":"LW","lob wedge":"LW"};
  if(a[s]) return a[s]==="52m"?{money:true}:a[s];
  let m=s.match(/^(\d{1,2})$/);
  if(m){const n=+m[1]; if(n>=1&&n<=9) return n+"i"; return impLoftWedge(n);}
  m=s.match(/^(\d{1,2})\s*(i|iron|irons|h|hy|hyb|hybrid|w|wd|wood|woods)?$/);
  if(m){const n=+m[1],t=m[2]||"i";
    const suf=/^(h|hy|hyb|hybrid)/.test(t)?"H":/^(w|wd|wood)/.test(t)?"W":"i";
    if(suf==="W"&&n===1) return "Dr"; return n+suf;}
  m=s.match(/^(\d{2})\s*(deg|degree|degrees)$/);
  if(m) return impLoftWedge(+m[1]);
  return null;
}
function impSplit(line){const out=[];let cur="",q=false;
  for(let i=0;i<line.length;i++){const ch=line[i];
    if(q){ if(ch==='"'){ if(line[i+1]==='"'){cur+='"';i++;} else q=false; } else cur+=ch; }
    else { if(ch==='"') q=true; else if(ch===","||ch==="\t"||ch===";"){out.push(cur);cur="";} else cur+=ch; }}
  out.push(cur); return out;}
const impNum=v=>{if(v==null)return null;const s=String(v).replace(/[^0-9.\-]/g,"");
  if(s===""||s==="-"||s===".")return null;const n=parseFloat(s);return isNaN(n)?null:n;};
// Signed lateral value: RIGHT = positive, LEFT = negative. Handles "R12","8L",
// "-8","+3", "Left 6" — however the monitor codes offline / spin-axis direction.
const impSide=v=>{if(v==null)return null;const raw=String(v).trim().toLowerCase();
  if(!raw||raw==="-"||raw==="0")return raw==="0"?0:null;
  const n=impNum(raw); if(n===null)return null;
  if(/(^|[^a-z])l|left/.test(raw)&&n>0) return -Math.abs(n);   // L / left  -> negative
  if(/(^|[^a-z])r|right/.test(raw)) return Math.abs(n);         // R / right -> positive
  return n;};
function impParse(text){
  if(!text||!text.trim()) return {ok:false,error:"That file looks empty."};
  const lines=text.split(/\r\n|\r|\n/).filter(l=>l.trim()!=="");
  if(lines.length<2) return {ok:false,error:"No shots found — the file has no data rows."};
  const grid=lines.map(impSplit);
  let hIdx=0,hScore=0;
  for(let r=0;r<Math.min(grid.length,8);r++){let sc=0;
    grid[r].forEach(c=>{const n=impNorm(c);for(const f in IMP_FIELDS){if(IMP_FIELDS[f].includes(n)){sc++;break;}}});
    if(sc>hScore){hScore=sc;hIdx=r;}}
  const header=grid[hScore>=2?hIdx:0];
  const cols={}; header.forEach((c,idx)=>{const n=impNorm(c);
    for(const f in IMP_FIELDS){if(cols[f]===undefined&&IMP_FIELDS[f].includes(n))cols[f]=idx;}});
  if(cols.carry===undefined&&cols.total===undefined)
    return {ok:false,error:"Couldn't find a distance column (carry or total). Columns seen: "+header.join(", ")};
  const rows=[];
  for(let i=(hScore>=2?hIdx:0)+1;i<grid.length;i++){const c=grid[i];
    if(c.length===1&&c[0].trim()==="")continue;
    let carry=cols.carry!==undefined?impNum(c[cols.carry]):null;
    let total=cols.total!==undefined?impNum(c[cols.total]):null;
    if(carry===null&&total!==null)carry=total; if(total===null&&carry!==null)total=carry;
    const rawClub=cols.club!==undefined?String(c[cols.club]||"").trim():"";
    rows.push({rawClub,club:impRecognizeClub(rawClub),carry,total,
      ball:cols.ball!==undefined?impNum(c[cols.ball]):null,
      clubspd:cols.clubspd!==undefined?impNum(c[cols.clubspd]):null,
      smash:cols.smash!==undefined?impNum(c[cols.smash]):null,
      side:cols.side!==undefined?impSide(c[cols.side]):null,
      axis:cols.axis!==undefined?impSide(c[cols.axis]):null,
      date:cols.date!==undefined?String(c[cols.date]||"").trim():""});}
  return {ok:true,rows,columns:cols,hasSide:cols.side!==undefined||cols.axis!==undefined};
}
const impMed=a=>{const s=a.slice().sort((x,y)=>x-y);const m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;};
const impQ=(a,q)=>{const s=a.slice().sort((x,y)=>x-y);const p=(s.length-1)*q,b=Math.floor(p),r=p-b;
  return s[b+1]!==undefined?s[b]+r*(s[b+1]-s[b]):s[b];};
// Effort windows (half / three-quarter / full) for the scoring wedge. The SC4 export
// doesn't label swing effort, so we INFER it: exclude short chips, then split the
// committed wedge carries into three distance bands. Effort tracks carry (and, on
// this monitor, club speed), so the low band is the half swing and the high band the
// full swing. Returns null when there aren't enough shots to split reliably.
const impWindows=carries=>{
  const cs=carries.filter(c=>c>=35).sort((a,b)=>a-b);
  if(cs.length<9) return null;
  const band=a=>[Math.round(impQ(a,0.25)),Math.round(impQ(a,0.75))];
  const t=Math.floor(cs.length/3);
  const w={half:band(cs.slice(0,t)),tq:band(cs.slice(t,2*t)),fs:band(cs.slice(2*t))};
  return (w.half[1]<=w.tq[1]&&w.tq[1]<=w.fs[1])?w:null;   // sane, monotonic bands only
};
function impClean(rows){
  const removed={unusable:0,impossible:0,duplicate:0,mishit:0};
  const seen=new Set(); const step=[];
  for(const r of rows){
    if(r.carry===null||r.carry<=0){removed.unusable++;continue;}
    if(r.carry>400||(r.ball!==null&&r.ball>240)||(r.smash!==null&&(r.smash>1.7||r.smash<0.5))){removed.impossible++;continue;}
    const key=[r.date,r.rawClub,r.carry,r.ball].join("|");
    if(seen.has(key)){removed.duplicate++;continue;} seen.add(key); step.push(r);}
  const keyOf=c=>c==null?null:(typeof c==="object"?"52m":c);
  const groups={},unknown=[];
  for(const r of step){const k=keyOf(r.club); if(k===null){unknown.push(r.rawClub);continue;} (groups[k]=groups[k]||[]).push(r);}
  const clubs={};
  for(const k in groups){const arr=groups[k];const med=impMed(arr.map(r=>r.carry));
    const kept=arr.filter(r=>{const bad=r.carry<0.55*med; if(bad)removed.mishit++; return !bad;});
    if(!kept.length)continue; const cs=kept.map(r=>r.carry);const m2=impMed(cs);
    // Left/right miss: prefer measured offline yards (side); fall back to spin-axis
    // direction (left/right spin) when the file only has curve, not tracing.
    const sideYds=kept.map(r=>r.side).filter(v=>v!=null);
    const axisDeg=kept.map(r=>r.axis).filter(v=>v!=null);
    const useYds=sideYds.length>=3; const src=useYds?sideYds:(axisDeg.length>=3?axisDeg:null);
    let side=null;
    if(src){const right=src.filter(v=>v>2).length,left=src.filter(v=>v<-2).length,tot=right+left;
      if(tot>=3){const dir=right>=left?"R":"L";
        side={dir,pct:Math.round(Math.max(right,left)/tot*100),med:Math.round(impMed(src)),
          unit:useYds?"y":"°",basis:useYds?"tracing":"spin axis",n:tot};}}
    const spds=kept.map(r=>r.clubspd).filter(v=>v!=null&&v>0);
    const spd=spds.length>=3?{lo:Math.round(impQ(spds,0.2)),hi:Math.round(impQ(spds,0.8))}:null;
    clubs[k]={n:kept.length,carry:Math.round(m2),lowN:Math.round(impQ(cs,0.2)),hiN:Math.round(impQ(cs,0.8)),
      sd:Math.round(Math.sqrt(cs.reduce((a,b)=>a+(b-m2)*(b-m2),0)/cs.length)),
      shortRate:Math.round(cs.filter(c=>c<m2-8).length/cs.length*100),side,
      spdLo:spd?spd.lo:null,spdHi:spd?spd.hi:null,
      windows:k==="52m"?impWindows(cs):null};}   // inferred half/¾/full for the scoring wedge
  return {clubs,removed,unknownLabels:[...new Set(unknown.filter(Boolean))],kept:step.length};
}
const IMP_ORDER=["Dr","2W","3W","4W","5W","7W","9W","1H","2H","3H","4H","5H","6H",
  "2i","3i","4i","5i","6i","7i","8i","9i","PW","SW","LW"];
function impToProfile(clubs){
  const carries={}; for(const k of IMP_ORDER){if(clubs[k])carries[k]=clubs[k].carry;}
  const mw=clubs["52m"];
  // Full effort windows when we could infer them, else just the full-smooth window.
  const w52=mw?(mw.windows||{fs:[mw.lowN,mw.hiN]}):null;
  const w52fs=mw?[mw.lowN,mw.hiN]:null;   // kept for backward compatibility
  return {carries,w52,w52fs};
}
// ====================================================================

const mapCarry=(c,P)=>{const fm=famOf(c);if(fm==="52")return c.includes("½")?62:c.includes("¾")?82:88;if(fm==="chip")return 22;return P.carries[fm]||100;};
const MiniMap=({h,P,plan})=>{const uw=268;const tx=d=>16+Math.min(d/h.y,1)*uw;
  const hz=h.hz.toUpperCase();const bands=[];
  if(hz.includes("LEFT"))bands.push({top:true,water:hz.includes("WATER")||hz.includes("CREEK")||hz.includes("POND")});
  if(hz.includes("RIGHT"))bands.push({top:false,water:hz.includes("WATER")||hz.includes("POND")});
  let cum=0;const pts=(plan||h.plan||[]).map(p=>{cum+=mapCarry(p.c,P);return{x:tx(Math.min(cum,h.y)),c:p.c.split(" ")[0]};});
  return (<svg viewBox="0 0 300 66" style={{width:"100%",display:"block",margin:"6px 0"}}>
    <rect x={16} y={25} width={uw} height={15} rx={7} fill="#3f6b52"/>
    {bands.map((b,i)=><rect key={i} x={16} y={b.top?15:42} width={uw} height={7} rx={3} fill={b.water?"#3b82f6":"#ef4444"} opacity={0.85}/>)}
    <rect x={7} y={21} width={13} height={23} rx={3} fill="#0f2b20" stroke="white" strokeWidth={1}/>
    <circle cx={16+uw} cy={32} r={10} fill="#30d158" stroke="white" strokeWidth={1.5}/>
    {pts.map((p,i)=>(<g key={i}><circle cx={p.x} cy={32} r={6.5} fill="#fcd34d" stroke="#0f2b20" strokeWidth={1}/><text x={p.x} y={35} textAnchor="middle" fontSize={6.5} fontWeight={800} fill="#0f2b20">{i+1}</text><text x={p.x} y={60} textAnchor="middle" fontSize={7} fill="#9fd6b4" fontWeight={700}>{p.c}</text></g>))}
  </svg>);};

// Smooth an array of [x,y] pixel points into an SVG path (Catmull-Rom → Bézier).
const smoothPath=pts=>{ if(pts.length<2) return "";
  if(pts.length===2) return `M ${pts[0][0]} ${pts[0][1]} L ${pts[1][0]} ${pts[1][1]}`;
  let d=`M ${pts[0][0]} ${pts[0][1]}`;
  for(let i=0;i<pts.length-1;i++){const p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||pts[i+1];
    const c1x=p1[0]+(p2[0]-p0[0])/6,c1y=p1[1]+(p2[1]-p0[1])/6,c2x=p2[0]-(p3[0]-p1[0])/6,c2y=p2[1]-(p3[1]-p1[1])/6;
    d+=` C ${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${p2[0]} ${p2[1]}`;}
  return d;};

// Normalized centerline x (0..1, left→right) at depth d (0..1, tee→green).
// Hole geometry (centerX / holeContext / lieAt) now lives in the pure geometry.js
// module, so the map and the decision engine read ONE source of truth. Imported above.

// Yardage for a hole from the chosen tee (falls back to the hole's flag distance).
const TEES=[["blue","Blue"],["white","White"],["gold","Gold"],["red","Red"],["green","Green"]];
const teeYardOf=(h,t)=>(h&&h.tees&&t&&h.tees[t]!=null)?h.tees[t]:(h?h.y:0);

// HoleView — the automatic strategic overview. A clean schematic (not satellite):
// the fairway BENDS along the hole's real centerline (h.path), hazards are drawn
// per side and per section (h.hazards) and look like what they are — trees as
// canopy, water as soft pools, sand as bunkers. The same geometry the engine can
// read for angle-aware decisions. Falls back to hz text for un-mapped holes.
// When onPlace is given, the map becomes tappable: a tap drops the ball marker and
// reports normalized (d,x) back so the engine learns where the shot finished.
const HoleView=({h,P,ball,onPlace,shots,target,dispersion,tee,compact,big})=>{
  const HZ=(h.hz||"").toUpperCase();
  const W=220,Ht=300,L=28,Rr=192,uw=Rr-L,teeY=254,greenY=48,span=teeY-greenY;
  const yAt=d=>teeY-Math.max(0,Math.min(1,d))*span;                 // d 0..1 (tee→green) → y
  const xAt=x=>L+Math.max(0,Math.min(1,x))*uw;                      // x 0..1 (left→right) → X
  // Centerline: use h.path ([d,x] points) if mapped, else straight / dogleg from text.
  let path=Array.isArray(h.path)&&h.path.length>=2?h.path:null;
  if(!path){const dog=/DOGLEG LEFT/.test(HZ)?-1:/DOGLEG RIGHT/.test(HZ)?1:0;
    path=dog?[[0,0.5],[0.5,0.5+dog*0.2],[1,0.5+dog*0.04]]:[[0,0.5],[1,0.5]];}
  const cxAt=d=>{for(let i=0;i<path.length-1;i++){const[d0,x0]=path[i],[d1,x1]=path[i+1];
    if(d<=d1||i===path.length-2){const t=Math.max(0,Math.min(1,(d-d0)/((d1-d0)||1)));return xAt(x0+(x1-x0)*t);}}return xAt(path[path.length-1][1]);};
  const px=path.map(([d,x])=>[xAt(x),yAt(d)]);
  const narrow=/TIGHT|NARROW|CHUTE|CORRIDOR|THREAD|SLALOM/.test(HZ);
  const fwW=narrow?22:34, off=fwW/2+11;
  // Hazards: structured list if mapped, else derived from dzL/dzR + hz side words.
  const dzType=v=>({trees:"trees",water:"water",sand:"sand",houses:"houses",waste:"sand"}[v]||v);
  let hazards=Array.isArray(h.hazards)?h.hazards:null;
  if(!hazards){hazards=[];
    const t=/WATER|CREEK|POND|LAKE|DITCH|GULLY/.test(HZ)?"water":/BUNKER|SAND|WASTE/.test(HZ)?"sand":/HOUSE|ROAD|HIGHWAY/.test(HZ)?"houses":/\bOB\b/.test(HZ)?"houses":"trees";
    if(h.dzL||/LEFT/.test(HZ)) hazards.push({side:"L",type:dzType(h.dzL)||t,from:0,to:1});
    if(h.dzR||/RIGHT/.test(HZ)) hazards.push({side:"R",type:dzType(h.dzR)||t,from:0,to:1});}
  const maxTee=Math.max(0,...Object.values(P.carries||{}));
  const lzD=maxTee&&maxTee<h.y?maxTee/h.y:null;
  const near=/BUNKER|SAND/.test(HZ)||(h.green&&/bunker/i.test(h.green.guard||""));
  const COL={trees:["#37573f","#5f8560"],water:["#7ba7c9","#a9cbe1"],sand:["#d9c48c","#e7d7ad"],houses:["#b3a996","#c8c0b0"]};
  const blob=(x,y,type,k)=>{const[c1,c2]=COL[type]||COL.trees;
    if(type==="water")return <circle key={k} cx={x} cy={y} r={8} fill={c1} opacity={0.9}/>;
    if(type==="sand")return <ellipse key={k} cx={x} cy={y} rx={8} ry={5.5} fill={c1}/>;
    if(type==="houses")return <rect key={k} x={x-6} y={y-6} width={12} height={12} rx={2} fill={c1}/>;
    return <g key={k}><circle cx={x} cy={y} r={9} fill={c1}/><circle cx={x-3} cy={y-3} r={4.5} fill={c2} opacity={0.8}/></g>;};
  // A "pool" hazard is a positioned water/sand BODY, not a side band: pool:[d0,d1,x0,x1]
  // in normalized coords. It's filled with the same small circles as the side hazards
  // (that look stays), just packed across the whole area so a pond reads as a broad
  // body of water rather than a thin creek down one edge.
  const pools=hazards.filter(hz=>Array.isArray(hz.pool));
  const bandHaz=hazards.filter(hz=>!Array.isArray(hz.pool));
  const poolEls=[];
  pools.forEach((hz,i)=>{const[d0,d1,x0,x1]=hz.pool;
    const X0=xAt(Math.min(x0,x1)),X1=xAt(Math.max(x0,x1));
    const Y0=yAt(Math.max(d0,d1)),Y1=yAt(Math.min(d0,d1));   // Y0 top → Y1 bottom
    const cxp=(X0+X1)/2,cyp=(Y0+Y1)/2,rxp=(X1-X0)/2||1,ryp=(Y1-Y0)/2||1;
    const type=dzType(hz.type),step=14;
    for(let yy=Y0;yy<=Y1;yy+=step)for(let xx=X0;xx<=X1;xx+=step){
      const nx=(xx-cxp)/rxp,ny=(yy-cyp)/ryp; if(nx*nx+ny*ny>1.03)continue;   // clip to an ellipse
      const jx=((i*7+Math.round(xx)*3+Math.round(yy))%5)-2, jy=((i*3+Math.round(yy)*2+Math.round(xx))%5)-2;
      poolEls.push(blob(xx+jx,yy+jy,type,"pl"+i+"_"+Math.round(xx)+"_"+Math.round(yy)));
    }});
  // sample the remaining side-band hazards into blobs that hug the bending corridor
  const feats=[];
  bandHaz.forEach((hz,hi)=>{const s=hz.side==="L"?-1:1;const from=hz.from??0,to=hz.to??1;
    const n=Math.max(2,Math.round((to-from)*13));
    for(let k=0;k<=n;k++){const d=from+(to-from)*k/n;const x=cxAt(d)+s*off;const y=yAt(d);feats.push(blob(x,y,dzType(hz.type),hi+"_"+k));}});
  // Split tees: a shorter tee sits FORWARD up the hole. Derive each tee's spot from
  // its yardage vs the back tee, so the selected tee's box shows where you actually
  // play from (e.g. Hole 2's forward tees sit across the water).
  const teeVals=h.tees?["blue","white","gold","red","green"].filter(k=>h.tees[k]!=null):[];
  const maxTeeYd=teeVals.length?Math.max(...teeVals.map(k=>h.tees[k])):0;
  const teeDof=k=>(maxTeeYd&&h.tees&&h.tees[k]!=null)?Math.max(0,Math.min(0.55,(maxTeeYd-h.tees[k])/maxTeeYd)):0;
  const teeD=tee?teeDof(tee):0;
  const gx=cxAt(1),gy=greenY,tx=cxAt(teeD),ty=yAt(teeD);
  // Tap → normalized (d,x): invert yAt/xAt using the SVG's own coordinate box.
  const handleTap=onPlace?e=>{const svg=e.currentTarget;const r=svg.getBoundingClientRect();
    const px=(e.clientX-r.left)/r.width*W, py=(e.clientY-r.top)/r.height*Ht;
    const x=Math.max(0,Math.min(1,(px-L)/uw)), d=Math.max(0,Math.min(1,(teeY-py)/span));
    onPlace(d,x);}:undefined;
  const bx=ball?xAt(ball.x):null, by=ball?yAt(ball.d):null;
  // Shot-by-shot path: tee → each recorded position → the current ball. A visual
  // record of the hole as it actually played out.
  const shotPts=(shots||[]).filter(s=>s.atD!=null).map(s=>[xAt(s.atX),yAt(s.atD)]);
  const pathPts=[[tx,ty],...shotPts]; if(ball) pathPts.push([bx,by]);
  return (<svg viewBox={`0 0 ${W} ${Ht}`} onClick={handleTap} style={{width:"100%",maxWidth:big?"min(94vw,440px)":compact?190:300,maxHeight:big?"74vh":compact?"min(184px,29vh)":"none",display:"block",margin:"0 auto",cursor:onPlace?"crosshair":"default"}}>
    <rect x={0} y={0} width={W} height={Ht} rx={18} fill="#eef1ea"/>
    {/* bending fairway corridor */}
    <path d={smoothPath(px)} fill="none" stroke="#cddbc9" strokeWidth={fwW+11} strokeLinecap="round" strokeLinejoin="round"/>
    <path d={smoothPath(px)} fill="none" stroke="#9dc0a1" strokeWidth={fwW} strokeLinecap="round" strokeLinejoin="round"/>
    {/* water/sand bodies (ponds) drawn over the ground, then side-band hazards */}
    {poolEls}
    {/* hazards */}
    {feats}
    {/* forced carry line (perpendicular-ish across the corridor at the carry distance) */}
    {h.carry&&h.carry<h.y&&(()=>{const d=h.carry/h.y,x=cxAt(d),y=yAt(d);return <g><line x1={x-fwW/2-7} y1={y} x2={x+fwW/2+7} y2={y} stroke="#7ba7c9" strokeWidth={6} strokeLinecap="round"/><text x={x} y={y-7} textAnchor="middle" fontSize={9} fill="#4a6d86" fontWeight={700}>{h.carryLabel||"carry"} {h.carry}</text></g>;})()}
    {/* player's landing zone */}
    {/* tees — faint boxes for the other sets, solid for the one you're playing */}
    {tee&&teeVals.filter(k=>k!==tee).map(k=>{const d=teeDof(k),x=cxAt(d),yy=yAt(d);
      return <rect key={"t"+k} x={x-7} y={yy-3} width={14} height={6} rx={2} fill="#233b30" opacity={0.22}/>;})}
    <rect x={tx-10} y={ty-4} width={20} height={9} rx={2} fill="#233b30"/>
    <text x={tx} y={ty+16} textAnchor="middle" fontSize={9} fill="#6b7d72" fontWeight={700}>{tee?tee.toUpperCase():"TEE"}</text>
    {/* greenside bunkers */}
    {near&&<><ellipse cx={gx-23} cy={gy+5} rx={9} ry={6} fill="#d9c48c"/><ellipse cx={gx+23} cy={gy+8} rx={8} ry={5} fill="#d9c48c"/></>}
    {/* green */}
    <circle cx={gx} cy={gy} r={16} fill="#6fae7c" stroke="#3c6a49" strokeWidth={2}/>
    <circle cx={gx} cy={gy} r={2.5} fill="#233b30"/>
    <text x={gx} y={gy-21} textAnchor="middle" fontSize={9} fill="#3c6a49" fontWeight={800}>GREEN</text>
    {/* shot path — the round as it played */}
    {pathPts.length>=2&&<><polyline points={pathPts.map(p=>p.join(",")).join(" ")} fill="none" stroke="#a3402f" strokeWidth={2} strokeDasharray="4 3" opacity={0.75}/>
      {shotPts.map(([x,y],i)=><circle key={"sp"+i} cx={x} cy={y} r={3.5} fill="#a3402f" opacity={0.8}/>)}</>}
    {/* dispersion footprint — the honest scatter this club/flight produces for THIS
        golfer, so the map answers "why does this target fit me?" (no false precision) */}
    {dispersion&&(()=>{const dX=xAt(dispersion.x),dY=yAt(dispersion.d);
      const rx=Math.max(9,(dispersion.rx||0.14)*uw), ry=Math.max(9,(dispersion.ry||0.06)*span);
      return <ellipse cx={dX} cy={dY} rx={rx} ry={ry} fill="rgba(111,174,124,0.22)" stroke="#6fae7c" strokeWidth={1.5} strokeDasharray="3 3"/>;})()}
    {/* aim target — the caddie's intended landing center */}
    {target&&(()=>{const tgX=xAt(target.x),tgY=yAt(target.d);return <g>
      <circle cx={tgX} cy={tgY} r={9} fill="rgba(200,162,74,0.22)" stroke="#c8a24a" strokeWidth={2.5}/>
      <line x1={tgX-13} y1={tgY} x2={tgX+13} y2={tgY} stroke="#c8a24a" strokeWidth={2}/>
      <line x1={tgX} y1={tgY-13} x2={tgX} y2={tgY+13} stroke="#c8a24a" strokeWidth={2}/>
      {target.label&&<text x={tgX} y={tgY-15} textAnchor="middle" fontSize={9} fill="#8a7327" fontWeight={800}>{target.label}</text>}</g>;})()}
    {/* placed ball — where the shot finished */}
    {ball&&<g><circle cx={bx} cy={by} r={7} fill="#fff" stroke="#a3402f" strokeWidth={2.5}/><circle cx={bx} cy={by} r={2.5} fill="#a3402f"/>
      <text x={bx} y={by-11} textAnchor="middle" fontSize={8.5} fill="#a3402f" fontWeight={800}>ball</text></g>}
  </svg>);
};

const S = {
  card:{background:"white",borderRadius:16,padding:14,marginBottom:10,boxShadow:"0 1px 4px rgba(0,0,0,0.07)",boxSizing:"border-box",width:"100%"},
  h:{fontSize:10,letterSpacing:1.4,fontWeight:700,color:"#8a8a8e",textTransform:"uppercase",marginBottom:6},
  big:{fontSize:24,fontWeight:800,color:"#111",letterSpacing:-0.4,lineHeight:1.15},
  sub:{fontSize:13,color:"#3a3a3c",lineHeight:1.45},
  btn:{border:"none",borderRadius:12,padding:"13px 14px",fontSize:15,fontWeight:700,cursor:"pointer"},
  inp:{padding:"11px 12px",fontSize:16,fontWeight:700,border:"2px solid #d1d1d6",borderRadius:12,boxSizing:"border-box",background:"white",minWidth:0},
  pill:(bg,fg)=>({display:"inline-block",background:bg,color:fg,borderRadius:20,padding:"3px 10px",fontSize:11,fontWeight:800}),
};
// One full-width objection button (the "Not comfortable?" panel).
const objBtn={display:"block",width:"100%",textAlign:"left",border:"1px solid #e7e2d8",background:"#fbfaf7",borderRadius:12,padding:"12px 13px",marginBottom:8,cursor:"pointer",fontSize:15,fontWeight:700,color:"#233b30"};

// The Whisper aesthetic: a caddie's leather yardage book meets a meditation app.
const PINE="#122b21", PAPER="#faf8f4", GOLD="#c8a24a", INK="#233b30", MUTE="#6b7d72";
const SERIF="Georgia,'Iowan Old Style','Palatino Linotype',serif";
const arrive={animation:"whisperIn .22s ease both"};
const WSTYLE=`@keyframes whisperIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.tapbtn{transition:transform .08s ease, filter .08s ease}
.tapbtn:active{transform:scale(.95);filter:brightness(.94)}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.tapbtn{transition:none}}`;
const buzz=()=>{try{navigator.vibrate&&navigator.vibrate(12);}catch(e){}};
// P3: how much longer a shot plays from each lie (ball comes out shorter, so you
// need more club). 1.0 = a clean fairway lie. Used to inflate the target yardage
// before picking a club, so recommendations reflect the real lie, not a perfect one.
const LIE_FACTOR={FW:1,FRINGE:1,FIRST:1.03,ROUGH:1.08,DEEP:1.18,SAND:1.06,FBUNK:1.06,TREES:1.0,DIRT:1.02,HARD:1.02,PINE:1.03};
const lieFactor=l=>LIE_FACTOR[l]||1;
const lieName={FW:"fairway",FRINGE:"fringe",FIRST:"first cut",ROUGH:"rough",DEEP:"deep rough",SAND:"bunker",FBUNK:"fairway bunker",TREES:"recovery",DIRT:"bare lie",HARD:"hardpan",PINE:"pine straw"};

export default function CaddieOS(){
  const [tab,setTab]=useState("caddie");
  const [asked,setAsked]=useState(false);        // whisper flow: has the player asked this shot?
  const [askObs,setAskObs]=useState(false);      // route-observation prompt (only when material)
  const [awaitResult,setAwaitResult]=useState(false); // waiting for the six-zone result tap
  const [awaitDrop,setAwaitDrop]=useState(null);   // after water: {dir} → tap the map to place the drop
  const [dropPos,setDropPos]=useState(null);       // pending drop position {d,x} from the map tap
  const [qYards,setQYards]=useState("");          // question-screen yardage entry
  const [lieLabel,setLieLabel]=useState("Fairway"); // which lie chip is lit (Tee vs Fairway both map to FW)
  const [showAlt,setShowAlt]=useState(false);     // "something else?" expander
  const [prepOpen,setPrepOpen]=useState(false);   // pre-round PREP card
  const [pendingLie,setPendingLie]=useState(null); // [lieVal,label] carried from last shot's result
  const [resDir,setResDir]=useState("line");       // richer result: direction selection
  const [editShot,setEditShot]=useState(null);     // index into live.shots being reviewed/edited
  const [P,setP]=useState(DEF_PROFILE);
  const [rounds,setRounds]=useState([]);
  const [loaded,setLoaded]=useState(false);
  const [live,setLive]=useState(null);
  const [atInput,setAtInput]=useState("");
  const [sel,setSel]=useState(null);
  const [courseHole,setCourseHole]=useState(0);
  const [prepSec,setPrepSec]=useState("body");
  const [meMsg,setMeMsg]=useState("");
  const [impTxt,setImpTxt]=useState("");
  const [editIdx,setEditIdx]=useState(null);
  const [trMsg,setTrMsg]=useState("");
  const [endArm,setEndArm]=useState(false);
  const [delArm,setDelArm]=useState(null);
  const [newName,setNewName]=useState("");
  const [newCarry,setNewCarry]=useState("");
  const [courseSel,setCourseSel]=useState("bpmapped");   // the mapped Bay Pointe is the default
  const [teeSel,setTeeSel]=useState("white");   // chosen tee set (applies to the whole round)
  const undoRef=useRef(false);                   // Back-button undo sets this so the reset effect skips
  const [mapExpanded,setMapExpanded]=useState(false);   // full-screen map for placing the ball
  const [viewHole,setViewHole]=useState(null);
  const [teeIn,setTeeIn]=useState("");
  const [tourn,setTourn]=useState(false);
  const [lie,setLie]=useState("FW");
  const [wind,setWind]=useState("NONE");
  const [dir,setDir]=useState(null);
  const [decision,setDecision]=useState(null);  // the play-first engine's full recommendation
  const [obsv,setObsv]=useState(null);          // golfer's route observation (only when material)
  const [showConf,setShowConf]=useState(false); // expand the confidence detail / "Why?" on the live card
  const [teeEdit,setTeeEdit]=useState(false);            // compact tee correction on the tee shot
  const [firstDecision,setFirstDecision]=useState(null); // the caddie's ORIGINAL call this shot (preserved)
  const [objections,setObjections]=useState([]);         // objections the golfer raised (history)
  const [objExclude,setObjExclude]=useState([]);         // clubs excluded for THIS shot's recompute only
  const [showRep,setShowRep]=useState(false);
  const [imp,setImp]=useState(null);        // staged import awaiting confirmation
  const [impErr,setImpErr]=useState("");
  const [dragOver,setDragOver]=useState(false);
  const [dataArm,setDataArm]=useState(null);       // armed destructive player-data action
  const [impCourses,setImpCourses]=useState({}); // courses imported from Shot Scope reads
  const [holeJson,setHoleJson]=useState("");     // paste box for a hole/course JSON
  const [holeMsg,setHoleMsg]=useState("");
  const courses={...COURSES,...impCourses};        // built-in + imported, used everywhere
  // De-duplicated list for the START picker: the mapped Bay Pointe supersedes the old
  // scripted "bp" (same practical course), so the golfer sees one clean choice.
  const startCourses=Object.entries(courses).filter(([k])=>!(k==="bp"&&courses.bpmapped));
  const undoShot=()=>{
    if(live.onGreen&&live.putts>0){saveLive({...live,putts:live.putts-1});return;}
    const hs=live.shots||[];let idx=-1;
    for(let k=hs.length-1;k>=0;k--){if(hs[k].h===live.hole+1){idx=k;break;}}
    if(idx<0){if(live.onGreen)saveLive({...live,onGreen:false});return;}
    const shot=hs[idx];const shots=hs.slice(0,idx).concat(hs.slice(idx+1));
    if(shot.pen){saveLive({...live,shots,pen:Math.max(0,(live.pen||0)-1)});return;}
    const hh=shots.filter(x=>x.h===live.hole+1);let a=null;hh.forEach((x,k)=>{const left=x.g?0:x.from-x.gain;if(left<=35&&a===null)a=k+1;});
    saveLive({...live,shots,strokes:Math.max(0,live.strokes-1),rem:shot.from,onGreen:false,i35At:a});
  };
  const [obIn,setObIn]=useState("");
  const editLiveHole=(hi,d)=>{const sc=[...live.scores];sc[hi]=Math.max(1,(sc[hi]||CH[hi].tgt)+d);saveLive({...live,scores:sc});};
  const editLivePutts=(hi,d)=>{const pa=[...live.puttsArr];pa[hi]=Math.max(0,(pa[hi]||0)+d);saveLive({...live,puttsArr:pa});};
  const convCycle=hi=>{const cv=[...live.convs];cv[hi]=cv[hi]===true?false:cv[hi]===false?null:true;saveLive({...live,convs:cv});};
  const playHoleNow=i=>{saveLive({...live,hole:i,strokes:0,rem:(live.teeAdj&&live.teeAdj[i])||teeYardOf(CH[i],live.tee),onGreen:false,putts:0,pen:0,i35At:null,teeAck:false});setViewHole(null);};
  // Quick hole change from the landing header — jump straight to that hole's tee.
  const goHole=i=>{if(!live||i<0||i>=CH.length||i===live.hole)return;buzz();playHoleNow(i);};
  // Universal Back — always steps to the previous screen. From the fresh question
  // screen it UNDOES the last shot and reopens its result, so a too-fast tap (wrong
  // lie/direction) is recoverable.
  const goBack=()=>{buzz();
    if(awaitDrop){setAwaitDrop(null);setDropPos(null);return;}
    if(awaitResult){setAwaitResult(false);return;}       // result → the read
    if(asked){setAsked(false);setShowAlt(false);return;} // read → question
    let ns=[...((live&&live.shots)||[])];
    if(ns.length&&ns[ns.length-1].pen) ns=ns.slice(0,-1);   // strip a trailing penalty
    const last=ns[ns.length-1];
    if(last&&!last.pen&&last.h===live.hole+1){              // undo the last struck shot, reopen its result
      ns=ns.slice(0,-1); undoRef.current=true; setSel(last.c); setResDir(last.dir==="L"?"left":last.dir==="R"?"right":"line");
      saveLive({...live,shots:ns,strokes:Math.max(0,live.strokes-1),rem:last.from,onGreen:false,ballX:last.atX!=null?last.atX:null,ballD:last.atD!=null?last.atD:null});
      setAwaitResult(true);
    }};
  const canGoBack=()=>{if(!live)return false;if(awaitDrop||awaitResult||asked)return true;
    return ((live.shots||[]).some(s=>s.h===live.hole+1&&!s.pen));};
  const endSave=()=>{const idx=live.scores.map((sc,i)=>sc!==null?i:-1).filter(i=>i>=0);
    if(idx.length){const rd={date:new Date().toLocaleDateString(),course:courses[live.course]?courses[live.course].name:"",holes:idx.length,total:idx.reduce((a,i)=>a+live.scores[i],0),plan:idx.reduce((a,i)=>a+CH[i].tgt,0),scores:live.scores.map(sc=>sc===null?0:sc),putts:live.puttsArr.reduce((a,b)=>a+(b||0),0),convMade:live.convs.filter(c=>c===true).length,convTried:live.convs.filter(c=>c!==null).length,benched:live.bench||[],shots:live.shots||[]};saveRounds([...rounds,rd]);}
    saveLive(null);store.set("caddie:live",null);setEndArm(false);setTab("trends");};
  const saveRounds=nr=>{setRounds(nr);store.set("caddie:rounds",nr);};
  const editHole=(ri,hi,d)=>{const nr=rounds.map((r,i)=>{if(i!==ri)return r;const sc=[...r.scores];sc[hi]=Math.max(1,(sc[hi]||CH[hi].tgt)+d);return {...r,scores:sc,total:sc.reduce((a,b)=>a+(b||0),0)};});saveRounds(nr);};
  const delRound=ri=>{if(delArm===ri){saveRounds(rounds.filter((_,i)=>i!==ri));setEditIdx(null);setDelArm(null);}else setDelArm(ri);};
  const shareRound=async r=>{
    const txt=`CaddieOS — ${r.course||"Round"} · ${r.date}\nScore ${r.total} (plan ${r.plan}, ${r.total-r.plan>=0?"+":""}${r.total-r.plan}) · ${r.putts} putts · 🎯 ${r.convMade}/${r.convTried} inside-35\nF9: ${r.scores.slice(0,9).join(" ")}  B9: ${r.scores.slice(9).join(" ")}`;
    try{if(navigator.share){await navigator.share({text:txt});setTrMsg("Shared ✓");}else{await navigator.clipboard.writeText(txt);setTrMsg("Copied to clipboard ✓");}}
    catch(e){try{await navigator.clipboard.writeText(txt);setTrMsg("Copied to clipboard ✓");}catch(e2){setTrMsg("Couldn't share on this device");}}
  };
  useEffect(()=>{(async()=>{
    const p=await store.get("caddie:profile"); if(p)setP({...DEF_PROFILE,...p,feels:{...DEF_PROFILE.feels,...(p.feels||{})}});
    const r=await store.get("caddie:rounds"); if(r)setRounds(r);
    const l=await store.get("caddie:live"); if(l)setLive(l);
    const h=await store.get("caddie:holes"); if(h)setImpCourses(h);
    setLoaded(true);})();},[]);
  // Import a hole or a whole course from a Shot Scope read (pasted/loaded JSON).
  // Accepts a single hole object, an array of holes, or {name,holes:[...]}.
  const importHoles=raw=>{
    setHoleMsg("");
    let j; try{ j=JSON.parse(raw); }catch(e){ setHoleMsg("That isn't valid JSON — check for a missing comma or bracket."); return; }
    let name, holes;
    if(Array.isArray(j)){ holes=j; }
    else if(j&&Array.isArray(j.holes)){ holes=j.holes; name=j.name; }
    else if(j&&j.par!=null&&j.y!=null){ holes=[j]; name=j.course; }
    else { setHoleMsg("Expected a hole object, an array of holes, or {name, holes:[…]}."); return; }
    holes=holes.filter(h=>h&&h.par!=null&&h.y!=null).map((h,i)=>({tgt:h.par+1,hz:h.hz||"",vibe:h.vibe||h.strategy||"",cue:h.cue||"",n:h.n||i+1,...h}));
    if(!holes.length){ setHoleMsg("No valid holes found — each hole needs at least par and y (yardage)."); return; }
    const key="ss_"+Date.now().toString(36);
    const next={...impCourses,[key]:{name:name||("Imported course ("+holes.length+")"),holes,imported:true,ref:"flag"}};
    setImpCourses(next); store.set("caddie:holes",next); setCourseSel(key); setHoleJson("");
    setHoleMsg(`Imported ${holes.length} hole${holes.length>1?"s":""} — "${next[key].name}". Pick it on the CADDIE screen to play.`);
  };
  const deleteCourse=key=>{const n={...impCourses};delete n[key];setImpCourses(n);store.set("caddie:holes",n);if(courseSel===key)setCourseSel("bp");};
  const saveLive=l=>{const lv=(l&&typeof l==="object")?{...l,v:SCHEMA}:l;setLive(lv);store.set("caddie:live",lv);};

  // --- Launch-monitor import: read file → parse → clean → stage for confirmation ---
  const handleImportFiles=fileList=>{
    setImpErr(""); setImp(null);
    const file=fileList&&fileList[0];
    if(!file) return;
    if(!/\.(csv|txt|tsv)$/i.test(file.name)){setImpErr("Please drop a .csv export from your launch monitor.");return;}
    const reader=new FileReader();
    reader.onload=()=>{
      const parsed=impParse(String(reader.result));
      if(!parsed.ok){setImpErr(parsed.error);return;}
      const cleaned=impClean(parsed.rows);
      if(!Object.keys(cleaned.clubs).length){setImpErr("Found rows, but no clubs we could recognize. Check the Club column.");return;}
      setImp({fileName:file.name,raw:parsed.rows.length,hasSide:parsed.hasSide,
        clubs:cleaned.clubs,removed:cleaned.removed,unknownLabels:cleaned.unknownLabels,
        patch:impToProfile(cleaned.clubs)});
    };
    reader.onerror=()=>setImpErr("Couldn't read that file.");
    reader.readAsText(file);
  };
  const applyImport=()=>{
    if(!imp) return;
    const carries={...P.carries,...imp.patch.carries};
    const w52=imp.patch.w52?{...P.w52,...imp.patch.w52}:P.w52;
    const clubStats={...(P.clubStats||{}),...imp.clubs};
    const p={...P,carries,w52,clubStats,updated:new Date().toISOString()};
    setP(p); store.set("caddie:profile",p);
    const n=Object.keys(imp.patch.carries).length+(imp.patch.w52?1:0);
    setMeMsg(`Imported ${imp.raw} shots — ${n} clubs learned. Your caddie now runs on your real numbers.`);
    setImp(null); setImpErr("");
  };

  const CH=(live&&courses[live.course]?courses[live.course]:courses[courseSel]).holes;
  const flags=clubFlags((live&&live.shots)||[],["52",...Object.keys(P.carries)]);
  const E=engine(P,(live&&live.bench)||[],flags.adj);
  const chips=["52½","52¾","52FS",...Object.keys(P.carries).sort((a,b)=>P.carries[a]-P.carries[b]),"CHIP"];
  const allShots=[...rounds.flatMap(r=>r.shots||[]),...((live&&live.shots)||[])];
  // Real club data present → the live engine drives every call; the scripted book is retired.
  const learned=!!(P.clubStats&&Object.keys(P.clubStats).length>0)||allShots.some(x=>!x.pen);
  const csKey=fm=>fm==="52"?"52m":fm;
  const cstat=fm=>P.clubStats?P.clubStats[csKey(fm)]:null;
  // Data-driven tips for a club family (only when sample size supports it — no generic lines).
  const clubTips=fm=>{const c=cstat(fm),t=[];if(!c)return t;
    if(c.spdLo&&c.spdHi&&c.spdLo!==c.spdHi)t.push(`${fm} dials in ${c.spdLo}–${c.spdHi} mph club speed`);
    if(c.n>=5&&c.sd<=7)t.push(`${fm} ±${c.sd}y — trust it`);
    return t.slice(0,2);};
  // A club has to PROVE a tendency before it steers strategy: below this many
  // side-traced shots, a lopsided miss % is noise, not a read. We still SHOW the
  // early sample (labelled), but we don't aim off it or dock reliability for it.
  const SIDE_PROVEN=5;
  const sideProven=c=>!!(c&&c.side&&(c.side.n==null||c.side.n>=SIDE_PROVEN));
  // Lateral aim-off from measured side bias: aim half the bias the opposite way.
  const aimOff=fm=>{const c=cstat(fm);if(!sideProven(c)||c.side.med==null||Math.abs(c.side.med)<2)return null;
    const off=Math.round(Math.abs(c.side.med)/2);const bias=c.side.med>0?"right":"left";const aim=c.side.med>0?"left":"right";
    return {off,bias,aim,text:`Biases ${Math.abs(c.side.med)}y ${bias} — aim ${off}y ${aim}`};};
  const disp=fm=>{const e=allShots.filter(x=>famOf(x.c)===fm&&!x.g&&!x.p&&(!x.lie||x.lie==="FW")&&x.from>x.exp+8).map(x=>x.gain-x.exp);if(e.length<2)return null;const avg=Math.round(e.reduce((a,b)=>a+b,0)/e.length);const sd=Math.round(Math.sqrt(e.reduce((a,b)=>a+(b-avg)*(b-avg),0)/e.length));return{n:e.length,avg,sd};};
  const ncdf=z=>1/(1+Math.exp(-1.702*z));
  const greenProb=fm=>{const d=disp(fm);if(!d)return null;const sd=Math.max(d.sd,4);return Math.round((ncdf((12-d.avg)/sd)-ncdf((-12-d.avg)/sd))*100);};
  const conf=fm=>{const d=disp(fm);if(!d)return null;const da=Math.max(0,100-Math.abs(d.avg)*4),di=Math.max(0,100-d.sd*4);
    const rec2=allShots.filter(x=>famOf(x.c)===fm&&!x.p&&(!x.lie||x.lie==="FW")&&(x.g||x.from>x.exp+8)).slice(-2);
    const rf=rec2.length<2?70:rec2.every(x=>x.g||Math.abs(x.gain-x.exp)<=8)?100:rec2.some(x=>!x.g&&x.gain-x.exp<=-15)?35:65;
    return Math.round(da*0.35+di*0.35+rf*0.3);};
  const dirBias=fm=>{const dd=allShots.filter(x=>famOf(x.c)===fm&&x.dir);if(dd.length<3)return null;const r=dd.filter(x=>x.dir==="R").length;const pct=Math.round(r/dd.length*100);return pct>=65?"R "+pct+"%":pct<=35?"L "+(100-pct)+"%":null;};
  const pullDraw=(()=>{const dd=allShots.filter(x=>x.dir).slice(-3);return dd.length===3&&dd.filter(x=>x.dir==="L").length>=2;})();
  // reliability(fam) 0..100 — how much to trust this club, from the player's own
  // dispersion (±yds), consistency (confidence), miss-direction bias, and hot/cold.
  // Drives club SELECTION, not just the words: a wild club loses ties to a steady one.
  // Per-club rolling confidence from OUTCOMES (recency + tournament weighted), the
  // fixed hot/cold engine. Reused for club selection, chip badges, and the bench prompt.
  const shotsOf=fm=>allShots.filter(s=>famOf(s.c)===fm);
  const confOf=fm=>clubConfidence(shotsOf(fm),cstat(fm));
  // Player Model — one normalized daily profile (permanent ability + today's form,
  // + an inert warm-up seam). The decision engine reads reliability from it; the value
  // is identical to the prior definition, so this centralizes without changing behavior.
  const playerDaily=dailyProfile(P,allShots,{warmup:(live&&live.warmup)||null});
  const reliability=fm=>{const m=playerDaily[fm];
    return m?m.reliability:reliabilityFrom(clubConfidence(shotsOf(fm),cstat(fm)).score,cstat(fm));};
  // Recovery-mode inputs: the bag (carry + confidence) and the player's money number.
  const wedgeDist=(P.w52&&P.w52.fs)?Math.round((P.w52.fs[0]+P.w52.fs[1])/2):100;
  const recoBag=()=>Object.keys(P.carries).map(k=>({k,carry:E.eff(k),rel:reliability(k)}));
  // The play-first engine's bag: today's effective carry + today's trust + benched flag,
  // straight from the Player Model so improvement, decline and benching all flow through.
  const decisionBag=(exclude=[])=>Object.keys(P.carries).map(k=>{const m=playerDaily[k];
    return {k,carry:E.eff(k),rel:reliability(k),sd:(m&&m.sd)||(cstat(k)&&cstat(k).sd)||10,
      benched:(live&&live.bench||[]).includes(k)||!!(m&&m.benched)||exclude.includes(k),state:m&&m.state};});
  const H=live?CH[live.hole]:null;
  // Live distances to key marks (carry hazard / dogleg corner) from the ball's spot.
  const holeMarks=(()=>{if(!H||!live)return [];const covered=H.y-live.rem;const m=[];
    if(H.carry&&H.carry-covered>0)m.push(`${H.carry-covered} yds to clear ${H.carryLabel||"the hazard"}`);
    if(H.corner&&H.corner-covered>0)m.push(`${H.corner-covered} yds to the ${H.cornerLabel||"corner"}`);
    return m;})();
  const getPlan=h=>h.plan||genPlan(h,P,(live&&live.bench)||[]);
  const GP=live?getPlan(H):[];
  const windMul=wind==="INTO"?1.08:wind==="DOWN"?0.94:1;                 // CROSS is an aim change, not distance
  const effRem=live?Math.round(live.rem*windMul*lieFactor(lie)):0;        // plays-like: wind + lie
  const lieExtra=live?Math.round(live.rem*(lieFactor(lie)-1)):0;          // yards the lie adds
  const R=live&&!live.onGreen?E.rec(effRem):null;
  const L=live&&!live.onGreen&&(!R||R.zone==="adv")?E.layup(live.rem).filter(o=>o.r.zone!=="adv"):null;
  // The single decision authority. Builds the situation from the map + Player Model and
  // returns ONE complete play (destination, route, flight, club, confidence, record).
  const scoreCeiling=(P.w52&&P.w52.fs)?P.w52.fs[1]:34;
  // ov (all optional): { obsv, lie, exclude } — objection overrides applied synchronously
  // so a recompute uses the corrected input immediately (React state is async).
  const runDecision=(v,ov={})=>{if(!H||!live)return null;
    const useLie=ov.lie||lie, useObs=ov.obsv!==undefined?ov.obsv:obsv, exclude=ov.exclude||objExclude;
    const ev=Math.round(v*windMul*lieFactor(useLie));
    const from=live.ballX!=null?{d:live.ballD,x:live.ballX}:null;
    return decideShot({hole:H,from,rem:v,effRem:ev,lie:useLie,wind,strokes:live.strokes,
      player:playerDaily,bag:decisionBag(exclude),wedgeDist,observation:useObs,scoreCeiling,
      scoring:(r)=>{const rr=E.rec(Math.round(r*windMul*lieFactor(useLie)));const chip=rr?rr.chip:"52½";return {chip,carry:E.chipCarry(chip)};}});
  };

  useEffect(()=>{ if(undoRef.current){undoRef.current=false;return;}   // Back-undo: keep the reopened result state
    setAsked(false);setAskObs(false);setObsv(null);setDecision(null);setFirstDecision(null);setObjections([]);setObjExclude([]);setShowConf(false);setAwaitResult(false);setAwaitDrop(null);setDropPos(null);setShowAlt(false);setMapExpanded(false);setQYards("");setResDir("line");
    if(!live||live.onGreen){setSel(null);return;}
    const hp=getPlan(CH[live.hole]);
    const bk=(!learned&&live.strokes<hp.length)?bookChipOf(hp[live.strokes].c,P):null;
    const bkOk=bk&&!(live.bench||[]).includes(famOf(bk));
    setSel(bkOk?bk:(R?R.chip:(L&&L[0]?L[0].k:Object.keys(P.carries)[0])));setTeeIn("");setObIn("");setDir(null);setWind("NONE");
    // P2/P3: opening shot is auto-classified as a tee shot; later shots start from
    // wherever the last one finished (P6 result carries the lie forward).
    if(live.strokes===0){setLie("FW");setLieLabel("Tee");}
    else if(pendingLie){setLie(pendingLie[0]);setLieLabel(pendingLie[1]);}
    else {setLie("FW");setLieLabel("Fairway");}
  },[live?live.hole:-1,live?live.strokes:-1,live?live.onGreen:false,live&&live.bench?live.bench.join(","):""]);

  const startRound=()=>{const N=(courses[courseSel]||COURSES.bpmapped||COURSES.bp).holes.length;saveLive({course:courseSel,tee:teeSel,hole:0,strokes:0,rem:teeYardOf(CH[0],teeSel),onGreen:false,putts:0,pen:0,i35At:null,teeAck:false,bench:[],shots:[],scores:Array(N).fill(null),puttsArr:Array(N).fill(null),convs:Array(N).fill(null),v:SCHEMA});};
  // ===== PLAYER-DATA CONTROLS (Part 11) — persistence keys are: caddie:profile (player),
  // caddie:rounds (history), caddie:live (active round + its decision records), caddie:holes
  // (imported courses). Mapped courses live in code and always remain. Every write stamps a
  // schema version (Part 12) so older saved shapes stay readable. =====
  const clearUIState=()=>{setDecision(null);setFirstDecision(null);setObjections([]);setObjExclude([]);setSel(null);setAsked(false);setAskObs(false);setObsv(null);setDataArm(null);};
  const resetTodayForm=()=>{ if(live)saveLive({...live,warmup:null,bench:[],dismiss:[],teeAdj:null}); setDataArm(null); setMeMsg("Today's form reset — warm-up and temporary adjustments cleared. Long-term data and past rounds untouched."); };
  const clearCurrentRound=()=>{ saveLive(null); store.set("caddie:live",null); clearUIState(); setMeMsg("Current round cleared. Completed rounds and long-term data untouched."); };
  const resetClubData=(club)=>{ const carries={...P.carries}; delete carries[club];
    const clubStats={...(P.clubStats||{})}; delete clubStats[csKey(club)];
    const feels={...(P.feels||{})}; delete feels[club];
    const p={...P,carries,clubStats,feels,schemaV:SCHEMA,updated:new Date().toISOString()};
    setP(p); store.set("caddie:profile",p); setDataArm(null); setMeMsg(`${club} data cleared — every other club is untouched.`); };
  const clearAllPlayerData=(keepCourses)=>{ const clean={...CLEAN_PROFILE};
    setP(clean); store.set("caddie:profile",clean);
    setRounds([]); store.set("caddie:rounds",[]);
    saveLive(null); store.set("caddie:live",null);
    if(!keepCourses){ setImpCourses({}); store.set("caddie:holes",{}); }
    clearUIState(); setTourn(false);
    setMeMsg(keepCourses?"Fresh start — all player data cleared, your course files kept.":"All player data cleared. The app is back to a clean first-use state; mapped courses remain."); };
  const addPenalty=()=>saveLive({...live,pen:(live.pen||0)+1,shots:[...(live.shots||[]),{pen:1,from:live.rem,c:"Penalty",h:live.hole+1}]});
  // P3: classify the shot from context so the golfer never labels it by hand.
  const shotType=(from,reach,g)=>live.strokes===0?"tee":g?"approach":from<=34?"pitch":reach?"approach":"positioning";
  const logShot=(gain,g,syn,dirOv,endLie,typeOv,penalty,nextBall)=>{
    // Record where this shot FINISHED (from the ball marker) so the round builds a
    // shot-by-shot path on the map. nextBall (a drop) seeds the NEXT shot's spot.
    // The decision record travels WITH the shot: the situation, the plays weighed, why
    // the losers were cut, the pick, its expected outcome and confidence — plus the
    // actual result, so the app can learn from what really happened later.
    // History stays honest: the caddie's ORIGINAL call (before any objection) is kept
    // as `original`; `objections` logs what the golfer flagged; `accepted`/`actual` are
    // what was actually played. An override never rewrites the first recommendation.
    const rec=decision&&decision.record?{...decision.record,
      original:(firstDecision&&firstDecision.record&&firstDecision.club!==(sel||decision.club))?{selected:firstDecision.record.selected,confidence:firstDecision.record.confidence}:null,
      objections:objections.length?objections.slice():null,
      accepted:{club:sel||decision.club,kind:decision.record.selected.kind},
      actual:{gain,end:endLie||(g?"green":null),dir:dirOv!==undefined?dirOv:dir,club:sel||decision.club}}:null;
    const shot={c:sel||"?",from:live.rem,gain,exp:E.chipCarry(sel||"CHIP"),g:g?1:0,p:syn?1:0,h:live.hole+1,lie,dir:dirOv!==undefined?dirOv:dir,
      end:endLie||null,type:typeOv||shotType(live.rem,E.chipCarry(sel||"CHIP")>=live.rem-6,g),tourn:tourn?1:0,
      atX:live.ballX!=null?live.ballX:null,atD:live.ballD!=null?live.ballD:null,rec};
    let l={...live,strokes:live.strokes+1,shots:[...(live.shots||[]),shot],
      ballX:nextBall?nextBall.x:null,ballD:nextBall?nextBall.d:null};
    // P6 fix: a Water outcome must apply its penalty in the SAME state update.
    // Previously it called addPenalty() separately, which re-saved from stale state
    // and clobbered the shot — the button looked dead. One update, one save.
    if(penalty){l.pen=(l.pen||0)+1;l.shots=[...l.shots,{pen:1,from:live.rem,c:"Penalty",h:live.hole+1}];}
    const nr=live.rem-gain;
    // With richer results the finishing LIE decides "on the green" — a long miss
    // into the rough must not be treated as holed just because carry exceeded distance.
    const onGreen = endLie ? endLie==="green" : (g||nr<=0);
    if(onGreen){l.onGreen=true;}
    else {l.rem=nr>0?nr:15; if(nr>0&&nr<=35&&l.i35At===null)l.i35At=l.strokes;}
    saveLive(l);setAtInput("");
  };
  // P2: review/edit any shot on the current hole. Shots are independent records
  // (distance is re-entered each shot), so editing a middle shot is safe.
  const dirWord=x=>x.dir==="L"?"left":x.dir==="R"?"right":x.gain<x.exp?"short":x.gain>x.exp?"long":"on line";
  const updateShot=(gi,patch)=>saveLive({...live,shots:live.shots.map((s,i)=>i===gi?{...s,...patch}:s)});
  const deleteShot=gi=>{const s=live.shots[gi];saveLive({...live,shots:live.shots.filter((_,i)=>i!==gi),strokes:s.pen?live.strokes:Math.max(0,live.strokes-1),pen:s.pen?Math.max(0,(live.pen||0)-1):live.pen});setEditShot(null);};
  const holeOut=()=>{
    const pen=live.pen||0;
    const total=live.strokes+live.putts+pen+1,h=live.hole;
    const conv=live.i35At!==null?(total-live.i35At)<=3:null;
    const sc=[...live.scores];sc[h]=total;
    const pa=[...live.puttsArr];pa[h]=live.putts+1;
    const cv=[...live.convs];cv[h]=conv;
    if(sc.every(x=>x!==null)){
      const rd={date:new Date().toLocaleDateString(),course:courses[live.course]?courses[live.course].name:"",total:sc.reduce((a,b)=>a+b,0),plan:CH.reduce((a,x)=>a+x.tgt,0),scores:sc,putts:pa.reduce((a,b)=>a+(b||0),0),convMade:cv.filter(c=>c===true).length,convTried:cv.filter(c=>c!==null).length,benched:live.bench||[],shots:live.shots||[]};
      const nr=[...rounds,rd];setRounds(nr);store.set("caddie:rounds",nr);
      saveLive(null);store.set("caddie:live",null);setTab("trends");
    } else {const N=sc.length;const nxt=(()=>{let n=(h+1)%N;while(sc[n]!==null&&n!==h)n=(n+1)%N;return n;})();
      saveLive({...live,hole:nxt,strokes:0,rem:(live.teeAdj&&live.teeAdj[nxt])||teeYardOf(CH[nxt],live.tee),onGreen:false,putts:0,pen:0,i35At:null,teeAck:false,scores:sc,puttsArr:pa,convs:cv});}
  };

  const TabBtn=({id,label})=>(
    <button onClick={()=>{setTab(id);}} style={{flex:1,background:"none",border:"none",cursor:"pointer",padding:"14px 0 16px",display:"flex",flexDirection:"column",alignItems:"center",gap:4}}>
      <span style={{width:5,height:5,borderRadius:5,background:tab===id?GOLD:"transparent"}}></span>
      <span style={{fontSize:11,letterSpacing:2,fontWeight:700,color:tab===id?INK:MUTE,fontFamily:SERIF}}>{label}</span>
    </button>);

  if(!loaded)return <div style={{padding:40,textAlign:"center",fontFamily:"-apple-system,sans-serif",color:"#8a8a8e"}}>Loading your caddie…</div>;

  const step=live?Math.min(live.strokes,Math.max(GP.length-1,0)):0;
  const done=live?live.scores.filter(s=>s!==null).length:0;
  const runTot=live?live.scores.reduce((a,b)=>a+(b||0),0):0;
  const runPlan=live?CH.slice(0,live.hole).reduce((a,h)=>a+h.tgt,0):0;
  const dv=runTot-runPlan;
  const totalPlan=CH.reduce((a,h)=>a+h.tgt,0);
  // Cold clubs from the confidence engine (not the old clean-lie filter that hid failures).
  const coldAlert=live?["52",...Object.keys(P.carries)].filter(f=>confOf(f).state==="cold"&&!live.bench.includes(f)&&!((live.dismiss||[]).includes(f))):[];
  const inspecting=live&&viewHole!==null&&viewHole!==live.hole;

  return (
    <div style={{background:PAPER,minHeight:"100vh",width:"100%",maxWidth:430,margin:"0 auto",overflowX:"hidden",fontFamily:"-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif",paddingBottom:46,boxSizing:"border-box"}}>
      <div style={{background:"#1a3a2e",padding:"12px 14px 9px",position:"sticky",top:0,zIndex:50}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <div>
            <div style={{color:"#86efac",fontSize:9,letterSpacing:3,fontWeight:800}}>CADDIE OS</div>
            <div style={{color:"white",fontSize:14,fontWeight:800}}>{P.name} · {(live&&courses[live.course]?courses[live.course]:courses[courseSel]).name} <button onClick={()=>setTourn(!tourn)} style={{marginLeft:6,border:"none",borderRadius:6,padding:"2px 8px",fontSize:9,fontWeight:800,cursor:"pointer",verticalAlign:"middle",background:tourn?"#fcd34d":"rgba(255,255,255,0.14)",color:tourn?"#1a3a2e":"#86efac"}}>{tourn?"TOURN ON":"TOURN"}</button></div>
          </div>
          {live&&<div style={{textAlign:"right"}}>
            <div style={{color:"white",fontSize:17,fontWeight:900}}>{runTot}<span style={{fontSize:11,fontWeight:700,color:dv>0?"#ffb3ad":dv<0?"#86efac":"#fcd34d"}}> {done>0?(dv>0?"+"+dv:dv)+" vs plan":""}</span></div>
            <div style={{color:"#6b9e7a",fontSize:9,fontWeight:700}}>H{live.hole+1} · {done}/{CH.length} holed</div>
          </div>}
        </div>
        {live&&<div style={{display:"flex",gap:3,overflowX:"auto",marginTop:8,paddingBottom:2}}>
          {CH.map((h,i)=>{const s=live.scores[i];const cur=i===live.hole;
            return <div key={i} onClick={()=>setViewHole(i===live.hole?null:i)} style={{cursor:"pointer",minWidth:22,textAlign:"center",borderRadius:6,padding:"2px 0",background:cur?"#86efac":s!==null?(s<=h.tgt?"rgba(48,209,88,0.3)":s>=7?"rgba(255,69,58,0.4)":"rgba(255,255,255,0.12)"):"rgba(255,255,255,0.07)",flexShrink:0}}>
              <div style={{fontSize:7,color:cur?"#1a3a2e":"#6b9e7a",fontWeight:700}}>{i+1}</div>
              <div style={{fontSize:11,fontWeight:900,color:cur?"#1a3a2e":s!==null?"white":"#6b9e7a"}}>{s!==null?s:h.tgt}</div>
            </div>;})}
        </div>}
      </div>

      {tab==="caddie"&&<div style={{padding:0}}>
        <style>{WSTYLE}</style>

        {!live&&(()=>{
          const cName=(courses[courseSel]||COURSES.bpmapped||COURSES.bp).name;
          const ch=(courses[courseSel]||COURSES.bpmapped||COURSES.bp).holes;
          const t0=ch&&ch[0]&&ch[0].tees;
          const teeLab=(TEES.find(([k])=>k===teeSel)||["",""])[1]||"White";
          return <div style={{padding:"26px 18px"}}>
          <div style={{fontFamily:SERIF,fontSize:30,color:INK,lineHeight:1.2,marginBottom:20}}>Ready when you are, {P.name||"golfer"}.</div>
          {/* The plan for today — calm and immediate. */}
          <div style={{background:"#fff",borderRadius:18,padding:"18px 18px",boxShadow:"0 1px 4px rgba(0,0,0,.06)",marginBottom:16}}>
            <button onClick={()=>setPrepSec(prepSec==="course"?"":"course")} style={{width:"100%",textAlign:"left",background:"none",border:"none",cursor:"pointer",padding:0,display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
              <span style={{fontFamily:SERIF,fontSize:22,color:INK}}>{cName}</span>
              <span style={{color:MUTE,fontSize:12}}>change ›</span>
            </button>
            {prepSec==="course"&&<div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:10}}>
              {startCourses.map(([k,c])=>(<button key={k} onClick={()=>{setCourseSel(k);setPrepSec("");}} style={{border:"none",borderRadius:12,padding:"9px 12px",fontSize:13,fontWeight:700,cursor:"pointer",background:courseSel===k?PINE:"#f1efe9",color:courseSel===k?PAPER:INK}}>{c.name}</button>))}
            </div>}
            {t0&&<><div style={{height:1,background:"#f0eee8",margin:"14px 0"}}></div>
            <button onClick={()=>setPrepSec(prepSec==="tees"?"":"tees")} style={{width:"100%",textAlign:"left",background:"none",border:"none",cursor:"pointer",padding:0,display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
              <span style={{fontFamily:SERIF,fontSize:18,color:INK}}>{teeLab} tees</span>
              <span style={{color:MUTE,fontSize:12}}>change ›</span>
            </button>
            {prepSec==="tees"&&<div style={{display:"flex",gap:6,flexWrap:"wrap",marginTop:10}}>
              {TEES.filter(([k])=>t0[k]!=null).map(([k,lab])=>{const on=teeSel===k;
                return <button key={k} onClick={()=>{setTeeSel(k);setPrepSec("");}} style={{border:"none",borderRadius:12,padding:"8px 12px",fontSize:13,fontWeight:700,cursor:"pointer",background:on?PINE:"#f1efe9",color:on?PAPER:INK}}>{lab} <span style={{opacity:.7}}>{t0[k]}</span></button>;})}
            </div>}</>}
          </div>
          <button onClick={()=>{buzz();startRound();}} style={{width:"100%",border:"none",borderRadius:18,padding:"18px",fontSize:18,fontWeight:800,cursor:"pointer",background:PINE,color:PAPER,letterSpacing:.4}}>Start round</button>
          {/* Secondary — quiet, never competing with Start. */}
          <div style={{display:"flex",gap:8,justifyContent:"center",marginTop:14,flexWrap:"wrap"}}>
            <button onClick={()=>setPrepOpen(!prepOpen)} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer",textDecoration:"underline"}}>Quick warm-up</button>
            <span style={{color:"#d9d5cc"}}>·</span>
            <button onClick={()=>setTab("me")} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer",textDecoration:"underline"}}>Player &amp; data</button>
          </div>
          {prepOpen&&<div style={{marginTop:14,background:"#fff",borderRadius:16,padding:16,boxShadow:"0 1px 4px rgba(0,0,0,.06)",color:INK,fontSize:14,lineHeight:1.7}}>
            <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:4}}>Body · 8 min</div>
            Glute bridges, world's-greatest stretch, torso rotations, then ten swings building to your smooth tempo.
            <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",margin:"12px 0 4px"}}>Range · fresh first</div>
            Check alignment, then your wedge windows before anything else. Five smooth 9-irons, five 7s at tempo. Finish on the greens: pace ladder 10/20/30, then five chips — walk to the first tee on a make.
            <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",margin:"12px 0 4px"}}>Fuel</div>
            Eat 2–3 hours out, top up every six holes, sip water every hole.
          </div>}
        </div>;})()}

        {live&&(()=>{
          if(viewHole!=null&&viewHole!==live.hole){const i=viewHole,h=CH[i],sc=live.scores[i];
            return <div style={{padding:"18px 16px"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
                <div style={{fontFamily:SERIF,fontSize:20,color:INK}}>Hole {i+1} · par {h.par} · {h.y}y</div>
                <button onClick={()=>setViewHole(null)} style={{border:"none",background:PINE,color:PAPER,borderRadius:10,padding:"8px 12px",cursor:"pointer"}}>Close</button>
              </div>
              <div style={{color:MUTE,fontSize:14,marginBottom:14,fontFamily:SERIF}}>{h.hz}</div>
              {sc!=null&&<div style={{display:"flex",alignItems:"center",gap:14,marginBottom:14}}>
                <button onClick={()=>editLiveHole(i,-1)} style={{border:"none",background:"#fff",borderRadius:10,padding:"8px 16px",fontSize:18,cursor:"pointer",boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>–</button>
                <span style={{fontSize:26,fontWeight:800,color:INK}}>{sc}</span>
                <button onClick={()=>editLiveHole(i,1)} style={{border:"none",background:"#fff",borderRadius:10,padding:"8px 16px",fontSize:18,cursor:"pointer",boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>+</button>
                <span style={{color:MUTE,fontSize:13}}>score</span>
              </div>}
              <button onClick={()=>{buzz();playHoleNow(i);}} style={{width:"100%",border:"none",borderRadius:16,padding:"15px",background:PINE,color:PAPER,fontSize:16,fontWeight:700,cursor:"pointer"}}>Play this hole now</button>
            </div>;
          }
          const phase=live.onGreen?"putt":awaitDrop?"drop":awaitResult?"result":askObs?"observe":asked?"whisper":"question";
          const y=parseInt(qYards)||live.rem;
          return <div style={{padding:"8px 16px 14px"}}>
            {/* Universal Back — steps to the previous screen; undoes a too-fast tap. */}
            {canGoBack()&&<button className="tapbtn" onClick={goBack} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,fontWeight:700,cursor:"pointer",padding:"0 0 2px",display:"flex",alignItems:"center",gap:3}}>‹ Back</button>}

            {phase==="question"&&<div style={arrive}>
              {(()=>{const c=coldAlert[0];if(!c)return null;const cc=confOf(c);
                return <div style={{background:"#fff",borderRadius:16,padding:14,marginBottom:16,boxShadow:"0 1px 4px rgba(0,0,0,.06)",border:"1px solid #efe7d8"}}>
                  <div style={{fontFamily:SERIF,fontSize:16,color:INK,marginBottom:6}}>{benchWhisper(c)}</div>
                  {cc.reasons.length>0&&<div style={{color:MUTE,fontSize:12,marginBottom:10,lineHeight:1.5}}>Recent {c}: {cc.reasons.map((r,i)=>(i+1)+") "+r).join("  ")} — confidence {cc.score}/100.</div>}
                  <div style={{display:"flex",gap:10}}>
                    <button className="tapbtn" onClick={()=>saveLive({...live,bench:[...live.bench,c]})} style={{flex:1,border:"none",borderRadius:12,padding:"12px",background:PINE,color:PAPER,fontWeight:700,cursor:"pointer"}}>Yes, route around it</button>
                    <button className="tapbtn" onClick={()=>saveLive({...live,dismiss:[...(live.dismiss||[]),c]})} style={{flex:1,border:"none",borderRadius:12,padding:"12px",background:"#f1efe9",color:INK,fontWeight:700,cursor:"pointer"}}>No, it's fine</button>
                  </div>
                </div>;})()}
              {/* Hole header — compact, with quick prev/next nav. */}
              {(()=>{const navBtn=en=>({border:"none",background:en?"#fff":"transparent",color:en?INK:"#cfcabf",width:36,height:36,borderRadius:18,fontSize:22,fontWeight:400,lineHeight:1,cursor:en?"pointer":"default",boxShadow:en?"0 1px 3px rgba(0,0,0,.06)":"none"});
                const canL=live.hole>0,canR=live.hole<CH.length-1;
                return <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:3}}>
                  <button className="tapbtn" onClick={()=>goHole(live.hole-1)} disabled={!canL} style={navBtn(canL)}>‹</button>
                  <div style={{textAlign:"center"}}>
                    <div style={{fontFamily:SERIF,fontSize:20,color:INK,fontWeight:700,lineHeight:1.05}}>Hole {H.n||live.hole+1}</div>
                    <div style={{color:MUTE,fontSize:11,letterSpacing:.3}}>Par {H.par} · {teeYardOf(H,live.tee)} yds · Shot {live.strokes+1}{live.strokes===0?" (tee)":""}</div>
                  </div>
                  <button className="tapbtn" onClick={()=>goHole(live.hole+1)} disabled={!canR} style={navBtn(canR)}>›</button>
                </div>;})()}
              {/* Tee is chosen at round setup — on the tee we just confirm it, with a small
                  correction if they moved up/back. No big control row. */}
              {live.strokes===0&&H.tees&&(()=>{const cur=live.tee||teeSel;const lab=(TEES.find(([k])=>k===cur)||["",""])[1]||"Tee";
                return <div style={{textAlign:"center",marginBottom:6}}>
                  <button onClick={()=>setTeeEdit(!teeEdit)} style={{border:"none",background:"transparent",color:MUTE,fontSize:12,cursor:"pointer"}}>{lab} tees · {teeYardOf(H,cur)}y <span style={{textDecoration:"underline"}}>change</span></button>
                  {teeEdit&&<div style={{display:"flex",gap:4,justifyContent:"center",flexWrap:"wrap",marginTop:6}}>
                    {TEES.filter(([k])=>H.tees[k]!=null).map(([k,tl])=>{const on=cur===k;
                      return <button key={k} className="tapbtn" onClick={()=>{setTeeSel(k);saveLive({...live,tee:k,rem:teeYardOf(H,k)});setQYards("");setTeeEdit(false);}} style={{border:"none",borderRadius:12,padding:"6px 10px",fontSize:12,fontWeight:700,cursor:"pointer",background:on?INK:"#fff",color:on?PAPER:MUTE,boxShadow:on?"none":"0 1px 3px rgba(0,0,0,.05)"}}>{tl} <span style={{opacity:.7}}>{H.tees[k]}</span></button>;})}
                  </div>}
                </div>;})()}
              {/* Hole overview — small preview that opens a FULL-SCREEN map for placing
                  the ball, so the tap target is big while the shot screen stays no-scroll. */}
              {Array.isArray(H.path)&&(()=>{
                const isApproach=live.strokes>0;
                const loc=live.ballX!=null?holeContext(H,live.ballD,live.ballX):null;
                const est=live.ballX!=null?Math.max(1,Math.min(H.y,Math.round((1-live.ballD)*H.y))):null;
                const where=loc?(loc.blocked?`blocked ${loc.side} — trees on your line`:loc.side==="center"?"middle — clean angle":`${loc.side}${loc.off?"":" — clean angle"}`):null;
                const placeFromMap=(d,x)=>{buzz();
                  const remA=Math.max(1,Math.min(H.y,Math.round((1-d)*H.y)));const det=lieAt(H,d,x);
                  setQYards(String(remA));setLie(det.lie);setLieLabel(det.label);
                  saveLive({...live,rem:remA,ballD:d,ballX:x});};
                const shotsHere=(live.shots||[]).filter(s=>s.h===live.hole+1);
                return <>
                  <div style={{textAlign:"center",color:MUTE,fontSize:11,marginBottom:3}}>{isApproach?(live.ballX!=null?"Ball placed — tap map to adjust":"Tap the map to place your ball"):"Tap the map to enlarge"}</div>
                  <div onClick={()=>setMapExpanded(true)} style={{cursor:"pointer"}}>
                    <HoleView h={H} P={P} tee={live.tee} compact ball={live.ballX!=null?{d:live.ballD,x:live.ballX}:null} shots={shotsHere}/>
                  </div>
                  {isApproach&&where&&<div style={{textAlign:"center",fontFamily:SERIF,fontSize:13,color:INK,marginTop:4}}>You're {where}{est!=null?` · ~${est} in`:""}.</div>}
                  {mapExpanded&&<div style={{position:"fixed",inset:0,zIndex:200,background:PAPER,display:"flex",flexDirection:"column",padding:14,boxSizing:"border-box"}}>
                    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6}}>
                      <div style={{fontFamily:SERIF,fontSize:17,color:INK,fontWeight:700}}>Hole {H.n||live.hole+1}{isApproach?" — tap your ball":""}</div>
                      <button className="tapbtn" onClick={()=>setMapExpanded(false)} style={{border:"none",background:PINE,color:PAPER,borderRadius:12,padding:"9px 20px",fontSize:15,fontWeight:800,cursor:"pointer"}}>Done</button>
                    </div>
                    <div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",minHeight:0}}>
                      <HoleView h={H} P={P} tee={live.tee} big ball={live.ballX!=null?{d:live.ballD,x:live.ballX}:null} shots={shotsHere} onPlace={isApproach?((d,x)=>{placeFromMap(d,x);setMapExpanded(false);}):undefined}/>
                    </div>
                    <div style={{textAlign:"center",color:MUTE,fontSize:14,marginTop:6}}>{isApproach?(live.ballX!=null?"Tap to move it · Done to confirm":"Tap where your ball finished"):"Done to close"}</div>
                  </div>}
                </>;})()}
              {live.strokes===0&&<div style={{fontFamily:SERIF,fontSize:12,color:MUTE,lineHeight:1.3,margin:"3px 8px 2px",textAlign:"center",maxHeight:32,overflow:"hidden"}}>{teeWhisper(H,teeYardOf(H,live.tee))}</div>}
              <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:12,margin:"2px 0 0"}}>
                <button onClick={()=>setQYards(String(Math.max(1,y-1)))} style={{border:"none",background:"#fff",width:40,height:40,borderRadius:20,fontSize:22,color:INK,cursor:"pointer",boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>–</button>
                <input inputMode="numeric" value={qYards} placeholder={String(live.rem)} onChange={e=>setQYards(e.target.value.replace(/[^0-9]/g,"").slice(0,3))} style={{width:118,textAlign:"center",fontSize:48,fontWeight:800,color:INK,border:"none",background:"transparent",fontVariantNumeric:"tabular-nums",outline:"none"}}/>
                <button onClick={()=>setQYards(String(y+1))} style={{border:"none",background:"#fff",width:40,height:40,borderRadius:20,fontSize:22,color:INK,cursor:"pointer",boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>+</button>
              </div>
              <div style={{textAlign:"center",color:MUTE,fontSize:10,marginBottom:6}}>{courses[live.course]&&courses[live.course].ref==="flag"?"to the flag":"to the middle"}{live.strokes>0&&Array.isArray(H.path)?" · tap or rangefinder":""}</div>
              {/* Lie only matters after the tee — on the tee it's known, so we hide it. */}
              {live.strokes>0&&<div style={{display:"flex",gap:4,justifyContent:"flex-start",flexWrap:"nowrap",overflowX:"auto",marginBottom:6,padding:"0 2px 2px",WebkitOverflowScrolling:"touch"}}>
                {[["Fairway","FW"],["Fringe","FRINGE"],["First cut","FIRST"],["Rough","ROUGH"],["Deep","DEEP"],["Bunker","FBUNK"],["Recovery","TREES"]].map(([lab,v])=>{const on=lieLabel===lab;
                  return <button key={lab} className="tapbtn" onClick={()=>{setLie(v);setLieLabel(lab);}} style={{flexShrink:0,border:"none",borderRadius:16,padding:"6px 11px",fontSize:12,fontWeight:600,cursor:"pointer",background:on?PINE:"#fff",color:on?PAPER:INK,boxShadow:on?"none":"0 1px 3px rgba(0,0,0,.06)"}}>{lab}</button>;})}
              </div>}
              <div style={{display:"flex",gap:6,justifyContent:"center",marginBottom:6}}>
                {[["NONE","calm"],["INTO","into"],["DOWN","down"],["CROSS","cross"]].map(([k,l])=>(
                  <button key={k} onClick={()=>setWind(k)} style={{border:"none",borderRadius:14,padding:"4px 11px",fontSize:12,fontWeight:600,cursor:"pointer",background:wind===k?INK:"transparent",color:wind===k?PAPER:MUTE}}>{l}</button>))}
              </div>
              {(()=>{const needPlace=live.strokes>0&&Array.isArray(H.path)&&live.ballX==null;
                return <button className="tapbtn" disabled={needPlace} onClick={()=>{if(needPlace)return;buzz();const v=parseInt(qYards)||live.rem;
                saveLive({...live,rem:v});
                // ONE authority: the play-first engine decides the play + club + record.
                const dec=runDecision(v);
                // Only pause to ask the golfer a route observation when it could change the play.
                if(dec&&dec.askObservation&&obsv==null){setDecision(dec);setAskObs(true);return;}
                setDecision(dec);if(dec)setSel(dec.club);
                setAsked(true);setShowAlt(false);}} style={{width:"100%",border:"none",borderRadius:16,padding:"14px",fontSize:17,fontWeight:700,cursor:needPlace?"default":"pointer",background:needPlace?"#d9d5cc":PINE,color:needPlace?"#8a8578":PAPER,letterSpacing:.4}}>{needPlace?"Tap your ball on the map first":live.strokes===0?"Tee off":"Read it"}</button>;})()}
              {(()=>{const hs=(live.shots||[]).map((x,gi)=>({x,gi})).filter(o=>o.x.h===live.hole+1);if(!hs.length)return null;
                return <div style={{marginTop:20,background:"#fff",borderRadius:16,padding:12,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
                  <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:8}}>Shots this hole — tap to review or fix</div>
                  {hs.map(({x,gi},n)=>{const open=editShot===gi;
                    return <div key={gi} style={{borderTop:n?"1px solid #f0eee8":"none",paddingTop:n?8:0,marginTop:n?8:0}}>
                      <button onClick={()=>setEditShot(open?null:gi)} style={{width:"100%",display:"flex",justifyContent:"space-between",alignItems:"center",background:"none",border:"none",cursor:"pointer",padding:"2px 0"}}>
                        <span style={{color:INK,fontSize:14,fontWeight:700}}>{n+1}. {x.pen?"Penalty":x.c}</span>
                        <span style={{color:MUTE,fontSize:12}}>{x.pen?"stroke & distance":`${x.type||""}${x.exp!=null?" · "+dirWord(x):""}${x.g?" · green":x.end?" · "+x.end:""}`} {open?"▾":"›"}</span>
                      </button>
                      {open&&!x.pen&&<div style={{marginTop:8}}>
                        <div style={{color:MUTE,fontSize:10,letterSpacing:1,textTransform:"uppercase",margin:"4px 0"}}>club</div>
                        <div style={{display:"flex",gap:5,overflowX:"auto",paddingBottom:4}}>{chips.map(c=>(<button key={c} onClick={()=>updateShot(gi,{c,exp:E.chipCarry(c)})} style={{flexShrink:0,border:"none",borderRadius:10,padding:"7px 10px",fontSize:12,fontWeight:700,cursor:"pointer",background:x.c===c?PINE:"#f1efe9",color:x.c===c?PAPER:INK}}>{c}</button>))}</div>
                        <div style={{color:MUTE,fontSize:10,letterSpacing:1,textTransform:"uppercase",margin:"8px 0 4px"}}>direction</div>
                        <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>{[["line","On line"],["short","Short"],["long","Long"],["left","Left"],["right","Right"]].map(([k,l])=>{const cur=dirWord(x)===(k==="line"?"on line":k);return <button key={k} onClick={()=>updateShot(gi,{dir:k==="left"?"L":k==="right"?"R":null,gain:k==="short"?Math.max(1,x.exp-10):k==="long"?x.exp+10:x.exp})} style={{border:"none",borderRadius:10,padding:"7px 10px",fontSize:12,fontWeight:600,cursor:"pointer",background:cur?PINE:"#f1efe9",color:cur?PAPER:INK}}>{l}</button>;})}</div>
                        <div style={{color:MUTE,fontSize:10,letterSpacing:1,textTransform:"uppercase",margin:"8px 0 4px"}}>ended</div>
                        <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>{[["fairway","Fairway"],["rough","Rough"],["bunker","Bunker"],["trees","Trees"],["water","Water"],["green","Green"]].map(([k,l])=>(<button key={k} onClick={()=>updateShot(gi,{end:k,g:k==="green"?1:0})} style={{border:"none",borderRadius:10,padding:"7px 10px",fontSize:12,fontWeight:600,cursor:"pointer",background:x.end===k?PINE:"#f1efe9",color:x.end===k?PAPER:INK}}>{l}</button>))}</div>
                        <button onClick={()=>deleteShot(gi)} style={{marginTop:10,border:"none",borderRadius:10,padding:"8px 12px",background:"#f6ece9",color:"#a3402f",fontSize:12,fontWeight:700,cursor:"pointer"}}>Delete this shot</button>
                      </div>}
                    </div>;})}
                </div>;})()}
            </div>}

            {phase==="observe"&&(()=>{
              // The ONE thing the caddie can't honestly know: the window on your line.
              // The golfer reports only the observation — the engine still picks the play.
              const opts=[["clear","Normal flight is clear"],["high","Gotta go high"],["low","Gotta stay low"],["curve","Need to curve it"],["nowindow","No usable window"]];
              const commit=(val)=>{buzz();setObsv(val);const dec=runDecision(live.rem,{obsv:val});if(!firstDecision&&decision)setFirstDecision(decision);setDecision(dec);if(dec)setSel(dec.club);setAskObs(false);setAsked(true);};
              return <div style={arrive}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
                  <div style={{color:MUTE,fontSize:14}}><span style={{color:INK,fontWeight:700}}>one look</span> · {live.rem}y · {lieLabel.toLowerCase()}</div>
                  <button onClick={()=>{setAskObs(false);}} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer"}}>↩ back</button>
                </div>
                <div style={{fontFamily:SERIF,fontSize:23,color:INK,marginBottom:4}}>What's your window?</div>
                <div style={{color:MUTE,fontSize:13,marginBottom:16,lineHeight:1.4}}>Something's on your line. Tell me only what I can't see from the data — I'll pick the play.</div>
                {opts.map(([val,lab])=>(<button key={val} className="tapbtn" onClick={()=>commit(val)} style={{display:"block",width:"100%",textAlign:"left",border:"2px solid #e7e2d8",background:"#fff",borderRadius:14,padding:"15px",marginBottom:10,cursor:"pointer",fontSize:16,fontWeight:700,color:INK}}>{lab}</button>))}
              </div>;})()}

            {phase==="whisper"&&isRecoveryLie(lie)&&(()=>{
              // RECOVERY — same play-first flow: the objective is the lowest expected score,
              // the window is the physical destination + simplest executable route. ONE call;
              // the plays weighed sit behind Why?.
              const loc=live.ballX!=null?holeContext(H,live.ballD,live.ballX):{};
              const plan=recoveryPlan(live.rem,lie,{bag:recoBag(),wedgeDist,side:loc.side,blocked:loc.blocked});
              const opt=plan.best||plan.options[0];
              const club=opt?humanClub(famOf(opt.club),opt.club):"—";
              return <div style={arrive}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
                  <div style={{color:MUTE,fontSize:13}}><span style={{color:"#a3402f",fontWeight:800}}>RECOVERY</span> · Hole {H.n||live.hole+1} · {live.rem}y · {lieLabel.toLowerCase()}</div>
                  <button onClick={()=>{setAsked(false);setShowAlt(false);}} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer"}}>↩ back</button>
                </div>
                {Array.isArray(H.path)&&<div style={{background:"#fff",borderRadius:16,padding:8,boxShadow:"0 1px 4px rgba(0,0,0,.06)",marginBottom:12}}>
                  <HoleView h={H} P={P} tee={live.tee} compact ball={live.ballX!=null?{d:live.ballD,x:live.ballX}:null} shots={(live.shots||[]).filter(s=>s.h===live.hole+1)}/>
                </div>}
                <div style={{background:PINE,borderRadius:24,padding:"20px 20px",boxShadow:"0 10px 30px rgba(18,43,33,.18)"}}>
                  <div style={{color:"#e7b7a6",fontSize:11,letterSpacing:2,textTransform:"uppercase",marginBottom:2,fontWeight:800}}>Objective</div>
                  <div style={{fontFamily:SERIF,fontSize:21,color:PAPER,marginBottom:plan.sideNote?2:10}}>{plan.objective}</div>
                  {plan.sideNote&&<div style={{color:"#e7b7a6",fontSize:12,marginBottom:10,opacity:.9}}>{plan.sideNote.replace(/^\s*—\s*/,"")}</div>}
                  <div style={{fontFamily:SERIF,fontSize:34,color:GOLD,marginBottom:8}}>{club}</div>
                  <div style={{fontFamily:SERIF,fontSize:16,color:PAPER,lineHeight:1.4,opacity:.96}}>{opt?opt.reason:""}</div>
                </div>
                <button onClick={()=>setShowConf(!showConf)} style={{marginTop:12,width:"100%",border:"1px solid #e7e2d8",background:"#fff",borderRadius:12,padding:"10px 12px",cursor:"pointer",display:"flex",justifyContent:"space-between",alignItems:"center",color:INK,fontSize:14,fontWeight:700}}>
                  <span>Lowest expected score to the hole</span><span style={{color:MUTE,fontSize:13}}>{showConf?"hide Why ▾":"Why? ›"}</span>
                </button>
                {showConf&&<div style={{marginTop:8,background:"#fff",borderRadius:14,padding:13,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
                  <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:8}}>Plays I compared</div>
                  {plan.options.map((o,i)=>{const isBest=plan.best&&o.kind===plan.best.kind;
                    return <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",gap:8,fontSize:12,padding:"4px 0",borderTop:i?"1px solid #f2efe8":"none"}}>
                      <span style={{color:isBest?INK:MUTE,fontWeight:isBest?800:600}}>{isBest?"✓ ":""}{o.label} · {o.club}{o.kind==="hero"?` · ${o.prob}% comes off`:""}</span>
                      <span style={{color:isBest?"#1a7f37":MUTE,fontWeight:700,whiteSpace:"nowrap"}}>exp {o.ev}</span>
                    </div>;})}
                </div>}
                <button className="tapbtn" onClick={()=>{buzz();if(opt)setSel(opt.club);setAwaitResult(true);}} style={{width:"100%",border:"none",borderRadius:18,padding:"18px",fontSize:19,fontWeight:800,cursor:"pointer",background:GOLD,color:PINE,letterSpacing:1,marginTop:14}}>PLAY IT</button>
              </div>;})()}

            {phase==="whisper"&&!isRecoveryLie(lie)&&decision&&(()=>{
              // ONE authoritative call, straight from decideShot(): club, aim, flight,
              // landing, one optional cue — no saved club-feel, no competing strategy.
              const D=decision, fam=famOf(D.club||"7i"), club=humanClub(fam,D.club);
              const c=D.confidence||{};
              const bandCol=b=>b==="High"?"#1a7f37":b==="Solid"?"#8a6d2f":"#a3402f";
              const showFlight=D.flight&&!["normal","your stock flight","committed","low"].includes(D.flight);
              const shotsHere=(live.shots||[]).filter(s=>s.h===live.hole+1);
              const overridden=firstDecision&&firstDecision.club!==D.club;
              const cap0=t=>String(t||"").charAt(0).toUpperCase()+String(t||"").slice(1);
              // An objection → the caddie RE-PICKS (it never hands strategy back). The
              // original call is preserved (firstDecision) so history isn't rewritten.
              const objectWith=(reason,ov)=>{buzz();if(!firstDecision)setFirstDecision(decision);setObjections(o=>[...o,reason]);
                const dec=runDecision(live.rem,ov);setDecision(dec);if(dec)setSel(dec.club);setShowAlt(false);};
              const distrust=()=>{const nx=[...objExclude,fam];setObjExclude(nx);objectWith("distrust:"+fam,{exclude:nx});};
              const row=(lab,val)=><div style={{display:"flex",gap:8,marginBottom:6}}>
                <div style={{color:"#9db8a6",fontSize:12,fontWeight:800,letterSpacing:.5,textTransform:"uppercase",width:52,flexShrink:0}}>{lab}</div>
                <div style={{fontFamily:SERIF,fontSize:16,color:PAPER,lineHeight:1.35}}>{val}</div></div>;
              return <div style={arrive}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
                  <div style={{color:MUTE,fontSize:13}}><b style={{color:INK}}>Hole {H.n||live.hole+1}</b> · par {H.par} · {live.rem}y{effRem!==live.rem?` (plays ${effRem})`:""} · {lieLabel.toLowerCase()}{wind!=="NONE"?` · ${wind.toLowerCase()} wind`:""}</div>
                  <button onClick={()=>{setAsked(false);setShowAlt(false);}} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer"}}>↩ back</button>
                </div>
                {/* One map — the SAME map with the decision overlay (aim + your dispersion). */}
                {Array.isArray(H.path)&&<div style={{background:"#fff",borderRadius:16,padding:8,boxShadow:"0 1px 4px rgba(0,0,0,.06)",marginBottom:12}}>
                  <HoleView h={H} P={P} tee={live.tee} compact ball={live.ballX!=null?{d:live.ballD,x:live.ballX}:null} target={D.aim} dispersion={D.dispersion} shots={shotsHere}/>
                </div>}
                {/* The call. */}
                <div style={{background:PINE,borderRadius:24,padding:"20px 20px",boxShadow:"0 10px 30px rgba(18,43,33,.18)"}}>
                  <div style={{fontFamily:SERIF,fontSize:38,color:GOLD,letterSpacing:.3,marginBottom:14,textWrap:"balance"}}>{club}</div>
                  {row("Aim",cap0(D.startLine))}
                  {showFlight&&row("Flight",cap0(D.trajectory))}
                  {row("Finish",cap0(D.landing))}
                  {D.cue&&<div style={{fontFamily:SERIF,fontSize:15,color:"#d9c48c",fontStyle:"italic",marginTop:8}}>{D.cue}</div>}
                </div>
                {overridden&&<div style={{color:MUTE,fontSize:12,margin:"8px 2px 0",fontStyle:"italic"}}>Re-picked after your note — your original call is kept in the record.</div>}
                {/* Confidence: one plain word; the detail + full alternative comparison sit behind Why? */}
                {c.band&&<button onClick={()=>setShowConf(!showConf)} style={{marginTop:12,width:"100%",border:"1px solid #e7e2d8",background:"#fff",borderRadius:12,padding:"10px 12px",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
                  <span style={{display:"flex",alignItems:"center",gap:8,color:INK,fontSize:14,fontWeight:700}}><span style={{width:10,height:10,borderRadius:10,background:bandCol(c.band)}}></span>Confidence: <span style={{color:bandCol(c.band)}}>{c.band}</span></span>
                  <span style={{color:MUTE,fontSize:13}}>{showConf?"hide Why ▾":"Why? ›"}</span>
                </button>}
                {showConf&&(()=>{
                  const comp=[["Player evidence",c.player],["Today's form",c.form],["Course information",c.course],["Observation certainty",c.observation],["Strategic play",c.play],["Execution method",c.execution]];
                  const cands=(D.record&&D.record.candidates)||[];
                  return <div style={{marginTop:8,background:"#fff",borderRadius:14,padding:13,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
                    <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:8}}>Confidence — {c.overall}/100 overall</div>
                    {comp.map(([lab,v])=>v==null?null:<div key={lab} style={{display:"flex",justifyContent:"space-between",fontSize:13,marginBottom:4}}><span style={{color:INK}}>{lab}</span><b style={{color:bandCol(v>=72?"High":v>=52?"Solid":"Limited")}}>{v}</b></div>)}
                    <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",margin:"12px 0 6px"}}>Plays I compared (before I called it)</div>
                    {cands.slice(0,6).map((o,i)=>{const chosen=o.club===D.club&&o.kind===D.kind;
                      return <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",gap:8,fontSize:12,padding:"3px 0",borderTop:i?"1px solid #f2efe8":"none"}}>
                        <span style={{color:chosen?INK:MUTE,fontWeight:chosen?800:600}}>{chosen?"✓ ":""}{o.club} · {o.kind}{o.leaves!=null?` · leaves ${o.leaves}`:""}{o.water>0.05?` · ${Math.round(o.water*100)}% water`:""}</span>
                        <span style={{color:o.executable?MUTE:"#a3402f",whiteSpace:"nowrap"}}>{o.executable?`exp ${o.ev}`:"cut"}</span>
                      </div>;})}
                  </div>;})()}
                <button onClick={()=>{buzz();setAwaitResult(true);}} style={{width:"100%",border:"none",borderRadius:18,padding:"18px",fontSize:19,fontWeight:800,cursor:"pointer",background:GOLD,color:PINE,letterSpacing:1,marginTop:14}}>PLAY IT</button>
                <button onClick={()=>setShowAlt(!showAlt)} style={{width:"100%",border:"none",background:"transparent",color:MUTE,fontSize:14,cursor:"pointer",marginTop:10,fontFamily:SERIF}}>{showAlt?"Keep original call":"Not comfortable?"}</button>
                {showAlt&&(()=>{
                  // Structured objections only — the golfer reports what's off; the caddie re-picks.
                  return <div style={{marginTop:8,background:"#fff",borderRadius:16,padding:14,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
                    <div style={{color:MUTE,fontSize:13,marginBottom:10}}>Tell me what's off — I'll re-pick. You never have to choose the club.</div>
                    <button className="tapbtn" onClick={distrust} style={objBtn}>I don't trust that club</button>
                    <div style={{display:"flex",gap:6,flexWrap:"wrap",margin:"0 0 8px"}}>
                      <div style={{fontSize:12,color:MUTE,width:"100%",marginBottom:2}}>The lie is worse —</div>
                      {[["ROUGH","Rough"],["DEEP","Deep"],["FBUNK","Bunker"],["TREES","Recovery"]].map(([v,lab])=>
                        <button key={v} className="tapbtn" onClick={()=>{setLie(v);setLieLabel(lab);objectWith("lie:"+v,{lie:v});}} style={{border:"1px solid #e7e2d8",borderRadius:10,padding:"8px 12px",background:"#fbfaf7",fontSize:13,fontWeight:700,color:INK,cursor:"pointer"}}>{lab}</button>)}
                    </div>
                    <button className="tapbtn" onClick={()=>{if(!firstDecision)setFirstDecision(decision);setObjections(o=>[...o,"distance"]);setShowAlt(false);setAsked(false);}} style={objBtn}>The distance is wrong</button>
                    <button className="tapbtn" onClick={()=>{if(!firstDecision)setFirstDecision(decision);setObjections(o=>[...o,"window"]);setShowAlt(false);setObsv(null);setAskObs(true);}} style={objBtn}>The window is different</button>
                    <button className="tapbtn" onClick={()=>{setShowConf(true);setShowAlt(false);}} style={objBtn}>Show me why</button>
                    <button onClick={()=>{buzz();addPenalty();}} style={{marginTop:6,border:"none",borderRadius:10,padding:"8px 12px",background:"#f6efe6",color:"#8a6d2f",fontSize:12,fontWeight:700,cursor:"pointer"}}>Add a penalty (stroke & distance)</button>
                  </div>;})()}
              </div>;})()}

            {phase==="drop"&&(()=>{
              // After a water ball: tap the map to drop, so the next shot knows its spot.
              const mapped=Array.isArray(H.path);
              const loc=dropPos?holeContext(H,dropPos.d,dropPos.x):null;
              const confirm=()=>{buzz();setPendingLie(["FW","Fairway"]);
                logShot(awaitDrop.gain,false,false,awaitDrop.dOv,"water",undefined,true,dropPos||undefined);
                setAwaitDrop(null);setDropPos(null);};
              return <div style={arrive}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
                  <div style={{color:MUTE,fontSize:14}}><span style={{color:"#2f6d8c",fontWeight:800}}>WATER</span> · penalty stroke added</div>
                  <button onClick={()=>{setAwaitDrop(null);setDropPos(null);}} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer"}}>↩ back</button>
                </div>
                <div style={{fontFamily:SERIF,fontSize:22,color:INK,textAlign:"center",marginBottom:8}}>Where are you dropping?</div>
                {mapped?<>
                  <div style={{textAlign:"center",color:MUTE,fontSize:12,marginBottom:8}}>{dropPos?"Drop placed — tap to move it":"Tap the map where you'll play from"}</div>
                  <HoleView h={H} P={P} tee={live.tee} ball={dropPos} onPlace={(d,x)=>setDropPos({d,x})}/>
                  {loc&&<div style={{textAlign:"center",fontFamily:SERIF,fontSize:15,color:INK,marginTop:8}}>Dropping {loc.blocked?`blocked ${loc.side} — trees on your line`:loc.side==="center"?"in the middle":`${loc.side} of the fairway`}.</div>}
                </>:<div style={{textAlign:"center",color:MUTE,fontSize:13,margin:"8px 0"}}>This hole isn't mapped yet — continue and enter your distance on the next shot.</div>}
                <button className="tapbtn" onClick={confirm} style={{width:"100%",border:"none",borderRadius:18,padding:"18px",fontSize:17,fontWeight:800,cursor:"pointer",background:PINE,color:PAPER,letterSpacing:.4,marginTop:14}}>{dropPos||!mapped?"Confirm the drop":"Skip — no exact spot"}</button>
              </div>;})()}

            {phase==="result"&&(()=>{const exp=E.chipCarry(sel||"CHIP");
              // P6: a shot has a direction AND a resulting lie. Pick the direction
              // (defaults to On line), then tap where it ended — that logs the shot,
              // feeds the learning engine, and sets up the next shot's lie (P2).
              const dirChips=[["line","On line"],["short","Short"],["long","Long"],["left","Left"],["right","Right"]];
              const gainFor=d=>d==="short"?Math.max(1,exp-10):d==="long"?exp+10:exp;
              const dOf=d=>d==="left"?"L":d==="right"?"R":null;
              const logResult=(lieKey,label,lieVal)=>{
                buzz();
                if(lieKey==="green"){ setPendingLie(null); logShot(live.rem,true,false,dOf(resDir),"green"); return; }
                // Water: don't log yet — first let the player tap where they're dropping,
                // so the engine knows the next position (and the round path stays honest).
                if(lieKey==="water"){ setDropPos(null); setAwaitDrop({gain:gainFor(resDir),dOv:dOf(resDir)}); return; }
                setPendingLie([lieVal,label]);
                logShot(gainFor(resDir),false,false,dOf(resDir),lieKey);
              };
              const lies=[["fairway","Fairway","FW"],["rough","Rough","ROUGH"],["bunker","Bunker","SAND"],["trees","Trees","TREES"],["water","Water","FW"]];
              return <div style={arrive}>
                <div style={{fontFamily:SERIF,fontSize:22,color:INK,textAlign:"center",marginBottom:6}}>Where'd it finish?</div>
                <div style={{textAlign:"center",color:MUTE,fontSize:12,marginBottom:14}}>direction, then where it ended</div>
                <div style={{display:"flex",gap:6,justifyContent:"center",flexWrap:"wrap",marginBottom:16}}>
                  {dirChips.map(([k,l])=>{const on=resDir===k;return <button key={k} className="tapbtn" onClick={()=>setResDir(k)} style={{border:"none",borderRadius:18,padding:"10px 15px",fontSize:14,fontWeight:600,cursor:"pointer",background:on?PINE:"#fff",color:on?PAPER:INK,boxShadow:on?"none":"0 1px 3px rgba(0,0,0,.06)"}}>{l}</button>;})}
                </div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
                  {lies.map(([k,l,v])=>(<button key={k} className="tapbtn" onClick={()=>logResult(k,l,v)} style={{border:"none",borderRadius:16,padding:"20px 10px",fontSize:16,fontWeight:700,cursor:"pointer",background:k==="water"?"#e9f1f6":"#fff",color:k==="water"?"#2f6d8c":INK,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>{l}</button>))}
                  <button className="tapbtn" onClick={()=>logResult("green")} style={{border:"none",borderRadius:16,padding:"20px 10px",fontSize:16,fontWeight:800,cursor:"pointer",background:PINE,color:PAPER}}>On the green</button>
                </div>
              </div>;})()}

            {phase==="putt"&&<div style={arrive}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:18}}>
                <div style={{color:MUTE,fontSize:14}}>On the green</div>
                <button onClick={undoShot} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer"}}>↩ back</button>
              </div>
              <div style={{background:PINE,borderRadius:28,padding:"30px 24px",boxShadow:"0 10px 30px rgba(18,43,33,.18)"}}>
                <div style={{fontFamily:SERIF,fontSize:26,color:GOLD,marginBottom:12}}>{live.i35At!=null?"Convert it.":"Putting."}</div>
                <div style={{fontFamily:SERIF,fontSize:22,color:PAPER,lineHeight:1.5}}>{puttWhisper(live.putts)}</div>
              </div>
              <div style={{display:"flex",gap:10,marginTop:18}}>
                <button onClick={()=>{buzz();saveLive({...live,putts:live.putts+1});}} style={{flex:1,border:"none",borderRadius:16,padding:"18px",fontSize:15,fontWeight:700,cursor:"pointer",background:"#fff",color:INK,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>Missed it · {live.putts} so far</button>
                <button onClick={()=>{buzz();holeOut();}} style={{flex:1,border:"none",borderRadius:16,padding:"18px",fontSize:15,fontWeight:700,cursor:"pointer",background:PINE,color:PAPER}}>Holed</button>
              </div>
            </div>}

            {!tourn&&<div style={{display:"flex",justifyContent:"center",gap:20,marginTop:4}}>
              <button onClick={()=>setShowRep(!showRep)} style={{border:"none",background:"transparent",color:MUTE,fontSize:12,cursor:"pointer"}}>round so far</button>
              <button onClick={()=>setEndArm(!endArm)} style={{border:"none",background:"transparent",color:MUTE,fontSize:12,cursor:"pointer"}}>end round</button>
            </div>}
            {showRep&&<div style={{marginTop:14,background:"#fff",borderRadius:16,padding:16,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
              <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:8}}>Through {done} holes</div>
              <div style={{fontFamily:SERIF,fontSize:20,color:INK}}>{runTot} strokes · {done>0?(dv>0?"+"+dv:dv)+" vs plan":"—"}</div>
            </div>}
            {endArm&&<div style={{marginTop:14,background:"#fff",borderRadius:16,padding:16,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
              <div style={{fontFamily:SERIF,fontSize:17,color:INK,marginBottom:12}}>End the round? {done} holes are saved.</div>
              <div style={{display:"flex",gap:10}}>
                <button onClick={endSave} style={{flex:1,border:"none",borderRadius:14,padding:"14px",background:PINE,color:PAPER,fontWeight:700,cursor:"pointer"}}>Save {done}</button>
                <button onClick={()=>{saveLive(null);store.set("caddie:live",null);setEndArm(false);}} style={{flex:1,border:"none",borderRadius:14,padding:"14px",background:"#f6ece9",color:"#a3402f",fontWeight:700,cursor:"pointer"}}>Discard</button>
                <button onClick={()=>setEndArm(false)} style={{border:"none",borderRadius:14,padding:"14px 16px",background:"#f1efe9",color:INK,cursor:"pointer"}}>✕</button>
              </div>
            </div>}
          </div>;
        })()}
      </div>}

      {tab==="prep"&&<div style={{padding:12}}>
        <div style={{display:"flex",gap:6,marginBottom:10}}>
          {[["body","🔥 Body"],["range","🏌️ Range"],["fuel","🥣 Fuel"]].map(([id,l])=>(
            <button key={id} onClick={()=>setPrepSec(id)} style={{...S.btn,flex:1,padding:"9px 0",fontSize:13,background:prepSec===id?"#1a3a2e":"white",color:prepSec===id?"#86efac":"#3a3a3c",boxShadow:"0 1px 3px rgba(0,0,0,0.06)"}}>{l}</button>))}
        </div>
        {prepSec==="body"&&<>
          <div style={S.card}><div style={S.h}>3-minute focus primer</div><div style={S.sub}>Sit still. 60s — breathe 4 in, 6 out. 60s — see three swings: smooth 74 off the tee, a rotation wedge landing center, a lag dying at the back of the cup. 60s — say it once: "Controlled is straight. Conversion is the round."</div></div>
          <div style={S.card}><div style={S.h}>Dynamic warmup · 8 min</div>
            {[["Glute bridges ×10","Wake the hips — the power source"],["World's greatest stretch ×5/side","Hip flexors + t-spine for the turn"],["Torso rotations ×10/side","Club across chest — rehearse rotation, hands passive"],["Arm circles + wrist rolls ×15","Shoulder prep, matches your training split"],["Tempo-club swings ×10","Long bending club · count of 3 back · no ball"],["Air swings at 74 feel ×5","Calibrate the governor before a ball exists"]].map(([a,b],i)=>(
              <div key={i} style={{padding:"7px 0",borderBottom:i<5?"1px solid #f2f2f7":"none"}}><div style={{fontSize:14,fontWeight:800}}>{a}</div><div style={{fontSize:12,color:"#6e6e73"}}>{b}</div></div>))}
          </div>
        </>}
        {prepSec==="range"&&<div style={S.card}>
          <div style={S.h}>Range protocol · windows FRESH FIRST</div>
          {[["1 · Alignment laser-check","Stick down at the SHORT station first — recent sessions show wedge starts drifting left. Verify before you groove it."],["2 · 52° windows FRESH","3 half · 3 ¾ · 3 full smooth — BEFORE any touch game. Windows read false when checked tired."],["3 · 9i smooth ×5","Most reliable iron. Center targets only."],["4 · 7i smooth ×5 at ≤74","SPEED-CREEP RULE: two straight carries 20+ over stock (or 75+ feel) = end the block on the next flush."],["5 · Putting pace ladder","3 balls each: 10 / 20 / 30 ft — back-of-cup pace."],["6 · Five chips","One look, commit, ON the green. Walk to the tee on a make."]].map(([a,b],i)=>(
            <div key={i} style={{padding:"8px 0",borderBottom:i<5?"1px solid #f2f2f7":"none"}}><div style={{fontSize:14,fontWeight:800}}>{a}</div><div style={{fontSize:12,color:"#6e6e73",lineHeight:1.4}}>{b}</div></div>))}
        </div>}
        {prepSec==="fuel"&&<div style={S.card}><div style={S.h}>Round-day nutrition</div>
          {[["Night before","Carb-forward dinner, full hydration. No experiments."],["2–3 hrs out","The standard: ½ cup oats · 1 scoop protein · chia · granola · honey."],["30 min out","Banana or granola bar + 16 oz water."],["In-round","~150–200 cal every 6 holes. Sip water EVERY hole — dehydration shows up as chunked irons before it feels like thirst. Electrolytes when hot."],["Avoid","Heavy/greasy pre-round · energy drinks mid-round (jitters fight the 74 governor) · alcohol until the card is signed."],["After","Protein within 60 min — feeds the physique program too."]].map(([a,b],i)=>(
            <div key={i} style={{padding:"8px 0",borderBottom:i<5?"1px solid #f2f2f7":"none"}}><div style={{fontSize:14,fontWeight:800}}>{a}</div><div style={{fontSize:12,color:"#6e6e73",lineHeight:1.4}}>{b}</div></div>))}
        </div>}
      </div>}

      {tab==="course"&&<div style={{padding:12}}>
        {!live&&<div style={{display:"flex",gap:8,marginBottom:10}}>
          {Object.entries(courses).map(([k,c])=>(
            <button key={k} onClick={()=>{setCourseSel(k);setCourseHole(0);}} style={{...S.btn,flex:1,padding:"9px 0",fontSize:13,background:courseSel===k?"#1a3a2e":"white",color:courseSel===k?"#86efac":"#3a3a3c",boxShadow:"0 1px 3px rgba(0,0,0,0.06)"}}>{c.name}</button>))}
        </div>}
        <div style={{display:"grid",gridTemplateColumns:"repeat(9,1fr)",gap:3,marginBottom:10}}>
          {CH.map((h,i)=>(
            <button key={h.n} onClick={()=>setCourseHole(i)} style={{height:32,borderRadius:8,border:"none",cursor:"pointer",fontWeight:900,fontSize:12,background:i===courseHole?"#1a3a2e":h.gap?"#ffe5e3":h.star?"#fff8dc":"white",color:i===courseHole?"#86efac":h.gap?"#ff453a":"#111",boxShadow:"0 1px 2px rgba(0,0,0,0.06)",padding:0}}>{h.n}</button>))}
        </div>
        {(()=>{const h=CH[courseHole];return(
          <div style={S.card}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6,flexWrap:"wrap",gap:4}}>
              <div style={S.big}>H{h.n} · Par {h.par} · {h.y}y</div>
              <span style={S.pill("#1a3a2e","#86efac")}>{h.tgt} {h.tgt-h.par===0?"PAR":"BOGEY"}</span>
            </div>
            {h.r3&&<span style={{...S.pill("#7c3aed","white"),marginRight:6}}>R3 {h.r3}</span>}
            {h.gap&&<span style={S.pill("#ff453a","white")}>🔴 GAP HOLE</span>}
            <div style={{...S.sub,margin:"8px 0",background:"#f7f7fa",borderRadius:10,padding:"9px 11px"}}>{h.vibe}</div>
            <MiniMap h={h} P={P} plan={getPlan(h)}/>
            {getPlan(h).map((s,i)=>(
              <div key={i} style={{display:"flex",gap:10,padding:"9px 0",borderTop:"1px solid #f2f2f7"}}>
                <div style={{minWidth:26,height:26,borderRadius:13,background:"#1a3a2e",color:"#86efac",display:"flex",alignItems:"center",justifyContent:"center",fontWeight:900,fontSize:12,flexShrink:0}}>{i+1}</div>
                <div style={{minWidth:0}}><div style={{fontSize:14,fontWeight:800}}>{s.c} — {s.a}</div><div style={{fontSize:12,color:"#6e6e73"}}>{s.t}</div></div>
              </div>))}
            <div style={{background:"#fff1f0",borderRadius:10,padding:"8px 11px",marginTop:8}}>
              <div style={{fontSize:10,fontWeight:800,color:"#ff453a",letterSpacing:1}}>HAZARDS</div>
              <div style={{fontSize:12,color:"#3a3a3c"}}>{h.hz}</div>
            </div>
            <div style={{background:"#eaf4ff",borderRadius:10,padding:"8px 11px",marginTop:6,fontSize:11,fontWeight:800,color:"#0a84ff"}}>🎯 INSIDE 35 — one look · commit · ON in one · two-putt ceiling</div>
          </div>);})()}
        <div style={S.card}>
          <div style={S.h}>Plan card · {CH.reduce((a,h)=>a+h.tgt,0)} total (par {CH.reduce((a,h)=>a+h.par,0)})</div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(9,1fr)",gap:3}}>
            {CH.map(h=>(<div key={h.n} style={{textAlign:"center",padding:"3px 0",borderRadius:6,background:h.gap?"#fff1f0":"#f2f2f7"}}><div style={{fontSize:8,color:"#8a8a8e"}}>{h.n}</div><div style={{fontSize:13,fontWeight:900}}>{h.tgt}</div></div>))}
          </div>
        </div>
      </div>}

      {tab==="rounds"&&<div style={{padding:12}}>
        {rounds.length===0&&<div style={{...S.card,textAlign:"center",padding:26}}><div style={{fontSize:34}}>📈</div><div style={S.big}>No rounds saved yet</div><div style={S.sub}>Finish a round in PLAY and it lands here for good — score, putts, conversion, benched clubs.</div></div>}
        {rounds.length>0&&(()=>{
          const last=rounds[rounds.length-1];
          const avg=f=>Math.round(rounds.reduce((a,r)=>a+f(r),0)/rounds.length*10)/10;
          const cp=r=>r.convTried?Math.round(r.convMade/r.convTried*100):0;
          const sugg=[];
          if(avg(cp)<50)sugg.push("Inside-35 conversion is still the #1 stroke leak — garage 13-ball conversion game 3×/week. Every conversion point ≈ 1–2 strokes.");
          if(avg(r=>r.putts)>35)sugg.push("Putts running high — pace ladder before every round, hold the two-putt ceiling.");
          const bc={};rounds.forEach(r=>(r.benched||[]).forEach(k=>bc[k]=(bc[k]||0)+1));
          const cold=Object.entries(bc).filter(([k,v])=>v>=2);
          if(cold.length)sugg.push(`Benched ${cold.map(([k,v])=>`${k} (${v}×)`).join(", ")} across rounds — that club needs a dedicated range block, not more course exposure.`);
          if(rounds.length>=2&&rounds[rounds.length-1].total<rounds[rounds.length-2].total)sugg.push("Scores trending down — the system works. Change nothing; add reps.");
          if(!sugg.length)sugg.push("Numbers holding. Next unlock: build the PW partial to close the 90–115 gap.");
          return(<>
          <div style={S.card}>
            <div style={S.h}>Latest · {last.date}</div>
            <div style={{display:"flex",gap:18,flexWrap:"wrap"}}>
              <div><div style={S.big}>{last.total}</div><div style={{fontSize:10,color:"#8a8a8e"}}>vs plan {last.plan} ({last.total-last.plan>=0?"+":""}{last.total-last.plan})</div></div>
              <div><div style={S.big}>{last.convMade}/{last.convTried}</div><div style={{fontSize:10,color:"#8a8a8e"}}>inside-35</div></div>
              <div><div style={S.big}>{last.putts}</div><div style={{fontSize:10,color:"#8a8a8e"}}>putts</div></div>
            </div>
          </div>
          <div style={S.card}>
            <div style={S.h}>All rounds ({rounds.length}) · tap a round to edit · baselines: 103 · 37p · 2/13</div>
            {trMsg&&<div style={{fontSize:12,fontWeight:700,color:"#1a7f37",marginBottom:6}}>{trMsg}</div>}
            {rounds.slice().reverse().map((r,i)=>{const ri=rounds.length-1-i;const open=editIdx===ri;
              return (<div key={ri} style={{borderBottom:"1px solid #f2f2f7",paddingBottom:open?10:0}}>
                <div onClick={()=>{setEditIdx(open?null:ri);setTrMsg("");}} style={{display:"flex",justifyContent:"space-between",padding:"9px 0",cursor:"pointer",flexWrap:"wrap"}}>
                  <span style={{fontSize:13,color:"#6e6e73"}}>{open?"▾ ":"▸ "}{r.date}{r.course?" · "+r.course.split(" ")[0]:""}</span>
                  <span style={{fontSize:13,fontWeight:800}}>{r.total}{r.holes&&r.holes<18?" ("+r.holes+"h)":""} <span style={{color:"#8a8a8e",fontWeight:400}}>· {r.putts}p · 🎯{r.convMade}/{r.convTried}</span></span>
                </div>
                {open&&<>
                  <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:5,marginBottom:8}}>
                    {r.scores.map((sc,hi)=>(
                      <div key={hi} style={{display:"flex",alignItems:"center",justifyContent:"space-between",background:"#f7f7fa",borderRadius:8,padding:"3px 5px"}}>
                        <button onClick={()=>editHole(ri,hi,-1)} style={{border:"none",background:"none",fontSize:15,fontWeight:900,cursor:"pointer",color:"#8a8a8e",padding:"2px 5px"}}>−</button>
                        <div style={{textAlign:"center"}}><div style={{fontSize:7,color:"#8a8a8e"}}>H{hi+1}</div><div style={{fontSize:14,fontWeight:900,color:sc<=CH[hi].tgt?"#1a7f37":sc>=7?"#ff453a":"#111"}}>{sc}</div></div>
                        <button onClick={()=>editHole(ri,hi,1)} style={{border:"none",background:"none",fontSize:15,fontWeight:900,cursor:"pointer",color:"#8a8a8e",padding:"2px 5px"}}>+</button>
                      </div>))}
                  </div>
                  <div style={{display:"flex",gap:8}}>
                    <button onClick={()=>shareRound(r)} style={{...S.btn,flex:1,padding:"10px",background:"#0a84ff",color:"white",fontSize:13}}>SHARE / EXPORT</button>
                    <button onClick={()=>delRound(ri)} style={{...S.btn,padding:"10px 14px",background:"#fff1f0",color:"#ff453a",fontSize:13}}>{delArm===ri?"TAP TO CONFIRM":"DELETE"}</button>
                  </div>
                </>}
              </div>);})}
          </div>
      <div style={S.card}>
        <div style={S.h}>Player ratings — all rounds</div>
        {(()=>{const g=v=>v>=90?"A":v>=80?"B":v>=70?"C":v>=55?"D":"F";
          const avgVs=rounds.reduce((a,r)=>a+(r.total-r.plan),0)/rounds.length;
          const cT=rounds.reduce((a,r)=>a+r.convTried,0);const conv=cT?rounds.reduce((a,r)=>a+r.convMade,0)/cT:0;
          const ppr=rounds.reduce((a,r)=>a+r.putts,0)/rounds.length;
          const blow=rounds.reduce((a,r)=>a+r.scores.filter(x=>x>=7).length,0)/rounds.length;
          // Ball-striking from OUTCOMES — how often struck shots find the short grass —
          // not a distance vs a stock number the on-course flow can't measure. (A drive
          // into the trees has to count against you; penalties are excluded, not NaN'd.)
          const struck=rounds.flatMap(r=>(r.shots||[]).filter(x=>!x.pen));
          const grassHit=struck.filter(x=>x.g||["green","fairway","first"].includes(x.end)).length;
          const bsPct=struck.length?Math.round(grassHit/struck.length*100):null;
          const rows=[["Scoring",Math.max(0,Math.min(100,Math.round(100-avgVs*6))),`${avgVs>=0?"+":""}${avgVs.toFixed(1)} vs plan`],
            ["Short game",Math.max(0,Math.min(100,Math.round(conv*100))),`${Math.round(conv*100)}% inside-35`],
            ["Putting",Math.max(0,Math.min(100,Math.round(100-(ppr-30)*5))),`${ppr.toFixed(1)} putts/round`],
            bsPct!==null?["Ball-striking",bsPct,`${bsPct}% found the short grass`]:null,
            ["Discipline",Math.max(0,Math.min(100,Math.round(100-blow*18))),`${blow.toFixed(1)} blowups/round`]].filter(Boolean);
          return rows.map((r,i)=>(<div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 0",borderBottom:"1px solid #f2f2f7",gap:8}}>
            <span style={{fontSize:14,fontWeight:800,flexShrink:0}}>{r[0]}</span>
            <span style={{fontSize:11,color:"#6e6e73",flex:1,textAlign:"right"}}>{r[2]}</span>
            <span style={{fontSize:16,fontWeight:900,minWidth:44,textAlign:"right",color:r[1]>=80?"#1a7f37":r[1]>=60?"#ff9f0a":"#ff453a"}}>{g(r[1])} <span style={{fontSize:10,color:"#8a8a8e"}}>{r[1]}</span></span>
          </div>));})()}
      </div>
      <div style={S.card}>
        <div style={S.h}>Club report — every tracked shot</div>
        {(()=>{const all=rounds.flatMap(r=>r.shots||[]);if(!all.length)return <div style={S.sub}>Play a round — every club selection is logged automatically and reported here.</div>;
          const fams=["52",...Object.keys(P.carries)];
          const rows=fams.map(f=>{const mine=all.filter(x=>famOf(x.c)===f&&!x.p);if(!mine.length)return null;
            // Hot/cold from where the ball FINISHED (the confidence engine), not distance
            // deviation — so a club that keeps ending in trees/rough cools, as it should.
            const cc=clubConfidence(mine,cstat(f));
            const grass=mine.filter(x=>x.g||["green","fairway","first"].includes(x.end)).length;
            const gpct=Math.round(grass/mine.length*100);
            const errs=mine.filter(x=>!x.g&&(!x.lie||x.lie==="FW")&&x.gain!=null&&x.exp!=null&&x.from>x.exp+8).map(x=>x.gain-x.exp);
            const m=errs.length?errs.reduce((a,b)=>a+b,0)/errs.length:0;
            const sd=errs.length>1?Math.round(Math.sqrt(errs.reduce((a,b)=>a+(b-m)*(b-m),0)/errs.length)):0;
            return {f,n:mine.length,gpct,sd,state:cc.state,score:cc.score};}).filter(Boolean);
          const stLbl=s=>s==="hot"?"HOT":s==="cold"?"COLD":"STEADY";
          const stCol=s=>s==="hot"?"#1a7f37":s==="cold"?"#ff453a":"#ff9f0a";
          return rows.map((r,i)=>(<div key={i} style={{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid #f2f2f7"}}>
            <span style={{fontSize:14,fontWeight:800}}>{r.f}</span>
            <span style={{fontSize:12,color:"#3a3a3c"}}>{r.n} shots · {r.gpct}% found grass{r.sd>0?` · ±${r.sd}y`:""}{(()=>{const b=dirBias(r.f);return b?" · miss "+b:"";})()} · <span style={{fontWeight:800,color:stCol(r.state)}}>{stLbl(r.state)}</span> <span style={{color:"#8a8a8e"}}>{r.score}</span></span>
          </div>));})()}
      </div>
          <div style={{...S.card,background:"#1a3a2e"}}>
            <div style={{...S.h,color:"#86efac"}}>Coach's read</div>
            {sugg.map((s,i)=><div key={i} style={{color:"white",fontSize:13,lineHeight:1.5,marginBottom:6}}>▸ {s}</div>)}
          </div></>);})()}
      </div>}

      {tab==="me"&&<div style={{padding:12}}>
        <div style={S.card}>
          <div style={S.h}>Player</div>
          <input value={P.name} onChange={e=>setP({...P,name:e.target.value})} style={{...S.inp,width:"100%"}}/>
        </div>

        {P.clubStats&&Object.keys(P.clubStats).length>0&&(()=>{
          const lbl=k=>k==="52m"?"52° wedge":k==="Dr"?"Driver":k;
          const cs=P.clubStats;const keys=Object.keys(cs).sort((a,b)=>cs[b].carry-cs[a].carry);
          const scoring=keys.filter(k=>cs[k].carry<=140);
          const best=scoring.slice().sort((a,b)=>cs[a].sd-cs[b].sd)[0];
          const longest=keys[0];
          const shaky=keys.slice().sort((a,b)=>cs[b].sd-cs[a].sd)[0];
          const shortMiss=keys.filter(k=>cs[k].shortRate>=60).sort((a,b)=>cs[b].shortRate-cs[a].shortRate)[0];
          const proven=c=>c.side&&(c.side.n==null||c.side.n>=SIDE_PROVEN);
          const sideMiss=keys.filter(k=>proven(cs[k])&&cs[k].side.pct>=60).sort((a,b)=>cs[b].side.pct-cs[a].side.pct)[0];
          // "misses right ~12y (94%)" for a proven club; "early right read" when the
          // sample's still too small to trust — the club has to earn the aim-off.
          const sideBit=c=>{if(!c.side)return"";const dir=c.side.dir==="R"?"right":"left";const md=c.side.med!=null?" ~"+Math.abs(c.side.med)+(c.side.unit||"y"):"";
            return proven(c)?(c.side.pct>=58?` · misses ${dir}${md} (${c.side.pct}%)`:""):` · early ${dir} read (${c.side.n||"few"})`;};
          const rel=sd=>sd<=5?["ROCK SOLID","#1a7f37"]:sd<=9?["reliable","#1a7f37"]:sd<=14?["variable","#ff9f0a"]:["inconsistent","#ff453a"];
          const attack=keys.filter(k=>cs[k].carry>=175&&cs[k].carry<=260).slice(-1)[0];
          return (<div style={{...S.card,background:"#1a3a2e"}}>
            <div style={{color:"#86efac",fontSize:10,letterSpacing:2,fontWeight:800,marginBottom:2}}>{(P.name||"YOUR").toUpperCase()}'S CADDIE PROFILE</div>
            <div style={{color:"white",fontSize:12,marginBottom:10,opacity:0.75}}>Built from your uploaded shots — {Object.values(cs).reduce((a,c)=>a+c.n,0)} strikes analyzed.</div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:10}}>
              <div style={{background:"rgba(255,255,255,0.08)",borderRadius:10,padding:"8px 10px"}}>
                <div style={{color:"#6b9e7a",fontSize:9,fontWeight:800,letterSpacing:1}}>LONGEST</div>
                <div style={{color:"white",fontSize:15,fontWeight:800}}>{lbl(longest)} · {cs[longest].carry}y</div>
              </div>
              {best&&<div style={{background:"rgba(255,255,255,0.08)",borderRadius:10,padding:"8px 10px"}}>
                <div style={{color:"#6b9e7a",fontSize:9,fontWeight:800,letterSpacing:1}}>BEST SCORING CLUB</div>
                <div style={{color:"white",fontSize:15,fontWeight:800}}>{lbl(best)} · ±{cs[best].sd}y</div>
              </div>}
              {shaky&&cs[shaky].sd>10&&<div style={{background:"rgba(255,69,58,0.18)",borderRadius:10,padding:"8px 10px"}}>
                <div style={{color:"#ffb3ad",fontSize:9,fontWeight:800,letterSpacing:1}}>LEAST TRUSTED</div>
                <div style={{color:"white",fontSize:15,fontWeight:800}}>{lbl(shaky)} · ±{cs[shaky].sd}y</div>
              </div>}
              {attack&&<div style={{background:"rgba(255,255,255,0.08)",borderRadius:10,padding:"8px 10px"}}>
                <div style={{color:"#6b9e7a",fontSize:9,fontWeight:800,letterSpacing:1}}>SMART TARGET</div>
                <div style={{color:"white",fontSize:15,fontWeight:800}}>Middle greens {cs[attack].carry}+</div>
              </div>}
            </div>
            {shortMiss&&<div style={{color:"#fcd34d",fontSize:12,fontWeight:700,marginBottom:6}}>⚠ {lbl(shortMiss)} finishes short {cs[shortMiss].shortRate}% of the time — the engine already plays it one club up.</div>}
            {sideMiss&&<div style={{color:"#fcd34d",fontSize:12,fontWeight:700,marginBottom:8}}>⟵⟶ {lbl(sideMiss)} misses {cs[sideMiss].side.dir==="R"?"right":"left"} {cs[sideMiss].side.med!=null?"~"+Math.abs(cs[sideMiss].side.med)+(cs[sideMiss].side.unit||"y")+" ":""}({cs[sideMiss].side.pct}%, {cs[sideMiss].side.n||"?"} shots) — aim the fat side.</div>}
            <div style={{borderTop:"1px solid rgba(255,255,255,0.12)",paddingTop:6}}>
              {keys.map(k=>{const c=cs[k],[word,col]=rel(c.sd);
                return <div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"4px 0"}}>
                  <span style={{color:"white",fontSize:13,fontWeight:800,minWidth:74}}>{lbl(k)}</span>
                  <span style={{color:"#9fd6b4",fontSize:12,flex:1,textAlign:"right"}}>{c.carry}y · plays {c.lowN}–{c.hiN}{sideBit(c)} · {c.n} shots</span>
                  <span style={{fontSize:11,fontWeight:800,color:col==="#1a7f37"?"#86efac":col,minWidth:74,textAlign:"right"}}>±{c.sd}y {word}</span>
                </div>;})}
            </div>
          </div>);})()}

        <div style={{...S.card,border:dragOver?"2.5px dashed #30d158":"2.5px dashed #c7c7cc"}}
          onDragOver={e=>{e.preventDefault();setDragOver(true);}}
          onDragLeave={()=>setDragOver(false)}
          onDrop={e=>{e.preventDefault();setDragOver(false);handleImportFiles(e.dataTransfer.files);}}>
          <div style={S.h}>Upload launch-monitor data</div>
          {!imp&&<>
            <div style={{...S.sub,fontSize:12,marginBottom:10}}>Drop your <b>SC4 Pro</b> (or any launch-monitor) <b>.csv</b> export here — or tap to browse. We detect the format automatically, recognize your clubs, drop mishits and duplicates, and set your stock carries. No formatting required.</div>
            <label htmlFor="lm-file" style={{...S.btn,display:"block",textAlign:"center",background:"#1a3a2e",color:"#86efac",cursor:"pointer"}}>📥 Choose CSV file</label>
            <input id="lm-file" type="file" accept=".csv,.txt,.tsv" style={{display:"none"}} onChange={e=>handleImportFiles(e.target.files)}/>
            {impErr&&<div style={{marginTop:8,fontSize:12,fontWeight:700,color:"#ff453a"}}>⚠ {impErr}</div>}
            <div style={{fontSize:11,color:"#8a8a8e",marginTop:8}}>We read distance <b>and</b> left/right: if your export includes side-carry tracing or spin axis, we learn each club's miss side too.</div>
          </>}
          {imp&&(()=>{const lbl=k=>k==="52m"?"52° wedge":k==="Dr"?"Driver":k;
            const rm=imp.removed,dropped=rm.unusable+rm.impossible+rm.duplicate+rm.mishit;
            const keys=Object.keys(imp.clubs).sort((a,b)=>imp.clubs[b].carry-imp.clubs[a].carry);
            return (<>
              <div style={{...S.big,fontSize:20,color:"#1a7f37"}}>We found {imp.raw} shots{imp.fileName?" in "+imp.fileName:""}.</div>
              <div style={{...S.sub,fontSize:12,margin:"4px 0 10px"}}>Here's what your caddie will learn. Review, then import.</div>
              <div style={{border:"1px solid #eee",borderRadius:10,overflow:"hidden",marginBottom:10}}>
                {keys.map((k,i)=>{const c=imp.clubs[k];const isNew=P.carries[k]===undefined&&k!=="52m";
                  return <div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 10px",background:i%2?"#fafafa":"white",gap:8}}>
                    <span style={{fontSize:14,fontWeight:800,minWidth:70}}>{lbl(k)}</span>
                    <span style={{fontSize:12,color:"#3a3a3c",flex:1,textAlign:"right"}}>{c.n} shots → <b>{c.carry}y</b> (plays {c.lowN}–{c.hiN}) · ±{c.sd}y{c.shortRate>=60?" · short "+c.shortRate+"%":""}{c.side&&c.side.pct>=58?" · misses "+(c.side.dir==="R"?"right":"left")+" "+c.side.pct+"%":""}</span>
                    <span style={S.pill(isNew?"#e7f7ec":"#eef2ff",isNew?"#1a7f37":"#3730a3")}>{isNew?"NEW":"UPDATE"}</span>
                  </div>;})}
              </div>
              {dropped>0&&<div style={{fontSize:11,color:"#8a8a8e",marginBottom:6}}>Filtered out {dropped}: {[rm.mishit&&rm.mishit+" mishits",rm.duplicate&&rm.duplicate+" duplicates",rm.impossible&&rm.impossible+" impossible readings",rm.unusable&&rm.unusable+" blank rows"].filter(Boolean).join(" · ")}.</div>}
              {imp.unknownLabels.length>0&&<div style={{fontSize:11,color:"#c2410c",marginBottom:6}}>⚠ Couldn't recognize {imp.unknownLabels.length} label(s): {imp.unknownLabels.slice(0,6).join(", ")} — those shots were skipped.</div>}
              {imp.patch.w52&&(()=>{const w=imp.patch.w52;return w.half&&w.tq?
                <div style={{fontSize:11,color:"#1a7f37",marginBottom:8}}>Wedge effort windows learned from swing speed — half {w.half[0]}–{w.half[1]}, ¾ {w.tq[0]}–{w.tq[1]}, full {w.fs[0]}–{w.fs[1]}y.</div>
                :<div style={{fontSize:11,color:"#1a7f37",marginBottom:8}}>Your scoring-wedge full window set to {w.fs[0]}–{w.fs[1]}y.</div>;})()}
              <div style={{display:"flex",gap:8}}>
                <button onClick={applyImport} style={{...S.btn,flex:1,background:"#1a3a2e",color:"#86efac"}}>IMPORT — LEARN MY GAME</button>
                <button onClick={()=>{setImp(null);setImpErr("");}} style={{...S.btn,background:"#f2f2f7",color:"#111"}}>Cancel</button>
              </div>
            </>);})()}
        </div>

        <div style={S.card}>
          <div style={S.h}>Course & hole maps</div>
          <div style={{...S.sub,fontSize:12,marginBottom:8}}>Play any course by importing its holes. Upload a Shot Scope screenshot in your Claude chat and ask for a "CaddieOS hole JSON" — paste the result here. Each hole needs at least <b>par</b> and <b>y</b> (yards); it can also carry hazards, a forced-carry, dogleg, and a strategy.</div>
          <textarea value={holeJson} onChange={e=>setHoleJson(e.target.value)} placeholder='{"name":"Pine Valley #6","holes":[{"n":6,"par":5,"y":520,"hz":"Water RIGHT · dogleg RIGHT · bunkers at green","dzR":"water","carry":210,"carryLabel":"the creek","strategy":"Driver, then lay up to 100."}]}' style={{...S.inp,width:"100%",minHeight:70,fontFamily:"monospace",fontSize:12,fontWeight:400}}/>
          <div style={{display:"flex",gap:8,marginTop:8}}>
            <button className="tapbtn" onClick={()=>importHoles(holeJson)} style={{...S.btn,flex:1,background:"#1a3a2e",color:"#86efac"}}>Import holes</button>
            <button className="tapbtn" onClick={()=>setHoleJson(JSON.stringify({name:"My course",holes:[{n:1,par:4,y:410,hz:"Water LEFT · bunker right of green",dzL:"water",carry:0,corner:250,cornerLabel:"corner",strategy:"Driver up the right, wedge in."}]},null,0))} style={{...S.btn,background:"white",color:"#1a3a2e",border:"2px solid #1a3a2e"}}>Template</button>
          </div>
          {holeMsg&&<div style={{fontSize:12,fontWeight:700,color:/Imported/.test(holeMsg)?"#1a7f37":"#c2410c",marginTop:8}}>{holeMsg}</div>}
          {Object.keys(impCourses).length>0&&<div style={{marginTop:10,borderTop:"1px solid #f2f2f7",paddingTop:8}}>
            <div style={{...S.h,marginBottom:6}}>Imported courses</div>
            {Object.entries(impCourses).map(([k,c])=>(<div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"5px 0"}}>
              <span style={{fontSize:13,fontWeight:700,color:"#111"}}>{c.name} · {c.holes.length} holes</span>
              <button className="tapbtn" onClick={()=>deleteCourse(k)} style={{border:"none",background:"#fff1f0",color:"#ff453a",borderRadius:8,padding:"5px 10px",fontSize:11,fontWeight:800,cursor:"pointer"}}>Remove</button>
            </div>))}
          </div>}
        </div>

        <div style={S.card}>
          <div style={S.h}>Your bag — add every club you carry</div>
          {Object.keys(P.carries).sort((a,b)=>P.carries[a]-P.carries[b]).map(k=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"6px 0",borderBottom:"1px solid #f2f2f7",gap:8}}>
              <span style={{fontSize:15,fontWeight:800,flex:1}}>{k}</span>
              <input type="number" value={P.carries[k]} onChange={e=>setP({...P,carries:{...P.carries,[k]:parseInt(e.target.value)||0}})} style={{...S.inp,width:70,textAlign:"center",padding:"8px 4px"}}/>
              {Object.keys(P.carries).length>1&&<button onClick={()=>{const c={...P.carries};delete c[k];setP({...P,carries:c});}} style={{border:"none",background:"#fff1f0",color:"#ff453a",borderRadius:8,width:30,height:30,fontWeight:900,cursor:"pointer"}}>✕</button>}
            </div>))}
          <div style={{display:"flex",gap:6,marginTop:10}}>
            <input value={newName} onChange={e=>setNewName(e.target.value)} placeholder="Club (6i, GW, 58°…)" style={{...S.inp,flex:1,fontSize:16,padding:"9px 10px"}}/>
            <input type="number" value={newCarry} onChange={e=>setNewCarry(e.target.value)} placeholder="yds" style={{...S.inp,width:64,fontSize:16,padding:"9px 6px",textAlign:"center"}}/>
            <button onClick={()=>{if(newName.trim()&&parseInt(newCarry)>0){setP({...P,carries:{...P.carries,[newName.trim()]:parseInt(newCarry)}});setNewName("");setNewCarry("");}}} style={{...S.btn,background:"#1a3a2e",color:"#86efac",padding:"9px 14px"}}>ADD</button>
          </div>
          <div style={{fontSize:11,color:"#8a8a8e",marginTop:6}}>Clubs ≤168y join approach and layup logic automatically; longer clubs stay tee-only. Hit SAVE PROFILE below to lock changes in.</div>
        </div>
        <div style={S.card}>
          <div style={S.h}>52° rotation windows</div>
          {[["half","Half"],["tq","Three-quarter"],["fs","Full smooth"]].map(([k,l])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"6px 0",borderBottom:"1px solid #f2f2f7"}}>
              <span style={{fontSize:14,fontWeight:800}}>{l}</span>
              <div style={{display:"flex",gap:5,alignItems:"center"}}>
                <input type="number" value={P.w52[k][0]} onChange={e=>setP({...P,w52:{...P.w52,[k]:[parseInt(e.target.value)||0,P.w52[k][1]]}})} style={{...S.inp,width:56,textAlign:"center",padding:"8px 4px"}}/>
                <span>–</span>
                <input type="number" value={P.w52[k][1]} onChange={e=>setP({...P,w52:{...P.w52,[k]:[P.w52[k][0],parseInt(e.target.value)||0]}})} style={{...S.inp,width:56,textAlign:"center",padding:"8px 4px"}}/>
              </div>
            </div>))}
        </div>
        <button onClick={()=>{const p={...P,schemaV:SCHEMA,updated:new Date().toISOString()};setP(p);store.set("caddie:profile",p);setMeMsg("Saved — the engine now runs on your numbers.");}} style={{...S.btn,width:"100%",background:"#1a3a2e",color:"#86efac",marginBottom:8}}>SAVE PROFILE</button>
        {meMsg&&<div style={{textAlign:"center",fontSize:12,fontWeight:700,color:"#1a7f37",marginBottom:8}}>{meMsg}</div>}
        {/* ===== PLAYER DATA — safe clearing controls (Part 11). ===== */}
        <div style={S.card}>
          <div style={S.h}>Player Data</div>
          <div style={{...S.sub,fontSize:12,marginBottom:10}}>Clear the parts you want. Long-term club data and completed rounds are only touched by the actions that say so.</div>
          <button className="tapbtn" onClick={resetTodayForm} style={{...S.btn,width:"100%",background:"#f1efe9",color:INK,marginBottom:8,textAlign:"left"}}>Reset today's form <span style={{color:MUTE,fontWeight:600,fontSize:12}}>· warm-up + temporary adjustments</span></button>
          {live&&<button className="tapbtn" onClick={()=>{if(dataArm==="round"){clearCurrentRound();}else setDataArm("round");}} style={{...S.btn,width:"100%",background:dataArm==="round"?"#f6ece9":"#f1efe9",color:dataArm==="round"?"#a3402f":INK,marginBottom:8,textAlign:"left"}}>{dataArm==="round"?"Tap again to clear the active round":"Clear current round"} <span style={{color:MUTE,fontWeight:600,fontSize:12}}>· keeps completed rounds</span></button>}
          <div style={{fontSize:12,color:MUTE,margin:"4px 0 6px"}}>Reset one club's data:</div>
          <div style={{display:"flex",gap:5,flexWrap:"wrap",marginBottom:8}}>
            {Object.keys(P.carries||{}).map(k=>(<button key={k} className="tapbtn" onClick={()=>setDataArm("club:"+k)} style={{border:"1px solid #e7e2d8",borderRadius:10,padding:"7px 11px",fontSize:13,fontWeight:700,cursor:"pointer",background:dataArm==="club:"+k?"#f6ece9":"#fbfaf7",color:dataArm==="club:"+k?"#a3402f":INK}}>{k}</button>))}
          </div>
          {dataArm&&dataArm.startsWith("club:")&&<div style={{background:"#faf3ee",borderRadius:12,padding:"10px 12px",marginBottom:8}}>
            <div style={{fontSize:13,color:INK,marginBottom:8}}>Clear all capability data for <b>{dataArm.slice(5)}</b>? Other clubs are untouched.</div>
            <div style={{display:"flex",gap:8}}>
              <button className="tapbtn" onClick={()=>resetClubData(dataArm.slice(5))} style={{flex:1,border:"none",borderRadius:10,padding:"10px",background:"#a3402f",color:"#fff",fontWeight:800,cursor:"pointer"}}>Clear {dataArm.slice(5)}</button>
              <button className="tapbtn" onClick={()=>setDataArm(null)} style={{flex:1,border:"none",borderRadius:10,padding:"10px",background:"#f1efe9",color:INK,fontWeight:700,cursor:"pointer"}}>Cancel</button>
            </div></div>}
          <div style={{height:1,background:"#f0eee8",margin:"10px 0"}}></div>
          <button className="tapbtn" onClick={()=>{if(dataArm==="fresh"){clearAllPlayerData(true);}else setDataArm("fresh");}} style={{...S.btn,width:"100%",background:dataArm==="fresh"?"#f6ece9":"#f1efe9",color:dataArm==="fresh"?"#a3402f":INK,marginBottom:8,textAlign:"left"}}>{dataArm==="fresh"?"Tap again — clear player data, keep courses":"Start fresh, keep courses"} <span style={{color:MUTE,fontWeight:600,fontSize:12}}>· preserves imported course files</span></button>
          {dataArm!=="all2"?
            <button className="tapbtn" onClick={()=>setDataArm("all2")} style={{...S.btn,width:"100%",background:"#fff",color:"#a3402f",border:"2px solid #e7c3ba",textAlign:"left"}}>Clear ALL player data…</button>
            :<div style={{background:"#faf0ec",border:"2px solid #e7c3ba",borderRadius:12,padding:"12px 13px"}}>
              <div style={{fontSize:13,fontWeight:800,color:"#a3402f",marginBottom:4}}>This removes everything about you:</div>
              <div style={{fontSize:12,color:INK,lineHeight:1.5,marginBottom:10}}>profile, clubs, carries, benched state, shot history, all rounds, decision records, warm-up, cues and imported data. Mapped courses stay. This can't be undone.</div>
              <div style={{display:"flex",gap:8}}>
                <button className="tapbtn" onClick={()=>clearAllPlayerData(false)} style={{flex:1,border:"none",borderRadius:10,padding:"12px",background:"#a3402f",color:"#fff",fontWeight:800,cursor:"pointer"}}>Yes, clear everything</button>
                <button className="tapbtn" onClick={()=>setDataArm(null)} style={{flex:1,border:"none",borderRadius:10,padding:"12px",background:"#f1efe9",color:INK,fontWeight:700,cursor:"pointer"}}>Cancel</button>
              </div></div>}
        </div>
        <div style={S.card}>
          <div style={S.h}>Notes — optional swing cues, in your words</div>
          <div style={{...S.sub,fontSize:12,marginBottom:8}}>Kept for your reference. The caddie's live cue now comes from the current shot, not a saved club message — these no longer auto-appear on recommendations.</div>
          {Object.keys(P.feels||{}).map(k=>(
            <div key={k} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:"1px solid #f2f2f7"}}>
              <span style={{fontSize:13,fontWeight:900,minWidth:42}}>{k}</span>
              <input value={P.feels[k]} onChange={e=>setP({...P,feels:{...P.feels,[k]:e.target.value}})} style={{...S.inp,flex:1,fontSize:16,fontWeight:600,padding:"8px 10px"}}/>
            </div>))}
          <div style={{fontSize:11,color:"#8a8a8e",marginTop:6}}>Hit SAVE PROFILE above to lock them in.</div>
        </div>
        <div style={S.card}>
          <div style={S.h}>Data drop — chat-to-caddie import</div>
          <div style={{...S.sub,fontSize:12,marginBottom:8}}>Paste launch-monitor numbers into any Claude chat and say: "Format as CaddieOS profile JSON with keys name, carries, w52." Paste the result here.</div>
          <textarea value={impTxt} onChange={e=>setImpTxt(e.target.value)} placeholder='{"name":"...","carries":{...},"w52":{...}}' style={{...S.inp,width:"100%",minHeight:64,fontFamily:"monospace",fontSize:12,fontWeight:400}}/>
          <div style={{display:"flex",gap:8,marginTop:8}}>
            <button onClick={()=>{try{const j=JSON.parse(impTxt);const p={...P,...j,updated:new Date().toISOString()};setP(p);store.set("caddie:profile",p);setMeMsg("Imported ✓");setImpTxt("");}catch(e){setMeMsg("Couldn't read that JSON — check the format.");}}} style={{...S.btn,flex:1,background:"#0a84ff",color:"white"}}>IMPORT</button>
            <button onClick={()=>{setImpTxt(JSON.stringify({name:P.name,carries:P.carries,w52:P.w52}));setMeMsg("Exported — copy it anywhere.");}} style={{...S.btn,flex:1,background:"white",color:"#0a84ff",border:"2px solid #0a84ff"}}>EXPORT</button>
          </div>
        </div>
        <div style={{...S.sub,fontSize:11,color:"#8a8a8e",textAlign:"center"}}>Profile + rounds persist on this device across sessions.</div>
        <div style={{...S.sub,fontSize:10,color:"#b0b0b4",textAlign:"center",marginTop:4}}>CaddieOS · {BUILD}</div>
      </div>}

      {!tourn&&<div style={{position:"fixed",bottom:0,left:0,right:0,maxWidth:430,margin:"0 auto",background:"rgba(250,248,244,0.97)",backdropFilter:"blur(12px)",borderTop:"1px solid #e7e2d8",display:"flex",paddingBottom:8,zIndex:60,boxSizing:"border-box"}}>
        <TabBtn id="caddie" label="CADDIE"/>
        <TabBtn id="rounds" label="ROUNDS"/>
        <TabBtn id="me" label="ME"/>
      </div>}
    </div>
  );
}
