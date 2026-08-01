/*
 * decision.js — the play-first decision engine.
 *
 * THE PRINCIPLE (settled): the caddie does not start by asking "what club reaches
 * this number?" It reasons in COMPLETE PLAYS — a destination, the route to it, the
 * ball flight it needs, the club that executes it, the misses it risks, and the
 * scoring consequence — then chooses the play that yields the LOWEST EXPECTED SCORE
 * for THIS golfer TODAY, and only then confirms a reliable club-and-flight to hit it.
 *
 * The play↔execution feedback loop is the heart of it: we never fall in love with an
 * ideal destination and then hand the golfer a club they can't trust. If the best
 * play has no reliable execution, it is eliminated (on the record) and the next
 * lowest-EV *executable* play is chosen automatically.
 *
 * Recovery is NOT a separate mode bolted on the side — a bad lie simply changes which
 * plays are on the table (get-back-in-position, escape, hero) and they compete on the
 * same expected-value scale through the same entry point, reading the same Player Model.
 *
 * Pure and unit-tested: no React, no storage, no DOM. The UI hands in the situation
 * and the Player Model; this returns one complete recommendation + a decision record.
 */
import { expectedStrokes, recoveryPlan, isRecoveryLie } from "./recovery.js";
import { exposure, remainingYards, dAfterCarry, centerX, holeContext } from "./geometry.js";

const clamp = (lo, hi, v) => Math.max(lo, Math.min(hi, v));
const round = Math.round;

// A club is "reliable enough to execute the ideal play" at/above this. Below it, the
// club is still playable — but only as a fallback when nothing better can execute.
const RELIABLE = 55;

// club family key (local + tiny so this file stays pure).
const famOf = c => {
  c = String(c || "");
  if (c.includes("52") || c.includes("½") || c.includes("¾")) return "52";
  if (c.includes("chip") || c.includes("bump")) return "chip";
  return c.split(" ")[0];
};

// ---- turning a club's yardage dispersion into normalized map scatter --------
// Honest approximation: the hole's x-axis (0..1) spans roughly a 60-yd-wide corridor,
// and a shakier club scatters wider than its raw ±sd. Calibrated, not measured — the
// SHAPE (tighter club = less hazard exposure) is what drives the decision.
function scatter(hole, sd, rel) {
  const s = Math.max(sd || 10, 6);
  const wobble = rel != null && rel < 70 ? 1 + (70 - rel) / 110 : 1;   // low trust → wider
  const sdD = clamp(0.03, 0.16, (s * wobble) / ((hole && hole.y) || 400));
  const sdX = clamp(0.04, 0.20, (s * wobble) / 55);
  return { sdD, sdX };
}

// Expected strokes-to-hole AFTER a ball comes to rest at a landing, given the odds it
// finds each ground type (from the dispersion-vs-hazard sample). Water = penalty.
function restES(remAfter, exp) {
  const es = lie => expectedStrokes(Math.max(0, remAfter), lie);
  const waterES = expectedStrokes(Math.max(remAfter, 30), "ROUGH") + 1.1;   // stroke + still out there
  const treesES = expectedStrokes(Math.max(remAfter, 40), "TREES");
  return (
    exp.fairway * es("FW") +
    exp.rough * es("ROUGH") +
    exp.sand * es("SAND") +
    exp.trees * treesES +
    exp.water * waterES
  );
}

// Is there an obstruction ON the forward line between the ball and a target d? Trees
// that merely LINE the fairway are scenery — they only block when (a) the ball is
// actually off the short grass among them on that side, or (b) a tree stand (pool)
// straddles the centerline the shot must travel. Anything looser over-asks the golfer.
function forwardObstruction(hole, dNow, xNow, dDest) {
  const haz = Array.isArray(hole && hole.hazards) ? hole.hazards : [];
  const cxNow = centerX(hole && hole.path, dNow);
  const off = Math.abs(xNow - cxNow) > 0.14;
  const side = xNow < cxNow - 0.09 ? "L" : xNow > cxNow + 0.09 ? "R" : null;
  return haz.some(z => {
    if (z.type !== "trees") return false;
    if (Array.isArray(z.pool)) {
      const [d0, d1, x0, x1] = z.pool;
      const lo = Math.min(d0, d1), hi = Math.max(d0, d1);
      if (hi < dNow || lo > dDest) return false;
      // straddles the line only if the corridor centerline runs through the stand ahead
      for (let d = Math.max(lo, dNow); d <= Math.min(hi, dDest); d += 0.02) {
        const cx = centerX(hole && hole.path, d);
        if (cx >= Math.min(x0, x1) - 0.05 && cx <= Math.max(x0, x1) + 0.05) return true;
      }
      return false;
    }
    // a side band blocks only when the ball is off the fairway on that same side
    return off && z.side === side && (z.from ?? 0) <= dDest && (z.to ?? 1) >= dNow;
  });
}

