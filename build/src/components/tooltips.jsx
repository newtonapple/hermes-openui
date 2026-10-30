// Tooltips on a diagram, a table, a metric tile, a bar chart, a map or an image: a dot on each element that has a tooltip, a tooltip on
// hover or keyboard focus, and one detail panel under the component on click, Enter or Space. ONE module for all of them, and the core
// carries it once for the whole page: the packs take it from window.__HM.mods["hermes-openui/tooltips"] (build.mjs SHARED_FILES). The pure parts (text rules, link rules, tooltip placement)
// are in tooltips-core.js. Nothing here sends anything to the agent.
//
// How a view uses it:
//   <Tipped tooltips={props.tooltips}> <div scroller> <svg> ... <Hot k="web" label="Web" shape={...} marker={[x, y]}>{element}</Hot> ... </svg> </div> </Tipped>
// Tipped is the relative wrapper (it owns the hover, focus and open state, the tooltip and the panel); Hot wraps one element and
// is a no-op (it returns its children) when that element has no tooltip, so a diagram without tooltips draws as before.
// An HTML component (Table, Metric, BarChart, Image) uses HotBox instead of Hot: it is the same element with the same attributes, so a
// <tr> stays a <tr>. A table row, header or cell keeps its own role (row, columnheader, cell) and is only made focusable: a role override
// would take it out of the table for a screen reader and nest one button in another. TipBox is the root of a component that has no root of
// its own to hold the wrapper and the panel.
import React, { createContext, useContext, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { C, TONES, MONO } from "../theme.js";
import { CodeView, copyText } from "./code.jsx";
import { normalizeTooltips, tooltipText, panelText, checkLink, placeTooltip, rowFlow } from "./tooltips-core.js";

// The targets that carry a tooltip, so a view can leave out the native <title> of an element that has a tooltip (it would double the tooltip)
// and give the svg role group instead of img (children of an img are hidden from assistive technology, and ours are buttons).
export function tippedKeys(tooltips) {
  return new Set(normalizeTooltips(tooltips).map((a) => a.target));
}

// Links open only in the native desktop build (desktop/plugin.js turns this on). The preview frame and an exported page never do,
// even if some bridge object happened to exist there: their sandbox blocks navigation and the URL stays text to copy.
let nativeLinks = false;
export function enableNativeLinks() {
  nativeLinks = true;
}
function bridge() {
  if (!nativeLinks) return null;
  try {
    const b = window.hermesDesktop;
    return b && typeof b.openExternal === "function" ? b : null;
  } catch (e) {
    return null;
  }
}

const Ctx = createContext(null);
const hotOf = (t) => {
  try {
    return t && t.closest ? t.closest("[data-tip]") : null;
  } catch (e) {
    return null;
  }
};
const toneColor = (tone) => TONES[tone] || TONES.info;

/* ------------------------------ one element ------------------------------ */
// shape: { t: "rect", x, y, w, h, rx } (a transparent hit rectangle under the element, so a row of text can be hovered between its glyphs,
// and the outline) or { t: "path", d } (a transparent 12 px hit path over the element, so a thin line can be hovered). marker: [x, y], the centre of the 6 px dot. proxy: a second piece of an element that is already a Hot (a link's
// label pill): it reacts to the mouse but is not a tab stop of its own. full: the whole label when the drawn one is cut.
// scale: the user units of one css pixel, for an svg whose viewBox is zoomed (a map); the dot, the outline and the hit path grow with it.
export function Hot({ k, label, shape, marker, proxy, full, scale = 1, children }) {
  const ctx = useContext(Ctx);
  const a = ctx && ctx.byKey.get(k);
  if (!a) return children == null ? null : children;
  const common = { "data-tip": k, "data-tip-label": label, "data-tip-full": full || undefined };
  const col = toneColor(a.tone);
  const dot = marker ? <circle data-tip-dot="" cx={marker[0]} cy={marker[1]} r={3 * scale} fill={col} stroke={C.card} strokeWidth={1.2 * scale} pointerEvents="none" /> : null;
  if (proxy) return <g {...common} style={{ cursor: "pointer" }}>{children}{dot}</g>;
  const open = ctx.openKey === k;
  const active = open || ctx.tipKey === k;
  return (
    <g
      {...common}
      tabIndex={0}
      role="button"
      aria-label={label + ". " + tooltipText(a)}
      aria-expanded={open}
      aria-controls={open ? ctx.panelId : undefined}
      aria-describedby={ctx.tipKey === k ? ctx.tipId : undefined}
      style={{ cursor: "pointer", outline: "none" }}
    >
      {shape && shape.t === "rect" ? <rect x={shape.x} y={shape.y} width={shape.w} height={shape.h} rx={shape.rx || 0} fill="transparent" pointerEvents="all" /> : null}
      {children}
      {shape && shape.t === "path" ? <path d={shape.d} fill="none" stroke="transparent" strokeWidth={12 * scale} strokeLinecap="round" strokeLinejoin="round" pointerEvents="stroke" /> : null}
      {active && shape && shape.t === "rect" ? (
        <rect x={shape.x - scale} y={shape.y - scale} width={shape.w + 2 * scale} height={shape.h + 2 * scale} rx={(shape.rx || 0) + scale} fill="none" stroke={col} strokeWidth={2 * scale} pointerEvents="none" />
      ) : null}
      {active && shape && shape.t === "path" ? (
        <path d={shape.d} fill="none" stroke={col} strokeWidth={4 * scale} strokeOpacity={0.45} strokeLinecap="round" strokeLinejoin="round" pointerEvents="none" />
      ) : null}
      {dot}
    </g>
  );
}

/* ------------------------------ an HTML element ------------------------------ */
// Whether a target has a tooltip (a Table marks a row's first cell as the anchor of the row's dot only when the row has one).
export function useTipHas() {
  const ctx = useContext(Ctx);
  return (k) => !!(ctx && ctx.byKey.has(k));
}
export function hasTips(tooltips) {
  return normalizeTooltips(tooltips).length > 0;
}

// The dot of a target, as a 6 px circle: placed by CSS offsets inside the nearest positioned ancestor, or (inline) right after the text of the
// element it belongs to, so it never drifts away from its text in a wide table cell. HotBox draws one by itself.
export function TipDot({ k, top, right, bottom, left, marginTop, marginLeft, inline }) {
  const ctx = useContext(Ctx);
  const a = ctx && ctx.byKey.get(k);
  if (!a) return null;
  const look = { width: 6, height: 6, borderRadius: 6, background: toneColor(a.tone), boxShadow: "0 0 0 1.2px " + C.card, pointerEvents: "none" };
  const place = inline ? { display: "inline-block", marginLeft: 6, verticalAlign: "middle" } : { position: "absolute", top, right, bottom, left, marginTop, marginLeft };
  return <span data-tip-dot="" aria-hidden="true" style={{ ...place, ...look }} />;
}

// One HTML element with a tooltip: the same attributes and behaviour as Hot has for an svg element (focusable, outline in the tone colour while
// hovered, focused or open, a dot), so the wrapper's delegated events treat both alike. `as` is the tag (a "tr" stays a real <tr>). A tr, th or td
// keeps its role: it gets tabindex and aria-describedby only, and aria-expanded when its role supports it (a row and a column header do, a plain
// cell does not); every other element is a role=button with an aria-label. name: what a screen reader says first (default label); label is the
// panel title. dot: CSS offsets of the dot, "inline" (after the children), or null when the element places it itself. inset: draw the outline
// inside the element (table cells, whose outer edge is clipped by the scroller). With no tooltip for k, or outside a Tipped, it draws exactly
// the plain element.
export function HotBox({ as: Tag = "div", k, label, name, dot = { top: 3, right: 3 }, inset, style, children, ...rest }) {
  const ctx = useContext(Ctx);
  const a = ctx && ctx.byKey.get(k);
  if (!a) return <Tag style={style} {...rest}>{children}</Tag>;
  const open = ctx.openKey === k, active = open || ctx.tipKey === k;
  const part = Tag === "tr" || Tag === "th" || Tag === "td";
  return (
    <Tag
      {...rest}
      data-tip={k}
      data-tip-label={label}
      tabIndex={0}
      role={part ? undefined : "button"}
      aria-label={part ? undefined : (name || label) + ". " + tooltipText(a)}
      aria-expanded={Tag === "td" ? undefined : open}
      aria-controls={open ? ctx.panelId : undefined}
      aria-describedby={ctx.tipKey === k ? ctx.tipId : undefined}
      style={{ ...style, ...(Tag === "tr" || dot === "inline" ? null : { position: (style && style.position) || "relative" }), cursor: "pointer", outline: active ? "2px solid " + toneColor(a.tone) : "none", outlineOffset: inset ? -2 : 2 }}
    >
      {children}
      {dot === "inline" ? <TipDot k={k} inline /> : dot ? <TipDot k={k} {...dot} /> : null}
    </Tag>
  );
}

// How far below a Metric tile its hover tooltip may reach: three lines of text and the gap. The tile's wrapper owns that much room through
// padding and an equal negative margin, so it takes no space in the layout, and it ignores the pointer outside the tile.
export const TILE_ROOM = 72;

// The root of a component that has none of its own to hold the wrapper and the panel (Table, Metric): a plain block with both inside.
// Without tooltips it returns the children unchanged, so the component draws as it always did.
// tile: the component is a tile in a row (Metric). Its tooltip has room below the tile, and when the row wraps (a Stack row with wrap) the open
// panel takes a line of its own below ALL the tiles, as wide as the row, so the other tiles keep their place and their height. In any other
// parent the panel sits under its tile.
export function TipBox({ tooltips, tile, children }) {
  const ref = useRef(null);
  const [flow, setFlow] = useState(null); // { gap } when the parent is a row that wraps
  useLayoutEffect(() => {
    const parent = tile && ref.current ? ref.current.parentElement : null;
    if (!parent) return;
    let f = null;
    try { f = rowFlow(window.getComputedStyle(parent)); } catch (e) {}
    setFlow((old) => (old && f && old.gap === f.gap ? old : f));
  }, [tile]);
  if (!hasTips(tooltips)) return children;
  if (!tile) return <div><Tipped tooltips={tooltips} keepFocus>{children}</Tipped></div>;
  const wrap = { display: "flex", flexDirection: "column", flex: flow ? "1 1 120px" : "1 1 auto", minWidth: 0, paddingBottom: TILE_ROOM, marginBottom: -TILE_ROOM, pointerEvents: "none" };
  const panel = flow ? { flex: "0 0 100%", order: 1, marginTop: flow.gap ? 0 : 8 } : undefined;
  return (
    <div ref={ref} style={flow ? { display: "contents" } : { display: "flex", flexDirection: "column", flex: "1 1 120px", minWidth: 0 }}>
      <Tipped tooltips={tooltips} keepFocus style={wrap} panelStyle={panel}>{children}</Tipped>
    </div>
  );
}

/* ------------------------------ the wrapper ------------------------------ */
// style: added to the wrapper's own style. panelStyle: added to the panel's. keepFocus: a sideways scroll keeps a keyboard-focused element's tooltip and places it again
// (Tab into a wide table scrolls the cell into view), instead of dropping it; the hover is dropped either way.
export function Tipped({ tooltips, style: wrapStyle, panelStyle, keepFocus, children }) {
  const list = useMemo(() => normalizeTooltips(tooltips), [tooltips]);
  const byKey = useMemo(() => {
    const m = new Map();
    list.forEach((a) => { if (!m.has(a.target)) m.set(a.target, a); });
    return m;
  }, [list]);
  const uid = useId().replace(/[^A-Za-z0-9]/g, "");
  const tipId = "tip-" + uid, panelId = "tip-panel-" + uid;
  const wrapRef = useRef(null), tipRef = useRef(null), textRef = useRef(null);
  const [hover, setHover] = useState(null); // { key, el, full }
  const [focus, setFocus] = useState(null); // keyboard focus only
  const [open, setOpen] = useState(null); // { key, label }
  const [pos, setPos] = useState(null); // { el, key, left, top, maxWidth, lines, maxHeight, hide }
  const [scrolled, setScrolled] = useState(0); // counts the scrolls that keepFocus answers by placing the tooltip again
  // Inside Tabs, React keeps this component when the tab changes and only hands it another diagram's tooltips. Whatever belonged to
  // the old ones (an open panel, a hover) must go, or the first tab's panel shows up on the second.
  const [mine, setMine] = useState(list);
  if (mine !== list) {
    setMine(list);
    setOpen(null);
    setHover(null);
    setFocus(null);
    setPos(null);
  }

  const shown = hover || focus;
  const tipKey = shown && byKey.has(shown.key) ? shown.key : null;
  const tipText = tipKey ? tooltipText(byKey.get(tipKey)) : "";
  const cur = open && byKey.has(open.key) ? open : null;

  useLayoutEffect(() => {
    if (!tipKey || !wrapRef.current || !tipRef.current || !shown.el) return;
    const box = tipRef.current, text = textRef.current;
    const w = wrapRef.current.getBoundingClientRect(), a = shown.el.getBoundingClientRect();
    // The placement asks how big the box is when its text may be at most so wide. Measure it that way with no cut, then put the
    // styles back exactly as React drew them (React only rewrites what changed in its own props).
    const saved = box.style.cssText, savedText = text ? text.style.cssText : "";
    const measure = (maxWidth) => {
      box.style.maxWidth = maxWidth + "px";
      box.style.maxHeight = "none";
      if (text) text.style.cssText = "";
      const r = box.getBoundingClientRect();
      return { width: r.width, height: r.height };
    };
    const p = placeTooltip(w, a, measure);
    box.style.cssText = saved;
    if (text) text.style.cssText = savedText;
    // An element scrolled out of the wrapper (a cell of a wide table) has no place for a tooltip: hide it until the element is back.
    const hide = keepFocus && (a.right < w.left || a.left > w.right || a.bottom < w.top || a.top > w.bottom);
    setPos((old) => (old && old.el === shown.el && old.key === tipKey && old.left === p.left && old.top === p.top && old.maxWidth === p.maxWidth && old.lines === p.lines && old.hide === hide ? old : { el: shown.el, key: tipKey, left: p.left, top: p.top, maxWidth: p.maxWidth, lines: p.lines, maxHeight: p.maxHeight, hide }));
  }, [tipKey, shown && shown.el, tipText, scrolled]);

  const ctx = useMemo(() => ({ byKey, tipKey, tipId, panelId, openKey: cur ? cur.key : null }), [byKey, tipKey, tipId, panelId, cur]);
  if (!byKey.size) return children;

  const entry = (el) => ({ key: el.getAttribute("data-tip"), el, full: el.getAttribute("data-tip-full") });
  // The element that takes the keyboard focus for a target: the one with a tabindex (the label pill of a link is only a second piece of it).
  const stopOf = (key) => {
    const root = wrapRef.current;
    if (!root) return null;
    for (const n of root.querySelectorAll("[data-tip]")) if (n.getAttribute("data-tip") === key && n.getAttribute("tabindex") === "0") return n;
    return null;
  };
  const toggle = (el) => {
    const key = el.getAttribute("data-tip");
    if (!byKey.has(key)) return;
    const opener = stopOf(key) || el;
    setOpen((o) => (o && o.key === key ? null : { key, label: el.getAttribute("data-tip-label") || key, opener }));
    // After a mouse click the focus may sit on the page background (a link, an svg piece): put it on the opener, so Escape reaches this
    // component and closes the panel.
    try {
      if (document.activeElement !== opener && typeof opener.focus === "function") opener.focus({ preventScroll: true });
    } catch (x) {}
  };
  // Closing from inside the panel (its close button, Escape) would drop focus on the page; give it back to the element that opened it.
  const closePanel = () => {
    const opener = cur && cur.opener;
    setOpen(null);
    try {
      if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus({ preventScroll: true });
    } catch (x) {}
  };
  const onKeyDown = (e) => {
    if (e.key === "Escape") {
      if (cur) {
        e.preventDefault(); // the app's own Escape handler (it stops a running turn) skips a key that is already handled
        closePanel();
      }
      return;
    }
    if (e.key === "Enter" || e.key === " ") {
      const el = hotOf(e.target);
      if (el && el === e.target && el.getAttribute("tabindex") === "0") {
        e.preventDefault();
        toggle(el);
      }
    }
  };
  const frame = {
    onMouseOver: (e) => {
      const el = hotOf(e.target);
      setHover((h) => (el && byKey.has(el.getAttribute("data-tip")) ? (h && h.el === el ? h : entry(el)) : null));
    },
    onMouseLeave: () => setHover(null),
    // the dots move under a sideways scroll; the next hover shows the tip again (a focused element keeps its tip when keepFocus is set)
    onScrollCapture: () => { setHover(null); if (keepFocus) setScrolled((n) => n + 1); else setFocus(null); },
    onFocus: (e) => {
      const el = hotOf(e.target);
      if (!el || el !== e.target || !byKey.has(el.getAttribute("data-tip"))) return;
      let visible = true;
      try { visible = el.matches(":focus-visible"); } catch (x) {}
      if (visible) setFocus(entry(el));
    },
    onBlur: () => setFocus(null),
    onClick: (e) => {
      const el = hotOf(e.target);
      if (el && byKey.has(el.getAttribute("data-tip"))) toggle(el);
      else setOpen(null); // the diagram background closes the panel
    },
    onKeyDown,
  };

  const placed = pos && shown && pos.el === shown.el && pos.key === tipKey && !pos.hide;
  const clamp = placed && pos.lines ? { display: "-webkit-box", WebkitBoxOrient: "vertical", WebkitLineClamp: pos.lines, overflow: "hidden" } : undefined;
  const tip = tipKey ? (
    <div
      ref={tipRef}
      id={tipId}
      role="tooltip"
      style={{
        position: "absolute", left: placed ? pos.left : 0, top: placed ? pos.top : 0, visibility: placed ? "visible" : "hidden",
        width: "max-content", maxWidth: placed ? pos.maxWidth : 280, maxHeight: placed && pos.lines ? pos.maxHeight : undefined, overflow: "hidden",
        boxSizing: "border-box", padding: "5px 8px", pointerEvents: "none", zIndex: 5,
        fontSize: 12.5, lineHeight: 1.4, overflowWrap: "anywhere", color: C.fg, background: C.card, border: "1px solid " + C.border,
        borderRadius: 6, boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
      }}
    >
      <div ref={textRef} style={clamp}>
        {shown.full ? <><span style={{ fontWeight: 600 }}>{shown.full}</span><br /></> : null}
        {tipText}
      </div>
    </div>
  ) : null;

  return (
    <Ctx.Provider value={ctx}>
      <div ref={wrapRef} style={{ position: "relative", minWidth: 0, ...wrapStyle }} {...frame}>
        {children}
        {tip}
      </div>
      {cur ? <Panel a={byKey.get(cur.key)} label={cur.label} id={panelId} onClose={closePanel} onKeyDown={onKeyDown} extra={panelStyle} /> : null}
    </Ctx.Provider>
  );
}

/* ------------------------------ the detail panel ------------------------------ */
const smallButton = { font: "inherit", fontSize: 12, color: C.muted, background: "transparent", border: "1px solid " + C.border, borderRadius: 6, padding: "0 8px", cursor: "pointer", lineHeight: 1.6 };

function LinkLine({ url, label }) {
  const [copied, setCopied] = useState("");
  const first = checkLink(url);
  const muted = { marginTop: 8, fontSize: 12.5, color: C.muted };
  if (!first.ok) return <div style={muted}>Link not shown: only http:// and https:// links are allowed.</div>;
  const live = bridge();
  // The renderer checks the link again at click time, whatever the validator said.
  const go = () => {
    const again = checkLink(url), b = bridge();
    if (!again.ok || !b) return;
    try {
      const r = b.openExternal(again.url);
      if (r && typeof r.catch === "function") r.catch(() => {});
    } catch (e) {}
  };
  const copy = () => {
    setCopied(copyText(first.url) ? "Copied" : "Copy blocked");
    setTimeout(() => setCopied(""), 1500);
  };
  const urlStyle = { fontFamily: MONO, fontSize: 12, overflowWrap: "anywhere", userSelect: "text", minWidth: 0 };
  return (
    <div style={{ ...muted, display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "2px 8px" }}>
      <span>Link</span>
      {label ? <span style={{ color: C.fg, fontWeight: 600 }}>{label}</span> : null}
      {live ? (
        <button type="button" data-tip-open-link="" onClick={go} title="Open in your browser" style={{ ...urlStyle, color: C.accent, background: "transparent", border: 0, padding: 0, cursor: "pointer", textDecoration: "underline", textAlign: "left" }}>{first.url}</button>
      ) : (
        <span data-tip-link="" style={{ ...urlStyle, color: C.fg }}>{first.url}</span>
      )}
      <button type="button" data-tip-copy-link="" onClick={copy} style={smallButton}>{copied || "Copy"}</button>
    </div>
  );
}

function Panel({ a, label, id, onClose, onKeyDown, extra }) {
  const col = toneColor(a.tone);
  return (
    <div
      id={id}
      role="region"
      aria-label={"Details: " + label}
      data-tip-panel=""
      tabIndex={-1}
      onKeyDown={onKeyDown}
      style={{ outline: "none", marginTop: 8, boxSizing: "border-box", minWidth: 0, padding: "8px 12px", border: "1px solid " + C.border, borderLeft: "3px solid " + col, borderRadius: 8, background: C.card, color: C.fg, fontSize: 13, lineHeight: 1.5, userSelect: "text", ...extra }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 8, background: col, flex: "none" }} />
        <span style={{ fontWeight: 600, flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{label}</span>
        <button type="button" data-tip-close="" onClick={onClose} aria-label="Close details" style={{ ...smallButton, fontSize: 15, lineHeight: 1.3, padding: "0 7px" }}>{"\u00d7"}</button>
      </div>
      {panelText(a) ? <div style={{ marginTop: 6, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{panelText(a)}</div> : null}
      {a.code ? <div style={{ marginTop: 8 }}><CodeView code={a.code} language={a.language || ""} /></div> : null}
      {a.link ? <LinkLine url={a.link} label={a.linkLabel} /> : null}
    </div>
  );
}
