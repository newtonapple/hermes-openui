// The Tooltip component: a hover tooltip with an optional click-to-open detail panel for one element of a Dag, Erd, InfraMap, SequenceDiagram, Table, Metric, BarChart, GeoMap or Image. It is DEFINED here, once, and
// registered in the always-on core components (core-components.jsx): a component registered by two packs would make
// createLibrary throw on the duplicate. The diagram packs only import it to type their `tooltips` argument (`Tooltip.ref`).
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { TONES } from "./tooltips-core.js";

export const Tooltip = defineComponent({
  name: "Tooltip",
  description:
    "A hover tooltip with an optional click-to-open detail panel for one element of a Dag, Erd, InfraMap, SequenceDiagram, Table, Metric, BarChart, GeoMap or Image, passed in that component's `tooltips`. target names the element: Dag node id; Erd entity name or `entity.column`; InfraMap node id, `zone:<zone name>` or `<fromId>><toId>` for a link; SequenceDiagram participant id or a SeqMessage id (a message without an id cannot have a tooltip); Table `row:3`, `col:status` or `cell:3.status`; Metric its own label; BarChart a bar's label; GeoMap a point's label or `A>B` for a link; Image the word `image`. Hovering shows hint (short, 140 characters); clicking opens a panel below the component with detail (800 characters), code (a command or snippet, 40 lines, highlighted for language) and link (http or https only; it opens only in the native desktop mode, elsewhere it is text to copy). Add one only where there is something worth saying, about 8 per component at most. tone sets the dot and outline colour (default info). `tooltips` is the LAST argument of the component, so write null for each optional argument before it, for example Dag(nodes, edges, null, null, [t1, t2]). A panel adds 70 px (hint only) to 400 px (detail, 8 lines of code and a link) below the component: in preview mode keep a widget with tooltips under about 800 px (about 20 SequenceDiagram steps, 8 top-to-bottom Dag rows); native mode has no height cap.",
  props: z.object({
    target: z.string(),
    hint: z.string().optional(),
    detail: z.string().optional(),
    code: z.string().optional(),
    language: z.string().optional(),
    tone: z.enum(TONES).optional(),
    link: z.string().optional(),
    linkLabel: z.string().optional(),
  }),
  component: () => null,
});
