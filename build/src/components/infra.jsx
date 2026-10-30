// Infrastructure map: zones of nodes joined by routed, labelled arrows, drawn as one SVG with its own layout.
// The layout runs along two abstract axes and is mapped to the screen at the end: u runs along the zone order (x for LR,
// y for TB) and v runs across it (the way nodes stack inside a zone). layoutInfra is exported for the unit tests, which run
// it in Node (tests/test_infra_builtin.py); the renderer is InfraMapView.
import React, { useId } from "react";
import { C, TONES, MONO } from "../theme.js";
import { Tipped, Hot, tippedKeys } from "./tooltips.jsx";

const STATUS = {
  up: { color: TONES.good, label: "up" },
  degraded: { color: TONES.warn, label: "degraded", outline: true },
  down: { color: TONES.bad, label: "down", outline: true },
  unknown: { color: C.muted, label: "unknown", hollow: true, dash: "4 3" },
};
export const STATUS_ORDER = ["up", "degraded", "down", "unknown"];
export const KINDS = ["client", "gateway", "service", "gpu", "database", "storage", "queue", "cloud"];
export const TONE_NAMES = ["neutral", "info", "good", "warn", "bad"];

// Small inline glyphs on a 16 x 16 grid, one per node kind.
const GLYPHS = {
  client: [["rect", { x: 2, y: 2.5, width: 12, height: 8.5, rx: 1.5 }], ["path", { d: "M5.5 14h5M8 11v3" }]],
  gateway: [["path", { d: "M2.5 2.5v11M13.5 2.5v11" }], ["path", { d: "M4.5 8h6.5M8.5 5.5L11 8l-2.5 2.5" }]],
  service: [["path", { d: "M8 1.5l5.5 3v7L8 14.5l-5.5-3v-7z" }], ["path", { d: "M2.5 4.5L8 7.5l5.5-3M8 7.5v7" }]],
  gpu: [
    ["rect", { x: 4, y: 4, width: 8, height: 8, rx: 1.2 }],
    ["rect", { x: 6.5, y: 6.5, width: 3, height: 3 }],
    ["path", { d: "M6.5 1.8V4M9.5 1.8V4M6.5 12v2.2M9.5 12v2.2M1.8 6.5H4M1.8 9.5H4M12 6.5h2.2M12 9.5h2.2" }],
  ],
  database: [["ellipse", { cx: 8, cy: 3.8, rx: 5, ry: 2 }], ["path", { d: "M3 3.8v8.4c0 1.1 2.2 2 5 2s5-.9 5-2V3.8M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" }]],
  storage: [
    ["rect", { x: 2, y: 2.5, width: 12, height: 4.2, rx: 1 }],
    ["rect", { x: 2, y: 9.3, width: 12, height: 4.2, rx: 1 }],
    ["path", { d: "M4.6 4.6h.01M4.6 11.4h.01" }],
  ],
  queue: [
    ["rect", { x: 1.5, y: 5.5, width: 3.4, height: 5, rx: 0.8 }],
    ["rect", { x: 6.3, y: 5.5, width: 3.4, height: 5, rx: 0.8 }],
    ["rect", { x: 11.1, y: 5.5, width: 3.4, height: 5, rx: 0.8 }],
  ],
  cloud: [["path", { d: "M4.8 12.5h6.4a3 3 0 0 0 .6-5.9 4 4 0 0 0-7.7.4 3 3 0 0 0 .7 5.5z" }]],
  plain: [["rect", { x: 3, y: 3, width: 10, height: 10, rx: 2 }]],
};

/* ------------------------------ helpers ------------------------------ */
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const str = (v) => (v == null ? "" : String(v));
const list = (v) => (Array.isArray(v) ? v : []);
const plain = (x) => (x && typeof x === "object" && x.props ? x.props : x);
const clip = (s, n) => { s = str(s); return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; };
const tw = (s, px) => str(s).length * px;
const n1 = (v) => Math.round(v * 10) / 10;
const dist = (a, b) => Math.sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1]));
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const maxOf = (base, arr) => Math.max(base, ...arr);
const pillW = (label) => (label ? Math.max(28, Math.round(tw(label, 6.1) + 12)) : 0);
const hit = (a, b, m) => a.x < b.x + b.w + m && b.x < a.x + a.w + m && a.y < b.y + b.h + m && b.y < a.y + a.h + m;