// What ball flight a play needs, folded against what the golfer just told us.
// observation: "clear" | "high" | "low" | "curve" | "nowindow" | null
function flightFor(obstructed, observation) {
  if (observation === "nowindow") return { flight: "sideways", route: "out", forced: true };
  if (observation === "high") return { flight: "high", route: "over", forced: true };
  if (observation === "low") return { flight: "low", route: "under", forced: true };
  if (observation === "curve") return { flight: "shaped", route: "around", forced: true };
  if (obstructed && observation !== "clear") return { flight: "high", route: "over", forced: false };
  return { flight: "normal", route: "direct", forced: false };
}

// Build one complete play object (destination, route, flight, execution, EV).
function buildPlay(ctx, o) {
  const { hole, from } = ctx;
  const dNow = from ? from.d : 0, xNow = from ? from.x : centerX(hole && hole.path, 0);
  const obstructed = forwardObstruction(hole, dNow, xNow, o.destD);
  const f = flightFor(obstructed, ctx.observation);
  const sc = scatter(hole, o.sd, o.rel);
  const exp = exposure(hole, o.destD, o.destX, sc.sdD, sc.sdX);
  const remAfter = o.leaves != null ? o.leaves : remainingYards(hole, o.destD);
  const ev = +(1 + restES(remAfter, exp)).toFixed(2);
  return {
    kind: o.kind,
    club: o.club,
    destination: { d: o.destD, x: o.destX, label: o.destLabel },
    distance: o.distance,
    leaves: remAfter,
    route: o.route || f.route,
    flight: o.flight || f.flight,
    flightForced: f.forced,
    obstructed,
    intent: o.intent,
    exposure: exp,
    scatter: sc,
    reach: !!o.reach,
    rel: o.rel,
    ev,
  };
}

// ---------------------- explicit shot-context classification -----------------
// ONE classifier, consumed by both candidate generation AND communication so the two
// never disagree. A tee shot is NOT automatically a fairway-position play: a par-3 tee
// is a green-targeting approach; only a par-4/5 tee is a positioning shot.
//   par3_tee | tee_position | approach | scoring | recovery
// (The chosen play's KIND — attack / layup / position / punch / hero / scoring — carries
//  the rest; a lay-up is an outcome of green-targeting, not a separate input context.)
export function shotContextOf(ctx) {
  const lie = ctx.lie, strokes = ctx.strokes, rem = ctx.rem, hole = ctx.hole;
  const scoreCeiling = ctx.scoreCeiling != null ? ctx.scoreCeiling : 34;
  if (isRecoveryLie(lie) || ctx.observation === "nowindow") return "recovery";
  if (rem <= scoreCeiling) return "scoring";
  const par = hole && hole.par;
  if (strokes === 0) return par === 3 ? "par3_tee" : "tee_position";
  return "approach";
}

