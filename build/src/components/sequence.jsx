// Sequence diagram: participants as columns with dashed lifelines, messages as arrows from top to bottom, drawn as one SVG.
// The layout is a pure function (sequence-layout.js, tested in Node); this file only draws what it returns.
import React from "react";
import { C, TONES } from "../theme.js";
import { layoutSequence, seqData } from "./sequence-layout.js";
import { Tipped, Hot, tippedKeys } from "./tooltips.jsx";

export { seqData };

const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const n1 = (v) => Math.round(v * 10) / 10;

// Small inline glyphs on a 16 x 16 grid, one per participant kind (the same drawing style as InfraMap).
const GLYPHS = {
  actor: [["circle", { cx: 8, cy: 4.8, r: 2.6 }], ["path", { d: "M3 14c0-3 2.2-5 5-5s5 2 5 5" }]],
  service: [["path", { d: "M8 1.5l5.5 3v7L8 14.5l-5.5-3v-7z" }], ["path", { d: "M2.5 4.5L8 7.5l5.5-3M8 7.5v7" }]],
  database: [["ellipse", { cx: 8, cy: 3.8, rx: 5, ry: 2 }], ["path", { d: "M3 3.8v8.4c0 1.1 2.2 2 5 2s5-.9 5-2V3.8M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" }]],
  queue: [
    ["rect", { x: 1.5, y: 5.5, width: 3.4, height: 5, rx: 0.8 }],
    ["rect", { x: 6.3, y: 5.5, width: 3.4, height: 5, rx: 0.8 }],
    ["rect", { x: 11.1, y: 5.5, width: 3.4, height: 5, rx: 0.8 }],
  ],
  external: [["path", { d: "M12.5 9v3.5a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1H7" }], ["path", { d: "M9.5 2.5h4v4M13.5 2.5L7.5 8.5" }]],
};

const glyph = (kind, x, y) => (
  <g transform={"translate(" + n1(x) + " " + n1(y) + ") scale(1.1)"} fill="none" stroke={C.accent} strokeWidth={1.25} strokeLinecap="round" strokeLinejoin="round">
    {GLYPHS[has(GLYPHS, kind) ? kind : "service"].map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs }))}
  </g>
);

function Warn({ items }) {
  if (!items.length) return null;
  return <div style={{ marginTop: 6, fontSize: 12, color: TONES.bad }}>{items.map((t, i) => <div key={i}>{"\u26a0 " + t}</div>)}</div>;
}

const HALO = { stroke: C.card, strokeWidth: 4, paintOrder: "stroke", strokeLinejoin: "round" };
const LINE = C.fg;
const FRAME = "color-mix(in srgb, " + C.fg + " 45%, transparent)";
const TAB_FILL = "color-mix(in srgb, " + C.fg + " 9%, " + C.card + ")";
const NOTE_FILL = "color-mix(in srgb, " + C.accent + " 10%, " + C.card + ")";
const NOTE_STROKE = "color-mix(in srgb, " + C.accent + " 45%, transparent)";
const BAR_FILL = "color-mix(in srgb, " + C.accent + " 22%, " + C.card + ")";

