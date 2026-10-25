// Pack "map": GeoMap (offline coastlines).
import React from "react";
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { MapView } from "../components/map.jsx";

const GeoPoint = defineComponent({
  name: "GeoPoint",
  description: 'Map pin: label, lat, lon (decimal degrees), optional tone "good"|"warn"|"bad"|"info"|"neutral".',
  props: z.object({ label: z.string(), lat: z.number(), lon: z.number(), tone: z.enum(["good", "warn", "bad", "info", "neutral"]).optional() }),
  component: () => null,
});
const GeoMap = defineComponent({
  name: "GeoMap",
  description:
    'Offline world map (no tiles; coarse coastlines, country/region scale) auto-zoomed to fit the pins. points: GeoPoint[]. links: optional array of [labelA, labelB] pairs drawn as dashed lines. Optional title.',
  props: z.object({
    points: z.array(GeoPoint.ref),
    links: z.array(z.array(z.string())).optional(),
    title: z.string().optional(),
  }),
  component: ({ props }) => <MapView points={(props.points ?? []).map((p) => p.props)} links={props.links ?? []} title={props.title} />,
});

export const pack = { name: "map", components: [GeoPoint, GeoMap] };
