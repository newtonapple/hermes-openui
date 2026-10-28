#!/usr/bin/env python3
"""Layout check for native mode: the real desktop/plugin.js, a stub SDK, one headless Chrome launch.

usage: python3 tools/verify_native.py [--plugin FILE] [--png OUT.png] [--json OUT.json] [--widths 360,640,1000,1800,2400]
                                      [--theme dark|light] [--app-css FILE|auto]

Builds one page (build/tests/native-harness.mjs) that draws the same 15 widgets, through the plugin's own directive render, in
chat columns of several widths, then screenshots it and measures every widget through tools/shoot.py --html --eval. It prints a
table (column width, widget width and height, scrollers, left offset and size of the first diagram, image or table) and checks:
widgets fill their column, nothing overflows its column, diagrams stay left aligned, images never grow past their natural size,
the widget does not inherit `overflow-wrap:anywhere`, and in a 360 px column the wide components get their own scroller.
Exit 1 when a check fails.

--app-css FILE inlines the Hermes Desktop stylesheet and wraps every widget in the wrapper elements the app puts around a message
(the Tailwind Typography `.prose` block and its overflow-wrap rule reach the widget that way). `auto` takes the newest
~/.hermes/hermes-agent/apps/desktop/dist/assets/index-*.css. Default: not used, so the run is offline and deterministic.
--theme picks the stub's theme tokens (default dark). The tokens are approximations of the app's, not its palette.

It proves layout of the plugin's output in plain Chrome. It does not run Hermes Desktop: the real message column, its padding and
the app's theme tokens are assumptions here, and with --app-css the wrapper chain is a copy of the app's classes, not its React
tree (see docs/development.md, native mode).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import shoot  # noqa: E402

EXAMPLES = ROOT / "docs" / "ui-components" / "examples"
WIDGETS = (
    "metric-tones", "table-wide", "bar-chart-load", "line-chart-series", "pie-chart-default", "tabs-overview", "dag-pipeline",
    "erd-schema", "infra-map-web-platform", "geo-map-world", "radar-chart-compare", "markdown-code-table", "code-block-python",
    "image-caption",
)
BUTTON_AND_CHOICE = (  # Button and Choice together, in one small widget
    'root = Stack([ask, actions])\n'
    'ask = Choice("Which node should I restart first?", ["web-1", "web-2", "web-3"], "Pick one. I will restart it and report back.")\n'
    'actions = Stack([a, b], "row", "s", true)\n'
    'a = Button("Restart nginx", @ToAssistant("Restart the nginx service on web-1"))\n'
    'b = Button("Show logs", @ToAssistant("Show the last 50 lines of the nginx log on web-1"))\n'
)
NARROW = 360  # the narrow chat column the scroller check is about
NEEDS_SCROLLER_AT_360 = ("infra-map-web-platform", "dag-pipeline", "erd-schema", "table-wide", "code-block-python")
DIAGRAMS = ("infra-map-web-platform", "dag-pipeline", "erd-schema")


def load_widgets():
    page, lint, _bundle, _packs = shoot.load_modules()
    out = []
    for name in WIDGETS:
        source = lint.strip_fences(shoot.docs_source((EXAMPLES / (name + ".oui")).read_text(encoding="utf-8")))
        out.append({"name": name, "source": page.inline_images(source)})
    out.append({"name": "button-and-choice", "source": BUTTON_AND_CHOICE})
    return out


def run(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise SystemExit("%s failed:\n%s%s" % (cmd[0], r.stdout, r.stderr))
    return r.stdout


def find_app_css():
    """The newest compiled stylesheet of an installed Hermes Desktop, or None."""
    found = glob.glob(os.path.expanduser("~/.hermes/hermes-agent/apps/desktop/dist/assets/index-*.css"))
    return max(found, key=os.path.getmtime) if found else None


def chrome_available():
    try:
        shoot.find_chrome(None)
    except SystemExit:  # find_chrome ends the process when there is none
        return False
    return True


def measure(plugin: Path, widths, png: Path, theme="dark", app_css=None):
    """Returns (rows, shoot summary). One Chrome launch."""
    with tempfile.TemporaryDirectory() as td:
        cfg, page = Path(td) / "cfg.json", Path(td) / "page.html"
        cfg.write_text(json.dumps({"widths": widths, "widgets": load_widgets()}), encoding="utf-8")
        node = ["node", str(ROOT / "build" / "tests" / "native-harness.mjs"), "--plugin", str(plugin), "--config", str(cfg), "--out", str(page), "--theme", theme]
        if app_css:
            node += ["--app-css", str(app_css)]
        run(node, 120)
        out = run([sys.executable, str(ROOT / "tools" / "shoot.py"), "--html", str(page), str(png), "--theme", theme, "--width", str(max(widths)),
                   "--scale", "1", "--eval", "measureAll()"], 180)
    line = [l for l in out.splitlines() if l.startswith("eval: ")]
    if not line:
        raise SystemExit("no measurement came back:\n" + out)
    rows = json.loads(line[-1][len("eval: "):])
    # measureAll() lists the cells in page order: one block of widgets per width
    names = [w["name"] for w in load_widgets()]
    for i, row in enumerate(rows):
        row["width"] = widths[i // len(names)]
    return rows, out.splitlines()[0]


def problems(rows):
    bad = []
    for r in rows:
        tag = "%s @%d" % (r["widget"], r["width"])
        if r.get("error"):
            bad.append("%s: %s" % (tag, r["error"]))
            continue
        if r["w"] != r["container"]:
            bad.append("%s: widget is %d px in a %d px column" % (tag, r["w"], r["container"]))
        if r["rootOverflow"] or r["slotOverflow"]:
            bad.append("%s: content overflows the column" % tag)
        m = r["media"][0] if r["media"] else None
        if r["widget"] in DIAGRAMS and m and m["x"] != 0:
            bad.append("%s: diagram is not left aligned (x=%d)" % (tag, m["x"]))
        if m and m["tag"] == "img" and m["w"] > m["nat"] + 2:  # + 2: the 1 px border
            bad.append("%s: image drawn at %d px, natural size is %d" % (tag, m["w"], m["nat"]))
        if r["wrap"] != "normal" or r["cellWrap"] not in ("", "normal"):
            bad.append("%s: inherits overflow-wrap %s (the preview page has normal)" % (tag, r["cellWrap"] if r["wrap"] == "normal" else r["wrap"]))
        if r["width"] == NARROW and r["widget"] in NEEDS_SCROLLER_AT_360 and not r["scrollers"]:
            bad.append("%s: expected its own scroller" % tag)
    return bad


def table(rows):
    lines = ["%-24s %5s %5s %5s  %-22s %s" % ("widget", "col", "w", "h", "first diagram/image/table", "scrollers")]
    for r in rows:
        if r.get("error"):
            lines.append("%-24s %5d  %s" % (r["widget"], r["container"], r["error"]))
            continue
        m = r["media"][0] if r["media"] else None
        first = "%s x=%d %dx%d" % (m["tag"], m["x"], m["w"], m["h"]) if m else "-"
        lines.append("%-24s %5d %5d %5d  %-22s %s" % (r["widget"], r["container"], r["w"], r["h"], first, ",".join(r["scrollers"][:3]) or "-"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plugin", default=str(ROOT / "desktop" / "plugin.js"), help="plugin file to draw (default: desktop/plugin.js)")
    ap.add_argument("--png", help="keep the screenshot here")
    ap.add_argument("--json", help="write the measurements here")
    ap.add_argument("--widths", default="360,640,1000,1800,2400", help="comma separated column widths in CSS px")
    ap.add_argument("--theme", choices=("dark", "light"), default="dark", help="theme tokens of the stub (approximations of the app's); default dark")
    ap.add_argument("--app-css", metavar="FILE", help="inline the Hermes Desktop stylesheet and wrap widgets like the app does; FILE or `auto` (newest installed). Default: off")
    a = ap.parse_args(argv)
    app_css = None
    if a.app_css:
        app_css = find_app_css() if a.app_css == "auto" else a.app_css
        if not app_css or not Path(app_css).is_file():
            raise SystemExit("no app stylesheet found (%s)" % a.app_css)
    widths = [int(x) for x in a.widths.split(",")]
    if not shutil.which("node"):
        raise SystemExit("needs Node")
    png = Path(a.png).resolve() if a.png else Path(tempfile.mkdtemp()) / "native.png"
    rows, summary = measure(Path(a.plugin).resolve(), widths, png, a.theme, app_css)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(summary)
    print(table(rows))
    bad = problems(rows)
    print("\n%d widgets x %d widths, %d problem(s)" % (len(rows) // len(widths), len(widths), len(bad)))
    for b in bad:
        print("  - " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