const ZP = 10; // padding inside a zone box
const HH = 24; // zone header (the name) height
const PH = 16; // link label pill height

// The parsed component elements ({typeName, props}) reduced to the plain data the layout and the view work on.
export function infraData(props) {
  const zones = list(props.zones).map((zn) => {
    const q = plain(zn) || {};
    return { name: q.name, tone: q.tone, nodes: list(q.nodes).map(plain) };
  });
  return { zones, links: list(props.links).map(plain), title: props.title, direction: props.direction };
}

/* ------------------------------- layout ------------------------------- */
export function layoutInfra(zonesIn, linksIn, direction) {
  const TB = direction === "TB";
  const P = (p) => (TB ? [p[1], p[0]] : [p[0], p[1]]);
  const rect = (u, v, du, dv) => (TB ? { x: v, y: u, w: dv, h: du } : { x: u, y: v, w: du, h: dv });

  const warns = [];
  const zones = [], recs = [], byId = Object.create(null), dupIds = [];
  list(zonesIn).forEach((zin, zi) => {
    const zn = { name: str(zin.name), tone: has(TONES, zin.tone) ? zin.tone : "neutral", recs: [] };
    list(zin.nodes).forEach((n, ni) => {
      const r = { n, id: str(n.id), zi, ni, idx: recs.length, label: clip(n.label, 22), detail: n.detail ? clip(n.detail, 26) : "" };
      zn.recs.push(r);
      recs.push(r);
      if (byId[r.id]) { if (!dupIds.includes(r.id)) dupIds.push(r.id); } else { byId[r.id] = r; }
    });
    zones.push(zn);
  });
  if (dupIds.length) warns.push("duplicate node ids: " + dupIds.join(", ") + " (every InfraNode id must be unique)");

  // node sizes
  const anyDetail = recs.some((r) => !!r.detail);
  const NH = anyDetail ? 46 : 36;
  recs.forEach((r) => {
    const text = Math.max(tw(r.label, 6.9) + (r.n.status ? 16 : 2), r.detail ? tw(r.detail, 6.3) : 0);
    r.w = Math.max(104, Math.ceil(34 + text + 9));
  });
  const gw = maxOf(104, recs.map((r) => r.w));
  zones.forEach((zn) => {
    zn.nw = TB ? gw : maxOf(104, zn.recs.map((r) => r.w));
    zn.nu = TB ? NH : zn.nw; // node size along u
    zn.nv = TB ? zn.nw : NH; // node size along v
  });

  // links: resolve, classify, size the label pill
  const known = Object.keys(byId).join(", ");
  const links = [];
  list(linksIn).forEach((lk, i) => {
    const a = byId[str(lk.from)], b = byId[str(lk.to)];
    if (!a || !b) {
      warns.push("link references unknown node id \"" + str(!a ? lk.from : lk.to) + "\" (known ids: " + known + ")");
      return;
    }
    if (a === b) { warns.push("link from \"" + a.id + "\" to itself is not drawn"); return; }
    const dz = b.zi - a.zi;
    const k = { i, lk, a, b, dir: dz >= 0 ? 1 : -1, label: lk.label ? clip(lk.label, 18) : "", dashed: lk.style === "dashed" };
    k.pw = pillW(k.label);
    k.type = dz === 0 ? (Math.abs(b.ni - a.ni) === 1 ? "stack" : "bracket") : (Math.abs(dz) === 1 ? "adj" : "far");
    links.push(k);
  });

  // zone sizes
  const padU0 = TB ? ZP + HH : ZP, padU1 = ZP, padV0 = TB ? ZP : ZP + HH, padV1 = ZP;
  zones.forEach((zn, zi) => {
    const stackPw = maxOf(0, links.filter((k) => k.type === "stack" && k.a.zi === zi).map((k) => k.pw));
    zn.gapV = TB ? Math.max(30, stackPw ? stackPw + 16 : 0) : 30;
    const cnt = zn.recs.length;
    zn.stack = cnt ? cnt * zn.nv + (cnt - 1) * zn.gapV : 22;
    zn.nameNeed = tw(zn.name, 7.4) + 26;
    zn.T = Math.max(zn.nu + padU0 + padU1, TB ? 0 : zn.nameNeed);
  });
  const Vmax = maxOf(0, zones.map((zn) => Math.max(padV0 + zn.stack + padV1, TB ? zn.nameNeed : 0)));
  const gapU = [];
  zones.forEach((zn, zi) => { if (zi < zones.length - 1) gapU[zi] = TB ? 34 : 26; });
  links.forEach((k) => {
    if (TB || !k.pw) return;
    if (k.type === "adj") {
      const g = Math.min(k.a.zi, k.b.zi);
      gapU[g] = Math.max(gapU[g], k.pw + 10 - 2 * ZP); // the label pill must fit between the two node edges
    } else if (k.type === "bracket" && k.a.zi < zones.length - 1) {
      gapU[k.a.zi] = Math.max(gapU[k.a.zi], k.pw - 1); // a bracket's pill sits beside it, in the gap to the next zone
    }
  });

  // positions
  let U = 0;
  zones.forEach((zn, zi) => {
    zn.U = U;
    U += zn.T + (zi < zones.length - 1 ? gapU[zi] : 0);
    const v0 = padV0 + (Vmax - padV0 - padV1 - zn.stack) / 2;
    zn.recs.forEach((r, j) => {
      r.nu = zn.nu; r.nv = zn.nv;
      r.u = zn.U + padU0 + (zn.T - padU0 - padU1 - zn.nu) / 2;
      r.v = v0 + j * (zn.nv + zn.gapV);
      r.cv = r.v + zn.nv / 2;
    });
  });

  // where each arrow touches a node edge: spread several arrows along the edge, ordered by where they are heading
  const att = Object.create(null);
  const attach = (r, side, k, end, other) => {
    const key = r.idx + side;
    (att[key] = att[key] || []).push({ k, end, other, r });
  };
  links.forEach((k) => {
    if (k.type === "stack") return;
    if (k.type === "far") k.side = (k.a.cv + k.b.cv) / 2 <= Vmax / 2 ? "top" : "bottom";
    const farOther = k.side === "top" ? -1e6 : 1e6;
    const oa = k.type === "far" ? farOther : k.b.cv, ob = k.type === "far" ? farOther : k.a.cv;
    if (k.type === "bracket") { attach(k.a, "e", k, "a", oa); attach(k.b, "e", k, "b", ob); }
    else if (k.dir > 0) { attach(k.a, "e", k, "a", oa); attach(k.b, "s", k, "b", ob); }
    else { attach(k.a, "s", k, "a", oa); attach(k.b, "e", k, "b", ob); }
  });
  Object.keys(att).forEach((key) => {
    const items = att[key];
    items.sort((p, q) => p.other - q.other || p.k.i - q.k.i);
    const n = items.length;
    items.forEach((e, j) => {
      const sp = n > 1 ? Math.min(12, (e.r.nv - 16) / (n - 1)) : 0; // wide enough that two arrowheads do not touch
      e.k[e.end + "v"] = e.r.cv + (j - (n - 1) / 2) * sp;
    });
  });

  // far links ride a lane outside the zones and cross each zone gap in a vertical run of their own
  const runs = [], lanes = { top: 0, bottom: 0 };
  const farPw = maxOf(0, links.filter((k) => k.type === "far").map((k) => k.pw));
  const LANE0 = TB ? Math.max(16, farPw / 2 + 10) : 16, LANE_STEP = 22;
  links.forEach((k) => {
    if (k.type !== "far") return;
    k.lane = lanes[k.side]++;
    k.g1 = k.dir > 0 ? k.a.zi : k.a.zi - 1;
    k.g2 = k.dir > 0 ? k.b.zi - 1 : k.b.zi;
    [k.g1, k.g2].forEach((g) => { (runs[g] = runs[g] || []).push(k); });
  });
  const gapX = (g, k) => {
    const rank = runs[g].indexOf(k);
    return zones[g].U + zones[g].T + gapU[g] * (rank + 1) / (runs[g].length + 1);
  };

  // paths, in (u, v) command lists
  const round = (pts, r) => {
    const cmds = [["M", pts[0]]];
    for (let i = 1; i < pts.length - 1; i++) {
      const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1], d1 = dist(p0, p1), d2 = dist(p1, p2);
      const rr = Math.min(r, d1 / 2, d2 / 2);
      if (d1 < 0.01 || d2 < 0.01 || rr < 0.5) { cmds.push(["L", p1]); continue; }
      cmds.push(["L", lerp(p1, p0, rr / d1)], ["Q", p1, lerp(p1, p2, rr / d2)]);
    }
    cmds.push(["L", pts[pts.length - 1]]);
    return cmds;
  };
  links.forEach((k) => {
    const a = k.a, b = k.b;
    let p0, p1;
    if (k.type === "stack") {
      const uc = a.u + a.nu / 2;
      if (a.ni < b.ni) { p0 = [uc, a.v + a.nv]; p1 = [uc, b.v]; } else { p0 = [uc, a.v]; p1 = [uc, b.v + b.nv]; }
      k.cmds = [["M", p0], ["L", p1]];
    } else if (k.type === "bracket") {
      p0 = [a.u + a.nu, k.av]; p1 = [b.u + b.nu, k.bv];
      k.cmds = [["M", p0], ["C", [p0[0] + 14, p0[1]], [p1[0] + 14, p1[1]], p1]]; // the bulge stays inside the zone padding
    } else if (k.type === "adj") {
      p0 = [k.dir > 0 ? a.u + a.nu : a.u, k.av]; p1 = [k.dir > 0 ? b.u : b.u + b.nu, k.bv];
      const c = (p1[0] - p0[0]) / 2;
      k.cmds = [["M", p0], ["C", [p0[0] + c, p0[1]], [p1[0] - c, p1[1]], p1]];
    } else {
      p0 = [k.dir > 0 ? a.u + a.nu : a.u, k.av]; p1 = [k.dir > 0 ? b.u : b.u + b.nu, k.bv];
      const vL = k.side === "top" ? -(LANE0 + k.lane * LANE_STEP) : Vmax + LANE0 + k.lane * LANE_STEP;
      const x1 = gapX(k.g1, k), x2 = gapX(k.g2, k);
      k.mid = [(x1 + x2) / 2, vL];
      k.cmds = round([p0, [x1, p0[1]], [x1, vL], [x2, vL], [x2, p1[1]], p1], 9);
    }
  });

  // flatten to screen polylines (for placing labels, for the tests, for the view box)
  const flatten = (cmds) => {
    const pts = [];
    let cur = null;
    cmds.forEach((c) => {
      if (c[0] === "M") { cur = c[1]; pts.push(P(cur)); }
      else if (c[0] === "L") {
        const steps = Math.max(1, Math.ceil(dist(cur, c[1]) / 4)); // a sample at least every 4 px, also on straight runs
        for (let i = 1; i <= steps; i++) pts.push(P(lerp(cur, c[1], i / steps)));
        cur = c[1];
      } else if (c[0] === "Q") {
        for (let i = 1; i <= 8; i++) {
          const t = i / 8;
          pts.push(P([(1 - t) * (1 - t) * cur[0] + 2 * (1 - t) * t * c[1][0] + t * t * c[2][0], (1 - t) * (1 - t) * cur[1] + 2 * (1 - t) * t * c[1][1] + t * t * c[2][1]]));
        }
        cur = c[2];
      } else {
        for (let i = 1; i <= 20; i++) {
          const t = i / 20;
          const m = 1 - t;
          pts.push(P([m * m * m * cur[0] + 3 * m * m * t * c[1][0] + 3 * m * t * t * c[2][0] + t * t * t * c[3][0], m * m * m * cur[1] + 3 * m * m * t * c[1][1] + 3 * m * t * t * c[2][1] + t * t * t * c[3][1]]));
        }
        cur = c[3];
      }
    });
    return pts;
  };
  const toD = (cmds) =>
    cmds.map((c) => c[0] + c.slice(1).map((p) => { const s = P(p); return n1(s[0]) + " " + n1(s[1]); }).join(" ")).join("");

  // rectangles on screen
  const nodeRects = recs.map((r) => {
    const q = rect(r.u, r.v, r.nu, r.nv);
    q.id = r.id; q.zone = zones[r.zi].name; q.label = r.label; q.detail = r.detail; q.rec = r;
    return q;
  });
  const zoneRects = zones.map((zn) => {
    const q = rect(zn.U, 0, zn.T, Vmax);
    q.name = zn.name; q.tone = zn.tone;
    return q;
  });

  // label pills: slide along the arrow until the pill touches no node and no other pill
  const placed = [];
  const obstacles = nodeRects.map((q) => ({ x: q.x, y: q.y, w: q.w, h: q.h }));
  links.forEach((k) => { k.poly = flatten(k.cmds); });
  links.forEach((k) => {
    const cum = [0];
    for (let i = 1; i < k.poly.length; i++) cum.push(cum[i - 1] + dist(k.poly[i - 1], k.poly[i]));
    k.len = cum[cum.length - 1];
    if (!k.label) return;
    const at = (s) => {
      s = Math.max(0, Math.min(k.len, s));
      for (let j = 1; j < cum.length; j++) {
        if (cum[j] >= s) {
          const span = cum[j] - cum[j - 1];
          return lerp(k.poly[j - 1], k.poly[j], span ? (s - cum[j - 1]) / span : 0);
        }
      }
      return k.poly[k.poly.length - 1];
    };
    const cands = [];
    if (k.type === "stack") {
      const mid = at(k.len / 2);
      cands.push(TB ? [mid[0], mid[1] - PH / 2 - 4] : [mid[0] + k.pw / 2 + 8, mid[1]]);
    } else {
      let pref = k.len / 2;
      if (k.type === "far") {
        const m = P(k.mid);
        let best = 1e9;
        for (let i = 0; i < k.poly.length; i++) { const dd = dist(k.poly[i], m); if (dd < best) { best = dd; pref = cum[i]; } }
      }
      const steps = [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6, -7, 7, -8, 8];
      steps.forEach((f) => {
        const s = pref + f * 12;
        if (s > 10 && s < k.len - 10) cands.push(at(s));
      });
      if (!cands.length) cands.push(at(pref));
      if (k.type === "bracket") {
        // the arrow hugs the node edges, so a pill on it would sit on the nodes in between: also try beside it
        steps.forEach((f) => {
          const s = pref + f * 12;
          if (s > 10 && s < k.len - 10) { const q = at(s); cands.push(TB ? [q[0], q[1] + PH / 2 + 6] : [q[0] + k.pw / 2 + 6, q[1]]); }
        });
      }
    }
    // a box on a node or on another pill is out; touching another arrow is a lesser evil, so take the candidate that
    // covers the fewest points of other arrows (the first one wins a tie, which keeps pills near the middle)
    let chosen = null, bestScore = 1e12;
    cands.forEach((c) => {
      const box = { x: c[0] - k.pw / 2, y: c[1] - PH / 2, w: k.pw, h: PH };
      const hard = obstacles.concat(placed).filter((o) => hit(box, o, 2)).length;
      let soft = 0;
      links.forEach((o) => {
        if (o === k) return;
        o.poly.forEach((p) => { if (p[0] > box.x - 1 && p[0] < box.x + box.w + 1 && p[1] > box.y - 1 && p[1] < box.y + box.h + 1) soft++; });
      });
      const score = hard * 100000 + soft;
      if (score < bestScore) { bestScore = score; chosen = box; }
    });
    chosen.text = k.label;
    chosen.link = k;
    k.pill = chosen;
    placed.push(chosen);
  });

  // view box: everything that is drawn, plus a little air
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  const grow = (x, y, w, hh) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + w); y1 = Math.max(y1, y + hh); };
  zoneRects.forEach((q) => grow(q.x, q.y, q.w, q.h));
  nodeRects.forEach((q) => grow(q.x, q.y, q.w, q.h));
  links.forEach((k) => {
    k.poly.forEach((p) => grow(p[0] - 2, p[1] - 2, 4, 4));
    if (k.pill) grow(k.pill.x, k.pill.y, k.pill.w, k.pill.h);
  });
  if (x0 > x1) { x0 = 0; y0 = 0; x1 = 120; y1 = 40; }
  const pad = 6;
  const viewBox = [n1(x0 - pad), n1(y0 - pad), n1(x1 - x0 + 2 * pad), n1(y1 - y0 + 2 * pad)];

  return {
    TB, NH, warns, viewBox, anyDetail,
    statuses: STATUS_ORDER.filter((s) => recs.some((r) => r.n.status === s)),
    nodes: nodeRects, zones: zoneRects,
    links: links.map((k) => ({ from: k.a.id, to: k.b.id, label: k.label, dashed: k.dashed, d: toD(k.cmds), points: k.poly, type: k.type })),
    pills: links.filter((k) => k.pill).map((k) => ({ text: k.pill.text, x: k.pill.x, y: k.pill.y, w: k.pill.w, h: k.pill.h, from: k.a.id, to: k.b.id })),
  };
}

