// Notes (native desktop mode only): the user leaves notes for the agent on what a widget shows, by clicking an item or selecting text,
// batches them in a tray under the widget and drafts them into the chat's message box. Nothing is sent: the only outward calls are
// host.composer.insertText (on the user's click on the primary button) and host.composer.focus. The pure parts (message, limits, sanitizer,
// keys, store) are in components/notes-core.js. Preview pages and exported pages carry none of this.
//
// How a widget is read: withIds() wraps every component in a display:contents element that carries data-oui-id (the source variable name,
// react-lang's statementId) and data-oui-type. Items inside a component carry data-oui-k (the Tooltip target key), data-oui-label and
// sometimes data-oui-what (tooltips.jsx). The controller below only reads those attributes and draws overlays: no change inside a component
// except tabindex on the items in notes mode, which it removes on leaving.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { host } from "@hermes/plugin-sdk";
import { copyText } from "../components/code.jsx";
import {
  NOTE_LIMITS, NO_META, isNoteable, createStore, addNote, updateNote, removeNote, collapse, cleanQuote, hoverName, plainWhere, fallbackId, hashText, isStale,
  numbersFor, settleNumbers, markDrafted, planDraft, buttonLabel, addedSentence,
} from "../components/notes-core.js";

const store = createStore(() => window.sessionStorage);
const UI = "[data-oui-notes-ui]";
const HL = "oui-note"; // the CSS Custom Highlight name (NATIVE_CSS has the ::highlight rule)
const HLP = "oui-note-pending"; // the words picked for a note that is not saved yet (a lighter tint)
const HALF = "Save or cancel this note first.";
const LIMIT_MSG = NOTE_LIMITS.notes + " notes is the most per widget.";
const PIN = 18;
const NO_WRAP = ["Stack", "Card", "TabItem"]; // containers: never wrapped, never targets
const inUi = (t) => !!(t && t.closest && t.closest(UI));
const elOf = (n) => (n && n.nodeType === 1 ? n : n && n.parentElement);
const fmt = (n) => n.toLocaleString("en-US");

/* ------------------------------ ids on the components ------------------------------ */
// Wraps a component's renderer: its output sits in <div style="display:contents" data-oui-id data-oui-type>. A component that draws
// nothing (a data part such as DagNode) still returns null. The wrapper has no box, so layout is the same (tools/verify_native.py).
export function withIds(list) {
  return list.map((c) => {
    const inner = c.component;
    if (typeof inner !== "function" || NO_WRAP.includes(c.name)) return c;
    const Marked = (p) => {
      const out = inner(p);
      if (out == null || out === false) return null;
      return <div style={{ display: "contents" }} data-oui-id={p.statementId || undefined} data-oui-type={c.name}>{out}</div>;
    };
    return { ...c, component: Marked };
  });
}

/* ------------------------------ which composer ------------------------------ */
// The app marks every chat surface with data-composer-target: "main" (the primary chat) or "tile:<stored session id>" (a split view or tile).
// insertText(null, ...) means "the composer the user focused last", which can be the OTHER pane. So the widget names its own chat:
//   tile:<id> -> that id (the SDK routes a stored id to that tile and fails closed when no tile shows it)
//   main      -> the runtime id of the session the primary shows (host.state.activeSessionId); "new" for a fresh draft with no session yet
//   anything else (no marker found, or no state in the SDK) -> null, as before.
export function composerAddress(root) {
  const t = root && root.closest ? root.closest("[data-composer-target]") : null;
  const v = t && t.dataset ? t.dataset.composerTarget || "" : "";
  if (v.indexOf("tile:") === 0 && v.length > 5) return v.slice(5);
  if (v === "main") {
    try {
      const a = host && host.state && host.state.activeSessionId;
      if (a && typeof a.get === "function") {
        const id = a.get();
        return typeof id === "string" && id.trim() ? id : "new";
      }
    } catch (e) {}
  }
  return null;
}

/* ------------------------------ reading the DOM ------------------------------ */
const typeOf = (w) => w.getAttribute("data-oui-type");
function compOf(node, root) {
  let el = elOf(node);
  while (el && root.contains(el)) {
    const w = el.closest("[data-oui-type]");
    if (!w || !root.contains(w)) return null;
    const type = typeOf(w);
    if (isNoteable(type)) return w;
    if (type === "Button" || type === "Choice") return null; // not noted
    el = w.parentElement;
  }
  return null;
}
function describeComp(w, root) {
  const type = typeOf(w);
  let id = w.getAttribute("data-oui-id"), unnamed = false;
  if (!id) {
    unnamed = true;
    id = fallbackId(type, Array.from(root.querySelectorAll('[data-oui-type="' + type + '"]')).indexOf(w) + 1);
  }
  const tabs = w.parentElement && w.parentElement.closest('[data-oui-type="Tabs"]');
  const tab = tabs && tabs.firstElementChild ? tabs.firstElementChild.getAttribute("data-oui-tab") || "" : "";
  // "2/3": the second of three components of this type (the tray says "Text, 2nd of 3"); empty when the type occurs once
  const same = Array.from(root.querySelectorAll('[data-oui-type="' + type + '"]'));
  return { cid: id, ctype: type, unnamed, tab, pos: same.length > 1 ? same.indexOf(w) + 1 + "/" + same.length : "" };
}
function itemOf(node, w, shift) {
  const el = elOf(node);
  let item = el && el.closest ? el.closest("[data-oui-k]") : null;
  if (item && shift && item.parentElement) item = item.parentElement.closest("[data-oui-k]");
  return item && w.contains(item) ? item : null;
}
function targetAt(node, root, shift) {
  const w = compOf(node, root);
  if (!w) return null;
  const comp = describeComp(w, root);
  const item = itemOf(node, w, shift);
  const key = item ? item.getAttribute("data-oui-k") || "" : "";
  const what = item ? item.getAttribute("data-oui-what") || "" : "";
  const label = item ? item.getAttribute("data-oui-label") || "" : "";
  const cell = item && /^cell:/.test(key) ? item.textContent || "" : ""; // what a table cell holds (the message quotes it for an item note)
  return { w, el: item || w, ...comp, key, what, label, cell, name: hoverName(comp.ctype, key, what, label, comp.pos) };
}
// The component for a stored note, now. Unnamed ones are "Type#n".
function findComp(root, n) {
  try {
    if (n.unnamed) {
      const m = /^(.*)#(\d+)$/.exec(n.cid);
      return m && m[1] === n.ctype ? Array.from(root.querySelectorAll('[data-oui-type="' + m[1] + '"]'))[Number(m[2]) - 1] || null : null;
    }
    // by id AND type: a component of another type that took over the name is not the one the note was about
    return Array.from(root.querySelectorAll("[data-oui-id]")).find((w) => w.getAttribute("data-oui-id") === n.cid && typeOf(w) === n.ctype) || null;
  } catch (e) {
    return null;
  }
}
const findItem = (w, key) => Array.from(w.querySelectorAll("[data-oui-k]")).find((e) => e.getAttribute("data-oui-k") === key) || null;
function rectOf(el) {
  if (!el.hasAttribute("data-oui-type")) return el.getBoundingClientRect();
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  for (const c of Array.from(el.children)) {
    const q = c.getBoundingClientRect();
    if (!q.width && !q.height) continue;
    l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom);
  }
  return l === Infinity ? el.getBoundingClientRect() : { left: l, top: t, right: r, bottom: b, width: r - l, height: b - t };
}
const rel = (q, R) => ({ x: q.left - R.left, y: q.top - R.top, w: q.width, h: q.height });

