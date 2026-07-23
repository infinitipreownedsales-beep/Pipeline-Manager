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
  hz: "Tree-lined par 5 · lake LEFT of the tee · fairway bends left then back right · pond in the trees right-of-center · trees both sides · bunker right of the green",
  favor: "center",
  // Tee center, a gentle bend left to the landing, then back right to the green.
  path: [[0, 0.55], [0.45, 0.45], [1, 0.57]],
  hazards: [
    { side: "L", type: "water", from: 0.00, to: 0.12 },   // lake left of the tee
    { side: "L", type: "trees", from: 0.10, to: 0.50 },   // trees down the left
    { side: "R", type: "trees", from: 0.12, to: 0.38 },   // trees down the right off the tee
    { type: "water", pool: [0.40, 0.52, 0.70, 0.90] },    // pond tucked in the trees right-of-center
    { side: "R", type: "trees", from: 0.54, to: 0.82 },   // trees up the right
    { side: "L", type: "trees", from: 0.62, to: 0.88 },   // a stand of trees pinches the left near the green
    { side: "R", type: "sand",  from: 0.90, to: 1.00 },   // bunker right of the green
  ],
  carry: null,
  corner: 250,
  cornerLabel: "landing",
  green: { toPin: 516, guard: "bunker right, trees left & long", reference: "hardwired flag" },
  landing: { target: 250, leaves: 266, note: "~250 to the center of the landing, favor center — leaves ~266 up the right-bending fairway" },
  vibe: "A 516 par 5 that rewards position over power. The tee shot threads a tree-lined corridor with a lake off the left, so the smart line is a center drive that holds the short grass — the fairway then bends left to the landing before curving back right to the green. A pond hides in the trees right-of-center, and a stand of trees pinches the left as you approach, so the lay-up is about angle: keep it center-right to open the green, which is guarded by a bunker on the right and trees left and long. Three smooth, committed swings up the middle beat one hero swing into the trees.",
  cue: "Center off the tee, hold the short grass, then position the lay-up center-right. Bunker guards the green right.",
};
