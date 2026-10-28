// The FULL widget library (core + every pack). Used by the Node-side tools only: the validator and the prompt
// generator must know every component. The browser never builds this: core.jsx assembles a library from the
// core components plus whichever packs the page embedded.
import { createLibrary } from "@openuidev/react-lang";
import { coreComponents } from "./core-components.jsx";
import { packs } from "./packs/index.js";

// Historical order: keeps references/components.md stable. New components land after these.
const ORDER = ["Stack", "Text", "Card", "Metric", "Table", "BarChart", "Callout", "Button", "TabItem", "Tabs", "Markdown", "CodeBlock", "Image", "DagNode", "Dag", "Entity", "Relation", "Erd", "GeoPoint", "GeoMap", "FaqItem", "Faq", "Choice", "Series", "LineChart", "AreaChart", "PieChart", "RadarChart", "InfraNode", "InfraZone", "InfraLink", "InfraMap"];
const all = [...coreComponents, ...packs.flatMap((p) => p.components)];
const byName = new Map(all.map((d) => [d.name, d]));
if (byName.size !== all.length) throw new Error("duplicate component name across core and packs");
const ordered = [...ORDER.filter((n) => byName.has(n)).map((n) => byName.get(n)), ...all.filter((d) => !ORDER.includes(d.name))];

export const components = ordered;
export const library = createLibrary({ root: "Stack", components: ordered });