// The text of a component with whitespace collapsed like collapse() does, and where each character lives, so a quote can be found again
// after React redrew the text (a Range does not survive that).
function textMap(w) {
  const walker = document.createTreeWalker(w, NodeFilter.SHOW_TEXT);
  let s = "", last = true;
  const map = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n.nodeValue;
    for (let i = 0; i < t.length; i++) {
      const ch = t[i];
      if (/\p{Cf}/u.test(ch) || /[^\P{Cc}\t\n\r]/u.test(ch)) continue;
      if (/\s/.test(ch)) {
        if (!last) { s += " "; map.push([n, i]); last = true; }
      } else { s += ch; map.push([n, i]); last = false; }
    }
  }
  return { s, map };
}
function findRanges(w, anchor) {
  const out = [];
  if (!anchor) return out;
  const { s, map } = textMap(w);
  for (let at = s.indexOf(anchor); at >= 0; at = s.indexOf(anchor, at + 1)) {
    const a = map[at], z = map[at + anchor.length - 1];
    if (!a || !z) break;
    const r = document.createRange();
    try { r.setStart(a[0], a[1]); r.setEnd(z[0], z[1] + 1); out.push(r); } catch (e) {}
  }
  return out;
}
function lineSpan(w, range) {
  const code = w.querySelector("pre code");
  if (!code || !code.contains(range.startContainer)) return "";
  const upTo = (node, off) => {
    const r = document.createRange();
    r.setStart(code, 0);
    r.setEnd(node, off);
    return (String(r).match(/\n/g) || []).length + 1;
  };
  const a = upTo(range.startContainer, range.startOffset);
  // The last line is a + the line breaks inside the words; a selection that ends right after a line break stops at the end of the line
  // before it (it must not count the empty start of the next one).
  let t = String(range);
  if (t.endsWith("\n")) t = t.slice(0, -1);
  const b = a + (t.match(/\n/g) || []).length;
  return a === b ? String(a) : a + "-" + b;
}

// Global highlight of every widget's quotes (one registry name, per-widget ranges).
const marks = new Map();
function paintHighlights() {
  try {
    if (typeof Highlight === "undefined" || !CSS.highlights) return;
    const all = [];
    marks.forEach((v) => all.push(...v));
    if (all.length) CSS.highlights.set(HL, new Highlight(...all));
    else CSS.highlights.delete(HL);
  } catch (e) {}
}

/* ------------------------------ the controller ------------------------------ */
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const sr = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };
const btn = { font: "inherit", fontSize: 12, lineHeight: 1.5, color: "var(--foreground)", background: "transparent", border: "1px solid var(--border)", borderRadius: 6, padding: "1px 9px", cursor: "pointer" };
const primary = { ...btn, color: "#fff", background: "var(--accent)", borderColor: "var(--accent)", fontWeight: 600 };

function Pencil() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" style={{ flex: "none", userSelect: "none" }}>
      <path d="M11.5 1.8 L14.2 4.5 L5.6 13.1 L2.2 13.8 L2.9 10.4 Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

// Where a pin goes. A text note: just above the first letter of its words, a little to the left (its bottom edge is 3 px inside the top of the first
// line box, above the glyphs of a lowercase start); with no room above, left of the first letter. An item note: centred on the item's top
// right corner. A pin that would sit under the Notes chip moves left of it.
function pinBox(p, rw, chip) {
  let left, top;
  if (p.text) {
    if (p.ty - PIN + 3 >= 0) { left = p.tx - 12 + (p.k - 1) * (PIN + 2); top = p.ty - PIN + 3; } // 3 px into the line box: above the glyphs, clear of a heading over it
    else if (p.tx - PIN - 2 >= 0) { left = p.tx - PIN - 2 - (p.k - 1) * (PIN + 2); top = p.ty; }
    else { left = p.tx + (p.k - 1) * (PIN + 2); top = 0; }
  } else {
    left = p.x - 9 - (p.k - 1) * 20;
    top = p.y - 9;
  }
  left = Math.max(0, Math.min(left, rw - PIN));
  top = Math.max(0, top);
  if (chip && top < chip.y + chip.h && top + PIN > chip.y && left + PIN > chip.x - 2) left = Math.max(0, chip.x - PIN - 4 - (p.k - 1) * 20);
  return { left, top };
}
// The hover label never sits on the item it names: above it, else below it, else beside it, else the top of the root.
function labelBox(h) {
  const H = 18, gap = 4, right = h.x + h.w / 2 > h.rootW / 2;
  const horiz = right ? { right: Math.max(0, h.rootW - (h.x + h.w + 2)) } : { left: Math.max(0, h.x - 2) };
  if (h.y - 2 - gap - H >= 0) return { ...horiz, top: h.y - 2 - gap - H };
  if (h.y + h.h + 2 + gap + H <= h.rootH) return { ...horiz, top: h.y + h.h + 2 + gap };
  if (h.x - 2 - gap >= 90) return { right: h.rootW - (h.x - 2 - gap), top: Math.max(0, h.y) };
  if (h.rootW - (h.x + h.w + 2 + gap) >= 90) return { left: h.x + h.w + 2 + gap, top: Math.max(0, h.y) };
  return { ...horiz, top: 0 };
}

