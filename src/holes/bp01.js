// Bay Pointe — Hole 1. Mapped from the Shot Scope recording + satellite.
// Kept as its own file so it can be refined independently over time.
// Distances are flag-referenced. `path` and `hazards` carry the real geometry so
// both the schematic AND the engine can reason about the bend and where trouble is.
export default {
  n: 1,
  par: 4,
  y: 368,                 // to the flag (this tee): 180 tee→point + 188 point→flag
  tgt: 5,
  hz: "Trees left off the tee, trees down the ENTIRE right · pond top-left by the green · uphill to a raised green · greenside bunkers",
  // centerline: [d (0 tee → 1 green), x (0 left → 1 right)]. Tee sits right of center,
  // the fairway bends left to the landing, then back to a center green.
  path: [[0, 0.60], [0.45, 0.34], [1, 0.50]],
  // per-side, per-section hazards (from/to are fractions of hole length from the tee)
  hazards: [
    { side: "L", type: "trees", from: 0.00, to: 0.42 },   // trees left near the tee
    { side: "R", type: "trees", from: 0.00, to: 1.00 },   // trees the entire right side
    { side: "L", type: "water", from: 0.74, to: 1.00 },   // pond top-left by the green
  ],
  dzL: "trees",
  dzR: "trees",
  favor: "left-center",   // engine/aim hint: follow the bend, away from the right tree wall
  carry: null,
  green: { toPin: 368, raised: true, guard: "greenside bunkers; pond left", reference: "hardwired flag" },
  landing: { target: 250, leaves: 118, note: "driver ~250 to the left-center corner leaves ~118 uphill" },
  elevation: "elevated tee down to the fairway, then uphill to a raised green — the approach plays longer, club up",
  vibe: "A 368 uphill par 4 that bends left off the tee then straightens to a raised green. Trees crowd the LEFT near the tee and line the ENTIRE right side, so favor the left-center off the tee and let the fairway's bend work for you — the right tree wall is the real danger. It climbs to a raised green with bunkers and a pond left, so club up on the approach, commit to the middle, and keep it out of the right trees.",
  cue: "Left-center off the tee, follow the bend, one more club in.",
};
