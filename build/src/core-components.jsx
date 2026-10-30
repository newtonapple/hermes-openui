// Always-on widget components (in every widget). Optional components live in packs/*.jsx and are only embedded
// into a widget that uses them. The prompt/validator see all of them through library.jsx.
import React, { useState } from "react";
import { action, defineComponent, useTriggerAction } from "@openuidev/react-lang";
import { z } from "zod/v4";

import { C, TONES } from "./theme.js";
import { Tooltip } from "./components/tooltip-schema.js";
import { Tipped, TipBox, HotBox, TipDot, useTipHas, hasTips } from "./components/tooltips.jsx";

const GAP = { none: 0, xs: 4, s: 8, m: 12, l: 20, xl: 28 };

const Stack = defineComponent({
  name: "Stack",
  description:
    'Flex container. direction "row"|"column" (default column). gap "none"|"xs"|"s"|"m"|"l"|"xl" (default m). wrap: true lets a row wrap.',
  props: z.object({
    children: z.array(z.any()),
    direction: z.enum(["row", "column"]).optional(),
    gap: z.enum(["none", "xs", "s", "m", "l", "xl"]).optional(),
    wrap: z.boolean().optional(),
  }),
  component: ({ props, renderNode }) => (
    <div
      style={{
        display: "flex",
        flexDirection: props.direction ?? "column",
        gap: GAP[props.gap ?? "m"],
        flexWrap: props.wrap ? "wrap" : undefined,
        alignItems: props.direction === "row" ? "stretch" : undefined,
      }}
    >
      {renderNode(props.children)}
    </div>
  ),
});

const Text = defineComponent({
  name: "Text",
  description: 'Text. variant "title"|"heading"|"body"|"muted"|"code" (default body).',
  props: z.object({
    text: z.string(),
    variant: z.enum(["title", "heading", "body", "muted", "code"]).optional(),
  }),
  component: ({ props }) => {
    const v = props.variant ?? "body";
    const style = {
      title: { fontSize: 20, fontWeight: 650, lineHeight: 1.25 },
      heading: { fontSize: 15, fontWeight: 600 },
      body: { fontSize: 14, lineHeight: 1.5 },
      muted: { fontSize: 12.5, color: C.muted },
      code: { fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12.5 },
    }[v];
    return <div style={{ margin: 0, ...style }}>{props.text}</div>;
  },
});

const Card = defineComponent({
  name: "Card",
  description: "Bordered panel with an optional title. Put related content inside.",
  props: z.object({ children: z.array(z.any()), title: z.string().optional() }),
  component: ({ props, renderNode }) => (
    <div
      style={{
        border: `1px solid ${C.border}`,
        borderRadius: 10,
        padding: 14,
        background: "color-mix(in srgb, " + C.card + " 60%, transparent)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        flex: "1 1 160px",
        minWidth: 0,
      }}
    >
      {props.title ? <div style={{ fontSize: 13, fontWeight: 600, color: C.muted }}>{props.title}</div> : null}
      {renderNode(props.children)}
    </div>
  ),
});

const Metric = defineComponent({
  name: "Metric",
  description:
    'KPI tile: label, value (string), optional delta text, optional tone "good"|"warn"|"bad"|"neutral" colouring the delta. tooltips: Tooltip[] is the LAST argument (write null for delta and tone if skipped, e.g. Metric("Latency", "120 ms", null, null, [t1])) and adds a hover tooltip with an optional click-to-open panel; one at most, its target is its own label.',
  props: z.object({
    label: z.string(),
    value: z.string(),
    delta: z.string().optional(),
    tone: z.enum(["good", "warn", "bad", "neutral"]).optional(),
    tooltips: z.array(Tooltip.ref).optional(),
  }),
  component: ({ props }) => {
    const tipped = hasTips(props.tooltips);
    return (
      <TipBox tooltips={props.tooltips} tile>
        <HotBox
          k={props.label}
          label={props.label}
          name={props.label + ": " + props.value + (props.delta ? ", " + props.delta : "")}
          style={{
            border: `1px solid ${C.border}`,
            borderRadius: 10,
            padding: "10px 14px",
            flex: tipped ? "1 1 auto" : "1 1 120px", // a tile with a tooltip sits in a wrapper that is the flex item and fills it
            minWidth: 0,
            ...(tipped ? { pointerEvents: "auto" } : null), // its wrapper ignores the pointer outside the tile (tooltips.jsx TILE_ROOM)
          }}
        >
          <div style={{ fontSize: 12, color: C.muted }}>{props.label}</div>
          <div style={{ fontSize: 24, fontWeight: 650, lineHeight: 1.2 }}>{props.value}</div>
          {props.delta ? (
            <div style={{ fontSize: 12, color: TONES[props.tone ?? "neutral"] }}>{props.delta}</div>
          ) : null}
        </HotBox>
      </TipBox>
    );
  },
});

