// SVG diagrams with built-in auto-layout: Dag (layered, longest-path + barycenter ordering) and Erd (grid + crow's-foot relations).
import React, { useId } from "react";
import { C, TONES, MONO } from "../theme.js";
import { Tipped, Hot } from "./tooltips.jsx";

const STATUS = {
  done: { color: TONES.good, label: "done" },
  running: { color: C.accent, label: "running" },
  failed: { color: TONES.bad, label: "failed" },
  pending: { color: C.muted, label: "pending" },
  skipped: { color: C.muted, label: "skipped", dash: "4 3" },
};
const textW = (s, px = 7.3) => String(s).length * px;

/* ------------------------------- DAG ------------------------------- */
export function layoutDag(nodes, edges, dir) {
  const ids = nodes.map((n) => n.id);
  const idx = new Map(ids.map((id, i) => [id, i]));
  const adj = ids.map(() => []);
  for (const [a, b] of edges) if (idx.has(a) && idx.has(b) && a !== b) adj[idx.get(a)].push(idx.get(b));
  // drop back edges so cycles can't loop forever
  const state = ids.map(() => 0);
  const kept = [];
  const dfs = (u) => {
    state[u] = 1;
    for (const v of adj[u]) {
      if (state[v] === 1) continue;
      kept.push([u, v]);
      if (state[v] === 0) dfs(v);
    }
    state[u] = 2;
  };
  ids.forEach((_, u) => state[u] === 0 && dfs(u));
  const preds = ids.map(() => []), succs = ids.map(() => []);
  for (const [u, v] of kept) { preds[v].push(u); succs[u].push(v); }
  const layer = ids.map(() => -1);
  const depth = (v) => (layer[v] >= 0 ? layer[v] : (layer[v] = preds[v].length ? 1 + Math.max(...preds[v].map(depth)) : 0));
  ids.forEach((_, v) => depth(v));
  const L = Math.max(0, ...layer) + 1;
  const cols = Array.from({ length: L }, () => []);
  ids.forEach((_, v) => cols[layer[v]].push(v));
  const pos = ids.map(() => 0);
  const stamp = () => cols.forEach((c) => c.forEach((v, i) => (pos[v] = i)));
  stamp();
  const bary = (v, nb) => (nb[v].length ? nb[v].reduce((s, u) => s + pos[u], 0) / nb[v].length : pos[v]);
  for (let it = 0; it < 4; it++) {
    for (let l = 1; l < L; l++) { cols[l].sort((a, b) => bary(a, preds) - bary(b, preds)); stamp(); }
    for (let l = L - 2; l >= 0; l--) { cols[l].sort((a, b) => bary(a, succs) - bary(b, succs)); stamp(); }
  }
  const NH = 44, GX = 64, GY = 18;
  const w = ids.map((_, v) => Math.max(110, textW(nodes[v].label) + 34));
  const lw = cols.map((c) => Math.max(...c.map((v) => w[v])));
  const maxCount = Math.max(...cols.map((c) => c.length));
  const out = ids.map(() => ({}));
  if (dir === "TB") {
    const rowW = cols.map((c) => c.reduce((s, v) => s + w[v], 0) + (c.length - 1) * GX);
    const total = Math.max(...rowW);
    cols.forEach((c, l) => {
      let x = (total - rowW[l]) / 2;
      c.forEach((v) => { out[v] = { x, y: l * (NH + 52), w: w[v], h: NH }; x += w[v] + GX; });
    });
    return { boxes: out, edges: kept, width: total, height: L * (NH + 52) - 52 };
  }
  const colH = cols.map((c) => c.length * NH + (c.length - 1) * GY);
  const total = maxCount * NH + (maxCount - 1) * GY;
  let x = 0;
  cols.forEach((c, l) => {
    let y = (total - colH[l]) / 2;
    c.forEach((v) => { out[v] = { x, y, w: lw[l], h: NH }; y += NH + GY; });
    x += lw[l] + GX;
  });
  return { boxes: out, edges: kept, width: x - GX, height: total };
}

