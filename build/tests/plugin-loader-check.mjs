// Replays the desktop app's OWN loader checks against out/plugin.js: the import-specifier scanner and rewriter are
// extracted verbatim from apps/desktop/src/contrib/runtime-loader.ts (not re-implemented), with only sdkImportMap stubbed.
import fs from "node:fs";
import path from "node:path";
import { transform, build } from "esbuild";

const SRC = path.join(process.env.HOME, ".hermes/hermes-agent/apps/desktop/src/contrib/runtime-loader.ts");
const BUILD = path.resolve(import.meta.dirname, "..");
const plugin = process.argv[2] || path.join(BUILD, "../desktop/plugin.js");
const ts = fs.readFileSync(SRC, "utf8");
const a = ts.indexOf("// Matches the specifier of a static `from");
const b = ts.indexOf("export function unloadRuntimePlugin");
if (a < 0 || b < 0) throw new Error("loader anchors moved; update this check");
const body = ts.slice(a, b);
const stub = `const sdkImportMap = (): Record<string,string> => ({
  '@hermes/plugin-sdk': 'blob:sdk', 'react/jsx-dev-runtime': 'blob:jsxdev', 'react/jsx-runtime': 'blob:jsx', react: 'blob:react' });\n`;
const js = (await transform(stub + body + "\nexport { rewriteSpecifiers, unsupportedImports, importSpecifierRe, codeRanges, inCode };\n", { loader: "ts", format: "esm" })).code;
fs.mkdirSync(path.join(BUILD, "dist"), { recursive: true }); // a fresh clone has no dist/ until the first build
const tmp = path.join(BUILD, "dist/_loader-replica.mjs");
fs.writeFileSync(tmp, js);
const L = await import(tmp);
fs.rmSync(tmp);

const source = fs.readFileSync(plugin, "utf8");
const unsupported = L.unsupportedImports(source);
const rewritten = L.rewriteSpecifiers(source);
const specs = [...rewritten.matchAll(L.importSpecifierRe())].filter((m) => L.inCode(L.codeRanges(rewritten), m.index)).map((m) => m[3]);
// The loader's own regex is the thing that can miss a form (e.g. a space-less `import"react"`), so ask a real parser what imports the
// REWRITTEN file still has.
fs.writeFileSync(path.join(BUILD, "dist/_rewritten.mjs"), rewritten);
const seen = new Set();
let parseError = null;
await build({ entryPoints: [path.join(BUILD, "dist/_rewritten.mjs")], bundle: true, write: false, format: "esm", logLevel: "silent", absWorkingDir: BUILD,
  plugins: [{ name: "record-imports", setup(b) { b.onResolve({ filter: /.*/ }, (a) => { if (a.kind === "entry-point") return undefined; seen.add(a.path); return { path: a.path, external: true }; }); } }],
}).catch((e) => { parseError = String(e.errors?.[0]?.text || e).slice(0, 140); });
fs.rmSync(path.join(BUILD, "dist/_rewritten.mjs"), { force: true });
const fromReact = parseError ? ["(parse failed: " + parseError + ")"] : [...seen].filter((s) => !s.startsWith("blob:"));
console.log("plugin file:", path.relative(BUILD, plugin), (source.length / 1024).toFixed(0) + " KB");
console.log("unsupported import specifiers (the loader refuses the file if any):", unsupported.length ? unsupported : "none");
console.log("import specifiers in code after rewrite:", [...new Set(specs)].join(", "));
console.log("bare specifiers a real parser still finds after the rewrite:", fromReact.length ? fromReact : "none");
console.log("dynamic import() in code:", [...source.matchAll(/import\s*\(/g)].filter((m) => L.inCode(L.codeRanges(source), m.index)).length);
console.log("top-level await (would hit the 10 s eval timeout path):", /^\s*await\s/m.test(source) ? "possible" : "none found");
process.exit(unsupported.length || fromReact.length ? 1 : 0);