/* -------------------------------- view -------------------------------- */
const glyph = (kind, x, y) => (
  <g transform={"translate(" + n1(x) + " " + n1(y) + ") scale(1.1)"} fill="none" stroke={C.accent} strokeWidth={1.25} strokeLinecap="round" strokeLinejoin="round">
    {GLYPHS[has(GLYPHS, kind) ? kind : "plain"].map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs }))}
  </g>
);

const statusDot = (st, cx, cy) =>
  st.hollow ? <circle cx={cx} cy={cy} r={3.6} fill="none" stroke={st.color} strokeWidth={1.5} /> : <circle cx={cx} cy={cy} r={4} fill={st.color} />;

function Warn({ items }) {
  if (!items.length) return null;
  return <div style={{ marginTop: 6, fontSize: 12, color: TONES.bad }}>{items.map((t, i) => <div key={i}>{"\u26a0 " + t}</div>)}</div>;
}

export function InfraMapView({ zones, links, title, direction, tooltips }) {
  const uid = str(useId()).replace(/[^A-Za-z0-9]/g, "");
  const lay = layoutInfra(zones, links, direction === "TB" ? "TB" : "LR");
  const vb = lay.viewBox;
  const arrow = "ia" + uid;
  const marked = tippedKeys(tooltips);

  const zoneBoxes = [], zoneLabels = [];
  lay.zones.forEach((q, i) => {
    const tinted = q.tone !== "neutral";
    const zk = "zone:" + q.name;
    zoneBoxes.push(
      <Hot key={"z" + i} k={zk} label={q.name} shape={{ t: "rect", x: q.x, y: q.y, w: q.w, h: q.h, rx: 12 }} marker={[q.x + q.w - 2, q.y + 2]}>
        <rect x={q.x} y={q.y} width={q.w} height={q.h} rx={12}
          fill={tinted ? "color-mix(in srgb, " + TONES[q.tone] + " 9%, transparent)" : C.soft}
          stroke={tinted ? "color-mix(in srgb, " + TONES[q.tone] + " 50%, transparent)" : C.border} strokeWidth={1} />
      </Hot>,
    );
    zoneLabels.push(
      <Hot key={"zl" + i} k={zk} label={q.name} proxy>
        <text x={q.x + 12} y={q.y + 17} fontSize={11.5} fontWeight={650} letterSpacing="0.02em" fill={tinted ? TONES[q.tone] : C.muted}>{q.name}</text>
      </Hot>,
    );
  });

  const linkEls = lay.links.map((k, i) => {
    const p0 = k.points[0], key = k.from + ">" + k.to, name = k.from + " \u2192 " + k.to;
    const pill = lay.pills.find((p) => p.from === k.from && p.to === k.to);
    const mid = k.points[Math.floor(k.points.length / 2)] || p0;
    return (
      <Hot key={"l" + i} k={key} label={name} shape={{ t: "path", d: k.d }} marker={pill ? null : [n1(mid[0]), n1(mid[1])]}>
        <g>
          <path d={k.d} fill="none" stroke={C.muted} strokeWidth={1.5} strokeDasharray={k.dashed ? "6 4" : undefined} strokeLinecap="round" opacity={0.9} markerEnd={"url(#" + arrow + ")"}>
            {marked.has(key) ? null : <title>{name + (k.label ? " (" + k.label + ")" : "")}</title>}
          </path>
          <circle cx={n1(p0[0])} cy={n1(p0[1])} r={2.4} fill={C.muted} />
        </g>
      </Hot>
    );
  });

  const nodeEls = lay.nodes.map((q, i) => {
    const r = q.rec, st = STATUS[r.n.status];
    const stroke = st && st.outline ? st.color : C.border;
    const cy = lay.anyDetail ? q.y + 14.5 : q.y + q.h / 2 - 0.5;
    const tip = str(r.n.label) + (r.n.kind ? " \u00b7 " + r.n.kind : "") + (st ? " \u00b7 " + st.label : "") + (r.n.detail ? " \u00b7 " + r.n.detail : "");
    return (
      <Hot key={"n" + i} k={q.id} label={str(r.n.label)} shape={{ t: "rect", x: q.x, y: q.y, w: q.w, h: q.h, rx: 8 }} marker={[q.x + q.w - 2, q.y + 2]}>
        <g>
          {marked.has(q.id) ? null : <title>{tip}</title>}
          <rect x={q.x} y={q.y} width={q.w} height={q.h} rx={8} fill={C.card} stroke={stroke} strokeWidth={st && st.outline ? 1.6 : 1} strokeDasharray={st && st.dash} />
          {glyph(r.n.kind, q.x + 9, q.y + q.h / 2 - 9.5)}
          <text x={q.x + 34} y={lay.anyDetail ? q.y + 19 : q.y + q.h / 2 + 4.5} fontSize={12.5} fontWeight={600} fill={C.fg}>{r.label}</text>
          {r.detail ? <text x={q.x + 34} y={q.y + 34} fontSize={10.5} fontFamily={MONO} fill={C.muted}>{r.detail}</text> : null}
          {st ? statusDot(st, q.x + q.w - 11, cy) : null}
        </g>
      </Hot>
    );
  });

  const pillEls = lay.pills.map((p, i) => (
    <Hot key={"p" + i} k={p.from + ">" + p.to} label={p.from + " \u2192 " + p.to} proxy marker={[n1(p.x + p.w - 1), n1(p.y + 1)]}>
      <g>
        <rect x={n1(p.x)} y={n1(p.y)} width={p.w} height={p.h} rx={PH / 2} fill={C.card} stroke={C.border} strokeWidth={1} />
        <text x={n1(p.x + p.w / 2)} y={n1(p.y + p.h / 2 + 3.8)} textAnchor="middle" fontSize={10.5} fill={C.fg}>{p.text}</text>
      </g>
    </Hot>
  ));

  const legend = lay.statuses.length ? (
    <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 6, fontSize: 11.5, color: C.muted }}>
      {lay.statuses.map((s) => {
        const st = STATUS[s];
        const dot = { width: 8, height: 8, borderRadius: 8, display: "inline-block", boxSizing: "border-box" };
        if (st.hollow) dot.border = "1.5px solid " + st.color; else dot.background = st.color;
        return (
          <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span style={dot} />
            {st.label}
          </span>
        );
      })}
    </div>
  ) : null;

  const w = vb[2];
  return (
    <div style={{ minWidth: 0 }}>
      {title ? <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{title}</div> : null}
      <Tipped tooltips={tooltips}>
      <div style={{ overflowX: "auto" }}>
        <svg viewBox={vb.join(" ")} role={marked.size ? "group" : "img"} aria-label={title || "Infrastructure map"} style={{ width: "100%", maxWidth: w, minWidth: Math.min(w, Math.round(w * 0.78)), height: "auto", display: "block" }}>
          <defs>
            <marker id={arrow} viewBox="0 0 10 10" refX={9} refY={5} markerWidth={9} markerHeight={9} markerUnits="userSpaceOnUse" orient="auto">
              <path d="M0 0L10 5L0 10z" fill={C.muted} />
            </marker>
          </defs>
          {zoneBoxes}
          {linkEls}
          {zoneLabels}
          {nodeEls}
          {pillEls}
        </svg>
      </div>
      </Tipped>
      <Warn items={lay.warns} />
      {legend}
    </div>
  );
}