export function SequenceDiagramView({ participants, steps, title, numbered, tooltips }) {
  const lay = layoutSequence({ participants, steps, numbered });
  const marked = tippedKeys(tooltips);
  const vb = lay.viewBox;
  const w = vb[2];

  // Frames and dividers sit under the activation bars; the tabs and divider labels sit over them, so a bar never hides a word.
  const frames = lay.groups.map((g, i) => (
    <g key={"g" + i}>
      <rect x={g.x} y={g.y} width={g.w} height={g.h} rx={4} fill="none" stroke={FRAME} strokeWidth={1} />
      {g.divider ? <line x1={g.x} y1={g.divider.y} x2={g.x + g.w} y2={g.divider.y} stroke={FRAME} strokeWidth={1} strokeDasharray="5 4" /> : null}
    </g>
  ));
  const tabs = lay.groups.map((g, i) => (
    <g key={"t" + i}>
      {g.full !== g.label ? <title>{g.kind + " " + g.full}</title> : null}
      <path d={"M" + g.tab.x + " " + g.tab.y + "h" + g.tab.w + "v" + (g.tab.h - 6) + "l-6 6h-" + (g.tab.w - 6) + "z"} fill={TAB_FILL} stroke={FRAME} strokeWidth={1} />
      <text x={g.tab.x + 8} y={g.tab.y + 12.5} fontSize={11} fill={C.fg}><tspan fontWeight={700}>{g.kind}</tspan>{" " + g.label}</text>
      {g.divider ? <text x={g.x + 8} y={g.divider.y + 12} fontSize={11} fill={C.muted} {...HALO}>{g.divider.label}</text> : null}
    </g>
  ));

  const lifelines = lay.lifelines.map((l, i) => (
    <line key={"l" + i} x1={l.x} y1={l.y1} x2={l.x} y2={l.y2} stroke={C.muted} strokeOpacity={0.55} strokeWidth={1} strokeDasharray="4 4" />
  ));

  const bars = lay.activations.map((b, i) => (
    <rect key={"b" + i} x={b.x} y={b.y1} width={b.w} height={n1(b.y2 - b.y1)} rx={1.5} fill={BAR_FILL} stroke={C.accent} strokeWidth={1} />
  ));

  const msgs = lay.messages.map((m, i) => {
    const lb = m.labelBox;
    const name = m.from + " \u2192 " + m.to + ": " + m.full;
    return (
      <Hot key={"m" + i} k={m.id || ""} what="message" label={name} full={m.full !== m.label ? m.full : undefined} shape={{ t: "path", d: m.d }} marker={[n1(lb.x + lb.w + 3), n1(lb.y + 1)]}>
        <g data-seq-id={m.id || undefined}>
          {m.id && marked.has(m.id) ? null : <title>{name}</title>}
          <path d={m.d} fill="none" stroke={LINE} strokeOpacity={0.85} strokeWidth={1.4} strokeDasharray={m.dashed ? "6 4" : undefined} strokeLinecap="round" />
          <path d={m.headD} fill={m.head === "filled" ? LINE : "none"} fillOpacity={0.85} stroke={LINE} strokeOpacity={0.85} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
          <text x={m.self ? lb.x : n1(lb.x + lb.w / 2)} y={n1(lb.y + 11)} textAnchor={lb.anchor} fontSize={12} fill={C.fg} {...HALO}>
            {m.number != null ? <tspan fill={C.muted}>{m.number + ". "}</tspan> : null}
            {m.label}
          </text>
        </g>
      </Hot>
    );
  });

  const notes = lay.notes.map((q, i) => (
    <g key={"n" + i}>
      <rect x={q.x} y={q.y} width={q.w} height={q.h} rx={6} fill={NOTE_FILL} stroke={NOTE_STROKE} strokeWidth={1} />
      <text fontSize={11.5} fill={C.fg}>
        {q.lines.map((ln, j) => <tspan key={j} x={n1(q.x + 8)} y={n1(q.y + 6 + 11 + j * 14)}>{ln}</tspan>)}
      </text>
    </g>
  ));

  const heads = lay.columns.map((c, i) => (
    <Hot key={"h" + i} k={c.id} label={c.full || c.label} full={c.full !== c.label ? c.full : undefined} shape={{ t: "rect", x: c.x, y: c.y, w: c.w, h: c.h, rx: 8 }} marker={[c.x + c.w - 2, c.y + 2]}>
      <g>
        {marked.has(c.id) ? null : <title>{(c.full !== c.label ? c.full + " \u00b7 " : "") + c.id + (c.kind ? " \u00b7 " + c.kind : "")}</title>}
        <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={8} fill={C.card} stroke={C.border} strokeWidth={1} strokeDasharray={c.kind === "external" ? "4 3" : undefined} />
        {glyph(c.kind, c.x + 9, c.y + c.h / 2 - 9.5)}
        <text x={c.x + 34} y={c.y + c.h / 2 + 4.5} fontSize={12.5} fontWeight={600} fill={C.fg}>{c.label}</text>
      </g>
    </Hot>
  ));

  return (
    <div style={{ minWidth: 0 }}>
      {title ? <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{title}</div> : null}
      <Tipped tooltips={tooltips}>
      <div style={{ overflowX: "auto" }}>
        <svg viewBox={vb.join(" ")} role={marked.size ? "group" : "img"} aria-label={title || "Sequence diagram"} style={{ width: "100%", maxWidth: w, minWidth: Math.min(w, Math.round(w * 0.78)), height: "auto", display: "block" }}>
          {lifelines}
          {frames}
          {bars}
          {tabs}
          {msgs}
          {notes}
          {heads}
        </svg>
      </div>
      </Tipped>
      <Warn items={lay.warns} />
    </div>
  );
}

