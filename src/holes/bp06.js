// Bay Pointe — Hole 6. Mapped from the Shot Scope overview (IMG_2300) + recording.
// A 150 par 3 played across a tree-filled ravine to a green benched on the far side,
// with a POND guarding the front-LEFT. It's a committed carry — trees fill the valley
// between tee and green and water sits short-left, so short and left are dead. Distances
// are flag-referenced.
export default {
  n: 6,
  par: 3,
  y: 150,
  tgt: 4,
  tees: { blue: 175, white: 160, gold: 140, red: 108, green: 103 },   // card yardages, all sets
  hz: "All carry over a water-filled ravine · a creek/crossing right off the tee · a big POND fills the front of the green · heavy trees both sides · SHORT is dead — commit the carry",
  favor: "center",
  dzL: "water",
  // Nearly straight, green a touch right of the tee line.
  path: [[0, 0.46], [0.5, 0.48], [1, 0.52]],
  hazards: [
    { type: "water", pool: [0.05, 0.19, 0.24, 0.74] },    // creek/crossing right off the tee boxes
    { side: "L", type: "trees", from: 0.12, to: 0.66 },   // wooded ravine, left
    { side: "R", type: "trees", from: 0.12, to: 0.70 },   // wooded ravine, right
    { type: "water", pool: [0.38, 0.52, 0.30, 0.60] },    // creek running through the ravine
    { type: "water", pool: [0.68, 0.96, 0.12, 0.64] },    // big pond filling the FRONT of the green
    { side: "R", type: "trees", from: 0.80, to: 0.94 },   // trees right of the green
  ],
  carry: 135,             // carry the ravine + the pond fronting the green (approx)
  carryLabel: "the water",
  green: { toPin: 150, raised: true, guard: "big pond fronts the green; creek off the tee; ravine short; trees both sides", pinch: true, reference: "hardwired flag" },
  landing: { target: 150, leaves: 0, note: "one shot, all carry over the water — center of the green, pin-high to a touch long" },
  vibe: "A 150 par 3 that is nothing but water and trees between you and the green. There's a creek/crossing right off the tee, a wooded ravine with water running through it, and a big pond that fills the entire front of the green. There is no bailout short — everything you can see is wet or wooded — so it's a full, committed carry to a green benched on the far side. Short is dead, so pick the club you can carry the number with cleanly, aim at the center, and make a free swing. The trouble only wins if you leave it in front of you.",
  cue: "All carry over the water — center of the green, enough club to be pin-high or long. Short is dead.",
};
