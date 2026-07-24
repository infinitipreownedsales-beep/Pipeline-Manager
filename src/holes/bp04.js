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
  hz: "Tree-lined par 5 · a small creek near the tee boxes · a creek cuts diagonally across the approach and widens into a triangle at the landing-left · heavy trees both sides · bunker right of the green",
  favor: "right-center",
  // Tee center, gentle bend, then back right to the green.
  path: [[0, 0.55], [0.45, 0.49], [1, 0.58]],
  hazards: [
    { type: "water", pool: [0.06, 0.16, 0.44, 0.68] },    // creek near the tee boxes
    { side: "L", type: "trees", from: 0.10, to: 0.55 },   // heavy trees down the left
    { side: "R", type: "trees", from: 0.12, to: 0.52 },   // heavy trees down the right
    // a creek cutting diagonally across the approach, widening into a triangle at the landing-left
    { type: "water", pool: [0.52, 0.64, 0.18, 0.42] },    // the triangle (creek widens, landing-left)
    { type: "water", pool: [0.64, 0.76, 0.36, 0.56] },    // creek mid
    { type: "water", pool: [0.78, 0.90, 0.54, 0.74] },    // creek up near the green (crosses right)
    { side: "R", type: "trees", from: 0.56, to: 0.82 },   // trees up the right
    { side: "L", type: "trees", from: 0.60, to: 0.90 },   // trees up the left
    { side: "R", type: "sand",  from: 0.90, to: 1.00 },   // bunker right of the green
  ],
  carry: null,
  corner: 250,
  cornerLabel: "landing",
  green: { toPin: 516, guard: "bunker right; the creek crosses the approach; trees both sides", reference: "hardwired flag" },
  landing: { target: 250, leaves: 266, note: "~250 short of the creek/triangle at the landing-left — leaves ~266, but the creek crosses the approach" },
  vibe: "A 516 tree-lined par 5 defended by a creek, not a lake. There's a small creek near the tee boxes to clear, then heavy trees line both sides down to a landing where a creek cuts diagonally across the hole and widens into a triangle on the left. The lay-up has to respect that diagonal — stay right of the triangle and short or long of the creek, never in it — and the creek keeps crossing up toward a green guarded by a bunker on the right. Position over power: find the gaps between the trees, take your medicine on the creek, and leave a clean wedge. Three smart swings beat one hero carry over the water.",
  cue: "Small creek off the tee, then thread the trees — stay right of the triangle and clear of the diagonal creek. Bunker guards the green right.",
};
