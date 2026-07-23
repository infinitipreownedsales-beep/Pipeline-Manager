// Bay Pointe — Hole 8. Mapped from the Shot Scope overview (IMG_2304) + recording.
// A short 327 par 4 pinched between out-of-bounds and trees: a neighborhood (OB)
// runs down the ENTIRE left, a tree line guards the right, and the fairway threads
// up the middle-right to a green tucked at the top. A placement hole — position,
// not power. Distances are flag-referenced.
export default {
  n: 8,
  par: 4,
  y: 327,                 // ~210 tee→corner + ~117 corner→flag
  tgt: 5,
  tees: { blue: 355, white: 340, gold: 325, red: 215, green: 208 },   // card yardages, all sets
  hz: "Short par 4 · houses / OB down the ENTIRE left · tree line down the right · waste-sand right of the landing · green tucked at the top — position over power",
  favor: "center-right",
  // Tee center-left, a touch right through the landing, green back to center.
  path: [[0, 0.45], [0.5, 0.56], [1, 0.48]],
  hazards: [
    { side: "L", type: "houses", from: 0.00, to: 0.86 },  // neighborhood / OB down the entire left
    { side: "R", type: "trees",  from: 0.05, to: 0.88 },  // tree line down the right
    { side: "R", type: "sand",   from: 0.52, to: 0.66 },  // waste-sand right of the landing
    { side: "L", type: "trees",  from: 0.82, to: 0.96 },  // trees left of the green
    { side: "R", type: "sand",   from: 0.90, to: 1.00 },  // bunker right of the green
  ],
  carry: null,
  corner: 210,
  cornerLabel: "landing",
  green: { toPin: 327, guard: "OB & trees left, bunker right", reference: "hardwired flag" },
  landing: { target: 210, leaves: 117, note: "~210 to the center-right of the fairway keeps OB left out of play — leaves ~117 in" },
  vibe: "A short 327 par 4 that is all about staying between the trouble. Out-of-bounds — a neighborhood — runs down the ENTIRE left, and a tree line guards the right, so this is a placement tee shot, not a driver. Take enough club to reach the center-right of the fairway (~210) and no more; that keeps the OB out of play and leaves a simple wedge (~117) to a green tucked at the top with a bunker right and trees left. Greed left is dead, so favor the right-center off the tee and let a smooth wedge do the scoring. Fairway first, flag second.",
  cue: "Placement, not power — center-right off the tee to take OB left out of play, then a smooth wedge in.",
};
