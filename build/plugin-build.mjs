// Build the OPTIONAL desktop plugin (see references/extending-runtime.md > Desktop plugin spike): ONE minified ESM file whose
// only imports are the ones the app's loader resolves. usage: node plugin-build.mjs  -> ../desktop/plugin.js
// OPENUI_PROBE=1 builds dist/plugin.probe.js (verification only: error-level console lines so desktop.log shows them).
// Then: node tests/plugin-loader-check.mjs   (replays the app's own import rewrite and parses the result)
process.env.DO_NOT_TRACK = "1";
process.env.OPENUI_TELEMETRY_DISABLED = "1";
delete process.env.OPENUI_RUNTIME_TELEMETRY_ENABLED;
import { build } from "esbuild";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const ROOT = import.meta.dirname;
const ALLOWED = ["react", "react/jsx-runtime", "react/jsx-dev-runtime", "@hermes/plugin-sdk"];
const stubIcons = {
  name: "stub-icons",
  setup(b) {
    b.onResolve({ filter: /lucideDynamicImports/ }, () => ({ path: "stub-icons", namespace: "stub" }));
    b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ contents: "export default {};", loader: "js" }));
  },
};
// react-dom is not importable by a disk plugin: portals/flushSync get the inline shim.
const reactDomShim = {
  name: "react-dom-shim",
  setup(b) {
    b.onResolve({ filter: /^react-dom(\/.*)?$/ }, () => ({ path: path.join(ROOT, "shims/react-dom.js") }));
  },
};
// Mark the allowed externals side-effect free. Otherwise esbuild keeps a bare `import"react"` for every module that only
// needed React for JSX, and the app loader (which rewrites `import` + WHITESPACE + quote only) leaves that one un-rewritten:
// the browser then refuses the whole file with 'Failed to resolve module specifier "react"'.
const externalsPure = {
  name: "externals-pure",
  setup(b) {
    b.onResolve({ filter: /^(react|react\/jsx-runtime|react\/jsx-dev-runtime|@hermes\/plugin-sdk)$/ }, (a) => ({ path: a.path, external: true, sideEffects: false }));
  },
};

const r = await build({
  absWorkingDir: ROOT,
  entryPoints: ["src/plugin/plugin.jsx"],
  bundle: true, minify: true, format: "esm", target: "chrome120", jsx: "automatic", legalComments: "none",
  define: { "process.env.NODE_ENV": '"production"', __PROBE__: process.env.OPENUI_PROBE ? "true" : "false" },
  loader: { ".css": "text" },
  external: ALLOWED,
  // Some bundled CommonJS deps call require("react"): esbuild's helper throws in a browser module. Hand them the HOST's
  // React instead (these two import statements are rewritten by the app loader like any other).
  banner: {
    js:
      'import*as __hr from"react";import*as __hj from"react/jsx-runtime";' +
      'var require=function(i){if(i==="react")return __hr;if(i==="react/jsx-runtime")return __hj;throw Error("Dynamic require of "+i+" is not supported")};',
  },
  plugins: [externalsPure, stubIcons, reactDomShim],
  write: false, metafile: true, logLevel: "error",
});
const bytes = r.outputFiles[0].contents;
let text = Buffer.from(bytes).toString("utf8");
text = text.replace(/import(["'])(react|react\/jsx-runtime|react\/jsx-dev-runtime|@hermes\/plugin-sdk)\1/g, "import $1$2$1");

// Privacy guard (the plugin runs with FULL app authority, so this matters more than for the sandboxed widget).
const net = text.match(/fetch\(|XMLHttpRequest|sendBeacon|WebSocket\(|EventSource\(|posthog|cloudfront/);
if (net) throw new Error("plugin bundle contains network code: " + net[0]);

fs.mkdirSync(path.join(ROOT, "dist"), { recursive: true });
fs.mkdirSync(path.join(ROOT, "../desktop"), { recursive: true });
const OUT = process.env.OPENUI_PROBE ? "dist/plugin.probe.js" : "../desktop/plugin.js";
fs.writeFileSync(path.join(ROOT, OUT), text);
// The package list the bundle really contains (build/scripts/notices.mjs turns it into THIRD_PARTY_NOTICES.md).
if (!process.env.OPENUI_PROBE) fs.writeFileSync(path.join(ROOT, "dist/bundled-inputs.json"), JSON.stringify(Object.keys(r.metafile.inputs)));
const gz = zlib.gzipSync(Buffer.from(text), { level: 9 }).length;

// Composition by package (raw minified bytes).
const by = {};
for (const [f, v] of Object.entries(Object.values(r.metafile.outputs)[0].inputs)) {
  const m = f.match(/node_modules\/((?:@[^/]+\/)?[^/]+)/);
  let k = m ? m[1] : "our src";
  if (k === "@openuidev/react-ui") k = /Charts|charts/.test(f) ? "@openuidev/react-ui (charts)" : "@openuidev/react-ui (theme)";
  by[k] = (by[k] || 0) + v.bytesInOutput;
}
const kb = (n) => (n / 1024).toFixed(0) + " KB";
console.log(`${OUT}  ${kb(Buffer.byteLength(text))} raw  ${kb(gz)} gzip`);
for (const [k, v] of Object.entries(by).sort((a, b) => b[1] - a[1]).slice(0, 8)) console.log("  ", k.padEnd(34), kb(v).padStart(7));
const dom = Object.keys(r.metafile.inputs).filter((f) => /node_modules\/react-dom\//.test(f));
console.log("real react-dom bundled:", dom.length ? "YES (bug)" : "no (shimmed)");
