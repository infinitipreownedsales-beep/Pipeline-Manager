// Bay Pointe — Hole 5. Mapped from the Shot Scope recording (no annotated overview).
// A ~374 dogleg par 4: the fairway runs out to a corner (~258) then turns to a green
// tucked behind a big POND that guards the front and right — the approach is a carry
// over water. Trees line both sides and a waste/sand area sits at the corner. Distances
// are flag-referenced. Par/yardage inferred from the 258 + 116 Shot Scope marks.
export default {
  n: 5,
  par: 4,
  y: 374,                 // 258 tee→corner + 116 corner→flag
  tgt: 5,
  tees: { blue: 375, white: 365, gold: 300, red: 260, green: 250 },   // card yardages, all sets
  hz: "Dogleg par 4 · trees both sides · waste/sand at the corner · big POND guards the front & RIGHT of the green — the approach carries water · miss left, never short-right",
  favor: "center",
  // Out to the corner (~d0.62), then the fairway turns left to a green tucked left.
  path: [[0, 0.60], [0.6, 0.66], [1, 0.40]],
  hazards: [
    { side: "R", type: "trees", from: 0.05, to: 0.58 },   // trees down the right
    { side: "L", type: "trees", from: 0.10, to: 0.55 },   // trees down the left
    { side: "R", type: "sand",  from: 0.56, to: 0.72 },   // waste/sand at the corner
    { side: "L", type: "trees", from: 0.66, to: 0.84 },   // trees left on the approach
    { type: "water", pool: [0.76, 1.00, 0.44, 0.88] },    // pond guarding the front & right of the green
    { side: "L", type: "sand",  from: 0.86, to: 0.98 },   // bunker short-left of the green
  ],
  carry: 340,             // carry the pond to the green on the approach (approx)
  carryLabel: "the water",
  corner: 258,
  cornerLabel: "corner",
  green: { toPin: 374, guard: "pond front & right, bunker short-left, trees left", reference: "hardwired flag" },
  landing: { target: 258, leaves: 116, note: "~258 to the corner, favor center — leaves ~116 across the water to the green" },
  vibe: "A ~374 dogleg par 4 that ends with a forced carry. Off the tee it's a position play out to the corner (~258) between tree lines, with a waste/sand area guarding the right of the turn — a smooth center drive is plenty. From there the hole shows its teeth: a big pond wraps the front and right of the green, so the approach (~116) is all carry to a green that leans left. Take enough club, aim at the center-left, and treat short and right as wet — long or left is the only safe miss. Position off the tee, commit over the water in.",
  cue: "Center to the corner, then all carry over the pond — aim center-left, short-right is wet.",
};
