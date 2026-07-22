// Bay Pointe — Hole 2. Mapped from a Shot Scope screen recording.
// A ~373 par 4 wrapped in water: lake left off the tee, a creek across the front
// of a peninsula green, pond + bunker right. Flag-referenced distances.
export default {
  n: 2,
  par: 4,
  y: 373,                 // to the flag: 218 tee→corner + 155 corner→flag
  tgt: 5,
  hz: "Water everywhere — lake LEFT off the tee, a creek crosses in front of the green, pond front-right of a peninsula green · bunker right",
  dzL: "water",
  dzR: "water",
  favor: "right-center",  // off the tee, away from the lake left
  // gentle bend around the water: tee, out to the corner, then across to the green
  path: [[0, 0.50], [0.58, 0.42], [1, 0.56]],
  hazards: [
    { side: "L", type: "water", from: 0.00, to: 0.50 },   // lake left off the tee
    { side: "L", type: "water", from: 0.62, to: 1.00 },   // creek/pond wrapping the green left
    { side: "R", type: "water", from: 0.66, to: 0.92 },   // pond front-right of the green
    { side: "R", type: "sand",  from: 0.90, to: 1.00 },   // bunker right of the green
  ],
  carry: 335,             // the approach must carry the creek short of the green
  carryLabel: "the creek",
  corner: 218,
  cornerLabel: "corner",
  green: { toPin: 373, peninsula: true, guard: "creek short & left, pond + bunker right", reference: "hardwired flag" },
  landing: { target: 218, leaves: 155, note: "~218 to the corner, favor right-center, leaves ~155 across the creek" },
  vibe: "A ~373 par 4 wrapped in water — a lake left off the tee and a creek that cuts across in front of a water-guarded, peninsula green (pond and bunker right). Off the tee it's a position play (~218 to the corner): favor the right-center and never chase the left, which is the lake. The approach (~155) must carry the creek to a green ringed by trouble — take enough club, aim center to long, and treat short (creek) and right (pond/bunker) as dead. Long or center-left is the only safe miss.",
  cue: "Right-center off the tee, then carry the creek — center-long, short and right are wet.",
};
