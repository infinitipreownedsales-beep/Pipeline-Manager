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
  hz: "Short par 4 · houses / OB down the ENTIRE left · stand of trees down the right · narrow corridor · green by the clubhouse with a bunker right — thread it, don't force it",
  favor: "center",
  // Nearly straight up a narrow corridor, green a touch left at the top.
  path: [[0, 0.45], [0.45, 0.54], [1, 0.44]],
  hazards: [
    { side: "L", type: "houses", from: 0.00, to: 0.88 },  // neighborhood / OB down the entire left
    { side: "R", type: "trees",  from: 0.05, to: 0.85 },  // stand of trees down the right
    { side: "L", type: "trees",  from: 0.82, to: 0.95 },  // trees left of the green
    { side: "R", type: "sand",   from: 0.90, to: 1.00 },  // bunker right of the green
  ],
  carry: null,
  corner: 198,
  cornerLabel: "landing",
  green: { toPin: 323, guard: "OB & trees left, bunker right, clubhouse long", reference: "hardwired flag" },
  landing: { target: 198, leaves: 130, note: "~198 to the middle of the corridor keeps OB left out of play — leaves ~130 in" },
  vibe: "A short 323 par 4 to finish the nine, and like the 8th it is about staying between the trouble. Out-of-bounds — a neighborhood — lines the ENTIRE left, and a stand of trees guards the right, leaving a narrow corridor for the tee shot. This is a position play: take enough club to reach the middle of the fairway (~198) and no more, which keeps the OB out of play and leaves a wedge (~130) to a green by the clubhouse with a bunker right. Left is dead and right is blocked by trees, so commit to the center, take your medicine if you're not perfect, and let a smooth wedge set up the finish.",
  cue: "Thread the corridor — center off the tee to hold OB left out of play, then a smooth wedge to the green.",
};