// ------------------------- candidate generation ------------------------------
function standardCandidates(ctx) {
  const { hole, from, rem, effRem, bag, wedgeDist } = ctx;
  const dNow = from ? from.d : 0;
  const playFactor = rem > 0 ? effRem / rem : 1;      // plays-like inflation (wind + lie)
  const cx = centerX(hole && hole.path, 1);
  const usable = bag.filter(c => c.carry > 0 && !c.benched);
  const cands = [];
  // Strategic type decides which plays exist — never strokes===0 alone.
  const kindOf = ctx.context || shotContextOf(ctx);
  const par3Tee = kindOf === "par3_tee";
  const teePosition = kindOf === "tee_position";
  const greenTargeting = kindOf === "approach" || par3Tee;   // destination IS the green

  const reachers = usable.filter(c => c.carry >= effRem - 6);
  // ── ATTACK THE GREEN — for every green-targeting shot (approach OR par-3 tee) that
  //    can honestly get home. Generate a play for each club whose carry FITS the green
  //    window; clubs that materially fly past are not offered (a 190y 3W is not an
  //    attack for a 118y par 3). If nothing fits, the least-overshoot club stands in. ──
  if (reachers.length && greenTargeting) {
    const window = reachers.filter(c => c.carry <= effRem + 18);
    const pool = window.length ? window : [reachers.slice().sort((a, b) => a.carry - b.carry)[0]];
    pool.forEach(pick => cands.push(buildPlay(ctx, {
      kind: "attack", club: pick.k, sd: pick.sd, rel: pick.rel,
      destD: 0.985, destX: cx, destLabel: "the green",
      distance: rem, leaves: 0, reach: true,
      intent: "at the flag — center of the green is the miss",
    })));
  }

  // ── LAY UP TO YOUR NUMBER — a green-targeting shot that chooses to stop short at a
  //    number you score from (real on a long par-3 you can't/shouldn't reach). ──
  if (greenTargeting) {
    const needed = rem - wedgeDist;
    if (needed >= 30) {
      const layClub = usable.filter(c => c.carry >= needed - 10 && c.carry <= needed + 20)
        .sort((a, b) => (b.rel - a.rel) || (a.carry - b.carry))[0]
        || usable.filter(c => c.carry <= needed).sort((a, b) => b.carry - a.carry)[0];
      if (layClub) {
        const trueCarry = layClub.carry / playFactor;
        const destD = dAfterCarry(hole, dNow, trueCarry);
        cands.push(buildPlay(ctx, {
          kind: "layup", club: layClub.k, sd: layClub.sd, rel: layClub.rel,
          destD, destX: centerX(hole && hole.path, destD), destLabel: `${wedgeDist} out`,
          distance: layClub.carry, leaves: Math.max(wedgeDist, rem - layClub.carry),
          intent: `advance to your money number — you score best from about ${wedgeDist}`,
        }));
      }
    }
  }

  // ── POSITION (par-4/5 tee) or SHORT (green-targeting that falls short). On a par-4/5
  //    tee every club is a position option; on a green-targeting shot a club that can't
  //    reach becomes a play-short lay-up — never a "fairway finder". ──
  usable.forEach(c => {
    if (greenTargeting && c.carry >= effRem - 6) return;   // reachers are ATTACKs above
    const trueCarry = c.carry / playFactor;
    const destD = dAfterCarry(hole, dNow, trueCarry);
    if (destD <= dNow + 0.01) return;                      // no forward progress
    const leaves = Math.max(0, rem - c.carry);
    cands.push(buildPlay(ctx, {
      kind: teePosition ? "position" : "layup", club: c.k, sd: c.sd, rel: c.rel,
      destD, destX: centerX(hole && hole.path, destD),
      destLabel: leaves > 0 ? `${leaves} out` : "pin-high",
      distance: c.carry, leaves, reach: leaves <= 6,
      intent: teePosition ? "find the fairway and set up the next one" : `play short to ${leaves} — a number you trust`,
    }));
  });

  return cands;
}

// Recovery plays: a bad lie changes WHICH plays exist. We reuse the proven expected-
// value recovery engine to enumerate escape / lay-up / hero, then present them as
// first-class candidates on the same EV scale and through the same record.
function recoveryCandidates(ctx) {
  const { hole, from, rem, lie, bag, wedgeDist } = ctx;
  const loc = from ? holeContext(hole, from.d, from.x) : {};
  const plan = recoveryPlan(rem, lie, {
    bag: bag.filter(c => !c.benched).map(c => ({ k: c.k, carry: c.carry, rel: c.rel })),
    wedgeDist, side: loc.side, blocked: loc.blocked,
  });
  const cands = plan.options.map(o => {
    const c = bag.find(b => b.k === o.club);
    return {
      kind: o.kind === "punch" ? "punch" : o.kind === "layup" ? "layup" : "hero",
      club: o.club, rel: c ? c.rel : 60, sd: c ? c.sd : 12,
      destination: { d: null, x: null, label: o.label },
      leaves: o.leaves, route: plan.blocked ? "out" : "direct",
      flight: o.kind === "hero" ? "committed" : "low", flightForced: false,
      obstructed: !!plan.blocked, intent: o.reason, reach: o.kind === "hero" && o.leaves === 0,
      ev: o.ev, label: o.label, prob: o.prob,
    };
  });
  return { cands, plan, loc };
}

