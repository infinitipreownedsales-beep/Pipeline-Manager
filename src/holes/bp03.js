// Bay Pointe — Hole 3. Mapped from the Shot Scope overview (IMG_2290, hole outlined,
// water zones marked) + the recording. A 110 par 3 that is all carry: a pond fills the
// front and left, wrapping around a raised green, with a small pond off the RIGHT and a
// bailout of grass long/behind. Short is the only truly dead miss — everything you can
// see between the tee and the green is water. Distances are flag-referenced.
export default {
  n: 3,
  par: 3,
  y: 110,
  tgt: 4,
  hz: "All carry over water — pond short, LEFT, and front wrapping a raised green · small pond off the RIGHT · bailout grass long/behind · SHORT is dead",
  favor: "center",        // island-style green — commit to the center, carry it
  // Nearly straight, green a touch left of the tee line.
  path: [[0, 0.56], [0.5, 0.54], [1, 0.51]],
  hazards: [
    { side: "L", type: "water", from: 0.00, to: 0.82 },   // the pond fills the left and front
    { side: "R", type: "water", from: 0.00, to: 0.55 },   // water short-right off the tee
    { side: "R", type: "water", from: 0.88, to: 1.00 },   // small pond off the right of the green
  ],
  carry: 95,              // carry the water to the front of the raised green
  carryLabel: "the water",
  green: { toPin: 110, raised: true, guard: "water short, left & front; pond right; grass long", reference: "hardwired flag" },
  landing: { target: 110, leaves: 0, note: "one shot, all carry — center of the green, take enough to be pin-high or a touch long" },
  vibe: "A 110 par 3 with nothing but water between you and the green. A pond fills the front and the whole left side and wraps around a raised green, with a small pond off the right and a bailout of grass long and behind. There is no lay-up and no ground game — it is a full, committed carry to the center. Short is dead, right flirts with the second pond, so the smart miss is pin-high to a hair long. Pick the club that carries the number without a doubt, aim center, and make a free, confident swing — the water only wins if you leave it short.",
  cue: "All carry — center of the green, enough club to be pin-high or long. Short is the only dead miss.",
};
