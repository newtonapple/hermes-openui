"""Runs INSIDE Hermes's own interpreter against an isolated HERMES_HOME. Verifies the real runtime: discovery, tool registration,
availability for a desktop (tui) session, dispatch, and a profile-aware output path. Usage: HERMES_HOME=<iso> python verify_runtime.py"""
import json
import os
import sys

home = os.environ["HERMES_HOME"]
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))
import model_tools  # noqa: E402  (importing it runs plugin discovery)
from tools.registry import registry  # noqa: E402

entry = registry.get_entry("render_widget")
print("registered:", bool(entry), "| toolset:", getattr(entry, "toolset", None))

try:
    from toolsets import resolve_toolset  # noqa: E402

    print("toolset 'widgets' resolves to:", resolve_toolset("widgets"))
except Exception as e:  # noqa: BLE001
    print("resolve_toolset failed:", e)

from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.tools_config import _get_platform_tools  # noqa: E402

# The desktop/TUI gateway builds its toolsets from the CLI platform's saved list (tui_gateway/agent_factory.py).
enabled = sorted(_get_platform_tools(load_config(), "cli", include_default_mcp_servers=True))
print("'widgets' toolset enabled for the desktop/CLI platform by default:", "widgets" in enabled, "| %d toolsets enabled" % len(enabled))

defs = model_tools.get_tool_definitions(enabled_toolsets=enabled, quiet_mode=True)
names = [d["function"]["name"] for d in defs]
print("render_widget in the tool array:", "render_widget" in names, "| total tools:", len(names), "| bridge tools:", [n for n in names if n.startswith("tool_")])

src = 'root = Stack([t, c])\nt = Text("Runtime check", "title")\nc = BarChart(["a","b","c"], [3, 5, 2])'
out = json.loads(model_tools.handle_function_call("render_widget", {"source": src, "name": "runtime-check"}))
print("dispatch ok:", out.get("ok"), "| mode:", out.get("mode"), "| packs:", out.get("packs"), "| checked:", out.get("checked"), "| bytes:", out.get("bytes"))
path = out["directive"].split('"')[1]
print("file under the isolated home:", path.startswith(home), "|", os.path.relpath(path, home))