// -------------------------- confidence components ----------------------------
// DISTINCT signals, never one overloaded number. Overall is a robust blend that
// leans on the components that could actually change the play (execution + play
// separation + today's form) and is capped by the club you'll physically hit — a
// single low-but-irrelevant component (e.g. an unmapped hole) can't collapse it,
// and we never claim more confidence than the execution can honestly carry.
function confidenceOf(ctx, sel, second) {
  const model = ctx.player || {};
  const m = model[famOf(sel.club)] || null;
  const player = m && m.longTerm && m.longTerm.n >= 4 && m.sd != null
    ? clamp(30, 96, round(96 - m.sd * 3)) : (m ? 55 : null);
  const form = m ? m.today.confidence : null;
  const course = Array.isArray(ctx.hole && ctx.hole.path)
    ? (Array.isArray(ctx.hole.hazards) && ctx.hole.hazards.length ? 88 : 72) : 45;
  const observation = ctx.askObservation && ctx.observation == null ? 45
    : ctx.observation ? 90 : 80;
  // play separation: how clearly the chosen play beats the next one (EV margin).
  const margin = second ? clamp(0, 1, (second.ev - sel.ev) / 0.6) : 0.6;
  const play = round(55 + margin * 40);
  const execution = m ? clamp(0, 100, round(m.reliability)) : 60;
  // Weighted blend, execution/play/form heaviest; light components can't tank it.
  const W = { player: 0.10, form: 0.18, course: 0.10, observation: 0.10, play: 0.22, execution: 0.30 };
  const comp = { player, form, course, observation, play, execution };
  let acc = 0, sw = 0;
  for (const k in W) if (comp[k] != null) { acc += W[k] * comp[k]; sw += W[k]; }
  let overall = sw ? round(acc / sw) : null;
  if (overall != null && execution != null) overall = Math.min(overall, execution + 12); // honesty cap
  const band = overall == null ? null : overall >= 72 ? "High" : overall >= 52 ? "Solid" : "Limited";
  return { player, form, course, observation, play, execution, overall, band };
}

/**
 * decideShot(ctx) -> one complete recommendation + decision record.
 *
 * ctx = {
 *   hole,                 // hole geometry (path, hazards, y, par, green, favor…)
 *   from: {d,x}|null,     // ball position (null → tee)
 *   rem,                  // true yards to the target
 *   effRem,               // plays-like yards (wind + lie); defaults to rem
 *   lie,                  // "FW"|"ROUGH"|"TREES"|…
 *   wind,                 // "NONE"|"INTO"|"DOWN"|"CROSS"
 *   strokes,              // shot index (0 = tee)
 *   player,               // dailyProfile() output
 *   bag: [{k,carry,rel,sd,benched,state}],   // effective carries + today's trust
 *   wedgeDist,            // money number
 *   observation,          // route flag: "clear"|"high"|"low"|"curve"|"nowindow"|null
 *   scoring,              // optional (rem) -> {chip,carry} for wedge-window scoring shots
 * }
 */
