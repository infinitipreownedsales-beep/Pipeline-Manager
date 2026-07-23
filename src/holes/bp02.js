// Bay Pointe — Hole 2. Mapped from the Shot Scope overview (IMG_2287) + recording.
// A 382 par 4 that opens with a forced water carry: a creek/wetland cuts across the
// hole in front of the fairway, so the tee shot has to carry it to reach short grass.
// Two tee boxes (the yellow circles) move day to day — the BACK box sits behind the
// water (you carry the creek), the FORWARD box is across it at the fairway start — so
// the yardage shown at the tee tells you which one is in play. Lake down the LEFT the
// whole way; the green sits up top with a pond front-RIGHT and water left/long.
// Distances are flag-referenced.
export default {
  n: 2,
  par: 4,
  y: 382,                 // official card yardage (back tee, over the water)
  tgt: 5,
  hz: "Forced carry off the tee — a creek crosses in front of the fairway · lake down the LEFT all the way · pond front-RIGHT of the green · bunker right · water left & long",
  dzL: "water",
  dzR: "water",
  favor: "right-center",  // off the tee, hold the right-center away from the lake left
  // Mostly straight, leaning gently right to a green just right of the tee line.
  path: [[0, 0.44], [0.5, 0.46], [1, 0.53]],
  hazards: [
    { side: "L", type: "water", from: 0.00, to: 0.55 },   // the lake down the left off the tee
    { side: "L", type: "water", from: 0.80, to: 1.00 },   // creek wrapping behind/left of the green
    { side: "R", type: "sand",  from: 0.46, to: 0.62 },   // waste/bunker area right of the fairway
    { side: "R", type: "trees", from: 0.60, to: 0.78 },   // tree line up the right
    { side: "R", type: "water", from: 0.72, to: 0.95 },   // pond front-right of the green
    { side: "R", type: "sand",  from: 0.92, to: 1.00 },   // bunker right of the green
  ],
  carry: 130,             // clear the creek off the BACK tee to reach the fairway (approx)
  carryLabel: "the creek",
  corner: 210,
  cornerLabel: "landing",
  green: { toPin: 382, guard: "pond front-right, water left & long, bunker right", reference: "hardwired flag" },
  landing: { target: 210, leaves: 172, note: "~210 down the right-center leaves ~172 to a green with a pond right" },
  tees: { note: "Two boxes: the BACK box is behind the water (carry the creek), the FORWARD box is across it at the fairway start. The tee yardage tells you which is set that day." },
  vibe: "A 382 par 4 that starts with a decision at the tee: a creek cuts across in front of the fairway, and the two tee boxes move — some days you're behind the water carrying the creek, some days you're across it at the fairway start, so read the yardage before you pull a club. The lake runs down the ENTIRE left, so the tee shot is a right-center position play — never flirt with the left. From the fairway (~172 in) the green sits up top with a pond front-RIGHT and water left and long; a waste/bunker area guards the right off the tee. Aim center, take enough club, and treat right (pond/bunker) and long-left (water) as dead — center to center-long is the only clean miss.",
  cue: "Read the tee yardage, then right-center over the creek — never left. Approach center, pond's right.",
};
