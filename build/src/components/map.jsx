// Tile-less map: Natural Earth 110m land (vendored, ~23 KB) in equirectangular projection with pins and links.
// No network, no tiles. Coastlines are coarse (110m): good for country/region scale, not street level.
import React, { useId } from "react";
import { C, TONES } from "../theme.js";
import { WORLD_PATH } from "../world-path.js";
import { Tipped, Hot } from "./tooltips.jsx";

const X = (lon) => (lon + 180) * 10;
const Y = (lat) => (90 - lat) * 10;

export function fitView(points) {
  if (!points.length) return { x: 0, y: 0, w: 3600, h: 1800 };
  let lon0 = Infinity, lon1 = -Infinity, lat0 = Infinity, lat1 = -Infinity;
  for (const p of points) { lon0 = Math.min(lon0, p.lon); lon1 = Math.max(lon1, p.lon); lat0 = Math.min(lat0, p.lat); lat1 = Math.max(lat1, p.lat); }
  const pad = (s) => Math.max(s * 0.3, 6);
  let w = (lon1 - lon0 + 2 * pad(lon1 - lon0)) * 10;
  let h = (lat1 - lat0 + 2 * pad(lat1 - lat0)) * 10;
  w = Math.max(w, 240); h = Math.max(h, 120);
  const aspect = 2;
  if (w / h < aspect) w = h * aspect; else h = w / aspect;
  if (w > 3600) { w = 3600; h = 1800; }
  const cx = (X(lon0) + X(lon1)) / 2, cy = (Y(lat0) + Y(lat1)) / 2;
  let x = cx - w / 2, y = cy - h / 2;
  x = Math.min(Math.max(0, x), 3600 - w); y = Math.min(Math.max(0, y), 1800 - h);
  return { x, y, w, h };
}

export function MapView({ points, links = [], title, tooltips }) {
  const uid = useId().replace(/:/g, "");
  const v = fitView(points);
  const k = v.w / 640; // view units per nominal css pixel
  const byLabel = new Map(points.map((p) => [p.label, p]));
  const grat = [];
  const step = v.w > 1800 ? 300 : v.w > 700 ? 100 : 50;
  for (let gx = Math.ceil(v.x / step) * step; gx <= v.x + v.w; gx += step) grat.push(<line key={"x" + gx} x1={gx} x2={gx} y1={v.y} y2={v.y + v.h} />);
  for (let gy = Math.ceil(v.y / step) * step; gy <= v.y + v.h; gy += step) grat.push(<line key={"y" + gy} x1={v.x} x2={v.x + v.w} y1={gy} y2={gy} />);
  return (
    // data-hermes-openui-map is a styling hook for native mode (plugin.jsx NATIVE_CSS); it changes nothing elsewhere.
    <div data-hermes-openui-map="" style={{ minWidth: 0 }}>
      {title ? <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{title}</div> : null}
      <Tipped tooltips={tooltips} keepFocus>
        <svg viewBox={`${v.x} ${v.y} ${v.w} ${v.h}`} style={{ width: "100%", height: "auto", display: "block", borderRadius: 10, border: `1px solid ${C.border}`, background: "color-mix(in srgb, var(--foreground, CanvasText) 3%, transparent)" }}>
          <g stroke={C.border} strokeWidth={0.7 * k} opacity="0.45">{grat}</g>
          <defs><path id={`w${uid}`} d={WORLD_PATH} /></defs>
          <g fill={C.soft} stroke={C.muted} strokeWidth={0.8 * k} strokeLinejoin="round" opacity="0.9">
            {[-3600, 0, 3600].map((dx) => <use key={dx} href={`#w${uid}`} x={dx} />)}
          </g>
          {links.map(([a, b], i) => {
            const p = byLabel.get(a), q = byLabel.get(b);
            if (!p || !q) return null;
            const line = <line x1={X(p.lon)} y1={Y(p.lat)} x2={X(q.lon)} y2={Y(q.lat)} stroke={C.accent} strokeWidth={1.6 * k} strokeDasharray={`${5 * k} ${4 * k}`} opacity="0.85" />;
            if (a === b) return <React.Fragment key={i}>{line}</React.Fragment>;
            const d = `M${X(p.lon)} ${Y(p.lat)}L${X(q.lon)} ${Y(q.lat)}`;
            // The dashed line is thin, so a transparent hit path of about 12 css px lies over it; the dot sits in the middle of the line.
            return (
              <Hot key={i} k={a + ">" + b} label={a + " \u2192 " + b} shape={{ t: "path", d }} marker={[(X(p.lon) + X(q.lon)) / 2, (Y(p.lat) + Y(q.lat)) / 2]} scale={k}>
                {line}
              </Hot>
            );
          })}
          {points.map((p, i) => {
            const col = TONES[p.tone || "info"] || C.accent;
            const x = X(p.lon), y = Y(p.lat);
            const right = x < v.x + v.w * 0.78;
            // The hit box covers the pin and its label (7.8 css px a letter, the width of a bold 12 px label), so the whole pin can be hovered and clicked.
            const tw = String(p.label).length * 7.8 * k;
            const x0 = right ? x - 9 * k : x - 9 * k - tw - 2 * k, w = 18 * k + tw + 2 * k;
            return (
              <Hot key={i} k={String(p.label)} label={String(p.label)} shape={{ t: "rect", x: x0, y: y - 10 * k, w, h: 20 * k, rx: 6 * k }} marker={[x0 + w, y - 8 * k]} scale={k}>
                <g>
                  <circle cx={x} cy={y} r={9 * k} fill={col} opacity="0.22" />
                  <circle cx={x} cy={y} r={4.6 * k} fill={col} stroke="var(--card, Canvas)" strokeWidth={1.4 * k} />
                  <text x={x + (right ? 9 : -9) * k} y={y + 4 * k} fontSize={12 * k} textAnchor={right ? "start" : "end"} fill={C.fg} stroke="var(--card, Canvas)" strokeWidth={3.2 * k} paintOrder="stroke" style={{ fontWeight: 550 }}>{p.label}</text>
                </g>
              </Hot>
            );
          })}
        </svg>
      </Tipped>
    </div>
  );
}
