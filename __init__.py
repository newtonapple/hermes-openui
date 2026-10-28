"""hermes-openui: rich inline widgets (charts, DAG/ER diagrams, maps, dashboards) for the Hermes desktop app.

Python half of a unified Hermes plugin: the `render_widget` tool and a bundled skill. The optional desktop half
(desktop/plugin.js) renders widgets natively in the transcript; see README.md.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import cli, export, schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    def settings():
        """The plugin's settings, read at call time so a change in Capabilities > Plugins applies without a restart."""
        out = {}
        for key, default in (("components", []), ("export_dir", "")):
            try:
                out[key] = ctx.get_config(key, default)
            except Exception:
                out[key] = default
        return out

    def render_widget(params, **kwargs):
        try:
            mode = ctx.get_config("mode", "preview")
        except Exception:
            mode = "preview"
        kwargs.pop("settings", None)
        return tools.render_widget(params, mode=mode if mode in ("preview", "native") else "preview", settings=settings(), **kwargs)

    ctx.register_tool(
        name="render_widget",
        toolset="widgets",
        schema=schemas.RENDER_WIDGET,
        handler=render_widget,
        description="Draw charts, graphs, DAG/ER diagrams, maps and dashboards.",
        emoji="🧩",
    )

    def export_widgets(params, **kwargs):
        kwargs.pop("settings", None)
        return export.export_widgets(params, settings=settings(), **kwargs)

    ctx.register_tool(
        name="export_widgets",
        toolset="widgets",
        schema=schemas.EXPORT_WIDGETS,
        handler=export_widgets,
        description="Export widgets or a report as one standalone HTML file.",
        emoji="\U0001F4E4",
    )

    register_cli = getattr(ctx, "register_cli_command", None)
    if register_cli:  # an older Hermes without CLI commands must not take the tool down with it
        try:
            register_cli("openui", "Manage hermes-openui component packs", cli.setup_parser, lambda args: cli.run(args, settings()))
        except Exception:
            logger.debug("hermes-openui: could not register the openui CLI command", exc_info=True)

    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                try:
                    ctx.register_skill(child.name, skill_md)
                except Exception:  # an older Hermes without register_skill must not take the tool down with it
                    logger.debug("hermes-openui: could not register skill %s", child.name, exc_info=True)
