"""`hermes openui ...`: manage linked component packs from the terminal.

    hermes openui components list           what is linked, and what is broken
    hermes openui components check FILE...  check pack files before linking them
    hermes openui widgets                   the widgets rendered in this profile, newest first
    hermes openui export NAME... [--out P]  save widgets as one standalone HTML page

The functions return (exit code, text) so they are easy to test; `handle` prints.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Callable, List, Optional, Tuple

from . import bundle, export, packs, tools

LINK_HELP = (
    "Add file or folder paths to the plugin's `components` setting (Capabilities > Plugins > hermes-openui), "
    "or in config.yaml under plugins.entries.hermes-openui.settings.components. To have the agent write a pack, ask it to load skill_view('hermes-openui:custom-components')."
)


def components_list(settings: Optional[dict]) -> Tuple[int, str]:
    found, problems = tools.load_custom(settings)
    if not found and not problems:
        return 0, "No component packs are linked.\n" + LINK_HELP
    lines: List[str] = []
    for p in found:
        lines.append("%s  %d component%s, %d KB  %s" % (p.name, len(p.components), "" if len(p.components) == 1 else "s", max(1, len(p.source.encode("utf-8")) // 1024), p.path))
        lines.append("    " + ", ".join(p.components))
    if problems:
        lines += ["", "Problems (these packs are skipped):"] + ["  - %s" % x for x in problems]
    return (1 if problems else 0), "\n".join(lines)


def components_check(paths: List[str]) -> Tuple[int, str]:
    """Check pack files without linking them: the header, the forbidden-API lint, and (with Node) that the script loads
    and registers exactly the components its header lists."""
    if not paths:
        return 2, "usage: hermes openui components check FILE [FILE...]"
    lines: List[str] = []
    failed = False
    node_ran = True
    for path in paths:
        found, problems = packs.load([path], bundle.component_names())
        if problems or not found:
            failed = True
            lines.append("FAIL  %s" % path)
            lines += ["  - %s" % x for x in (problems or ["no pack found"])]
            continue
        errs = tools._node_validate("root = Stack([])", found)
        if errs is None:
            node_ran = False
        elif errs:
            failed = True
            lines.append("FAIL  %s" % path)
            lines += ["  - %s" % x for x in errs]
            continue
        lines.append("OK    %s  (%s: %s)" % (path, found[0].name, ", ".join(found[0].components)))
    if not node_ran:
        lines.append("")
        lines.append("Node was not found, so only the header and the forbidden-API lint were checked. Install Node 18+ to also load each script.")
    return (1 if failed else 0), "\n".join(lines)


def widgets_list(limit: int = 20) -> Tuple[int, str]:
    """The widgets rendered in this profile, newest first. The name shown is what `export` and export_widgets take."""
    folder = tools.widgets_dir()
    files = sorted((f for f in folder.glob("*") if f.suffix in (".html", ".oui") and f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return 0, "No widgets have been rendered in this profile yet."
    lines = ["%-34s  %7s  %s" % ("NAME", "SIZE", "RENDERED")]
    for f in files[:limit]:
        st = f.stat()
        lines.append("%-34s  %5d KB  %s" % (f.stem, max(1, st.st_size // 1024), time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))))
    if len(files) > limit:
        lines.append("... and %d older" % (len(files) - limit))
    return 0, "\n".join(lines)


def export_command(widgets: List[str], title: Optional[str], out: Optional[str], overwrite: bool, theme: str, settings: Optional[dict]) -> Tuple[int, str]:
    """Save widgets as one standalone HTML page: the same code path the export_widgets tool uses."""
    params = {"sections": [{"widget": w} for w in widgets], "overwrite": bool(overwrite), "theme": theme}
    if title:
        params["title"] = title
    if out:
        params["path"] = out
    result = json.loads(export.export_widgets(params, settings=settings))
    if result.get("ok"):
        return 0, "Saved %s (%d KB, %d section%s)" % (result["path"], max(1, result["bytes"] // 1024), result["sections"], "" if result["sections"] == 1 else "s")
    return 1, "Not exported:\n" + "\n".join("  - %s" % e for e in result.get("errors", ["unknown error"]))


def setup_parser(parser) -> None:
    sub = parser.add_subparsers(dest="openui_cmd")
    comp = sub.add_parser("components", help="work with linked component packs")
    csub = comp.add_subparsers(dest="components_cmd")
    csub.add_parser("list", help="show the linked packs and any problems")
    chk = csub.add_parser("check", help="check pack files before linking them")
    chk.add_argument("paths", nargs="+", metavar="FILE")
    sub.add_parser("widgets", help="list the widgets rendered in this profile, newest first")
    ex = sub.add_parser("export", help="save widgets as one standalone HTML page")
    ex.add_argument("widgets", nargs="+", metavar="WIDGET", help="names from `hermes openui widgets`")
    ex.add_argument("--title", help="page title (default: Hermes report)")
    ex.add_argument("--out", metavar="PATH", help="a .html file or a folder; default is the exports folder of this profile")
    ex.add_argument("--overwrite", action="store_true", help="replace an existing file")
    ex.add_argument("--theme", choices=("auto", "light", "dark"), default="auto")
    parser.set_defaults(_openui_parser=parser)


def handle(args, settings: Optional[dict], out: Callable[[str], None] = print) -> int:
    if getattr(args, "openui_cmd", None) == "components" and getattr(args, "components_cmd", None) in ("list", "check"):
        if args.components_cmd == "list":
            code, text = components_list(settings)
        else:
            code, text = components_check(list(args.paths))
        out(text)
        return code
    if getattr(args, "openui_cmd", None) == "widgets":
        code, text = widgets_list()
        out(text)
        return code
    if getattr(args, "openui_cmd", None) == "export":
        code, text = export_command(list(args.widgets), args.title, args.out, args.overwrite, args.theme, settings)
        out(text)
        return code
    parser = getattr(args, "_openui_parser", None)
    out(parser.format_help() if parser is not None else "usage: hermes openui components {list,check}")
    return 0


def run(args, settings: Optional[dict]) -> None:
    """Entry point Hermes calls; exits non-zero when a command reports a problem."""
    code = handle(args, settings)
    if code:
        sys.exit(code)
