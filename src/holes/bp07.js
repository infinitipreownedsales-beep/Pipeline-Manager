// Bay Pointe — Hole 7. Mapped from the Shot Scope overview (IMG_2302) + recording.
// A 483 par 5 built around a central stand of trees: the drive plays up the LEFT
// side, then the hole turns back RIGHT to a green on the far corridor. Ponds sit
// low-left near the tee, trees line everything (and divide the two fairways), houses
// run down the right, and a bunker guards the green. Distances are flag-referenced.
export default {
  n: 7,
  par: 5,
  y: 483,                 // ~237 tee→corner + ~246 corner→flag
  tgt: 6,
  hz: "Par 5 around a central tree stand · drive up the LEFT · ponds low-left off the tee · trees divide the fairways · turns back RIGHT to the green · bunker right · houses right",
  favor: "center",
  // Up the left off the tee, then the hole turns back right to the green.
  path: [[0, 0.55], [0.5, 0.35], [1, 0.62]],
  hazards: [
    { type: "water", pool: [0.00, 0.15, 0.02, 0.30] },    // ponds low-left near the tee
    { side: "L", type: "trees", from: 0.12, to: 0.62 },   // trees down the far left
    { side: "R", type: "trees", from: 0.06, to: 0.34 },   // trees right off the tee
    { side: "R", type: "trees", from: 0.40, to: 0.80 },   // the central stand that divides the fairways
    { side: "L", type: "trees", from: 0.74, to: 0.92 },   // trees left of the green
    { side: "R", type: "sand",  from: 0.90, to: 1.00 },   // bunker right of the green
  ],
  carry: null,
  corner: 237,
  cornerLabel: "corner",
  green: { toPin: 483, guard: "bunker right, trees left; central stand short-right", reference: "hardwired flag" },
  landing: { target: 237, leaves: 246, note: "~237 up the left corridor to the corner, then the hole turns right — leaves ~246 to the green" },
  vibe: "A 483 par 5 that plays around a central stand of trees. Off the tee the line is up the LEFT corridor — ponds sit low-left so it's not a bail-out, but the left side is the only way to keep the green in view. From the corner the hole turns back RIGHT: the central trees block the direct line, so the lay-up is about getting an angle down the right side to a green guarded by a bunker right and trees left. Position over power — take the left off the tee, advance to a clean angle, then attack. One greedy swing at the trees turns a birdie hole into a scramble.",
  cue: "Up the left off the tee, then work back right around the central trees. Bunker guards the green right.",
};
