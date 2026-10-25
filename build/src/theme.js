// Shared theme tokens. The desktop injects --foreground, --muted-foreground, --accent, --border, --card
// into the widget frame; the fallbacks keep the widget readable when opened standalone in a browser.
export const C = {
  fg: "var(--foreground, CanvasText)",
  muted: "var(--muted-foreground, GrayText)",
  accent: "var(--accent, AccentColor)",
  border: "var(--border, color-mix(in srgb, CanvasText 18%, transparent))",
  card: "var(--card, Canvas)",
  soft: "color-mix(in srgb, var(--foreground, CanvasText) 6%, transparent)",
};
export const TONES = {
  good: "#3fb950",
  warn: "#d29922",
  bad: "#f85149",
  info: C.accent,
  neutral: C.muted,
};
export const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";
