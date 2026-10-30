// Rebuilds the skill's generated files after editing src/. Needs Node + `npm install` in this directory.
//   assets/core.js.gz            browser engine: React + react-lang + zod + theme + always-on components
//   assets/packs/<name>.js.gz    one file per optional pack (charts, diagrams, map, text), built against the core
//   assets/packs.json            manifest the plugin's page builder reads: file sizes and which component lives in which pack
//   assets/validate.cjs          Node validator for model-written OpenUI Lang (knows EVERY component)
//   assets/components.md         component/syntax reference for the model (generated from the same full library)
// Why gzip: the desktop reads preview files through a 512 KiB bridge and loads them as a sandboxed srcdoc
// (no sibling assets), so each widget ships its runtime inside the page as base64 gzip and inflates it in the
// browser. Why packs: a widget then pays only for the optional components it uses (render.py picks them).
// OpenUI's lang-core ships install-time and (opt-in) runtime telemetry to PostHog. This skill is local-only:
// opt out for the build process and bake the opt-out into the generated validator, whatever env it runs under.
process.env.DO_NOT_TRACK = "1";
process.env.OPENUI_TELEMETRY_DISABLED = "1";
delete process.env.OPENUI_RUNTIME_TELEMETRY_ENABLED;
const NO_TELEMETRY_BANNER =
  'process.env.DO_NOT_TRACK="1";process.env.OPENUI_TELEMETRY_DISABLED="1";delete process.env.OPENUI_RUNTIME_TELEMETRY_ENABLED;';

import { build } from "esbuild";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const REPO = path.resolve(import.meta.dirname, "..");
const define = { "process.env.NODE_ENV": '"production"' };
const kb = (n) => (n / 1024).toFixed(0) + " KB";
const gzip = (b) => zlib.gzipSync(b, { level: 9 });
// Hash the UNCOMPRESSED bundle: the gzip bytes depend on the zlib build (Node versions differ by ~1 KB), the content does not.
const sha256 = (b) => crypto.createHash("sha256").update(b).digest("hex");