export function NotesHost({ stem, rootRef, source, children }) {
  const [all, setAll] = useState(() => store.get(stem)); // every stored note; the ones written for another version of the source are set aside below
  const [meta, setMeta] = useState(() => store.getMeta(stem)); // { frozen, top }: once a draft went through, numbers stay (see notes-core.js)
  const srcHash = source == null ? "" : hashText(source);
  const notes = useMemo(() => all.filter((n) => !isStale(n, srcHash)), [all, srcHash]);
  const old = useMemo(() => all.filter((n) => isStale(n, srcHash)), [all, srcHash]);
  const [mode, setMode] = useState(false);
  const [hover, setHover] = useState(null); // { x, y, w, h, name }
  const [editor, setEditor] = useState(null); // { index, target, anchor: {x,y,w,h}, opener }
  const [pos, setPos] = useState(null); // { x, y, w } of the editor card
  const [grow, setGrow] = useState(0);
  const [layout, setLayout] = useState({ pins: [], rows: [], chip: null });
  const [last, setLast] = useState(null); // { ok, text, said } after a draft; dirty marks a change since
  const [dirty, setDirty] = useState(false);
  const [info, setInfo] = useState("");
  const [limited, setLimited] = useState(false); // the 21st note was refused: the hint bar and the hover label say so until the next pointer move or key
  const [pulse, setPulse] = useState(0); // the editor flashes once when a click would have thrown away a half typed note
  const edText = useRef({ now: "", first: "" });
  const wantClear = useRef(false), clearRef = useRef(null);
  const [liveMsg, setLiveMsg] = useState({ n: 0, text: "" });
  const [flash, setFlash] = useState(null); // { n, x, y, w, h }
  const R = useRef({});
  R.current = { notes, old, mode, editor, meta };
  const chipRef = useRef(null), cardRef = useRef(null), spacerRef = useRef(null), stopsRef = useRef(new Map());

  const announce = (text) => setLiveMsg((m) => ({ n: m.n + 1, text }));
  const setNotes = (next, nextMeta) => { // next: the current notes; the set-aside ones stay after them
    const full = next.concat(R.current.old);
    store.set(stem, full);
    setAll(full);
    if (nextMeta && nextMeta !== R.current.meta) { store.setMeta(stem, nextMeta); setMeta(nextMeta); }
    setDirty(true);
    setInfo("");
  };

  /* ---- positions of pins, highlights and tray state ---- */
  const compute = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;
    const RR = root.getBoundingClientRect();
    const ranges = [];
    const pins = [], rows = [];
    R.current.notes.forEach((n, i) => {
      const w = findComp(root, n);
      if (!w) return void rows.push({ i, visible: false });
      const item = n.key ? findItem(w, n.key) : null;
      const q = rel(rectOf(item || w), RR);
      let hit = false, tx = q.x, ty = q.y; // a text note's pin sits at the start of its words; if they cannot be found, at the component's top left (away from the chip)
      if (n.anchor) {
        const rs = findRanges(w, n.anchor);
        const r = rs[Math.min(n.nth || 0, rs.length - 1)];
        if (r) {
          ranges.push(r); hit = true;
          const rc = r.getClientRects(), f = rc.length ? rc[0] : r.getBoundingClientRect();
          tx = f.left - RR.left; ty = f.top - RR.top;
        }
      }
      const at = n.anchor ? "t" + Math.round(tx) + ":" + Math.round(ty) : Math.round(q.x + q.w) + ":" + Math.round(q.y);
      pins.push({ i, x: q.x + q.w, y: q.y, tx, ty, text: !!n.anchor, key: at, hit });
      rows.push({ i, visible: true });
    });
    const seen = {};
    pins.forEach((p) => { p.k = seen[p.key] = (seen[p.key] || 0) + 1; });
    marks.set(stem, ranges);
    paintHighlights();
    const chip = chipRef.current ? rel(chipRef.current.getBoundingClientRect(), RR) : null;
    setLayout((old) => (same(old, { pins, rows, chip }) ? old : { pins, rows, chip }));
  }, [stem]);
  const frame = useRef(0);
  const schedule = useCallback(() => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => { frame.current = 0; compute(); });
  }, [compute]);
  useLayoutEffect(() => { compute(); }, [notes, mode, compute, source]);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let ro = null;
    try { ro = new ResizeObserver(schedule); ro.observe(root); } catch (e) {}
    const mo = new MutationObserver((recs) => {
      if (recs.some((r) => !inUi(r.target) && !(r.target.nodeType === 1 && r.target.hasAttribute("data-oui-notes-ui")))) schedule();
    });
    mo.observe(root, { childList: true, subtree: true, characterData: true });
    root.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    return () => {
      if (ro) ro.disconnect();
      mo.disconnect();
      root.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      if (frame.current) cancelAnimationFrame(frame.current);
      marks.delete(stem);
      paintHighlights();
    };
  }, [schedule, stem]);

  // The chip, the mode and "has notes" show on the root through attributes (CSS in NATIVE_CSS decides what is visible).
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    root.toggleAttribute("data-oui-mode", mode);
    root.toggleAttribute("data-oui-active", mode || notes.length > 0 || old.length > 0);
    return () => { root.removeAttribute("data-oui-mode"); root.removeAttribute("data-oui-active"); };
  }, [mode, notes.length, old.length]);

  // The words picked for a note that is not saved yet stay marked while the editor is open (the textarea took the selection away).
  useEffect(() => {
    const r = editor && editor.index < 0 && editor.range;
    try { if (r && typeof Highlight !== "undefined" && CSS.highlights) CSS.highlights.set(HLP, new Highlight(r)); } catch (e) {}
    return () => { try { if (typeof CSS !== "undefined" && CSS.highlights) CSS.highlights.delete(HLP); } catch (e) {} };
  }, [editor]);

  // The "20 notes" message in the hint bar and on the hover label ends with the next pointer move or key (no timer).
  useEffect(() => {
    if (!limited) return;
    const end = () => setLimited(false);
    window.addEventListener("pointermove", end, true);
    window.addEventListener("keydown", end, true);
    return () => { window.removeEventListener("pointermove", end, true); window.removeEventListener("keydown", end, true); };
  }, [limited]);

  // A double-click on message content hearts the message in the app: it stops here while the mode is on and for the editor and the tray always.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const stop = (e) => { if (R.current.mode || inUi(e.target)) e.stopPropagation(); };
    root.addEventListener("dblclick", stop);
    return () => root.removeEventListener("dblclick", stop);
  }, []);

  /* ---- opening and closing the editor ---- */
  // A click on another item while the editor holds words the user typed must not throw them away: the editor stays, flashes once, and says so.
  // (An empty editor, or an old note not changed, simply moves.)
  const busy = (except) => {
    const e = R.current.editor, t = edText.current;
    if (!e || (except != null && e.index === except) || !(t.now || "").trim() || t.now === t.first) return false;
    setInfo(HALF);
    setPulse((n) => n + 1);
    return true;
  };
  const openEditor = (target, anchor, opener, range) => {
    if (busy()) return false;
    setInfo("");
    setPos(null);
    setGrow(0);
    setEditor({ index: -1, target, anchor, opener: opener || chipRef.current, range: range || null });
    return true;
  };
  const openEdit = (i, opener) => {
    if (busy(i)) return;
    setInfo("");
    const p = layout.pins.find((x) => x.i === i);
    const RR = rootRef.current.getBoundingClientRect();
    setPos(null);
    setGrow(0);
    setEditor({ index: i, target: notes[i], anchor: p ? { x: p.x - 6, y: p.y - 6, w: 12, h: 12 } : { x: 0, y: 0, w: 12, h: 12 }, opener: opener || chipRef.current, RR });
  };
  const closeEditor = (focusBack = true) => {
    const e = R.current.editor;
    setEditor(null);
    setGrow(0);
    if (focusBack && e && e.opener && e.opener.isConnected) {
      try { e.opener.focus({ preventScroll: true }); } catch (x) {}
    }
  };

  /* ---- notes mode: capture listeners on the widget root ---- */
  useEffect(() => {
    const root = rootRef.current;
    if (!root || !mode) return;
    const RR = () => root.getBoundingClientRect();
    const hoverOf = (t) => {
      if (!t) return setHover(null);
      setHover({ ...rel(rectOf(t.el), RR()), name: t.name, rootW: root.clientWidth, rootH: root.getBoundingClientRect().height });
    };
    const tabbar = (t) => !!(t && t.closest && t.closest("[data-oui-tabbar]"));
    const onOver = (e) => {
      if (inUi(e.target)) return setHover(null);
      e.stopPropagation(); // tooltips are suspended while the mode is on
      hoverOf(targetAt(e.target, root, e.shiftKey));
    };
    const onLeave = () => setHover(null);
    const onFocusIn = (e) => {
      if (inUi(e.target)) return;
      e.stopPropagation();
      hoverOf(targetAt(e.target, root, false));
    };
    const atLimit = () => {
      if (R.current.notes.length + R.current.old.length < NOTE_LIMITS.notes) return false;
      setInfo(LIMIT_MSG); // the tray keeps it; the hint bar and the hover label show it until the next move or key
      setLimited(true);
      return true;
    };
    const fromTarget = (t, opener) => {
      if (atLimit()) return;
      openEditor({ cid: t.cid, ctype: t.ctype, unnamed: t.unnamed, key: t.key, what: t.what, label: t.label, tab: t.tab, pos: t.pos, cell: t.cell, quote: "", anchor: "", nth: 0, lines: "" }, rel(rectOf(t.el), RR()), opener);
    };
    const fromSelection = () => {
      const sel = window.getSelection();
      if (!sel || !sel.rangeCount || sel.isCollapsed) return false;
      const range = sel.getRangeAt(0);
      if (!root.contains(range.startContainer) || inUi(range.startContainer)) return false;
      const t = targetAt(range.startContainer, root, false);
      const anchor = collapse(String(sel));
      if (!t || !anchor) return false;
      if (atLimit()) return true;
      const found = findRanges(t.w, anchor.slice(0, 300));
      let nth = found.findIndex((r) => r.compareBoundaryPoints(Range.START_TO_START, range) === 0);
      if (nth < 0) nth = 0;
      const rects = range.getClientRects();
      const q = rects.length ? rects[rects.length - 1] : range.getBoundingClientRect();
      openEditor(
        { cid: t.cid, ctype: t.ctype, unnamed: t.unnamed, key: t.key, what: t.what, label: t.label, tab: t.tab, pos: t.pos, cell: "", quote: cleanQuote(anchor), anchor: anchor.slice(0, 300), nth, lines: t.ctype === "CodeBlock" ? lineSpan(t.w, range) : "" },
        rel(q, RR()), null, range.cloneRange(),
      );
      return true;
    };
    let tookSelection = false; // the mouseup that ends a drag opens the text editor; the click that follows it must not open a second one
    const onDown = (e) => { tookSelection = false; };
    const onClick = (e) => {
      if (inUi(e.target) || tabbar(e.target)) return; // the notes controls and the tab bar work as always
      e.preventDefault();
      e.stopPropagation(); // Buttons, Choices and every other control are inert
      if (tookSelection) { tookSelection = false; return; }
      if (e.detail > 1) return;
      const sel = window.getSelection();
      if (sel && !sel.isCollapsed) return; // the end of a drag: mouseup took it as text
      const t = targetAt(e.target, root, e.shiftKey);
      if (t) fromTarget(t, null);
    };
    const onUp = (e) => {
      if (inUi(e.target)) return;
      tookSelection = fromSelection();
    };
    const onKeyDown = (e) => {
      if (inUi(e.target)) return;
      if ((e.key === "Enter" || e.key === " ") && e.target.hasAttribute && e.target.hasAttribute("data-oui-stop")) {
        e.preventDefault();
        e.stopPropagation();
        const t = targetAt(e.target, root, false);
        if (t) fromTarget(t, e.target);
      }
    };
    const onKeyUp = (e) => {
      if (inUi(e.target)) return;
      if (e.shiftKey || e.key === "Shift") fromSelection(); // shift + arrows
    };
    root.addEventListener("mouseover", onOver, true);
    root.addEventListener("mouseleave", onLeave);
    root.addEventListener("focusin", onFocusIn, true);
    root.addEventListener("click", onClick, true);
    root.addEventListener("mousedown", onDown, true);
    root.addEventListener("mouseup", onUp, true);
    root.addEventListener("keydown", onKeyDown, true);
    root.addEventListener("keyup", onKeyUp, true);

    // One tab stop per component (roving tabindex): Tab moves between components, the arrow keys between the items of one component in
    // reading order, Enter or Space opens the editor. A table of 100 rows is one stop, not 300. The items keep what tabindex they had
    // (a Tooltip target has 0) and get it back when the mode ends.
    const stops = stopsRef.current; // Map: element -> the tabindex attribute it had (null: none)
    const groupOf = (el) => {
      const w = el.closest("[data-oui-type]");
      return w ? Array.from(w.querySelectorAll("[data-oui-stop]")).filter((x) => x.closest("[data-oui-type]") === w) : [];
    };
    const setCurrent = (el) => groupOf(el).forEach((x) => x.setAttribute("tabindex", x === el ? "0" : "-1"));
    const markStops = () => {
      root.querySelectorAll("[data-oui-type]").forEach((w) => {
        const type = typeOf(w);
        if (!isNoteable(type)) return;
        const items = Array.from(w.querySelectorAll("[data-oui-k]")).filter((it) => it.closest("[data-oui-type]") === w);
        const leaves = items.filter((it) => !it.querySelector("[data-oui-k]"));
        const targets = leaves.length ? leaves : w.firstElementChild ? [w.firstElementChild] : [];
        targets.forEach((el) => {
          if (el.hasAttribute("data-oui-stop")) return;
          if (!stops.has(el)) stops.set(el, el.getAttribute("tabindex"));
          el.setAttribute("data-oui-stop", "");
          el.setAttribute("tabindex", "-1");
        });
        const group = targets.filter((el) => el.hasAttribute("data-oui-stop"));
        if (group.length && !group.some((el) => el.getAttribute("tabindex") === "0")) group[0].setAttribute("tabindex", "0");
      });
    };
    markStops();
    const onFocusStop = (e) => { if (e.target.hasAttribute && e.target.hasAttribute("data-oui-stop")) setCurrent(e.target); };
    root.addEventListener("focusin", onFocusStop, true); // capture: the hover handler above stops this event on the way down
    const onArrow = (e) => {
      const back = e.key === "ArrowLeft" || e.key === "ArrowUp", fwd = e.key === "ArrowRight" || e.key === "ArrowDown";
      if (!(back || fwd) || e.altKey || e.ctrlKey || e.metaKey || inUi(e.target) || !e.target.hasAttribute || !e.target.hasAttribute("data-oui-stop")) return;
      const group = groupOf(e.target), at = group.indexOf(e.target), next = group[at + (fwd ? 1 : -1)];
      e.preventDefault(); // the arrows move between items in the mode; they do not scroll the page
      if (next) { try { next.focus(); } catch (x) {} }
    };
    root.addEventListener("keydown", onArrow, true);
    // A click on a gap or on the hint bar puts the focus on the root, so Esc still reaches this widget (a click on bare page would leave it on the body).
    const rootStop = !root.hasAttribute("tabindex");
    if (rootStop) root.setAttribute("tabindex", "-1");
    const mo = new MutationObserver((recs) => { if (recs.some((r) => !inUi(r.target))) markStops(); });
    mo.observe(root, { childList: true, subtree: true });
    return () => {
      root.removeEventListener("mouseover", onOver, true);
      root.removeEventListener("mouseleave", onLeave);
      root.removeEventListener("focusin", onFocusIn, true);
      root.removeEventListener("click", onClick, true);
      root.removeEventListener("mousedown", onDown, true);
      root.removeEventListener("mouseup", onUp, true);
      root.removeEventListener("keydown", onKeyDown, true);
      root.removeEventListener("keyup", onKeyUp, true);
      mo.disconnect();
      root.removeEventListener("focusin", onFocusStop, true);
      root.removeEventListener("keydown", onArrow, true);
      if (rootStop) root.removeAttribute("tabindex");
      stops.forEach((was, el) => { el.removeAttribute("data-oui-stop"); if (was == null) el.removeAttribute("tabindex"); else el.setAttribute("tabindex", was); });
      stops.clear();
      setHover(null);
    };
  }, [mode]);

  // Escape: preventDefault only when it closed the editor or left the mode, so the app's Escape (it stops a running turn) still works otherwise.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      if (R.current.editor) { e.preventDefault(); closeEditor(); }
      else if (R.current.mode) { e.preventDefault(); setMode(false); if (chipRef.current && root.contains(document.activeElement)) { try { chipRef.current.focus({ preventScroll: true }); } catch (x) {} } }
    };
    root.addEventListener("keydown", onKey);
    return () => root.removeEventListener("keydown", onKey);
  }, []);

  /* ---- the editor card: placed inside the root ---- */
  useLayoutEffect(() => {
    if (!editor || !cardRef.current || !rootRef.current) return;
    const rw = rootRef.current.clientWidth, spacer = spacerRef.current ? spacerRef.current.offsetHeight : 0;
    const rh = rootRef.current.getBoundingClientRect().height - spacer;
    const c = cardRef.current.getBoundingClientRect();
    const w = Math.min(340, Math.max(220, rw - 8)), h = c.height, a = editor.anchor, gap = 6;
    let y = a.y + a.h + gap;
    // below the item; above it when there is no room below and room above; else below anyway and the spacer grows the widget (the card never covers its item)
    if (y + h > rh && a.y - gap - h >= 0) y = a.y - gap - h;
    const x = Math.max(0, Math.min(a.x, rw - w));
    setPos((o) => (o && o.x === x && o.y === y && o.w === w ? o : { x, y, w }));
    setGrow(Math.max(0, Math.ceil(y + h + 6 - rh)));
  }, [editor, layout]);

  /* ---- saving, removing, drafting ---- */
  const save = (text) => {
    const e = R.current.editor;
    if (!e) return;
    const r = e.index >= 0 ? updateNote(R.current.notes, e.index, text) : addNote(R.current.notes, { ...e.target, text, src: srcHash }, R.current.meta);
    if (!r.ok) return setInfo(r.error);
    const m = r.meta || R.current.meta;
    setNotes(r.notes, m);
    const nums = numbersFor(r.notes, m);
    announce("Note " + nums[e.index >= 0 ? e.index : r.notes.length - 1] + (e.index >= 0 ? " updated" : " added"));
    closeEditor();
  };
  const remove = (i) => {
    const gone = numbersFor(R.current.notes, R.current.meta)[i];
    setNotes(removeNote(R.current.notes, i));
    announce("Note " + gone + " removed");
    if (R.current.editor) closeEditor();
  };
  const keepStale = () => { // the notes written for another version count again, for this version; a kept note that was in a message before is "edited"
    const kept = all.map((n) => (isStale(n, srcHash) ? { ...n, src: srcHash, edited: !!(n.drafted || n.edited), drafted: false } : n));
    const s = settleNumbers(kept, meta); // once numbers are frozen a kept note takes the next free one
    store.set(stem, s.notes);
    store.setMeta(stem, s.meta);
    setAll(s.notes);
    setMeta(s.meta);
    setDirty(true);
    announce("Earlier notes kept");
  };
  const dropStale = () => {
    const full = all.filter((n) => !isStale(n, srcHash));
    store.set(stem, full);
    setAll(full);
    announce("Earlier notes cleared");
  };
  const clearAll = () => {
    store.set(stem, []);
    store.setMeta(stem, NO_META); // the numbers start again at 1
    setAll([]);
    setMeta(NO_META);
    setLast(null);
    setDirty(false);
    setInfo("");
    announce("Notes cleared");
  };
  // all: "Add all again" (every note, the original header, the same numbers); otherwise what the primary button says.
  const draft = async (again) => {
    const plan = planDraft(stem, notes, meta, again === true);
    if (plan.kind === "none") return;
    if (!plan.message.ok) return setInfo(plan.message.error);
    const sent = plan.indexes.map((i) => notes[i]); // by object: a note edited while the composer answered is not marked
    let ok = false;
    const addr = composerAddress(rootRef.current); // the composer of the chat that holds this widget, never "the one last focused"
    try {
      const c = host && host.composer;
      if (c && typeof c.insertText === "function") ok = (await c.insertText(addr, plan.message.text, { mode: "block" })) === true;
    } catch (e) { ok = false; }
    if (ok) {
      try { host.composer.focus(addr); } catch (e) {}
      const now = R.current.notes;
      const done = markDrafted(now, now.map((n, i) => (sent.includes(n) ? i : -1)).filter((i) => i >= 0), R.current.meta);
      const full = done.notes.concat(R.current.old);
      store.set(stem, full);
      store.setMeta(stem, done.meta);
      setAll(full);
      setMeta(done.meta);
      setMode(false); // the notes are in the message box: the mode is done
      wantClear.current = true; // focus goes to "Clear notes" unless the composer took it (below)
    }
    const said = addedSentence(plan, notes.length);
    setLast({ ok, text: plan.message.text, said });
    if (ok) announce(said.split(" Edit it")[0]);
    setDirty(false);
    setInfo("");
  };
  const copyAll = () => { // the message the primary button would draft; with nothing new, the one "Add all again" would
    const plan = planDraft(stem, notes, meta, false);
    const m = (plan.kind === "none" ? planDraft(stem, notes, meta, true) : plan).message;
    if (!m.ok) return setInfo(m.error);
    setInfo(copyText(m.text) ? "Copied." : "Copy blocked. Select the text and copy it yourself.");
  };
  const flashRow = (i) => {
    const root = rootRef.current, n = notes[i];
    const w = root && findComp(root, n);
    if (!w) return;
    const el = (n.key && findItem(w, n.key)) || w;
    try { (el.hasAttribute("data-oui-type") && el.firstElementChild ? el.firstElementChild : el).scrollIntoView({ block: "nearest", inline: "nearest" }); } catch (e) {}
    const q = rel(rectOf(el), root.getBoundingClientRect());
    setFlash({ n: (flash ? flash.n : 0) + 1, ...q });
  };

  /* ---- drawing ---- */
  // After a draft the button the user pressed is gone: keep the focus in the tray, on "Clear notes", unless the message box took it.
  useEffect(() => {
    if (!wantClear.current || !clearRef.current) return;
    wantClear.current = false;
    const a = document.activeElement, root = rootRef.current;
    if (!a || a === document.body || (root && root.contains(a))) { try { clearRef.current.focus({ preventScroll: true }); } catch (e) {} }
  });
  const count = notes.length;
  const visibleRow = (i) => (layout.rows.find((r) => r.i === i) || {}).visible !== false;
  const nums = numbersFor(notes, meta); // the number of every note: its position until a draft went through, then frozen
  const plan = planDraft(stem, notes, meta, false); // what the primary button drafts; kind "none": every note is in the message box
  const said = last && last.ok && !dirty ? last.said : null;
  const card = { boxSizing: "border-box", border: "1px solid var(--border)", borderRadius: 8, background: "var(--card)", color: "var(--foreground)", fontSize: 13, lineHeight: 1.45, boxShadow: "0 4px 14px rgba(0,0,0,0.28)" };
  const accent = "var(--accent, #5B9CF6)";

  return (
    <>
      <button
        ref={chipRef}
        type="button"
        data-oui-notes-ui=""
        data-oui-chip=""
        aria-pressed={mode}
        title={mode ? "Finish notes (Esc)" : "Add notes on this widget"}
        onClick={() => {
          if (R.current.editor) { if (busy()) return; closeEditor(false); } // the chip ends the mode and the editor with it
          setMode((m) => !m);
          setHover(null);
        }}
        style={{ position: "absolute", top: 4, right: 4, zIndex: 7, display: "inline-flex", alignItems: "center", gap: 5, font: "inherit", fontSize: 12, lineHeight: 1.4, minHeight: 24, padding: "1px 8px", borderRadius: 999, cursor: "pointer", color: mode ? "#fff" : "var(--foreground)", background: mode ? accent : "var(--card)", border: "1px solid " + (mode ? accent : "var(--border)"), boxShadow: "0 1px 4px rgba(0,0,0,0.25)", userSelect: "none" }}
      >
        <Pencil />
        <span>Notes{count ? " \u00b7 " + count : ""}</span>
      </button>
      {mode ? (
        <div data-oui-notes-ui="" data-oui-hint="" style={{ display: "flex", alignItems: "center", gap: 8, boxSizing: "border-box", padding: "3px 8px", margin: "0 0 8px", paddingRight: 96, border: "1px solid " + accent, borderRadius: 6, background: "var(--card)", color: "var(--foreground)", fontSize: 12.5 }}>
          <span style={{ flex: 1, minWidth: 0 }}>{limited ? LIMIT_MSG : "Click anything or select text to add a note. Shift+click picks the parent. Esc to finish."}</span>
        </div>
      ) : null}
      {children}
      <div data-oui-notes-ui="" data-oui-overlay="" style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 6 }}>
        {hover && !editor ? (
          <>
            <div style={{ position: "absolute", left: hover.x - 2, top: hover.y - 2, width: hover.w + 4, height: hover.h + 4, boxSizing: "border-box", outline: "2px solid " + accent, borderRadius: 4, background: "color-mix(in srgb, " + accent + " 12%, transparent)" }} />
            <div data-oui-hover-label="" style={{ position: "absolute", ...labelBox(hover), maxWidth: "90%", padding: "0 7px", borderRadius: 4, background: accent, color: "#fff", fontSize: 11.5, lineHeight: "18px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{limited ? LIMIT_MSG : hover.name}</div>
          </>
        ) : null}
        {flash ? (
          <div key={flash.n} data-oui-flash="" onAnimationEnd={() => setFlash(null)} style={{ position: "absolute", left: flash.x - 3, top: flash.y - 3, width: flash.w + 6, height: flash.h + 6, boxSizing: "border-box", border: "2px solid " + accent, borderRadius: 5, animation: "oui-flash 1.2s ease-out 1" }} />
        ) : null}
        {layout.pins.map((p) => {
          const n = notes[p.i];
          if (!n) return null;
          const { left, top } = pinBox(p, rootRef.current ? rootRef.current.clientWidth : 9999, layout.chip);
          return (
            <button
              key={p.i}
              type="button"
              data-oui-notes-ui=""
              data-oui-pin={nums[p.i]}
              aria-label={"Note " + nums[p.i] + " on " + plainWhere(n) + ": " + n.text}
              title={n.text}
              onClick={(e) => openEdit(p.i, e.currentTarget)}
              style={{ position: "absolute", left, top, width: PIN, height: PIN, padding: 0, borderRadius: 9, pointerEvents: "auto", cursor: "pointer", font: "inherit", fontSize: 11, fontWeight: 700, lineHeight: "16px", textAlign: "center", color: "#fff", background: accent, border: "1px solid var(--card)", boxShadow: "0 1px 3px rgba(0,0,0,0.4)", opacity: n.drafted ? 0.85 : 1, userSelect: "none" }}
            >
              {nums[p.i]}
            </button>
          );
        })}
        {editor ? (
          <Editor
            key={editor.index + ":" + editor.target.cid + ":" + (editor.target.key || "") + ":" + (editor.target.anchor || "")}
            editor={editor}
            num={editor.index >= 0 ? nums[editor.index] : 0}
            pos={pos}
            cardRef={cardRef}
            cardStyle={card}
            err={info}
            pulse={pulse}
            textRef={edText}
            onType={() => setInfo((v) => (v === HALF ? "" : v))}
            onSave={save}
            onCancel={() => closeEditor()}
            onDelete={() => remove(editor.index)}
          />
        ) : null}
      </div>
      <div ref={spacerRef} aria-hidden="true" data-oui-notes-ui="" style={{ height: grow }} />
      {count || old.length ? (
        <div data-oui-notes-ui="" data-oui-tray="" role="group" aria-label="Notes on this widget" style={{ ...card, boxShadow: "none", marginTop: 10, padding: "8px 10px", fontSize: 12.5 }}>
          {count ? <div style={{ fontWeight: 600, marginBottom: 4 }}>{count === 1 ? "1 note" : count + " notes"}</div> : null}
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {notes.map((n, i) => {
              const vis = visibleRow(i);
              return (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <button type="button" data-oui-row={nums[i]} onClick={() => vis && flashRow(i)} aria-disabled={!vis} title={vis ? "Show where this note is (id " + n.cid + ")" : n.tab ? "Not visible now: switch back to its tab" : "Not in this widget now"} style={{ all: "unset", boxSizing: "border-box", flex: 1, minWidth: 0, display: "flex", gap: 8, alignItems: "baseline", padding: "3px 4px", borderRadius: 5, cursor: vis ? "pointer" : "default", opacity: vis ? 1 : 0.65, color: "var(--foreground)" }}>
                    <span style={{ flex: "none", minWidth: 16, height: 16, lineHeight: "16px", borderRadius: 8, textAlign: "center", fontSize: 11, fontWeight: 700, color: "#fff", background: accent }}>{nums[i]}</span>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: "block", color: "var(--muted-foreground)", fontSize: 11.5 }}>
                        {plainWhere(n)}{n.tab ? " \u00b7 tab " + n.tab : ""}{vis ? "" : n.tab ? " \u00b7 not visible now" : " \u00b7 not in this widget now"}
                        {n.drafted || n.edited ? <>{" "}<span data-oui-state={n.drafted ? "drafted" : "edited"} style={{ marginLeft: 4, padding: "0 6px", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11, lineHeight: "15px", whiteSpace: "nowrap", color: n.drafted ? "var(--muted-foreground)" : "var(--foreground)" }}>{n.drafted ? "in your message" : "edited"}</span></> : null}
                      </span>
                      {n.quote ? <span style={{ display: "block", color: "var(--muted-foreground)", fontStyle: "italic", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{"\u201c" + n.quote + "\u201d"}</span> : null}
                      <span style={{ display: "block", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{n.text}</span>
                    </span>
                  </button>
                  <button type="button" data-oui-remove={nums[i]} aria-label={"Remove note " + nums[i]} title="Remove this note" onClick={() => remove(i)} style={{ ...btn, flex: "none", minWidth: 24, minHeight: 24, padding: "0 7px", fontSize: 14, lineHeight: 1.3 }}>{"\u00d7"}</button>
                </div>
              );
            })}
          </div>
          {old.length ? (
            <div data-oui-stale="" style={{ marginTop: count ? 8 : 0, paddingTop: count ? 6 : 0, borderTop: count ? "1px solid var(--border)" : "none" }}>
              <div style={{ fontWeight: 600 }}>These notes were written for an earlier version of this widget.</div>
              <div style={{ margin: "4px 0", opacity: 0.75 }}>
                {old.map((n, i) => (
                  <div key={i} data-oui-stale-row="" title="Not in this widget now" style={{ padding: "2px 4px" }}>
                    <span style={{ display: "block", color: "var(--muted-foreground)", fontSize: 11.5 }}>{plainWhere(n)}</span>
                    <span style={{ display: "block", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{n.text}</span>
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button type="button" data-oui-keep="" style={btn} onClick={keepStale}>Keep them</button>
                <button type="button" data-oui-drop="" style={btn} onClick={dropStale}>Clear them</button>
              </div>
            </div>
          ) : null}
          {count && last && !last.ok ? (
            <div data-oui-fail="" style={{ marginTop: 8 }}>
              <div style={{ color: "var(--muted-foreground)", marginBottom: 4 }}>Could not reach the message box. Copy this and paste it into the chat.</div>
              <pre style={{ margin: 0, padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 6, whiteSpace: "pre-wrap", overflowWrap: "anywhere", userSelect: "text", WebkitUserSelect: "text", fontSize: 12, maxHeight: 220, overflow: "auto" }}>{last.text}</pre>
            </div>
          ) : null}
          {count && said ? <div data-oui-done="" style={{ marginTop: 8, color: "var(--foreground)" }}>{said}</div> : null}
          {count && plan.kind === "none" ? <div data-oui-allin="" style={{ marginTop: said ? 2 : 8, color: "var(--muted-foreground)" }}>{count === 1 ? "The note is in your message box." : "All " + count + " notes are in your message box."}</div> : null}
          {info ? <div role="status" data-oui-info="" style={{ marginTop: 6, color: "var(--muted-foreground)" }}>{info}</div> : null}
          {count ? (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, marginTop: 8 }}>
              {plan.kind !== "none" ? (
                <button type="button" data-oui-draft="" style={primary} onClick={() => draft(false)}>{buttonLabel(plan, count)}</button>
              ) : (
                <>
                  <button type="button" data-oui-again="" style={btn} onClick={() => draft(true)}>Add all again</button>
                  <button ref={clearRef} type="button" data-oui-clear-done="" style={btn} onClick={clearAll}>Clear notes</button>
                </>
              )}
              <button type="button" data-oui-copy="" style={btn} onClick={copyAll}>Copy</button>
              {plan.kind !== "none" ? <button type="button" data-oui-clear="" style={btn} onClick={clearAll}>Clear</button> : null}
            </div>
          ) : null}
        </div>
      ) : null}
      <div role="status" aria-live="polite" style={sr}><span key={liveMsg.n}>{liveMsg.text}</span></div>
    </>
  );
}

function Editor({ editor, num, pos, cardRef, cardStyle, err, pulse, textRef, onType, onSave, onCancel, onDelete }) {
  const first = editor.index >= 0 ? editor.target.text : "";
  const [text, setText] = useState(first);
  const ta = useRef(null);
  useEffect(() => { try { ta.current && ta.current.focus({ preventScroll: true }); } catch (e) {} }, []);
  textRef.current = { now: text, first }; // the controller asks before it moves the editor (it looks only while an editor is open)
  const t = editor.target;
  const empty = !text.trim();
  const limit = text.length >= NOTE_LIMITS.note;
  const submit = () => { if (!empty) onSave(text); };
  return (
    <div
      ref={cardRef}
      role="dialog"
      aria-label={(num ? "Note " + num + " on " : "Note on ") + plainWhere(t)}
      data-oui-notes-ui=""
      data-oui-editor=""
      data-oui-pulse={pulse || undefined}
      style={{ ...cardStyle, position: "absolute", left: pos ? pos.x : 0, top: pos ? pos.y : 0, width: pos ? pos.w : 320, opacity: pos ? 1 : 0, padding: 10, pointerEvents: "auto", zIndex: 8, animation: pulse ? (pulse % 2 ? "oui-pulse-a" : "oui-pulse-b") + " .9s ease-out 1" : undefined }}
    >
      <div style={{ fontWeight: 600, fontSize: 12.5, overflowWrap: "anywhere" }}>{(num ? "Note " + num + " \u00b7 " : "") + plainWhere(t)}</div>
      {t.quote ? <div style={{ margin: "3px 0 0", color: "var(--muted-foreground)", fontStyle: "italic", fontSize: 12, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflowWrap: "anywhere" }}>{"\u201c" + t.quote + "\u201d"}</div> : null}
      <textarea
        ref={ta}
        value={text}
        maxLength={NOTE_LIMITS.note}
        rows={3}
        placeholder="What should the agent look at or answer?"
        aria-label="Your note"
        onChange={(e) => { setText(e.target.value); onType(); }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); submit(); }
        }}
        style={{ display: "block", boxSizing: "border-box", width: "100%", marginTop: 8, padding: "5px 7px", font: "inherit", fontSize: 13, color: "var(--foreground)", background: "transparent", border: "1px solid var(--border)", borderRadius: 6, resize: "vertical", userSelect: "text", WebkitUserSelect: "text" }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
        <span style={{ flex: 1, minWidth: 0, fontSize: 11.5, color: limit ? "var(--foreground)" : "var(--muted-foreground)" }}>
          {limit ? "Limit reached: a note is at most " + fmt(NOTE_LIMITS.note) + " characters." : fmt(text.length) + " / " + fmt(NOTE_LIMITS.note)}
        </span>
        {editor.index >= 0 ? <button type="button" data-oui-delete="" style={btn} onClick={onDelete}>Delete</button> : null}
        <button type="button" data-oui-cancel="" style={btn} onClick={onCancel}>Cancel</button>
        <button type="button" data-oui-save="" style={{ ...primary, opacity: empty ? 0.5 : 1 }} disabled={empty} onClick={submit}>Save</button>
      </div>
      {err ? <div role="alert" style={{ marginTop: 6, fontSize: 12, color: "var(--muted-foreground)" }}>{err}</div> : null}
    </div>
  );
}
