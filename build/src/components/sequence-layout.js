// Sequence diagram layout: a PURE function (no React, no DOM, no imports) so Node can load and test it directly
// (tests/test_sequence_builtin.py). The renderer is components/sequence.jsx; the validator checks are components/sequence-check.js.
//
// Input: the parsed props of SequenceDiagram (seqData turns the parser's elements into plain data) or plain data built by hand:
//   { participants: [{ id, label, kind }], steps: [msg | note | group], numbered }
//   msg   { t: "msg", from, to, label, style: "sync" | "async" | "return", id }
//   note  { t: "note", over, text, to }
//   group { t: "group", kind: "alt" | "opt" | "loop" | "par", label, steps, elseSteps, elseLabel }
// Output: positions and sizes of columns, lifelines, messages, activation bars, notes and group frames, plus a view box.

export const KINDS = ["actor", "service", "database", "queue", "external"];
export const STYLES = ["sync", "async", "return"];
export const GROUP_KINDS = ["alt", "opt", "loop", "par"];
export const MAX_PARTICIPANTS = 10;
export const MAX_STEPS = 100;
export const MAX_DEPTH = 3;

const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const str = (v) => (v == null ? "" : String(v));
const list = (v) => (Array.isArray(v) ? v : []);
const plain = (x) => (x && typeof x === "object" && x.props ? x.props : x);
const oneLine = (s) => str(s).replace(/\s+/g, " ").trim();

// Width units: the text widths below are estimates for Latin text. A code point at or above U+2E80 (CJK, Hangul, fullwidth forms)
// and the common emoji blocks are about twice as wide, so they count 2; everything else counts 1.
const cpUnits = (cp) => (cp >= 0x2e80 || (cp >= 0x2600 && cp <= 0x27bf) || (cp >= 0x2b00 && cp <= 0x2bff) ? 2 : 1);
const units = (s) => { let u = 0; for (const ch of str(s)) u += cpUnits(ch.codePointAt(0)); return u; };
// The longest head of s that fits in `max` units (always at least one code point, so a loop over a long word ends).
const headUnits = (s, max) => {
  let u = 0, i = 0;
  for (const ch of s) {
    const w = cpUnits(ch.codePointAt(0));
    if (i && u + w > max) break;
    u += w; i += ch.length;
  }
  return i;
};
const clip = (s, n) => { s = oneLine(s); return units(s) > n ? s.slice(0, headUnits(s, n - 1)) + "\u2026" : s; };
const n1 = (v) => Math.round(v * 10) / 10;

export const LIMITS = { participant: 22, label: 48, group: 40, divider: 40 };

// Geometry (px at 1:1). Text widths are estimates (characters x an average advance), as in the other diagrams.
const CH = 6.4; // message label, 12 px
const CH_NOTE = 6.2; // note text, 11.5 px
const HDR_H = 36;
const HDR_MIN = 96;
const HDR_GAP = 24; // space between two neighbouring header boxes
const TOP = 10; // from the header to the first row
const ROW_ABOVE = 22; // from the top of a row to its arrow: room for the label
const ROW_BELOW = 12;
const SELF_ABOVE = 14;
const SELF_H = 16; // height of a self-call loop
const SELF_W = 26; // how far the loop reaches right of the lifeline
const BAR_W = 8;
const BAR_OFF = 5; // nested activation bars sit this much further right
const TAB_H = 18;
const FRAME_PAD = 12;
const NOTE_PAD = 14; // a note over two lifelines reaches this far past them
const NOTE_LINE = 14;
const HEAD = 9;

/* ------------------------------ data ------------------------------ */
function normStep(x) {
  if (x && typeof x === "object" && x.t) return x; // already plain
  const type = x && x.typeName;
  const p = plain(x) || {};
  if (type === "SeqMessage") {
    return { t: "msg", from: str(p.from), to: str(p.to), label: str(p.label), style: STYLES.includes(p.style) ? p.style : "sync", id: p.id == null ? null : str(p.id) };
  }
  if (type === "SeqNote") return { t: "note", over: str(p.over), text: str(p.text), to: p.to == null || p.to === "" ? null : str(p.to) };
  if (type === "SeqGroup") {
    return {
      t: "group", kind: GROUP_KINDS.includes(p.kind) ? p.kind : "alt", label: str(p.label), steps: list(p.steps).map(normStep),
      elseSteps: Array.isArray(p.elseSteps) ? p.elseSteps.map(normStep) : null, elseLabel: p.elseLabel == null ? null : str(p.elseLabel),
    };
  }
  return { t: "bad", typeName: type ? str(type) : typeof x };
}

