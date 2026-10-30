// Pure helpers for tooltips (hover tips and click panels) on the diagrams, Table, Metric, BarChart, GeoMap and Image. No imports, no React, no DOM: Node tests load this file
// directly, like sequence-layout.js. The view is tooltips.jsx, the validator checks are tooltips-check.js.

export const TONES = ["info", "good", "warn", "bad"];
export const LIMITS = { count: 60, hint: 140, detail: 800, code: 2000, codeLines: 40, language: 20, linkLabel: 60, link: 300 };
// The components that take a `tooltips` argument, in the order the messages list them.
export const TIP_HOSTS = ["Dag", "Erd", "InfraMap", "SequenceDiagram", "Table", "Metric", "BarChart", "GeoMap", "Image"];
// One correct call for each of them, with every optional argument before `tooltips` written as null (used in the messages about a Tooltip list in the wrong slot).
export const TIP_EXAMPLES = {
  Dag: "Dag(nodes, edges, null, null, [t1])",
  Erd: "Erd(entities, relations, null, [t1])",
  InfraMap: "InfraMap(zones, links, null, null, [t1])",
  SequenceDiagram: "SequenceDiagram(participants, steps, null, null, [t1])",
  Table: "Table(columns, rows, [t1])",
  Metric: "Metric(label, value, null, null, [t1])",
  BarChart: "BarChart(labels, values, null, null, [t1])",
  GeoMap: "GeoMap(points, null, null, [t1])",
  Image: "Image(src, null, null, [t1])",
};
// How to write a target, for the components whose targets are not obvious from the diagram (used in the "matches no element" message).
export const TARGET_FORMS = {
  Table: "targets are row:N, col:HEADER or cell:N.HEADER",
  Metric: "the target is the label of the Metric",
  BarChart: "a target is a bar's label",
  GeoMap: "a target is a point's label, or A>B for a link",
  Image: "the target is the word image",
};
export const TIP_FALLBACK = "Click for details";
export const TIP_DETAIL_CHARS = 100;
// The tooltip box: at most 280 px wide, never narrower than 140 px beside a node (unless the wrapper itself is narrower), 12.5 px
// text at line height 1.4 (17.5 px a line) with 5 px of padding and a 1 px border above and below (12 px of chrome).
export const TIP = { maxWidth: 280, minWidth: 140, floorWidth: 100, chrome: 12, line: 17.5 };

// Whether the parent of a Metric is a flex row that wraps (a Stack row with wrap): only there can a panel take a line of its own below the
// tiles. cs: { display, flexDirection, flexWrap, rowGap } as getComputedStyle reports them. Returns { gap } (the row gap in px) or null.
export function rowFlow(cs) {
  if (!cs || !/flex/.test(String(cs.display))) return null;
  if (!/^row/.test(String(cs.flexDirection)) || !/^wrap/.test(String(cs.flexWrap))) return null;
  return { gap: parseFloat(cs.rowGap) || 0 };
}

const str = (v) => (v == null ? "" : String(v));
const list = (v) => (Array.isArray(v) ? v : []);
const plain = (x) => (x && typeof x === "object" && x.props ? x.props : x);
const text = (v) => (typeof v === "string" && v.trim() ? v : null);

// The parsed `tooltips` argument ({typeName: "Tooltip", props}) reduced to plain data. Bad values are dropped or become
// null, as everywhere else in the runtime; an item that is not a Tooltip is ignored (the validator reports it).
export function normalizeTooltips(raw) {
  const out = [];
  list(raw).forEach((x) => {
    if (!x || typeof x !== "object") return;
    if (x.typeName && x.typeName !== "Tooltip") return;
    const p = plain(x) || {};
    if (typeof p.target !== "string" || !p.target) return;
    out.push({
      target: p.target,
      hint: text(p.hint) && p.hint.trim(),
      detail: text(p.detail),
      code: text(p.code),
      language: text(p.language) && p.language.trim(),
      tone: TONES.includes(p.tone) ? p.tone : "info",
      link: typeof p.link === "string" && p.link ? p.link : null,
      linkLabel: text(p.linkLabel) && p.linkLabel.trim(),
    });
  });
  return out;
}

