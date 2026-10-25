"""Tool schema: what the model reads to decide when to call render_widget.

Keep the description SHORT, but rich in the words people actually say. With Tool Search on (the default) only the first sentence appears
in the always-visible listing (clipped to ~60 characters) and the whole description is what the BM25 search indexes; with it off, the whole
description rides on every API call. The component reference is deliberately NOT here: render_widget(reference=true) returns it on demand.
Recall was measured (tools/verify_discovery.py): adding graph/plot/flowchart/schema/topology/KPI took keyword recall from 13/20 to 20/20.
"""

RENDER_WIDGET = {
    "name": "render_widget",
    "description": (
        "Draw charts, graphs, DAG/ER diagrams, maps and dashboards. "
        "Show data visually in the Hermes desktop chat as an interactive inline widget written in OpenUI Lang: KPI metric tiles, tables, tabs, cards, "
        "bar/line/area/pie/radar charts and plots, flowcharts, DAG pipelines, ER database schemas, network topology, offline maps, code blocks, markdown, "
        "FAQs and clickable Choice questions. "
        "Pass the OpenUI Lang as `source`; the tool validates it and returns a one-line directive to put ALONE on its own line in your reply. "
        "Call it once with reference=true first to get the exact component signatures. "
        "Desktop app only. For a single value or a short answer, reply in plain text instead."
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
