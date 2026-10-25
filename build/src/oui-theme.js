// Maps OpenUI design tokens onto the Hermes desktop theme variables (injected into every widget frame:
// --foreground, --muted-foreground, --accent, --border, --card) so OpenUI's own components look native.
// Fallbacks keep a widget readable when opened standalone in a browser.
//
// Chart palette: OpenUI samples N consecutive entries centred on the middle of the array, so the order below is
// chosen to make the middle region the nicest categorical run: 1 series = amber (Hermes gold), 2 = blue+green,
// 3 = blue+amber+green, 4 = blue+amber+green+rose, and so on. Concrete hex only: the chart code does colour math.
export const CHART_PALETTE = [
  "#C7C95A", // olive
  "#A78BFA", // violet
  "#36C2CE", // cyan
  "#5B9CF6", // blue
  "#F2A93B", // amber
  "#4FC38A", // green
  "#E8657A", // rose
  "#F08BC0", // pink
];

export const openuiTheme = {
  textNeutralPrimary: "var(--foreground, CanvasText)",
  textNeutralSecondary: "var(--muted-foreground, GrayText)",
  textNeutralTertiary: "var(--muted-foreground, GrayText)",
  borderDefault: "var(--border, color-mix(in srgb, CanvasText 18%, transparent))",
  borderInteractive: "var(--border, color-mix(in srgb, CanvasText 18%, transparent))",
  foreground: "var(--card, Canvas)",
  background: "var(--card, Canvas)",
  sunk: "color-mix(in srgb, var(--foreground, CanvasText) 6%, transparent)",
  defaultChartPalette: CHART_PALETTE,
  barChartPalette: CHART_PALETTE,
  lineChartPalette: CHART_PALETTE,
  areaChartPalette: CHART_PALETTE,
  pieChartPalette: CHART_PALETTE,
  radarChartPalette: CHART_PALETTE,
  radialChartPalette: CHART_PALETTE,
  horizontalBarChartPalette: CHART_PALETTE,
};
