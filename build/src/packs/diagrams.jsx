// Pack "diagrams": Dag and Erd.
import React from "react";
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { DagView, ErdView } from "../components/diagrams.jsx";

const DagNode = defineComponent({
  name: "DagNode",
  description: 'One DAG node: unique id, display label, optional status "done"|"running"|"failed"|"pending"|"skipped".',
  props: z.object({ id: z.string(), label: z.string(), status: z.enum(["done", "running", "failed", "pending", "skipped"]).optional() }),
  component: () => null,
});
const Dag = defineComponent({
  name: "Dag",
  description:
    'Directed acyclic graph with automatic layered layout (pipelines, task graphs, dependencies). nodes: DagNode[]. edges: array of [fromId, toId] pairs. direction "LR" or "TB" (omit for auto: LR unless too wide for the chat column, then TB). Optional title.',
  props: z.object({
    nodes: z.array(DagNode.ref),
    edges: z.array(z.array(z.string())),
    direction: z.enum(["LR", "TB"]).optional(),
    title: z.string().optional(),
  }),
  component: ({ props }) => (
    <DagView nodes={(props.nodes ?? []).map((n) => n.props)} edges={props.edges ?? []} direction={props.direction} title={props.title} />
  ),
});

const Entity = defineComponent({
  name: "Entity",
  description:
    'ERD table. name plus fields: strings like "id uuid PK", "user_id uuid FK", "email text UNIQUE" = column name, type, optional flags.',
  props: z.object({ name: z.string(), fields: z.array(z.string()) }),
  component: () => null,
});
const Relation = defineComponent({
  name: "Relation",
  description:
    'ERD relationship between two entity names. kind "1:1"|"1:N"|"N:1"|"N:M" (default 1:N: first entity is the one side). Optional label.',
  props: z.object({ from: z.string(), to: z.string(), kind: z.enum(["1:1", "1:N", "N:1", "N:M"]).optional(), label: z.string().optional() }),
  component: () => null,
});
const Erd = defineComponent({
  name: "Erd",
  description: "Entity-relationship diagram with automatic layout and crow's-foot relations. entities: Entity[], relations: Relation[]. Optional title.",
  props: z.object({ entities: z.array(Entity.ref), relations: z.array(Relation.ref), title: z.string().optional() }),
  component: ({ props }) => (
    <ErdView entities={(props.entities ?? []).map((e) => e.props)} relations={(props.relations ?? []).map((r) => r.props)} title={props.title} />
  ),
});

export const pack = { name: "diagrams", components: [DagNode, Dag, Entity, Relation, Erd] };
