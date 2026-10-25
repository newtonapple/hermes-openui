// The optional packs. Adding a pack: create packs/<name>.jsx exporting `pack`, list it here, rebuild.
import { pack as charts } from "./charts.jsx";
import { pack as diagrams } from "./diagrams.jsx";
import { pack as map } from "./map.jsx";
import { pack as text } from "./text.jsx";
export const packs = [charts, diagrams, map, text];
