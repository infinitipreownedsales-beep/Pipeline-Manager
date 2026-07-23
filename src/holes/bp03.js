// Bay Pointe — Hole 3. Mapped from the Shot Scope overview (IMG_2290/2292) + recording.
// A 110 par 3 over a big pond: the water is one central body that fills the front and
// left, and the tee shot flies over/up the RIGHT edge of it to a raised green perched
// just past the far bank. A small pond sits off the right of the green; grass long/behind
// is the bailout. Short is dead — it's all carry. Distances are flag-referenced.
export default {
  n: 3,
  par: 3,
  y: 110,
  tgt: 4,
  tees: { blue: 126, white: 118, gold: 105, red: 95, green: 85 },   // card yardages, all sets
  hz: "All carry over a big central pond (front + left) · line skirts the RIGHT edge to a raised green · small pond off the RIGHT · trees frame both sides · bailout grass long · SHORT is dead",
  favor: "center",
  // Tee sits right of the pond; the line plays up its right edge to a green just past it.
  path: [[0, 0.60], [0.5, 0.585], [1, 0.52]],
  hazards: [
    // the main pond: one body filling the front-left that you carry to the green
    { type: "water", pool: [0.16, 0.80, 0.06, 0.60] },
    // a small pond off the right of the green
    { type: "water", pool: [0.80, 0.97, 0.66, 0.90] },
    // tree line down the right of the corridor, and trees framing the left of the green
    { side: "R", type: "trees", from: 0.05, to: 0.92 },
    { side: "L", type: "trees", from: 0.82, to: 1.00 },
  ],
  carry: 95,              // carry the pond to the front of the raised green
  carryLabel: "the water",
  green: { toPin: 110, raised: true, guard: "big pond short & left, small pond right, grass long", reference: "hardwired flag" },
  landing: { target: 110, leaves: 0, note: "one shot, all carry over the pond — center of the green, pin-high to a touch long" },
  vibe: "A 110 par 3 played entirely over a big pond. The water is one body that fills the front and the whole left, and your line runs up its RIGHT edge to a raised green just past the far bank, with a small pond off the right and grass long as the bailout. There's no lay-up and no ground game — pick the club that carries the number without a doubt, aim center to a hair long, and swing free. Short is the only dead miss; the water only wins if you leave it in front of you.",
  cue: "All carry over the pond — center green, enough club to be pin-high or long. Short is dead.",
};