// What the tooltip says: the hint; else the first line of the detail cut at 100 characters; else a fixed prompt.
export function tooltipText(a) {
  if (a && text(a.hint)) return a.hint.trim();
  const first = a && text(a.detail) ? str(a.detail).split(/\r?\n/).map((s) => s.trim()).find(Boolean) : "";
  if (first) return first.length > TIP_DETAIL_CHARS ? first.slice(0, TIP_DETAIL_CHARS - 1).trimEnd() + "\u2026" : first;
  return TIP_FALLBACK;
}

// Link rules, used by the validator AND again by the renderer at click time. Only http: and https: URLs, written in lowercase,
// with a host, no credentials, no whitespace or control characters. The app opens new URL(link).toString(), and the panel shows
// the string as written, so the two must read the same: no invisible (format) character anywhere, only ASCII in the host and the
// port, and a port the app accepts. Returns { ok: true, url } or { ok: false, reason }.
const hex = (ch) => "U+" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0");
export function checkLink(value) {
  if (typeof value !== "string") return { ok: false, reason: "is not text" };
  if (value === "") return { ok: false, reason: "is empty (leave the link out, or pass null)" };
  if (value.length > LIMITS.link) return { ok: false, reason: "is " + value.length + " characters; the limit is " + LIMITS.link };
  const fmt = /\p{Cf}/u.exec(value);
  if (fmt) return { ok: false, reason: "contains the invisible character " + hex(fmt[0]) + ", which can make the address read differently from where it goes; remove it" };
  if (/[\s\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value)) return { ok: false, reason: "contains whitespace or a control character" };
  if (value.indexOf("\\") !== -1) return { ok: false, reason: "contains a backslash" };
  const m = /^https?:\/\/([^/?#]*)/.exec(value);
  if (!m) {
    if (value.slice(0, 2) === "//") return { ok: false, reason: "has no scheme (it starts with //); start it with https://" };
    const s = /^([A-Za-z][A-Za-z0-9+.\-]*):/.exec(value);
    if (s && /^https?$/i.test(s[1])) return { ok: false, reason: "does not start with lowercase http:// or https:// (use lowercase and keep the //)" };
    if (s) return { ok: false, reason: "uses the " + s[1].toLowerCase() + ": scheme; only http:// and https:// links are accepted" };
    return { ok: false, reason: "does not start with http:// or https://" };
  }
  const authority = m[1];
  if (authority.indexOf("@") !== -1) return { ok: false, reason: "contains a user:password@ part; remove the credentials" };
  if (/^(:\d*)?$/.test(authority)) return { ok: false, reason: "has no host" };
  const wide = /[^\x00-\x7f]/u.exec(authority);
  if (wide) return { ok: false, reason: "has the non-ASCII character " + hex(wide[0]) + " in its host or port; write the host in ASCII, as punycode if needed" };
  let port = null;
  if (authority.charAt(0) === "[") {
    const close = authority.indexOf("]");
    if (close !== -1 && authority.charAt(close + 1) === ":") port = authority.slice(close + 2);
  } else if (authority.indexOf(":") !== -1) {
    port = authority.slice(authority.lastIndexOf(":") + 1);
  }
  if (port !== null && !(/^\d{1,5}$/.test(port) && Number(port) >= 1 && Number(port) <= 65535)) {
    return { ok: false, reason: "has the port `" + port + "`, which the app cannot open; a port is 1 to 5 digits, from 1 to 65535" };
  }
  return { ok: true, url: value };
}

// What the panel says as its text line: the detail, else the hint (a touch screen has no hover, so a click must still show the hint),
// else nothing (a code block or a link line may follow).
export function panelText(a) {
  if (a && text(a.detail)) return a.detail;
  if (a && text(a.hint)) return a.hint.trim();
  return null;
}

// How many text lines fit in a tooltip box of this height (never fewer than one).
export function tipLines(height) {
  return Math.max(1, Math.floor((height - TIP.chrome) / TIP.line));
}

// Where the tooltip goes. wrap and anchor are { left, top, width, height } in viewport coordinates (getBoundingClientRect). tip is the
// tooltip's size { width, height } or, better, a function (maxWidth) => { width, height }: the size the box takes when its text may
// be at most that wide (a narrower box wraps to more lines). The answer is relative to the wrapper:
//   { left, top, side, maxWidth, lines, maxHeight }
// maxWidth is the width the box must be given (so its text wraps to the room it has). lines is null, or the number of text lines to
// keep (the rest is cut with an ellipsis) when the box would be taller than the room it has; then maxHeight is its height in px.
// The order: above the element, else below it, else beside it (right, else left; wrapped to the room that side has, down to 140 px and, if neither side has that, 100 px),
// else squeezed into the room above or below (cut to the lines that fit), and only when there is no room anywhere clamped over the
// element ("over"). It always stays inside the wrapper, which is the only way it cannot change the height of the page while hovering.
export function placeTooltip(wrap, anchor, tip, gap) {
  const g = gap == null ? 6 : gap;
  const W = wrap.width, H = wrap.height;
  const ax = anchor.left - wrap.left, ay = anchor.top - wrap.top, aw = anchor.width, ah = anchor.height;
  const size = typeof tip === "function" ? tip : (mw) => ({ width: Math.min(tip.width, mw), height: tip.height });
  const round = (n) => Math.round(n * 10) / 10;
  const cap = Math.max(1, Math.min(TIP.maxWidth, W));
  const t = size(cap);
  const centred = (w) => Math.max(0, Math.min(ax + aw / 2 - w / 2, W - w));
  // A box of this size and top; cut when it is taller than limit (the room it has), with the left and the width it ends up with.
  const out = (left, top, side, mw, h, limit) => {
    const cut = h > limit + 0.5;
    const lines = cut ? tipLines(limit) : null;
    const height = cut ? Math.min(limit, TIP.chrome + lines * TIP.line) : h;
    return { left: round(left), top: round(top(height)), side, maxWidth: round(mw), lines, maxHeight: cut ? round(height) : null };
  };
  const above = ay - g - t.height, below = ay + ah + g;
  if (above >= 0) return out(centred(t.width), () => above, "above", cap, t.height, H);
  if (below + t.height <= H) return out(centred(t.width), () => below, "below", cap, t.height, H);

  const sides = [{ side: "right", room: W - (ax + aw + g) }, { side: "left", room: ax - g }];
  const pick = (need) => {
    const rooms = sides.filter((r) => r.room >= need);
    return rooms.find((r) => r.room >= t.width) || rooms.slice().sort((a, b) => b.room - a.room)[0];
  };
  const roomy = pick(Math.min(TIP.minWidth, t.width)) || pick(Math.min(TIP.floorWidth, t.width));
  if (roomy) {
    const mw = Math.min(cap, roomy.room), s = size(mw);
    const top = (h) => Math.max(0, Math.min(ay + ah / 2 - h / 2, H - h));
    return out(roomy.side === "right" ? ax + aw + g : ax - g - s.width, top, roomy.side, mw, s.height, H);
  }

  const spaceAbove = ay - g, spaceBelow = H - (ay + ah + g);
  if (Math.max(spaceAbove, spaceBelow) >= TIP.chrome + TIP.line) {
    const up = spaceAbove > spaceBelow;
    const room = up ? spaceAbove : spaceBelow;
    return out(centred(t.width), (h) => (up ? ay - g - h : below), up ? "above" : "below", cap, t.height, room);
  }
  return out(centred(t.width), (h) => Math.max(0, Math.min(ay + ah / 2 - h / 2, H - h)), "over", cap, t.height, H);
}

/* ------------------------------ targets ------------------------------ */
// The elements of each diagram that a tooltip can name, read from the parsed props of the diagram (elements are
// { typeName, props }). Each entry: { key, what, label }. A key that appears more than once is ambiguous.
const walkSeq = (steps, fn) => list(steps).forEach((s) => {
  const type = s && s.typeName, p = plain(s) || {};
  if (type === "SeqMessage") fn(p);
  else if (type === "SeqGroup") { walkSeq(p.steps, fn); walkSeq(p.elseSteps, fn); }
});

export function targetEntries(kind, props) {
  const p = props || {};
  const out = [];
  const add = (key, what, label, ends) => { if (key !== "") out.push({ key, what, label: label == null || label === "" ? key : label, ends: ends || null }); };
  if (kind === "Dag") {
    list(p.nodes).map(plain).filter(Boolean).forEach((n) => add(str(n.id), "node", str(n.label)));
  } else if (kind === "Erd") {
    list(p.entities).map(plain).filter(Boolean).forEach((e) => {
      add(str(e.name), "entity", str(e.name));
      list(e.fields).forEach((f) => { const col = str(f).trim().split(/\s+/)[0]; if (col) add(str(e.name) + "." + col, "column", str(e.name) + "." + col); });
    });
  } else if (kind === "InfraMap") {
    const ids = new Set();
    list(p.zones).map(plain).filter(Boolean).forEach((z) => {
      add("zone:" + str(z.name), "zone", str(z.name));
      list(z.nodes).map(plain).filter(Boolean).forEach((n) => { ids.add(str(n.id)); add(str(n.id), "node", str(n.label)); });
    });
    list(p.links).map(plain).filter(Boolean).forEach((l) => {
      const a = str(l.from), b = str(l.to);
      if (a !== b && ids.has(a) && ids.has(b)) add(a + ">" + b, "link", a + " \u2192 " + b, [a, b]);
    });
  } else if (kind === "SequenceDiagram") {
    list(p.participants).map(plain).filter(Boolean).forEach((q) => add(str(q.id), "participant", str(q.label)));
    walkSeq(p.steps, (m) => { if (m.id != null && str(m.id) !== "") add(str(m.id), "message", str(m.label)); });
  } else if (kind === "Table") {
    // row:3 is the third data row (1-based), col:status a header cell, cell:3.status the cell of that row under that header. A header may
    // hold dots, so a cell target is split at the FIRST dot. Columns come first so the first few valid targets show the three forms.
    const cols = list(p.columns).map(str), rows = list(p.rows);
    cols.forEach((c) => add("col:" + c, "column", c));
    rows.forEach((r, i) => add("row:" + (i + 1), "row", "Row " + (i + 1)));
    rows.forEach((r, i) => list(r).forEach((_, j) => { if (j < cols.length && cols[j] !== "") add("cell:" + (i + 1) + "." + cols[j], "cell", "Row " + (i + 1) + ", " + cols[j]); }));
  } else if (kind === "Metric") {
    add(str(p.label), "metric", str(p.label));
  } else if (kind === "BarChart") {
    list(p.labels).forEach((l) => add(str(l), "bar", str(l)));
  } else if (kind === "GeoMap") {
    const labels = new Set();
    list(p.points).map(plain).filter(Boolean).forEach((pt) => { labels.add(str(pt.label)); add(str(pt.label), "point", str(pt.label)); });
    list(p.links).forEach((l) => {
      const a = str(list(l)[0]), b = str(list(l)[1]);
      if (a !== b && labels.has(a) && labels.has(b)) add(a + ">" + b, "link", a + " \u2192 " + b, [a, b]);
    });
  } else if (kind === "Image") {
    add("image", "image", "Image");
  }
  return out;
}

// { keys: [unique keys in drawing order], count: { key: [what, what, ...] }, ends: { key: [[from, to], ...] } (links only) }
export function targetSummary(kind, props) {
  const keys = [], count = Object.create(null), ends = Object.create(null);
  targetEntries(kind, props).forEach((e) => {
    if (!count[e.key]) { count[e.key] = []; keys.push(e.key); }
    count[e.key].push(e.what);
    if (e.ends) (ends[e.key] = ends[e.key] || []).push(e.ends);
  });
  return { keys, count, ends };
}
