---
name: openui-render
description: "Patterns and pitfalls for render_widget: dashboards, charts, DAG/ER diagrams, maps."
version: 0.1.0
---

# render_widget patterns

`render_widget(source=<OpenUI Lang>)` validates the source, saves a widget, and returns a one-line directive. Put that directive ALONE on its own line in your reply, after at most one sentence of context. The widget appears when the turn finishes.

First use: call `render_widget(reference=true)` for the exact component signatures. Never guess a signature.

## Pick the component

| Need | Use |
|---|---|
| Several numbers at a glance | `Stack` row of `Metric` tiles |
| Rows and columns | `Table` (under about 12 rows) |
| Trend over time, several series | `LineChart` (use `AreaChart` only for stacked totals) |
| Parts of a whole | `PieChart` (8 slices at most; group the rest as "Other") |
| Compare entities across metrics | `RadarChart` |
| One series of categories | `BarChart` |
| Pipeline, dependency graph, network hierarchy | `Dag` |
| Database schema | `Erd` |
| Places | `GeoMap` (country or region scale; coastlines only) |
| Ask the user to choose | `Choice` |
| Alternate views of one subject | `Tabs`, with a `Card` per view |

## Rules that are easy to break

- Arguments are POSITIONAL. `Stack(children, direction: "row")` silently breaks; write `Stack(children, "row")`.
- `root = Stack([...])` comes first. Every other variable must be reachable from `root` or it will not render.
- Chart `labels` and every series `values` array must be the same length.
- Edges, relations and links name the node id, entity name or point label as a STRING, never a variable.
- `Dag`: leave `direction` as `null` so it picks left-to-right or top-to-bottom to fit the column. Keep labels short (about ten characters). Edges have no labels: put link details in a `Table`. Layout is layered: a linked node always sits one layer after its source, and only an edge that closes a cycle is dropped (silently). It suits hierarchies and pipelines, not meshes.
- Data must be literals you already have. Never invent numbers to fill a layout. A widget is a snapshot: new data means a new widget.
- Images: an absolute local path, 100 KB or less per image.
- `Button("Label", @ToAssistant("instruction"))` and `Choice` send text back to you as the next turn (500 characters at most). Only that text is sent: the optional second `@ToAssistant` argument (`context`) is ignored, so put everything the next turn needs in the message. Act on the click, then render a NEW widget with the updated state.
- One widget per reply. Use `Tabs` and `Card` for several sections.

## When not to use it

A single value, a short answer, anything the user will copy into a terminal, or any surface other than the desktop app. Reply in plain text there.
