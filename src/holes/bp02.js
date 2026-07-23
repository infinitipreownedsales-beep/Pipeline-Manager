// Bay Pointe — Hole 2. Mapped from the Shot Scope overview with the hole outlined
// (IMG_2288) + the recording. A 382 par 4 that plays nearly straight up a corridor
// pinched by water: a pond low-LEFT off the tee, then a creek that cuts ACROSS the
// hole around the middle (the forced carry), with the river/lake running down the
// upper-LEFT and wrapping left of the green. The landing area is generous to the
// RIGHT but guarded by a waste/bunker area and a tree line; the green sits up top,
// just left of the tee line, with a pond front-RIGHT. Two tee boxes (the yellow
// circles) move day to day, so the yardage at the tee tells you which is in play.
// Distances are flag-referenced.
export default {
  n: 2,
  par: 4,
  y: 382,
  tgt: 5,
  hz: "Creek cuts ACROSS the middle (forced carry) · pond low-left off the tee · river/lake down the upper-LEFT and left of the green · waste + trees RIGHT · pond front-right of the green",
  dzL: "water",
  dzR: "water",
  favor: "center",        // thread it between the left water and the right waste
  // Nearly straight: tee center, a touch right through the landing, green just LEFT.
  path: [[0, 0.50], [0.5, 0.51], [1, 0.46]],
  hazards: [
    { side: "L", type: "water", from: 0.10, to: 0.32 },   // pond low-left off the tee
    { side: "L", type: "water", from: 0.55, to: 1.00 },   // river down the upper-left, left of the green
    { side: "R", type: "sand",  from: 0.45, to: 0.66 },   // waste/bunker area right of the landing
    { side: "R", type: "trees", from: 0.66, to: 0.88 },   // tree line up the right
    { side: "R", type: "water", from: 0.90, to: 1.00 },   // pond front-right of the green
  ],
  carry: 170,             // carry the creek that crosses the middle (approx, back tee)
  carryLabel: "the creek",
  corner: 200,
  cornerLabel: "landing",
  green: { toPin: 382, guard: "pond front-right, river left & long, tree line right", reference: "hardwired flag" },
  landing: { target: 200, leaves: 182, note: "~200 up the center carries the creek and leaves ~182 to a green with a pond right" },
  tees: { note: "Two boxes: the BACK box is behind the water, the FORWARD box is across it. The tee yardage tells you which is set that day." },
  vibe: "A 382 par 4 that plays straighter than it looks but is pinched by water the whole way. A creek cuts across the middle — that's the forced carry — with a pond low-left off the tee and the river running down the upper-left and around the left of the green. The landing area is generous to the RIGHT, but a waste/bunker area and a tree line punish the over-cut, so the tee shot is a center thread: carry the creek, hold the middle, never bail left into the water. From there (~182 in) the green sits just left of your line with a pond front-RIGHT — aim center to center-left, take enough club, and treat right (pond) and long-left (river) as dead. Center is the whole game on this hole.",
  cue: "Read the tee yardage, carry the creek up the center — water left, waste right. Approach center-left, pond's right.",
};