// The parsed SequenceDiagram props (elements with typeName and props) reduced to plain data.
export function seqData(props) {
  const p = props || {};
  return {
    participants: list(p.participants).map((x) => { const q = plain(x) || {}; return { id: str(q.id), label: str(q.label), kind: q.kind }; }),
    steps: list(p.steps).map(normStep),
    title: p.title == null ? "" : str(p.title),
    numbered: p.numbered !== false,
  };
}

/* ---------------------------- activations ---------------------------- */
// msgs: drawn messages in order of appearance, nested groups included. A "sync" opens a bar on its receiver; the next "return"
// from that receiver back to the sender closes the innermost such open sync. Returns [openIndex, closeIndex] pairs.
export function matchActivations(msgs) {
  const open = []; // indexes of syncs that wait for a return
  const pairs = [];
  list(msgs).forEach((m, i) => {
    if (m.style === "sync") { open.push(i); return; }
    if (m.style !== "return") return;
    for (let k = open.length - 1; k >= 0; k--) {
      const o = msgs[open[k]];
      if (o.to === m.from && o.from === m.to) { pairs.push([open[k], i]); open.splice(k, 1); break; }
    }
  });
  return pairs.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
}

/* ------------------------------- text ------------------------------- */
export function wrapText(text, maxChars) {
  const max = Math.max(4, Math.floor(maxChars));
  const out = [];
  str(text).split("\n").forEach((para) => {
    const words = para.split(/\s+/).filter(Boolean);
    let cur = "";
    words.forEach((w0) => {
      let w = w0;
      while (units(w) > max) {
        if (cur) { out.push(cur); cur = ""; }
        const k = headUnits(w, max);
        out.push(w.slice(0, k));
        w = w.slice(k);
      }
      if (!cur) cur = w;
      else if (units(cur + " " + w) <= max) cur += " " + w;
      else { out.push(cur); cur = w; }
    });
    out.push(cur);
  });
  return out.length ? out : [""];
}

const tw = (s, px) => units(s) * px;

