---
name: openui-render
description: "Patterns and pitfalls for render_widget: dashboards, charts, DAG/ER diagrams, maps."
version: 0.2.1
---

# render_widget patterns

`render_widget(source=<OpenUI Lang>)` validates the source, saves a widget and returns a one-line directive. Put it ALONE on its own line in your reply, after at most one sentence. The widget appears when the turn ends.

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
| Pipeline, dependency graph, tree of steps | `Dag` |
| How servers and services connect (infrastructure, network) | `InfraMap` |
| Database schema | `Erd` |
| Places | `GeoMap` (country or region scale; coastlines only) |
| Ask the user to choose | `Choice` |
| Alternate views of one subject | `Tabs`, with a `Card` per view |

## Rules that are easy to break

- Arguments are POSITIONAL. `Stack(children, direction: "row")` silently breaks; write `Stack(children, "row")`.
- `root = Stack([...])` comes first. Every other variable must be reachable from `root` or it will not render.
- Chart `labels` and every series `values` array must be the same length.
- Edges, relations and links name the node id, entity name or point label as a STRING, never a variable.
- `InfraMap`: an `InfraLink` names a node id, never a label (`InfraLink("web", "pg")`). About four zones and twelve nodes fit the column; more scroll sideways unseen. Set `status` only if the user or a tool gave it.
- `Dag`: leave `direction` as `null`; it picks left-to-right or top-to-bottom to fit the column. Keep labels short (about ten characters). Edges have no labels; put link details in a `Table`. Layout is layered: a linked node sits one layer after its source, and only an edge that closes a cycle is dropped, silently. It suits hierarchies and pipelines, not meshes.
- Data must be literals you already have. Never invent numbers to fill a layout. A widget is a snapshot: new data means a new widget.
- Images: an absolute local path, 100 KB or less per image.
- `Button("Label", @ToAssistant("instruction"))` and `Choice` send text back as your next turn (500 characters at most). Only that text is sent; the optional second `@ToAssistant` argument (`context`) is ignored, so put everything the next turn needs in the message. Act on the click, then render a NEW widget.
- One widget per reply. Use `Tabs` and `Card` for several sections.

## Export to a file

When the user asks to save, share or export what you drew, or wants a report as a file, call `export_widgets`.

- `sections`: one per widget or block. Each is `{title?, source | widget}`. `widget` names a widget rendered earlier in this chat: the file name in its directive, without `.html`.
- To export several widgets, give each its own section. To write a report, compose sections from `Markdown`, `Metric` rows, `Table` and charts.
- Leave `path` out unless the user named a place. If a path is refused, say why and offer the default folder. Do not work around a refusal.
- Reply with the result's `media_tag` alone on its own line, no backticks. Never paste the HTML.

## Custom components

If the end of `render_widget(reference=true)` has a "Custom components" section, the user linked packs. Use them like built-ins (preview mode only). To add a component the user asks for, load `skill_view('hermes-openui:custom-components')`. Do not invent a name.

## When not to use it

A single value, a short answer, anything to copy into a terminal, or any surface but the desktop app. Reply in plain text there.
