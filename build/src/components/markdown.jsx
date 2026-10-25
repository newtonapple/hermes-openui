// Tiny markdown renderer -> React elements (no innerHTML, no deps).
// Supports: #..###### headings, paragraphs, **bold**, *italic*, `code`, [text](url) (shown, not navigable),
// fenced code, -/*/1. lists, > quotes, --- rules, GitHub pipe tables.
import React from "react";
import { C, MONO } from "../theme.js";
import { CodeView } from "./code.jsx";

function inline(text, key) {
  const out = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const k = `${key}-${i++}`;
    if (m[1]) out.push(<code key={k} style={{ fontFamily: MONO, fontSize: "0.9em", background: C.soft, padding: "1px 5px", borderRadius: 4 }}>{t.slice(1, -1)}</code>);
    else if (m[2] || m[3]) out.push(<strong key={k}>{inline(t.slice(2, -2), k)}</strong>);
    else if (m[4]) out.push(<em key={k}>{inline(t.slice(1, -1), k)}</em>);
    else {
      const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(t);
      out.push(<span key={k} title={mm[2]} style={{ color: C.accent, textDecoration: "underline", textUnderlineOffset: 2 }}>{mm[1]}</span>);
    }
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const splitRow = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function renderMarkdown(src) {
  const lines = String(src).replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0, n = 0;
  const key = () => `b${n++}`;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    let m;
    if ((m = /^```\s*([\w+-]*)\s*$/.exec(line))) {
      const buf = []; i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) buf.push(lines[i++]);
      i++;
      blocks.push(<CodeView key={key()} code={buf.join("\n")} language={m[1] || ""} />);
    } else if ((m = /^(#{1,6})\s+(.*)$/.exec(line))) {
      const lvl = m[1].length;
      const size = [22, 18, 16, 14.5, 14, 13][lvl - 1];
      blocks.push(<div key={key()} style={{ fontSize: size, fontWeight: 650, margin: "6px 0 2px", lineHeight: 1.3 }}>{inline(m[2], "h")}</div>);
      i++;
    } else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      blocks.push(<hr key={key()} style={{ border: 0, borderTop: `1px solid ${C.border}`, margin: "8px 0", width: "100%" }} />);
      i++;
    } else if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(<div key={key()} style={{ borderLeft: `3px solid ${C.border}`, paddingLeft: 12, color: C.muted, display: "flex", flexDirection: "column", gap: 6 }}>{renderMarkdown(buf.join("\n"))}</div>);
    } else if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*+]|\d+[.)])\s+/, ""));
      const Tag = ordered ? "ol" : "ul";
      blocks.push(<Tag key={key()} style={{ margin: 0, paddingLeft: 22, display: "flex", flexDirection: "column", gap: 3 }}>{items.map((t, j) => <li key={j} style={{ lineHeight: 1.5 }}>{inline(t, `li${j}`)}</li>)}</Tag>);
    } else if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = splitRow(line); i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(splitRow(lines[i++]));
      blocks.push(
        <div key={key()} style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr>{head.map((h, j) => <th key={j} style={{ textAlign: "left", padding: "5px 10px", borderBottom: `1px solid ${C.border}`, color: C.muted }}>{inline(h, `th${j}`)}</th>)}</tr></thead>
            <tbody>{rows.map((r, a) => <tr key={a}>{r.map((c, j) => <td key={j} style={{ padding: "5px 10px", borderBottom: `1px solid ${C.border}` }}>{inline(c, `td${a}-${j}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
    } else {
      const buf = [];
      while (i < lines.length && lines[i].trim() && !/^(```|#{1,6}\s|\s*>|\s*([-*+]|\d+[.)])\s+)/.test(lines[i])) buf.push(lines[i++]);
      blocks.push(<p key={key()} style={{ margin: 0, lineHeight: 1.55 }}>{inline(buf.join(" "), "p")}</p>);
    }
  }
  return blocks;
}