const Table = defineComponent({
  name: "Table",
  description:
    "Data table. columns: array of header strings. rows: array of rows, each an array of strings/numbers matching columns. tooltips: Tooltip[] is the LAST argument, Table(columns, rows, [t1]), and adds a hover tooltip with an optional click-to-open panel; target is `row:3` (1-based data row), `col:status` (a column header) or `cell:3.status` (row number, a dot, then the header); duplicate headers make col: and cell: targets ambiguous.",
  props: z.object({
    columns: z.array(z.string()),
    rows: z.array(z.array(z.union([z.string(), z.number()]))),
    tooltips: z.array(Tooltip.ref).optional(),
  }),
  component: ({ props }) => (
    <TipBox tooltips={props.tooltips}>
      <TableView columns={props.columns} rows={props.rows} />
    </TipBox>
  ),
});

// The table itself. Inside a Tipped, a row, a header or a cell with a tooltip is marked through HotBox (the same tag, so a <tr> stays a <tr>
// directly under <tbody>, and each part keeps its own role). The dot of a header or a cell sits right after its text; a row's dot sits after
// the text of its first cell, because only a cell can hold it.
function TableView({ columns, rows }) {
  const has = useTipHas();
  const TH = { textAlign: "left", padding: "6px 10px", color: C.muted, fontWeight: 600, borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap" };
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c, i) => (
              <HotBox as="th" key={i} k={"col:" + c} label={c} inset dot="inline" style={TH}>
                {c}
              </HotBox>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <HotBox as="tr" key={i} k={"row:" + (i + 1)} label={"Row " + (i + 1)} inset dot={null}>
              {r.map((cell, j) => {
                const cellKey = j < columns.length ? "cell:" + (i + 1) + "." + columns[j] : "";
                const lead = j === 0 && has("row:" + (i + 1));
                return (
                  <HotBox as="td" key={j} k={cellKey} label={"Row " + (i + 1) + ", " + columns[j]} inset dot="inline" style={{ padding: "6px 10px", borderBottom: `1px solid ${C.border}` }}>
                    {String(cell)}
                    {lead ? <TipDot k={"row:" + (i + 1)} inline /> : null}
                  </HotBox>
                );
              })}
            </HotBox>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// One bar. With a tooltip its dot sits inside the bar at the top, centred: that spot is never the value above or the label below, whatever the
// width of the column, and it follows the bar. (A bar so short that the dot is taller than it is drawn the same way.)
function Bar({ k, height }) {
  const has = useTipHas();
  return (
    <div style={{ width: "100%", maxWidth: 48, height, background: C.accent, borderRadius: "4px 4px 0 0", position: has(k) ? "relative" : undefined }}>
      <TipDot k={k} top={1} left="50%" marginLeft={-3} />
    </div>
  );
}

const BarChart = defineComponent({
  name: "BarChart",
  description:
    "Vertical bar chart. labels and values are parallel arrays; optional title and unit suffix (e.g. \"%\"). tooltips: Tooltip[] is the LAST argument (write null for title and unit if skipped, e.g. BarChart(labels, values, null, null, [t1])) and adds a hover tooltip with an optional click-to-open panel; target is a bar's label (the whole column), so duplicate labels are ambiguous.",
  props: z.object({
    labels: z.array(z.string()),
    values: z.array(z.number()),
    title: z.string().optional(),
    unit: z.string().optional(),
    tooltips: z.array(Tooltip.ref).optional(),
  }),
  component: ({ props }) => {
    const { labels, values, unit = "" } = props;
    const max = Math.max(1, ...values);
    const H = 120;
    return (
      <div>
        {props.title ? <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{props.title}</div> : null}
        <Tipped tooltips={props.tooltips}>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: H + 36 }}>
            {values.map((v, i) => (
              <HotBox key={i} k={String(labels[i] ?? "")} label={String(labels[i] ?? "")} name={labels[i] + ": " + v + unit} dot={null} style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end" }}>
                <div style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}>
                  {v}
                  {unit}
                </div>
                <Bar k={String(labels[i] ?? "")} height={Math.max(2, (v / max) * H)} />
                <div style={{ fontSize: 11, color: C.muted, marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "100%" }}>
                  {labels[i]}
                </div>
              </HotBox>
            ))}
          </div>
        </Tipped>
      </div>
    );
  },
});

