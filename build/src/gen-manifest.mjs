import { coreComponents } from "./core-components.jsx";
import { packs } from "./packs/index.js";
process.stdout.write(JSON.stringify({ core: coreComponents.map((d) => d.name), packs: Object.fromEntries(packs.map((p) => [p.name, p.components.map((d) => d.name)])) }));
