// Bay Pointe — Hole 9. Mapped from the Shot Scope overview (IMG_2306) + recording.
// A short 323 par 4 that closes the front nine: a neighborhood (OB) runs down the
// ENTIRE left and a stand of trees guards the right, so the fairway is a narrow
// corridor up to a green by the clubhouse with a bunker right. Position over power.
// Distances are flag-referenced.
export default {
  n: 9,
  par: 4,
  y: 323,                 // ~198 tee→corner + ~130 corner→flag
  tgt: 5,
  hz: "Short par 4 · houses / OB down the ENTIRE left · stand of trees down the right · POND in front of the green — the approach carries water · bunker right — thread it, don't force it",
  favor: "center",
  // Nearly straight up a narrow corridor, green a touch left at the top.
  path: [[0, 0.45], [0.45, 0.54], [1, 0.44]],
  hazards: [
    { side: "L", type: "houses", from: 0.00, to: 0.88 },  // neighborhood / OB down the entire left
    { side: "R", type: "trees",  from: 0.05, to: 0.82 },  // stand of trees down the right
    { type: "water", pool: [0.84, 0.97, 0.24, 0.62] },    // pond fronting the green — the approach carries it
    { side: "L", type: "trees",  from: 0.80, to: 0.94 },  // trees left of the green
    { side: "R", type: "sand",   from: 0.90, to: 1.00 },  // bunker right of the green
  ],
  carry: 300,             // carry the pond in front to the green (approx)
  carryLabel: "the water",
  corner: 198,
  cornerLabel: "landing",
  green: { toPin: 323, guard: "pond in front, OB & trees left, bunker right", reference: "hardwired flag" },
  landing: { target: 198, leaves: 130, note: "~198 to the middle of the corridor keeps OB left out of play — leaves ~130 over the pond to the green" },
  vibe: "A short 323 par 4 to finish the nine, and like the 8th it is about staying between the trouble — with a sting at the end. Out-of-bounds — a neighborhood — lines the ENTIRE left, and a stand of trees guards the right, leaving a narrow corridor for the tee shot. This is a position play: take enough club to reach the middle of the fairway (~198) and no more, keeping the OB out of play. But the green is fronted by a pond, so the wedge (~130) is a committed carry — take enough club to be pin-high, never short. Left is dead, short is wet, so commit to the center off the tee and then carry the water with confidence.",
  cue: "Thread the corridor, then carry the pond — center off the tee, enough club to clear the water. Short is wet.",
};
