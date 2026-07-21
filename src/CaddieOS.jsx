import { useState, useEffect } from "react";
import { whisper, humanClub, teeWhisper, puttWhisper, benchWhisper } from "./whisper.js";

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
  const pick=(y)=>{
    const bag=Object.keys(P.carries).filter(k=>!out(k)).sort((a,b)=>eff(a)-eff(b));
    if(!y||y<=0) return {chip:bag[0]||"7i",fam:bag[0]||"7i",reach:false,leaves:0,carry:0};
    if(y<=34){ const r=rec(y); return {chip:r.chip,fam:"chip",reach:true,leaves:0,carry:chipCarry(r.chip)}; }
    if(y<=W.fs[1]&&!out("52")){ const r=rec(y); return {chip:r.chip,fam:"52",reach:true,leaves:0,carry:chipCarry(r.chip)}; }
    if(!bag.length) return {chip:"7i",fam:"7i",reach:false,leaves:y,carry:0};
    const reachK=bag.filter(k=>eff(k)>=y-6);         // clubs that carry the number (small tolerance)
    if(reachK.length){ const k=reachK[0];            // take just enough club, no more
      return {chip:k,fam:k,reach:true,leaves:Math.max(0,y-eff(k)),carry:eff(k)}; }
    const k=bag[bag.length-1];                        // can't get home -> longest club, advance
    return {chip:k,fam:k,reach:false,leaves:y-eff(k),carry:eff(k)};
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
const impNorm=h=>String(h||"").toLowerCase().replace(/[()]/g," ").replace(/[_\-]/g," ")
  .replace(/\b(yds|yards|yard|mph|rpm|deg|degrees|ft|feet|m)\b/g," ")
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
      spdLo:spd?spd.lo:null,spdHi:spd?spd.hi:null};}
  return {clubs,removed,unknownLabels:[...new Set(unknown.filter(Boolean))],kept:step.length};
}
const IMP_ORDER=["Dr","2W","3W","4W","5W","7W","9W","1H","2H","3H","4H","5H","6H",
  "2i","3i","4i","5i","6i","7i","8i","9i","PW","SW","LW"];
