// Assembles the individually-mapped holes into a built-in, flag-referenced course.
// Add a hole by creating its own file (bp03.js, …) and appending it to `holes`.
import bp01 from "./bp01.js";
import bp02 from "./bp02.js";
import bp03 from "./bp03.js";
import bp04 from "./bp04.js";
import bp05 from "./bp05.js";

export const MAPPED_HOLES = [bp01, bp02, bp03, bp04, bp05];

export const MAPPED = {
  bpmapped: {
    name: "Bay Pointe (mapped)",
    holes: MAPPED_HOLES,
    ref: "flag",       // distances read "to the flag", matching how Shot Scope measures
    mapped: true,
  },
};