export function decideShot(ctx) {
  ctx = { effRem: ctx.rem, wind: "NONE", observation: null, bag: [], ...ctx };
  const { hole, from, rem, effRem, lie, bag, wedgeDist, strokes } = ctx;

  // Should we ask the golfer a route observation? Only when an obstruction on the line
  // could MATERIALLY change the play — never to offload the strategic decision.
  const dNow = from ? from.d : 0, xNow = from ? from.x : centerX(hole && hole.path, 0);
  const obstructed = forwardObstruction(hole, dNow, xNow, 0.985);
  ctx.askObservation = obstructed && ctx.observation == null;

  // Classify the shot ONCE — candidate generation and communication both read this.
  ctx.context = shotContextOf(ctx);

  // ── SCORING SHOT — inside the wedge/chip windows, the play is "get it close and
  //    take your two putts." Defer the exact wedge chip to the app's calibrated
  //    windows (single authority still decides it IS a scoring shot). ──
  if (ctx.context === "scoring" && ctx.scoring) {
    const s = ctx.scoring(rem);
    const sel = {
      kind: "scoring", club: s.chip, destination: { d: 0.985, x: centerX(hole && hole.path, 1), label: "the green" },
      leaves: 0, route: "direct", flight: "committed", reach: true, ev: +(1 + expectedStrokes(0, "FW")).toFixed(2),
      intent: "on the green first try — two putts is the miss", rel: 80,
    };
    const confidence = confidenceOf(ctx, sel, null);
    return finalize(ctx, "standard", sel, [sel], confidence, null, "One look, commit.");
  }

  // ── Assemble candidate plays — recovery lies change WHICH plays exist. ──
  const recovery = ctx.context === "recovery";
  let candidates, recoData = null;
  if (recovery) {
    const r = recoveryCandidates(ctx);
    candidates = r.cands; recoData = r;
  } else {
    candidates = standardCandidates(ctx);
  }
  if (!candidates.length) {
    // Never leave the golfer without a call — smooth the biggest trusted club and advance.
    const c = bag.filter(b => !b.benched).sort((a, b) => b.carry - a.carry)[0] || bag[0];
    const sel = { kind: "advance", club: c ? c.k : "7i", destination: { label: "advance" }, leaves: Math.max(0, rem - (c ? c.carry : 0)), route: "direct", flight: "normal", reach: false, ev: 5, intent: "advance it and re-plan", rel: c ? c.rel : 60 };
    return finalize(ctx, recovery ? "recovery" : "standard", sel, [sel], confidenceOf(ctx, sel, null), recoData, "Smooth and advance.");
  }

  // ── Rank by expected score (lowest EV first). ──
  candidates.sort((a, b) => a.ev - b.ev);

  // ── The play↔execution feedback loop. Walk best-EV first; keep the first play we
  //    can actually EXECUTE — a reliable club, and a flight the golfer can produce for
  //    the route. Eliminations are recorded, not hidden. Never pick an ideal
  //    destination we can't hit. ──
  const ranked = candidates.map(c => ({ ...c, elim: null, executable: true }));
  let selected = null;
  for (const c of ranked) {
    const rel = c.rel != null ? c.rel : 60;
    if (rel < RELIABLE) { c.executable = false; c.elim = `club not trusted enough today (${round(rel)}/100)`; continue; }
    if (c.flightForced && c.flight === "sideways" && c.kind !== "punch" && c.kind !== "hero") {
      c.executable = false; c.elim = "no window forward — needs a reposition"; continue;
    }
    selected = c; break;
  }
  // Nothing cleared the trust bar → automatically fall to the next-lowest-EV play we
  // can execute at all: the most reliable advance. Protect today's score, honestly.
  if (!selected) {
    selected = ranked.slice().sort((a, b) => (b.rel || 0) - (a.rel || 0) || a.ev - b.ev)[0];
    selected.elim = null; selected.executable = true;
    selected.underProtest = true;
  }

  const second = ranked.find(c => c !== selected && c.executable) || ranked[1] || null;
  const confidence = confidenceOf(ctx, selected, second);
  const cue = cueFor(selected);
  return finalize(ctx, recovery ? "recovery" : "standard", selected, ranked, confidence, recoData, cue);
}

// One swing cue — a single feel, never a stat.
function cueFor(sel) {
  if (sel.kind === "punch" || sel.route === "out") return "Low, sideways, back in play.";
  if (sel.kind === "hero") return "Full commit or don't take it on.";
  if (sel.flight === "high") return "Elevate it — get it up and over.";
  if (sel.flight === "low") return "Knock it down — stay under it.";
  if (sel.flight === "shaped") return "Start it at the edge and let it work.";
  if (sel.kind === "layup") return "Smooth — this is a placement, not a hit.";
  if (sel.kind === "position") return "Fairway finder — center, no hero.";
  return "Smooth and committed.";
}

