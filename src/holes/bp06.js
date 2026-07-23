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
  hz: "All carry over a wooded ravine · pond guards the front-LEFT of the green · trees fill the valley both sides · short and LEFT are dead — miss right or long",
  favor: "center-right",
  dzL: "water",
  // Nearly straight, green a touch right of the tee line.
  path: [[0, 0.46], [0.5, 0.48], [1, 0.52]],
  hazards: [
    { type: "water", pool: [0.00, 0.09, 0.02, 0.22] },    // small pond left of the tee
    { side: "L", type: "trees", from: 0.08, to: 0.70 },   // wooded valley, left
    { side: "R", type: "trees", from: 0.08, to: 0.80 },   // wooded valley, right
    { type: "water", pool: [0.70, 0.88, 0.14, 0.48] },    // pond guarding the front-left of the green
    { side: "R", type: "trees", from: 0.82, to: 0.95 },   // trees right of the green
  ],
  carry: 135,             // carry the ravine + pond to the benched green (approx)
  carryLabel: "the ravine",
  green: { toPin: 150, raised: true, guard: "pond front-left, trees right & long, wooded ravine short", reference: "hardwired flag" },
  landing: { target: 150, leaves: 0, note: "one shot, all carry over the ravine — center-right of the green, pin-high to a touch long" },
  vibe: "A 150 par 3 with nothing but a wooded ravine between you and the green, and a pond guarding the front-left. There's no bailout short — trees fill the valley and water sits short-left — so it's a full, committed carry to a green benched on the far side. Short is dead and left brings the pond, so favor the center-right and take enough club to be pin-high or a hair long. Pick the club you can carry the number with cleanly, aim away from the water, and make a free swing — the trouble only wins if you come up short.",
  cue: "All carry over the ravine — center-right, enough club to be pin-high or long. Short and left are dead.",
};
