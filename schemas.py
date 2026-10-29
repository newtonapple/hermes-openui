"""Tool schema: what the model reads to decide when to call render_widget.

Keep the description SHORT, but rich in the words people actually say. With Tool Search on (the default) only the first sentence appears
in the always-visible listing (clipped to ~60 characters) and the whole description is what the BM25 search indexes; with it off, the whole
description rides on every API call. The component reference is deliberately NOT here: render_widget(reference=true) returns it on demand.
Recall was measured (tools/verify_discovery.py): adding graph/plot/flowchart/schema/topology/KPI took keyword recall from 13/20 to 20/20. Adding infrastructure/server/architecture took the 25-query set from 21 to 25. Adding the sequence words (call flow, request flow, message sequence chart) is measured the same way.
"""

RENDER_WIDGET = {
    "name": "render_widget",
    "description": (
        "Draw charts, graphs, DAG/ER diagrams, maps and dashboards. "
        "Show data visually in the Hermes desktop chat as an inline widget in OpenUI Lang: KPI tiles, tables, tabs, cards, "
        "bar/line/area/pie/radar charts and plots, flowcharts, DAG pipelines, ER database schemas, network topology, infrastructure and server maps, architecture diagrams, "
        "sequence diagrams (call flow, request flow, message sequence chart, API call sequence), maps, code, markdown, "
        "FAQs, custom components and Choice questions. "
        "Pass OpenUI Lang as `source`; the tool validates it and returns a directive to put ALONE on its own line in your reply. "
        "Call it with reference=true first for exact component signatures. "
        "Desktop app only. For one value or a short answer, reply in plain text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "OpenUI Lang: `root = Stack([...])` first, then one `name = Component(...)` statement per line. Positional arguments, double-quoted strings, literal data only.",
            },
            "name": {
                "type": "string",
                "description": "Optional short label for the saved file, e.g. gpu-status.",
            },
            "reference": {
                "type": "boolean",
                "description": "true = return the component reference instead of rendering. Do this before your first widget.",
            },
        },
        "required": [],
    },
}


# A second tool, not a mode of render_widget: render_widget's schema and its Tool Search ranking stay exactly as measured.
# Same rules as above: short, first sentence <= 60 characters, and the words people say ("export html", "save as html", "share a report",
# "standalone page", "offline report", "export dashboard", "download chart") in the description or the parameter names. It deliberately does NOT
# repeat render_widget's vocabulary (graph, table, diagram, ...) and says "widget" once: measured with Hermes's Tool Search, doing so pushed
# render_widget out of the top 5 for bare keyword queries. With this wording all 7 export queries rank export_widgets first and render_widget's
# top-5 recall is unchanged (only the bare one-word query "dashboard" now lists export_widgets first and render_widget second).
EXPORT_WIDGETS = {
    "name": "export_widgets",
    "description": (
        "Export a report or dashboard as one standalone HTML file. "
        "Save, share or download a chart as an offline HTML page that opens in any browser (save as html, share a report). "
        "Each section is new OpenUI Lang as `source`, or a widget already shown in this chat, by name. "
        "The result is a single offline HTML file written to the exports folder or to your `path` (set `overwrite` to replace a file, `theme` for light or dark): "
        "tell the user where it is, never paste the HTML."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Page title and heading. Default: Hermes report."},
            "sections": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "description": "Report sections, top to bottom. Give each EXACTLY ONE of source or widget.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Optional heading above this section."},
                        "source": {"type": "string", "description": "OpenUI Lang, same rules as render_widget (call that with reference=true for the components)."},
                        "widget": {"type": "string", "description": "Name of a widget shown earlier in this chat: the file name from its directive, e.g. gpu-status-1a2b3c.html."},
                    },
                },
            },
            "path": {"type": "string", "description": "Absolute .html file path, or a folder. Default: this profile's exports folder."},
            "overwrite": {"type": "boolean", "description": "true = replace an existing file at `path`. Default false."},
            "theme": {"type": "string", "enum": ["auto", "light", "dark"], "description": "auto follows the viewer's OS setting."},
        },
        "required": ["sections"],
    },
}
