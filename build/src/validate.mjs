// Node CLI: validate OpenUI Lang against the Hermes widget library.
// usage: node validate.cjs <file.oui>   -> exit 0 ok, 1 problems (printed for the model)
import fs from "node:fs";
import { createParser } from "@openuidev/lang-core";
import { library } from "./library.jsx";

const file = process.argv[2];
if (!file) { console.error("usage: validate.cjs <file>"); process.exit(2); }
const src = fs.readFileSync(file, "utf8");
const parser = createParser(library.toJSONSchema(), library.root);
const { root, meta } = parser.parse(src);
const problems = [];
if (!root) problems.push("No renderable `root` — define `root = Stack([...])`.");
if (meta.incomplete) problems.push("Input looks truncated/incomplete (unbalanced brackets or quotes).");
for (const u of meta.unresolved) problems.push(`Reference \`${u}\` is used but never defined.`);
for (const o of meta.orphaned) problems.push(`\`${o}\` is defined but not reachable from root (it will not render) — add it to a parent's children.`);
// Cross-reference checks (ids/names that must match across components).
const walk = (n, fn) => { if (n && typeof n === "object") { if (n.typeName) fn(n); for (const v of Object.values(n.props ?? {})) (Array.isArray(v) ? v : [v]).forEach((c) => walk(c, fn)); } };
const refNames = (arr, key) => (Array.isArray(arr) ? arr.map((x) => x?.props?.[key]).filter((x) => typeof x === "string") : []);
walk(root, (n) => {
  const p = n.props ?? {};
  if (n.typeName === "Dag") {
    const ids = refNames(p.nodes, "id");
    const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
    if (dup.length) problems.push(`Dag has duplicate node ids: ${[...new Set(dup)].join(", ")}.`);
    for (const e of p.edges ?? []) for (const id of e) if (!ids.includes(id)) problems.push(`Dag edge uses unknown node id \`${id}\` (edges take the DagNode id string; known ids: ${ids.join(", ")}).`);
  }
  if (n.typeName === "Erd") {
    const names = refNames(p.entities, "name");
    for (const r of p.relations ?? []) for (const k of ["from", "to"]) { const v = r?.props?.[k]; if (v && !names.includes(v)) problems.push(`Erd relation ${k} \`${v}\` is not an Entity name (use the entity's name string, not the variable; known: ${names.join(", ")}).`); }
  }
  if (["LineChart", "AreaChart", "RadarChart"].includes(n.typeName)) {
    const L = (p.labels ?? []).length;
    for (const sr of p.series ?? []) {
      const sp = sr?.props ?? {};
      if (Array.isArray(sp.values) && sp.values.length !== L) problems.push(`${n.typeName} series \`${sp.category}\` has ${sp.values.length} values but the chart has ${L} labels (they must be parallel).`);
    }
    if (!(p.series ?? []).length) problems.push(`${n.typeName} needs at least one Series(name, values).`);
  }
  if (["PieChart", "BarChart"].includes(n.typeName)) {
    const a = (p.labels ?? []).length, b = (p.values ?? []).length;
    if (a !== b) problems.push(`${n.typeName} has ${a} labels but ${b} values (they must be parallel).`);
    if (n.typeName === "PieChart" && a > 8) problems.push(`PieChart has ${a} slices; use at most 8 (group the rest as "Other") or switch to a Table/BarChart.`);
  }
  if (n.typeName === "GeoMap") {
    const labels = refNames(p.points, "label");
    for (const l of p.links ?? []) for (const x of l) if (!labels.includes(x)) problems.push(`GeoMap link uses unknown point label \`${x}\` (known: ${labels.join(", ")}).`);
  }
});
for (const e of meta.errors) problems.push(`${e.component ?? ""}${e.statementId ? " in `" + e.statementId + "`" : ""}: ${e.message ?? JSON.stringify(e)}${e.hint ? " — " + e.hint : ""}`);
const uniq = [...new Set(problems)]; problems.length = 0; problems.push(...uniq);
if (problems.length) { console.log("OpenUI validation FAILED:\n- " + problems.join("\n- ")); process.exit(1); }
console.log(`OpenUI validation OK (${meta.statementCount} statements).`);
