// Node CLI: validate OpenUI Lang against the Hermes widget library.
// usage: node validate.cjs <file.oui>   -> exit 0 ok, 1 problems (printed for the model)
import fs from "node:fs";
import vm from "node:vm";
import React from "react";
import * as JsxRuntime from "react/jsx-runtime";
import * as Zod from "zod/v4";
import { createLibrary, defineComponent, action, useTriggerAction, useIsQueryLoading } from "@openuidev/react-lang";
import { createParser } from "@openuidev/lang-core";
import { library as builtinLibrary, components as builtinComponents } from "./library.jsx";
import { checkSequence } from "./components/sequence-check.js";

// usage: node validate.cjs [--pack FILE]... <file.oui>
// A --pack is a user-linked component pack (see packs.py). It is evaluated in a bare vm context against the SAME React, zod and
// defineComponent the browser runtime hands to packs (window.__HM.mods), so its zod schemas are enforced exactly as in the page.
const argv = process.argv.slice(2);
const packFiles = [];
let file;
for (let i = 0; i < argv.length; i++) { if (argv[i] === "--pack") packFiles.push(argv[++i]); else file = argv[i]; }
if (!file) { console.error("usage: validate.cjs [--pack FILE]... <file>"); process.exit(2); }
const src = fs.readFileSync(file, "utf8");
const problems = [];

const extraComponents = [];
const packChecks = []; // { names:Set, fn, label }
const inert = () => inertProxy;
const inertProxy = new Proxy(function () {}, { get: () => inertProxy, apply: () => inertProxy, construct: () => inertProxy });
for (const pf of packFiles) {
  const label = pf.split(/[\\/]/).pop();
  let text;
  try { text = fs.readFileSync(pf, "utf8"); } catch (e) { problems.push(`pack ${label} cannot be read: ${e.message}`); continue; }
  const registered = [];
  const win = {
    __HM: {
      mods: { react: React, "react/jsx-runtime": JsxRuntime, zod: Zod, "@openuidev/react-lang": { defineComponent, action, useTriggerAction, useIsQueryLoading } },
      register: (p) => registered.push(p),
    },
  };
  win.window = win;
  const sandbox = { window: win, document: inertProxy, navigator: inertProxy, matchMedia: inert, console: { log() {}, info() {}, warn() {}, error() {} } };
  try {
    vm.runInNewContext(text, sandbox, { filename: label, timeout: 3000 });
  } catch (e) { problems.push(`pack ${label} failed to load: ${e && e.message ? e.message : e}`); continue; }
  const declared = (() => {
    const m = text.match(/\/\*\s*hermes-openui-pack\b([\s\S]*?)\*\//);
    try { return m ? Object.keys(JSON.parse(m[1]).components || {}) : []; } catch { return []; }
  })();
  const actual = registered.flatMap((p) => (p.components || []).map((c) => c.name));
  const missing = declared.filter((n) => !actual.includes(n)), extra = actual.filter((n) => !declared.includes(n));
  if (missing.length) problems.push(`pack ${label}: the header lists ${missing.join(", ")} but the script does not register ${missing.length > 1 ? "them" : "it"}`);
  if (extra.length) problems.push(`pack ${label}: the script registers ${extra.join(", ")} but the header does not list ${extra.length > 1 ? "them" : "it"}`);
  for (const p of registered) {
    extraComponents.push(...(p.components || []));
    if (typeof p.validate === "function") packChecks.push({ names: new Set((p.components || []).map((c) => c.name)), fn: p.validate, label });
  }
}
if (problems.length) { console.log("OpenUI validation FAILED:\n- " + [...new Set(problems)].join("\n- ")); process.exit(1); }

const library = extraComponents.length ? createLibrary({ root: builtinLibrary.root, components: [...builtinComponents, ...extraComponents] }) : builtinLibrary;
const parser = createParser(library.toJSONSchema(), library.root);
const { root, meta } = parser.parse(src);
if (!root) problems.push("No renderable `root` — define `root = Stack([...])`.");
if (meta.incomplete) problems.push("Input looks truncated/incomplete (unbalanced brackets or quotes).");
for (const u of meta.unresolved) problems.push(`Reference \`${u}\` is used but never defined.`);
for (const o of meta.orphaned) problems.push(`\`${o}\` is defined but not reachable from root (it will not render) — add it to a parent's children.`);
// Cross-reference checks (ids/names that must match across components).
const walk = (n, fn) => { if (n && typeof n === "object") { if (n.typeName) fn(n); for (const v of Object.values(n.props ?? {})) (Array.isArray(v) ? v : [v]).forEach((c) => walk(c, fn)); } };
const refNames = (arr, key) => (Array.isArray(arr) ? arr.map((x) => x?.props?.[key]).filter((x) => typeof x === "string") : []);
const str = (v) => (v == null ? "" : String(v));
const list = (v) => (Array.isArray(v) ? v : []);
walk(root, (n) => {
  const p = n.props ?? {};
  for (const c of packChecks) {
    if (!c.names.has(n.typeName)) continue;
    try { for (const m of c.fn(n.typeName, p) || []) problems.push(String(m)); }
    catch (e) { problems.push(`pack ${c.label}: its validate hook threw on ${n.typeName}: ${e && e.message ? e.message : e}`); }
  }
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
  if (n.typeName === "InfraZone" && !list(p.nodes).length) problems.push(`InfraZone \`${str(p.name)}\` has no nodes (give it at least one InfraNode, or remove the zone).`);
  if (n.typeName === "SequenceDiagram") for (const m of checkSequence(p)) problems.push(m);
  if (n.typeName === "InfraMap") {
    const zones = list(p.zones).map((z) => z?.props ?? {});
    if (!zones.length) problems.push("InfraMap needs at least one InfraZone in `zones`.");
    const nodes = zones.flatMap((z) => list(z.nodes).map((x) => x?.props).filter(Boolean));
    const ids = nodes.map((x) => str(x.id));
    const labels = new Map(nodes.map((x) => [str(x.label).toLowerCase(), str(x.id)])); // lower-cased label -> id, to name the right id when a link uses a label
    const dup = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
    if (dup.length) problems.push(`InfraMap has duplicate node ids: ${dup.join(", ")} (every InfraNode id must be unique across all zones).`);
    for (const lk of list(p.links).map((l) => l?.props).filter(Boolean)) {
      for (const end of ["from", "to"]) {
        const id = str(lk[end]);
        if (ids.includes(id)) continue;
        const hint = labels.has(id.toLowerCase()) ? ` \`${id}\` is a label; the id is \`${labels.get(id.toLowerCase())}\`.` : "";
        problems.push(`InfraMap link uses unknown node id \`${id}\` in \`${end}\` (InfraLink takes InfraNode id strings, not variable names or labels; known ids: ${ids.join(", ")}).${hint}`);
      }
      if (str(lk.from) === str(lk.to) && ids.includes(str(lk.from))) problems.push(`InfraMap link from \`${str(lk.from)}\` to itself cannot be drawn.`);
    }
  }
});
for (const e of meta.errors) problems.push(`${e.component ?? ""}${e.statementId ? " in `" + e.statementId + "`" : ""}: ${e.message ?? JSON.stringify(e)}${e.hint ? " — " + e.hint : ""}`);
const uniq = [...new Set(problems)]; problems.length = 0; problems.push(...uniq);
if (problems.length) { console.log("OpenUI validation FAILED:\n- " + problems.join("\n- ")); process.exit(1); }
console.log(`OpenUI validation OK (${meta.statementCount} statements).`);
