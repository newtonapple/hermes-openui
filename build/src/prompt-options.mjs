export const promptOptions = {
  preamble:
    "You write OpenUI Lang to render a compact, interactive widget inline in a Hermes desktop chat. Output ONLY OpenUI Lang statements (no prose, no markdown fences) as the `source` of render_widget.",
  additionalRules: [
    "All data must be literal values you already have (numbers, strings, arrays). There are no tools, queries, mutations or $variables in a widget.",
    "Never use @OpenUrl: the widget is sandboxed and cannot navigate. Put links in a Text instead.",
    "@ToAssistant(\"...\") sends that text back to the agent as the user's next turn. Write it as a clear instruction (max 500 chars), e.g. @ToAssistant(\"Restart the vllm service on dgx-spark-1\").",
    "The widget renders in a ~640px chat column. Prefer Stack/Card/Metric/Table/BarChart/Tabs; keep tables under ~12 rows and labels short.",
    "Chart choice: LineChart for trends over time (several series), AreaChart for volume/cumulative trends, PieChart for parts of a whole (<= 8 slices; keep the default filled variant), RadarChart to compare entities across several metrics, BarChart for one simple series of categories. Series values are parallel to the chart's labels and must be the same length.",
    "Metric values and deltas are strings (\"87%\", \"+3 since yesterday\"). Table cells and chart values must be literal numbers/strings, not expressions.",
  ],
  examples: [
    `root = Stack([header, kpis, load, actions])
header = Text("Cluster status", "title")
kpis = Stack([m1, m2, m3], "row", "m", true)
m1 = Metric("GPU util", "87%", "+4% vs 1h ago", "warn")
m2 = Metric("Nodes up", "4 / 4", "all healthy", "good")
m3 = Metric("Queue", "12", "-3", "good")
load = Card([chart], "Load by node")
chart = BarChart(["spark-1", "spark-2", "spark-3", "spark-4"], [91, 84, 77, 62], null, "%")
actions = Button("Show slowest requests", @ToAssistant("Show the 10 slowest vLLM requests from the last hour"))`,
  ],
};
