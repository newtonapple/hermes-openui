// Page script of the native layout harness (see native-harness.mjs). It registers the REAL desktop/plugin.js against a stub
// SDK, then draws the same widgets through the plugin's own directive `render({attrs:{file}})` inside slots of several widths,
// the way the app draws `::openui{file=...}` in a chat column. `measureAll()` reports the layout of every widget.
import { createRoot } from "react-dom/client";
import plugin from "native-plugin";

const cfg = window.__CFG; // { widths: [...], widgets: [{ name, source }], wrap: bool }
const sources = Object.fromEntries(cfg.widgets.map((w) => [w.name, w.source]));
window.hermesDesktop = {
  readFileText: async (file) => {
    const text = sources[file.split("/").pop().replace(/\.oui$/, "")];
    return { text, byteSize: text.length, binary: false, truncated: false };
  },
};

let directive = null;
plugin.register({ register: (d) => (directive = d) });
const render = directive.data.render;

// With --app-css the widget sits where the app puts it: inside the message's wrapper elements. Classes are the ones in the app
// source (thread/response-group.tsx, thread/assistant-message.tsx, markdown-text.tsx; the Streamdown div per its styles.css
// comment) so the compiled stylesheet's rules bind: `.prose` margins and table width, `overflow-wrap:anywhere`, the clipping
// `overflow-hidden`. The font-size/leading utilities, the `prose-*` modifiers and the message indent are NOT copied.
const APP_WRAPPERS = [
  ["flex min-w-0 flex-col", {}],
  ["group flex w-full min-w-0 max-w-full flex-col gap-0 self-start overflow-hidden", { "data-slot": "aui_assistant-message-root" }],
  ["wrap-anywhere min-w-0 max-w-full overflow-hidden", { "data-slot": "aui_assistant-message-content" }],
  ["aui-md prose w-full min-w-0 max-w-none overflow-hidden", {}],
  ["space-y-4 whitespace-normal", {}],
];
// The element the plugin's root is a direct child of: the slot itself, or the innermost wrapper.
function hostOf(slot) {
  let el = slot;
  if (cfg.wrap) {
    for (const [cls, attrs] of APP_WRAPPERS) {
      const d = document.createElement("div");
      d.className = cls;
      for (const k of Object.keys(attrs)) d.setAttribute(k, attrs[k]);
      el.appendChild(d);
      el = d;
    }
  }
  el.setAttribute("data-host", "");
  return el;
}

const page = document.getElementById("page");
const slots = [];
for (const width of cfg.widths) {
  const col = document.createElement("section");
  col.className = "col";
  col.innerHTML = `<h2>chat column ${width} px</h2>`;
  for (const w of cfg.widgets) {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.dataset.widget = w.name;
    cell.innerHTML = `<div class="label">${w.name}</div>`;
    const slot = document.createElement("div");
    slot.className = "slot";
    slot.style.width = width + "px";
    cell.appendChild(slot);
    col.appendChild(cell);
    slots.push({ slot, host: hostOf(slot), name: w.name });
  }
  page.appendChild(col);
}
for (const { host, name } of slots) createRoot(host).render(render({ attrs: { file: "/h/widgets/" + name + ".oui" } }));

// shoot.py waits for every `.mount` to hold a child: the gate gets one once each slot drew its widget.
const gate = document.getElementById("gate");
const wait = setInterval(() => {
  if (slots.every(({ host }) => host.querySelector("[data-hermes-openui-widget]"))) {
    clearInterval(wait);
    gate.appendChild(document.createElement("span")); // shoot.py counts element children
  }
}, 100);

const SCROLLABLE = new Set(["auto", "scroll"]);
const describe = (el) => el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : "");
window.measureAll = () =>
  [...document.querySelectorAll(".cell")].map((cell) => {
    const host = cell.querySelector("[data-host]"); // the widget's parent: the column itself, or the app's innermost wrapper
    const root = host.querySelector("[data-hermes-openui-widget]");
    const row = { widget: cell.dataset.widget, container: host.clientWidth };
    if (!root) return { ...row, error: "no widget drawn: " + host.textContent.slice(0, 80) };
    const box = root.getBoundingClientRect();
    const scrollers = [];
    const clipped = [];
    const media = [];
    for (const el of root.querySelectorAll("*")) {
      const over = el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1;
      if (over) {
        const ox = getComputedStyle(el).overflowX;
        if (SCROLLABLE.has(ox)) scrollers.push(describe(el));
        else if (ox === "hidden" || ox === "clip") clipped.push(describe(el));
      }
      const tag = el.tagName.toLowerCase();
      const r = el.getBoundingClientRect();
      if ((tag === "svg" && r.width >= 100) || tag === "img" || tag === "canvas" || tag === "table")
        media.push({ tag, w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left - box.left), nat: tag === "img" ? el.naturalWidth : undefined, select: tag === "svg" ? getComputedStyle(el).userSelect : undefined });
    }
    // Elements with a tooltip: what the app's stylesheet leaves selectable. `picked` is what a real Range over the element returns.
    const pick = (el) => {
      const sel = window.getSelection(), range = document.createRange();
      sel.removeAllRanges();
      range.selectNodeContents(el);
      sel.addRange(range);
      const text = String(sel);
      sel.removeAllRanges();
      return text;
    };
    const tipSelect = [];
    const addTip = (name, el) => {
      if (!el) return void tipSelect.push({ name: name + " (not drawn)", select: "missing", text: "", picked: "" });
      tipSelect.push({ name, select: getComputedStyle(el).userSelect, text: el.textContent.trim(), picked: pick(el).trim() });
    };
    if (root.querySelector("[data-tip]")) {
      addTip("a table cell with a tooltip", root.querySelector('td[data-tip="cell:1.service"]'));
      addTip("a table header with a tooltip", root.querySelector('th[data-tip="col:status"]'));
      addTip("a cell of a row with a tooltip", root.querySelector('tr[data-tip="row:2"] td'));
      addTip("a metric tile with a tooltip", root.querySelector('div[data-tip="Error rate"]'));
      addTip("a metric value with a tooltip", root.querySelector('div[data-tip="Error rate"] > div:nth-child(2)'));
      addTip("a bar with a tooltip", root.querySelector('div[data-tip="api"]'));
      addTip("a bar label with a tooltip", root.querySelector('div[data-tip="api"] > div:last-of-type'));
      const pin = root.querySelector('g[data-tip="web"] text'); // an svg element: the range covers its text node
      addTip("a map pin label with a tooltip", pin);
    }
    return {
      ...row,
      tipSelect,
      w: Math.round(box.width),
      h: Math.round(box.height),
      rootOverflow: root.scrollWidth > root.clientWidth + 1,
      slotOverflow: host.scrollWidth > host.clientWidth + 1,
      wrap: getComputedStyle(root).overflowWrap, // the preview page has "normal"; the app's message text has "anywhere"
      cellWrap: (() => { const c = root.querySelector("td,th"); return c ? getComputedStyle(c).overflowWrap : ""; })(),
      scrollers,
      clipped,
      media: media.slice(0, 3),
    };
  });