const Callout = defineComponent({
  name: "Callout",
  description: 'Highlighted note. tone "info"|"success"|"warn"|"error" (default info).',
  props: z.object({
    text: z.string(),
    tone: z.enum(["info", "success", "warn", "error"]).optional(),
  }),
  component: ({ props }) => {
    const color = { info: TONES.info, success: TONES.good, warn: TONES.warn, error: TONES.bad }[props.tone ?? "info"];
    return (
      <div
        style={{
          borderLeft: `3px solid ${color}`,
          background: `color-mix(in srgb, ${color} 12%, transparent)`,
          padding: "8px 12px",
          borderRadius: 6,
          fontSize: 13.5,
          lineHeight: 1.45,
        }}
      >
        {props.text}
      </div>
    );
  },
});

const Button = defineComponent({
  name: "Button",
  description:
    'Clickable button. Second arg is the action, e.g. Button("Restart vllm", @ToAssistant("Restart the vllm service")). @ToAssistant sends that text to the agent as a new turn (max 500 chars).',
  props: z.object({ label: z.string(), action: action().optional() }),
  component: ({ props }) => {
    const trigger = useTriggerAction();
    return (
      <button
        onClick={() => trigger(props.label, undefined, props.action)}
        style={{
          font: "inherit",
          fontSize: 13,
          fontWeight: 550,
          color: C.fg,
          background: "transparent",
          border: `1px solid ${C.accent}`,
          borderRadius: 8,
          padding: "6px 14px",
          cursor: "pointer",
          alignSelf: "flex-start",
        }}
      >
        {props.label}
      </button>
    );
  },
});

const TabItem = defineComponent({
  name: "TabItem",
  description: "One tab: label and its content (array of components). Only valid inside Tabs.",
  props: z.object({ label: z.string(), content: z.array(z.any()) }),
  component: () => null,
});

const Tabs = defineComponent({
  name: "Tabs",
  description: "Tabbed container. items: array of TabItem.",
  props: z.object({ items: z.array(TabItem.ref) }),
  component: ({ props, renderNode }) => {
    const [active, setActive] = useState(0);
    const items = props.items ?? [];
    const cur = items[Math.min(active, items.length - 1)];
    return (
      <div>
        <div style={{ display: "flex", gap: 4, borderBottom: `1px solid ${C.border}`, marginBottom: 10 }}>
          {items.map((it, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              style={{
                font: "inherit",
                fontSize: 13,
                color: i === active ? C.fg : C.muted,
                background: "transparent",
                border: 0,
                borderBottom: `2px solid ${i === active ? C.accent : "transparent"}`,
                padding: "6px 10px",
                cursor: "pointer",
              }}
            >
              {it.props.label}
            </button>
          ))}
        </div>
        {cur ? renderNode(cur.props.content) : null}
      </div>
    );
  },
});

const Image = defineComponent({
  name: "Image",
  description:
    'Image. src is an absolute local file path (png/jpg/webp/gif/svg; inlined automatically by the renderer, max 100 KB each, less if the widget also has charts or a map) or a data: URI. Remote URLs are NOT guaranteed to load. Optional alt and caption. tooltips: Tooltip[] is the LAST argument (write null for alt and caption if skipped, e.g. Image(src, null, null, [t1])) and adds a hover tooltip with an optional click-to-open panel; one at most, its target is the word image.',
  props: z.object({ src: z.string(), alt: z.string().optional(), caption: z.string().optional(), tooltips: z.array(Tooltip.ref).optional() }),
  component: ({ props }) => {
    const [bad, setBad] = useState(false);
    const pic = bad ? (
      <div style={{ border: `1px dashed ${C.border}`, borderRadius: 10, padding: 18, color: C.muted, fontSize: 13 }}>Image failed to load{props.alt ? `: ${props.alt}` : ""}</div>
    ) : (
      <img src={props.src} alt={props.alt ?? ""} onError={() => setBad(true)} style={{ maxWidth: "100%", height: "auto", borderRadius: 10, border: `1px solid ${C.border}`, display: "block", alignSelf: "flex-start" }} />
    );
    return (
      <figure style={{ margin: 0, display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
        <Tipped tooltips={props.tooltips} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {hasTips(props.tooltips) ? <HotBox k="image" label={props.alt || "Image"} style={{ alignSelf: "flex-start", maxWidth: "100%", borderRadius: 10 }}>{pic}</HotBox> : pic}
          {props.caption ? <figcaption style={{ fontSize: 12.5, color: C.muted }}>{props.caption}</figcaption> : null}
        </Tipped>
      </figure>
    );
  },
});

// Tooltip is defined once (components/tooltip-schema.js) and lives here, not in a pack: every diagram pack refers to it, and a
// component registered by two packs would make createLibrary throw.
export const coreComponents = [Stack, Text, Card, Metric, Table, BarChart, Callout, Button, TabItem, Tabs, Image, Tooltip];