function impToProfile(clubs){
  const carries={}; for(const k of IMP_ORDER){if(clubs[k])carries[k]=clubs[k].carry;}
  const w52fs=clubs["52m"]?[clubs["52m"].lowN,clubs["52m"].hiN]:null;
  return {carries,w52fs};
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

const S = {
  card:{background:"white",borderRadius:16,padding:14,marginBottom:10,boxShadow:"0 1px 4px rgba(0,0,0,0.07)",boxSizing:"border-box",width:"100%"},
  h:{fontSize:10,letterSpacing:1.4,fontWeight:700,color:"#8a8a8e",textTransform:"uppercase",marginBottom:6},
  big:{fontSize:24,fontWeight:800,color:"#111",letterSpacing:-0.4,lineHeight:1.15},
  sub:{fontSize:13,color:"#3a3a3c",lineHeight:1.45},
  btn:{border:"none",borderRadius:12,padding:"13px 14px",fontSize:15,fontWeight:700,cursor:"pointer"},
  inp:{padding:"11px 12px",fontSize:16,fontWeight:700,border:"2px solid #d1d1d6",borderRadius:12,boxSizing:"border-box",background:"white",minWidth:0},
  pill:(bg,fg)=>({display:"inline-block",background:bg,color:fg,borderRadius:20,padding:"3px 10px",fontSize:11,fontWeight:800}),
};

// The Whisper aesthetic: a caddie's leather yardage book meets a meditation app.
const PINE="#122b21", PAPER="#faf8f4", GOLD="#c8a24a", INK="#233b30", MUTE="#6b7d72";
const SERIF="Georgia,'Iowan Old Style','Palatino Linotype',serif";
const arrive={animation:"whisperIn .22s ease both"};
const WSTYLE=`@keyframes whisperIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}`;
const buzz=()=>{try{navigator.vibrate&&navigator.vibrate(12);}catch(e){}};

export default function CaddieOS(){
  const [tab,setTab]=useState("caddie");
  const [asked,setAsked]=useState(false);        // whisper flow: has the player asked this shot?
  const [awaitResult,setAwaitResult]=useState(false); // waiting for the six-zone result tap
  const [qYards,setQYards]=useState("");          // question-screen yardage entry
  const [lieLabel,setLieLabel]=useState("Fairway"); // which lie chip is lit (Tee vs Fairway both map to FW)
  const [showAlt,setShowAlt]=useState(false);     // "something else?" expander
  const [prepOpen,setPrepOpen]=useState(false);   // pre-round PREP card
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
  const [courseSel,setCourseSel]=useState("bp");
  const [viewHole,setViewHole]=useState(null);
  const [teeIn,setTeeIn]=useState("");
  const [tourn,setTourn]=useState(false);
  const [lie,setLie]=useState("FW");
  const [wind,setWind]=useState("NONE");
  const [dir,setDir]=useState(null);
  const [showRep,setShowRep]=useState(false);
  const [imp,setImp]=useState(null);        // staged import awaiting confirmation
  const [impErr,setImpErr]=useState("");
  const [dragOver,setDragOver]=useState(false);
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
  const playHoleNow=i=>{saveLive({...live,hole:i,strokes:0,rem:(live.teeAdj&&live.teeAdj[i])||CH[i].y,onGreen:false,putts:0,pen:0,i35At:null,teeAck:false});setViewHole(null);};
  const endSave=()=>{const idx=live.scores.map((sc,i)=>sc!==null?i:-1).filter(i=>i>=0);
    if(idx.length){const rd={date:new Date().toLocaleDateString(),course:COURSES[live.course]?COURSES[live.course].name:"",holes:idx.length,total:idx.reduce((a,i)=>a+live.scores[i],0),plan:idx.reduce((a,i)=>a+CH[i].tgt,0),scores:live.scores.map(sc=>sc===null?0:sc),putts:live.puttsArr.reduce((a,b)=>a+(b||0),0),convMade:live.convs.filter(c=>c===true).length,convTried:live.convs.filter(c=>c!==null).length,benched:live.bench||[],shots:live.shots||[]};saveRounds([...rounds,rd]);}
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
    setLoaded(true);})();},[]);
  const saveLive=l=>{setLive(l);store.set("caddie:live",l);};

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
    const w52=imp.patch.w52fs?{...P.w52,fs:imp.patch.w52fs}:P.w52;
    const clubStats={...(P.clubStats||{}),...imp.clubs};
    const p={...P,carries,w52,clubStats,updated:new Date().toISOString()};
    setP(p); store.set("caddie:profile",p);
    const n=Object.keys(imp.patch.carries).length+(imp.patch.w52fs?1:0);
    setMeMsg(`Imported ${imp.raw} shots — ${n} clubs learned. Your caddie now runs on your real numbers.`);
    setImp(null); setImpErr("");
  };

  const CH=(live&&COURSES[live.course]?COURSES[live.course]:COURSES[courseSel]).holes;
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
  // Lateral aim-off from measured side bias: aim half the bias the opposite way.
  const aimOff=fm=>{const c=cstat(fm);if(!c||!c.side||c.side.med==null||Math.abs(c.side.med)<2)return null;
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
  const H=live?CH[live.hole]:null;
  // Live distances to key marks (carry hazard / dogleg corner) from the ball's spot.
  const holeMarks=(()=>{if(!H||!live)return [];const covered=H.y-live.rem;const m=[];
    if(H.carry&&H.carry-covered>0)m.push(`${H.carry-covered} yds to clear ${H.carryLabel||"the hazard"}`);
    if(H.corner&&H.corner-covered>0)m.push(`${H.corner-covered} yds to the ${H.cornerLabel||"corner"}`);
    return m;})();
  const getPlan=h=>h.plan||genPlan(h,P,(live&&live.bench)||[]);
  const GP=live?getPlan(H):[];
  const effRem=live?(wind==="INTO"?Math.round(live.rem*1.08):wind==="DOWN"?Math.round(live.rem*0.94):live.rem):0;
  const R=live&&!live.onGreen?E.rec(effRem):null;
  const L=live&&!live.onGreen&&(!R||R.zone==="adv")?E.layup(live.rem).filter(o=>o.r.zone!=="adv"):null;

  useEffect(()=>{ setAsked(false);setAwaitResult(false);setShowAlt(false);setQYards("");
    if(!live||live.onGreen){setSel(null);return;}
    const hp=getPlan(CH[live.hole]);
    const bk=(!learned&&live.strokes<hp.length)?bookChipOf(hp[live.strokes].c,P):null;
    const bkOk=bk&&!(live.bench||[]).includes(famOf(bk));
    setSel(bkOk?bk:(R?R.chip:(L&&L[0]?L[0].k:Object.keys(P.carries)[0])));setTeeIn("");setLie("FW");setObIn("");setDir(null);setWind("NONE");
  },[live?live.hole:-1,live?live.strokes:-1,live?live.onGreen:false,live&&live.bench?live.bench.join(","):""]);

  const startRound=()=>saveLive({course:courseSel,hole:0,strokes:0,rem:CH[0].y,onGreen:false,putts:0,pen:0,i35At:null,teeAck:false,bench:[],shots:[],scores:Array(18).fill(null),puttsArr:Array(18).fill(null),convs:Array(18).fill(null)});
  const addPenalty=()=>saveLive({...live,pen:(live.pen||0)+1,shots:[...(live.shots||[]),{pen:1,from:live.rem,c:"Penalty",h:live.hole+1}]});
  const logShot=(gain,g,syn,dirOv)=>{
    const shot={c:sel||"?",from:live.rem,gain,exp:E.chipCarry(sel||"CHIP"),g:g?1:0,p:syn?1:0,h:live.hole+1,lie,dir:dirOv!==undefined?dirOv:dir};
    let l={...live,strokes:live.strokes+1,shots:[...(live.shots||[]),shot]};
    const nr=live.rem-gain;
    if(g||nr<=0){l.onGreen=true;}
    else {l.rem=nr; if(nr<=35&&l.i35At===null)l.i35At=l.strokes;}
    saveLive(l);setAtInput("");
  };
  const holeOut=()=>{
    const pen=live.pen||0;
    const total=live.strokes+live.putts+pen+1,h=live.hole;
    const conv=live.i35At!==null?(total-live.i35At)<=3:null;
    const sc=[...live.scores];sc[h]=total;
    const pa=[...live.puttsArr];pa[h]=live.putts+1;
    const cv=[...live.convs];cv[h]=conv;
    if(sc.every(x=>x!==null)){
      const rd={date:new Date().toLocaleDateString(),course:COURSES[live.course]?COURSES[live.course].name:"",total:sc.reduce((a,b)=>a+b,0),plan:CH.reduce((a,x)=>a+x.tgt,0),scores:sc,putts:pa.reduce((a,b)=>a+(b||0),0),convMade:cv.filter(c=>c===true).length,convTried:cv.filter(c=>c!==null).length,benched:live.bench||[],shots:live.shots||[]};
      const nr=[...rounds,rd];setRounds(nr);store.set("caddie:rounds",nr);
      saveLive(null);store.set("caddie:live",null);setTab("trends");
    } else {const nxt=(()=>{let n=(h+1)%18;while(sc[n]!==null&&n!==h)n=(n+1)%18;return n;})();
      saveLive({...live,hole:nxt,strokes:0,rem:(live.teeAdj&&live.teeAdj[nxt])||CH[nxt].y,onGreen:false,putts:0,pen:0,i35At:null,teeAck:false,scores:sc,puttsArr:pa,convs:cv});}
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
  const coldAlert=live?flags.cold.filter(f=>!live.bench.includes(f)&&!((live.dismiss||[]).includes(f))):[];
  const inspecting=live&&viewHole!==null&&viewHole!==live.hole;

  return (
    <div style={{background:PAPER,minHeight:"100vh",width:"100%",maxWidth:430,margin:"0 auto",overflowX:"hidden",fontFamily:"-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif",paddingBottom:76,boxSizing:"border-box"}}>
      <div style={{background:"#1a3a2e",padding:"12px 14px 9px",position:"sticky",top:0,zIndex:50}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <div>
            <div style={{color:"#86efac",fontSize:9,letterSpacing:3,fontWeight:800}}>CADDIE OS</div>
            <div style={{color:"white",fontSize:14,fontWeight:800}}>{P.name} · {(live&&COURSES[live.course]?COURSES[live.course]:COURSES[courseSel]).name} <button onClick={()=>setTourn(!tourn)} style={{marginLeft:6,border:"none",borderRadius:6,padding:"2px 8px",fontSize:9,fontWeight:800,cursor:"pointer",verticalAlign:"middle",background:tourn?"#fcd34d":"rgba(255,255,255,0.14)",color:tourn?"#1a3a2e":"#86efac"}}>{tourn?"TOURN ON":"TOURN"}</button></div>
          </div>
          {live&&<div style={{textAlign:"right"}}>
            <div style={{color:"white",fontSize:17,fontWeight:900}}>{runTot}<span style={{fontSize:11,fontWeight:700,color:dv>0?"#ffb3ad":dv<0?"#86efac":"#fcd34d"}}> {done>0?(dv>0?"+"+dv:dv)+" vs plan":""}</span></div>
            <div style={{color:"#6b9e7a",fontSize:9,fontWeight:700}}>H{live.hole+1} · {done}/18 holed</div>
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

        {!live&&<div style={{padding:"22px 18px"}}>
          <div style={{fontFamily:SERIF,fontSize:30,color:INK,lineHeight:1.2,marginBottom:6}}>Ready when you are.</div>
          <div style={{color:MUTE,fontSize:15,marginBottom:20,fontFamily:SERIF}}>Tell me the number and your lie. I'll take care of the rest.</div>
          <div style={{display:"flex",gap:10,marginBottom:12}}>
            {Object.entries(COURSES).map(([k,c])=>(
              <button key={k} onClick={()=>setCourseSel(k)} style={{flex:1,border:"none",borderRadius:16,padding:"14px 10px",fontSize:14,fontWeight:700,cursor:"pointer",background:courseSel===k?PINE:"#fff",color:courseSel===k?PAPER:INK,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>{c.name}</button>))}
          </div>
          <button onClick={()=>{buzz();startRound();}} style={{width:"100%",border:"none",borderRadius:18,padding:"18px",fontSize:18,fontWeight:700,cursor:"pointer",background:PINE,color:PAPER,letterSpacing:.4}}>Start the round</button>
          {!P.clubStats&&<button onClick={()=>setTab("me")} style={{width:"100%",marginTop:10,border:"none",background:"transparent",color:INK,fontSize:13,textDecoration:"underline",cursor:"pointer"}}>First time? Upload your launch-monitor data →</button>}
          <div style={{marginTop:18,background:"#fff",borderRadius:16,padding:16,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
            <button onClick={()=>setPrepOpen(!prepOpen)} style={{width:"100%",display:"flex",justifyContent:"space-between",alignItems:"center",background:"none",border:"none",cursor:"pointer",padding:0}}>
              <span style={{fontFamily:SERIF,fontSize:17,color:INK}}>Warm up first</span>
              <span style={{color:MUTE,fontSize:20}}>{prepOpen?"–":"+"}</span>
            </button>
            {prepOpen&&<div style={{marginTop:10,color:INK,fontSize:14,lineHeight:1.7}}>
              <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:4}}>Body · 8 min</div>
              Glute bridges, world's-greatest stretch, torso rotations, then ten swings building to your smooth tempo.
              <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",margin:"12px 0 4px"}}>Range · fresh first</div>
              Check alignment, then your wedge windows before anything else. Five smooth 9-irons, five 7s at tempo. Finish on the greens: pace ladder 10/20/30, then five chips — walk to the first tee on a make.
              <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",margin:"12px 0 4px"}}>Fuel</div>
              Eat 2–3 hours out, top up every six holes, sip water every hole. Dehydration shows up as a chunked iron before it feels like thirst.
            </div>}
          </div>
        </div>}

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
          const phase=live.onGreen?"putt":awaitResult?"result":asked?"whisper":"question";
          const y=parseInt(qYards)||live.rem;
          return <div style={{padding:"16px 16px 28px"}}>

            {phase==="question"&&<div style={arrive}>
              {(()=>{const c=flags.cold.find(f=>!live.bench.includes(f)&&!((live.dismiss||[]).includes(f)));if(!c)return null;
                return <div style={{background:"#fff",borderRadius:16,padding:14,marginBottom:16,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
                  <div style={{fontFamily:SERIF,fontSize:16,color:INK,marginBottom:10}}>{benchWhisper(c)}</div>
                  <div style={{display:"flex",gap:10}}>
                    <button onClick={()=>saveLive({...live,bench:[...live.bench,c]})} style={{flex:1,border:"none",borderRadius:12,padding:"12px",background:PINE,color:PAPER,fontWeight:700,cursor:"pointer"}}>Yes, route around it</button>
                    <button onClick={()=>saveLive({...live,dismiss:[...(live.dismiss||[]),c]})} style={{flex:1,border:"none",borderRadius:12,padding:"12px",background:"#f1efe9",color:INK,fontWeight:700,cursor:"pointer"}}>No, it's fine</button>
                  </div>
                </div>;})()}
              {live.strokes===0&&<div style={{fontFamily:SERIF,fontSize:16,color:MUTE,lineHeight:1.5,marginBottom:18}}>{teeWhisper(H,H.y)}</div>}
              <div style={{textAlign:"center",marginBottom:6,color:MUTE,fontSize:12,letterSpacing:2,textTransform:"uppercase"}}>How far?</div>
              <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:14,marginBottom:18}}>
                <button onClick={()=>setQYards(String(Math.max(1,y-1)))} style={{border:"none",background:"#fff",width:52,height:52,borderRadius:26,fontSize:24,color:INK,cursor:"pointer",boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>–</button>
                <input inputMode="numeric" value={qYards!==""?qYards:String(live.rem)} onChange={e=>setQYards(e.target.value.replace(/[^0-9]/g,""))} style={{width:150,textAlign:"center",fontSize:74,fontWeight:800,color:INK,border:"none",background:"transparent",fontVariantNumeric:"tabular-nums",outline:"none"}}/>
                <button onClick={()=>setQYards(String(y+1))} style={{border:"none",background:"#fff",width:52,height:52,borderRadius:26,fontSize:24,color:INK,cursor:"pointer",boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>+</button>
              </div>
              <div style={{textAlign:"center",color:MUTE,fontSize:12,marginBottom:16}}>yards to the middle</div>
              <div style={{display:"flex",gap:7,justifyContent:"center",flexWrap:"wrap",marginBottom:16}}>
                {[["Tee","FW"],["Fairway","FW"],["Rough","ROUGH"],["Sand","SAND"],["Trees","TREES"]].map(([lab,v])=>{const on=lieLabel===lab;
                  return <button key={lab} onClick={()=>{setLie(v);setLieLabel(lab);}} style={{border:"none",borderRadius:20,padding:"10px 16px",fontSize:14,fontWeight:600,cursor:"pointer",background:on?PINE:"#fff",color:on?PAPER:INK,boxShadow:on?"none":"0 1px 3px rgba(0,0,0,.06)"}}>{lab}</button>;})}
              </div>
              <div style={{display:"flex",gap:6,justifyContent:"center",marginBottom:22}}>
                {[["NONE","calm"],["INTO","into"],["DOWN","down"],["CROSS","cross"]].map(([k,l])=>(
                  <button key={k} onClick={()=>setWind(k)} style={{border:"none",borderRadius:14,padding:"6px 12px",fontSize:12,fontWeight:600,cursor:"pointer",background:wind===k?INK:"transparent",color:wind===k?PAPER:MUTE}}>{l}</button>))}
              </div>
              <button onClick={()=>{buzz();const v=parseInt(qYards)||live.rem;const ev=wind==="INTO"?Math.round(v*1.08):wind==="DOWN"?Math.round(v*0.94):v;const pk=E.pick(ev);saveLive({...live,rem:v});setSel(pk.chip);setAsked(true);setShowAlt(false);}} style={{width:"100%",border:"none",borderRadius:18,padding:"18px",fontSize:17,fontWeight:700,cursor:"pointer",background:PINE,color:PAPER,letterSpacing:.4}}>Read it</button>
            </div>}

            {phase==="whisper"&&(()=>{
              const fam=famOf(sel||"7i");
              const sideC=(()=>{const c=cstat(fam);if(c&&c.side)return{dir:c.side.dir,pct:c.side.pct};const b=dirBias(fam);if(b)return{dir:b[0],pct:parseInt(b.slice(1))};return null;})();
              const carrySel=E.chipCarry(sel||"CHIP");
              const reach=carrySel>=effRem-6;              // wind-aware: can this club get home?
              const leaves=Math.max(0,live.rem-carrySel);  // yards left uses the real distance
              const W=whisper({fam,chip:sel,eff:E.eff(fam),stat:disp(fam),conf:conf(fam),hot:flags.hot.includes(fam),cold:flags.cold.includes(fam),adj:flags.adj[fam]||null,side:sideC,feel:(P.feels&&P.feels[fam])||null,hole:{dzL:H.dzL,dzR:H.dzR},i35:live.rem<=34,reach,leaves,wind});
              return <div style={arrive}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:18}}>
                  <div style={{color:MUTE,fontSize:14}}>{live.rem} yards · {lieLabel.toLowerCase()}{wind!=="NONE"?" · "+wind.toLowerCase()+" wind":""}</div>
                  <button onClick={()=>{setAsked(false);setShowAlt(false);}} style={{border:"none",background:"transparent",color:MUTE,fontSize:13,cursor:"pointer"}}>↩ back</button>
                </div>
                <div style={{background:PINE,borderRadius:28,padding:"30px 24px",boxShadow:"0 10px 30px rgba(18,43,33,.18)"}}>
                  <div style={{fontFamily:SERIF,fontSize:44,color:GOLD,letterSpacing:.3,marginBottom:16,textWrap:"balance"}}>{W.club}</div>
                  {W.lines.map((l,i)=>(<div key={i} style={{fontFamily:SERIF,fontSize:20,color:PAPER,lineHeight:1.5,marginBottom:10,opacity:.96}}>{l}</div>))}
                </div>
                <button onClick={()=>{buzz();setAwaitResult(true);}} style={{width:"100%",border:"none",borderRadius:18,padding:"20px",fontSize:19,fontWeight:800,cursor:"pointer",background:GOLD,color:PINE,letterSpacing:1,marginTop:18}}>HIT IT</button>
                <button onClick={()=>setShowAlt(!showAlt)} style={{width:"100%",border:"none",background:"transparent",color:MUTE,fontSize:14,cursor:"pointer",marginTop:12,fontFamily:SERIF,fontStyle:"italic"}}>{showAlt?"never mind":"something else?"}</button>
                {showAlt&&<div style={{marginTop:12,background:"#fff",borderRadius:16,padding:14,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>
                  <div style={{color:MUTE,fontSize:11,letterSpacing:1.4,textTransform:"uppercase",marginBottom:8}}>Pick a different club</div>
                  <div style={{display:"flex",gap:6,overflowX:"auto",paddingBottom:6,marginBottom:8}}>
                    {chips.map(c=>{const on=sel===c;return <button key={c} onClick={()=>setSel(c)} style={{flexShrink:0,border:"none",borderRadius:12,padding:"9px 12px",fontSize:14,fontWeight:700,cursor:"pointer",background:on?PINE:"#f1efe9",color:on?PAPER:INK}}>{c}<span style={{opacity:.6,fontSize:10}}> {E.chipCarry(c)}</span></button>;})}
                  </div>
                  {(()=>{const d=disp(fam),gp=greenProb(fam),cf=conf(fam);const bits=[];
                    if(d)bits.push(`${d.n} tracked · ${d.avg>=0?"+":""}${d.avg}y avg · ±${d.sd}y`);
                    if(gp!=null)bits.push(`on-target ~${gp}%`);
                    if(cf!=null)bits.push(`confidence ${cf}/100`);
                    if(sideC&&sideC.pct>=58)bits.push(`miss ${sideC.dir} ${sideC.pct}%`);
                    return bits.length?<div style={{color:MUTE,fontSize:12,lineHeight:1.6}}>{bits.join(" · ")}</div>:<div style={{color:MUTE,fontSize:12}}>No tracked data yet for this club — the number's your best guide.</div>;})()}
                  <button onClick={()=>{buzz();addPenalty();}} style={{marginTop:10,border:"none",borderRadius:10,padding:"8px 12px",background:"#f6efe6",color:"#8a6d2f",fontSize:12,fontWeight:700,cursor:"pointer"}}>Add a penalty (stroke & distance)</button>
                </div>}
              </div>;})()}

            {phase==="result"&&(()=>{const exp=E.chipCarry(sel||"CHIP");
              const Z=(lab,fn)=>(<button onClick={()=>{buzz();fn();}} style={{border:"none",borderRadius:16,padding:"24px 10px",fontSize:16,fontWeight:700,cursor:"pointer",background:"#fff",color:INK,boxShadow:"0 1px 4px rgba(0,0,0,.06)"}}>{lab}</button>);
              return <div style={arrive}>
                <div style={{fontFamily:SERIF,fontSize:22,color:INK,textAlign:"center",marginBottom:20}}>Where'd it finish?</div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
                  {Z("Short",()=>logShot(Math.max(1,exp-10),false,false,null))}
                  {Z("Long",()=>logShot(exp+10,false,false,null))}
                  {Z("Left",()=>logShot(exp,false,false,"L"))}
                  {Z("Right",()=>logShot(exp,false,false,"R"))}
                  {Z("On line",()=>logShot(exp,false,false,null))}
                  <button onClick={()=>{buzz();logShot(live.rem,true,false,null);}} style={{border:"none",borderRadius:16,padding:"24px 10px",fontSize:16,fontWeight:800,cursor:"pointer",background:PINE,color:PAPER}}>On the green</button>
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

            {!tourn&&<div style={{display:"flex",justifyContent:"center",gap:20,marginTop:28}}>
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
          {Object.entries(COURSES).map(([k,c])=>(
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
          const allE=rounds.flatMap(r=>(r.shots||[]).filter(x=>!x.g).map(x=>Math.abs(x.gain-x.exp)));
          const mae=allE.length?allE.reduce((a,b)=>a+b,0)/allE.length:null;
          const rows=[["Scoring",Math.max(0,Math.min(100,Math.round(100-avgVs*6))),`${avgVs>=0?"+":""}${avgVs.toFixed(1)} vs plan`],
            ["Short game",Math.max(0,Math.min(100,Math.round(conv*100))),`${Math.round(conv*100)}% inside-35`],
            ["Putting",Math.max(0,Math.min(100,Math.round(100-(ppr-30)*5))),`${ppr.toFixed(1)} putts/round`],
            mae!==null?["Ball-striking",Math.max(0,Math.min(100,Math.round(100-mae*4))),`±${Math.round(mae)}y vs number`]:null,
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
          const rows=fams.map(f=>{const mine=all.filter(x=>famOf(x.c)===f&&!x.p);if(!mine.length)return null;const errs=mine.filter(x=>!x.g&&(!x.lie||x.lie==="FW")&&x.from>x.exp+8).map(x=>x.gain-x.exp);const m=errs.length?Math.round(errs.reduce((a,b)=>a+b,0)/errs.length):0;const sd=errs.length>1?Math.round(Math.sqrt(errs.reduce((a,b)=>a+(b-m)*(b-m),0)/errs.length)):0;const gpct=Math.round(mine.filter(x=>x.g||Math.abs(x.gain-x.exp)<=8).length/mine.length*100);return {f,n:mine.length,m,sd,gpct};}).filter(Boolean);
          return rows.map((r,i)=>(<div key={i} style={{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid #f2f2f7"}}>
            <span style={{fontSize:14,fontWeight:800}}>{r.f}</span>
            <span style={{fontSize:12,color:"#3a3a3c"}}>{r.n} shots · {r.m>=0?"+":""}{r.m}y · ±{r.sd}y{(()=>{const b=dirBias(r.f);return b?" · miss "+b:"";})()} · {r.gpct}% on <span style={{fontWeight:800,color:r.gpct>=60?"#1a7f37":r.gpct>=40?"#ff9f0a":"#ff453a"}}>{r.gpct>=60?"HOT":r.gpct>=40?"OK":"COLD"}</span></span>
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
          const sideMiss=keys.filter(k=>cs[k].side&&cs[k].side.pct>=60).sort((a,b)=>cs[b].side.pct-cs[a].side.pct)[0];
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
            {sideMiss&&<div style={{color:"#fcd34d",fontSize:12,fontWeight:700,marginBottom:8}}>⟵⟶ {lbl(sideMiss)} misses {cs[sideMiss].side.dir==="R"?"right":"left"} {cs[sideMiss].side.pct}% of the time — aim the fat side.</div>}
            <div style={{borderTop:"1px solid rgba(255,255,255,0.12)",paddingTop:6}}>
              {keys.map(k=>{const c=cs[k],[word,col]=rel(c.sd);
                return <div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"4px 0"}}>
                  <span style={{color:"white",fontSize:13,fontWeight:800,minWidth:74}}>{lbl(k)}</span>
                  <span style={{color:"#9fd6b4",fontSize:12,flex:1,textAlign:"right"}}>{c.carry}y · plays {c.lowN}–{c.hiN}{c.side&&c.side.pct>=58?" · "+c.side.dir+" "+c.side.pct+"%":""} · {c.n} shots</span>
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
              {imp.patch.w52fs&&<div style={{fontSize:11,color:"#1a7f37",marginBottom:8}}>Your 52° full-smooth window set to {imp.patch.w52fs[0]}–{imp.patch.w52fs[1]}y.</div>}
              <div style={{display:"flex",gap:8}}>
                <button onClick={applyImport} style={{...S.btn,flex:1,background:"#1a3a2e",color:"#86efac"}}>IMPORT — LEARN MY GAME</button>
                <button onClick={()=>{setImp(null);setImpErr("");}} style={{...S.btn,background:"#f2f2f7",color:"#111"}}>Cancel</button>
              </div>
            </>);})()}
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
        <button onClick={()=>{const p={...P,updated:new Date().toISOString()};setP(p);store.set("caddie:profile",p);setMeMsg("Saved — the engine now runs on your numbers.");}} style={{...S.btn,width:"100%",background:"#1a3a2e",color:"#86efac",marginBottom:8}}>SAVE PROFILE</button>
        {meMsg&&<div style={{textAlign:"center",fontSize:12,fontWeight:700,color:"#1a7f37",marginBottom:8}}>{meMsg}</div>}
        <div style={S.card}>
          <div style={S.h}>Feels — your best cues, in your words</div>
          <div style={{...S.sub,fontSize:12,marginBottom:8}}>These show on every suggested shot. Write the cue that actually works for you.</div>
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
      </div>}

      {!tourn&&<div style={{position:"fixed",bottom:0,left:0,right:0,maxWidth:430,margin:"0 auto",background:"rgba(250,248,244,0.97)",backdropFilter:"blur(12px)",borderTop:"1px solid #e7e2d8",display:"flex",paddingBottom:8,zIndex:60,boxSizing:"border-box"}}>
        <TabBtn id="caddie" label="CADDIE"/>
        <TabBtn id="rounds" label="ROUNDS"/>
        <TabBtn id="me" label="ME"/>
      </div>}
    </div>
  );
}
