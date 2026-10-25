// Pack "charts": OpenUI's own line/area/pie/radar charts, re-registered under our descriptions.
import { defineComponent } from "@openuidev/react-lang";
import { LineChartCondensed as OuiLine } from "../../node_modules/@openuidev/react-ui/dist/genui-lib/Charts/LineChartCondensed.js";
import { AreaChartCondensed as OuiArea } from "../../node_modules/@openuidev/react-ui/dist/genui-lib/Charts/AreaChartCondensed.js";
import { PieChart as OuiPie } from "../../node_modules/@openuidev/react-ui/dist/genui-lib/Charts/PieChart.js";
import { RadarChart as OuiRadar } from "../../node_modules/@openuidev/react-ui/dist/genui-lib/Charts/RadarChart.js";
import { Series as OuiSeries } from "../../node_modules/@openuidev/react-ui/dist/genui-lib/Charts/Series.js";
import chartsCss from "../../node_modules/@openuidev/react-ui/dist/styles/charts.css";
// OpenUI's descriptions mention query data ("data.categories") that widgets don't have.

const redescribe = (def, description) =>
  defineComponent({ name: def.name, props: def.props, description, component: def.component });

const Series = redescribe(
  OuiSeries,
  "One data series for LineChart/AreaChart/RadarChart: Series(name, values). values is a number array parallel to the chart's labels.",
);
const LineChart = redescribe(
  OuiLine,
  'Line chart over categories (trends over time, several series). LineChart(labels, [Series(...)], variant?, xLabel?, yLabel?, height?). variant "linear"|"natural"(smooth, default)|"step".',
);
const AreaChart = redescribe(
  OuiArea,
  'Filled STACKED area chart (series are stacked on top of each other, so it shows parts of a growing total; use LineChart to compare series directly). AreaChart(labels, [Series(...)], variant?, xLabel?, yLabel?, height?). variant "linear"|"natural"|"step".',
);
const PieChart = redescribe(
  OuiPie,
  'Pie/donut of parts of a whole. PieChart(labels, values, variant?, appearance?). variant "pie" (filled, default, most legible) | "donut" (thin outer ring style); appearance "circular"|"semiCircular". Use <= 8 slices; labels and values are parallel literal arrays.',
);
const RadarChart = redescribe(
  OuiRadar,
  "Radar/spider chart comparing several metrics for one or more entities. RadarChart(labels, [Series(...)]); one axis per label, each series values parallel to labels.",
);

export const pack = { name: "charts", components: [Series, LineChart, AreaChart, PieChart, RadarChart], css: chartsCss };
