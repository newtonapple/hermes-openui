"""hermes-openui: rich inline widgets (charts, DAG/ER diagrams, maps, dashboards) for the Hermes desktop app.

Python half of a unified Hermes plugin: the `render_widget` tool and a bundled skill. The optional desktop half
(desktop/plugin.js) renders widgets natively in the transcript; see README.md.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    def render_widget(params, **kwargs):
        # Read the mode at call time so a change in Capabilities > Plugins applies without a restart.
        try:
            mode = ctx.get_config("mode", "preview")
        except Exception:
            mode = "preview"
        return tools.render_widget(params, mode=mode if mode in ("preview", "native") else "preview", **kwargs)

    ctx.register_tool(
        name="render_widget",
        toolset="widgets",
        schema=schemas.RENDER_WIDGET,
        handler=render_widget,
        description="Draw charts, graphs, DAG/ER diagrams, maps and dashboards.",
        emoji="🧩",
    )

    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                try:
                    ctx.register_skill(child.name, skill_md)
                except Exception:  # an older Hermes without register_skill must not take the tool down with it
                    logger.debug("hermes-openui: could not register skill %s", child.name, exc_info=True)