const COLUMN = 640;
// Scale to the column first; only scroll when that would make text unreadable (< ~62%).
const fit = (w) => ({ width: "100%", maxWidth: w, minWidth: Math.min(w, Math.round(w * 0.78)), height: "auto", display: "block" });

export function DagView({ nodes, edges, direction, title, tooltips }) {
  const uid = useId().replace(/:/g, "");
  let dir = direction;
  let lay = layoutDag(nodes, edges, dir || "LR");
  if (!dir) {
    dir = "LR";
    if (lay.width > COLUMN - 16) { dir = "TB"; lay = layoutDag(nodes, edges, "TB"); }
  }
  direction = dir;
  const pad = 8;
  const used = [...new Set(nodes.map((n) => n.status).filter(Boolean))];
  return (
    <div style={{ minWidth: 0 }}>
      {title ? <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{title}</div> : null}
      <Tipped tooltips={tooltips}>
      <div style={{ overflowX: "auto" }}>
        <svg viewBox={`${-pad} ${-pad} ${lay.width + pad * 2} ${lay.height + pad * 2}`} style={fit(lay.width + pad * 2)}>
          <defs>
            <marker id={`ar${uid}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill={C.muted} />
            </marker>
          </defs>
          {lay.edges.map(([u, v], i) => {
            const a = lay.boxes[u], b = lay.boxes[v];
            let d;
            if (direction === "TB") {
              const x1 = a.x + a.w / 2, y1 = a.y + a.h, x2 = b.x + b.w / 2, y2 = b.y, my = (y1 + y2) / 2;
              d = `M${x1} ${y1}C${x1} ${my} ${x2} ${my} ${x2} ${y2}`;
            } else {
              const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2, mx = (x1 + x2) / 2;
              d = `M${x1} ${y1}C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`;
            }
            return <path key={i} d={d} fill="none" stroke={C.muted} strokeWidth="1.4" opacity="0.8" markerEnd={`url(#ar${uid})`} />;
          })}
          {nodes.map((n, v) => {
            const b = lay.boxes[v];
            const st = STATUS[n.status];
            const col = st ? st.color : C.border;
            return (
              <Hot key={n.id} k={n.id} label={n.label} shape={{ t: "rect", x: b.x, y: b.y, w: b.w, h: b.h, rx: 9 }} marker={[b.x + b.w - 2, b.y + 2]}>
                <g>
                  <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="9" fill={C.card} stroke={col} strokeWidth={st ? 1.6 : 1} strokeDasharray={st && st.dash} />
                  {st ? <circle cx={b.x + 14} cy={b.y + b.h / 2} r="4" fill={col} /> : null}
                  <text x={b.x + (st ? 26 : 0) + (b.w - (st ? 26 : 0)) / 2} y={b.y + b.h / 2 + 4.5} textAnchor="middle" fontSize="13" fill={C.fg}>{n.label}</text>
                </g>
              </Hot>
            );
          })}
        </svg>
      </div>
      </Tipped>
      <Warn items={edges.flatMap(([a, b]) => [a, b]).filter((id) => !nodes.some((n) => n.id === id)).map((id) => `edge references unknown node id "${id}"`)} />
      {used.length ? (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 6, fontSize: 11.5, color: C.muted }}>
          {used.filter((s) => STATUS[s]).map((s) => (
            <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: 8, background: STATUS[s].color, display: "inline-block" }} />{STATUS[s].label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------- ERD ------------------------------- */
const HEAD = 30, ROW = 21;
function parseField(s) {
  const p = String(s).trim().split(/\s+/);
  const flags = p.slice(2).join(" ");
  return { name: p[0] || "", type: p[1] || "", flags };
}
export function layoutErd(entities, relations) {
  const n = entities.length;
  const idxOf = new Map(entities.map((e, i) => [e.name, i]));
  const deg = entities.map(() => 0);
  const nbr = entities.map(() => new Set());
  for (const r of relations) {
    const a = idxOf.get(r.from), b = idxOf.get(r.to);
    if (a == null || b == null || a === b) continue;
    deg[a]++; deg[b]++; nbr[a].add(b); nbr[b].add(a);
  }
  const order = [];
  const seen = new Set();
  const byDeg = [...entities.keys()].sort((a, b) => deg[b] - deg[a]);
  for (const s of byDeg) {
    if (seen.has(s)) continue;
    const q = [s]; seen.add(s);
    while (q.length) {
      const u = q.shift(); order.push(u);
      [...nbr[u]].sort((a, b) => deg[b] - deg[a]).forEach((v) => { if (!seen.has(v)) { seen.add(v); q.push(v); } });
    }
  }
  const cols = n <= 2 ? n : n === 4 ? 2 : Math.min(3, Math.ceil(Math.sqrt(n)));
  if (n >= 3 && n <= 8) {
    const pairs = [];
    relations.forEach((r) => { const a = idxOf.get(r.from), b = idxOf.get(r.to); if (a != null && b != null && a !== b) pairs.push([a, b]); });
    const cost = (ord) => {
      const cell = new Array(n);
      ord.forEach((e, k) => (cell[e] = k));
      return pairs.reduce((t, [a, b]) => t + Math.abs((cell[a] % cols) - (cell[b] % cols)) + Math.abs(Math.floor(cell[a] / cols) - Math.floor(cell[b] / cols)), 0);
    };
    let best = order.slice(), bestC = cost(best);
    const perm = (arr, k) => {
      if (k === arr.length) { const c = cost(arr); if (c < bestC) { bestC = c; best = arr.slice(); } return; }
      for (let i = k; i < arr.length; i++) { [arr[k], arr[i]] = [arr[i], arr[k]]; perm(arr, k + 1); [arr[k], arr[i]] = [arr[i], arr[k]]; }
    };
    perm(order.slice(), 0);
    order.splice(0, order.length, ...best);
  }
  const w = entities.map((e) => Math.max(170, ...e.fields.map((f) => { const p = parseField(f); return textW(p.name, 7.4) + textW(p.type, 6.8) + textW(p.flags, 6.5) + 52; }), textW(e.name, 8.2) + 28));
  const h = entities.map((e) => HEAD + e.fields.length * ROW + 8);
  const colW = Array.from({ length: cols }, () => 0);
  const rows = Math.ceil(n / cols);
  const rowH = Array.from({ length: rows }, () => 0);
  order.forEach((ei, k) => { colW[k % cols] = Math.max(colW[k % cols], w[ei]); rowH[Math.floor(k / cols)] = Math.max(rowH[Math.floor(k / cols)], h[ei]); });
  const GX = 84, GY = 54;
  const boxes = entities.map(() => ({}));
  order.forEach((ei, k) => {
    const c = k % cols, r = Math.floor(k / cols);
    const x = colW.slice(0, c).reduce((s, v) => s + v + GX, 0);
    const y = rowH.slice(0, r).reduce((s, v) => s + v + GY, 0);
    boxes[ei] = { x, y, w: colW[c], h: h[ei] };
  });
  const width = colW.reduce((s, v) => s + v, 0) + GX * (cols - 1);
  const height = rowH.reduce((s, v) => s + v, 0) + GY * (rows - 1);
  return { boxes, width, height, idxOf };
}

function endMark(x, y, dx, dy, many, key) {
  const px = -dy, py = dx;
  if (many) {
    const bx = x + dx * 13, by = y + dy * 13;
    return (
      <g key={key} stroke={C.muted} strokeWidth="1.4" fill="none">
        <path d={`M${bx} ${by}L${x + px * 7} ${y + py * 7}M${bx} ${by}L${x} ${y}M${bx} ${by}L${x - px * 7} ${y - py * 7}`} />
      </g>
    );
  }
  const bx = x + dx * 11, by = y + dy * 11;
  return <path key={key} d={`M${bx - px * 6} ${by - py * 6}L${bx + px * 6} ${by + py * 6}`} stroke={C.muted} strokeWidth="1.6" />;
}

function segHits(pts, boxes, skip) {
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    const xa = Math.min(x1, x2), xb = Math.max(x1, x2), ya = Math.min(y1, y2), yb = Math.max(y1, y2);
    for (let k = 0; k < boxes.length; k++) {
      if (skip.has(k)) continue;
      const b = boxes[k];
      if (xb > b.x - 2 && xa < b.x + b.w + 2 && yb > b.y - 2 && ya < b.y + b.h + 2) return true;
    }
  }
  return false;
}

// Orthogonal route between two entity boxes; detours over the top (or down the right side) if a box is in the way.
function routeErd(ia, ib, boxes, laneN, k) {
  const a = boxes[ia], b = boxes[ib];
  const ao = ((k % 3) - 1) * 18, jm = ((k % 4) - 1.5) * 9; // anchor offset along the edge, lane jitter
  const acx = a.x + a.w / 2, acy = a.y + a.h / 2, bcx = b.x + b.w / 2, bcy = b.y + b.h / 2;
  const horiz = Math.abs(bcx - acx) / ((a.w + b.w) / 2) >= Math.abs(bcy - acy) / ((a.h + b.h) / 2);
  let pts, d1, d2;
  if (horiz) {
    const s = bcx >= acx ? 1 : -1;
    const p1 = [s > 0 ? a.x + a.w : a.x, acy + ao], p2 = [s > 0 ? b.x : b.x + b.w, bcy - ao];
    const mx = (p1[0] + p2[0]) / 2 + jm;
    pts = [p1, [mx, p1[1]], [mx, p2[1]], p2]; d1 = [s, 0]; d2 = [-s, 0];
  } else {
    const s = bcy >= acy ? 1 : -1;
    const p1 = [acx + ao, s > 0 ? a.y + a.h : a.y], p2 = [bcx - ao, s > 0 ? b.y : b.y + b.h];
    const my = (p1[1] + p2[1]) / 2 + jm;
    pts = [p1, [p1[0], my], [p2[0], my], p2]; d1 = [0, s]; d2 = [0, -s];
  }
  const skip = new Set([ia, ib]);
  let lane = false;
  if (segHits(pts, boxes, skip)) {
    lane = true;
    if (Math.abs(acx - bcx) < 24) {
      const x = Math.max(a.x + a.w, b.x + b.w) + 22 + 10 * laneN;
      pts = [[a.x + a.w, acy], [x, acy], [x, bcy], [b.x + b.w, bcy]]; d1 = [1, 0]; d2 = [1, 0];
    } else {
      const top = Math.min(a.y, b.y) - 22 - 10 * laneN;
      pts = [[acx, a.y], [acx, top], [bcx, top], [bcx, b.y]]; d1 = [0, -1]; d2 = [0, -1];
    }
  }
  return { pts, d1, d2, lane };
}

export function ErdView({ entities, relations, title, tooltips }) {
  const lay = layoutErd(entities, relations);
  const unknown = [];
  let laneN = 0;
  const routes = [];
  relations.forEach((r, i) => {
    const ia = lay.idxOf.get(r.from), ib = lay.idxOf.get(r.to);
    if (ia == null || ib == null) { unknown.push(`${ia == null ? r.from : r.to}`); return; }
    if (ia === ib) return;
    const rt = routeErd(ia, ib, lay.boxes, laneN, routes.length);
    if (rt.lane) laneN++;
    routes.push({ r, rt, i });
  });
  // viewBox covers boxes plus any detour lanes
  let x0 = 0, y0 = 0, x1 = lay.width, y1 = lay.height;
  routes.forEach(({ rt }) => rt.pts.forEach(([x, y]) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }));
  const pad = 14;
  const VW = x1 - x0 + pad * 2, VH = y1 - y0 + pad * 2;
  return (
    <div style={{ minWidth: 0 }}>
      {title ? <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{title}</div> : null}
      <Tipped tooltips={tooltips}>
      <div style={{ overflowX: "auto" }}>
        <svg viewBox={`${x0 - pad} ${y0 - pad} ${VW} ${VH}`} style={fit(VW)}>
          {routes.map(({ r, rt, i }) => {
            const [ka, kb] = String(r.kind || "1:N").toUpperCase().split(":");
            const p1 = rt.pts[0], p2 = rt.pts[rt.pts.length - 1];
            const path = "M" + rt.pts.map((p) => p.join(" ")).join("L");
            const m1 = rt.pts[1], m2 = rt.pts[2];
            const lx = (m1[0] + m2[0]) / 2, ly = (m1[1] + m2[1]) / 2;
            return (
              <g key={i}>
                <path d={path} fill="none" stroke={C.muted} strokeWidth="1.3" strokeLinejoin="round" />
                {endMark(p1[0], p1[1], rt.d1[0], rt.d1[1], ka === "N" || ka === "M", "a")}
                {endMark(p2[0], p2[1], rt.d2[0], rt.d2[1], kb === "N" || kb === "M", "b")}
                {r.label ? <text x={lx} y={ly - 5} textAnchor="middle" fontSize="11" fill={C.muted} stroke={C.card} strokeWidth="4" paintOrder="stroke">{r.label}</text> : null}
              </g>
            );
          })}
          {entities.map((e, i) => {
            const b = lay.boxes[i];
            return (
              <Hot key={e.name} k={e.name} label={e.name} shape={{ t: "rect", x: b.x, y: b.y, w: b.w, h: b.h, rx: 8 }} marker={[b.x + b.w - 2, b.y + 2]}>
              <g>
                <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="8" fill={C.card} stroke={C.border} />
                <path d={`M${b.x} ${b.y + HEAD}V${b.y + 8}a8 8 0 0 1 8-8H${b.x + b.w - 8}a8 8 0 0 1 8 8V${b.y + HEAD}z`} fill={C.soft} />
                <line x1={b.x} x2={b.x + b.w} y1={b.y + HEAD} y2={b.y + HEAD} stroke={C.border} />
                <text x={b.x + 12} y={b.y + 20} fontSize="13.5" fontWeight="650" fill={C.fg}>{e.name}</text>
                {e.fields.map((f, j) => {
                  const p = parseField(f);
                  const y = b.y + HEAD + 8 + j * ROW + 13;
                  const key = /\bPK\b/i.test(p.flags);
                  const col = e.name + "." + p.name;
                  return (
                    <Hot key={j} k={col} label={col} shape={{ t: "rect", x: b.x + 1, y: y - 15, w: b.w - 2, h: ROW, rx: 3 }} marker={[b.x + b.w - 5, y - 11]}>
                    <g>
                      <text x={b.x + 12} y={y} fontSize="12.5" fontFamily={MONO} fontWeight={key ? 700 : 400} fill={C.fg}>{p.name}</text>
                      <text x={b.x + b.w - 12 - textW(p.flags, 6.5) - (p.flags ? 10 : 0)} y={y} fontSize="11.5" fontFamily={MONO} textAnchor="end" fill={C.muted}>{p.type}</text>
                      {p.flags ? <text x={b.x + b.w - 12} y={y} fontSize="10.5" textAnchor="end" fill={key ? C.accent : C.muted} fontWeight="650">{p.flags}</text> : null}
                    </g>
                    </Hot>
                  );
                })}
              </g>
              </Hot>
            );
          })}
        </svg>
      </div>
      </Tipped>
      <Warn items={unknown.map((n) => `relation references unknown entity "${n}" (use the Entity name, not the variable name)`)} />
    </div>
  );
}

export function Warn({ items }) {
  if (!items || !items.length) return null;
  return <div style={{ marginTop: 6, fontSize: 12, color: TONES.bad }}>{[...new Set(items)].map((t, i) => <div key={i}>⚠ {t}</div>)}</div>;
}