// A picture, not numbers: where to aim, what the ball should do, where it finishes.
// Language is shaped by the KIND of play so a tee shot never reads like an approach
// and a lay-up never tells the golfer to control the final resting spot.
function pictureOf(ctx, sel) {
  const isRec = sel.kind === "punch" || sel.kind === "hero" || sel.route === "out" || sel.route === "sideways";
  let startLine;
  if (sel.route === "over") startLine = "over the trouble, at the flag";
  else if (sel.route === "around") startLine = "start it at the edge and let it turn back";
  else if (isRec) startLine = "out to the open side";
  else if (sel.kind === "attack") startLine = "at the flag — center is plenty";
  else if (sel.kind === "layup") startLine = "short of the trouble, to your number";
  else startLine = "at the middle of the fairway";   // position / par-4-5 tee only
  const trajectory = sel.flight === "high" ? "high and soft"
    : sel.flight === "low" ? "low and running"
    : sel.flight === "shaped" ? "a working ball"
    : "your stock flight";
  let landing;
  if (sel.kind === "attack" || sel.reach) landing = "onto the green";
  else if (isRec) landing = sel.leaves > 0 ? `back in play, about ${sel.leaves} to the pin` : "back in the short grass";
  else if (sel.kind === "layup") landing = `leaving about ${sel.leaves} in`;
  else landing = `into the fairway, about ${sel.leaves} to the green`;    // tee / position
  return { startLine, trajectory, landing };
}

// Assemble the final recommendation + the decision record (for later learning).
function finalize(ctx, mode, sel, ranked, confidence, recoData, cue) {
  const pic = pictureOf(ctx, sel);
  const record = {
    situation: {
      hole: ctx.hole && (ctx.hole.n || null), par: ctx.hole && ctx.hole.par,
      rem: ctx.rem, effRem: ctx.effRem, lie: ctx.lie, wind: ctx.wind,
      from: ctx.from ? { d: ctx.from.d, x: ctx.from.x } : null, strokes: ctx.strokes,
      context: ctx.context || null,
    },
    // Every play weighed BEFORE the caddie spoke: club+flight, today's trust, the
    // expected score, the severe-miss exposure, and the expected next position. This
    // is the internal comparison behind the single call (surfaced under "Why?").
    candidates: ranked.map(c => ({
      kind: c.kind, club: c.club, flight: c.flight || null, ev: c.ev,
      rel: c.rel != null ? Math.round(c.rel) : null,
      leaves: c.leaves != null ? c.leaves : null,
      water: c.exposure ? c.exposure.water : null,
      executable: c.executable !== false, elim: c.elim || null,
    })),
    selected: {
      kind: sel.kind, club: sel.club, route: sel.route, flight: sel.flight, ev: sel.ev,
      destination: sel.destination, distance: sel.distance, leaves: sel.leaves, intent: sel.intent,
    },
    expected: { ev: sel.ev, leaves: sel.leaves },
    confidence,
    observation: { asked: !!ctx.askObservation, given: ctx.observation || null },
    underProtest: !!sel.underProtest,
    actual: null,     // filled when the shot's result is logged
  };
  // A dispersion footprint for the map (Part 7) — the honest scatter this club/flight
  // produces for this golfer around the intended landing. Standard plays only.
  const dest = sel.destination || {};
  const dispersion = (dest.d != null && dest.x != null && sel.scatter)
    ? { d: dest.d, x: dest.x, rx: sel.scatter.sdX * 1.6, ry: sel.scatter.sdD * 1.6 } : null;
  return {
    mode, context: ctx.context || null, club: sel.club, kind: sel.kind, flight: sel.flight, route: sel.route,
    play: { kind: sel.kind, destination: sel.destination, distance: sel.distance, leaves: sel.leaves, intent: sel.intent, ev: sel.ev },
    startLine: pic.startLine, trajectory: pic.trajectory, landing: pic.landing, cue,
    reach: !!sel.reach, leaves: sel.leaves, intent: sel.intent,
    aim: dest.d != null ? { d: dest.d, x: dest.x, label: null } : null, dispersion,
    confidence, candidates: ranked, record,
    askObservation: !!ctx.askObservation,
    recovery: recoData ? recoData.plan : null,
  };
}