/* ------------------------------ layout ------------------------------ */
export function layoutSequence(data) {
  const d = data || {};
  const warns = [];
  const numbered = d.numbered !== false;

  // columns
  const cols = [];
  const byId = new Map();
  list(d.participants).forEach((p0) => {
    const p = plain(p0) || {};
    const id = str(p.id);
    if (byId.has(id)) { warns.push("duplicate participant id \"" + id + "\" (every SeqParticipant id must be unique)"); return; }
    const label = clip(p.label || id, LIMITS.participant);
    const col = { i: cols.length, id, label, full: oneLine(p.label || id), kind: KINDS.includes(p.kind) ? p.kind : "service", w: Math.max(HDR_MIN, Math.ceil(34 + tw(label, 6.9) + 12)) };
    cols.push(col);
    byId.set(id, col);
  });
  const known = cols.map((c) => c.id).join(", ");
  const idx = (id) => (byId.has(id) ? byId.get(id).i : -1);

  // keep only what can be drawn: drop messages and notes that name an unknown participant, and anything that is not a step
  const msgsFlat = [];
  const prune = (steps, where) => {
    const out = [];
    list(steps).forEach((s0, n) => {
      const s = normStep(s0);
      if (s.t === "msg") {
        const a = idx(s.from), b = idx(s.to);
        if (a < 0 || b < 0) { warns.push("message \"" + clip(s.label, 30) + "\" uses unknown participant id \"" + (a < 0 ? s.from : s.to) + "\" (known ids: " + known + ")"); return; }
        const m = { t: "msg", a, b, from: s.from, to: s.to, label: clip(s.label, LIMITS.label), full: oneLine(s.label), style: s.style, id: s.id, self: a === b };
        m.k = msgsFlat.length;
        m.number = numbered ? m.k + 1 : null;
        msgsFlat.push(m);
        out.push(m);
      } else if (s.t === "note") {
        const a = idx(s.over), b = s.to == null ? idx(s.over) : idx(s.to);
        if (a < 0 || b < 0) { warns.push("note \"" + clip(s.text, 30) + "\" uses unknown participant id \"" + (a < 0 ? s.over : s.to) + "\" (known ids: " + known + ")"); return; }
        out.push({ t: "note", a: Math.min(a, b), b: Math.max(a, b), text: str(s.text) });
      } else if (s.t === "group") {
        out.push({
          t: "group", kind: s.kind, label: clip(s.label, LIMITS.group), full: oneLine(s.label), steps: prune(s.steps),
          elseSteps: s.elseSteps ? prune(s.elseSteps) : null, elseLabel: clip(s.elseLabel == null ? "else" : s.elseLabel, LIMITS.divider),
        });
      } else {
        warns.push((where || "steps") + " item " + (n + 1) + " is not a SeqMessage, SeqNote or SeqGroup");
      }
    });
    return out;
  };
  const tree = prune(d.steps);

  // activation bars: which messages open and close one, and how deep each bar sits on its participant
  const pairs = matchActivations(msgsFlat);
  const closeOf = new Map(pairs.map(([o, c]) => [o, c]));
  const stacks = cols.map(() => []);
  const bars = [];
  const topDepth = (ci) => stacks[ci].reduce((mx, b) => Math.max(mx, b.depth), -1);
  msgsFlat.forEach((m, i) => {
    if (closeOf.has(i)) {
      const bar = { participant: m.to, ci: m.b, depth: stacks[m.b].length ? topDepth(m.b) + 1 : 0, open: i, close: closeOf.get(i) };
      stacks[m.b].push(bar);
      bars.push(bar);
    }
    m.dFrom = topDepth(m.a);
    m.dTo = topDepth(m.b);
    stacks[m.a] = stacks[m.a].filter((b) => b.close !== i);
  });
  // (a return that closes a bar leaves from that bar: dFrom was read before the bar was removed)

  // widths: every need is "the distance between lifeline a and lifeline b is at least X"
  const gaps = [];
  for (let i = 0; i < cols.length - 1; i++) gaps.push((cols[i].w + cols[i + 1].w) / 2 + HDR_GAP);
  const needs = [];
  let rightExtra = 0; // what the last column needs on its right
  const numW = (m) => (m.number == null ? 0 : tw(m.number + ". ", CH));
  msgsFlat.forEach((m) => {
    m.labelW = Math.ceil(tw(m.label, CH) + numW(m));
    if (m.self) {
      const need = SELF_W + 8 + m.labelW + 14;
      if (m.a < cols.length - 1) needs.push({ a: m.a, b: m.a + 1, need }); else rightExtra = Math.max(rightExtra, need);
    } else {
      needs.push({ a: Math.min(m.a, m.b), b: Math.max(m.a, m.b), need: m.labelW + 28 });
    }
  });
  const noteNodes = [];
  const collect = (steps) => steps.forEach((s) => {
    if (s.t === "note") {
      noteNodes.push(s);
      if (s.b > s.a) needs.push({ a: s.a, b: s.b, need: Math.min(tw(s.text, CH_NOTE) + 16, 300) - 2 * NOTE_PAD });
    } else if (s.t === "group") { collect(s.steps); if (s.elseSteps) collect(s.elseSteps); }
  });
  collect(tree);
  needs.sort((p, q) => (p.b - p.a) - (q.b - q.a) || p.a - q.a);
  needs.forEach(({ a, b, need }) => {
    let cur = 0;
    for (let i = a; i < b; i++) cur += gaps[i];
    if (cur < need) { const add = (need - cur) / (b - a); for (let i = a; i < b; i++) gaps[i] += add; }
  });
  let x = cols.length ? cols[0].w / 2 : 0;
  cols.forEach((c, i) => { if (i) x += gaps[i - 1]; c.cx = x; c.x = x - c.w / 2; });

  const edge = (ci, depth, side) => (depth < 0 ? cols[ci].cx : cols[ci].cx + depth * BAR_OFF + side * (BAR_W / 2));

  // rows, top to bottom
  const out = { messages: [], notes: [], groups: [] };
  let y = HDR_H + TOP;
  const grow = (ext, x0, x1) => { if (x0 < ext.x0) ext.x0 = x0; if (x1 > ext.x1) ext.x1 = x1; };
  const walk = (steps, depth) => {
    const ext = { x0: Infinity, x1: -Infinity };
    steps.forEach((s) => {
      if (s.t === "msg") {
        const dir = s.b > s.a ? 1 : s.b < s.a ? -1 : 0;
        const rowTop = y;
        const m = { index: s.k, number: s.number, from: s.from, to: s.to, label: s.label, full: s.full, style: s.style, id: s.id, self: s.self, dashed: s.style === "return", head: s.style === "sync" ? "filled" : "open", depthFrom: s.dFrom, depthTo: s.dTo };
        if (s.self) {
          const ay = rowTop + SELF_ABOVE;
          const x0 = edge(s.a, Math.max(s.dFrom, s.dTo), 1);
          m.y = ay; m.dir = -1; m.x1 = x0; m.x2 = x0;
          m.loop = { w: SELF_W, h: SELF_H, y2: ay + SELF_H };
          m.d = "M" + n1(x0) + " " + n1(ay) + "L" + n1(x0 + SELF_W) + " " + n1(ay) + "L" + n1(x0 + SELF_W) + " " + n1(ay + SELF_H) + "L" + n1(x0 + (m.head === "filled" ? 6 : 0)) + " " + n1(ay + SELF_H);
          const tip = x0, ty = ay + SELF_H;
          m.headD = m.head === "filled"
            ? "M" + n1(tip) + " " + n1(ty) + "L" + n1(tip + HEAD) + " " + n1(ty - 4) + "L" + n1(tip + HEAD) + " " + n1(ty + 4) + "Z"
            : "M" + n1(tip + HEAD) + " " + n1(ty - 4.5) + "L" + n1(tip) + " " + n1(ty) + "L" + n1(tip + HEAD) + " " + n1(ty + 4.5);
          m.labelBox = { x: n1(x0 + SELF_W + 8), y: n1(ay + SELF_H / 2 - 8), w: s.labelW, h: 14, anchor: "start" };
          m.rowH = SELF_ABOVE + SELF_H + ROW_BELOW;
          grow(ext, cols[s.a].cx - BAR_W - 2, m.labelBox.x + m.labelBox.w); // a frame clears the lifeline and its bars
        } else {
          const ay = rowTop + ROW_ABOVE;
          const x1 = edge(s.a, s.dFrom, dir), x2 = edge(s.b, s.dTo, -dir);
          m.y = ay; m.dir = dir; m.x1 = x1; m.x2 = x2;
          const end = m.head === "filled" ? x2 - dir * (HEAD - 1) : x2;
          m.d = "M" + n1(x1) + " " + n1(ay) + "L" + n1(end) + " " + n1(ay);
          m.headD = m.head === "filled"
            ? "M" + n1(x2) + " " + n1(ay) + "L" + n1(x2 - dir * HEAD) + " " + n1(ay - 4) + "L" + n1(x2 - dir * HEAD) + " " + n1(ay + 4) + "Z"
            : "M" + n1(x2 - dir * HEAD) + " " + n1(ay - 4.5) + "L" + n1(x2) + " " + n1(ay) + "L" + n1(x2 - dir * HEAD) + " " + n1(ay + 4.5);
          const mid = (cols[s.a].cx + cols[s.b].cx) / 2;
          m.labelBox = { x: n1(mid - s.labelW / 2), y: n1(ay - 17), w: s.labelW, h: 14, anchor: "middle" };
          m.rowH = ROW_ABOVE + ROW_BELOW;
          grow(ext, Math.min(cols[s.a].cx, cols[s.b].cx) - BAR_W - 2, Math.max(cols[s.a].cx, cols[s.b].cx) + BAR_W + 2);
        }
        out.messages[s.k] = m;
        y = rowTop + m.rowH;
      } else if (s.t === "note") {
        const span = s.b > s.a;
        let w, nx;
        if (span) { nx = cols[s.a].cx - NOTE_PAD; w = cols[s.b].cx - cols[s.a].cx + 2 * NOTE_PAD; }
        else { w = Math.max(90, Math.min(190, Math.ceil(tw(oneLine(s.text), CH_NOTE) + 16))); nx = cols[s.a].cx - w / 2; }
        const lines = wrapText(s.text, (w - 16) / CH_NOTE);
        const h = lines.length * NOTE_LINE + 12;
        const note = { over: cols[s.a].id, to: span ? cols[s.b].id : null, text: s.text, lines, x: n1(nx), y: n1(y + 6), w: n1(w), h };
        out.notes.push(note);
        grow(ext, note.x, note.x + note.w);
        y += 6 + h + 10;
      } else if (s.t === "group") {
        const top = y;
        const g = { kind: s.kind, label: s.label, full: s.full, depth, x: 0, y: top, w: 0, h: 0, divider: null };
        const tabW = Math.ceil(tw(s.kind + " " + s.label, CH) + 18);
        g.tab = { x: 0, y: top, w: tabW, h: TAB_H };
        out.groups.push(g);
        y = top + TAB_H + 2;
        const inner = walk(s.steps, depth + 1);
        let more = null;
        if (s.elseSteps) {
          const dy = y + 4;
          g.divider = { y: dy, label: s.elseLabel };
          y = dy + 16;
          more = walk(s.elseSteps, depth + 1);
        }
        y += 8;
        const e = { x0: inner.x0, x1: inner.x1 };
        if (more) grow(e, more.x0, more.x1);
        if (!(e.x0 <= e.x1)) { e.x0 = cols.length ? cols[0].cx - 20 : 0; e.x1 = cols.length ? cols[cols.length - 1].cx + 20 : 100; }
        g.x = n1(e.x0 - FRAME_PAD);
        const minW = Math.max(tabW + 8, g.divider ? tw(s.elseLabel, CH) + 24 : 0);
        g.w = n1(Math.max(e.x1 + FRAME_PAD - g.x, minW));
        g.h = n1(y - top);
        g.tab.x = g.x;
        y += 8;
        grow(ext, g.x, g.x + g.w);
      }
    });
    return ext;
  };
  walk(tree, 0);

  // activation bars, now that every message has a y
  const barOut = bars.map((b) => {
    const c = cols[b.ci];
    return { participant: b.participant, depth: b.depth, open: b.open, close: b.close, x: n1(c.cx + b.depth * BAR_OFF - BAR_W / 2), w: BAR_W, y1: n1(out.messages[b.open].y - 4), y2: n1(out.messages[b.close].y + 4) };
  });

  // lifelines and the view box: everything that is drawn, plus a little air
  const bottom = Math.max(y, HDR_H + 24) + 4;
  let x0 = Infinity, x1 = -Infinity;
  const take = (a, b) => { x0 = Math.min(x0, a); x1 = Math.max(x1, b); };
  cols.forEach((c) => take(c.x, c.x + c.w));
  out.notes.forEach((q) => take(q.x, q.x + q.w));
  out.groups.forEach((g) => take(g.x, Math.max(g.x + g.w, g.x + g.tab.w)));
  out.messages.forEach((m) => { take(Math.min(m.x1, m.x2), Math.max(m.x1, m.x2)); take(m.labelBox.x, m.labelBox.x + m.labelBox.w); if (m.self) take(m.x1, m.x1 + SELF_W + 2); });
  barOut.forEach((b) => take(b.x, b.x + b.w));
  if (rightExtra && cols.length) take(0, cols[cols.length - 1].cx + rightExtra);
  if (!(x0 <= x1)) { x0 = 0; x1 = 120; }
  const pad = 6;
  const viewBox = [n1(x0 - pad), -pad, n1(x1 - x0 + 2 * pad), n1(bottom + 2 * pad)];

  return {
    warns, viewBox, width: viewBox[2], height: viewBox[3], numbered,
    columns: cols.map((c) => ({ id: c.id, label: c.label, full: c.full, kind: c.kind, cx: n1(c.cx), x: n1(c.x), y: 0, w: c.w, h: HDR_H })),
    lifelines: cols.map((c) => ({ id: c.id, x: n1(c.cx), y1: HDR_H, y2: n1(bottom) })),
    messages: out.messages, activations: barOut, notes: out.notes, groups: out.groups,
  };
}
