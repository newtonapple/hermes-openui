// Pack "infra": InfraMap with its InfraZone, InfraNode and InfraLink parts. A pack of its own so a page that only uses
// Dag or Erd does not carry the map's layout engine.
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { InfraMapView, infraData, KINDS, STATUS_ORDER, TONE_NAMES } from "../components/infra.jsx";
import { Tooltip } from "../components/tooltip-schema.js";

const InfraNode = defineComponent({
  name: "InfraNode",
  description:
    "One box inside an InfraZone. id is unique across the whole map and is what InfraLink uses. kind picks a small glyph, status adds a health dot and outline, detail is a short second line such as `8 GPUs` or `vllm :8000`.",
  props: z.object({
    id: z.string(),
    label: z.string(),
    kind: z.enum(KINDS).optional(),
    status: z.enum(STATUS_ORDER).optional(),
    detail: z.string().optional(),
  }),
  component: () => null,
});

const InfraZone = defineComponent({
  name: "InfraZone",
  description:
    "A labelled rounded box that groups nodes (a network, rack, host or cloud). tone tints the box (info blue, good green, warn amber, bad red). Needs at least one node.",
  props: z.object({ name: z.string(), nodes: z.array(InfraNode.ref), tone: z.enum(TONE_NAMES).optional() }),
  component: () => null,
});

const InfraLink = defineComponent({
  name: "InfraLink",
  description:
    'A curved arrow from one InfraNode id to another. label (a protocol or purpose such as `SQL`) sits in a pill on the line; "dashed" marks an optional or indirect path.',
  props: z.object({ from: z.string(), to: z.string(), label: z.string().optional(), style: z.enum(["solid", "dashed"]).optional() }),
  component: () => null,
});

const InfraMap = defineComponent({
  name: "InfraMap",
  description:
    "Infrastructure map: zones are columns left to right (LR, default) or rows top to bottom (TB), nodes stacked inside, links routed around the zones between them, legend for the statuses in use. Stays legible in the chat column up to about 4 zones and 12 nodes. tooltips: Tooltip[] is the LAST argument (write null for each skipped optional argument before it, e.g. InfraMap(zones, links, null, null, [t1])) and adds a hover tooltip with an optional click-to-open detail panel (target: a node id, `zone:<zone name>` or `<fromId>><toId>` for a link).",
  props: z.object({
    zones: z.array(InfraZone.ref),
    links: z.array(InfraLink.ref),
    title: z.string().optional(),
    direction: z.enum(["LR", "TB"]).optional(),
    tooltips: z.array(Tooltip.ref).optional(),
  }),
  component: ({ props }) => <InfraMapView {...infraData(props)} tooltips={props.tooltips} />,
});

export const pack = { name: "infra", components: [InfraNode, InfraZone, InfraLink, InfraMap] };
