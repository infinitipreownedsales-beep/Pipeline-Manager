// Bay Pointe — Hole 4. Mapped from the Shot Scope overview (IMG_2295/2296) + recording.
// A 516 par 5 up a tree-lined corridor: a lake sits left of the tee, the fairway bends
// gently LEFT to the landing then back RIGHT to the green, heavy trees line both sides,
// a pond hides in the trees right-of-center, and a bunker guards the green right. A
// position par 5 — stay in the short grass and it opens up. Distances are flag-referenced.
export default {
  n: 4,
  par: 5,
  y: 516,
  tgt: 6,
  tees: { blue: 605, white: 530, gold: 515, red: 475, green: 420 },   // card yardages, all sets
  hz: "Tree-lined par 5 · lake LEFT of the tee · WATER runs up the LEFT-center of the fairway through the landing & approach · pond in the trees right-of-center · trees both sides · bunker right of the green",
  favor: "right-center",
  // Tee center, gentle bend, then back right to the green — holding away from the left water.
  path: [[0, 0.55], [0.45, 0.49], [1, 0.58]],
  hazards: [
    { side: "L", type: "water", from: 0.00, to: 0.12 },   // lake left of the tee
    { side: "L", type: "trees", from: 0.10, to: 0.48 },   // trees down the left off the tee
    { side: "R", type: "trees", from: 0.12, to: 0.38 },   // trees down the right off the tee
    { type: "water", pool: [0.40, 0.52, 0.70, 0.90] },    // pond tucked in the trees right-of-center
    { type: "water", pool: [0.50, 0.88, 0.16, 0.56] },    // water up the LEFT-center of the fairway (blue mark)
    { side: "R", type: "trees", from: 0.54, to: 0.82 },   // trees up the right
    { side: "R", type: "sand",  from: 0.90, to: 1.00 },   // bunker right of the green
  ],
  carry: null,
  corner: 250,
  cornerLabel: "landing",
  green: { toPin: 516, guard: "bunker right; water & trees left", reference: "hardwired flag" },
  landing: { target: 250, leaves: 266, note: "~250 to the center-right of the landing, away from the left water — leaves ~266" },
  vibe: "A 516 par 5 where water down the LEFT is the whole story. A lake sits off the tee left, and water runs up the left-center of the fairway through the landing and approach — so every shot favors the right side of the corridor. Off the tee, a center-right drive holds the short grass away from the water and the trees; the lay-up should stay right-center to keep dry and open the green. A pond also hides in the trees right-of-center, and the green is guarded by a bunker right, so the miss is short-right, never left. Three committed swings up the right beat any flirt with the water left.",
  cue: "Right-center the whole way — water runs up the left. Lay up right of it, then bunker guards the green right.",
};
