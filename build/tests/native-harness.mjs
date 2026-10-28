// Builds ONE HTML page that shows the same widgets at several chat-column widths, drawn by the real desktop plugin against a
// stub SDK. usage (normally through tools/verify_native.py):
//   node tests/native-harness.mjs --plugin ../desktop/plugin.js --config cfg.json --out page.html [--theme dark|light] [--app-css FILE]
// cfg.json: { "widths": [360, 640], "widgets": [{ "name": "table", "source": "root = Stack([...])" }] }
// --app-css FILE inlines the Hermes Desktop stylesheet (without its @font-face rules, so the page stays offline) and puts every
// widget inside the wrapper classes the app puts around a message (see native-harness-entry.jsx), so the app's Tailwind
// Typography rules (`.prose`) and `overflow-wrap:anywhere` reach the widget the way they do in a chat.
// It needs the same node_modules as the build and adds no dependency.
import { build } from "esbuild";
import fs from "node:fs";
import path from "node:path";

const HERE = import.meta.dirname;
const arg = (name) => {
  const i = process.argv.indexOf("--" + name);
  if (i < 0 || !process.argv[i + 1]) throw new Error("missing --" + name);
  return path.resolve(process.argv[i + 1]);
};
const opt = (name) => {
  const i = process.argv.indexOf("--" + name);
  return i < 0 || !process.argv[i + 1] ? null : process.argv[i + 1];
};
const plugin = arg("plugin");
const cfg = JSON.parse(fs.readFileSync(arg("config"), "utf8"));
const theme = opt("theme") || "dark";
if (theme !== "dark" && theme !== "light") throw new Error("--theme must be dark or light");
const appCssFile = opt("app-css");
const appCss = appCssFile
  ? fs.readFileSync(path.resolve(appCssFile), "utf8").replace(/@font-face\s*\{[^}]*\}/g, "").replace(/<\/style/gi, "<\\/style")
  : "";
cfg.wrap = Boolean(appCssFile);

const r = await build({
  absWorkingDir: path.resolve(HERE, ".."),
  entryPoints: [path.join(HERE, "native-harness-entry.jsx")],
  bundle: true, write: false, format: "iife", target: "chrome120", jsx: "automatic", logLevel: "error", legalComments: "none",
  define: { "process.env.NODE_ENV": '"production"' },
  alias: { "native-plugin": plugin, "@hermes/plugin-sdk": path.join(HERE, "native-sdk-stub.js") },
  nodePaths: [path.resolve(HERE, "../node_modules")], // the plugin file sits outside build/, so it finds react here
});
const js = r.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");
const json = JSON.stringify(cfg).replace(/</g, "\\u003c");

// Theme tokens are the harness's approximation (the values tools/shoot.py uses), not the app's own palette.
const TOKENS = {
  dark: { text: "#e8eaed", muted: "#9aa0a6", accent: "#5B9CF6", stroke: "rgba(255,255,255,.16)", editor: "#202124", bg: "#17181a", outline: "rgba(255,255,255,.28)" },
  light: { text: "#1f2328", muted: "#59636e", accent: "#0969da", stroke: "rgba(31,35,40,.16)", editor: "#f6f8fa", bg: "#ffffff", outline: "rgba(31,35,40,.28)" },
}[theme];
const tokenCss = `:root{--ui-text-primary:${TOKENS.text};--ui-text-tertiary:${TOKENS.muted};--ui-accent:${TOKENS.accent};--ui-stroke-tertiary:${TOKENS.stroke};--ui-bg-editor:${TOKENS.editor};color-scheme:${theme}}`;
const layoutCss = `
#page{display:flex;flex-wrap:wrap;gap:0 24px;align-items:flex-start}
.col{margin-bottom:28px}.col h2{margin:8px 0;font-size:16px;color:${TOKENS.accent}}
.cell{margin-bottom:18px}.label{font:11px monospace;color:${TOKENS.muted};margin-bottom:3px}
.slot{box-sizing:border-box;outline:1px dashed ${TOKENS.outline}}`;
// The app's own stylesheet fixes html, body and #root to the window height and hides overflow; a tall test page needs it undone.
// Its font (size, line height) is left alone on purpose, so the widgets see the app's text metrics.
const css = appCss
  ? `${appCss}\n${tokenCss}\nhtml,body,#root{height:auto;overflow:visible}html,body{margin:0;background:${TOKENS.bg};color:${TOKENS.text}}${layoutCss}`
  : `\n${tokenCss}\nhtml,body{margin:0;background:${TOKENS.bg};color:${TOKENS.text};font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}${layoutCss}`;
const html = `<!doctype html><html data-hermes-mode="${theme}"><head><meta charset="utf-8"><title>native layout</title><style>${css}</style></head>
<body><div id="page"></div><div id="gate" class="mount"></div>
<script>window.__CFG=${json}</script><script>${js}</script></body></html>`;
fs.writeFileSync(arg("out"), html);
console.log("wrote " + path.basename(arg("out")) + " (" + (html.length / 1024).toFixed(0) + " KB)");
