// Pack "map": GeoMap (offline coastlines).
import React from "react";
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { MapView } from "../components/map.jsx";
import { Tooltip } from "../components/tooltip-schema.js";

const GeoPoint = defineComponent({
  name: "GeoPoint",
  description: 'Map pin: label, lat, lon (decimal degrees), optional tone "good"|"warn"|"bad"|"info"|"neutral".',
  props: z.object({ label: z.string(), lat: z.number(), lon: z.number(), tone: z.enum(["good", "warn", "bad", "info", "neutral"]).optional() }),
  component: () => null,
});
const GeoMap = defineComponent({
  name: "GeoMap",
  description:
    'Offline world map (no tiles; coarse coastlines, country/region scale) auto-zoomed to fit the pins. points: GeoPoint[]. links: optional array of [labelA, labelB] pairs drawn as dashed lines. Optional title. tooltips: Tooltip[] is the LAST argument (write null for links and title if skipped, e.g. GeoMap(points, null, null, [t1])) and adds a hover tooltip with an optional click-to-open panel; target is a point\'s label (the pin) or A>B for a link (such as web>api); two links joining the same pair are ambiguous.',
  props: z.object({
    points: z.array(GeoPoint.ref),
    links: z.array(z.array(z.string())).optional(),
    title: z.string().optional(),
    tooltips: z.array(Tooltip.ref).optional(),
  }),
  component: ({ props }) => <MapView points={(props.points ?? []).map((p) => p.props)} links={props.links ?? []} title={props.title} tooltips={props.tooltips} />,
});

export const pack = { name: "map", components: [GeoPoint, GeoMap] };