// react-ui resolves icons through ~1k lazy lucide imports we never use (widgets have no Icon component).
const stubIcons = {
  name: "stub-icons",
  setup(b) {
    b.onResolve({ filter: /lucideDynamicImports/ }, () => ({ path: "stub-icons", namespace: "stub" }));
    b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ contents: "export default {};", loader: "js" }));
  },
};
// Node-side tools only need the chart SCHEMAS, not the d3/SVG renderers: stub the renderer barrel.
const stubChartRenderers = {
  name: "stub-chart-renderers",
  setup(b) {
    b.onResolve({ filter: /components\/Charts$/ }, () => ({ path: "chart-renderers", namespace: "stub-charts" }));
    b.onLoad({ filter: /.*/, namespace: "stub-charts" }, () => ({
      contents: ["LineChartCondensed", "AreaChartCondensed", "PieChart", "RadarChart"].map((n) => `export const ${n} = () => null;`).join("\n"),
      loader: "js",
    }));
  },
};
// Packs must not bundle their own React / zod / react-lang: they take the core's instances from window.__HM.mods.
// (lang-core is deliberately absent: exposing it would pull its dormant telemetry into the core; a pack that imports
// it trips the guard below, which is the cue to rethink, not to share it.)
const SHARED = ["react", "react/jsx-runtime", "react-dom", "react-dom/client", "zod", "zod/v4", "@openuidev/react-lang"];
const MOD_FOR = { zod: "zod", "zod/v4": "zod" };
// Upstream modules that hold React context must also be the core's instance (a pack's own copy of the ThemeProvider
// would give charts the default palette instead of the Hermes one). Matched on the RESOLVED path, so any import
// shape ("../ThemeProvider", ".../ThemeProvider/index.js") lands on the same shared module.
// The Tooltip definition is another one: Dag, Erd, InfraMap and SequenceDiagram (three packs) type their `tooltips` with it, and the parser matches
// a component to a slot by the identity of its schema object, so a pack that bundled its own copy would silently drop every Tooltip in the page.
// The interaction module (tooltips.jsx, with its React context) and the code highlighter it uses are shared too: the core carries them once for the
// whole page (Table, Metric, BarChart and Image are core components), so a pack that draws a tooltip or a code block takes them from there.
const SHARED_FILES = [
  [/react-ui\/dist\/components\/ThemeProvider\/index\.js$/, "react-ui/ThemeProvider"],
  [/src\/components\/tooltip-schema\.js$/, "hermes-openui/tooltip-schema"],
  [/src\/components\/tooltips\.jsx$/, "hermes-openui/tooltips"],
  [/src\/components\/code\.jsx$/, "hermes-openui/code"],
];
const sharedFromCore = {
  name: "shared-from-core",
  setup(b) {
    b.onResolve({ filter: /.*/ }, async (a) => {
      if (SHARED.includes(a.path)) return { path: a.path, namespace: "hm-shared" };
      if (a.pluginData?.skipShared || a.namespace === "hm-shared" || a.kind === "entry-point") return undefined;
      const r = await b.resolve(a.path, { resolveDir: a.resolveDir, kind: a.kind, importer: a.importer, pluginData: { skipShared: true } });
      const hit = r.path && SHARED_FILES.find(([re]) => re.test(r.path));
      return hit ? { path: hit[1], namespace: "hm-shared" } : undefined;
    });
    b.onLoad({ filter: /.*/, namespace: "hm-shared" }, (a) => ({
      contents: `module.exports = window.__HM.mods[${JSON.stringify(MOD_FOR[a.path] ?? a.path)}];`,
      loader: "js",
    }));
  },
};
const browser = { bundle: true, minify: true, format: "iife", target: "chrome120", jsx: "automatic", define, legalComments: "none", loader: { ".css": "text" }, write: false, metafile: true, logLevel: "error" };
// Privacy guard: the browser files must contain no network code (OpenUI ships opt-in telemetry in lang-core).
const NETWORK = /fetch\(|XMLHttpRequest|sendBeacon|WebSocket\(|EventSource\(|posthog|cloudfront/;
const assertNoNetwork = (label, bytes) => {
  const m = Buffer.from(bytes).toString("utf8").match(NETWORK);
  if (m) throw new Error(`${label} contains network code (${m[0]}): see references/extending-runtime.md, Privacy`);
};
// Which react-lang names the core shares with packs (single source: the ReactLangShared object in src/core.jsx).
const sharedLang = fs.readFileSync("src/core.jsx", "utf8").match(/const ReactLangShared = \{([^}]*)\}/)[1].split(",").map((x) => x.trim()).filter(Boolean);
function assertPackLangImports(name, files) {
  const used = new Set();
  for (const f of files) {
    if (!fs.existsSync(f)) continue;
    const src = fs.readFileSync(f, "utf8");
    for (const m of src.matchAll(/import\s*\{([^}]*)\}\s*from\s*["']@openuidev\/react-lang["']/g)) {
      m[1].split(",").map((x) => x.trim().split(/\s+as\s+/)[0]).filter(Boolean).forEach((n) => used.add(n));
    }
    if (/import\s+(\*\s+as\s+\w+|\w+)\s*(,\s*\{[^}]*\})?\s*from\s*["']@openuidev\/react-lang["']/.test(src)) {
      throw new Error(`pack "${name}": ${f} uses a default/namespace import of react-lang`);
    }
  }
  const extra = [...used].filter((n) => !sharedLang.includes(n));
  if (extra.length) throw new Error(`pack "${name}" imports react-lang export(s) the core does not share: ${extra.join(", ")} (add them to ReactLangShared in src/core.jsx)`);
}
const inputsOf = (r) => Object.keys(Object.values(r.metafile.outputs)[0].inputs);

fs.mkdirSync("dist", { recursive: true });
fs.mkdirSync(path.join(REPO, "assets/packs"), { recursive: true });
for (const f of fs.readdirSync(path.join(REPO, "assets/packs"))) fs.rmSync(path.join(REPO, "assets/packs", f));

// 1. Browser core
const core = await build({ ...browser, entryPoints: ["src/core.jsx"], plugins: [stubIcons] });
const coreBytes = core.outputFiles[0].contents;
assertNoNetwork("core", coreBytes);
fs.writeFileSync("dist/core.js", coreBytes);
const coreGz = gzip(coreBytes);
fs.writeFileSync(path.join(REPO, "assets/core.js.gz"), coreGz);
const coreInputs = new Set(inputsOf(core));

// 2. Browser packs (one per src/packs/*.jsx)
const packNames = fs.readdirSync("src/packs").filter((f) => f.endsWith(".jsx")).map((f) => f.slice(0, -4)).sort();
const packInfo = {};
for (const name of packNames) {
  const r = await build({
    ...browser,
    stdin: { contents: `import { pack } from "./packs/${name}.jsx"; window.__HM.register(pack);`, resolveDir: path.resolve("src"), loader: "jsx", sourcefile: `pack-${name}.jsx` },
    plugins: [stubIcons, sharedFromCore],
  });
  const bytes = r.outputFiles[0].contents;
  assertPackLangImports(name, inputsOf(r));
  // Guard: a pack that bundled its own copy of a shared dependency would break react-lang's context (and bloat).
  const bad = inputsOf(r).filter((f) => /node_modules\/(react|react-dom|zod|@openuidev\/react-lang|@openuidev\/lang-core)\//.test(f));
  if (bad.length) throw new Error(`pack "${name}" bundles shared deps: ${bad.slice(0, 3).join(", ")}`);
  // Report modules duplicated between the core and this pack (harmless for plain data, a bug for React context).
  const sizes = Object.values(r.metafile.outputs)[0].inputs;
  const dup = inputsOf(r).filter((f) => coreInputs.has(f) && !/src\/theme\.js$/.test(f) && sizes[f].bytesInOutput > 1000);
  if (dup.length) console.warn(`  note: pack "${name}" duplicates ${dup.length} core module(s): ${dup.map((f) => f.split("node_modules/").pop()).slice(0, 4).join(", ")}`);
  assertNoNetwork(`pack ${name}`, bytes);
  fs.writeFileSync(`dist/pack-${name}.js`, bytes);
  const gz = gzip(bytes);
  fs.writeFileSync(path.join(REPO, "assets/packs", `${name}.js.gz`), gz);
  packInfo[name] = { file: `packs/${name}.js.gz`, raw: bytes.length, gz: gz.length, sha256: sha256(bytes) };
}

// 3. Node validator (full library)
await build({
  entryPoints: ["src/validate.mjs"], bundle: true, minify: true, platform: "node", format: "cjs", target: "node18", jsx: "automatic",
  define, legalComments: "none", loader: { ".css": "text" }, plugins: [stubChartRenderers], banner: { js: NO_TELEMETRY_BANNER },
  outfile: path.join(REPO, "assets/validate.cjs"), logLevel: "error",
});

// 4. Prompt reference + component->pack manifest (generated from the same full library, so they cannot drift)
const nodeScript = (entry, out) =>
  build({ entryPoints: [entry], bundle: true, platform: "node", format: "esm", jsx: "automatic", packages: "external", loader: { ".css": "text" }, plugins: [stubChartRenderers], outfile: out, logLevel: "error" });
await nodeScript("src/gen-prompt.mjs", "dist/gen-prompt.mjs");
fs.writeFileSync(path.join(REPO, "assets/components.md"), execFileSync("node", ["dist/gen-prompt.mjs"], { encoding: "utf8" }));
await nodeScript("src/gen-manifest.mjs", "dist/gen-manifest.mjs");
const names = JSON.parse(execFileSync("node", ["dist/gen-manifest.mjs"], { encoding: "utf8" }));
if (JSON.stringify(Object.keys(names.packs).sort()) !== JSON.stringify(packNames)) throw new Error(`packs/index.js (${Object.keys(names.packs)}) and src/packs/*.jsx (${packNames}) disagree`);
const components = {};
for (const [pack, list] of Object.entries(names.packs)) for (const c of list) components[c] = pack;
for (const [pack, info] of Object.entries(packInfo)) info.components = names.packs[pack];
const manifest = { core: { file: "core.js.gz", raw: coreBytes.length, gz: coreGz.length, sha256: sha256(coreBytes), components: names.core }, packs: packInfo, components };
fs.writeFileSync(path.join(REPO, "assets/packs.json"), JSON.stringify(manifest, null, 1) + "\n");

const page = (gz) => kb((gz * 4) / 3);
console.log(`core        ${kb(coreBytes.length)} -> ${kb(coreGz.length)} gz (page ~ ${page(coreGz.length)} + HTML shell + content; hard cap 512 KB)`);
for (const [n, i] of Object.entries(packInfo)) console.log(`pack ${n.padEnd(9)} ${kb(i.raw)} -> ${kb(i.gz)} gz (+${page(i.gz)} page)  [${i.components.join(", ")}]`);
console.log("validate.cjs", kb(fs.statSync(path.join(REPO, "assets/validate.cjs")).size), "| components.md", kb(fs.statSync(path.join(REPO, "assets/components.md")).size));
